# E2 — Pydantic mechanics for sub-schema projection and splicing

*Sub-agent report, completed 2026-09-07. Rescued from the parent agent's
context after a session-limit kill; the parent agent (`E-frameworks-practice`)
died before it could file this.*

**Evidence quality note.** This agent did not only read docs — it installed
**Pydantic 2.13.5** and **pydantic-partial 0.11.1** and executed real code.
Claims marked **VERIFIED (executed)** are actual library behaviour, which is
stronger evidence than a docs paraphrase.

Docs note: `docs.pydantic.dev` now 301-redirects to
`pydantic.dev/docs/validation/latest/…` — the docs site moved domains.
(VERIFIED via redirect response.)

---

## 1. Nested `BaseModel` and `model_json_schema()`

A nested `BaseModel` is emitted **once** into a top-level `$defs` map and
referenced via `{"$ref": "#/$defs/ModelName"}`. VERIFIED (executed, 2.13.5):

```python
class Address(BaseModel):
    street: str
    city: str = Field(alias="cityName")

class Person(BaseModel):
    name: str
    address: Address
    addresses: List[Address] = []

Person.model_json_schema()
# {
#   "$defs": {"Address": {"properties": {"street": {...}, "cityName": {...}},
#                          "required": [...], "type": "object"}},
#   "properties": {
#     "name": {"type": "string", ...},
#     "address": {"$ref": "#/$defs/Address"},
#     "addresses": {"type": "array", "items": {"$ref": "#/$defs/Address"}, ...}
#   },
#   "required": ["name", "address"], "title": "Person", "type": "object"
# }
```

Three parameters matter for projection:

- **`by_alias`** (default `True`) — property keys are the field's alias, not its
  Python name. `by_alias=False` turns `"cityName"` back into `"city"` everywhere
  including inside `$defs`. VERIFIED (executed + docs).
- **`ref_template`** — rewrites the `$ref` pattern, e.g.
  `ref_template="#/components/schemas/{model}"` for embedding into OpenAPI.
  VERIFIED (executed + docs).
- **`mode='validation'` vs `mode='serialization'`** — identical on a plain model;
  they diverge only when a field's accepted input type differs from its emitted
  output type (`@computed_field`, or `Decimal`, which accepts str-or-number on
  input but emits str). **Generate against `mode='validation'`** — the schema
  describing acceptable input. VERIFIED (executed showed no diff on a simple
  model; the `Decimal` divergence is VERIFIED from docs).

Source: <https://pydantic.dev/docs/validation/latest/concepts/json_schema/> (fetched).

---

## 2. `create_model()` — projecting a runtime sub-model

Exact signature (VERIFIED — `inspect.signature(pydantic.create_model)` on
installed 2.13.5, source `pydantic/main.py`):

```python
def create_model(
    model_name: str, /, *,
    __config__: ConfigDict | None = None,
    __doc__: str | None = None,
    __base__: type[ModelT] | tuple[type[ModelT], ...] | None = None,
    __module__: str | None = None,
    __validators__: dict[str, Callable[..., Any]] | None = None,
    __cls_kwargs__: dict[str, Any] | None = None,
    __qualname__: str | None = None,
    **field_definitions: Any | tuple[Any, Any],
) -> type[ModelT]
```

**The key trick for projection:** each `field_definitions` value is either a bare
annotation or an `(annotation, default)` tuple — and the second element can be
the original **`FieldInfo` object itself**, not just a plain default. That
preserves constraints (`ge`, `max_length`, `description`, alias) which a plain
default silently drops.

```python
def project_model(model: type[BaseModel], field_names: list[str],
                  name: str | None = None) -> type[BaseModel]:
    fields = {}
    for fname in field_names:
        finfo = model.model_fields[fname]
        fields[fname] = (finfo.annotation, finfo)   # FieldInfo in the default slot
    return create_model(name or f"{model.__name__}Projected", **fields)

Proj2 = project_model(BigForm, ["q1", "q2"])
Proj2.model_json_schema()
# {"properties": {"q1": {"type": "string", ...}, "q2": {"type": "integer", ...}},
#  "required": ["q1", "q2"], "title": "BigFormProjected", "type": "object"}
Proj2(q1="x", q2=5)   # works, full validation intact
```

