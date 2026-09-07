# F: Long Output Chunking — Ceiling and Decay on Long Structured Output

Research agent F. Covers: hard output token limits across major model providers,
quality decay with output length, long structured generation benchmarks,
chunked/batched generation practice, cross-chunk consistency, constraint-aware
bulk data generation (DB literature), and whether chunking helps or hurts.

STATUS: IN PROGRESS — writing incrementally as sources are found.

---

## 1. Hard output token limits (current, dated)

### Anthropic Claude — PRIMARY (platform.claude.com/docs/en/models/overview, fetched 2026-09-07)

Current lineup ("Max output" = Messages API `max_tokens` synchronous limit):

| Model | Context window | Max output (sync Messages API) | Reliable knowledge cutoff |
|---|---|---|---|
| Claude Fable 5.1 | 1M tokens | 128K tokens | Jun 2026 |
| Claude Opus 5 | 1M tokens | 128K tokens | May 2026 |
| Claude Sonnet 5 | 1M tokens | 128K tokens | Jan 2026 |
| Claude Haiku 4.5 | 200K tokens | 64K tokens | Feb 2025 |

Critical extra fact (PRIMARY, same page, footnote on "Max output" row): **On the Message
Batches API, Claude Opus 5, Claude Sonnet 5, Claude Opus 4.8, Claude Opus 4.7, Claude Opus
4.6, and Claude Sonnet 4.6 support up to 300K output tokens** with the
`output-300k-2026-03-24` beta header. So the practical ceiling for a single Claude
generation today, if you're willing to use async batch + a beta header, is **300K output
tokens**, not 128K. Sync/interactive calls are capped at 128K (64K for Haiku 4.5).

Also PRIMARY (same fetch, from search snippet of platform.claude.com/docs/en/build-with-claude/handling-stop-reasons
and the models-overview footnotes): thinking tokens count toward `max_tokens` — it's a
hard limit on total output (thinking + visible response text) for models with
adaptive/extended thinking on. So for a reasoning-heavy model, the *usable* budget for
actual structured-output content is `max_tokens` minus however much the model spends
thinking, which is variable and not fully controllable by the caller for adaptive-thinking
models (effort is a steering knob, not a hard budget split).

Historical trend (secondhand recollection cross-checked against known Anthropic release
notes, not re-verified against archived docs in this session — flagged as lower
confidence): Claude 3.5 Sonnet (2024) shipped with a 4096-token default / 8192-token max
output. Claude 3.7 Sonnet (Feb 2025) raised standard max output to 64K tokens, with a
128K-output beta. The ceiling has moved up roughly 16-30x in about two years. This
trajectory itself is the point for the delta project: whatever number we cite has a shelf
life of months, not years.

### OpenAI GPT family — PRIMARY (developers.openai.com/api/docs/models, fetched 2026-09-07)

Current lineup as shown on the primary docs page today:

| Model | Context window | Max output tokens |
|---|---|---|
| GPT-5.6 Sol (`gpt-5.6-sol`) | 1.05M tokens | 128K tokens |
| GPT-5.6 Terra (`gpt-5.6-terra`) | 1.05M tokens | 128K tokens |
| GPT-5.6 Luna (`gpt-5.6-luna`) | 1.05M tokens | 128K tokens |
| GPT-6 Astra (`gpt-6-astra`, flagship) | 1.05M tokens | 128K tokens |

All current OpenAI models cap at **128K output tokens** — same number across the whole
current lineup, and the same number Anthropic uses for sync output. Earlier in this
session (before pinning the primary source above) a secondhand community-forum synthesis
described GPT-5 (the non-.6 model, now presumably superseded/renamed in the docs UI) as
128K output tokens within a 400K total context (272K max input + 128K max output) — that
number is **not from a primary doc fetch** in this session, flagged secondhand, but it is
consistent with the 128K output figure holding across GPT-5 → GPT-5.6 → GPT-6.

### Google Gemini — PRIMARY (ai.google.dev/gemini-api/docs/models/*, fetched 2026-09-07)

