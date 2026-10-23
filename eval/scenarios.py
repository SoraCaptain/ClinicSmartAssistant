"""Scenario data for the live E2E eval (source of truth: TEST_SCENARIOS_CASES.md).

Check vocabulary (see run_scenarios.py):
- contains: list of fact-groups; a group is a list of alternative regexes (case-insensitive).
  ALL groups must match somewhere in the reply (AND of ORs).
- not_contains: regexes that must NOT match the reply.
- booking_created: True  -> reply must carry a booking object this turn
                   False -> booking_created must be null
- post (phase B): expect_bookings / no_create / names checks against GET /api/bookings.

Literal scenario text is expected here: this file IS the test suite (product code stays clean).
"""

# --- date / time alternation helpers -----------------------------------------

NOV5 = r"November 5|2026-11-05|Nov\.? 5|5 November|05 November|5 Nov"
NOV15 = r"November 15|2026-11-15|Nov\.? 15|15 November|15 Nov"
NOV20 = r"November 20|2026-11-20|Nov\.? 20|20 November|20 Nov"
NOV21 = r"November 21|2026-11-21|Nov\.? 21|21 November|21 Nov"
NOV25 = r"November 25|2026-11-25|Nov\.? 25|25 November|25 Nov"
NOV28 = r"November 28|2026-11-28|Nov\.? 28|28 November|28 Nov"
NOV30 = r"November 30|2026-11-30|Nov\.? 30|30 November|30 Nov"
DEC2 = r"December 2|2026-12-02|Dec\.? 2|2 December|02 December|2 Dec"
DEC3 = r"December 3|2026-12-03|Dec\.? 3|3 December|03 December|3 Dec"
DEC4 = r"December 4|2026-12-04|Dec\.? 4|4 December|04 December|4 Dec"
DEC5 = r"December 5|2026-12-05|Dec\.? 5|5 December|05 December|5 Dec"
DEC10 = r"December 10|2026-12-10|Dec\.? 10|10 December|10 Dec"
APR12 = r"April 12|2026-04-12|Apr\.? 12|12 April|12 Apr"

T0900 = r"9:00\s*AM|09:00|9:00|9\s*AM"
T1000 = r"10:00\s*AM|10:00|10\s*AM"
T1100 = r"11:00\s*AM|11:00|11\s*AM"
T1430 = r"2:30\s*PM|14:30|2:30"
T1300 = r"1:00\s*PM|13:00|1\s*PM"
T1500 = r"3:00\s*PM|15:00|3\s*PM"

JOINT = r"Joint\s*(?:&|and)\s*Pain"
ROSTOVA = r"Rostova"
JENKINS = r"Jenkins"
WILSON = r"Wilson"
CHANG = r"Chang"
GATE_ASK = r"confirm|shall|proceed|[Yy]es / no|book it\??"
ONLY_MATCH = r"only|matching|auto|makes sense|the (dermatolog|orthoped)"

# Cross-patient leakage markers (P002 Alice Smith, P003 Robert Johnson).
# Note: the literal words "Amoxicillin"/"cough" may legitimately appear in a *denial*
# (the doc's own expected answer echoes them), so they are NOT banned; hard
# identifiers of the other patients are.
LEAK_MARKERS = [r"Alice", r"Robert", r"\bP00[23]\b", r"\bB100[23]\b", r"\bH9001\b",
                r"Cough Syrup", r"37\.8"]

SEED_BOOKING_IDS = {"B1001", "B1002", "B1003", "B1004"}


def turn(say, contains=None, not_contains=None, booking_created=None):
    return {"say": say, "contains": contains or [], "not_contains": not_contains or [],
            "booking_created": booking_created}


def scenario(sid, turns, kind="chat", **post):
    s = {"id": sid, "kind": kind, "turns": turns}
    if post:
        s["post"] = post
    return s


# --- Phase A: read-only scenarios (parallel) ----------------------------------