VERIFIED (executed). **This is the direct implementation of the PROJECT step**
for "regenerate only Q3": `model_fields["q3"]` →
`create_model("Q3Fragment", q3=(finfo.annotation, finfo))` → a schema containing
exactly and only Q3's own constraints.

`model_fields` is a class-level `dict[str, FieldInfo]`. VERIFIED (docs + executed).

---

## 3. Partial / optional models

**Manual Optional-ising:**

```python
def make_partial(model: type[BaseModel], name=None) -> type[BaseModel]:
    fields = {f: (Optional[fi.annotation], None) for f, fi in model.model_fields.items()}
    return create_model(name or f"Partial{model.__name__}", **fields)
```

`PartialBigForm()` succeeds with no args; `PartialBigForm(q2="not an int")` still
raises `ValidationError` (`int_parsing`). **Optional-ising loosens presence, not
type.** VERIFIED (executed).

**`model_construct()` is the wrong tool here.** It bypasses validation entirely —
`BigForm.model_construct(q1="ok", q2="NOT AN INT - bypassed")` returns an
instance with `q2` still a raw string, no error. Docs: *"Creates a new model
setting `__dict__` … from trusted or pre-validated data… no other validation is
performed."* It is for skipping validation on data you already trust, not for
defining what is optional at generation time. VERIFIED (executed + docs).

**`pydantic-partial` is real and maintained** — v0.11.1, pydantic v2, MIT,
author David Danier / TEAM23 GmbH. VERIFIED (installed). Public API read from
installed source (`pydantic_partial/partial.py`):

```python
def create_partial_model(base_cls: type[SelfT], *fields: str, recursive: bool = False,
                          partial_cls_name: str | None = None) -> type[SelfT]

class PartialModelMixin(pydantic.BaseModel):
    @classmethod
    def model_as_partial(cls, *fields: str, recursive: bool = False,
                          partial_cls_name: str | None = None) -> type[Self]: ...
    # .as_partial(...) exists but is deprecated
```

Internally it does the same `create_model(name, __base__=base_cls, **optional_fields)`
trick — the library *is* the manual technique, packaged, plus three extras all
verified by execution:

1. **Selective fields.** `Person.model_as_partial("age")` makes only `age`
   optional; `name`/`address` stay required.
2. **Dotted-path partial into a nested model.**
   `Person.model_as_partial("address.city")` makes `address.city` optional inside
   a synthesized `AddressPartial`, while `address.street` stays required and
   `address` stays required on `Person`. **This is the closest off-the-shelf
   match to "project down to one nested leaf and loosen only that."**
3. **`recursive=True`** cascades partial-ness into nested submodels, generating a
   `SubmodelPartial` for each and rewriting `$ref`s.

Caveat read from source: dotted/nested partialling works only for submodels that
**also** mix in `PartialModelMixin` — `_partial_annotation_arg` checks
`issubclass(field_annotation, PartialModelMixin)` and no-ops otherwise.

---

## 4. Discriminated unions

Generated schema shape, VERIFIED (executed — docs describe this only in prose):

```json
{
  "$defs": {"Cat": {"properties": {"pet_type": {"const": "cat"}, "meows": {}}},
            "Dog": {"properties": {"pet_type": {"const": "dog"}, "barks": {}}}},
  "properties": {
    "pet": {
      "discriminator": {"propertyName": "pet_type",
                        "mapping": {"cat": "#/$defs/Cat", "dog": "#/$defs/Dog"}},
      "oneOf": [{"$ref": "#/$defs/Cat"}, {"$ref": "#/$defs/Dog"}]
    },
    "name": {"type": "string"}
  }
}
```

Also supports a callable `Discriminator(fn, ...)` with `Tag(...)` per arm, for
unions without a shared literal field name. VERIFIED (docs).

