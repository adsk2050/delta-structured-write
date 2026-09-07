"""P2 (project a sub-schema) and P5 (decide whether the splice is provably safe).

This module is where the literature review turns into code. Two things worth
knowing before reading it:

**The safe fragment is larger for replacement than for insert/delete.** An
in-place replacement at an existing path changes neither the sibling key set nor
the array length, so `required`, `minItems`/`maxItems`, `dependentRequired`,
`propertyNames` and `additionalProperties` cannot be disturbed by it. They break
insertion and deletion only. This was the correction that came out of the review
(notes/03 §11) and it matters, because the form case is almost always
replacement.

**The walk is a fast path, not a proof.** A constraint written in Python rather
than in the schema — a Pydantic `model_validator(mode="after")` — is invisible to
any schema-level analysis. `cross_field_validators` below finds the ones Pydantic
happens to record, but an arbitrary validator body can reach anywhere, so a clean
walk means "revalidation is expected to be a formality", never "revalidation can
be skipped".
"""

from __future__ import annotations

import typing
from dataclasses import dataclass
from typing import Any, Union, get_args, get_origin

from pydantic import BaseModel, create_model

Path = tuple[str | int, ...]

# Keywords that a *replacement* at an existing path can still break, because
# their satisfaction depends on values rather than on the key set or length.
REPLACE_BREAKERS = frozenset({
    "uniqueItems", "if", "then", "else", "dependentSchemas",
    "oneOf", "anyOf", "not", "prefixItems",
    "unevaluatedProperties", "unevaluatedItems",
})

# Additionally unsafe once a write can add or remove a key or an element.
STRUCTURAL_BREAKERS = frozenset({
    "required", "minItems", "maxItems", "minProperties", "maxProperties",
    "dependentRequired", "propertyNames", "additionalProperties",
})


@dataclass(frozen=True)
class Safety:
    """The verdict of the root-to-target walk."""

    safe: bool
    operation: str
    breakers: tuple[tuple[str, str], ...]      # (json-pointer-ish location, keyword)
    cross_field_validators: tuple[str, ...]    # Pydantic validators we could see
    checked_depth: int

    @property
    def revalidation_is_load_bearing(self) -> bool:
        return not self.safe or bool(self.cross_field_validators)

    def explain(self) -> str:
        if self.safe and not self.cross_field_validators:
            return (
                f"SAFE ({self.operation}): no breaking keyword on the "
                f"{self.checked_depth}-step path; splice is provably schema-preserving."
            )
        bits = []
        if self.breakers:
            bits.append(
                "schema breakers: "
                + ", ".join(f"{kw} at {loc or '<root>'}" for loc, kw in self.breakers)
            )
        if self.cross_field_validators:
            bits.append(
                "cross-field validators outside the schema: "
                + ", ".join(self.cross_field_validators)
            )
        return f"UNSAFE ({self.operation}): " + "; ".join(bits)


def cross_field_validators(model: type[BaseModel]) -> tuple[str, ...]:
    """Names of `model_validator` functions Pydantic records on `model`.

    The literature note said Pydantic exposes no way to detect these. That is
    *nearly* right and worth stating precisely: `__pydantic_decorators__` does
    record them, so their existence is discoverable — but nothing reveals which
    fields the validator body actually touches, since it is arbitrary Python.
    So this narrows the blind spot without removing it.
    """
    decorators = getattr(model, "__pydantic_decorators__", None)
    if decorators is None:
        return ()
    return tuple(sorted(getattr(decorators, "model_validators", {}) or {}))


def _unwrap_optional(annotation: Any) -> Any:
    """`X | None` -> `X`. Leaves genuine multi-member unions alone."""
    if get_origin(annotation) in (Union, typing.Union):
        args = [a for a in get_args(annotation) if a is not type(None)]
        if len(args) == 1:
            return args[0]
    return annotation


