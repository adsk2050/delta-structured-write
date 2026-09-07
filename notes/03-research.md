# 03 — What the literature says

*Step 2 deliverable. Answers to the open questions of
[`02-formulation.md`](02-formulation.md), from seven parallel literature
searches. Detailed source reports with full citations and provenance markers are
in [`../research/raw/`](../research/raw/).*

**Provenance convention**, carried through from the raw reports:
**PRIMARY** = read from the paper, spec, source code, or vendor's own page;
**SECONDHAND** = seen only via a third party. Dates are given wherever recorded;
numbers in this field go stale fast.

**Completeness.** All theory and economics questions are resolved. Two agents
were still surveying frameworks and constraint-programming decomposition when
this was written; neither can change the verdict.

---

## 0. The short version

Eight things are now settled.

1. **The mechanism already ships.** Constrained decoding against a projected
   sub-schema is deployed under a name we did not know: **Structural Tags**.
   Step (c) of the architecture needs no research at all.
2. **The residue we feared is almost empty** — today's engines *already* fail to
   enforce those keywords during ordinary whole-document generation. The true new
   cost of going fragment-wise is **two things**, not twelve.
3. **The safe fragment is bigger than I claimed.** Key-set and length constraints
   cannot be disturbed by an *in-place replacement*, which is what the form case
   almost always is.
4. **The strongest argument is quality, not cost.** Per-field accuracy compounds:
   0.97 over 20 fields gives ~0.54 for the object. Measured — and measured to be
   fixable by generating field-wise.
5. **Full regeneration provably corrupts, and it has now been measured** — ~25%
   of document content by the end of long workflows, ~50% by turn 20.
6. **The cost argument survives; the latency argument mostly does not.**
   Speculation is capped at γ+1 and reduces no billed output tokens.
7. **The theory is settled and it favours the fallback design.** Validating after
   a splice is PTIME; masking exactly during decoding is PSPACE-complete at best,
   and **undecidable** for recursive schemas with cross-position value equality.
8. **The compositional class has three names already** — shuffle-closedness,
   local tree grammars, local DTDs — but **the JSON Schema instance is
   unclaimed**, and no incremental or streaming JSON Schema validator exists.

The opening is narrow and real: the constrained-decoding literature and the
decomposed-extraction literature **do not cite each other**, and three separate
communities reached this exact question and explicitly declined it.

---

## 1. The keyword audit — the single most important result

This was meant to be a background check. It turned out to reshape the problem.

**Verified from primary sources** — llguidance `docs/json_schema.md`,
outlines-core `parsing.rs`, vLLM `backend_xgrammar.py`, llama.cpp
`grammars/README.md`, plus the OpenAI/Azure, Anthropic and Gemini docs:

> **`uniqueItems`, `if`/`then`/`else`, `dependentRequired`, `dependentSchemas`,
> `not`, `propertyNames` and `contains` are enforced by ZERO engines, in ZERO
> products, during ordinary whole-document constrained generation.**

And `required` is enforced only by a trick: engines **fix property order** to
schema-declaration order, which is itself a documented departure from JSON
Schema semantics (where object keys are unordered).

The consequence for us is large. [`02`](02-formulation.md) §6.3 listed a dozen
"non-local" keywords as the cost of going fragment-wise. Most of that list is
not a cost of *our* approach — it is the pre-existing, universally unenforced
remainder that full generation already ignores.

> **The true new cost of fragment-wise generation is two things:** `required`
> across a fragment boundary, and `minItems`/`maxItems` on a containing array.
> Both are counting constraints. Both are cheap to carry (§4.3).

### 1.1 Constrained decoding already fails silently, at scale

**JSONSchemaBench, arXiv:2501.10868, Table 4.** PRIMARY. Best empirical coverage
on GitHub-Hard is **41%**; on JSONSchemaStore **38%**; Gemini managed **7%** on
GitHub-*Easy*.

- **XGrammar had 38 distinct categories of under-constrained failure** — accepted
  the schema, then generated output violating it.
- **vLLM ships a hand-maintained denylist** because XGrammar *silently drops*
  `minLength`/`maxLength` when combined with `pattern`.
- **Gemini and Outlines both silently degrade `oneOf` to `anyOf`.**
- **Outlines cannot enforce `minimum`/`maximum` at all** and truncates recursion
  at depth 3.

This reframes the entire safety argument. Fragment-wise generation does not have
to be perfect. **It has to be no worse than a baseline that is already leaky, and
honest about where it sits** — exactly the standard set in
[`02`](02-formulation.md) §6.2.

---

## 2. The mechanism already ships: Structural Tags

