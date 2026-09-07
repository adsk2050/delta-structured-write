# 04 — Verdict and solution approaches

*Step 3 deliverable. Built on [`03-research.md`](03-research.md); every claim
here traces to a citation there or in [`../research/raw/`](../research/raw/).*

---

## 1. The verdict

[`01`](01-problem-plain-english.md) §9 offered three possible endings. The honest
answer is **all three, in different parts of the problem** — and knowing which
part is which is most of the value.

| Part of the problem | Verdict |
|---|---|
| **Flat, developer-declared slot forms** | **Already solved — since 2020.** Dialogue state tracking, and shipping in production. |
| Constraining a fragment to a sub-schema | **Already solved.** Deployed as Structural Tags. Use it. |
| Projecting a sub-schema; splicing back | **Already solved.** Ordinary Pydantic, with three known traps. |
| Which schemas are safe to splice into | **Solved as a class** (three names, 2004–07) — **but the JSON instance is unclaimed.** |
| Bounded state for chunked construction | **Solved as theory** (Segoufin & Vianu 2002). Flat row schemas are inside the safe class. |
| An exact decode-time guarantee | **Does not need solving — and mostly cannot be.** PSPACE-complete at best, undecidable at worst, and unnecessary. |
| Latency | **Does not need solving** in the edit case. Speculative decoding covers it. |
| Incremental / streaming JSON Schema validation | **Open — but the algorithm exists**, unpointed at JSON (§2, P5). |
| Cross-call state in a decoder | **Open, but unbuilt rather than unsolved.** |
| **Nested, schema-structured documents** | **Open. This is the actual gap.** |
| **Does any of this pay off at large `N` and small ρ** | **Open, and unmeasured by anyone.** |

**In one sentence:** the pieces exist, the theory that says how to assemble them
exists for XML, the flat case was solved five years ago under another name,
nobody has assembled any of it for *nested* JSON, and nobody has measured the
regime that motivates doing so.

### 1.0 What the flat case being solved does to the claim

Dialogue state tracking hit the form problem first and answered it:
**SOM-DST** (2020) predicts a per-slot operation — carry, delete, update — rather
than regenerating the belief state; **MinTL** (2020) emits Levenshtein belief
spans; **Rasa Pro's CALM** ships an LLM-driven `SetSlot`-per-changed-field
mechanism **in production today**.

Cite this as prior art, do not rediscover it. But note precisely what it does not
cover: a belief state is a **flat bag of independent slots**, so the
compositionality question never arises — every slot is trivially independent.
Nesting, recursion, `$ref` structure, arrays with cardinality and uniqueness, and
conditional sub-schemas are all absent.

> **That is the line.** Flat slots: solved. `list[Response]` inside `Form` inside
> a discriminated union: not. The user's form and spreadsheet both sit on the
> unsolved side, which is the whole reason the problem still has content.

### 1.1 The one thing that changed my mind

I expected the answer to be "constrain harder during decoding". The complexity
results say the opposite, and say it cleanly:

| Question | Complexity |
|---|---|
| **Q1** — is this finished fragment safe to splice? | **PTIME-complete** |
| **Q2** — can this half-written fragment still be completed safely? | **PSPACE-complete** (non-recursive), **EXPTIME-complete** (recursive) |
| Q2 with `uniqueItems` + recursion | **Undecidable** — Bourhis et al., Prop. 4 |

A token mask needs Q2 at every step. Validation after the splice needs only Q1.

> **So the original note's own fallback — *"maybe after the JSON file is edited we
> check the full schema"* — is not the consolation prize. It is the right
> answer, and there is a complexity-theoretic reason why.**

That is worth saying plainly: the instinct in the handwritten note was correct,
and the research supports the throwaway line rather than the main proposal.

---

## 2. What to build

The design follows from §1: **do not try to guarantee validity while decoding.
Guarantee what is free by construction, and check the rest cheaply afterwards.**

```
  ┌── LOCALISE ──┐   ┌── PROJECT ──┐   ┌── GENERATE ──┐   ┌── SPLICE ──┐   ┌── CHECK ──┐
  │ system picks │ → │ sub-schema  │ → │ constrained  │ → │ dict patch │ → │ full      │
  │ the path p   │   │ at p        │   │ decode on it │   │ + validate │   │ validate  │
  └──────────────┘   └─────────────┘   └──────────────┘   └────────────┘   └───────────┘
        P1                  P2                 P3               P4              P5
```

