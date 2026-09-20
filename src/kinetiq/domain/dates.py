"""Timezone-aware 'today' and lenient date parsing."""
from __future__ import annotations
import datetime as dt
from zoneinfo import ZoneInfo

DEFAULT_TZ = "Asia/Kolkata"


def now_utc() -> dt.datetime:
    return dt.datetime.now(dt.timezone.utc)


def today(tz: str | None = None) -> dt.date:
    zone = ZoneInfo(tz or DEFAULT_TZ)
    return dt.datetime.now(zone).date()


def parse_date(value: str | dt.date | None, tz: str | None = None) -> dt.date:
    """Accept ``today``, ``yesterday``, ``YYYY-MM-DD`` or a ``date`` object."""
    if value is None:
        return today(tz)
    if isinstance(value, dt.date):
        return value
    s = value.strip().lower()
    if s in ("today", "now"):
        return today(tz)
    if s == "yesterday":
        return today(tz) - dt.timedelta(days=1)
    try:
        return dt.date.fromisoformat(s)
    except ValueError as e:
        raise ValueError(f"invalid date {value!r}: {e}") from e


def iso_utc() -> str:
    return now_utc().strftime("%Y-%m-%dT%H:%M:%SZ")


def days_between(a: dt.date | str, b: dt.date | str) -> int:
    a = parse_date(a) if isinstance(a, str) else a
    b = parse_date(b) if isinstance(b, str) else b
    return (b - a).days
