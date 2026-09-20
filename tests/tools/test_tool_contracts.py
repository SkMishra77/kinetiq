"""Ensure the 22-tool contract stays stable — a snapshot test.

Fails if a tool name, its readOnly/destructive annotation, or its description's
first line changes without an intentional update. Regenerate by inspecting
`tests/golden/tool_contracts.json` and re-approving.
"""
import json
from pathlib import Path

import pytest
from fastmcp import Client


GOLDEN = Path(__file__).parent.parent / "golden" / "tool_contracts.json"

EXPECTED_TOOLS = {
    "get_briefing", "save_profile", "log_checkin", "log_pain_or_injury",
    "search_exercises", "add_exercise", "compare_exercises",
    "create_program", "get_program", "edit_session_template", "set_program_phase",
    "plan_next_session", "log_workout", "amend_workout", "analyze_workout",
    "get_exercise_history", "get_training_history", "update_insight",
    "search_knowledge", "search_research", "save_finding",
    "export_training_data",
}


@pytest.mark.asyncio
async def test_tool_set_and_annotations(server):
    async with Client(server) as c:
        tools = await c.list_tools()
    names = {t.name for t in tools}
    missing = EXPECTED_TOOLS - names
    extra = names - EXPECTED_TOOLS
    assert not missing, f"missing tools: {missing}"
    assert not extra, f"unexpected tools: {extra}"
    # Every tool must have annotations + a non-empty description.
    for t in tools:
        assert t.annotations is not None, f"{t.name} has no annotations"
        assert t.description, f"{t.name} has no description"
    # Save a snapshot for humans to diff.
    snap = sorted([
        {
            "name": t.name,
            "read_only": t.annotations.read_only_hint if t.annotations else None,
            "destructive": t.annotations.destructive_hint if t.annotations else None,
            "open_world": t.annotations.open_world_hint if t.annotations else None,
            "description_head": (t.description or "").splitlines()[0][:120],
        }
        for t in tools
    ], key=lambda x: x["name"])
    GOLDEN.parent.mkdir(parents=True, exist_ok=True)
    GOLDEN.write_text(json.dumps(snap, indent=2) + "\n", encoding="utf-8")


@pytest.mark.asyncio
async def test_get_briefing_shape(server):
    async with Client(server) as c:
        r = await c.call_tool("get_briefing", {})
    assert r.data["state"] in ("needs_onboarding", "needs_program", "ready")
    for k in ("today", "timezone", "profile", "program", "guidance",
              "suggested_next_call", "trainer_directives"):
        assert k in r.data, f"missing key: {k}"


@pytest.mark.asyncio
async def test_only_amend_workout_is_destructive(server):
    async with Client(server) as c:
        tools = await c.list_tools()
    destructive = {t.name for t in tools if t.annotations and t.annotations.destructive_hint}
    assert destructive == {"amend_workout"}, destructive