**XGrammar-2's Structural Tags**, deployed in vLLM, SGLang, TensorRT-LLM and
MLC-LLM. Treats a JSON Schema as a **first-class atomic type composable inside a
larger structure**, with a `TriggeredTags` combinator that switches which
constraint is active based on the model's own earlier output. Reported **100%
schema accuracy on BFCL-V3**.

That is step (c) of the architecture — constrain a fragment against a projected
sub-schema — already built, deployed in four inference engines, and named.

**State-conditioned grammars are likewise solved**, and older than expected:
**GENRE** (2021), **PICARD** (2021 — rejects tokens naming tables or columns
absent from the live database schema), **Trie Automata** (2026).

### 2.1 The compilation-cost objection dissolves

I had assumed a delta grammar must be recompiled per request because it depends
on the document. Under the reframing that is mostly false, and the numbers say
even the hard case is fine:

- A **projected sub-grammar depends only on `(S, path)`** — a finite,
  precompilable set. The spreadsheet's "10 rows" grammar is **byte-identical
  every batch** and hits every cache.
- Anthropic caches compiled grammars **24 h from last use**, invalidated only by
  a schema-structure change. OpenAI charges first-use latency only.
- Even a genuinely document-derived constraint is cheap: a **trie over 100,000
  strings compiles in 67 ms and masks at 0.65 µs/token** (arXiv:2608.12574).

Against which, Outlines' own compile cost is a real operational limit — 20–40 s
for an FSM index in one reported case, and an OOM after ~1600 s on a 32 GB
machine. Engine choice matters; the objection does not.

---

## 3. The quality argument — stronger than the cost argument

**arXiv:2604.27906.** PRIMARY. The mechanism is simple arithmetic and the
consequences are large.

> With per-field accuracy 0.97 across 20 fields, single-pass **object** accuracy
> is **~0.54**. Iterative per-field generation with validation reaches **~0.98**.

Their measured cascade on a real task: field F1 **97.53%** → object accuracy
**90.42%** → output accuracy **62.67%**. Their iterative pipeline beat GPT-5.5 at
high reasoning effort (44.00%) and Gemini 3.1 Pro (61.67%).

This is hypothesis **H6** from [`02`](02-formulation.md) §11, confirmed with a
mechanism: errors compound multiplicatively across fields, so the object is
always worse than its fields, and the gap widens with field count. Generating
field-wise does not merely save tokens — it **breaks the compounding**.

Corroborating from a different angle, **arXiv:2604.27296**'s long-code subset:
FullCode 39.75% pass@1 at 648 tokens vs structure-addressed 40.69% at 482 tokens.
Accuracy slightly *up*, tokens down 26%.

### 3.1 The distortion worry was misplaced

I expected a narrower grammar to distort the model's distribution more. **No
published evidence supports that.**

- Tam et al.'s "Let Me Speak Freely?" is **confounded** — different prompts per
  condition. The .txt/Outlines re-run **reverses** the result.
- **JSONSchemaBench independently measures constrained decoding *improving*
  accuracy by +3.3 to +3.7 points.**
- The one paper sweeping schema complexity (arXiv:2606.25605) finds a **binary,
  not graded**, effect.
- The reproducible damage is **token misalignment** (−10.7 GSM8K points), and it
  is **fully fixed by DOMINO**.
- The genuine, unfixable distortion (grammar-aligned decoding / ASAp) is
  **#P-hard for everyone** and orthogonal to fragment size.

Drop this from the risk list.

---

## 4. Does full regeneration actually corrupt? Yes — now measured directly

In the first draft of this note I listed "untouched-region integrity, measured
directly" as unknown. It is not.

**DELEGATE-52 — Laban, Schnabel & Neville, arXiv:2604.15597, April 2026.**
PRIMARY. 19 models, 52 domains.

> Frontier models (Gemini 3.1 Pro, Claude Opus 4.6, GPT-5.4) **corrupt an average
> of 25% of document content by the end of long workflows**; **~50% across all
> models by turn 20**. *"Each 1k-token increment progressively increases
> degradation"*, with **no plateau out to 100 turns.**

**arXiv:2601.03640**, verbatim transcription stress test: **0% perfect runs at
N=300 items**, down from 44% at N=100.

And speculative decoding is **provably incapable** of helping here: it is
distribution-preserving *by theorem*, so it reproduces every one of those errors
faithfully, only faster.

Supporting evidence from adjacent domains:

- **Aider's laziness benchmark.** PRIMARY. Under whole-block rewrite, GPT-4
  Turbo emitted lazy placeholders — `# ...add logic here...` — on **12 of 89
  tasks (13%)**; unified diffs cut it to **4 of 89 (4.5%)**. Aider had to build
  an AST-node-count detector to catch silent content loss during full rewrites.
