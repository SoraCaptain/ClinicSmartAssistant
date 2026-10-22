#!/usr/bin/env python3
"""Live E2E eval runner — replays every scenario from TEST_SCENARIOS_CASES.md
against the running stack (backend :8000 -> ai-service :8001 -> DeepSeek).

Usage:
    python3 eval/run_scenarios.py [--base-url http://localhost:8000]
                                  [--db /tmp/clinicpilot.db]
                                  [--workers 4] [--phase a|b|all] [--only ID,ID,...]

Phases:
  A  read-only scenarios, run in parallel (sections 2-7, 10/11 chat-level, 12 summary)
  B  booking-creating scenarios, run sequentially; created rows are verified via
     GET /api/bookings and then deleted straight from the DB (seed ids are never touched).
     ERROR-06/07 exercise POST /api/bookings directly (400/422 + no row).

Report: a PASS/FAIL table on stdout + full JSON (all replies) under eval/results/.
"""

from __future__ import annotations

import argparse
import json
import re
import sqlite3
import sys
import time
import urllib.error
import urllib.request
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import scenarios as scn  # noqa: E402

TURN_TIMEOUT = 180          # one LLM round trip can be slow
RETRY_WAIT = 5              # retry once after 5s on transient errors
OUTAGE_THRESHOLD = 3        # consecutive transport-ERROR scenarios -> provider outage


class TransportError(Exception):
    pass


