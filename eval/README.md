# Live E2E Scenario Eval

Replays every scenario from `TEST_SCENARIOS_CASES.md` against the running stack
(backend `:8000` → ai-service `:8001` → DeepSeek) and mechanically checks each turn.

## Usage

Prereqs: backend + ai-service running (host uvicorn), machine date `2026-10-22`,
seed P001 bookings B1001/B1004 present.

```bash
python3 eval/run_scenarios.py                 # full run (~20-40 min)
python3 eval/run_scenarios.py --only CLINIC-01,DOCTOR-04   # debug subset
python3 eval/run_scenarios.py --phase a       # read-only scenarios only
```

- `--db` must point at the SQLite file the live backend actually uses
  (default `/tmp/clinicpilot.db`). It is used only to delete bookings the eval
  itself created — seed ids `B1001–B1004` are never touched.
- Phase A (read-only) runs in parallel; Phase B (booking-creating) runs
  sequentially, verifies created rows via `GET /api/bookings`, then deletes them.
- `ERROR-06/07` call `POST /api/bookings` directly (expect 400/422 + no row).

## Files

- `scenarios.py` — the test suite data (turn scripts + regex fact-groups).
  `contains` = AND of OR-groups (case-insensitive regex alternatives);
  `not_contains` = must-not-match; `booking_created` = gate semantics.
- `run_scenarios.py` — runner, liveness preflight (BLOCKED on stale stack),
  retry-once per turn, provider-outage abort, PASS/FAIL table + full JSON
  under `eval/results/` (gitignored).

Note: PATIENT-05 / BOOKING-QUERY-06 ban hard cross-patient identifiers
(Alice/Robert/P002/P003/B1002/B1003/H9001), not the literal words
"Amoxicillin"/"cough" — the doc's own expected answers echo those words in a
denial, so banning them would false-fail correct behavior.