### P1 — Localise

The model **never writes a path**. Two options, in order of preference:

1. **The system computes it.** "Change the answer to Q3" → look up `Q3` in the
   form's own index → `/responses/2`. Deterministic, no error mode.
2. **The model picks from a constrained menu.** Build a trie of legal paths and
   constrain the choice to it. A trie over 100,000 strings compiles in **67 ms**
   and masks at **0.65 µs/token** — this is not a bottleneck.

Why this matters: the addressing evidence in [`03`](03-research.md) §6 is
unambiguous. Line-number addressing collapses to 14–33% pass@1; structural-unit
addressing matches and beats full regeneration. A JSON Pointer chosen by the
system, or chosen from an enumerated menu, is the best case of the best category.

### P2 — Project

For Pydantic, this is a dozen lines:

```python
finfo = Form.model_fields["responses"]          # or walk to the target
Fragment = create_model("Q3Fragment", answer=(finfo.annotation, finfo))
```

Passing the **`FieldInfo` itself** as the default preserves constraints that a
plain default silently drops. Use `TypeAdapter` when the target is not naturally
a model (`List[Row]`, a bare scalar).

**Three traps, all verified by execution**
([`E2`](../research/raw/E2-pydantic-projection.md)):

1. **Dangling `$ref`.** Slicing one `$defs` entry leaves references to siblings
   that did not travel with it. You must compute the **transitive closure** of
   reachable `$defs`. No Pydantic API does this — it is a ~20-line graph walk you
   own.
2. **Recursive models don't inline the root.** The top-level schema is
   `{"$defs": {...}, "$ref": "#/$defs/Node"}`. Always resolve through `$defs`;
   never assume root fields are inlined.
3. **Discriminated unions lose their tag on descent.** If the target is inside
   one arm, carry the discriminator value as pinned context or the splice will
   not round-trip.

**A better framing than "descend through the schema."** Assume-guarantee
reasoning (Pnueli 1984; Clarke, Long & McMillan 1989) says PROJECT should derive
an **interface**, not just a sub-schema: what the fragment must *promise* the
rest of the document, and what it may *assume* about the untouched remainder. In
practice the assumption is the pinned context you already have to carry — the
resolved union branch, the sibling values a conditional depends on — and naming
it as an interface makes it explicit rather than ad hoc. Worth adopting; it costs
nothing and it is how you would explain the design in a paper.

### P3 — Generate

Ordinary constrained decoding against the projected schema. **Structural Tags**
(XGrammar-2; vLLM, SGLang, TensorRT-LLM, MLC-LLM) does exactly this — JSON Schema
as a first-class composable type. Nothing to invent.

The sub-grammar depends only on `(S, path)`, so it is **precompilable and
cacheable**. In the construction regime the "10 rows" grammar is byte-identical
every batch.

### P4 — Splice

```python
d = doc.model_dump()
d["responses"][2] = fragment       # patch the dict
Form.model_validate(d)             # full validation, PTIME
```

> **Never use `model_copy(update=...)` as the splice.** It does not validate.
> `Strict(n=5).model_copy(update={"n": "not an int"})` returns `Strict(n='not an
> int')` with no error. It is a silent-corruption trap that looks safe because it
> type-checks at the call site.

### P5 — Check, and know when the check is a formality

This is where the research pays off. Before generating, **walk the path from root
to target in O(|p|)** and classify the write.

**For in-place replacement at an existing path** — which is what the form case
almost always is — these are **safe** and need no thought:

`required` · `minItems` / `maxItems` · `dependentRequired` · `propertyNames` ·
`additionalProperties`

They are key-set and length constraints, and a replacement changes neither the
sibling key set nor the array length. *(This was my error in
[`02`](02-formulation.md) §6.3, corrected in [`03`](03-research.md) §11.)*

**These are the breakers** — if any appears on the root-to-target path, global
revalidation is load-bearing:

`uniqueItems` · `if`/`then`/`else` · `dependentSchemas` · `oneOf`/`anyOf` ·
`not` · `prefixItems` / tuple-form `items` · `unevaluated*`

**For insert and delete**, the first list becomes breakers too.

