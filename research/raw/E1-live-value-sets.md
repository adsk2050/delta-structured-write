# E1 — Constrained decoding over live / dynamic value sets

*Sub-agent report, completed 2026-09-07. Rescued from the parent agent's
context after a session-limit kill; the parent agent (`E-frameworks-practice`)
died before it could file this.*

**Question.** Find production systems that constrain LLM structured output to a
set of values drawn from **live / runtime data** — dynamic enums, or generated
keys constrained to an existing document's key set. This is the
"state-conditioned grammar" idea in practice.

---

## Headline verdict

Building an enum constraint from **runtime data** is not a distinct feature in
any tool surveyed. It is the trivial consequence of every constrained-decoding
API taking a **plain list** as an argument or a JSON Schema field, built however
your own code likes. **No library treats "static enum" and "dynamic enum" as
different code paths.** The genuinely documented limits are about **size** — how
many values, how long the compiled automaton takes — not about whether values
can be runtime-sourced.

**Negative result:** no production system was found that constrains a generated
**key or reference to the keys already present in an existing document being
edited**. That pattern — directly relevant to the form scenario's LOCALISE
step — appears to be an engineering gap, not a solved problem.

---

## 1. Outlines — `Choice` is explicitly the dynamic-enum API

> "Additionally, you can use the Outlines-specific type `Choice` that takes a
> `list` as an argument. This type is useful in situations in which the list of
> choices is dynamic."

```python
from outlines.types import Choice

def get_multiple_choices() -> list:
    return ["pizza", "burger"]   # could be built from a live DB query

output_type = Choice(get_multiple_choices())
```

`Literal[...]` / `Enum` are the static equivalents; `Choice` is explicitly the
runtime-list version.
Source: <https://dottxt-ai.github.io/outlines/latest/features/core/output_types/> — **VERIFIED** (primary docs, fetched).

**Performance ceiling.** Outlines compiles constraints to a regex-FSM ahead of
generation, and that compile step is a known bottleneck independent of enums. A
GitHub discussion documents "Compiling FSM index for all state transitions"
taking **20–40 s** per new schema; issue #658 reports an **OOM after ~1600 s**
building a generator for a schema with several constrained string/list fields on
a **32 GB** machine, the reporter noting memory grew "in exponential fashion" as
string-length constraints grew, and asking (unanswered in the visible thread)
whether the FSM could be split to avoid state explosion.
Sources: <https://github.com/dottxt-ai/outlines/discussions/1183>,
<https://github.com/dottxt-ai/outlines/issues/658> — **VERIFIED** (fetched).
*Caveat:* enum-specific numbers were not found; that large enums hit the same
FSM-size wall as large regex constraints is **inferred**, not a claim Outlines'
docs make about enums per se.

## 2. Guidance — `select()` takes a plain list; dynamism is just Python

```python
lm += select(["A", "B", "C", "D"], name="model_selection")
# vs. constructed from data:
lm += select([chr(i + ASCII_OFFSET) for i in range(len(choices))], name="string_choice")
```

The second form is from Guidance's own README: the option list is built from a
variable, confirming runtime-sourced lists are normal, unremarkable usage rather
than a special mode.
Source: <https://github.com/guidance-ai/guidance/blob/main/README.md> — **VERIFIED** (fetched).
No documented size limit for `select()` in the README (absence not confirmed via
issue tracker).

## 3. OpenAI Structured Outputs — enum is plain JSON Schema; hard numeric ceilings

`enum` is a normal supported keyword (confirmed via current docs examples, e.g.
`"enum": ["div", "button", "header", "section", "field", "form"]`). Nothing
distinguishes a hand-written from a data-sourced enum — it is serialised JSON
your code produced.
Source: <https://developers.openai.com/api/docs/guides/structured-outputs> — **VERIFIED** (primary) for enum support.

The numeric-limits subsection did not render through the fetch tool (likely
client-rendered), so the figures below are **SECONDHAND**, from two independent
OpenAI Developer Community posts quoting the docs/changelog directly and
mutually consistent:

| | Pre-July 2025 | After 2025-07-11 update |
|---|---|---|
| Max enum values per schema | 500 | **1,000** |
| Max object properties | 100 | **5,000** |
| Max nesting levels | 5 | 5 |
| Total chars (property names + enum + const) | 15,000 | **120,000** |
| Char budget for enums with >250 values | 7,500 | 15,000 |

Sources:
<https://community.openai.com/t/measuring-maximum-depth-and-object-properties-in-structured-outputs/918388>,
<https://community.openai.com/t/structured-outputs-limits-are-raised-to-support-larger-schemas/1313593> — **SECONDHAND** but corroborating, dated, with before/after numbers.

> **Implication for "enum of live IDs".** Even after the increase, ~1,000 live
> values is a hard ceiling. A live-ID enum works at small-to-medium cardinality
> only; it does not scale to "all customer IDs" in a real table.

## 4. Anthropic tool use / structured outputs — enum supported, no published ceiling

Strict tool use (`strict: true`) and structured outputs compile `input_schema`
(including `enum`) into a grammar via grammar-constrained sampling.