- **Displacement Rate**, arXiv:2608.25358. PRIMARY. Values produced correctly but
  placed at the wrong structural position: GPT-4o **24.2%**, DeepSeek-V3 26.2%,
  DeepSeek-V4-Flash 35.4%, Qwen2.5-7B 73.8%. *"Structural fidelity degrades
  earlier and faster than content accuracy."*

**A caveat that discounts much of the code-editing literature.** "Edit, But
Verify", arXiv:2604.05100, PRIMARY: *"**59% of low-coverage suites [are] unable
to detect modifications outside edit regions**."* The benchmarks cannot see the
failure they would need to see, so published pass rates **overstate** real
correctness and silent corruption is systematically under-measured.

---

## 5. Direct prior work: built twice, opposite results

### 5.1 JSON Whisperer — the pessimistic result

**Duanis, Greenstein-Messica & Habba (Lightricks), EMNLP 2025 Industry Track,
arXiv:2510.04717.** PRIMARY. The original note's idea exactly: the LLM emits an
RFC 6902 patch.

| | Result |
|---|---|
| Token reduction | **31%** |
| Edit quality vs full regeneration | **within 5%** — slightly *worse* |
| Latency | −42.3% (Claude Sonnet), −31.5% (GPT-4o-mini) |

Two findings matter more than the headline:

- **Plain RFC 6902 does not work.** They had to invent **EASE**, turning arrays
  into dictionaries with stable keys, because "LLMs struggle with array index
  arithmetic".
- **Models "miss necessary updates"** — changing one field implies changing a
  related one, and a model seeing only a fragment does not see the implication.

**Morph's fast-apply corroborates the magnitude:** 40% fewer tokens, 1.8×.

### 5.2 PatchOptic — the optimistic result, and it is our architecture

**Bai & Cai, arXiv:2607.05483, July 2026.** PRIMARY. *Preprint; peer-review
status unconfirmed.* LOCALISE → PROJECT → GENERATE → SPLICE → verify, built, and
framed as **optics** (§7). PatchBench: 46 cases, 5,520 live runs.

| Metric | Actor | Unconstrained | PatchOptic | Δ |
|---|---|---|---|---|
| Semantic pass rate | GPT-5-mini | 0.609 | **0.779** | **+17.0 pp** |
| Semantic pass rate | Mistral 7B | 0.560 | **0.690** | **+13.0 pp** |
| Content quality | GPT-5-mini | 0.925 | 0.927 | flat |
| Leak rate | GPT-5-mini | 0.315 | **0.002** | −31.3 pp |
| Mean tokens | GPT-5-mini | 817.5 | 718.6 | −12.1% |

Their runtime verifier took unsafe accepts from 2.2–3.1 per round to **zero**,
and rejected 9/9 adversarial patches sourcing from unauthorised regions.

**A residue we had not identified.** One leak survived in 5,520 runs: the model
*inferred* a protected term from visible context rather than copying it. Hiding
a field from the projection does not prevent the model reproducing content it can
infer.

### 5.3 Reconciling them, and the regime nobody measured

The likely reconciliation: **JSON Whisperer asked the model to write the patch;
PatchOptic had the system define the region and verified the write.** That is
precisely the reframing your examples forced.

But there is a second, sharper reconciliation, and it matters for what to
believe. Let `ρ = k/N`, the fraction of the document that changes.

> JSON Whisperer and Morph both measure **ρ ≈ 0.3–0.5** on 5–10k-token artifacts.
> The form case is a 120-token fragment of a 20,000-token form: **ρ = 0.006**.

A patch carries fixed per-operation overhead, so at ρ ≈ 0.4 the patch is nearly
as long as the document and 31% is all arithmetic allows. At ρ = 0.006 the same
cost model predicts **~39× on dollars and ~109× on latency**. **Nobody has
measured that regime.** The 31% figure *confirms* the cost model rather than
bounding it — and anyone quoting it as the ceiling is extrapolating from the
regime where the approach looks worst.

---

## 6. The addressing question — settled, and favourable

**Cheng et al., "To Diff or Not to Diff?", arXiv:2604.27296, April 2026.**
PRIMARY. Model and tasks held fixed; only the addressing scheme varies.
Qwen2.5-Coder-7B, average pass@1 over five benchmarks:

| Addressing scheme | pass@1 |
|---|---|
| FullCode (whole-file regeneration) | 57.07 |
| MinUniDiff — line-number indexed | **14.07** |
| UniDiff — line-number indexed | **33.15** |
| ContentDiff — content/string matched | 54.43 |
| BlockDiff — structural unit | 55.98 |
| FuncDiff — structural unit | 57.32 |
| **FuncDiff + AdaEdit** | **57.95** — beats regeneration |

