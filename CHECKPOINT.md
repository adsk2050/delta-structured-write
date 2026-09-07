# CHECKPOINT — delta-structured-write

Last updated: 2026-09-07, after research fan-out (7 agents running).

## The question
When a schema-governed structured output must be produced repeatedly with small
changes, or is too large to emit at once, can the system generate only the
relevant *fragment* — under ordinary constrained decoding against that
fragment's own schema — and splice it back with a guarantee that the whole
document still satisfies the schema? Solved / not worth solving / open?

## Scope — decided with the user, do not relitigate
- **In scope:** any schema-governed structured output produced repeatedly or in
  pieces. Two anchor cases: **edit regime** (a Pydantic form; user says "change
  the answer to Q3"; regenerate only that response) and **construction regime**
  (a 10,000-row spreadsheet emitted 10 rows at a time).
- **Out of scope:** code/prose editing (no schema); agent memory/state (user:
  "memory problem is already solved"); unstructured output.
- **Deliverable:** research answer only. **No prototype, no code.**
- **AS** in the original note = the full structured output object.

## The reframing that happened mid-session — important
The problem is NOT "make the model write a JSON Patch". The model should never
have to write a pointer or a diff. The architecture is:
**LOCALISE** a region → **PROJECT** the sub-schema there → **GENERATE** the
fragment under ordinary constrained decoding → **SPLICE** → revalidate.
Patch-as-a-language is a fallback design, not the main one.

## Established facts (do not re-derive)
- Constrained decoding guarantees prefix-validity against a grammar, nothing more.
- `L(G_S) ≠ ⟦S⟧` in practice: engines over-approximate value constraints
  (uniqueItems, cardinality) and under-approximate key order. So fragment-wise
  generation inherits an unsoundness that already exists; it does not create it.
- **The reduction:** the whole problem collapses to computing or soundly
  approximating the *residual* `S/(D,p) = { v : D[p:=v] ⊨ S }` and compiling it
  to a decoding constraint. Splice soundness is then trivial by definition.
- **The Q1/Q2 gap:** membership in the residual is cheap (ordinary validation);
  prefix-feasibility is the hard one, and it is what a token mask needs.
  This is the formal reason "generate then validate" is attractive.
- **Untouched-region integrity** is 1 by construction under fragment generation
  and provably < 1 under full regeneration. This is a difference in kind, not
  degree, and no inference-speed technique closes it.
- `N > L_max` (max output tokens) makes the construction regime an
  impossibility, not an expense. Speculative decoding cannot help.
- Non-local keywords are the whole difficulty: `required`, minItems/maxItems,
  `uniqueItems`, dependentRequired/Schemas, if/then/else, oneOf/anyOf,
  additionalProperties, plus Pydantic `model_validator(mode="after")`.

## Done
- `notes/00-original-note.md` — verbatim transcription.
- `notes/01-problem-plain-english.md` — plain-English statement, revised around
  the form and spreadsheet examples.
- `notes/02-formulation.md` — academic formulation: residual schemas, the
  reduction, sound/complete lattice, streaming state for the construction
  regime, cost model, metrics, 6 hypotheses, 3 conjectures marked ⚠.

## Pending
- 7 research agents running; raw output under `research/raw/`.
- `notes/03-research.md` — merged literature answer, adjudicating Conjectures 1–3.
- `notes/04-solution-approaches.md` — final solution approach(es) + verdict.

## File ownership during fan-out (never write another agent's file)
| Agent | Model | Owns |
|---|---|---|
| constrained decoding foundations | opus | `research/raw/A-constrained-decoding.md` |
| patch formalisms + schema theory  | opus | `research/raw/B-patch-formalisms.md` |
| LLM edit/fragment empirics        | sonnet | `research/raw/C-llm-edit-empirics.md` |
| cheap regeneration (devil's advocate) | opus | `research/raw/D-cheap-regeneration.md` |
| frameworks + production practice  | sonnet | `research/raw/E-frameworks-practice.md` |
| long output limits + chunking     | sonnet | `research/raw/F-long-output-chunking.md` |
| adjacent formalisms               | sonnet | `research/raw/G-adjacent-formalisms.md` |

All were told to create their file before searching and append after every few
sources, so a killed agent still leaves usable work on disk.

## Resume
Read this file, then `notes/02-formulation.md`, then `ls research/raw/` and read
whatever landed. Continue from Pending.

---

## Research findings so far (2026-09-07, batch 1 partial) — DO NOT RE-DERIVE

### Direct prior work — the problem has been attempted
- **JSON Whisperer** (Duanis, Greenstein-Messica, Habba; Lightricks; EMNLP 2025
  Industry; arXiv:2510.04717). LLM emits RFC 6902 patch vs full regen.
  **31% token reduction, edit quality within 5% (slightly worse), latency
  -42.3% Claude Sonnet / -31.5% GPT-4o-mini.** Had to invent **EASE** encoding
  (arrays -> dicts with stable keys) because "LLMs struggle with array index
  arithmetic". Documented failure: models "miss necessary updates" across
  siblings. **Only ~400 small synthetic film-production docs — does NOT test
  the large-N regime the user cares about.** Patch mode roughly doubles/triples
  INPUT tokens while cutting output ~40-45%.
- **PatchOptic** (Bai & Cai, arXiv:2607.05483, Jul 2026). Essentially our
  architecture, framed as **optics/lenses**: projected read view, authorized
  write region, runtime verifier before commit. PatchBench, 46 cases, 5,520 live
  runs. **Semantic pass rate 0.609 -> 0.779 (+17pp) GPT-5-mini; +13pp Mistral-7B.
  Leak rate 0.315 -> 0.002. Tokens -12 to -16%. Quality flat.** Strongest
  evidence anywhere that projection *improves* correctness, not just preserves it.
  Peer-review status unconfirmed. New residue found: model can *infer* hidden
  field content from visible context (1 case / 5,520).

### The addressing-scheme result — decisive for design
**"To Diff or Not to Diff?"** (Cheng et al., arXiv:2604.27296, Apr 2026),
Qwen2.5-Coder-7B, avg pass@1 across 5 benchmarks:
| Addressing | pass@1 |
|---|---|
| FullCode (regen) | 57.07 |
| Line-number diff | **14.07-33.15 (collapse)** |
| Content/string-addressed | 54.43 |
| **Structure-aware (block/function unit)** | **55.98-57.95 (matches/beats regen)** |
Their diagnosis: "LLMs struggle to generate precise line numbers and offsets, and
this issue persists even when the input code is explicitly numbered."
**JSON Pointer into a schema-known document is structure-aware addressing**, the
category that works. Both frontier labs converged the same way: Anthropic
`str_replace` and OpenAI `apply_patch` V4A are content-anchored, never
line-numbered.

### The economics — settled
- **Output token = 50x a cached input token** (GPT-5.6 Sol, Opus 5, Sonnet 5,
  Haiku 4.5), 60-80x (GPT-5.5/5/Terra/Luna), **200x on Claude Fable 5.1**.
- **Speculative decoding ceiling is gamma+1** (Leviathan Thm 3.8 with c~0 as
  alpha->1). Real gamma is 5-10, so ~5-20x latency, best published EAGLE-3 6.5x.
  **Nothing published approaches N/k.**
- **Every speculative method reduces latency, none reduces billed output tokens.**
  OpenAI Predicted Outputs bills `rejected_prediction_tokens` at the OUTPUT rate —
  can cost *more* than full regen. Excludes `tools`, so unavailable for tool-call
  structured output. No GPT-5-family support as of 2026-09.
- Anthropic sells fast mode at 2.5x speed for 2x price: latency and cost are
  separate goods on a hosted API.

### The ceiling and decay — the construction regime
- Max output tokens: **128K** (Claude Fable 5.1/Opus 5/Sonnet 5, GPT-5.6 family,
  GPT-6 Astra), 64K Haiku 4.5, 65K Gemini 3.1 Pro, 384K DeepSeek V4.
- **LongGenBench**: adherence degrades beyond **4,000 output tokens**; at 16K
  output GPT-4o-mini has 97% completion but **27.9% instruction adherence**; at
  32K no model completes; **~45% of long outputs show significant repetition**.
- Long-INPUT ability does not predict long-OUTPUT ability (Pearson 0.51-0.66).
- **LongWriter** (ICLR 2025): the output ceiling is an SFT-data artifact, and
  their own fix (AgentWrite) *is* decomposition into subtasks.
- **VOLTBench** (arXiv:2605.01357): "Structured Content Accuracy" = correct
  sections / required sections — exactly the per-row metric we wanted. Models
  fail ~half of tasks at 50 sections.

### Conjecture 3 — confirmed from the tooling side
JSON Schema blog / dottxt case study, PRIMARY: **"`uniqueItems` in arrays:
Ensuring array elements are unique requires remembering all previously generated
elements, a context that can grow arbitrarily large."** Same source flags sibling
dependencies and if/then/else as hard. So unbounded state for value-equality
constraints is acknowledged by the constraint-enforcement community, not just
conjectured by us.

### The missing formalism — LENSES
PatchOptic's "optics" framing points at Foster/Greenwald/Moore/Pierce/Schmitt,
"Combinators for Bidirectional Tree Transformations" (POPL 2005 / TOPLAS 2007) —
typed lenses, get/put, well-behavedness laws — plus **edit lenses** (Hofmann,
Pierce, Wagner) and **delta lenses** (Diskin, Xiong, Czarnecki), and the ancestor
**view update problem** (Bancilhon & Spyratos 1981). Our PROJECT step is `get`,
our SPLICE is `put`. Agent B has been asked whether this subsumes Conjecture 2.

### Vendor/protocol layer — clean negative result
**No vendor or protocol supports semantic partial tool-call arguments.** MCP,
OpenAI, Anthropic, Gemini all require the complete argument object every call
(all VERIFIED primary). Streaming `input_json_delta` / argument deltas are
TRANSPORT deltas of a full generation — they save nothing. Prompt caching is
input-side only ("Prompt caching has no effect on output token generation").
No open feature request anywhere. OpenAI actively 400s partial tool replies.

### Failure-mode evidence
- **Aider laziness**: GPT-4 Turbo emitted lazy placeholders ("# ...add logic
  here...") on **12/89 tasks (13%)** under whole-block rewrite; unified diff cut
  it to **4/89 (4.5%)**. Direct measured evidence that regeneration corrupts, and
  that deltas fix it.
- **Displacement Rate** (arXiv:2608.25358, Aug 2026): fraction of values produced
  correctly but placed at the wrong structural position. At highest complexity:
  GPT-4o 24.2%, DeepSeek-V3 26.2%, DeepSeek-V4-Flash 35.4%, Qwen2.5-7B 73.8%.
  "Structural fidelity degrades earlier and faster than content accuracy."
- **Benchmark validity caveat** (arXiv:2604.05100): "59% of low-coverage suites
  [are] unable to detect modifications outside edit regions" — the code-editing
  literature systematically UNDER-measures silent corruption.
- **Coeditor** (ICLR 2024): fine-tuning on the edit distribution lifts exact-match
  34.7% -> 60.4%. Prompting != training for edit emission.

## Batch discipline (new rule, added to global CLAUDE.md)
Run 2-3 agents at a time, not 7. On 2026-09-07 all seven were killed by one
session limit; 281 KB survived only because of the write-as-you-go rule.
- Batch 1 (running): A constrained-decoding, B theory/lenses, D devil's advocate.
- Batch 2 (queued): E frameworks §2-5, G adjacent formalisms §1,2,4,5,6,7.
- C and F are largely complete; only minor verification action items remain.

## Batch 1 complete (A, D done; B still running) — additional established facts

### A's keyword audit — RESHAPES THE PROBLEM
VERIFIED from llguidance docs, outlines-core parsing.rs, vLLM backend_xgrammar.py,
llama.cpp grammars/README.md, + OpenAI/Azure/Anthropic/Gemini docs:
**uniqueItems, if/then/else, dependentRequired, dependentSchemas, not,
propertyNames, contains are enforced by ZERO engines in ZERO products** during
ordinary whole-document generation. `required` is enforced only by FIXING
PROPERTY ORDER to schema-declaration order (a departure from JSON Schema
semantics). => **The true new cost of fragment-wise generation is TWO things:
`required` across a boundary, and minItems/maxItems on a containing array.**
Both counting constraints, both cheap to carry.
- JSONSchemaBench (arXiv:2501.10868, Table 4): best coverage GitHub-Hard 41%,
  JSONSchemaStore 38%, Gemini 7% on GitHub-EASY. XGrammar had **38 categories of
  under-constrained failure**. vLLM ships a denylist because XGrammar silently
  drops minLength/maxLength when combined with pattern. Gemini and Outlines both
  silently degrade oneOf -> anyOf. Outlines cannot enforce minimum/maximum,
  truncates recursion at depth 3.

### Step (c) already ships: STRUCTURAL TAGS
XGrammar-2 Structural Tags, deployed in vLLM, SGLang, TensorRT-LLM, MLC-LLM.
JSON Schema as a first-class atomic type composable inside a larger structure;
`TriggeredTags` switches the active constraint on the model's own earlier output.
100% schema accuracy on BFCL-V3. State-conditioned grammars also solved: GENRE
(2021), PICARD (2021), Trie Automata (2026).
Caching objection dissolves: sub-grammar depends only on (S, path) so it is
precompilable and the "10 rows" grammar is byte-identical every batch; Anthropic
caches compiled grammars 24h from last use; a trie over 100,000 strings compiles
in **67 ms**, masks at **0.65 us/token** (arXiv:2608.12574).

### The quality argument beats the cost argument
arXiv:2604.27906: per-field accuracy 0.97 over 20 fields => single-pass OBJECT
accuracy **~0.54**; iterative per-field generation with validation **~0.98**.
Measured cascade: field F1 97.53% -> object accuracy 90.42% -> output accuracy
62.67%. Their iterative pipeline beat GPT-5.5 high-reasoning (44.00%) and
Gemini 3.1 Pro (61.67%). **Errors compound multiplicatively; fragmenting breaks
the compounding.** This is H6 confirmed with a mechanism.

### Distortion worry was misplaced — DROP from risk list
No published evidence a narrower grammar distorts more. Tam et al. confounded
(different prompts per condition); .txt re-run reverses it; JSONSchemaBench
measures constrained decoding IMPROVING accuracy +3.3 to +3.7 points;
arXiv:2606.25605 finds a binary not graded effect. Real damage is token
misalignment (-10.7 GSM8K, fully fixed by DOMINO). GAD/ASAp distortion is
#P-hard for everyone and orthogonal to fragment size.

### H2 CONFIRMED — the corruption is measured
**DELEGATE-52** (Laban, Schnabel, Neville; arXiv:2604.15597, Apr 2026), 19 models,
52 domains: frontier models corrupt **an average of 25% of document content by
the end of long workflows**; **~50% across all models by turn 20**; "each 1k-token
increment progressively increases degradation"; **no plateau to 100 turns**.
arXiv:2601.03640 (verbatim transcription): **0% perfect runs at N=300 items**,
down from 44% at N=100. Speculative decoding is distribution-preserving BY
THEOREM, so it reproduces every one of these errors faithfully and faster.

### The rho argument — why 31% is not the ceiling
rho = k/N. JSON Whisperer and Morph both measure **rho ~ 0.3-0.5** on 5-10k-token
artifacts. The user's form case is **rho = 0.006**, where the same cost model
predicts **~39x on dollars, ~109x on latency**. **Nobody has measured that
regime.** 31% confirms the cost model rather than bounding it.

### Wording discipline (D's caveat)
Do NOT write "input is cheap, output is expensive" — production cost attribution
says input dominates agentic bills. Defensible version: **in a
regenerate-the-whole-object turn, input and output token counts are equal, so the
50-200x price gap falls entirely on the output side.**

### The quadratic input trap — design constraint
1,000 chunked calls where each sees all prior rows costs **$102.50 input vs
$10.00 output** on Opus 5. **The design MUST bound what chunk i sees of 1..i-1.**

### The opening
**The constrained-decoding literature and the decomposed-extraction literature do
not cite each other at all.** One knows how to enforce a grammar at decode time;
the other knows field-by-field beats whole-object. Nobody has asked what happens
when you do both. Conjecture 2 (compositionality) is genuinely open — searched,
nothing found.

### Batch status
- Batch 1: A DONE (115 KB), D DONE (80 KB), B still running.
- Batch 2: E resumed (needs sections 2,3,4,5), G resumed (redirected to CP
  decomposition + ALLDIFFERENT/GCC lead, then DB deferred constraints, then CRDTs).
- C and F complete.
- notes/03-research.md written and current as of A + D landing.

---

## COMPLETE — 2026-09-07. All 7 agents finished; all 5 notes written.

### Final additions from batch 2 (E, G)

**E — the flat case was already solved, in 2020, in another vocabulary.**
Dialogue state tracking: **SOM-DST** (per-slot operation: carry/delete/update),
**MinTL** (Levenshtein belief spans), and **Rasa Pro CALM** shipping an
LLM-driven SetSlot-per-changed-field mechanism in production TODAY. But a belief
state is a FLAT BAG OF INDEPENDENT SLOTS — compositionality never arises. Nesting,
recursion, $ref, arrays with cardinality/uniqueness, conditional sub-schemas are
all absent. **That is the line: flat slots solved, nested schemas open.** Cite as
prior art; claim only the nested case.
- Library audit: **clean negative across all 9** (Instructor, BAML, Outlines,
  Guidance, Marvin, Mirascope, DSPy, LangChain, LlamaIndex). None supports
  sub-schema projection or "update this object".
- Documented demand: Outlines issue **#1383** — practitioner hits this exact wall,
  falls back to raw `pydantic.create_model()`, calls it "clunky". BAML TypeBuilder
  /@@dynamic is **additive-only**, cannot narrow (its own issue **#2980**).
- **Guidance has every primitive already** (immutable `lm +=` + `gen_json(schema=)`)
  — nobody has packaged it. Missing library, not missing capability.
- LangGraph channel reducers solve P4 (splice) only. CrewAI/AutoGen/OpenAI Agents
  SDK have no merge mechanism at all.

**G — adjacent formalisms.**
- **CRDTs DO NOT TRANSFER, with a smoking gun:** Automerge's own core maintainer
  built `automerge-jsonschema`, a RESTRICTED vocabulary discarding maxContains/
  contains/prefixItems because ordinary keywords **"do not distribute over
  merges"**. A merge can violate a constraint BOTH inputs satisfied.
- **OT** — correctness is structural convergence (TP1/TP2), never validity.
- **Delta encoding** — byte-level, vocabulary only.
- **CP TRANSFERS, and the boundary lands on us: Beldiceanu et al., AAAI 2013
  (arXiv:1309.7145) — regular-language constraint + at-most/at-least cardinality
  is POLYNOMIAL; exact-count is NP-HARD.** minItems/maxItems are at-most/at-least,
  so the second of our two new costs is TRACTABLE. NEGATIVE RESULT: no clean
  full-generality joint GAC for GRAMMAR + ALLDIFFERENT, so uniqueItems stays hard.
- **Freuder (JACM 1982)** width/backtrack-free search: a computable diagnostic for
  when local consistency implies global consistency — a second, independent safety
  check alongside the O(|p|) keyword walk.
- **Assume-guarantee** (Pnueli 1984; Clarke/Long/McMillan 1989): PROJECT should
  derive an INTERFACE ASSUMPTION, not just a syntactic sub-schema. Better framing
  of P2, adopted in notes/04.
- **DB deferred constraints + transaction abort/retry** = GENERATE→SPLICE→
  REVALIDATE, decades-validated, with precedent for our residue (cyclic FKs,
  swapping unique values, out-of-order ingestion).
- **Ross, Srivastava & Sudarshan (1996)**: encode integrity constraints as
  materialised views required to be empty => IVM maintains the VALIDITY CHECK
  incrementally. **This is the recipe for the missing incremental JSON Schema
  validator.**
- Evaluation: plain TED needs a JSON-aware semantic layer; **STED**
  (arXiv:2512.23712) and **GTED** (arXiv:2507.07399) do this. Practical JSON diff
  tools (jsondiffpatch, json-delta, deepdiff) are LCS heuristics, NOT minimum TED.

### Deliverables — all written
- `README.md` — index and the idea in one paragraph.
- `notes/00-original-note.md` — verbatim transcription.
- `notes/01-problem-plain-english.md` — plain English, form + spreadsheet examples.
- `notes/02-formulation.md` — academic formulation (§6.3 carries a correction
  banner pointing to 03 §11).
- `notes/03-research.md` — 13 sections, full literature answer.
- `notes/04-solution-approaches.md` — verdict, design P1-P5, what not to do, the
  settling experiment, risks, paper contributions, recommendation.
- `research/raw/` — A (115 KB), B (152 KB), C, D (80 KB), E (85 KB), E1, E2,
  F, G (64 KB). ~600 KB of sourced research with provenance markers.

### The verdict in one line
All three endings are true in different parts. Flat slots: solved (DST, 2020).
Mechanism: solved (Structural Tags). Exact decode-time guarantee: does not need
solving and is PSPACE-complete/undecidable anyway. **Open: the JSON Schema
instance of the compositional class, incremental JSON Schema validation, and the
large-N low-rho measurement nobody has run.**

### If resuming
Everything is written. The only outstanding work is the experiment in
`notes/04-solution-approaches.md` §5, which the user has NOT asked for (scope is
research answer only, no prototype). Do not start building without asking.

---

## Phase 2 — codebase built, 2026-09-07

`uv` project, Python 3.12, deps: google-genai, pydantic, python-dotenv, httpx,
tenacity, rich, pytest. `git init` done, `.env` gitignored and verified ignored.
No commits made (not asked for).

### Layout
| module | concept |
|---|---|
| `src/dsw/config.py` | keys, pinned model, measured free-tier quota |
| `src/dsw/providers.py` | Gemini (primary), OpenRouter (cross-check, reports constrained=False) |
| `src/dsw/forms.py` | corpus: `ReviewForm` + `DecodableReviewForm` |
| `src/dsw/projection.py` | P2 projection + P5 O(\|p\|) safety walk |
| `src/dsw/splice.py` | P4 dump/patch/model_validate |
| `src/dsw/metrics.py` | untouched-region integrity |
| `src/dsw/experiment.py` | two arms, throttle, resumable JSONL runner |
| `scripts/` | smoke.py, run_integrity.py, analyse.py |

### API facts — MEASURED, all secondary sources were wrong
- **Gemini free tier = 20 requests/day/model.** From the API's own 429 body:
  `quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier, quotaValue: 20`.
  Blogs claiming 1,500/day are wrong. Retested 3x over 15 min — it is a real
  daily cap, not a per-minute window (the `retryDelay: 31s` hint is misleading).
- **OPENROUTER_API_KEY is DEAD.** `GET /api/v1/key` -> 401 "User not found".
  Format is fine (73 chars, `sk-or-v1-` prefix) so it is revoked/orphaned, not
  mistyped. Needs replacing at openrouter.ai/keys. Nothing to fix in code.
- **INCEPTION_API_KEY works**, model `mercury-2`, strict json_schema confirmed
  working. But Mercury is a **diffusion** LLM -> paradigm confound for the main
  arm. Reserved as a follow-up (does in-place refinement corrupt less?).

### Model selection — four attempts, all recorded in config.py
| candidate | outcome |
|---|---|
| gemini-2.5-flash | 404 "no longer available to new users" |
| gemini-3.6-flash | works; free bucket spent during setup probing |
| gemini-3.7/3.8-flash | reject thinking_level "minimal" AND "low" with 400 |
| **gemini-3.5-flash** | **PINNED** — accepts "minimal", 0 thought tokens |

`gemini-flash-latest` excluded on principle: a moving alias reintroduces the
model effect the experiment exists to remove.

### Two findings that fell out of building it
1. **Gemini rejects `minItems`/`maxItems` outright** (400 INVALID_ARGUMENT, at
   max=50 as well as 400) despite its own docs listing them as supported. Not
   silently dropped — refused. Handled by keeping TWO models: `ReviewForm`
   (real constraints, all validation) and `DecodableReviewForm` (weaker, used
   only for generation), so the enforcement gap shows up in results.
2. **Thinking must be held down or output accounting is meaningless.** Default
   thinking spent 561 tokens on a trivial call; thinking bills as output.
   `thinking_level="minimal"` gives 0 thought tokens on 3.5-flash.
   `thinking_budget=0` and `"none"` are 400s on Gemini 3.x.

### Two bugs found and fixed by running it
- Transient network failures (`RemoteProtocolError`, dropped connections on
  ~50s 17K-token generations) were not in the retry set. Now are.
- Resume marked a *failed* chain as done, so one dropped connection permanently
  poisoned that cell. Now only fully-successful chains are skipped.

### First results (thin, large=16,895 tokens, gemini-3.5-flash)
`data/runs/integrity_first_attempt.jsonl` — 3 good turns before the transport bug:
| arm | turn | integrity | applied | out tokens | latency |
|---|---|---|---|---|---|
| baseline | 1 | **1.0000** | yes | 16,883 | 50.4s |
| baseline | 2 | **1.0000** | yes | 16,883 | 52.8s |
| fragment | 1 | 1.0000 | yes | **98** | **4.3s** |

**172x fewer output tokens, 12x faster.** But integrity is 1.0 on baseline for
the first two turns — H2 is NOT showing yet at this size/depth. Whether it
compounds over more turns is the open question the deeper run tests.
Token estimates were near-exact (predicted 17,045 in / 16,895 out; actual
16,988 / 16,883), so the budget model is sound.

### Designs
- `--design thin`: large only, 1 seed, 10 turns, both arms = 20 calls = one
  free-tier day = ~$0.89 paid.
- `--design thick`: 3 sizes x 5 seeds x 10 turns x 2 arms = 300 calls,
  ~3.62M tokens, ~$6.32 paid (~$3.16 batched). 15 days on free tier.

### Next
- Deeper baseline chain running to test turn-compounding.
- Thick design needs paid billing (~$6/run) or a working OpenRouter key.
- Formulation doc 02 §3 updated with the constrained-decoding answer + §3.1
  distinguishing its three roles (guarantee / mechanism / rejected candidate).

## RESULT — thin design, 2026-09-07. H2 NOT SUPPORTED.
gemini-3.5-flash, large=16,895 tokens, 1 seed.
| arm | perfect integrity | mean out tokens | latency |
|---|---|---|---|
| baseline | **12/12 (100%)** | 16,869 | 54.5s |
| fragment | 1/1 | **98** | **4.35s** |

- **Cost case CONFIRMED and bigger than predicted: 172x fewer output tokens,
  12.5x lower latency.** Budget model near-exact (predicted 17,045/16,895,
  actual 16,972/16,869) so extrapolation is trustworthy.
- **Integrity case NOT SUPPORTED.** 12 consecutive turns, zero corrupted leaves,
  no compounding. Literature predicted ~25% corruption (DELEGATE-52) and 13%
  lazy elision (Aider). Neither appeared.
- **Leading hypothesis: constrained decoding itself prevents it.** The corruption
  literature measures UNCONSTRAINED regeneration; our baseline runs under a
  decode-time schema constraint. If so the thesis RELOCATES, not collapses:
  integrity argument applies to unconstrained regeneration; for
  already-constrained output the reason to fragment is cost/latency (172x).
- **Next experiment, highest value: unconstrained baseline arm** (drop
  response_mime_type/schema). If corruption appears there and not here, the
  relocation is confirmed and becomes the finding. Ahead of the thick design.
- Caveats: n=1 seed, one size, one model, synthetic corpus with regular repeating
  structure. Null at n=1 is evidence not proof — but it is a null at the size and
  depth where the effect was predicted largest.
- notes/04 §9 added recording this against my own earlier argument; risk table
  row "Integrity turns out fine" marked as materialised.

---

## Phase 3 — the retry experiment, 2026-09-07. OSCILLATION NOT SUPPORTED.

Built and run after the user asked whether fragment generation helps on
**retries** — salvaging a partly-good output instead of re-rolling the whole
thing. It was the strongest remaining argument, because it does not depend on
the integrity claim the thin design already nulled.

Full design and results: `RETRY.md`. New code: `src/dsw/constraints.py`,
`src/dsw/retry.py`, `scripts/run_retry.py`, `scripts/analyse_retry.py`,
`metrics.integrity_outside` (multi-path). Data: `data/runs/retry.jsonl`.

### Why the retry path looked strong (the argument going in)
- **P1 stops being hand-wavy.** `ValidationError.errors()[i]['loc']` IS a JSON
  pointer. The weakest link in P1-P5 is solved free by the thing that triggered
  the retry.
- **Retries are the hot loop, not the rare path.** notes/03: per-field 0.97 over
  20 fields => single-pass object accuracy ~0.54.
- **The new claim:** whole-object reask is a random walk on validity (fixing
  field 7 can break field 30); fragment repair is coordinate descent, hence
  monotone. That is where the residual/locality analysis finally earns its keep.

### What was measured
6 episodes, 21 steps, **20 free-tier calls — the exact daily cap**, medium
(70 responses) + one small + one large. Three coupled closure rules, gated on
`status == "resolved"`, so R2/R3 form a real trap: promoting a low-confidence
answer to `high` trades an R3 violation for an R2 one. Asserted offline.

| | whole (reask) | fragment (targeted) |
|---|---|---|
| reached valid | 4/4, 1 round, 1 call | 3/4, 1 round, 2.75 calls |
| **introduced a new violation** | **0 / 4 steps** | **0 / 10 steps** |
| mean fixed per step | 3.50 | 1.00 |
| collateral (integrity) | **4/4 perfect, 1.00000** | 10/10 perfect, 1.00000 |
| mean output tokens | 5,800 | **257** |
| mean latency | 26.5s | **9.0s** |

**Mean 25.7x fewer output tokens to repair, median 26.0x.**

### The findings, in order of importance
1. **H(oscillation) NOT SUPPORTED.** Zero introduced violations in either arm.
   The whole arm fixed **eight violations in a single call** on the high-density
   episode. Every repair was monotone. This is the third integrity-shaped null
   in a row; the honest reading is that for schema-constrained output from a
   current frontier model, **regeneration is simply reliable**, and every
   surviving reason to fragment is economic.
2. **Collateral damage on the retry path is also zero** — the one path the thin
   design never exercised. Confirms and extends the earlier null.
3. **NEW NEGATIVE, and it is ours:** the fragment arm pays **one call per
   violation**, so its advantage shrinks with violation density. 3 violations:
   2 calls vs 1, 26x on tokens. 9 violations: 8 calls vs 1, ~6x. There is a
   crossover where per-call overhead eats the saving. **Batching sibling repairs
   into one projected call is the fix and is NOT built.** Build it first.
4. **Localisation split: 64% exact / 36% hinted, 0% unlocalisable.** R2 is
   declared on `Response` so Pydantic's `loc` is exact and free; R1/R3 need
   `status`, live on the form, so `loc == ()` and the path must be declared by
   hand. **Design rule: where you put the validator decides whether a retry can
   be aimed.** Costs nothing to follow.
5. **With the rules stated up front, the failure does not happen at all.**
   2/2 episodes valid on the first attempt, including 3 violations fixed while
   retyping a 220-response / 16,895-token document in one pass. So the default
   withholds the rules — the ordinary production failure, where business rules
   live in the validator and the prompt under-specifies.

### Caveats (do not overstate this)
- n=6 episodes, one model, one synthetic corpus. A null at low n.
- `medium/0/p8` fragment arm is **incomplete** — 4 of 8 repairs before the
  20-call cap. Its 12.1x ratio is a lower bound, not a finished episode.
- **Unexplained:** `medium/2` whole-arm repair emitted 7,562 output tokens for a
  5,276-token document, `finish_reason=STOP`, 0 thought tokens, integrity
  perfect. Output correct; token count not explained.

### Next, in priority order
1. Batch sibling repairs into one projected call (removes finding 3).
2. **Unconstrained arms — still the highest-value experiment in the repo**, and
   now it settles both experiments at once: drop `response_mime_type` and see
   whether corruption AND oscillation appear where the constraint is absent.
3. More episodes at high violation density; the null rests on 4 whole-arm steps.
4. A genuinely unlocalisable rule (global counting/uniqueness) to measure the
   fallback case at 0% instead of asserting it.

Free tier is exhausted for `gemini-3.5-flash` today (20/20). The whole retry
grid costs ~$0.30 paid, so billing is the unblocker, not budget.

---

## Phase 4 — the user's rebuttal, and the agentic-loop experiment. BUILT, NOT RUN.

The user rejected the "regeneration is simply reliable" conclusion on two
grounds. **Both are correct and one is a defect in the instrument, not a
limitation of scope.** Full write-up:
`notes/05-what-the-experiments-did-not-test.md`.

### Objection 1 — the schema was too easy
`ReviewForm` is depth 3 with no unions, no recursion, no lists-in-lists, one
flat cross-field rule. Every property notes/03 blames for structural failure was
absent. Displacement Rate (arXiv:2608.25358) reports 24-74% **at highest
complexity**; we measured at the bottom of the range and reported the absence of
an effect defined to appear at the top.

### Objection 2 — CONFIRMED AS A DESIGN DEFECT
`experiment.py:107` builds every turn's prompt from scratch. There is **no
transcript**. So the "12-turn chain" was 12 independent single-shot calls at a
flat ~17K prompt on a 1M window — **~1.6% of the window at turn 1 and turn 12
alike**. `EXPERIMENT.md` claimed the chain captured DELEGATE-52's compounding;
it conflated *document lineage* with *context accumulation*. DELEGATE-52
measures the latter ("each 1k-token increment progressively increases
degradation", "no plateau to 100 turns").
**The mechanism the experiment set out to detect was structurally excluded from
the design.** The null is a measurement taken with the effect switched off.

Lost-in-the-middle status: **not fixed**. Simple needle retrieval is saturated
(which is why NIAH stopped being informative), but aggregation/multi-hop/
semantic-match tasks still degrade far below the advertised window (RULER,
NoLiMa). Faithful reproduction is in the second category. *Directional claim —
needs a current citation check before it goes in a paper.*

### The asymmetry neither of us had written down — and it favours the thesis
In a real loop the transcript accumulates, and the two arms grow at wildly
different rates. The whole arm **poisons its own context** by ~one document per
turn until it is operating in the degraded regime; the fragment arm stays flat.
This is the **quadratic input trap** from notes/04 §3 — already filed as a *risk
to our design* — seen from the other side: the baseline pays it in full and the
fragment arm barely pays it at all. Same phenomenon, opposite sign.

### Status of earlier claims
| claim | status |
|---|---|
| cost 172x (edit) / 26x (repair) | **stands** |
| collateral damage zero | stands, **but only at 1.6% context, depth-3 schema** |
| oscillation does not occur | stands, same two qualifiers |
| "regeneration is simply reliable" | **WITHDRAWN** |
| "every surviving reason is economic" | **WITHDRAWN as premature** |

### What was built (all offline-verified, zero API calls spent)
| file | what |
|---|---|
| `src/dsw/dossier.py` | depth-5 corpus: discriminated union of 3 block kinds, lists-in-lists, subsections, strict/decodable split |
| `src/dsw/dossier_rules.py` | D1 local, **D2 referential** (spans the document), D3 structural, **D4 global/unlocalisable**, D5 branch shape |
| `src/dsw/agentic.py` | the accumulating-transcript loop, both arms, mid-chain resume |
| `scripts/run_agentic.py` | runner + `--offline` invariants + `--dry-run` growth curve |
| `scripts/analyse_agentic.py` | per-turn trajectory, divergence point, integrity by context band |
| `providers.py` | now takes `history=[(role, text)]` as real multi-turn `contents` |

**D4 fills the gap `RETRY.md` flagged:** it is genuinely unlocalisable
(`repair_paths == ()`), so the fallback case can be measured instead of asserted
at 0%.

### Two design bugs caught before spending anything
1. **The transcript was storing the full document-bearing prompt**, so both arms'
   context would have grown by a document per turn and the isolation would have
   been destroyed. Fixed: history holds the *instruction* + output; the current
   document is injected fresh each turn.
2. **No mid-chain resume.** A 40-turn chain needs 40 consecutive calls against a
   20/day cap, so it would die at turn 20 and restart from turn 1 forever — the
   free tier could not have run this experiment at all. Fixed and **verified
   with a stub provider**: 3 turns, resume to 5, exactly 2 new calls, transcript
   continuous across the boundary.

### The prediction, recorded before the run so it can be wrong
The arms track each other for the first several turns — reproducing the earlier
nulls as a control — then diverge, baseline integrity falling as its context
grows while the fragment arm stays flat.

### Budget — free tier exhausted 2026-09-07 (20/20 on gemini-3.5-flash)
| design | whole final ctx | frag final ctx | paid |
|---|---|---|---|
| small, 30 turns | 63K | 8.7K | $1.11 |
| small, 40 turns | 84K | 11K | $1.82 |
| medium, 30 turns | 166K | 12K | $2.76 |
| **medium, 40 turns** | **221K** | **14K** | **$4.53** |

Recommended: **medium / 40 turns**, which drives the whole arm to ~221K context
against the fragment arm's ~14K — a 15x contrast, deep enough to be well past
most models' effective context. `--max-history-turns N` runs the "just prune the
transcript" objection as its own condition.

### Resume
`uv run python scripts/run_agentic.py --sizes medium --turns 40` — safe to
interrupt, resumes mid-chain, then `scripts/analyse_agentic.py`.

---

## Phase 4a — the day-by-day run plan (free tier)

### When the quota resets
Google's free-tier daily quota resets at **midnight Pacific**, not midnight
local. In September that is PDT (UTC-7), and this machine is IST (UTC+5:30), so
the two are 12h30m apart:

> **The quota day rolls over at 12:30 PM IST.** Not at local midnight.

So a run started in the morning is still on the *previous* day's bucket. Start
after lunch. (Confidence: this is the documented behaviour for Google Cloud
daily quotas; it will be confirmed empirically by the first call after 12:30 —
if it 429s, the reset is on a different clock and this note is wrong.)

### The phasing — 10 turns per day, BOTH arms
`medium` / 40 turns / 2 arms = 80 calls = 4 quota-days at 20/day.

Run both arms to the *same depth* each day rather than finishing one arm first.
Mid-chain resume (verified with a stub) makes this free, and it means **every
day ends with a complete, analysable comparison** instead of three days of half
an experiment.

| day | command | calls | whole ctx | frag ctx |
|---|---|---|---|---|
| 1 | `--sizes medium --turns 10` | 20 | ~55K | ~7K |
| 2 | `--sizes medium --turns 20` | 20 | ~110K | ~9K |
| 3 | `--sizes medium --turns 30` | 20 | ~166K | ~12K |
| 4 | `--sizes medium --turns 40` | 20 | ~221K | ~14K |

```bash
uv run python scripts/run_agentic.py --sizes medium --turns <N>
uv run python scripts/analyse_agentic.py
```

Each day re-runs the same command with `--turns` bumped by 10. Prior turns are
replayed from the log at zero cost; only the new ones are bought.

- **Each day is exactly 20 calls, with no slack.** A failed turn eats into that
  day's budget, but resume makes the shortfall harmless — the next day simply
  picks up where it stopped. Nothing is ever re-bought.
- **Stop early if the divergence appears.** The prediction is that the arms track
  each other and then separate. If `analyse_agentic.py` shows the whole arm
  losing integrity at day 2 or 3, the result is in hand and days 3-4 become
  confirmation rather than discovery.
- **Day 5, optional:** the pruning condition —
  `--max-history-turns 5 --out data/runs/agentic_pruned.jsonl` — which answers
  "why not just prune the transcript instead".

Paid alternative: the whole 4-day grid is **~$4.53** in one sitting.
