"""Measuring what actually happened to the document.

The headline metric is **untouched-region integrity**: of the leaves that were
not supposed to change, how many are byte-identical afterwards? Under
fragment-wise generation this is 1.0 by construction, because those bytes are
never regenerated — so the experiment only has to measure the baseline. That
asymmetry is the reason the experiment is cheap.

Leaf-level exact equality is used rather than tree edit distance. TED is the
right *graded* metric (Zhang-Shasha; APTED at O(n^3)), but plain TED penalises
JSON key-order differences that carry no meaning, which is why the recent
literature had to layer semantic equivalence on top of it. For "did anything
change that shouldn't have", exact equality on flattened leaves is the direct
question and has no such artifact.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

from pydantic import BaseModel

from .projection import Path


def flatten(value: Any, prefix: str = "") -> dict[str, Any]:
    """Every leaf in the tree, keyed by JSON-Pointer-ish path."""
    out: dict[str, Any] = {}
    if isinstance(value, dict):
        for k, v in value.items():
            out.update(flatten(v, f"{prefix}/{k}"))
    elif isinstance(value, list):
        for i, v in enumerate(value):
            out.update(flatten(v, f"{prefix}/{i}"))
    else:
        out[prefix or "/"] = value
    return out


def _pointer(path: Path) -> str:
    return "".join(f"/{s}" for s in path)


@dataclass
class Integrity:
    """How faithfully the untouched part of the document survived."""

    total_untouched_leaves: int
    preserved_leaves: int
    corrupted: dict[str, tuple[Any, Any]] = field(default_factory=dict)  # path -> (before, after)
    added: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()

    @property
    def rate(self) -> float:
        if self.total_untouched_leaves == 0:
            return 1.0
        return self.preserved_leaves / self.total_untouched_leaves

    @property
    def perfect(self) -> bool:
        return not self.corrupted and not self.added and not self.removed

    def summary(self) -> str:
        if self.perfect:
            return f"intact ({self.total_untouched_leaves} leaves)"
        return (
            f"{len(self.corrupted)} changed, {len(self.added)} added, "
            f"{len(self.removed)} removed of {self.total_untouched_leaves}"
        )


def integrity(before: BaseModel, after: BaseModel, target: Path) -> Integrity:
    """Compare everything *outside* `target` between two document versions."""
    return integrity_outside(before, after, (target,))


def integrity_outside(
    before: BaseModel, after: BaseModel, targets: tuple[Path, ...]
) -> Integrity:
    """Compare everything outside *all* of `targets`.

    The retry loop needs the plural form: a repair round is allowed to write to
    every path a violation points at, so "untouched" means outside their union
    rather than outside a single edit site.
    """
    tgts = [_pointer(t) for t in targets]

    def outside(k: str) -> bool:
        return not any(k == t or k.startswith(t + "/") for t in tgts)

    a = {k: v for k, v in flatten(before.model_dump(mode="json")).items() if outside(k)}
    b = {k: v for k, v in flatten(after.model_dump(mode="json")).items() if outside(k)}

    corrupted = {k: (a[k], b[k]) for k in a.keys() & b.keys() if a[k] != b[k]}
    return Integrity(
        total_untouched_leaves=len(a),
        preserved_leaves=len(a.keys() & b.keys()) - len(corrupted),
        corrupted=corrupted,
        added=tuple(sorted(b.keys() - a.keys())),
        removed=tuple(sorted(a.keys() - b.keys())),
    )


def target_applied(after: BaseModel, target: Path, expected: dict[str, Any]) -> bool:
    """Did the edit we asked for actually land?"""
    from .splice import get_at

    try:
        node = get_at(after.model_dump(mode="json"), target)
    except (KeyError, IndexError, TypeError):
        return False
    return all(node.get(k) == v for k, v in expected.items())
