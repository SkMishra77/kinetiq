"""get_briefing tool."""
from __future__ import annotations
from typing import Annotated, Literal

from fastmcp import FastMCP
from pydantic import Field
from mcp.types import ToolAnnotations

from ..services import Services
from ..briefing.builder import build


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="get_briefing",
        description=(
            "CALL THIS FIRST in every conversation before giving any training advice. "
            "Returns the user's profile summary, active program and rotation position, "
            "recent sessions, days since each muscle group was trained, weekly volume, "
            "PRs, open insights (pain/fatigue/plateau/etc), pending next-session "
            "adjustments, current readiness, and `state` (needs_onboarding | needs_program "
            "| ready) with a `suggested_next_call`. Never plan a workout or answer "
            "'what should I do today' without calling this first. Do not re-ask the user "
            "for information this tool already returns."
        ),
        annotations=ToolAnnotations(
            title="Get Briefing",
            readOnlyHint=True,
            destructiveHint=False,
            idempotentHint=True,
            openWorldHint=False,
        ),
    )
    def get_briefing(
        detail: Annotated[Literal["compact", "full"], Field(default="compact",
            description="'compact' (default, ~2-3k tokens) or 'full' (adds full session detail).")] = "compact",
        recent_sessions: Annotated[int, Field(default=5, ge=1, le=20,
            description="Number of recent workouts to summarise.")] = 5,
    ) -> dict:
        return build(svc.db, tz=svc.settings.timezone, detail=detail,
                      recent_sessions=recent_sessions)