| Model | Input token limit | Output token limit | Status |
|---|---|---|---|
| Gemini 3 Pro Preview | 1,048,576 | 65,536 | **Deprecated, shut down March 9, 2026** |
| Gemini 3.1 Pro Preview | 1,048,576 | 65,536 | Current (last doc update Feb 2026) |

The Gemini 3 developer guide (ai.google.dev/gemini-api/docs/gemini-3) states plainly:
"Gemini 3 models support a 1 million token input context window and up to 64k tokens of
output." So Gemini's output ceiling (**~64K tokens, 65,536 exactly**) is roughly half of
Claude's and OpenAI's 128K sync ceiling.

Open question flagged by a community forum thread found in search (Google AI Developers
Forum, "Gemini 3.8 Flash HIGH: does maxOutputTokens include thinking tokens?" —
**secondhand, forum post, not verified against primary docs in this session**): whether
thinking/reasoning tokens count against `maxOutputTokens` for Gemini 3.x the way they do
for Claude's adaptive thinking. Not confirmed either way from a primary source this
session; flagged as an open point, same shape as the confirmed Claude behavior above.

### Leading open-weight models — mixed primary/secondhand, fetched 2026-09-07

| Model | Context window | Max output tokens | Source confidence |
|---|---|---|---|
| DeepSeek V4 Pro / V4 Flash | 1M tokens (shared input+output envelope) | **384K tokens** | PRIMARY (api-docs.deepseek.com/quick_start/pricing) |
| Qwen3.8-Max (0902) | 1,000,000 tokens | 131,072 completion tokens (+262K max reasoning budget, separate) | Secondhand (OpenRouter listing via search snippet, not independently fetched) |
| Qwen3 Max (original) | 262,144 tokens | 65,536 tokens | Secondhand (OpenRouter listing via search snippet) |
| Kimi K2.6 (Moonshot AI) | 262,144 tokens | 262,144 tokens | Fetched from OpenRouter model page (aggregator, not Moonshot's own docs — semi-primary) |
| Llama 4 (Meta, Apr 2025 / re-released Aug 2026 open weights) | 10M tokens (input-focused figure) | Not found — no source in this session gave a distinct max-output number | Negative result, see below |
| Llama 5 (Meta, claimed Apr 2026) | 5M tokens (per one secondhand blog) | Not found | Low confidence — see caveat below |

Caveat on Llama 5: found only via general web search, sources were SEO/aggregator blogs
(RAGyfied, TokenCalculator.com, andrew.ooo, explainx.ai, NeuralStack) with no
corroboration from ai.meta.com or llama.com fetched directly in this session, and the
reported dates/specs were inconsistent across the blogs (one says Llama 4 "open weights"
released Aug 2026, more than a year after Llama 4 originally shipped, which is suspicious
phrasing — possibly conflating multiple release events). **Treat "Llama 5 / 600B / 5M
context" as unverified** until checked against ai.meta.com or llama.com directly. Did not
spend further budget chasing this since it's a minor sub-point of item 1.

**Takeaway for item 1 (output ceiling):** the frontier sync-API output ceiling clusters at
**~64K–128K tokens** for the big proprietary labs (Gemini ~64K, Claude/OpenAI 128K), with
Claude reaching 300K on async batch with a beta header. Some open-weight / non-US-lab
models advertise much higher output ceilings — DeepSeek V4 at 384K tokens (PRIMARY,
verified) is the largest confirmed number found this session, more than double Claude's
batch ceiling and 3x its sync ceiling. This matters directly for the bulk-table case: **no
mainstream model can emit an unbounded structured artifact in one call**, but the wall is
higher and more provider-dependent than a single round number — anywhere from 64K
(Gemini sync) to 384K (DeepSeek) tokens, and that's before accounting for how many of
those tokens get consumed by JSON syntax/field-name overhead vs actual row content, or by
thinking tokens on reasoning-enabled models (confirmed to count against the same budget
for Claude; unconfirmed but plausible for Gemini 3.x, see forum thread flagged above).

## 2. Quality decay with output length

### LongWriter (Bai et al., ICLR 2025) — PRIMARY (arxiv.org/abs/2408.07055, fetched 2026-09-07)

Full abstract quote: "Current long context large language models (LLMs) can process
inputs up to 100,000 tokens, yet struggle to generate outputs exceeding even a modest
length of 2,000 words. Through controlled experiments, we find that the model's effective
generation length is inherently bounded by the sample it has seen during supervised
fine-tuning (SFT)... their output limitation is due to the scarcity of long-output
examples in existing SFT datasets."

Key point for the delta project: **the output ceiling before LongWriter-style
interventions was not a hard architectural/context-window limit — it was a training-data
artifact.** Models see almost no >2000-word single-turn completions in SFT data, so they
learn to stop around there regardless of how much context window is technically available.
Their fix, AgentWrite, is itself a chunking method: it "decomposes ultra-long generation
tasks into subtasks, enabling off-the-shelf LLMs to generate coherent outputs exceeding
20,000 words" — i.e., **the state-of-the-art way to get long coherent output out of an
LLM is already agentic decomposition into subtasks**, which is directly relevant to our
bulk-table chunking question. They built LongWriter-6k (6,000 SFT examples, 2k-32k words)
and retrained models on it to push native single-shot output past 10,000 words "while
maintaining output quality" (abstract asserts this but the fetched excerpt gave no
quantitative degradation curve backing that specific claim — would need the full paper
body/tables for that, not just the abstract).

