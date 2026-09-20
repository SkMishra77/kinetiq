"""End-to-end scenario from the design brief.

Day 1: log bench 60kg×8,7 / 57.5kg×8. Day 3 (rotation returns Upper A):
`plan_next_session` should retrieve history and suggest bench near 60 kg. When
the user hits 60×10×3, the analyzer flips the verdict to `progressed` and the
next plan pulls 62.5 kg from the pending adjustment.
"""
import pytest
from fastmcp import Client


PROFILE = {
    "patch": {
        "height_cm": 178, "age_years": 29, "sex": "male",
        "training_experience": "intermediate", "primary_goal": "muscle_gain",
        "days_per_week": 4, "session_minutes": 60,
        "equipment": [
            {"equipment": "barbell", "increment_kg": 2.5},
            {"equipment": "dumbbell", "increment_kg": 2.0},
            {"equipment": "cable", "increment_kg": 2.5},
            {"equipment": "machine", "increment_kg": 5.0},
        ],
    },
}
PROGRAM = {
    "program": {
        "name": "UL-4", "goal": "muscle_gain", "split_type": "upper_lower",
        "days_per_week": 4,
        "sessions": [
            {"name": "Upper A", "target_muscles": ["chest", "lats"],
             "exercises": [
                 {"exercise": "Bench Press", "sets": 3, "rep_min": 6, "rep_max": 10, "rest_s": 180},
                 {"exercise": "Incline DB press", "sets": 3, "rep_min": 8, "rep_max": 12, "rest_s": 120},
                 {"exercise": "Lat Pulldown", "sets": 3, "rep_min": 8, "rep_max": 12, "rest_s": 120},
             ]},
            {"name": "Lower A", "target_muscles": ["quads", "hamstrings"],
             "exercises": [
                 {"exercise": "Barbell Back Squat", "sets": 3, "rep_min": 5, "rep_max": 8, "rest_s": 240},
                 {"exercise": "Romanian Deadlift", "sets": 3, "rep_min": 6, "rep_max": 10, "rest_s": 180},
                 {"exercise": "Leg Press", "sets": 3, "rep_min": 10, "rep_max": 15, "rest_s": 120},
             ]},
        ],
    },
}


@pytest.mark.asyncio
async def test_day1_to_day4(server):
    async with Client(server) as c:
        r = await c.call_tool("save_profile", PROFILE)
        assert r.data["onboarding_missing"] == []
        r = await c.call_tool("create_program", PROGRAM)
        assert r.data["status"] == "stored"

        # Day 1 — Upper A
        p = (await c.call_tool("plan_next_session", {})).data
        assert p["template_name"] == "Upper A"
        r = (await c.call_tool("log_workout", {
            "performed_on": "2026-09-01",
            "template_id": p["template_id"],
            "exercises": [
                {"exercise": "Bench Press", "sets_shorthand": "60kg × 8, 60kg × 7, 57.5kg × 8"},
                {"exercise": "Incline Dumbbell Press", "sets_shorthand": "22.5kg × 10 × 3"},
                {"exercise": "Lat Pulldown", "sets_shorthand": "55kg × 10, 55kg × 9, 50kg × 10"},
            ],
        })).data
        assert r["status"] == "stored"
        assert any(v["exercise"] == "Barbell Bench Press" and v["status"] == "first_time"
                   for v in r["analysis"]["per_exercise"])

        # Day 2 — Lower A
        pl = (await c.call_tool("plan_next_session", {})).data
        assert pl["template_name"] == "Lower A"
        await c.call_tool("log_workout", {
            "performed_on": "2026-09-03",
            "template_id": pl["template_id"],
            "exercises": [
                {"exercise": "Barbell Back Squat", "sets_shorthand": "80kg × 5 × 3"},
                {"exercise": "Romanian Deadlift", "sets_shorthand": "90kg × 8 × 3"},
                {"exercise": "Leg Press", "sets_shorthand": "120kg × 12 × 3"},
            ],
        })

        # Day 3 — Upper A rolls back around; suggested load = last top (60).
        p2 = (await c.call_tool("plan_next_session", {})).data
        assert p2["template_name"] == "Upper A"
        bench = next(pe for pe in p2["exercises"] if pe["exercise"] == "Barbell Bench Press")
        assert bench["suggested_load_kg"] == 60.0

        # Nail rep_max on every set → engine progresses to +2.5 kg.
        r3 = (await c.call_tool("log_workout", {
            "performed_on": "2026-09-05",
            "template_id": p2["template_id"],
            "exercises": [
                {"exercise": "Bench Press", "sets_shorthand": "60kg × 10 × 3"},
                {"exercise": "Incline Dumbbell Press", "sets_shorthand": "22.5kg × 12 × 3"},
                {"exercise": "Lat Pulldown", "sets_shorthand": "55kg × 12 × 3"},
            ],
        })).data
        bench_v = next(v for v in r3["analysis"]["per_exercise"] if v["exercise"] == "Barbell Bench Press")
        assert bench_v["status"] == "progressed"
        assert bench_v["next_action"] == "increase_load"
        assert bench_v["next_load_kg"] == 62.5

        # Rotate through Lower, then back to Upper A — plan pulls the +2.5 kg
        pl2 = (await c.call_tool("plan_next_session", {})).data
        await c.call_tool("log_workout", {
            "performed_on": "2026-09-07",
            "template_id": pl2["template_id"],
            "exercises": [
                {"exercise": "Barbell Back Squat", "sets_shorthand": "82.5 × 5 × 3"},
                {"exercise": "Romanian Deadlift", "sets_shorthand": "95 × 8 × 3"},
                {"exercise": "Leg Press", "sets_shorthand": "125 × 12 × 3"},
            ],
        })
        p4 = (await c.call_tool("plan_next_session", {"session_date": "2026-09-09"})).data
        bench = next(pe for pe in p4["exercises"] if pe["exercise"] == "Barbell Bench Press")
        assert bench["suggested_load_kg"] == 62.5
        assert bench["basis"]["source"] == "pending_adjustment_load"