def http_json(url: str, payload: dict | None = None, timeout: int = 30) -> tuple[int, object]:
    data = json.dumps(payload).encode() if payload is not None else None
    req = urllib.request.Request(url, data=data, method="POST" if data else "GET",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode()
            return resp.status, (json.loads(body) if body else None)
    except urllib.error.HTTPError as e:
        body = e.read().decode()
        try:
            parsed = json.loads(body)
        except ValueError:
            parsed = body
        return e.code, parsed
    except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as e:
        raise TransportError(str(e)) from e


def chat_turn(base_url: str, session_id: str, message: str) -> dict:
    """POST /api/chat with one retry on transient failure; returns parsed response."""
    last: Exception | None = None
    for attempt in (1, 2):
        try:
            status, body = http_json(f"{base_url}/api/chat",
                                     {"session_id": session_id, "message": message},
                                     timeout=TURN_TIMEOUT)
            if status >= 500:
                raise TransportError(f"HTTP {status}: {body}")
            if status != 200:
                raise RuntimeError(f"HTTP {status}: {body}")
            if not isinstance(body, dict) or "reply" not in body:
                raise RuntimeError(f"malformed chat response: {body!r}")
            return body
        except (TransportError, RuntimeError) as e:
            last = e
            if attempt == 1:
                time.sleep(RETRY_WAIT)
    raise TransportError(f"chat turn failed twice: {last}")


# --- check evaluation -----------------------------------------------------------

def check_reply(reply: str, t: dict) -> str | None:
    """Evaluate one turn's contains/not_contains/booking_created checks."""
    for group in t["contains"]:
        if not any(re.search(alt, reply, re.IGNORECASE) for alt in group):
            return f"missing fact-group {group}"
    for pat in t["not_contains"]:
        if re.search(pat, reply, re.IGNORECASE):
            return f"forbidden pattern matched: {pat}"
    return None


# --- DB helpers (cleanup lives next to the data; seeds are never deleted) --------

def db_delete_bookings(db_path: str, ids: list[str]) -> list[str]:
    ids = [i for i in ids if i and i not in scn.SEED_BOOKING_IDS]
    if not ids:
        return []
    con = sqlite3.connect(f"file:{db_path}?mode=rw", uri=True, timeout=15)
    try:
        cur = con.execute(
            "DELETE FROM patient_bookings WHERE booking_id IN (%s)"
            % ",".join("?" * len(ids)), ids)
        con.commit()
        return ids if cur.rowcount else []
    finally:
        con.close()


def db_count_bookings(db_path: str, patient_id: str) -> int:
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
    try:
        (n,) = con.execute("SELECT COUNT(*) FROM patient_bookings WHERE patient_id = ?",
                           (patient_id,)).fetchone()
        return n
    finally:
        con.close()


def get_booking_ids(base_url: str, patient_id: str = "P001") -> set[str]:
    status, body = http_json(f"{base_url}/api/bookings?patient_id={patient_id}")
    if status != 200 or not isinstance(body, list):
        raise TransportError(f"GET /api/bookings -> {status}: {body!r}")
    return {r["booking_id"] for r in body}


def get_bookings(base_url: str, patient_id: str = "P001") -> list[dict]:
    status, body = http_json(f"{base_url}/api/bookings?patient_id={patient_id}")
    if status != 200 or not isinstance(body, list):
        raise TransportError(f"GET /api/bookings -> {status}: {body!r}")
    return body


# --- scenario runners ------------------------------------------------------------

def new_result(sid: str) -> dict:
    return {"id": sid, "status": None, "first_fail": None, "turns": [],
            "post": [], "error": None, "created_booking_ids": []}


def record_turn(res: dict, say: str, resp: dict | None, fail: str | None) -> None:
    entry = {"say": say}
    if resp is not None:
        entry.update({"reply": resp.get("reply"), "intent": resp.get("intent"),
                      "booking_created": resp.get("booking_created"),
                      "session_id": resp.get("session_id")})
    if fail:
        entry["fail"] = fail
        if res["first_fail"] is None:
            res["first_fail"] = f"[{say[:40]!r}] {fail}"
    res["turns"].append(entry)


def finalize(res: dict, error: Exception | None = None) -> dict:
    if error is not None:
        res["status"] = "ERROR"
        res["error"] = f"{type(error).__name__}: {error}"
    else:
        res["status"] = "FAIL" if res["first_fail"] else "PASS"
    return res


def run_chat_scenario(scn_def: dict, base_url: str, db_path: str | None) -> dict:
    """Run a chat scenario; phase-B variants get snapshot/post/cleanup via db_path."""
    res = new_result(scn_def["id"])
    session = str(uuid.uuid4())
    before: set[str] = set()
    try:
        if db_path:
            before = get_booking_ids(base_url)
        for t in scn_def["turns"]:
            try:
                resp = chat_turn(base_url, session, t["say"])
            except TransportError as e:
                record_turn(res, t["say"], None, str(e))
                raise
            fail = check_reply(resp.get("reply") or "", t)
            if t["booking_created"] is True and not resp.get("booking_created"):
                fail = fail or "expected booking_created=true this turn"
            if t["booking_created"] is False and resp.get("booking_created"):
                fail = fail or "booking_created must be null this turn"
            if resp.get("booking_created"):
                res["created_booking_ids"].append(resp["booking_created"].get("booking_id"))
            record_turn(res, t["say"], resp, fail)
        if db_path:
            run_post_checks(scn_def, res, base_url, db_path, before)
    except TransportError as e:
        if db_path and res["created_booking_ids"]:
            try:  # best-effort cleanup so an ERROR never leaks rows
                doomed = sorted(set(res["created_booking_ids"]))
                res["cleanup"] = {"deleted": db_delete_bookings(db_path, doomed),
                                  "leftover": []}
            except Exception as ce:  # noqa: BLE001
                res["cleanup"] = {"deleted": [], "error": str(ce)}
        return finalize(res, e)
    return finalize(res)


def run_post_checks(scn_def: dict, res: dict, base_url: str, db_path: str, before: set[str]):
    post = scn_def.get("post", {})
    rows = get_bookings(base_url)
    after_ids = {r["booking_id"] for r in rows}
    new_ids = after_ids - before

    def fail(msg: str):
        res["post"].append(msg)
        if res["first_fail"] is None:
            res["first_fail"] = f"[post] {msg}"

    for exp in post.get("expect_bookings", []):
        hit = next((r for r in rows
                    if r["patient_id"] == "P001"
                    and r["doctor_id"] == exp["doctor_id"]
                    and r["treatment_id"] == exp["treatment_id"]
                    and r["booking_date"] == exp["booking_date"]
                    and str(r["booking_time"])[:5] == exp["booking_time"][:5]), None)
        if hit is None:
            fail(f"persisted booking not found for {exp}")
        else:
            res["created_booking_ids"].append(hit["booking_id"])
            names = post.get("expect_names")
            if names:
                for field, frag in names.items():
                    if frag.lower() not in str(hit.get(field, "")).lower():
                        fail(f"joined field {field}={hit.get(field)!r} lacks {frag!r}")
    for sid in post.get("expect_seed_ids", []):
        if sid not in after_ids:
            fail(f"seed booking {sid} missing from booking list")
    if post.get("no_create") and new_ids:
        fail(f"booking must not be created, but got new ids {sorted(new_ids)}")

    # cleanup: delete everything this scenario created (never seeds)
    doomed = sorted({i for i in res["created_booking_ids"] if i} | new_ids)
    deleted = db_delete_bookings(db_path, doomed)
    leftover = get_booking_ids(base_url) - before
    if leftover:
        fail(f"cleanup incomplete, leftover ids {sorted(leftover)}")
    res["cleanup"] = {"deleted": deleted, "leftover": sorted(leftover)}


def run_summarize_scenario(scn_def: dict, base_url: str) -> dict:
    res = new_result(scn_def["id"])
    try:
        status, body = http_json(f"{base_url}/api/summarize/transcript",
                                 {"transcript": scn.SUMMARY_TRANSCRIPT}, timeout=TURN_TIMEOUT)
        if status >= 500:
            raise TransportError(f"HTTP {status}: {body}")
        if status != 200:
            return finalize(res, RuntimeError(f"HTTP {status}: {body}"))
        res["response"] = body
        for field, groups in scn.SUMMARY_FIELD_CHECKS.items():
            val = str(body.get(field, ""))
            if not val:
                res["first_fail"] = res["first_fail"] or f"field {field} empty"
                continue
            for group in groups:
                if not any(re.search(alt, val, re.IGNORECASE) for alt in group):
                    msg = f"field {field}={val!r} missing {group}"
                    res["first_fail"] = res["first_fail"] or msg
    except TransportError as e:
        return finalize(res, e)
    return finalize(res)


def run_api_case(case: dict, base_url: str, db_path: str) -> dict:
    res = new_result(case["id"])
    nr = case["no_row"]
    try:
        n_before = db_count_bookings(db_path, nr["patient_id"])
        status, body = http_json(f"{base_url}/api/bookings", case["payload"], timeout=30)
        res["status_code"] = status
        res["response"] = body
        text = json.dumps(body) if not isinstance(body, str) else body
        if status not in case["accept_status"]:
            res["first_fail"] = (f"HTTP {status} not in {case['accept_status']}: "
                                 f"{text[:200]}")
        else:
            for group in case["body_contains"]:
                if not any(re.search(alt, text, re.IGNORECASE) for alt in group):
                    msg = f"response body missing {group}"
                    res["first_fail"] = res["first_fail"] or msg
        n_after = db_count_bookings(db_path, nr["patient_id"])
        if nr["patient_id"] == "P999":
            if n_after:
                res["first_fail"] = res["first_fail"] or f"row created for P999 ({n_after})"
        elif n_after != n_before:
            res["first_fail"] = (res["first_fail"]
                                 or f"row count changed {n_before} -> {n_after}")
        res["post"].append(f"no-row check: {nr['patient_id']} {n_before}->{n_after}")
    except TransportError as e:
        return finalize(res, e)
    return finalize(res)


# --- orchestration ----------------------------------------------------------------

def preflight(base_url: str, db_path: str) -> list[str]:
    problems = []
    status, body = http_json(f"{base_url}/api/health")
    if status != 200 or not isinstance(body, dict) or body.get("status") != "ok":
        problems.append(f"/api/health -> {status}: {body!r}")
    status, body = http_json(f"{base_url}/api/clinics?search=metro")
    if status != 200 or not isinstance(body, list) or not body:
        problems.append(f"/api/clinics?search=metro -> {status}: {body!r} "
                        "(stale code? reloaded catalog search missing)")
    ids = get_booking_ids(base_url)
    for sid in ("B1001", "B1004"):
        if sid not in ids:
            problems.append(f"seed booking {sid} missing for P001 (seeds not loaded?)")
    con = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=15)
    try:
        rows = con.execute("SELECT booking_id FROM patient_bookings").fetchall()
    finally:
        con.close()
    if not {r[0] for r in rows} >= {"B1001", "B1004"}:
        problems.append(f"DB {db_path} lacks seed bookings — wrong --db path?")
    return problems


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--base-url", default="http://localhost:8000")
    ap.add_argument("--db", default="/tmp/clinicpilot.db",
                    help="sqlite DB the live backend uses (for booking cleanup)")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--phase", choices=["a", "b", "all"], default="all")
    ap.add_argument("--only", help="comma-separated scenario ids to run (debug)")
    args = ap.parse_args()

    out_dir = Path(__file__).parent / "results"
    out_dir.mkdir(exist_ok=True)

    problems = preflight(args.base_url, args.db)
    if problems:
        print("BLOCKED — stack not healthy / DB mismatch:")
        for p in problems:
            print(f"  - {p}")
        return 2

    only = {s.strip() for s in args.only.split(",")} if args.only else None
    results: list[dict] = []
    started = time.monotonic()
    outage = False
    consecutive_errors = 0

    def should_run(s):
        return (not only or s["id"] in only) and not outage

    # ---- Phase A: read-only, parallel ----
    phase_a = [s for s in scn.PHASE_A if should_run(s)]
    if phase_a and args.phase in ("a", "all"):
        print(f"== Phase A: {len(phase_a)} read-only scenarios, "
              f"{args.workers} workers ==", flush=True)
        with ThreadPoolExecutor(max_workers=args.workers) as pool:
            futs = {pool.submit(run_chat_scenario, s, args.base_url, None): s
                    for s in phase_a}
            for fut in as_completed(futs):
                res = fut.result()
                results.append(res)
                consecutive_errors = consecutive_errors + 1 if res["status"] == "ERROR" else 0
                if consecutive_errors >= OUTAGE_THRESHOLD:
                    outage = True
                print(f"  [{res['status']:>5}] {res['id']} "
                      f"({time.monotonic() - started:.0f}s elapsed)", flush=True)
        if outage:
            print("!! provider outage suspected after Phase A — aborting", flush=True)
    results.sort(key=lambda r: r["id"])

    # ---- Phase B: booking-creating, sequential ----
    if not outage and args.phase in ("b", "all"):
        phase_b = [s for s in scn.PHASE_B if should_run(s)]
        print(f"== Phase B: {len(phase_b)} booking scenarios (sequential) ==", flush=True)
        for s in phase_b:
            res = run_chat_scenario(s, args.base_url, args.db)
            results.append(res)
            consecutive_errors = consecutive_errors + 1 if res["status"] == "ERROR" else 0
            if consecutive_errors >= OUTAGE_THRESHOLD:
                outage = True
                print("!! provider outage suspected — marking remaining cases ERROR",
                      flush=True)
            print(f"  [{res['status']:>5}] {res['id']} "
                  f"({time.monotonic() - started:.0f}s elapsed)", flush=True)
            if outage:
                break
        if not outage:
            api_cases = [c for c in scn.API_CASES if not only or c["id"] in only]
            print(f"== API cases: {len(api_cases)} (POST /api/bookings) ==", flush=True)
            for c in api_cases:
                res = run_api_case(c, args.base_url, args.db)
                results.append(res)
                print(f"  [{res['status']:>5}] {res['id']}", flush=True)
    if outage:
        done = {r["id"] for r in results}
        for s in scn.PHASE_A + scn.PHASE_B + scn.API_CASES:
            if s["id"] not in done and (not only or s["id"] in only):
                r = new_result(s["id"])
                r["status"] = "ERROR"
                r["error"] = "skipped: provider outage"
                results.append(r)

    # ---- final integrity: seeds intact, no leftover created rows ----
    integrity = {"seeds_present": True, "leftover_p001": []}
    try:
        ids = get_booking_ids(args.base_url)
        integrity["seeds_present"] = {"B1001", "B1004"} <= ids
        integrity["leftover_p001"] = sorted(ids - scn.SEED_BOOKING_IDS)
    except TransportError as e:
        integrity["error"] = str(e)

    # ---- report ----
    passed = sum(1 for r in results if r["status"] == "PASS")
    failed_ids = [r["id"] for r in results if r["status"] != "PASS"]
    total = len(results)

    print("\n" + "=" * 100)
    print(f"{'CASE':<22} {'RESULT':<7} FIRST FAILING CHECK / REPLY SNIPPET")
    print("-" * 100)
    for r in sorted(results, key=lambda x: x["id"]):
        snippet = (r["first_fail"] or r["error"] or "")[:120]
        if r["status"] == "PASS":
            snippet = ""
            if r["turns"]:
                snippet = (r["turns"][-1].get("reply") or "")[:120]
        print(f"{r['id']:<22} {r['status']:<7} {snippet}")
    print("-" * 100)
    print(f"{passed}/{total} passed; failing: {', '.join(failed_ids) or 'none'}")
    print(f"integrity: seeds_present={integrity['seeds_present']} "
          f"leftover={integrity['leftover_p001'] or 'none'}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    out_file = out_dir / f"run_{stamp}.json"
    payload = {
        "started": datetime.now().isoformat(),
        "base_url": args.base_url,
        "db": args.db,
        "elapsed_sec": round(time.monotonic() - started, 1),
        "summary": {"passed": passed, "total": total, "failing_ids": failed_ids},
        "integrity": integrity,
        "results": sorted(results, key=lambda r: r["id"]),
    }
    out_file.write_text(json.dumps(payload, indent=2))
    print(f"full JSON: {out_file}")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
