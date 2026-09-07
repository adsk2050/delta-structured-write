"""P4: put a generated fragment back into the document.

One rule dominates this module. `model_copy(update=...)` **does not validate** —
`Strict(n=5).model_copy(update={"n": "not an int"})` returns `Strict(n='not an
int')` with no error. It looks safe because it type-checks at the call site while
doing no runtime checking at all, which makes it a silent-corruption trap. So the
splice always goes dump -> patch the plain dict -> `model_validate`, and the
final validation is what gives the step teeth.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import BaseModel, ValidationError

from .projection import Path


@dataclass(frozen=True)
class SpliceResult:
    document: BaseModel | None
    ok: bool
    error: str | None = None


def get_at(data: Any, path: Path) -> Any:
    for step in path:
        data = data[step]
    return data


def set_at(data: Any, path: Path, value: Any) -> None:
    """In-place assignment into a plain dict/list tree. `path` must exist."""
    if not path:
        raise ValueError("cannot set at an empty path")
    for step in path[:-1]:
        data = data[step]
    data[path[-1]] = value


def splice(
    document: BaseModel, path: Path, fragment: BaseModel | dict | Any
) -> SpliceResult:
    """Replace the subtree at `path` with `fragment` and revalidate the whole.

    Revalidation is deliberately *full*, not incremental. It is PTIME, it is not
    the bottleneck, and it is the only thing that can catch a constraint written
    in Python rather than in the schema.
    """
    payload = document.model_dump(mode="json")
    value = (
        fragment.model_dump(mode="json")
        if isinstance(fragment, BaseModel)
        else fragment
    )
    try:
        set_at(payload, path, value)
    except (KeyError, IndexError, TypeError) as exc:
        return SpliceResult(None, False, f"bad path {path}: {type(exc).__name__}: {exc}")

    try:
        return SpliceResult(type(document).model_validate(payload), True)
    except ValidationError as exc:
        return SpliceResult(None, False, f"revalidation failed: {exc.error_count()} error(s): {exc}")