Their benchmark, LongBench-Write, evaluates ultra-long generation; LongWrite-Ruler is a
lightweight stress test purely of max output length attainable.

### LongGenBench (Wu et al.) — PRIMARY (arxiv.org/html/2409.02076v7, fetched 2026-09-07)

This is a direct, quantitative benchmark of quality decay vs. output length. Key numbers,
all from the fetched paper text:

- **Performance cliff located concretely**: "strong adherence to initial instructions at
  shorter sequence lengths, but performance gradually degraded as the text generation
  extended beyond the **4,000-token threshold**."
- **At 16K output tokens**: best model (GPT-4o-mini) hit 97% task *completion* but only
  **27.9% instruction adherence** (their STIC-2 metric) — i.e. the model finishes the
  response but stops correctly following the constraints partway through. Completion and
  correctness are decoupled: length compliance is not accuracy.
- **At 32K output tokens**: total collapse — "no model successfully completed 32K
  evaluations, with completions ranging from 7.4% to 66.2%."
- **~45% of long outputs showed significant repetition**, even under varied prompts —
  quantifies the "repetition loop" failure mode the task description asked about.
- Failure modes catalogued: premature termination, repetitive content, instruction drift
  ("models correctly described initial floors but deviated from the original plan as the
  task progressed" — a spatial-planning task, but directly analogous to schema drift over
  a long row-by-row table), and a difficulty hierarchy where periodic/structural
  instructions ("every Nth row do X") are hardest, followed by ranged, then single
  instructions.
- Models tested: GPT-4o, GPT-4o-mini (closed); Llama3.1-8B/70B, Qwen2-7B/72B,
  Mistral-v0.2-7B, Mixtral-8x7B, FILM-7B, LongWriter-llama3.1-8B (open). Note this is a
  2024-era model roster (pre-dates the 2026 frontier models covered in section 1), so
  absolute numbers are dated, but the *shape* of the decay curve (cliff around 4K tokens,
  collapse by 32K) is the reusable finding.
- Also notable: Pearson correlation between a model's long-*input* handling ability and
  its long-*output* generation ability was only **0.51 at 16K and 0.66 at 32K** — being
  good at long-context reading does NOT predict being good at long-form writing. This is
  an important caution against assuming "the model has a 1M context window, so a 10K-row
  table is fine" — input capacity and output capacity are empirically different skills.

### On Stable Long-Form Generation: Benchmarking and Mitigating Length Volatility (2026) — PRIMARY (arxiv.org/html/2605.01357v1, fetched 2026-09-07)