**Outside JSON Schema entirely:** a Pydantic `@model_validator(mode="after")`
leaves **zero trace** in the generated schema and cannot be detected by
introspection. `@field_validator` is safe to treat as local. So on an arbitrary
Pydantic model the walk is a *fast path*, never a proof.

> **The payoff of the walk:** on the safe path, the splice is provably sound and
> P5 is a formality you could skip. On the unsafe path, P5 is doing real work and
> you need a retry policy. Knowing which you are on, cheaply, is the practical
> contribution.

**Two things make P5 cheaper than it looks.**

- **Full revalidation is PTIME**, and linear without value equality. Even done
  naively it is not the bottleneck.
- **Incremental revalidation has a known algorithm nobody has pointed at JSON.**
  Ross, Srivastava & Sudarshan (1996) encode integrity constraints as
  materialised views required to be empty, so ordinary incremental view
  maintenance keeps the *validity check* up to date under local updates. There is
  no incremental JSON Schema validator today; this is the recipe for one.

**A second, independent safety diagnostic** is available if you want it:
Freuder's width theorem (JACM 1982) characterises when local consistency
guarantees global consistency, and it is computable. It gives a different handle
on the same question as the keyword walk, and the two should agree.

---

## 3. The construction regime needs one extra thing

The spreadsheet case is not editing, and it has its own failure mode.

**Good news first.** Segoufin & Vianu's theorem says constant-memory streaming
validation is possible **iff the schema is non-recursive**. Flat, Excel-style row
schemas are non-recursive and shallow, so **the bulk case sits inside the
proved-safe class**. Cardinality and pending-obligation constraints need only a
counter and a bitmask.

**More good news, from constraint programming.** Beldiceanu et al. (AAAI 2013)
show that combining a regular-language constraint with **at-most / at-least
cardinality bounds is polynomial**, while **exact-count bounds are NP-hard**.
`minItems`/`maxItems` are at-most/at-least bounds. So the second of the two
genuinely new costs of fragmenting lands on the **tractable** side of a known
boundary — there is a filtering algorithm for it, twenty years old, in a field
the constrained-decoding literature does not cite.

**The exception is value equality.** `uniqueItems`, ids, foreign keys need
Ω(m) state — proved twice, and acknowledged by the tooling community
([`03`](03-research.md) §11). There is no small summary.

**But this is buildable, not blocked.** Uniqueness against a *known finite set*
is a regular constraint. Carry the emitted ids forward and compile them into an
**exclusion trie** — 67 ms for 100,000 strings. No decoder ships cross-call state
today, which is why this is listed as open, but it is an unbuilt feature rather
than an unsolved problem.

**The trap that will actually bite you.** If every chunk sees all prior rows,
input cost goes quadratic: 1,000 chunks × prior rows = **$102.50 of input against
$10.00 of output** on Opus 5. The economics invert.

> **Bound what chunk *i* sees of chunks 1…*i*−1.** Pass the bounded state — the
> counter, the obligation bits, the exclusion set — not the prior rows
> themselves. This is the single most important engineering constraint the
> research surfaced, and it is exactly what the streaming-validation result tells
> you is sufficient.

**Choose the batch size against the decay curve, not the token limit.** Adherence
degrades past **~4,000 output tokens**, thirty times below the 128K hard ceiling.
Batches should be sized to stay well inside that, not to fill the context.

---

## 4. What not to do

- **Do not have the model write JSON Patch.** JSON Whisperer had to invent a
  custom array encoding because "LLMs struggle with array index arithmetic", and
  still landed 5% *below* full regeneration on quality. Both frontier labs
  independently rejected positional addressing for their own edit tools.
- **Do not chase an exact decode-time guarantee.** PSPACE-complete at best,
  undecidable for recursive schemas with `uniqueItems`, and unnecessary given Q1
  is PTIME.
- **Do not worry about distribution distortion.** The headline result claiming it
  is confounded; the re-run reverses it; JSONSchemaBench measures constrained
  decoding *improving* accuracy by +3.3 to +3.7 points. Drop it from the risk
  list.
- **Do not argue this on latency.** Speculative decoding is capped at γ+1 and
  covers the edit case. Concede it and argue cost and quality instead.
- **Do not reach for CRDTs.** They guarantee convergence, not validity. The
  evidence is not an argument but an artifact: Automerge's own core maintainer
  had to build `automerge-jsonschema`, a *restricted* schema vocabulary that
  discards `maxContains`, `contains` and `prefixItems` because ordinary keywords
  **"do not distribute over merges"**. A merge can produce a document violating a
  constraint that **both** inputs satisfied.