PHASE_A = [
    # 2. Clinic information retrieval
    scenario("CLINIC-01", [turn(
        "What are the weekday operating hours of Metro Care Health Clinic?",
        contains=[[r"Metro Care"], [r"8:00\s*AM|8\s*AM|08:00"], [r"6:00\s*PM|6\s*PM|18:00"],
                  [r"Mon|Friday|weekday"]])]),
    scenario("CLINIC-02", [turn(
        "Is Metro Care Health Clinic open on Saturdays?",
        contains=[[r"Sat(urdays?)?"], [r"9:00\s*AM|9\s*AM|09:00"], [r"1:00\s*PM|1\s*PM|13:00"],
                  [r"\byes\b|open"]])]),
    scenario("CLINIC-03", [turn(
        "Is Sunset Wellness Center open this weekend?",
        contains=[[r"Sunset"], [r"Sat(urday)?|Sun(day)?|weekend"],
                  [r"closed|not open|isn'?t open|only (open |Monday )"]])]),
    scenario("CLINIC-04", [turn(
        "What is the cancellation policy at Metro Care Health Clinic?",
        contains=[[r"24\s*(hours|hrs|h)|twenty[- ]four"], [r"\$?\s*50|fifty"]])]),
    scenario("CLINIC-05", [turn(
        "How much notice should I give to cancel an appointment at Sunset Wellness Center?",
        contains=[[r"12\s*(hours|h)|twelve"]],
        not_contains=[r"\$\s*\d|\d+\s*(dollars|USD)"])]),  # charge amount is not in the data
    scenario("CLINIC-06", [turn(
        "What should I do in a life-threatening emergency?",
        contains=[[r"911"], [r"emergency room|hospital|ER\b"]])]),
    scenario("CLINIC-07", [turn(
        "Where can I see the dermatologist?",
        contains=[[ROSTOVA], [r"Sunset Wellness"], [r"Santa Monica|456 Ocean"]])]),

    # 3. Doctor information retrieval
    scenario("DOCTOR-01", [turn(
        "Which doctor specializes in eczema and acne?",
        # doc's accepted variant names Rostova + eczema/acne without the word "Dermatology"
        contains=[[ROSTOVA], [r"[Dd]ermatolog|eczema|acne"]])]),
    scenario("DOCTOR-02", [turn(
        "Which doctor should I contact about child development or vaccinations?",
        contains=[[CHANG], [r"[Pp]ediatric"]])]),
    scenario("DOCTOR-03", [turn(
        "Who specializes in joint pain and sports injuries?",
        # wording-flexible per doc global rule: Wilson + the conditions is the fact
        contains=[[WILSON], [r"[Oo]rthopedic|joint|sports"]])]),
    scenario("DOCTOR-04", [turn(
        "How much is a consultation with Dr. Sarah Jenkins?",
        contains=[[JENKINS], [r"150"]])]),
    scenario("DOCTOR-05", [turn(
        "Is there a doctor who speaks Mandarin?",
        contains=[[CHANG], [r"[Mm]andarin"]])]),
    scenario("DOCTOR-06", [turn(
        "Which doctor speaks Russian?",
        contains=[[ROSTOVA], [r"[Rr]ussian"]])]),
    scenario("DOCTOR-07", [turn(
        "Which doctor has the lowest consultation fee?",
        contains=[[JENKINS], [r"150"]])]),

    # 4. Treatment information retrieval
    scenario("TREATMENT-01", [turn(
        "What treatments are available?",
        contains=[[r"General Health Checkup"], [r"Pediatric Vaccination"],
                  [r"Dermatology Consultation"], [r"Flu Shot"], [JOINT]])]),
    scenario("TREATMENT-02", [turn(
        "How should I prepare for a General Health Checkup?",
        contains=[[r"8\s*(hours|h)|eight hours|eight-hour"], [r"fast"]])]),
    scenario("TREATMENT-03", [turn(
        "What should I do before a Dermatology Consultation?",
        contains=[[r"clean"], [r"makeup|lotion"]])]),
    scenario("TREATMENT-04", [turn(
        "Do I need to prepare for a flu shot?",
        contains=[[r"no (special |prior )?preparation|no prep|not need|don'?t need|none"],
                  [r"fever"]])]),
    scenario("TREATMENT-05", [turn(
        "What should I wear for a Joint & Pain Consultation?",
        contains=[[r"loose"], [r"clothing|clothes"]])]),
    scenario("TREATMENT-06", [turn(
        "How much does a Dermatology Consultation cost, and how long does it take?",
        contains=[[r"200"], [r"30\s*(min|minutes)|thirty"]])]),
    scenario("TREATMENT-07", [turn(
        "What should I bring for a Pediatric Vaccination?",
        contains=[[r"vaccination record|record booklet|booklet"]])]),

    # 5. Recommendation and grounding
    scenario("RECOMMEND-01", [turn(
        "I have itchy skin and a rash. Which available service and doctor are most relevant?",
        contains=[[r"Dermatology Consultation"], [ROSTOVA]])]),
    scenario("RECOMMEND-02", [turn(
        "My knee has been hurting. What service and doctor should I consider?",
        contains=[[JOINT], [WILSON]])]),
    scenario("RECOMMEND-03", [turn(
        "I want a routine annual checkup. What should I book?",
        contains=[[r"General Health Checkup"], [JENKINS]])]),
    scenario("RECOMMEND-04", [turn(
        "I think I have a food allergy. Can I book an allergy test?",
        contains=[[r"not|cannot|can'?t|isn'?t|unavailable|no allergy test"],
                  [r"General Health Checkup"]],
        booking_created=False)]),
    scenario("RECOMMEND-05", [turn(
        "I have tooth pain. Which dentist can I book?",
        contains=[[r"no dentist|not (available|listed)|no dental|cannot|can'?t|unable|don'?t have"],
                  [r"dental|dentist"]],
        booking_created=False)]),

    # 6. Personalized patient context
    scenario("PATIENT-01", [turn(
        "Do I have any known allergies?",
        contains=[[r"[Pp]enicillin"], [r"[Pp]eanut"]])]),
    scenario("PATIENT-02", [turn(
        "What was my last recorded visit?",
        contains=[[APR12], [JENKINS], [r"checkup|check-up|check up"]])]),
    scenario("PATIENT-03", [turn(
        "Have I seen Dr. Sarah Jenkins before?",
        contains=[[JENKINS], [APR12]])]),
    scenario("PATIENT-04", [turn(
        "What did the doctor note during my previous health checkup?",
        contains=[[r"120/80"], [r"glucose"], [r"exercise"],
                  [r"three times|3x|3 times|per week"]])]),
    scenario("PATIENT-05", [turn(
        "Was I prescribed Amoxicillin for a cough?",
        contains=[[r"\bno\b|not|don'?t|doesn'?t|no record"]],
        not_contains=LEAK_MARKERS)]),
    scenario("PATIENT-06", [turn(
        "I am allergic to Penicillin. Is that recorded in my profile?",
        contains=[[r"[Yy]es"], [r"[Pp]enicillin"], [r"[Pp]eanut"]],
        not_contains=[r"dos(e|ing)|mg\b"])]),

    # 7. Existing booking queries
    scenario("BOOKING-QUERY-01", [turn(
        "When is my next appointment?",
        # status is supplementary (doc tolerates shorter core answers, cf. PATIENT-02)
        contains=[[NOV5], [T0900], [JENKINS], [r"General Health Checkup"]])]),
    scenario("BOOKING-QUERY-02", [turn(
        "Show me all my upcoming appointments.",
        # doc acceptance: "Both records must be present" (status per row is wording)
        contains=[[NOV5], [NOV15], [JENKINS], [WILSON], [r"General Health Checkup"], [JOINT]])]),
    scenario("BOOKING-QUERY-03", [turn(
        "Who is the doctor for my next appointment?",
        contains=[[JENKINS]])]),
    scenario("BOOKING-QUERY-04", [turn(
        "Do I have an appointment with Dr. James Wilson?",
        # "Confirmed" omitted from the doc's accepted short variant, so not required
        contains=[[WILSON], [NOV15], [T1100], [r"\byes\b|you have"]])]),
    scenario("BOOKING-QUERY-05", [turn(
        "How many upcoming appointments do I have?",
        contains=[[r"\btwo\b|\b2\b"], [r"appointment"]])]),
    scenario("BOOKING-QUERY-06", [turn(
        "Do I have a dermatology appointment on November 6?",
        contains=[[r"\bno\b|not|don'?t|no dermatology|isn'?t"]],
        not_contains=[r"Alice", r"\bP002\b", r"\bB1002\b", r"2:30\s*PM|14:30"])]),
    scenario("BOOKING-QUERY-07", [turn(
        "I want to cancel my booking on November 5.",
        # honest refusal: deterministic text, clinic phone + policy verbatim
        contains=[[r"can'?t cancel|cannot cancel|unable to cancel"],
                  [r"\+1-555-019-2831"],
                  [r"24 hours|24-hour"]],
        not_contains=[r"noted your request", r"(?:I'?ve |has been |successfully )?cancelled (?:it|your booking)",
                      r"I(?:'| a)m cancelling", r"\bcancelled\b"],
        booking_created=False)]),

    # 10. Intent switching (read-only instance)
    scenario("INTENT-01", [
        turn("How much does Dr. Elena Rostova charge?", contains=[[r"220"]]),
        turn("By the way, when is my next appointment?",
             contains=[[NOV5], [T0900], [JENKINS], [r"General Health Checkup"]]),
    ]),

    # 11. Validation and error handling (chat level)
    scenario("ERROR-01", [turn(
        "Book an appointment with Dr. Superman tomorrow at 10 AM.",
        contains=[[r"Superman"], [r"not|cannot|can'?t|unavailable|couldn'?t|not found|isn'?t"]],
        booking_created=False)]),
    scenario("ERROR-02", [turn(
        "Book an Allergy Test for November 20, 2026, at 10 AM.",
        contains=[[r"[Aa]llergy [Tt]est"], [r"not|cannot|can'?t|unavailable|isn'?t"]],
        booking_created=False)]),
    scenario("ERROR-03", [turn(
        "Book a General Health Checkup with Dr. Sarah Jenkins on February 30, 2027, at 10 AM.",
        contains=[[r"February 30|2027-02-30|Feb 30"],
                  [r"valid|invalid|not a (valid )?(date|real)|exist"]],
        booking_created=False)]),
    scenario("ERROR-04", [turn(
        "Book a Dermatology Consultation for October 20, 2026, at 2 PM.",
        contains=[[r"past"], [r"future|valid|choose|select|provide|another date"]],
        booking_created=False)]),
    scenario("ERROR-05", [turn(
        "I need an appointment.",
        contains=[[r"treatment|service|care"], [r"[Ww]hat|[Ww]hich|would you|help"]],
        booking_created=False)]),

    # 12. Structured transcript summary (direct API, read-only)
    scenario("SUMMARY-01", [], kind="summarize"),
]