**This is probably the single most relevant paper found for the bulk-table case.** ArXiv
ID 2605.01357 → submitted ~May 2026, i.e. very recent. Introduces VOLTBench, a
multi-section generation benchmark (chapters, diary entries, dialogue rounds, code
functions — "chapter-based design is the key to our scalability, enabling us to create
instructions that range from a concise 5-chapter document to an expansive 500-chapter
tome"). A "section" is a discrete structured unit with its own minimum content
requirement, similar in shape to a row in a bulk table.

**Metric = "Structured Content Accuracy" (SCA)**, defined exactly as:
`SCA = Number of Correct Chapters / Number of Required Chapters`
— evaluated by execution-based verification (JSON must parse, code must run). **This is
precisely the "per-row accuracy against row count" metric the assignment asked us to look
for**, just applied to chapters/sections instead of table rows. Companion metric UCA
(Unstructured Content Accuracy) uses LLM-as-judge for prose tasks.

**Quantitative decay curve (direct quotes):**
- "While most models...adhere to constraints on shorter tasks (5-50 sections), their
  performance plummets and grows more volatile as the context length increases."
- "When tasked with generating up to 50 sections, models failed in approximately half of
  the cases. For requests exceeding 50 sections, all models failed."
- At the 500-section scale: "Against a requirement of 100 constrained sections, no model
  delivered more than 40" (wording as published — read as: even restricting attention to
  just the first 100 of a 500-section ask, no model produced more than 40 correct
  sections).
- Per-model volatility numbers at the **100-section** task (their Table 2, "length
  volatility" = run-to-run variance in output length, LVC = Length Variation Coefficient):
  - GPT-4o-mini: LSD 325.65 (~32.9% relative volatility)
  - Claude-3.5-Sonnet: extremely brief outputs, 176 words average (i.e. the model
    essentially refuses/truncates the long multi-section task rather than attempting it
    and failing partway)
  - DeepSeek-R1: LVC 8.6%, highest UCA at 93.3% (best-behaved model in their test)
  - LongWriter-8B (a model specifically trained for long output, see LongWriter paper
    above): LVC 45.4%, lowest UCA at 66.7% — notable that the model *trained* for long
    output was the LEAST stable on this structured multi-section task, suggesting
    training for raw length and training for per-section structural fidelity are
    different objectives that can trade off against each other.
  - For Qwen2.5-7B specifically: LVC jumped from 2.2% (short outputs) to **17.0% (100
    sections)** — an ~8x increase in relative volatility purely from asking for more
    sections at the same per-section content spec.

**Root-cause mechanism (attention analysis, direct quotes) — this is the best "why"
evidence found for the whole decay literature:**
- "After that, attention collapses to near-zero, signaling loss of focus on prompt
  constraints and resulting in halted or irrelevant output." (attention collapse)
- Abnormal attention spikes occur "immediately preceding the model's deviation from
  sequential output" (attention instability precedes failure)
- Synthesis: "Stable long generation depends on preserving reliable attention anchors,
  while losing attention to structural or constraint tokens often precedes termination,
  repetition, or section skipping."

This gives a mechanistic account of the failure modes asked about in the assignment:
truncation = attention collapse -> halted output; repetition/section skipping = loss of
the attention anchor tracking "which section am I on."

**Mitigation tested — GLoBo (Stable Generation via Logits Boosting):** on LongWriter-8B at
100 sections:
- Mean output length improved **148%**
- Length volatility (LVC) reduced **69%**, from 45.4% -> 14.02%
- Mean Length Accuracy improved **148%**, from 31.6% -> 78.25%
- **Structured Content Accuracy: 100% vs. LongWriter-8B's baseline 32.6%** (their
  strongest single number — a 3x improvement in per-section correctness from a
  decoding-time intervention, no retraining)
- Cost: modest throughput hit, 20.4 -> 18.2 tokens/second

Caveat: GLoBo is a logits-boosting decode-time technique specific to open-weight models
where you control the sampler; it is very unlikely to be applicable to closed frontier
APIs (Claude/GPT/Gemini) where you don't get logit-level control. Relevant as evidence
that decay is mitigable in principle, not as a technique we could adopt directly for an
API-based delta/bulk system.

### HelloBench (Que et al., 2409.16191, Sept 2024) — secondhand (via search synthesis, not independently fetched full text this session)

