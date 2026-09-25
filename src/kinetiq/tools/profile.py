"""save_profile, log_checkin, log_pain_or_injury tools."""
from __future__ import annotations

from typing import Annotated

from fastmcp import FastMCP
from fastmcp.exceptions import ToolError
from mcp.types import ToolAnnotations
from pydantic import Field

from ..db.repos import checkins as ck
from ..db.repos import exercises as exr
from ..db.repos import issues as iss
from ..db.repos import profile as pr
from ..domain.dates import iso_utc, parse_date
from ..domain.models import ProfileUpdate
from ..services import Services


def register(mcp: FastMCP, svc: Services) -> None:
    @mcp.tool(
        name="save_profile",
        description=(
            "Create or update the user's persistent profile with a partial patch "
            "(omitted fields stay unchanged; lists replace when provided). Use "
            "during onboarding after gathering the details conversationally, and "
            "whenever the user reports a change (goal, schedule, equipment, "
            "preferences, injuries, body weight). Injuries in the payload are "
            "written to `issues` and will make plan_next_session substitute or "
            "cap loads next time. Exercise names in preferences/injuries are "
            "resolved via the library; unresolved names come back in `unresolved`. "
            "Returns the full updated profile snapshot and `onboarding_missing` "
            "so you know what to still ask."
        ),
        annotations=ToolAnnotations(
            title="Save Profile", readOnlyHint=False, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def save_profile(patch: ProfileUpdate) -> dict:
        data = patch.model_dump(exclude_unset=True)
        changed = list(data.keys())
        reason = data.pop("change_reason", None)

        # Resolve exercise names in preferences into ids
        unresolved: list[dict] = []

        def resolve_ids(names: list[str]) -> list[int]:
            ids: list[int] = []
            for n in names:
                res = exr.resolve_name(svc.db, n)
                if res.exercise_id:
                    ids.append(res.exercise_id)
                else:
                    unresolved.append({"input": n, "candidates": res.candidates})
            return ids

        pref_like_ids = pref_dislike_ids = pref_cannot_ids = pref_avoid_ids = None
        if data.get("preferences_like") is not None:
            pref_like_ids = resolve_ids(data.pop("preferences_like") or [])
        if data.get("preferences_dislike") is not None:
            pref_dislike_ids = resolve_ids(data.pop("preferences_dislike") or [])
        if data.get("preferences_cannot") is not None:
            pref_cannot_ids = resolve_ids(data.pop("preferences_cannot") or [])
        if data.get("preferences_avoid") is not None:
            pref_avoid_ids = resolve_ids(data.pop("preferences_avoid") or [])

        equipment = data.pop("equipment", None)
        injuries = data.pop("injuries", None)
        limitations = data.pop("limitations", None)
        weight_kg = data.pop("weight_kg", None)
        body_fat_pct = data.pop("body_fat_pct", None)
        measurements = data.pop("measurements", None)

        pr.upsert_profile(svc.db, data, changed, reason)

        if equipment is not None:
            pr.replace_equipment(svc.db, equipment)
        if any(x is not None for x in (pref_like_ids, pref_dislike_ids, pref_cannot_ids, pref_avoid_ids)):
            pr.replace_preferences(svc.db, pref_like_ids, pref_dislike_ids,
                                    pref_cannot_ids, pref_avoid_ids)
        if injuries is not None:
            # Also open issues for active injuries
            pr.replace_injuries(svc.db, injuries)
            for inj in injuries:
                if inj.get("status") == "active":
                    iss.open_issue(
                        svc.db, kind="injury",
                        body_region=inj["body_region"],
                        side=inj.get("side", "both"),
                        severity=6,
                        description=inj["description"],
                        restrictions={"avoid_patterns": inj.get("affected_patterns", [])},
                        linked_exercise_id=None,
                        source="onboarding",
                    )
        if limitations is not None:
            pr.replace_limitations(svc.db, limitations)
        if weight_kg is not None or measurements is not None or body_fat_pct is not None:
            pr.add_body_metric(svc.db, iso_utc()[:10], weight_kg, body_fat_pct,
                                "onboarding",
                                measurements if measurements is None else measurements,
                                None)
        # Mark onboarding complete if all required fields present
        prof = pr.profile_snapshot(svc.db)
        missing = pr.missing_onboarding(prof)
        if not missing:
            pr.mark_onboarding_complete(svc.db)
        return {
            "profile": prof,
            "onboarding_missing": missing,
            "unresolved": unresolved,
            "echo": _profile_echo(prof, changed),
        }

    @mcp.tool(
        name="log_checkin",
        description=(
            "Record non-workout data for a date: body weight, sleep hours and "
            "quality, energy, per-muscle soreness (0-5), stress, resting heart "
            "rate. One row per date (calling again on the same date updates). "
            "Feeds the fatigue engine and the bodyweight trend. Use whenever the "
            "user mentions any of these outside a workout report."
        ),
        annotations=ToolAnnotations(
            title="Log Check-in", readOnlyHint=False, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def log_checkin(
        checkin_on: Annotated[str | None, Field(default=None,
            description="'today' (default) / 'yesterday' / ISO date.")] = None,
        bodyweight_kg: Annotated[float | None, Field(default=None, ge=30, le=300)] = None,
        sleep_hours: Annotated[float | None, Field(default=None, ge=0, le=16)] = None,
        sleep_quality: Annotated[int | None, Field(default=None, ge=1, le=5)] = None,
        energy: Annotated[int | None, Field(default=None, ge=1, le=5)] = None,
        soreness: Annotated[dict | None, Field(default=None,
            description="{'muscle': 0-5}, e.g. {'chest': 3}.")] = None,
        stress: Annotated[int | None, Field(default=None, ge=1, le=5)] = None,
        resting_hr: Annotated[int | None, Field(default=None, ge=25, le=200)] = None,
        notes: Annotated[str | None, Field(default=None)] = None,
    ) -> dict:
        date_iso = parse_date(checkin_on, svc.settings.timezone).isoformat()
        cid = ck.upsert_checkin(
            svc.db, checkin_on=date_iso, bodyweight_kg=bodyweight_kg,
            sleep_hours=sleep_hours, sleep_quality=sleep_quality, energy=energy,
            soreness=soreness, stress=stress, resting_hr=resting_hr, notes=notes,
        )
        if bodyweight_kg is not None:
            pr.add_body_metric(svc.db, date_iso, bodyweight_kg, None, "checkin", None, notes)
        trend = ck.bodyweight_trend(svc.db)
        return {"checkin_id": cid, "checkin_on": date_iso, "bodyweight_trend": trend,
                "echo": _checkin_echo(date_iso, bodyweight_kg, sleep_hours, energy)}

    @mcp.tool(
        name="log_pain_or_injury",
        description=(
            "Open, update or resolve a pain / injury / limitation. Setting status='active' "
            "makes plan_next_session substitute or cap loads on affected patterns. "
            "For pain reported DURING a specific exercise, use log_workout's per-exercise "
            "`pain_score` field instead."
        ),
        annotations=ToolAnnotations(
            title="Log Pain or Injury", readOnlyHint=False, destructiveHint=False,
            idempotentHint=False, openWorldHint=False,
        ),
    )
    def log_pain_or_injury(
        action: Annotated[str, Field(pattern="^(open|update|resolve)$",
            description="'open' (new), 'update' (existing), or 'resolve'.")],
        issue_id: Annotated[int | None, Field(default=None)] = None,
        kind: Annotated[str, Field(default="pain",
            pattern="^(pain|injury|limitation)$")] = "pain",
        body_region: Annotated[str | None, Field(default=None)] = None,
        side: Annotated[str, Field(default="both",
            pattern="^(left|right|both|na)$")] = "both",
        severity: Annotated[int, Field(default=0, ge=0, le=10)] = 0,
        description: Annotated[str | None, Field(default=None)] = None,
        affected_patterns: Annotated[list[str] | None, Field(default=None)] = None,
        affected_exercises: Annotated[list[str] | None, Field(default=None)] = None,
        load_cap_pct: Annotated[float | None, Field(default=None, ge=0.1, le=1.0)] = None,
    ) -> dict:
        if action == "open":
            if not body_region or not description:
                raise ToolError("open requires body_region and description")
            avoid_ids: list[int] = []
            for name in (affected_exercises or []):
                r = exr.resolve_name(svc.db, name)
                if r.exercise_id:
                    avoid_ids.append(r.exercise_id)
            restrictions: dict = {}
            if affected_patterns:
                restrictions["avoid_patterns"] = affected_patterns
            if avoid_ids:
                restrictions["avoid_exercise_ids"] = avoid_ids
            if load_cap_pct:
                restrictions["load_cap_pct"] = float(load_cap_pct)
            iid = iss.open_issue(
                svc.db, kind=kind, body_region=body_region, side=side,
                severity=severity, description=description,
                restrictions=restrictions, linked_exercise_id=None,
            )
            return {"issue_id": iid, "status": "open",
                     "echo": f"Opened {kind} on {body_region} ({side}), severity {severity}"}
        if action == "update":
            if issue_id is None:
                raise ToolError("update requires issue_id")
            iss.update_issue(svc.db, issue_id, severity=severity or None,
                              description=description)
            return {"issue_id": issue_id, "status": "updated"}
        # resolve
        if issue_id is None:
            raise ToolError("resolve requires issue_id")
        iss.update_issue(svc.db, issue_id, status="resolved")
        return {"issue_id": issue_id, "status": "resolved"}

    @mcp.tool(
        name="get_body_trends",
        description=(
            "Return body weight, body fat %, and measurement trends over time. "
            "Use when the user asks 'how has my weight changed', 'show my body "
            "composition progress', or 'what are my measurements'. Returns "
            "time-series data points and summary statistics."
        ),
        annotations=ToolAnnotations(
            title="Get Body Trends", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_body_trends(
        days: Annotated[int, Field(default=90, ge=7, le=365,
            description="Look-back window in days.")] = 90,
    ) -> dict:
        return pr.body_composition_trend(svc.db, days=days)

    @mcp.tool(
        name="get_physique_report",
        description=(
            "Evaluate body proportions against the user's aesthetic goal "
            "(aesthetic_vtaper, aesthetic_balanced, classic_physique). Returns "
            "measurement ratios (shoulder-to-waist, chest-to-waist, calf-to-arm), "
            "a proportionality score 0-100, lagging body parts with volume "
            "adjustment suggestions, and left-right symmetry issues. Requires "
            "body measurements in the profile. Use when the user asks about "
            "their physique balance, proportions, or V-taper progress."
        ),
        annotations=ToolAnnotations(
            title="Get Physique Report", readOnlyHint=True, destructiveHint=False,
            idempotentHint=True, openWorldHint=False,
        ),
    )
    def get_physique_report(
        goal: Annotated[str | None, Field(default=None,
            description="Override goal; defaults to profile primary_goal.")] = None,
    ) -> dict:
        from ..engine.proportions import assess_proportions
        from ..engine.thresholds import AESTHETIC_VOLUME_PRIORITIES

        measurements = pr.latest_measurements(svc.db)
        if not measurements:
            raise ToolError(
                "No body measurements on file. Ask the user to provide "
                "measurements (shoulders, waist, chest, arms, etc.) via save_profile."
            )

        effective_goal = goal
        if not effective_goal:
            prof = pr.profile_snapshot(svc.db)
            effective_goal = prof.get("primary_goal") or "aesthetic_balanced"
        if effective_goal not in AESTHETIC_VOLUME_PRIORITIES:
            effective_goal = "aesthetic_balanced"

        report = assess_proportions(measurements, effective_goal)
        return {
            "goal": report.goal,
            "score": report.score,
            "ratios": report.ratios,
            "targets": report.targets,
            "lagging": [
                {"muscles": lp.muscles, "ratio": lp.ratio_name,
                 "current": lp.current, "target": lp.target,
                 "gap_pct": lp.gap_pct, "suggestion": lp.suggestion}
                for lp in report.lagging
            ],
            "symmetry_issues": report.symmetry_issues,
            "measurements_used": measurements,
        }


def _profile_echo(prof: dict, changed: list[str]) -> str:
    bits = []
    if prof.get("primary_goal"):
        bits.append(f"goal={prof['primary_goal']}")
    if prof.get("training_experience"):
        bits.append(f"experience={prof['training_experience']}")
    if prof.get("days_per_week"):
        bits.append(f"{prof['days_per_week']}d/wk")
    if prof.get("height_cm"):
        bits.append(f"{prof['height_cm']}cm")
    if changed:
        bits.append(f"changed: {', '.join(changed[:6])}")
    return "Profile: " + " · ".join(bits) if bits else "Profile updated."


def _checkin_echo(d: str, bw: float | None, sleep: float | None, energy: int | None) -> str:
    bits = [f"date={d}"]
    if bw is not None:
        bits.append(f"bw={bw}kg")
    if sleep is not None:
        bits.append(f"sleep={sleep}h")
    if energy is not None:
        bits.append(f"energy={energy}/5")
    return "Check-in: " + " · ".join(bits)