Their diagnosis: *"LLMs struggle to generate precise line numbers and offsets,
and this issue persists even when the input code is explicitly numbered."*
Numbering the input does not fix it.

The three tiers map onto our design space:

| Their tier | Our analogue |
|---|---|
| line-number | raw array index / byte offset — **catastrophic** |
| content matching | `str_replace`, `apply_patch` — **good** |
| **structural unit** | **JSON Pointer into a known schema — best** |

`/responses/2/answer` names a schema-defined unit. That is the category that
matched and beat full regeneration.

Their AdaEdit router picks the cheaper-sufficient format per instance at **>90%
accuracy** — evidence our own "fragment or regenerate?" decision is learnable.

**Converging industrial evidence.** Both frontier labs independently rejected
positional addressing. Anthropic's `str_replace_based_edit_tool` is 100%
content-addressed on the write side and treats a non-unique match as a **hard
error**. OpenAI's `apply_patch` V4A uses context-anchored hunks, so "patches
remain valid even if the file has been modified" (SECONDHAND rationale).

---

## 7. The economics

### 7.1 The price asymmetry — stated carefully

Per-token list prices, 2026-09-07. PRIMARY.

| Model | Output ÷ input | **Output ÷ cached input** |
|---|---|---|
| GPT-5.6 Sol | 5.0× | **50×** |
| GPT-5.6 Terra / Luna | 6.0× | **60×** |
| GPT-5 | 8.0× | **80×** |
| Claude Opus 5 / Sonnet 5 / Haiku 4.5 | 5.0× | **50×** |
| Claude Fable 5.1 | 5.0× | **200×** |

The cached-input discount has deepened every generation: 0.5× of input on
GPT-4o, 0.25× on GPT-4.1, 0.1× on GPT-5 and later.

> **Do not write "input is cheap, output is expensive."** Production
> cost-attribution data says input *dominates* agentic bills. The defensible
> claim is narrower and still decisive: **in a regenerate-the-whole-object turn
> the input and output token counts are equal, so the 50–200× price gap falls
> entirely on the output side.**

### 7.2 Speculation is capped, and buys latency only

**Leviathan et al., ICML 2023, arXiv:2211.17192.** PRIMARY. Theorem 3.8 gives
walltime improvement `(1 − α^(γ+1)) / ((1 − α)(γc + 1))`. With a prompt-lookup
draft `c ≈ 0`, and as `α → 1` — the "regenerate with one small change" case —
this collapses to **γ + 1**.

