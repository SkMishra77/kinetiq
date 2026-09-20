"""Program-rotation helper."""
from __future__ import annotations


def next_template_index(current_index: int, template_count: int) -> int:
    """Cyclic rotation pointer (0-based, wraps)."""
    if template_count <= 0:
        return 0
    return (current_index % template_count)


def advance(current_index: int, template_count: int) -> int:
    if template_count <= 0:
        return 0
    return (current_index + 1) % template_count