- **Do not say "input is cheap, output is expensive."** Production cost
  attribution says input dominates agentic bills. Say the narrower true thing:
  *in a regenerate-the-whole-object turn the input and output token counts are
  equal, so the 50–200× price gap falls entirely on the output side.*
- **Do not rediscover dialogue state tracking.** The flat-slot version of this
  was solved in 2020 and ships in production. Cite it; claim only the nested
  case.

---

## 5. The experiment that settles it

Everything above is design. One measurement decides whether the work is worth
doing, and it appears never to have been run for schema-constrained output.

> **Take a 10–20K-token Pydantic object. Change one leaf. Regenerate the whole
> thing. Diff every field that was supposed to be untouched. Repeat across
> turns.**

That yields the untouched-region integrity number directly. The surrounding
evidence says it will be bad — DELEGATE-52 measures **~25% of document content
corrupted** by the end of long workflows and ~50% by turn 20, with no plateau to
100 turns; a transcription stress test finds **0% perfect runs at 300 items**.
But those are adjacent tasks, not this one.

Three things make this experiment unusually cheap and unusually decisive:

1. **The comparison is free.** Fragment-wise integrity is 1 *by construction* —
   bytes never regenerated cannot change. You only have to measure the baseline.
2. **It targets the unmeasured regime.** Every published number sits at
   ρ ≈ 0.3–0.5 on documents under 10K tokens. This is ρ ≈ 0.006.
3. **The metric already exists.** VOLTBench's Structured Content Accuracy and
   STED (semantic tree edit distance for JSON) are both off the shelf.

Add a second, cheaper run for the compounding claim: generate a 20-field object
whole, then field-by-field, and compare object-level accuracy. The prediction —
0.97 per field giving ~0.54 whole and ~0.98 iteratively — is already measured
elsewhere and should reproduce.

---

## 6. What would kill this

Stated plainly, because a research plan should say what would falsify it.

| Risk | Why it is serious | Current evidence |
|---|---|---|
| **Localisation error replaces validity error** | "The system changed the wrong field" is *less* detectable than invalid JSON. You trade a loud failure for a quiet one. | AdaEdit routes at >90%, but for a coarser decision. **Untested for us.** |
| **The model misses implied updates** | Changing one field often implies changing a sibling; a fragment cannot see that. | **Observed empirically** in JSON Whisperer. Real. |
| **Inference through the projection** | Hiding a field does not stop the model reconstructing it from visible context. | 1 case in 5,520 PatchOptic runs. Small but real. |
| **Integrity turns out fine** | If full regeneration corrupts rarely at realistic sizes, the strongest argument evaporates and only cost remains. | **This risk materialised — see §9.** 12/12 clean turns at 17K tokens. Cost now carries the case. |
| **Per-call overhead eats the win** | Many small calls multiply fixed costs and input tokens. | The quadratic input trap is real; bounded state is the mitigation. |

The second row is the one I would watch. It is the failure mode full
regeneration genuinely does not have, and no amount of schema machinery fixes it
— it is a reasoning limitation, not a validity one. A serious system needs an
explicit answer, most likely "let the model nominate *several* paths and generate
several fragments in one constrained pass".

---

## 7. If this became a paper

The contribution is **not** the architecture — PatchOptic built something close —
and **not** the flat-slot case, which dialogue state tracking solved in 2020. Be
disciplined about that; the claim is stronger for being narrow. What is left is
genuinely unclaimed:

1. **The JSON Schema instance of the compositional class.** Shuffle-closedness,
   local tree grammars and local DTDs are the same idea found three times for
   XML between 2004 and 2007. Nobody has stated it for JSON Schema — and JSON has
   a keyword, `uniqueItems`, that falls outside every framework XML built (not
   MSO- or tree-automata-definable).
2. **The O(|p|) safety decision procedure**, with the replacement-versus-insertion
   distinction that materially enlarges the safe fragment, plus worked
   counterexamples. Cross-checkable against Freuder's width diagnostic.
3. **Incremental and streaming JSON Schema validation.** Both exist for XML;
   neither exists for JSON. And the algorithm to build the incremental one is
   already known (Ross, Srivastava & Sudarshan 1996) — it has simply never been
   pointed at JSON Schema.
