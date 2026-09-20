"""Exercise-name alias resolution."""
from __future__ import annotations
import re
from dataclasses import dataclass

try:
    from rapidfuzz import fuzz, process
except ImportError:  # pragma: no cover
    fuzz = None
    process = None


_ABBREV = {
    r"\bdb\b": "dumbbell",
    r"\bbb\b": "barbell",
    r"\bohp\b": "overhead press",
    r"\bohsp\b": "overhead press",
    r"\brdl\b": "romanian deadlift",
    r"\bsldl\b": "stiff-leg deadlift",
    r"\blat pd\b": "lat pulldown",
    r"\bpull\s*down\b": "pulldown",
    r"\bpull\s*ups\b": "pull up",
    r"\bchin\s*ups\b": "chin up",
    r"\bbench\b(?!\s+press)": "bench press",
    r"\bincl\.?\s*bench\b(?!\s+press)": "incline bench press",
    r"\bincline db\b": "incline dumbbell",
    r"\bmach\b": "machine",
}

_STOPWORDS = {"the", "a"}


def normalise(name: str) -> str:
    """Lowercase, drop punctuation, expand common abbreviations."""
    s = name.lower().strip()
    s = re.sub(r"[^\w\s+/-]", " ", s)
    for pat, repl in _ABBREV.items():
        s = re.sub(pat, repl, s)
    tokens = [t for t in re.split(r"\s+", s) if t and t not in _STOPWORDS]
    # Very light singularisation.
    tokens = [t[:-1] if t.endswith("s") and len(t) > 3 and not t.endswith("ss") else t for t in tokens]
    return " ".join(tokens).strip()


@dataclass
class Resolution:
    exercise_id: int | None
    slug: str | None
    name: str | None
    confidence: float                 # 0-100
    matched_on: str                   # "exact" | "alias" | "fuzzy" | "none"
    candidates: list[dict]            # for unresolved: top few possibilities


def resolve(
    raw: str,
    *,
    alias_map: dict[str, tuple[int, str, str]],
    name_pool: list[tuple[int, str, str]],  # (id, slug, name)
) -> Resolution:
    """Look up ``raw`` against the alias table and (as a fallback) fuzzy-match names.

    ``alias_map`` keys must already be normalised.
    Returns a :class:`Resolution`; ``exercise_id`` is None when nothing crossed the
    ≥88 fuzzy threshold.
    """
    norm = normalise(raw)
    if not norm:
        return Resolution(None, None, None, 0.0, "none", [])

    hit = alias_map.get(norm)
    if hit:
        eid, slug, name = hit
        return Resolution(eid, slug, name, 100.0, "alias", [])

    # Fuzzy fallback against canonical names (and their normalised form).
    if not name_pool or process is None:
        return Resolution(None, None, None, 0.0, "none", [])

    choices = {i: normalise(n) for i, (_, _, n) in enumerate(name_pool)}
    best = process.extract(norm, choices, scorer=fuzz.token_set_ratio, limit=5)
    top_score = best[0][1] if best else 0
    candidates = [
        {"slug": name_pool[idx][1], "name": name_pool[idx][2], "score": float(score)}
        for _, score, idx in best[:3]
    ]
    if top_score >= 88:
        eid, slug, name = name_pool[best[0][2]]
        return Resolution(eid, slug, name, float(top_score), "fuzzy", candidates)
    return Resolution(None, None, None, float(top_score), "none", candidates)
