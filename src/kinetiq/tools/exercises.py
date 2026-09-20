"""search_exercises, add_exercise, compare_exercises tools."""
from __future__ import annotations
from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from pydantic import Field
from mcp.types import ToolAnnotations

from ..services import Services
from ..db.repos import exercises as exr
from ..db.repos import profile as pr
from ..db.repos import knowledge as kr


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="search_exercises",
        description=(
            "Find exercises in the library by name/alias, muscle, equipment or "
            "movement pattern. With `respect_profile=True` (default) excludes "
            "exercises marked cannot/avoid, filters by available equipment, and "
            "marks entries that conflict with open issues. Each result carries "
            "muscles, equipment, load type, default increment and evidence "
            "summary. Use when designing programs, finding substitutions, or "
            "answering 'which exercise for X'."
        ),
        annotations=ToolAnnotations(
            title="Search Exercises", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def search_exercises(
        query: Annotated[str | None, Field(default=None,
            description="Name or alias substring.")] = None,
        muscle: Annotated[str | None, Field(default=None,
            description="Muscle name from the taxonomy (e.g. 'lats').")] = None,
        movement_pattern: Annotated[str | None, Field(default=None)] = None,
        equipment: Annotated[list[str] | None, Field(default=None)] = None,
        respect_profile: Annotated[bool, Field(default=True)] = True,
        limit: Annotated[int, Field(default=15, ge=1, le=50)] = 15,
    ) -> dict:
        results = exr.search(svc.db, query=query, muscle=muscle,
                              movement_pattern=movement_pattern,
                              equipment=equipment, limit=limit)
        excluded_ids: set[int] = set()
        if respect_profile:
            prof = pr.profile_snapshot(svc.db)
            avail = {e["equipment"] for e in (prof.get("equipment") or []) if e.get("available")}
            if avail:
                results = [r for r in results if r["equipment"] in avail or r["equipment"] == "bodyweight"]
            for p in (prof.get("preferences") or []):
                if p["kind"] in ("cannot", "avoid"):
                    excluded_ids.add(p["exercise_id"])
            results = [r for r in results if r["id"] not in excluded_ids]
        return {"count": len(results), "exercises": results}

    @mcp.tool(
        name="add_exercise",
        description=(
            "Add a custom exercise not in the library (or an alias for an "
            "existing one via `aliases`). Check search_exercises first to avoid "
            "duplicates. Set `source='user'` unless the caller is an internal "
            "seed loader. Returns the created exercise."
        ),
        annotations=ToolAnnotations(
            title="Add Exercise", readOnlyHint=False, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def add_exercise(
        name: Annotated[str, Field(min_length=2, max_length=120)],
        movement_pattern: str,
        equipment: str,
        primary_muscles: list[str],
        aliases: Annotated[list[str], Field()] = [],
        secondary_muscles: Annotated[list[str], Field()] = [],
        load_type: str = "external",
        laterality: str = "bilateral",
        is_compound: bool = True,
        default_increment_kg: float = 2.5,
        cues: str | None = None,
        contraindication_tags: Annotated[list[str], Field()] = [],
    ) -> dict:
        try:
            row = exr.create_exercise(
                svc.db, name=name, movement_pattern=movement_pattern,
                equipment=equipment, load_type=load_type, laterality=laterality,
                primary_muscles=primary_muscles, secondary_muscles=secondary_muscles,
                is_compound=is_compound, default_increment_kg=default_increment_kg,
                cues=cues, contraindication_tags=contraindication_tags,
                aliases=aliases,
            )
        except Exception as e:  # noqa: BLE001
            raise ToolError(f"could not create exercise: {e}")
        return {"exercise": row, "echo": f"Added exercise: {row['name']} ({row['slug']})"}

    @mcp.tool(
        name="compare_exercises",
        description=(
            "Rank candidate exercises for a `muscle` + `goal` combination using "
            "evidence strength, muscle emphasis, equipment fit and issue-safety. "
            "If `candidates` is empty the tool scores all matching library entries. "
            "Flags `insufficient_evidence` when the library has no verified evidence "
            "for the pair — Claude should say so rather than invent."
        ),
        annotations=ToolAnnotations(
            title="Compare Exercises", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def compare_exercises(
        muscle: Annotated[str, Field(description="Muscle from the taxonomy.")],
        goal: Annotated[str, Field(default="muscle_gain")] = "muscle_gain",
        candidates: Annotated[list[str] | None, Field(default=None,
            description="Optional list of exercise names to compare; empty scores all matching.")] = None,
        limit: Annotated[int, Field(default=6, ge=1, le=15)] = 6,
    ) -> dict:
        if candidates:
            pool: list[dict] = []
            for name in candidates:
                r = exr.resolve_name(svc.db, name)
                if not r.exercise_id:
                    continue
                pool.append(exr.get_by_id(svc.db, r.exercise_id))  # type: ignore[arg-type]
        else:
            pool = exr.search(svc.db, muscle=muscle, limit=40)
        scored: list[dict] = []
        for ex in pool:
            if not ex:
                continue
            sel = ex.get("selection_scores") or {}
            base = float(sel.get(goal, 3))
            emphasis = 2 if muscle in (ex.get("primary_muscles") or []) else \
                       1 if muscle in (ex.get("secondary_muscles") or []) else 0
            notes = kr.search_notes(svc.db, exercise_id=ex["id"], goal=goal, limit=3)
            evidence_bonus = 0.5 if any(n.get("citations") for n in notes) else 0.0
            scored.append({
                "slug": ex["slug"], "name": ex["name"],
                "score": base + emphasis + evidence_bonus,
                "muscle_emphasis": "primary" if emphasis == 2 else "secondary" if emphasis == 1 else "none",
                "equipment": ex["equipment"], "movement_pattern": ex["movement_pattern"],
                "evidence_summary": ex.get("evidence_summary"),
                "insufficient_evidence": not bool(notes),
                "citations": [c for n in notes for c in (n.get("citations") or [])],
            })
        scored.sort(key=lambda x: x["score"], reverse=True)
        return {"muscle": muscle, "goal": goal,
                 "candidates": scored[:limit],
                 "notice": "'score' is a ranking guide, not a substitute for training judgment."}