SUMMARY_TRANSCRIPT = (
    "Patient: I have had knee pain for two weeks after running. Doctor: This appears to be "
    "a mild overuse injury. Take acetaminophen as directed on the label and avoid running "
    "for one week. Return if the pain gets worse."
)
SUMMARY_FIELD_CHECKS = {  # per-field contains groups (AND of ORs)
    "chief_complaint": [[r"knee"], [r"pain"], [r"run|two weeks|2 weeks"]],
    "diagnosis": [[r"overuse|mild"]],
    "medication": [[r"acetaminophen"]],
    "doctor_instructions": [[r"run|rest|avoid"], [r"week|worse|return"]],
}

# --- Phase B: booking-creating scenarios (sequential) --------------------------

PHASE_B = [
    scenario("BOOKING-CREATE-01", [
        turn("Book a Dermatology Consultation with Dr. Elena Rostova on November 20, 2026, at 2:30 PM.",
             contains=[[r"Dermatology Consultation"], [ROSTOVA], [NOV20], [T1430], [GATE_ASK]],
             booking_created=False),
        turn("Yes, please book it.",
             contains=[[ROSTOVA], [NOV20], [T1430], [r"booked|confirmed|[Cc]onfirmation"]],
             booking_created=True),
    ], expect_bookings=[{"doctor_id": "D103", "treatment_id": "T003",
                         "booking_date": "2026-11-20", "booking_time": "14:30"}]),

    scenario("BOOKING-CREATE-02", [
        turn("I want to book a Dermatology Consultation on November 20, 2026, at 2:30 PM.",
             contains=[[r"Dermatology Consultation"], [ROSTOVA], [NOV20], [T1430], [ONLY_MATCH]],
             booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D103", "treatment_id": "T003",
                         "booking_date": "2026-11-20", "booking_time": "14:30"}]),

    scenario("BOOKING-CREATE-03", [
        turn("I want to book Dr. James Wilson on November 21, 2026, at 10:00 AM.",
             contains=[[WILSON], [JOINT], [NOV21], [T1000], [ONLY_MATCH]],
             booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D104", "treatment_id": "T005",
                         "booking_date": "2026-11-21", "booking_time": "10:00"}]),

    scenario("BOOKING-CREATE-04", [
        turn("Book a General Health Checkup with Dr. Sarah Jenkins at 9:30 AM.",
             contains=[[r"date|when|which day"]], booking_created=False),
    ], no_create=True),

    scenario("BOOKING-CREATE-05", [
        turn("Book a General Health Checkup with Dr. Sarah Jenkins on November 25, 2026.",
             contains=[[r"time|when"]], booking_created=False),
    ], no_create=True),

    scenario("BOOKING-CREATE-06", [
        turn("I want to book a Joint & Pain Consultation.",
             contains=[[WILSON], [r"date|when|which day"]], booking_created=False),
        turn("November 28, 2026.", contains=[[r"time|when"]], booking_created=False),
        turn("3 PM.",
             contains=[[JOINT], [WILSON], [NOV28], [T1500], [GATE_ASK]], booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D104", "treatment_id": "T005",
                         "booking_date": "2026-11-28", "booking_time": "15:00"}]),

    scenario("BOOKING-CREATE-07", [
        turn("I have a persistent skin rash. Which available service is relevant?",
             contains=[[r"Dermatology Consultation"], [ROSTOVA]], booking_created=False),
        turn("Book the recommended option for December 2, 2026, at 11 AM.",
             contains=[[r"Dermatology Consultation"], [ROSTOVA], [DEC2], [T1100], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D103", "treatment_id": "T003",
                         "booking_date": "2026-12-02", "booking_time": "11:00"}]),

    scenario("BOOKING-CREATE-08", [
        turn("Book a Dermatology Consultation with Dr. James Wilson on November 30, 2026, at 10 AM.",
             contains=[[r"[Oo]rthopedic"], [ROSTOVA],
                       [r"mismatch|while|not match|instead|or book|would you like"]],
             booking_created=False),
    ], no_create=True),

    scenario("INTENT-02", [
        turn("Book a Dermatology Consultation with Dr. Elena Rostova on December 4, 2026, at 1 PM.",
             contains=[[r"Dermatology Consultation"], [ROSTOVA], [DEC4], [T1300], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
        turn("How should I prepare for it?",
             contains=[[r"clean"], [r"makeup|lotion"]], booking_created=False),
    ], expect_bookings=[{"doctor_id": "D103", "treatment_id": "T003",
                         "booking_date": "2026-12-04", "booking_time": "13:00"}]),

    scenario("INTENT-03", [
        turn("I want to book a General Health Checkup with Dr. Sarah Jenkins.",
             contains=[[r"date|when|which day"]], booking_created=False),
        turn("Before that, what is Metro Care Health Clinic's cancellation policy?",
             contains=[[r"24\s*(hours|hrs|h)|twenty[- ]four"], [r"\$?\s*50|fifty"]],
             booking_created=False),
        turn("Okay, book it for December 5, 2026, at 10 AM.",
             contains=[[r"General Health Checkup"], [JENKINS], [DEC5], [T1000], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D101", "treatment_id": "T001",
                         "booking_date": "2026-12-05", "booking_time": "10:00"}]),

    scenario("PERSIST-01", [
        turn("Book a Flu Shot Injection with Dr. Sarah Jenkins on December 3, 2026, at 10:00 AM.",
             contains=[[r"Flu Shot"], [JENKINS], [DEC3], [T1000], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
        turn("Show me my appointments on December 3, 2026.",
             contains=[[r"Flu Shot"], [JENKINS], [DEC3]], booking_created=False),
    ], expect_bookings=[{"doctor_id": "D101", "treatment_id": "T004",
                         "booking_date": "2026-12-03", "booking_time": "10:00"}]),

    scenario("PERSIST-02", [
        turn("Book a Pediatric Vaccination with Dr. Michael Chang on December 10, 2026, at 9:00 AM.",
             contains=[[r"Pediatric Vaccination"], [CHANG], [DEC10], [T0900], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
    ], expect_bookings=[{"doctor_id": "D102", "treatment_id": "T002",
                         "booking_date": "2026-12-10", "booking_time": "09:00"}],
        expect_names={"doctor_name": "Chang", "treatment_name": "Pediatric Vaccination"},
        expect_seed_ids=["B1001", "B1004"]),

    scenario("DEMO", [
        turn("Do I have any known allergies?",
             contains=[[r"[Pp]enicillin"], [r"[Pp]eanut"]], booking_created=False),
        turn("I also have a persistent skin rash. Which available service is most relevant?",
             contains=[[r"Dermatology Consultation"], [ROSTOVA]], booking_created=False),
        turn("Book the recommended option for November 20, 2026.",
             contains=[[r"time|when"]], booking_created=False),
        turn("2:30 PM.",
             contains=[[r"Dermatology Consultation"], [ROSTOVA], [NOV20], [T1430], [GATE_ASK]],
             booking_created=False),
        turn("Yes.", booking_created=True),
        turn("Show me all my upcoming appointments.",
             contains=[[NOV5], [NOV15], [NOV20], [r"General Health Checkup"], [JOINT],
                       [r"Dermatology Consultation"]], booking_created=False),
    ], expect_bookings=[{"doctor_id": "D103", "treatment_id": "T003",
                         "booking_date": "2026-11-20", "booking_time": "14:30"}]),
]

# --- Direct booking-API validation cases ---------------------------------------

API_CASES = [
    {
        "id": "ERROR-06",
        "payload": {"patient_id": "P001", "doctor_id": "D103"},
        "accept_status": [400, 422],
        # structured validation error must identify the missing fields
        "body_contains": [[r"treatment"], [r"date"], [r"time"]],
        "no_row": {"patient_id": "P001"},
    },
    {
        "id": "ERROR-07",
        "payload": {"patient_id": "P999", "doctor_id": "D103", "treatment_id": "T003",
                    "booking_date": "2026-12-01", "booking_time": "10:00:00"},
        "accept_status": [404, 400, 422],
        "body_contains": [[r"[Pp]atient"]],
        "no_row": {"patient_id": "P999"},
    },
]