def walk(model: type[BaseModel], path: Path) -> tuple[Any, list[type[BaseModel]]]:
    """Follow `path` through `model`.

    Returns the annotation at the target, and the **ancestors**: every model on
    which a key was taken to get there. The target itself is deliberately not in
    that list — a validator on the target model can only see the fragment, so it
    is local and safe; a validator on an ancestor can see the target's siblings,
    which is what makes it dangerous.
    """
    current: Any = model
    ancestors: list[type[BaseModel]] = []
    for step in path:
        current = _unwrap_optional(current)
        if isinstance(step, str):
            if not (isinstance(current, type) and issubclass(current, BaseModel)):
                raise TypeError(f"cannot take key {step!r} on non-model {current!r}")
            ancestors.append(current)
            field = current.model_fields.get(step)
            if field is None:
                raise KeyError(f"{current.__name__} has no field {step!r}")
            current = field.annotation
        else:
            origin = get_origin(current)
            if origin not in (list, tuple):
                raise TypeError(f"cannot index a non-sequence {current!r}")
            current = get_args(current)[0]
    return _unwrap_optional(current), ancestors


def project(model: type[BaseModel], path: Path) -> type[BaseModel]:
    """Return a Pydantic model constraining exactly the fragment at `path`.

    When the target is already a model, it is returned directly — a nested
    `BaseModel` is its own schema, which is why this step needs no research.
    Scalars and containers are wrapped in a single-field model, because Gemini's
    structured output requires an object at the root.
    """
    target, _ = walk(model, path)
    if isinstance(target, type) and issubclass(target, BaseModel):
        return target
    name = "".join(str(s).title() for s in path if isinstance(s, str)) or "Fragment"
    # Passing the FieldInfo through would preserve constraints, but at a leaf
    # reached by walk() we only have the annotation; callers wanting constraint
    # preservation should project the *containing* model instead.
    return create_model(f"{name}Fragment", value=(target, ...))


def _schema_of(model: type[BaseModel]) -> tuple[dict, dict]:
    schema = model.model_json_schema()
    return schema, schema.get("$defs", {})


def _deref(node: dict, defs: dict) -> dict:
    seen = 0
    while "$ref" in node and seen < 32:
        ref = node["$ref"]
        if not ref.startswith("#/$defs/"):
            break
        node = defs.get(ref.split("/")[-1], {})
        seen += 1
    return node


def classify_write(
    model: type[BaseModel], path: Path, operation: str = "replace"
) -> Safety:
    """The O(|p|) root-to-target walk.

    Descends the *JSON Schema* (not the Python model) collecting any keyword that
    could make the splice unsound, choosing the breaker set by operation.
    """
    if operation not in {"replace", "insert", "delete"}:
        raise ValueError(f"operation must be replace/insert/delete, got {operation!r}")

    breaking = REPLACE_BREAKERS if operation == "replace" else (
        REPLACE_BREAKERS | STRUCTURAL_BREAKERS
    )

    schema, defs = _schema_of(model)
    node = _deref(schema, defs)
    found: list[tuple[str, str]] = []
    location = ""

    def collect(n: dict, loc: str) -> None:
        for kw in sorted(breaking):
            if kw in n:
                # `additionalProperties: false` and an empty `required` cannot
                # actually be violated, so they are not reported as breakers.
                value = n[kw]
                if kw == "additionalProperties" and value is False:
                    continue
                if kw == "required" and not value:
                    continue
                found.append((loc, kw))

    collect(node, location)
    for step in path:
        if isinstance(step, str):
            props = node.get("properties", {})
            if step not in props:
                break
            node = _deref(props[step], defs)
            location = f"{location}/{step}"
        else:
            items = node.get("items")
            if items is None:
                break
            node = _deref(items, defs)
            location = f"{location}/{step}"
        collect(node, location)

    # Only ancestors matter: a validator on the target model sees just the
    # fragment and is reproduced faithfully by validating the fragment alone.
    _, ancestors = walk(model, path)
    ancestor_validators = tuple(
        f"{m.__name__}.{v}" for m in ancestors for v in cross_field_validators(m)
    )

    return Safety(
        safe=not found,
        operation=operation,
        breakers=tuple(found),
        cross_field_validators=ancestor_validators,
        checked_depth=len(path),
    )