4. **The first measurement in the large-`N`, low-ρ regime**, with
   untouched-region integrity as the headline metric.
5. **Connecting three literatures that do not cite each other.** Constrained
   decoding knows how to enforce a grammar at decode time. Decomposed extraction
   knows field-by-field beats whole-object. Constraint programming has been
   propagating grammar constraints jointly with cardinality since 2004 and has
   the tractability boundary already drawn. None of the three cites the others.
6. **Extending fragment-wise generation from flat slots to nested schemas** —
   which is precisely where DST stopped and where compositionality first becomes
   a real question.

And there is a good framing line available, honestly earned: **three separate
communities — the XML patch RFC, the W3C XQuery Update working group, and the
EDBT projection-update-merge line — arrived at exactly this question and
explicitly set it aside.** RFC 5261 delegates schema validity to the caller;
Benedikt & Cheney found XQuery Update's own typing rules unsound for `transform`;
Baazizi et al. wrote *"the revalidation issue is not considered in this paper."*

---

## 8. Recommendation

**Build it, but build the cheap version, and measure first.**

1. **Run the integrity experiment** (§5). It decides whether the motivating
   argument is real, and it is currently unmeasured by anyone.
2. **Build P1–P5 with the O(|p|) walk** as a thin library over Pydantic +
   Structural Tags. There is no new algorithm here; the value is that the walk
   tells you when the final check is a formality and when it is load-bearing.
3. **Do not build a decode-time residual enforcer.** The complexity results say
   it is not worth it and sometimes not possible.
4. **For the construction regime, build bounded state first** — counter,
   obligation bits, exclusion trie — because the quadratic input trap will
   otherwise invert the economics before any of the rest matters.

---

## 9. Measured, 2026-09-07 — and it changes the emphasis

Step 1 has now been run. See [`../EXPERIMENT.md`](../EXPERIMENT.md) for the
design and full data. `gemini-3.5-flash`, a 16,895-token form, one edit per turn.

| arm | perfect integrity | out tokens | latency |
|---|---|---|---|
| baseline (regenerate all) | **12/12** | 16,869 | 54.5 s |
| fragment | 1/1 | **98** | **4.35 s** |

**The cost case is confirmed and larger than predicted: 172× fewer output
tokens, 12.5× lower latency.**

**The integrity case is not supported.** Twelve consecutive turns, a ~17,000-token
document retyped each time, **zero corrupted leaves** and no compounding — turn
12 as clean as turn 1. The literature predicted ~25% of content corrupted by the
end of a long workflow. None appeared.

So the paragraph that used to close this document — *"the strongest case is not
tokens and not speed, it is that bytes never regenerated cannot be corrupted"* —
**is not supported by the first measurement**, and it was the argument I leaned
on hardest. Recorded plainly rather than quietly revised.

### The likely reason, and why it improves the thesis

The corruption evidence in [`03`](03-research.md) §4 comes from *unconstrained*
regeneration — agentic document workflows, free-text code editing. This baseline
arm regenerated **under a schema constraint enforced at decode time**, which
fixes the key set, the types and the structure, leaving far less room to drift or
elide.

If that is what is happening, the argument relocates rather than collapses:

> The integrity argument applies to **unconstrained** regeneration. For output
> that is already constrained-decoded, the reason to generate fragments is
> **cost and latency** — and that reason is worth 172×.

That is narrower, more defensible, and directly falsifiable: rerun the same grid
with the constraint dropped from the baseline arm and see whether corruption
appears. That is now the single most informative next experiment, ahead of the
thick design.

**What the result cannot bear.** One seed, one size, one model, a synthetic
corpus with regular repeating structure — which is plausibly easier to copy
faithfully than real heterogeneous content. A null at n=1 is evidence, not proof.
But it is a null at the size and turn-depth where the effect was predicted to be
*largest*, which makes it worth considerably more than a null at the easy end.

### Revised recommendation

Lead with **cost and latency**, which are measured, large, and hold regardless of
why the corruption did not appear. Treat integrity as an **open question with one
negative datapoint**, and resolve it by running the unconstrained baseline. Do
not put the integrity claim in a paper abstract until that runs.

---

*Back to: [`00`](00-original-note.md) · [`01`](01-problem-plain-english.md) ·
[`02`](02-formulation.md) · [`03`](03-research.md)*