Real γ is small (prompt-lookup defaults to 10; vLLM's n-gram to 5), so the honest
ceiling is **5–20× latency**. Best published is EAGLE-3 at 6.5× with acceptance
length 4.05–7.5. **Nothing published approaches `N/k`.**

> **Every speculative technique reduces wall-clock time. None reduces the billed
> output-token count.**

- **OpenAI Predicted Outputs**, verbatim: *"Any rejected tokens are still billed
  like other completion tokens."* Best case you pay full-regeneration price;
  worst case **more**. Azure adds it can be a *latency regression* too.
- **It excludes `tools`** — so it is unavailable for structured output emitted
  through tool calls, which is most of it.
- **No GPT-5-family support** on OpenAI's or Azure's list as of 2026-09-07 — ~1.5
  years without extension to the flagship line.
- **No Anthropic or Google equivalent.** NEGATIVE RESULT, searched. Anthropic
  instead sells fast mode at **2.5× throughput for 2× price** — the clearest
  statement that latency and cost are separate goods on a hosted API.

Self-hosted is the exception: on your own GPU, the latency win *is* a cost win.

**An untested assumption underneath every "3–5× for structured output" claim:**
no published measurement exists of speculative decoding running *with* a
JSON-schema grammar. Grammar validation is the non-parallelisable path — up to
**37.5% slower at batch 512**.

### 7.3 The quadratic input trap — a design constraint, not an objection

Chunked construction multiplies *input*. If each of 1,000 chunk calls sees all
prior rows, the input cost on Opus 5 is **$102.50 against $10.00 of output.**

> **The design must bound what chunk *i* sees of chunks 1…*i*−1.** This is the
> single most important engineering constraint the research surfaced, and it
> follows directly from the streaming-state question in
> [`02`](02-formulation.md) §7 — the bounded carry is not just a nicety, it is
> what keeps the economics from inverting.

---

## 8. The ceiling and the decay — the construction regime

### 8.1 The hard ceiling

Max output tokens, 2026-09-07. PRIMARY. Claude Fable 5.1 / Opus 5 / Sonnet 5:
**128K**. Haiku 4.5: 64K. GPT-5.6 family, GPT-6 Astra: 128K. Gemini 3.1 Pro:
65,536. DeepSeek V4: 384K.

A 10,000-row table at ~30–40 tokens per row is 300–400K tokens — **above every
frontier ceiling**. For that workload fragmenting is not an optimisation, it is
the only way through, and no decoding technique raises `max_tokens`.

### 8.2 The soft ceiling is thirty times lower, and it is the real story

**LongGenBench, arXiv:2409.02076.** PRIMARY.

- Adherence degrades sharply **beyond ~4,000 output tokens**.
- At **16K**: GPT-4o-mini reaches 97% *completion* but **27.9% instruction
  adherence**. Completion and correctness decouple.
- At **32K**: total collapse; no model completed.
- **~45% of long outputs showed significant repetition.**
- Long-*input* ability barely predicts long-*output* ability (Pearson **0.51** at
  16K, **0.66** at 32K). "It has a 1M context window, so a 10K-row table is fine"
  is a non sequitur.

**LongWriter, ICLR 2025, arXiv:2408.07055.** PRIMARY. The output ceiling is a
*training-data artifact* — models see almost no long completions in SFT. Note
what their fix is: **AgentWrite decomposes ultra-long generation into subtasks.**
Fragmentation is already the state-of-the-art response.

**VOLTBench, arXiv:2605.01357**, May 2026. PRIMARY. Defines **Structured Content
Accuracy = correct sections / required sections** — exactly the per-row metric
[`02`](02-formulation.md) §10 asked for. Models fail roughly half of tasks at 50
sections.

> **The effective ceiling is ~4,000 output tokens, not 128,000.** That binds on
> documents far smaller than anyone expects, and it has nothing to do with money.

---

## 9. The vendor and protocol layer — a clean negative result

**No vendor or protocol supports semantic partial tool-call arguments.** MCP,
OpenAI, Anthropic and Gemini all require the complete argument object on every
call. All four VERIFIED from primary specs.

The two features that look like progress are not:

- **Streaming argument deltas** (`input_json_delta`,
  `response.function_call_arguments.delta`) are **transport deltas of a full
  generation.** The model still generates every token. They save nothing in
  tokens, cost, or generation time.
- **Prompt caching** is input-side only. Anthropic, verbatim: *"Prompt caching
  has no effect on output token generation."*

No feature requests found anywhere. OpenAI actively **400s** partial tool
replies. Anything built here must be a client-side wrapper.

### 9.1 No structured-output library supports this either

Audited: Instructor, BAML, Outlines, Guidance, Marvin, Mirascope, DSPy,
LangChain, LlamaIndex. **Clean negative across all nine** — none supports
sub-schema projection, and none has "update this object" as a first-class
operation.

Two findings inside that negative are worth more than the negative itself:

- **There is documented demand.** Outlines issue **#1383** is a practitioner
  hitting exactly this wall and falling back to raw `pydantic.create_model()`,
  which they describe as "clunky". BAML's `TypeBuilder` / `@@dynamic` is
  **additive-only** and cannot narrow a schema — confirmed by its own open issue
  **#2980**.
- **Guidance could already do it, by hand.** Its immutable `lm +=` composition
  plus `gen_json(schema=...)` has every primitive the architecture needs.
  **Nobody has packaged it.** That is the shape of a missing library, not a
  missing capability.

For splicing specifically, **LangGraph's channel reducers solve P4** — applying a
typed partial update to state — but offer nothing for LOCALISE or PROJECT.
CrewAI, AutoGen and the OpenAI Agents SDK have **no merge mechanism at all**.

### 9.2 The flat case was solved in 2020, in a different vocabulary

This is the strongest "already solved" finding in the review, and it narrows the
claim that can honestly be made.

**Dialogue state tracking** faced the form problem — a slot-filling state updated
turn by turn as a user corrects individual fields — and solved the delta version
of it years ago:

- **SOM-DST** (2020) predicts a **state operation per slot** (carry / delete /
  update) rather than regenerating the whole belief state.
- **MinTL** (2020) uses **Levenshtein belief spans** — emit the edit to the state,
  not the state.
- **Rasa Pro's CALM** architecture ships an **LLM-driven `SetSlot`-per-changed-field
  mechanism in production today.**

> **So for flat, developer-declared slot schemas, the answer is (a) already
> solved — and has been since 2020.**

What DST did *not* solve is what makes our problem hard: **nesting, recursion,
`$ref` structure, arrays with cardinality and uniqueness constraints, and
conditional sub-schemas.** A belief state is a flat bag of slots; a Pydantic form
with `list[Response]` inside `Form` inside a discriminated union is not. The
compositionality question ([`03`](03-research.md) §11) simply does not arise for
flat slots, because every slot is trivially independent.

**This sharpens the contribution rather than eliminating it:** the flat case is
prior art and should be cited as such; the **nested, schema-structured case is
the unclaimed part**, and it is exactly the case the user's form and spreadsheet
examples occupy.

---

## 10. The formal home: lenses give vocabulary, not the theorem

PatchOptic's "optics" framing pointed at the right literature, but the theory
review returned a sharper and more useful answer than expected.

A **lens** is a pair `get : S → A`, `put : A × S → S`. Our PROJECT is `get`; our
SPLICE is `put`. The foundational work is **Foster, Greenwald, Moore, Pierce &
Schmitt, "Combinators for Bidirectional Tree Transformations", POPL 2005 / ACM
TOPLAS 2007**.

> **The well-behavedness laws give us nothing.** GetPut, PutGet and PutPut are
> all **vacuously true** for an in-place splice at a fixed path. One hundred
> percent of the content sits in the **(Put) typing condition**,
> `put(A × C) ⊆ C` — which is the residual question restated, not answered.

That is worth knowing precisely, because it prevents a plausible mistake: citing
lens laws as if they established splice soundness. They do not.

There is also a directional mismatch. **Lens languages are synthesis-oriented** —
you build a lens and its types come out. Ours is **analysis-oriented**: infer the
view type from a schema somebody else wrote. The field never needed that
direction.

### 10.1 Three literatures reached this exact boundary and stopped

The most quotable finding in the whole review:

- **RFC 5261** (XML patch) explicitly **delegates schema validity of the patched
  document to the caller**.
- **Benedikt & Cheney** found the W3C XQuery Update Facility 1.0's own typing
  rules **unsound for `transform`**.
- **Baazizi et al. (EDBT 2011)** built and proved a project → update → merge
  pipeline with depth-bounded memory, then wrote: *"the revalidation issue is not
  considered in this paper."*

Three separate communities built the machinery, arrived at our question, and
declined it.

### 10.2 But the theorem exists for XML — and its price is free for us

**Cheney's Flux (2007) already proves update soundness (Thm 3) for XML.** The
price is a **child-axis-only path language** — and that is *exactly what JSON
Pointer already is*. The restriction that made the XML result feel narrow costs
us nothing.

Regular-expression-type subtyping, which the proof leans on, is EXPTIME-complete.

---

## 11. Adjudicating the conjectures — all three resolved

| | Status |
|---|---|
| **C1** — prefix-feasibility intractable | **CONFIRMED, and stronger than stated** |
| **C2** — a compositional fragment exists | **CONFIRMED in substance; the class is prior work, the JSON instance is unclaimed** |
| **C3** — bounded state iff counting/propositional | **CONFIRMED, with one correction** |

### C1 — Q2 *is* satisfiability

Not "as hard as". At the empty prefix, "does some completion land in the
residual?" is literally "does a value satisfying `S′` exist", with linear
reductions both ways. So Q2 inherits **Bourhis, Reutter, Suárez & Vrgoč, PODS
2017**, Props. 7 and 10 (read at primary source):

| Fragment | Complexity of Q2 |
|---|---|
| Non-recursive, no `uniqueItems` | **PSPACE-complete** |
| Recursive, no `uniqueItems` | **EXPTIME-complete** |
| With `uniqueItems`, non-recursive | PSPACE-hard, in EXPSPACE (**upper bound not known tight**) |
| With `uniqueItems`, recursive | EXPTIME-hard, in 2EXPTIME (**not known tight**) |

Against Q1 (membership) at **PTIME-complete**, linear without value equality
(their Prop. 3).

> **This is the formal justification for the fallback design.** Generate, splice,
> then validate is PTIME. Exact decode-time masking is PSPACE-complete at best.
> The gap is not an implementation detail; it is a complexity class.

**And there is a hard wall nobody had flagged.** Their **Prop. 4: satisfiability
is UNDECIDABLE with cross-position value equality plus recursion, even in the
negation-free fragment** (by reduction from two-counter machines). So an exact
decode-time guarantee is not merely expensive for recursive schemas with
`uniqueItems` — it is impossible.

### C2 — the class already has three names; the JSON instance does not

The compositional fragment is real, and it was independently discovered three
times between 2004 and 2007:

| Name | Source |
|---|---|
| **shuffle-closedness** | Foster et al., TOPLAS 2007 — the typing side-condition on their `map` combinator |
| **local tree grammars** | Murata et al., ACM ToIT 2005 |
| **local DTDs** | Balmin, Papakonstantinou & Vianu, TODS 2004 |

Two corrections to my breaker list in [`02`](02-formulation.md) §6.3:

- **It was too strong for in-place replacement.** `required`, `minItems`/
  `maxItems`, `dependentRequired`, `propertyNames` and `additionalProperties` are
  **key-set and length constraints that a replacement cannot disturb** — swapping
  the value at an existing path changes neither the sibling key set nor the array
  length. They break insert and delete, not replace. **So the safe fragment is
  materially larger than I claimed, and it is largest exactly in the Pydantic-form
  case**, where the operation is almost always in-place replacement.
- **It missed three breakers:** `not`, `prefixItems` / tuple-form `items`, and the
  `unevaluated*` keywords.

> **The JSON Schema instance of this class is unclaimed.** That — plus an
> **O(|p|) root-to-target decision procedure** and worked counterexamples — is
> the contribution available here.

**The Pydantic caveat stands.** A `@model_validator(mode="after")` leaves zero
trace in the generated JSON Schema, and Pydantic exposes no introspection API to
detect one (VERIFIED by execution,
[`E2`](../research/raw/E2-pydantic-projection.md)). So the decision procedure is
sound on a JSON Schema but not on an arbitrary Pydantic model, and global
revalidation stays load-bearing. `@field_validator` constraints depend only on
their own field and **are** safe to treat as local.

### C3 — confirmed, with a fourth memory term I had missed

**Segoufin & Vianu, "Validating Streaming XML Documents", PODS 2002.** PRIMARY,
full text read.

| Result | Statement |
|---|---|
| Thm 3.1 / 3.2 | constant-memory streaming validation **⟺ non-recursive** schema |
| Thm 5.1 | otherwise, a depth-bounded pushdown automaton suffices |
| Thm 4.2 | deciding recognisability is EXPTIME; **PTIME for 1-unambiguous** regular expressions |

Ω(m) for uniqueness is proved two ways: a two-line fooling-set argument, and
Pezoa et al.'s non-regularity of `uniqueItems`.

**The correction:** my conjecture said the dividing line was *constraint kind*
(counting vs propositional vs value-equality). The real dividing line is
**recursion and nesting depth**. Depth is a fourth memory term I had omitted.

**And this is good news for the spreadsheet case.** Flat, Excel-style row schemas
are **non-recursive and shallow**, so the bulk construction regime sits **inside
the proved-safe class** — constant-memory streaming validation applies.

### 11.1 The operator that puts JSON outside XML's frameworks

One clean structural finding: **`uniqueItems` is the keyword that takes JSON
outside every framework XML built.** It is not MSO- or tree-automata-definable,
and the state-of-the-art JSON Schema witness generator excludes it. Everything
else transfers; this does not.

---

## 12. What the neighbouring fields give us

Seven adjacent formalisms were assessed. Three do not transfer, and saying so
precisely is worth as much as the ones that do.

### 12.1 Does not transfer — with a smoking gun

**JSON CRDTs** (Kleppmann & Beresford 2017; Automerge; delta-state CRDTs)
guarantee **convergence, not validity**. The evidence is better than an argument:
Automerge's own core maintainer had to build **`automerge-jsonschema`**, a
*restricted* JSON Schema vocabulary that throws out `maxContains`, `contains` and
`prefixItems` because ordinary schema keywords **"do not distribute over
merges"**.

> A CRDT merge can produce a document that violates a constraint **both**
> pre-merge documents satisfied. That is a sharp, citable negative result, and it
> disposes of the most commonly suggested "just use CRDTs" response.

**Operational Transformation** — even tree/XML variants define correctness purely
as structural convergence (TP1/TP2); schema validity never appears.

**Delta encoding** (VCDIFF, bsdiff, git packs, rsync) — byte-level. Vocabulary
only.

### 12.2 Transfers: constraint programming, and a tractability boundary that lands on us

Constrained decoding was invented twenty years early, in another field: the
**REGULAR constraint** (Pesant, CP 2004) and the **GRAMMAR constraint**
(Sellmann; Quimper & Walsh, 2006) constrain a sequence of variables to a formal
language, with filtering algorithms.

And that field also knows how to combine a grammar with counting — which is
exactly the residue [`04`](04-solution-approaches.md) identifies:

> **Beldiceanu et al., AAAI 2013 (arXiv:1309.7145):** combining a regular-language
> constraint with **at-most / at-least cardinality bounds is polynomial**;
> combining it with **exact-count bounds is NP-hard.**

That maps directly onto JSON Schema. `minItems`/`maxItems` are at-most/at-least
bounds — **tractable**. Exact cardinality is not. One of the two genuinely new
costs of fragment-wise generation therefore lands on the *good* side of a known
boundary.

**NEGATIVE RESULT:** no clean full-generality joint GAC algorithm for
GRAMMAR + ALLDIFFERENT was found (queries recorded in the raw report). So
`uniqueItems` remains the hard one, consistent with §11.1.

Two more borrowings, both design-shaping:

- **Freuder (JACM 1982), width and backtrack-free search** gives a *computable
  diagnostic* for when local consistency suffices for global consistency — a
  second, independent decision procedure alongside the O(|p|) keyword walk.
- **Assume-guarantee reasoning** (Pnueli 1984; Clarke, Long & McMillan 1989)
  gives the right *shape* for the fix, and it is a genuine improvement on our
  design: **PROJECT should derive an interface assumption, not merely a syntactic
  sub-schema.** The fragment is a component; what it must promise the rest of the
  document is its guarantee; what it may assume about the untouched remainder is
  its assumption. That is a better formulation of P2 than "descend through the
  schema".

### 12.3 Transfers: databases already run this pattern in production

**DEFERRABLE constraints and transaction abort/retry** are a decades-validated
instance of exactly GENERATE → SPLICE → REVALIDATE: violate a constraint
temporarily inside a transaction, check at commit, roll back on failure. The
database world also has concrete precedent for our residue — cyclic foreign keys,
swapping two unique values, out-of-order ingestion — all cases where the
intermediate state is invalid and only the committed state must not be.

**Constraint simplification theory** (Nicolas 1982; Christiansen & Martinenghi
2006) reaches the *same* tractability boundary as the CP literature from a
completely different direction — query-containment decidability. Two independent
formal routes converging on one line is worth noting.

**And it closes a gap I listed as open.** **Ross, Srivastava & Sudarshan (1996)**
encode integrity constraints as materialised views required to be empty, so
ordinary incremental view maintenance machinery maintains the *validity check*
incrementally. That is a known technique for the "no incremental JSON Schema
validation exists" gap — the algorithm exists, it has simply never been pointed
at JSON Schema.

### 12.4 Transfers, but only to evaluation

**Tree edit distance** (Zhang–Shasha 1989; APTED, O(n³) time / O(n²) space) is
the natural metric for "did the system change only what it should have" — but
plain TED penalises key-order differences that are semantically irrelevant in
JSON. Two very recent papers independently confirm the fix is a JSON-aware
semantic layer: **STED** (arXiv:2512.23712) and **GTED** (arXiv:2507.07399).
Note that practical JSON diff tools — jsondiffpatch, json-delta, deepdiff — do
**not** compute minimum tree edit distance; they are LCS-based heuristics. "The
diff my tool printed" and "the minimum edit" are different things.

---

## 13. What is genuinely unknown

The theory questions have closed. What remains is empirical, and one gap is
structural.

1. **The large-`N`, low-ρ regime — the headline gap.** Every measurement is at
   ρ ≈ 0.3–0.5 on documents under 10K tokens. The user's cases are ρ ≈ 0.006 and
   300K-token targets. **Nobody has measured the regime that motivates the work.**
2. **The JSON Schema instance of the compositional class.** The class is known
   under three names; nobody has instantiated it for JSON Schema or written the
   O(|p|) decision procedure.
3. **No incremental JSON Schema validation exists.** NEGATIVE RESULT, searched.
   Nor streaming JSON Schema validation, nor static schema-preservation checking
   for JSON Patch. The XML equivalents all exist. JSON simply has not been done.
4. **Cross-call state.** No constrained decoder carries state between generation
   calls. But this is an **unbuilt feature, not a research problem**: uniqueness
   against a known finite set is regular, and a 100,000-string trie compiles in
   67 ms.
5. **Localisation accuracy.** AdaEdit's >90% is the nearest proxy, for a coarser
   decision than ours.
6. **Speculative decoding under a grammar.** Never measured, and every "3–5× for
   structured output" claim silently assumes it.

**The one cheap experiment that would settle most of this:** regenerate a
10–20K-token Pydantic object with one leaf changed, and diff every field that was
supposed to be untouched, across turns. It appears never to have been run for
schema-constrained output.

**The one cheap experiment that would settle most of this:** regenerate a
10–20K-token Pydantic object with one leaf changed, and diff every field that was
supposed to be untouched, across turns. It appears never to have been run for
schema-constrained output.

---

*Next: [`04-solution-approaches.md`](04-solution-approaches.md) — the verdict and
what to build.*
