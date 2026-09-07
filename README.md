# delta-structured-write

Working out whether an LLM can emit only the *changed part* of a schema-governed
structured output, instead of regenerating the whole object every time — and
whether that can keep the hard guarantee that constrained decoding gives.

Started from a handwritten note. The goal is a research answer, not a product:
is this **already solved**, **not worth solving**, or **genuinely open**?

## The two cases driving it

**Edit.** A form defined by a Pydantic model. The user says *"change the answer
to Q3."* Today the model retypes all forty responses to change one. It should
regenerate `responses[2]` alone, constrained against the `Response` schema, and
the system should splice it in.

**Construction.** A spreadsheet with 10,000 schema-governed rows. One generation
cannot hold it — every model caps output tokens — so emit 10 rows at a time and
assemble. Here fragmentation is not an optimisation, it is the only way through.

## Read in this order

| | |
|---|---|
| [`notes/00-original-note.md`](notes/00-original-note.md) | The handwritten note, transcribed verbatim. |
| [`notes/01-problem-plain-english.md`](notes/01-problem-plain-english.md) | What the problem is, in plain words, with worked examples. |
| [`notes/02-formulation.md`](notes/02-formulation.md) | The same thing stated precisely: residual schemas, the reduction, the cost model, hypotheses. |
| [`notes/03-research.md`](notes/03-research.md) | What the literature actually says. |
| [`notes/04-solution-approaches.md`](notes/04-solution-approaches.md) | Verdict, what to build, and the experiment that settles it. |
| [`notes/05-what-the-experiments-did-not-test.md`](notes/05-what-the-experiments-did-not-test.md) | Why the first three nulls do not support the conclusion drawn from them, and the redesign that follows. |

[`research/raw/`](research/raw/) holds the detailed source reports the notes are
built from. [`CHECKPOINT.md`](CHECKPOINT.md) is the resume point.

## The code

[`EXPERIMENT.md`](EXPERIMENT.md) and [`RETRY.md`](RETRY.md) are the two
experiments' designs, budgets and decision logs — read them before running
anything. The first asks what regeneration does to fields nobody asked about;
the second asks whether regeneration reliably fixes the fields that were
rejected.

```bash
uv sync
uv run python scripts/smoke.py --offline        # no API calls; asserts the invariants
uv run python scripts/run_integrity.py --design thin --dry-run
uv run python scripts/run_integrity.py --design thin
uv run python scripts/analyse.py

uv run python scripts/run_retry.py --offline     # no API calls; asserts the invariants
uv run python scripts/run_retry.py --sizes medium --seeds 3
uv run python scripts/analyse_retry.py
```

| module | what it is |
|---|---|
| `src/dsw/config.py` | keys, the pinned model, and the measured free-tier quota |
| `src/dsw/providers.py` | Gemini (primary) and OpenRouter (cross-check only) |
| `src/dsw/forms.py` | the corpus: a nested form with an invariant no schema can see |
| `src/dsw/projection.py` | **P2** projection and **P5** the O(\|p\|) safety walk |
| `src/dsw/splice.py` | **P4** splice — dump, patch, revalidate |
| `src/dsw/metrics.py` | untouched-region integrity, the headline measurement |
| `src/dsw/constraints.py` | the closure rules, and where each violation is repaired |
| `src/dsw/experiment.py` | the integrity experiment's two arms, throttling, and a resumable runner |
| `src/dsw/retry.py` | the retry experiment: whole-document reask against targeted repair |
| `src/dsw/dossier.py` | the hard corpus: depth 5, a discriminated union, lists inside lists |
| `src/dsw/dossier_rules.py` | five invariants that fail five different ways, one of them global |
| `src/dsw/agentic.py` | the agentic loop, where the transcript actually accumulates |

The interesting file is `projection.py`: it implements the corrected result from
[`notes/03`](notes/03-research.md) §11 — that an in-place *replacement* cannot
disturb key-set or length constraints, so the provably-safe fragment of JSON
Schema is materially larger than the insert/delete case, and largest exactly in
the form scenario.

## The idea in one paragraph

Don't make the model write a patch. Make the **system** decide which region is
in play, derive the schema of just that region, and let the model do ordinary
constrained decoding against that smaller schema. Splice the fragment back in
code. The model never writes a path or a diff — it answers one small,
well-posed question.

Formally this collapses to a single object: the **residual**
`S/(D,p) = { v : D[p := v] ⊨ S }`, the values that keep the whole document valid
given everything around them. Constrain to that and correctness is free by
definition. So the entire difficulty is whether the residual can be computed,
approximated, and compiled into something a decoder can enforce.

## What is at stake

Two arguments, and they are not equally strong.

The **cost** argument — fewer output tokens, lower latency — is real but erodable;
speculative decoding and caching chip away at it, and one of the research agents
is specifically tasked with arguing that side as forcefully as the evidence
allows.

The **integrity** argument looked like it did not erode. Bytes that are never
regenerated cannot be corrupted, so the untouched part of a fragment-generated
document is identical by construction while a fully regenerated one is a sample
from a distribution. The literature says models really do quietly paraphrase,
drop and drift while retyping things they were not asked to change.

**Both experiments failed to reproduce that.** Twelve turns of whole-document
regeneration corrupted nothing ([`EXPERIMENT.md`](EXPERIMENT.md)); whole-document
*repair* of a rejected document corrupted nothing and never traded one violation
for another ([`RETRY.md`](RETRY.md)). The common factor is constrained decoding:
the corruption evidence in [`notes/03`](notes/03-research.md) §4 all comes from
unconstrained generation. So for schema-constrained output the honest position is
that regeneration is reliable, and every surviving reason to generate fragments
is economic — 172× on the edit path, 26× on the repair path.