- **Supported:** `enum` (strings/numbers/bools/null only, no complex types),
  `const`, `anyOf`/`allOf` (with restrictions), `$ref`/`$def`.
- **Unsupported:** **recursive schemas**, external `$ref`, `minLength`/`maxLength`/
  `minimum`/`maximum`, array constraints beyond `minItems` ∈ {0,1}.

Sources: <https://platform.claude.com/docs/en/agents-and-tools/tool-use/strict-tool-use>,
<https://platform.claude.com/docs/en/build-with-claude/structured-outputs> — **VERIFIED** (primary, fetched in full).

Unsupported features return a 400. Unlike OpenAI, the docs **do not publish** a
max-enum-count, max-schema-size, or max-nesting-depth. No mention of "dynamic
per-request enum" as a concept — consistent with it being a non-feature.

*Side-finding worth recording:* Anthropic's strict-mode PHI guidance explicitly
warns against putting PHI in `enum` values, because compiled schemas are cached
up to 24 h separately from message-content HIPAA protections. Directly relevant
if anyone considers putting live customer data into an enum.

## 5. PICARD — real prior art for state-conditioned grammars, but for identifiers

PICARD ("Parsing Incrementally for Constrained Auto-Regressive Decoding",
ElementAI / ServiceNow Research, EMNLP 2021, open-sourced) is the clearest real
instance of a state-conditioned grammar: an incremental SQL parser that rejects
tokens producing table or column references **that do not exist in the actual
target database schema**, applied at every decoding step, requiring no model
retraining.

It is schema-aware in the sense we mean — constrain to what is really there —
but it constrains **structural identifiers** (table and column names), **not
row-level data values**. It will not constrain a `WHERE city = ...` literal to
actually-occurring city values.
Source: <https://github.com/ElementAI/picard> — **SECONDHAND** (README summarised
via search, not fetched in full), corroborated by multiple independent sources
describing the same mechanism.

> **Contrast worth recording.** The common industry pattern for "does this
> generated value correspond to something real" is **not** constrained decoding.
> It is free generation followed by retrieval / fuzzy / embedding-similarity
> matching — generate an entity name, then resolve it against a database by
> nearest-neighbour or string similarity. That is post-hoc correction, a
> fundamentally different mechanism, and it is the default in RAG and
> entity-linking pipelines.

## 6. vLLM — same pattern at the serving layer

```python
from vllm.sampling_params import GuidedDecodingParams
guided_decoding_params = GuidedDecodingParams(choice=["Positive", "Negative"])
sampling_params = SamplingParams(guided_decoding=guided_decoding_params)
```

Renamed in v0.12.0 to `StructuredOutputsParams(choice=...)`. Again a plain Python
list, trivially runtime-constructible; no static/dynamic distinction.
Source: <https://docs.vllm.ai/en/v0.8.2/features/structured_outputs.html> —
**VERIFIED** via search snippet quoting the docs page; the rename is
changelog-derived, **SECONDHAND**.

## 7. Others

- **lm-format-enforcer** — README fetched directly: **no** example of a
  runtime/dynamic-list enum, no documented large-choice-set performance guidance.
  Negative result. <https://github.com/noamgat/lm-format-enforcer> — **VERIFIED** (absence confirmed).
- **XGrammar** — independently benchmarked as faster than Outlines and
  lm-format-enforcer via precompiled pushdown automata: up to **3.5×** on JSON
  schema, **>10×** on CFG. That is where large-enum compile cost would matter
  most, but no doc page giving a live-data-enum example was found. Treat as
  *unexamined*, not negative.
  <https://blog.mlc.ai/2024/11/22/achieving-efficient-flexible-portable-structured-generation-with-xgrammar> — **SECONDHAND** (search snippet).

---

## Negative results (explicit)

Queries tried that returned nothing on-point:

- `"constrained decoding" OR "grammar constrained" LLM select existing column name OR customer ID from database schema live values`
- `LLM structured output constrain field name to existing JSON object keys grammar "already exists" edit`

**No production tool or documented pattern** was found for constraining a
generated field name / key / reference to the **live key-set of an existing
document being edited** via true constrained decoding. Everything found either
(a) constrains to a *schema's* structural vocabulary (PICARD: valid tables and
columns), or (b) is enum-of-values support that is scalar-value-shaped, not
document-key-shaped. **This is a genuine, reportable gap.**

---

## Judgement (the agent's, not sourced)

- **The mechanism is a solved, boring problem.** Every constrained-decoding
  surface takes option lists as ordinary runtime data. Building an enum from a
  live query requires **zero** new engineering beyond what already ships.
- **What is unsolved is scale, and the "existing document keys" variant.**
  (a) Hard vendor ceilings — OpenAI's 1,000-enum / 120k-char limits, Outlines'
  FSM compile blow-ups — mean live-value constraining works only at
  small-to-medium cardinality. It is not a general answer to "constrain to any of
  my 50,000 SKUs" without a retrieval/pre-filtering step first.
  (b) Nobody has productised "constrain the generated key to
  `existing_object.keys()`" as a first-class API — which is precisely what the
  LOCALISE step needs to pick which field to touch, or to validate a target key
  against the real object. **A small but real gap the architecture must build
  itself rather than borrow.**