**Projecting across a discriminated union.** Clean when the union field *is* the
localised region — the fragment is the `oneOf` + `discriminator` plus the `$defs`
it points at, generable standalone via `TypeAdapter(Union[Cat, Dog])`.

**Not clean when the region is inside one arm** (you know it is a `Cat` and want
to regenerate `Cat.meows`): the discriminator information is lost the moment you
descend into an arm. You must carry the discriminator value (`pet_type: "cat"`)
as pinned context outside the generated fragment, or the spliced object will not
round-trip through the union at final revalidation. A splice-time bookkeeping
burden, not a projection failure.

Root-level discriminated unions behave identically under `RootModel[...]`. A
bare `TypeAdapter(Union[Cat, Dog])` *without* a discriminator produces `anyOf`
instead — Pydantic's smart-union shape. VERIFIED (executed).

---

## 5. Recursive models

```python
class Node(BaseModel):
    value: int
    children: List["Node"] = []
Node.model_rebuild()
Node.model_json_schema()
# {"$defs": {"Node": {"properties": {"value": {...},
#                                     "children": {"items": {"$ref": "#/$defs/Node"}}}}},
#  "$ref": "#/$defs/Node"}
```

Two implementation-relevant details from the raw output (VERIFIED, executed):

- The recursion is a normal `$ref` cycle **inside** `$defs`. No special-casing
  needed for a consumer that already resolves `$ref`.
- **The top-level schema for a recursive model is just
  `{"$defs": {...}, "$ref": "#/$defs/Node"}`** — Pydantic does not inline the
  root. Any projection tool assuming "root fields are inlined at the top level"
  breaks on recursive (and, per §7 case 1, shared-submodel) models. Always
  resolve through `$defs`.

**What breaks.** A fragment at depth *N* into a recursive model
(`children[2].children[0].value`) is schema-wise trivial — still
`{"$ref": "#/$defs/Node"}`, since every depth shares one definition. But the
**splice path** is not: reattaching means walking and mutating a specific
*instance* path, and nothing in Pydantic does this for you (see §6).

---

## 6. Splicing back: `model_copy(update=...)` vs `model_validate()`

**`model_copy(update=...)` does NOT validate.** Exact docstring: *"Values to
change/add in the new model. **Note: the data is not validated before creating
the new model. You should trust this data.**"* VERIFIED (fetched + executed):

```python
s = Strict(n=5)                       # class Strict(BaseModel): n: int
s.model_copy(update={"n": "not an int"})
# Strict(n='not an int')   <-- no error; n is now a str despite the annotation
```

**Safe splice = dump → patch → `model_validate()`:**

```python
d = s.model_dump()
d["n"] = "not an int"
Strict.model_validate(d)   # raises ValidationError, as expected
```

VERIFIED (executed).

> **Recommendation for the SPLICE step.** Never use `model_copy(update=...)` as
> the final splice. It is a silent-corruption trap that looks safe because it
> type-checks at the call site while performing zero runtime checking. Always
> splice into a plain dict and go through `model_validate` / `model_validate_json`
> so the global revalidation step actually has teeth.

---

## 7. `TypeAdapter` for non-`BaseModel` fragments

Not every localised region is a `BaseModel` — it may be a bare `List[Address]`,
a `Dict[str, int]`, or a union. `TypeAdapter` handles arbitrary typing
constructs for both schema generation and standalone validation, with no
throwaway wrapper model:

```python
ta = TypeAdapter(List[Address])
ta.json_schema()   # {"$defs": {...}, "items": {"$ref": "#/$defs/Address"}, "type": "array"}
ta.validate_python([{"street": "Main", "cityName": "Springfield"}])   # fully validated
```

VERIFIED (executed). Same `mode`/`ref_template`/`by_alias` parameters as
`model_json_schema()` (docs; parameter parity not independently executed).

**This is the right tool for the GENERATE step when the region is not naturally
a whole model** — projecting to "just the `List[str]` that is q4" needs no
wrapper; `TypeAdapter(List[str])` gives both the schema to constrain against and
the validator to check the result.

---

## 8. Where projection breaks — three structural failure modes

All three reproduced empirically on 2.13.5, not merely reasoned about.