Evaluated ~30 mainstream LLMs across five task categories (open-ended QA, summarization,
chat, text completion, heuristic text generation, per Bloom's Taxonomy). Finding, as
reported: "even advanced models face severe repetition" on diverse in-the-wild long-text
scenarios, and current LLMs broadly "lack long text generation capabilities." Proposes
HelloEval, a hierarchical human-aligned auto-eval method to make evaluating long outputs
cheaper than pure human eval while staying correlated with it. No specific
degradation-vs-length numbers were retrieved in this session — flagged as a gap, would
need a direct fetch of the paper body to get quantitative tables.

### Lost-in-the-Middle in Long-Text *Generation* (2503.06868, ~March 2025) — PRIMARY abstract only (arxiv.org/abs/2503.06868, fetched 2026-09-07); full PDF fetch failed (binary/garbled)

This is the direct output-side analogue of Liu et al.'s input-side "lost in the middle"
that the assignment asked us to check for — **confirmed to exist as a named, studied
phenomenon**, not just an input-side effect. The paper:
- Introduces "LongInOutBench," a synthetic dataset + evaluation framework specifically
  for measuring lost-in-the-middle in generated (not just retrieved) long text.
- Proposes "RAL-Writer," a mitigation that "retrieves and restates important yet
  overlooked content, mitigating the 'lost-in-the-middle' issue by constructing explicit
  prompts" — i.e., periodically re-injecting a summary of earlier output back into context
  during generation, structurally similar to the "passing prior output back as context"
  technique the assignment asks about for item 4/5.
- Abstract confirms effectiveness ("results demonstrate the effectiveness of our
  approach") but does NOT give the magnitude — full PDF was unreadable as fetched
  (binary/garbled content, saved locally but not parseable via WebFetch). **Flagged as an
  incomplete extraction** — the paper clearly exists and is on-topic, but exact numbers
  were not obtained this session. If this gap matters for the final writeup, it's worth a
  second attempt with a different fetch method (e.g. ar5iv.org HTML mirror) rather than
  the raw arxiv PDF.

Additional detail from second fetch (ar5iv HTML mirror, arxiv 2503.06868, fetched
2026-09-07): Figure 7(b) shows LongInOutBench has "a significantly reduced decline in
accuracy when responding to questions related to the 2nd (the middle position) paper"
compared to baselines (AgentWrite, Compress, single-model invocation) — confirms
middle-position decay is measured and mitigated, but **no exact percentage-point drop
values were recoverable** from this fetch. Table 2 numbers (Qwen2.5-14B, 8k-word target,
consistency/quality scores 0-100 scale): AgentWrite baseline 55.66 consistency / 74.51
quality vs RAL-Writer 58.23 consistency / 75.93 quality — real but modest improvements
(+2.57 and +1.42 points respectively), which itself is a useful data point: **mitigating
output-side lost-in-the-middle is hard; the fix that exists moves the needle by a few
points, not by closing the gap.**

## 3. Long structured generation benchmarks (text-to-table, JSON extraction, bulk records)

### LLMStructBench (2602.14743, Feb 2026) — PRIMARY (arxiv.org/html/2602.14743v1, fetched 2026-09-07)

995 manually verified samples, 5 use cases (support tickets, sick leave, project
extension, conference registration, loan requests), JSON schemas ranging 5-10 keys,
depth 2-4, with nested arrays in the hardest case. **Does NOT test scaling to many
records/rows** — it's single-document, single-object extraction, so it's evidence about
schema *complexity* (depth, nesting) rather than schema *volume* (row count). Marking
this a partial miss for item 3's specific ask (per-row accuracy vs row count) but useful
supporting data:

- Best models (Gemma3-27B, GPT-4o) hit F1_micro 0.96 but DOC_micro (whole-document exact
  match, i.e. the entire structured object being fully correct) only **0.52** — a huge
  field-level-vs-object-level gap. **Getting every field right is much harder than getting
  most fields right**, even at just 5-10 keys. This is a warning sign for bulk generation:
  if whole-object correctness is ~50% at one small object, whole-*table* correctness
  (every row correct) at thousands of rows implied by naive multiplication would be
  effectively zero — which is exactly the argument for per-row/per-chunk validation
  rather than trusting a full-document generation to be globally correct.
- Error-type breakdown by model scale (DeepSeek-R1 family): small models (1.5B) show
  36.8% Missing Keys / 18.9% Missing Values / 76.7% Wrong Values; at 7B+ "Missing Keys
  nearly eliminated... Wrong Values dominate at 91.5-98.3%". Their conclusion: "key
  omissions vanish once the model reaches mid-scale, but incorrect or absent values
  persist" — i.e. once a model is competent, the dominant failure mode shifts from
  *structural* errors (schema violations, which constrained decoding fixes) to *semantic*
  errors (wrong values, which constrained decoding CANNOT fix). Important for the whole
  delta project: constrained decoding solves the schema-validity problem, not the
  correctness problem, at any scale.
- "Choosing the right prompting strategy is more important than standard attributes such
  as model size" — prompting strategy (they compare P, PJ+, etc.) beat raw model size in
  their experiments (11 vs 8 wins across strategies).

### AOE / "Beyond Isolated Dots" (2507.16271, Jul 2025) — PRIMARY abstract only, full text unreadable (PDF binary) this session

Abstract (direct quote): introduces the "Arranged and Organized Extraction Benchmark
(AOE)," bilingual, "data and documents of varying lengths," 11 tasks across 3 domains,
requires the model to invent context-specific schema (not fixed-schema extraction).
Direct quote: **"even the most advanced models struggled significantly."** Could not
recover the Cell-F1-vs-table-size breakdown that the secondhand search snippet claimed
existed ("Cell F1 scores remaining critically low across various models and domains") —
full PDF fetch failed both as raw PDF and was not retried via ar5iv in this session.
Flagged as a gap; the paper is clearly on-topic (LLMs building tables from unstructured
input) but this session could not pull its quantitative size-scaling table.

### Multi-Faceted Evaluation of LLM-Generated Synthetic Data (2404.14445) — PRIMARY (arxiv.org/pdf/2404.14445, fetched 2026-09-07)

### SynEval (2404.14445) — abstract only, numeric claims from the earlier secondhand search snippet NOT verified against primary text this session

PRIMARY abstract confirms scope: SynEval evaluates fidelity/utility/privacy of LLM-generated
synthetic tabular data (product reviews), tested on ChatGPT, Claude, Llama. The specific
numbers reported by web-search synthesis earlier ("coverage degrades monotonically with
network size: 20.3% at 12 nodes... 6.2% at 60 nodes, a 69% relative decline") **could not
be re-confirmed from the paper itself** (PDF fetch returned binary garbage twice) — that
number may belong to a different paper conflated in the search engine's summary. **Treat
the "20.3% -> 6.2%" figure as unverified/possibly misattributed and do not cite it without
independently re-locating its source.** Flagging explicitly per the negative-results
instruction.

## 5/6 bridge: constrained decoding's own literature already names the cross-chunk uniqueness problem

### JSON Schema blog / dottxt case study — PRIMARY (json-schema.org/blog/posts/dottxt-case-study, fetched 2026-09-07)

This is a direct, primary-source acknowledgment from the constrained-decoding tooling
world (dottxt / Outlines maintainers, a leading structured-generation-constraint library)
that **`uniqueItems` is a known-hard case for schema-constrained decoding**, and the exact
reason given is structurally the same reason cross-batch uniqueness is hard:

Direct quote: **"`uniqueItems` in arrays: Ensuring array elements are unique requires
remembering all previously generated elements, a context that can grow arbitrarily
large."**

This confirms, from the constraint-enforcement side (not just empirically from LLM
behavior), that **enforcing global uniqueness is fundamentally a growing-state problem**,
not a per-token grammar problem — you cannot compile `uniqueItems` into a finite-state
token filter the way you can compile "this token must be a digit" or "this key must be
one of these five strings." The filter needs to consult an ever-growing exclusion set.
This is exactly the same shape of problem as cross-chunk uniqueness in the bulk-table
case: whether the "already emitted" set lives inside one generation's KV cache or is
carried explicitly between independent chunk calls, **something has to hold and consult
a growing blocklist**, and today's schema-constrained-decoding tooling treats this as an
open/hard case even *within a single generation*, let alone across independently-launched
chunk calls that don't share decoder state at all.

Other context-sensitive JSON Schema features flagged as hard by the same source, useful
as a checklist of "things that break when you naively constrain-decode a big structured
document": **dependencies between sibling properties** (validity of one field depends on
another field's value/presence), **conditional schema (`if`/`then`/`else`)** where "the
schema rules that apply can change based on data already generated, requiring dynamic
schema selection," and dependent requirements. All of these get *harder*, not easier, at
bulk-table scale, because a bulk table often has cross-row conditional logic (e.g. "row
type determines which other columns are required") layered on top of the cross-row
uniqueness problem.

Baseline reliability number from the same source: **"Ask [LLMs] for JSON, and you might
get valid JSON 95% of the time"** unconstrained, and "up to 50% of the time spent
integrating LLMs" goes to handling output-formatting problems — this is the unconstrained
baseline that constrained decoding fixes for *syntactic* validity; it says nothing about
semantic/value correctness (consistent with the LLMStructBench finding above that once
structural errors are fixed, wrong-value errors dominate).

### Synthesizing Linked Data Under Cardinality/Integrity Constraints (2103.14435) — found but NOT verified this session (PDF unreadable both attempts)

On-topic by title (classic DB-style constraint synthesis, predates the LLM era, exactly
the kind of "borrow their clean technique" work item 6 asks for) but this session could
not extract its content — two fetch attempts both returned binary/garbled PDF stream data
with no readable text. Recorded here as a citation to chase later, not as a verified
finding. Do not cite its content without another extraction attempt (e.g. via
semanticscholar.org or an HTML mirror).

## 6. Constraint-aware bulk data generation outside LLMs (classic DB literature)

Secondhand (search-engine synthesis, not yet independently fetched/verified this
session — flagged) but consistent across multiple independent hits, so treat as
moderately reliable pending a primary fetch:

- **PDGF (Parallel Data Generation Framework)**, from University of Passau (Prof. Harald
  Kosch's group), is the standard reference tool for generating large relational
  benchmark datasets (used in TPC benchmarks, extended for BigBench's clickstream and
  TextGen unstructured-text generators). Key architectural fact: it's explicitly built to
  **parallelize across multi-core/cluster hardware**, which means the field already had to
  solve "how do you generate a huge constraint-satisfying dataset using many independent
  parallel workers" for relational data, decades before LLMs. One search snippet
  explicitly notes "PDGF addresses key requirements but **cannot yet handle all data
  dependencies**" — i.e. even the classic parallel DB generator has known limits on
  cross-partition dependency enforcement, which is a useful "even the non-LLM version of
  this problem has an unsolved residual" data point.
- Related classic-DB-literature titles surfaced (not yet fetched, listed for the record):
  "Efficient update data generation for DBMS benchmarks" (ACM/SPEC ICPE 2012),
  "A Data Generator for Cloud-Scale Benchmarking," "BDGS: A Scalable Big Data Generator
  Suite." Common thread across all: **partition-then-generate-then-merge, with explicit
  bookkeeping (typically hash-partitioning keys or reserving disjoint ID ranges per
  worker) to guarantee cross-partition uniqueness without needing workers to communicate.**
  This is the standard technique: don't detect-and-fix duplicates after the fact, avoid
  the possibility of collision by construction — e.g. give worker `i` of `N` the id range
  `[i * (total/N), (i+1) * (total/N))` up front, so no two workers can ever emit the same
  key regardless of what values they choose internally. **This is a clean, directly
  reusable technique for the delta/bulk LLM case**: if row IDs or any uniqueItems-style
  key is needed, pre-partition the id space across chunk calls deterministically (chunk k
  owns ids [k*B, (k+1)*B)) instead of asking the LLM to invent globally-unique values and
  hoping, or post-hoc deduplicating. The LLM never needs to "know" what other chunks
  produced for THIS specific constraint, because the constraint is enforced by the
  harness, not by the model.
- Not yet retrieved/verified this session: "Synthesizing Linked Data Under Cardinality and
  Integrity Constraints" (2103.14435, PDF unreadable, see above), Berkeley "Query Aware
  Synthetic Data Generation" tech report, Lauca (1912.07172), SynSQL (2604.27261),
  QAgrow "Constraint-based Test Database Generation for SQL Queries" (2010). All found by
  title/relevance via search, none independently content-verified this session due to
  time budget — listed here as a citation trail for a follow-up pass if the synthesis
  agent needs deeper DB-literature grounding.

## 4/7 practice: batch size N, and does chunking help or hurt

### Self-Instruct / Alpaca — semi-primary (search synthesis of a well-known, previously-known paper; ROUGE-L threshold is a widely-cited number I can corroborate from prior knowledge, not re-fetched from the PDF this session)

The canonical historical precedent for "generate many items, watch for duplicates": Alpaca
generated 52K instruction-following examples via Self-Instruct starting from 175 seed
tasks. Their duplicate-control technique was **not** structural (no global uniqueness
constraint, no reserved-ID-range trick) — it was *post-hoc similarity filtering*: "if the
ROUGE-L similarity between a new instruction and existing instructions exceeds 0.7, the
new instruction is discarded," plus discarding instances "that are identical or have the
same input but different outputs." This is the **soft/statistical dedup approach**,
contrasted with the DB literature's **hard/structural** partition approach above. It's
notable that the field's most famous LLM bulk-generation pipeline used the weaker,
similarity-threshold technique rather than a constructive guarantee — presumably because
natural-language instructions don't have a clean primary key to partition on the way
table rows with an id column do. This is a relevant fork for the delta/bulk project:
**structural techniques (ID partitioning) work when the uniqueness key is a manufactured
field (row id, primary key); similarity-threshold techniques are the fallback when
uniqueness is semantic (no two rows should describe the same real-world entity) and can't
be enforced by construction.**

### Prompt caching offsetting chunking's input-token multiplication — cross-checked against PRIMARY Anthropic pricing data already fetched in section 1

The assignment specifically asks whether prompt caching offsets the cost penalty of
re-sending shared context on every chunk call. From the PRIMARY platform.claude.com
models-overview fetch (section 1 above): **"prompt cache reads cost 10% of the base input
price"** (2.5% for Fable 5.1) and **"Batch API requests are 50% off."** A secondhand
aggregator (multiple consistent blog hits, not independently verified against OpenAI's or
Anthropic's own pricing-mechanics docs beyond the base numbers above) states these
compound: batch (50% off) + cache read (90% off the already-discounted batch price, i.e.
paying 10% of base) multiply to roughly **95% total savings on the repeated/cached
portion of the prompt** when both discounts apply together. OpenAI's cache discount is
reported (secondhand) as a flat 50% off cached-prefix tokens, smaller than Anthropic's 90%
— and OpenAI's caching is automatic (static content just needs to be at the top of the
prompt) vs Anthropic's explicit `cache_control` markers.

**What this means concretely for chunked bulk generation**: if a bulk-table job re-sends
the same schema + system prompt + few-shot examples on every one of, say, 1,000 chunk
calls, and that shared prefix is, say, 80% of each call's input tokens, then with caching
the *effective* input-token cost of that repeated prefix drops to roughly 10% (Anthropic
non-batch) or 5% (Anthropic batch+cache) of its face value from the second call onward.
This substantially blunts (but does not eliminate — cache reads are not free, and the
first call in any cache lineage still pays full price, and caches expire/have TTLs) the
"chunking multiplies input tokens" cost concern the assignment raised. **No source found
this session gives a head-to-head total-cost-in-dollars comparison of "1 call of 10,000
rows" vs "1,000 calls of 10 rows with caching" for a real workload** — this specific
comparison, which is exactly what the delta project needs, appears to be an open
gap in the literature, not an already-answered question. Flagged as a negative result.