### 8.1 `$ref` pointing outside the projected fragment

```python
class SharedDef(BaseModel): code: str
class Left(BaseModel):  shared: SharedDef; left_only: str
class Right(BaseModel): shared: SharedDef; right_only: str
class Parent(BaseModel): left: Left; right: Right
```

`$defs` contains `Left`, `Right`, `SharedDef` — `SharedDef` appears **once**, and
both `Left` and `Right` `$ref` it. Naively slicing out `$defs["Left"]` as "the
Left fragment" leaves `{"$ref": "#/$defs/SharedDef"}` **dangling**, because the
definition did not travel with it. VERIFIED (executed).

**Fix** (agent's synthesis, not from docs): projection must compute the
transitive closure of `$ref` targets reachable from the fragment root — a DFS
over `$defs` keys referenced directly or nested from the extracted subtree — and
carry all of them into the projected document's own `$defs`. **No Pydantic API
does this closure for you**; it is a ~20-line graph walk you own.

### 8.2 Root-level unions

A model that *is* a union at the root (`RootModel[Union[Cat, Dog]]`, or bare
`TypeAdapter(Union[...])`) has no field name to localise into — the root **is**
the branch choice. VERIFIED (executed: schema is `{"$defs": {...}, "anyOf":
[...]}` with no `properties` key at all).

Projection degenerates to "pick a branch, then project inside it". You cannot
localise smaller than one full union arm without first resolving which arm you
are in. A *discriminated* union gives a cheap tag for that; a plain union does
not — resolving the arm may require validating against every arm.

### 8.3 `@model_validator(mode='after')` — the global-constraint residue, in Pydantic form

```python
class DateRange(BaseModel):
    start: int
    end: int
    @model_validator(mode="after")
    def check_order(self) -> "DateRange":
        if self.start > self.end: raise ValueError("start must be <= end")
        return self
```

`DateRange.model_json_schema()` shows **only** `{"properties": {"start": ..., "end": ...},
"required": [...]}`. The ordering constraint leaves **zero trace** in the schema.
VERIFIED (executed). `DateRange(start=10, end=1)` raises — but only once both
fields are present on one object, since `mode='after'` validators receive `self`,
the fully-assembled instance.

**Consequence for the architecture.** If the localised region is `end` alone, its
projected schema is just `{"type": "integer", "title": "End"}`. Generating
against it can produce a value that is locally well-typed and globally invalid —
a new `end` now less than the untouched `start` — and **nothing in PROJECT or
GENERATE can catch this, by construction**, because the constraint was never
expressible as part of any one field's schema. It is caught only at the final
global revalidation, which means a bad localised generation is *wasted* work
rather than *prevented* work.

**Contrast with `@field_validator`:** also invisible in the JSON Schema (VERIFIED
executed), but it depends only on that field's own value, so re-running it
during isolated fragment validation reproduces exactly what full-object
validation would give. **`field_validator` constraints are safe to treat as
local; `model_validator(mode='after')` constraints are not.**

`@model_validator(mode='before')` is a third case: it runs on raw pre-validation
input before coercion (VERIFIED executed), so it is a preprocessing hook, largely
orthogonal — except that a `mode='before'` validator on the *parent* may assume
it always receives the full input shape, which a fragment violates if you ever
run the parent's pipeline on a fragment alone.

---

## Bottom line for an implementer

- `field_validator` constraints: schema-invisible but **safe to treat as local**.
- `model_validator(mode='after')` constraints: exactly the class that forces the
  global revalidation step to be **load-bearing rather than a formality**.
- Pydantic offers **no introspection API** to even detect "this model has a
  cross-field validator you should worry about" — it is arbitrary Python. You
  cannot statically decide whether a given projection is safe.

*(That last point is direct evidence on Conjecture 2 in
[`../../notes/02-formulation.md`](../../notes/02-formulation.md): within JSON
Schema the compositional fragment may be characterisable, but Pydantic models
routinely carry constraints that live **outside** JSON Schema entirely, and for
those no static characterisation is possible even in principle.)*
