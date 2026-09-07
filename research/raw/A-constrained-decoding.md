# A — Constrained decoding foundations: what the guarantee actually is, and where it stops

Research agent A. Started 2026-09-07.
Scope: (1) the precise guarantee of grammar-guided decoding; (2) per-engine JSON Schema keyword
coverage audit; (3) compilation cost; (4) theory limits (non-CF constraints, lookahead);
(5) distribution distortion; (6) prior work on dynamic / state-conditioned grammars.

**Verification convention used throughout:**
`[PRIMARY]` = I fetched the paper / spec / source code / official docs page myself and read the
claim there. `[SECONDHAND]` = I only saw it asserted in a blog, issue thread, or another paper.
`[INFERRED]` = my reading of primary material, not a direct quotation.

---

## How to read this file

Sections were appended in the order the research happened, so they are **not in numeric order**.
Reading order on disk:

| On disk | Section |
|---|---|
| 1 | The precise guarantee (Outlines, DOMINO, XGrammar, XGrammar-2) |
| 2 | Keyword coverage audit — JSONSchemaBench, OpenAI/Azure, llguidance, Gemini, llama.cpp, vLLM, SGLang, Anthropic, **summary matrix in 2.9** |
| 5 | Distribution distortion (GAD/ASAp, Tam et al. and the .txt rebuttal) |
| 4 | Theory limits (lookahead, NP/#P hardness, sound vs complete, counting constraints, CP literature) |
| 6 | Dynamic / state-conditioned grammars (GENRE, Trie Automata, XGrammar-2, PICARD) — **and the real negative in 6.5** |
| 2 cont. | Audit addenda: Outlines from source (2.10), corrections (2.11-2.12), **the three failure modes (2.13)** |
| 3 | Compilation cost, consolidated tables |
| **PART TWO** | The reframed questions 7-11 |
| 7 | Sub-schema projection in practice — root-type table, the `$ref` problem, **Structural Tags (7.3)** |
| 8 | Grammar caching across many small calls |
| 9 | Compositionality — what composes and what does not |
| 10 | Cross-fragment state — **the second real negative** |
| 11 | Field-at-a-time vs whole-object accuracy |
| 5 cont. | Does distortion scale with restrictiveness? (the Constraint Tax sweep) |
| J1-J8 | My judgement |
| — | What I did not get to; full source list |

**If you read only three things: section 2.9 (the keyword matrix), section 2.13 (the three failure
modes), and J2 (the residue is the status quo).**

A **consolidated list of every source, marked read-in-full vs lead-only, is at the END of this
file.**

---
## 1. The precise guarantee

### 1.1 Willard & Louf, "Efficient Guided Generation for Large Language Models" (Outlines)

- Brandon T. Willard, Rémi Louf, 2023, arXiv:2307.09702 (never formally published at a venue; it is
  the reference paper for the Outlines library). https://arxiv.org/abs/2307.09702
- Read via ar5iv HTML rendering: https://ar5iv.labs.arxiv.org/html/2307.09702  **[PRIMARY]**

What the method is, precisely:

- The generation process is reformulated as **transitions between states of a finite-state machine
  (FSM)**. A regular expression is compiled to a DFA; an index `sigma: Q -> P(V)` maps each FSM
  state to the *subset of the vocabulary* whose token strings can legally be read from that state.
- The decode step is a **logit mask**: `alpha_tilde = m(S_tilde_t) * alpha` — build a boolean mask
  from the current FSM state, multiply into the logits, then sample. (Algorithm 2, lines 5-6.)
  **[PRIMARY]**
- Cost claim: **O(1) on average per token** after preprocessing, versus O(N) per token for the naive
  approach where N = |V| ~ 50,000. **[PRIMARY]**
- Index memory: proportional to the number of FSM states |Q|. For an "augmented Python grammar" the
  index is reported at **~50 MB** even using un-reduced DFAs. **[PRIMARY]**
- CFG extension: uses an **LALR(1) parser + pushdown automaton**. For each parse state they build an
  FSM that is the union of the FSMs of the terminal symbols readable in that state; the index
  becomes a **trie** so it can be queried against the parser stack. **[PRIMARY]**
- The paper's own timing evidence against Guidance is a **plot, not a table** — I looked for a
  numeric table and there is none in the ar5iv rendering. The claim is qualitative scaling
  ("Outlines stays roughly flat in max sampled tokens, Guidance grows"). Treat "significantly
  outperforms" as a plot-level claim, not a tabulated measurement. **[PRIMARY, negative finding]**

**What the guarantee actually is (my reading, [INFERRED] from the above):** at every decode step the
sampled token is one that keeps the generated string a **prefix of some string in L(G)**. That is
*prefix-validity*, plus termination in an accepting state if the engine forces it. It is a guarantee
about *membership in a formal language*, and nothing else. Two consequences that matter to us:

1. Anything not expressible in the grammar is simply outside the guarantee. There is no notion of
   "the value is semantically right" or "this document satisfies a constraint that spans two
   distant subtrees".
2. Prefix-validity is only useful if the engine can decide *can this prefix still be completed?*
   For regular languages that is trivial (non-dead state). For CFGs it needs a parser with
   lookahead. See section 4.

### 1.2 Beurer-Kellner, Fischer, Vechev — "Guiding LLMs The Right Way: Fast, Non-Invasive Constrained Generation" (DOMINO), ICML 2024

- PMLR v235; arXiv:2403.06988; https://proceedings.mlr.press/v235/beurer-kellner24a.html
- Read via ar5iv HTML: https://ar5iv.labs.arxiv.org/html/2403.06988 **[PRIMARY, via LLM extraction
  of the HTML — key numbers flagged for re-verification below]**

Key contributions relevant to us:

- **Definition 2.1 (Minimally Invasive).** A constrained decoding method is minimally invasive if
  *every valid output that the unconstrained model could generate for a prompt is also generatable
  by the constrained model on the same prompt.* This is the formal version of "the constraint
  should filter, not steer." **[PRIMARY]** This is exactly the "sound vs complete masking" notion
  asked about in Q4: a non-minimally-invasive method forbids *too much*.
- **The subword misalignment problem.** LLM vocabularies are sub-word; grammar terminals are not
  token-aligned. Naive per-token masking commits to a tokenisation of the terminal and thereby
  excludes token sequences that would have produced a *valid* string via a different tokenisation.
  So the constraint is not merely a filter — it removes legal outputs. **[PRIMARY]**
- **Measured accuracy damage from naive constraining** (their Table 2, GSM8K, Mistral 7B):
  unconstrained **41.5%**, naive constrained (guidance) **30.8%** (a **10.7 point drop**),
  DOMINO (minimally invasive) **41.8%**. Similar effect reported on CoNLL2003.
  **[PRIMARY — but extracted by the fetch model; I did not eyeball the PDF table. Flagged.]**
  This is one of the most important numbers in the whole area: it shows *the mechanism by which
  constrained decoding hurts accuracy is often an implementation artefact (misalignment), not the
  constraint itself.*
- **Speed** (their Table 3): DOMINO 1.77x speedup vs unconstrained on JSON-with-schema (Mistral 7B),
  1.66x on Llama-2 13B JSON schema, 1.52x on XML; guidance ~0.5-2.0x, llama.cpp ~0.74-0.87x
  (i.e. llama.cpp's GBNF masking makes generation *slower* than unconstrained). Speedup >1 comes
  from a speculative-decoding trick: when the grammar forces the next characters, emit them free.
  **[PRIMARY, same caveat]**
- **Precomputation cost: 1-5 seconds for typical grammars, ~20 s for a C grammar** (Section 4.3).
  **[PRIMARY, same caveat]** — this is a *very* important number for the delta idea: DOMINO-style
  precomputation is seconds, so it is emphatically NOT something you can redo per request from a
  document D without blowing the latency budget, unless the construction is far cheaper.

### 1.3 XGrammar (Dong et al., 2024) — arXiv:2411.15100

- https://arxiv.org/abs/2411.15100 ; full text read at https://arxiv.org/html/2411.15100 **[PRIMARY]**
- Mechanism: split the vocabulary into **context-independent** tokens (validity decidable from the
  automaton position alone, precomputable) and **context-dependent** tokens (need the parser stack).
- Numbers **[PRIMARY]**:
  - For Llama-3.1 (128k vocab) with a JSON grammar, **context-dependent tokens are <1% — 1,134 of
    128k**; a "context expansion" optimisation cuts that by **90%, to 120 tokens**.
  - Adaptive token mask cache memory reduced **from 160 MB to 0.46 MB (0.2%)** for that setting.
  - Per-token mask latency (Figure 9): **under 40 microseconds** for JSON Schema and JSON CFG;
    **under 200 microseconds** for XML and a Python DSL.
  - Speedups vs best baseline (Outlines v1.0, llama.cpp b3998, lm-format-enforcer v0.10.9):
    **up to 3x on JSON Schema, over 100x on CFG**.
  - Prefix-based rollback reduces characters checked across the vocabulary to **30%**.
- **Negative findings I checked for and did not find in the paper:** no explicit table of grammar
  *compilation* time and its scaling; no enumeration of which JSON Schema keywords are supported;
  no discussion of grammar cache reuse across requests. **[PRIMARY, negative]**

### 1.4 XGrammar-2 (2026) — the closest existing thing to "dynamic grammars"

- "XGrammar-2: Dynamic and Efficient Structured Generation Engine for Agentic LLMs",
  arXiv:2601.04426, published at **ACM CAIS 2026** (Conference on AI and Agentic Systems),
  DOI 10.1145/3786335.3813124. Full text: https://arxiv.org/html/2601.04426v2 **[PRIMARY]**
- **This is the single most relevant prior work I found for Q6.** It is explicitly about grammars
  that are *not* known ahead of time.
- Their taxonomy of dynamism **[PRIMARY]**:
  - **Inter-request dynamism**: "each request may expose a different set of tools and schemas, often
    with per-tool access control" — so the grammar is assembled per request from a live tool
    catalogue. This is state-conditioned grammar construction, though the state is a *tool list*,
    not a document instance.
  - **Intra-request dynamism**: the constraint switches based on the model's own earlier output
    (choosing a tool name selects the schema for its arguments). This is a *dependent* grammar —
    directly analogous to our `trie(pointer) x subschema(pointer)` product.
- Cost numbers **[PRIMARY]**:
  - Grammar compilation: **XGrammar-2 ~10 ms vs XGrammar >1000 ms** (Fig. 8) for the dynamic
    tool-catalogue setting. The mechanism is **JIT compilation** — compile automaton states lazily,
    amortised over mask generation, "avoid compilation for states that are never used" — plus
    **cross-grammar caching** of shared substructures.
  - Per-token overhead **<250 microseconds** (Fig. 7); llguidance quoted at 250-1000 microseconds
    per token in their comparison.
  - End-to-end **7x** speedup over XGrammar (Fig. 9).
  - Mask generation baseline 45.50 microseconds; "repetition compression" improvement 99.6x
    (Table 4) — repetition compression is how they handle minItems/maxItems/minLength/maxLength
    without blowing up the automaton.
  - Experimental setting: a pool of **100 tools from BFCL**, each request sampling **5, 20 or 50**
    of them at random.
- **Explicit negative**: the paper contains **no discussion of incremental editing or patch-style
  modification of an existing structure**. It constrains generation from scratch every time.
  **[PRIMARY, negative — important for us]**

---

## 2. Keyword coverage audit — the crucial audit

### 2.0 The single best public evidence: JSONSchemaBench (Geng et al., 2025)

- "JSONSchemaBench: A Rigorous Benchmark of Structured Outputs for Language Models"
  (earlier title: "Generating Structured Outputs from Language Models: Benchmark and Studies"),
  Saibo Geng et al., EPFL DLAB, arXiv:2501.10868. Full text read at
  https://arxiv.org/html/2501.10868v3 **[PRIMARY]**. Dataset: 10K real-world JSON schemas,
  https://huggingface.co/datasets/epfl-dlab/JSONSchemaBench
- Six engines evaluated: **Guidance (llguidance), Outlines, llama.cpp, XGrammar, OpenAI, Gemini.**

**Their definitions (Definition 5.0)** **[PRIMARY]**:
- **Declared coverage** — the framework accepts the schema without rejecting it or erroring.
- **Empirical coverage** — the outputs produced under the framework's constraints are actually
  schema-compliant.
- **Compliance rate** = empirical / declared: how often the engine's promise is kept once it has
  accepted a schema.

**Empirical coverage by dataset (their Table 4)** **[PRIMARY]**:

| Dataset | Guidance | Outlines | llama.cpp | XGrammar | OpenAI | Gemini |
|---|---|---|---|---|---|---|
| GlaiveAI (tool-call schemas) | 96% | 95% | 95% | 93% | 89% | 86% |
| GitHub Easy | 86% | 59% | 75% | 79% | 29% | 7% |
| Snowplow | 82% | 36% | 74% | n/a | 21% | n/a |
| GitHub Medium | 69% | 29% | 57% | 52% | 12% | n/a |
| Kubernetes | 91% | 57% | 76% | **7%** | 21% | n/a |
| Washington Post | 86% | 22% | 94% | 64% | 13% | n/a |
| GitHub Hard | 41% | **3%** | 39% | 28% | 9% | n/a |
| JSONSchemaStore | 30% | 9% | 38% | 33% | **6%** | n/a |

Read that again: on real-world schema corpora, **no engine gets above 41% on GitHub Hard, and the
best on JSONSchemaStore is 38%**. Gemini fell to **7%** on GitHub Easy. OpenAI Structured Outputs
managed **6%** on JSONSchemaStore. The headline "guaranteed valid JSON matching your schema" is
true only for the restricted schemas each engine actually accepts.

**Failure taxonomy (their Table 6)** **[PRIMARY]** — this is the load-bearing finding for us:

| Failure class | Guidance | Outlines | llama.cpp | XGrammar |
|---|---|---|---|---|
| Compilation errors (schema rejected) | 25 categories | 42 | 37 | — |
| **Over-constrained** (blocks valid instances) | 7 | 16 | 18 | — |
| **Under-constrained** (permits INVALID instances) | 1 | — | 7 | **38** |

**XGrammar had 38 under-constrained failure categories** — i.e. it accepted the schema, told the
caller it was enforcing it, and then emitted output that violates it. That is a *silent* failure of
the guarantee during ordinary full-document generation. **[PRIMARY]**

Keywords named as causing timeouts / trouble (Outlines analysis): **minItems, maxItems, enum,
array** constructs. **[PRIMARY]**

**Efficiency (their Table 2, llama.cpp backend)** **[PRIMARY]**:

| Metric | Guidance | llama.cpp | Outlines | LM only |
|---|---|---|---|---|
| Grammar compilation time | ~0.00 s | ~0.05 s | **3.5-8 s** | n/a |
| Time to first token | 0.2-0.5 s | 0.2-0.3 s | **3.6-8.4 s** | 0.1-0.2 s |
| Time per token | 6-10 ms | 27-29 ms | 30-47 ms | 15-17 ms |

Guidance/llguidance beats the unconstrained LM on per-token time because of **token
fast-forwarding** (when the grammar determines the next characters, emit them without a forward
pass). Outlines' compilation is **seconds**, dominating TTFT.

**Task quality (their Table 8)** **[PRIMARY]**: constrained decoding *improved* downstream accuracy
in their runs — Guidance +3.3% on Last Letter (50.7 -> 54.0), +3.3% on Shuffle Objects
(52.6 -> 55.9), **+3.7% on GSM8K (80.1 -> 83.8)**. They explicitly present this as contradicting the
"format restrictions hurt performance" claim. (See section 5 for the Tam et al. dispute.)

> **SCOPE REFRAME received mid-research (2026-09-07).** The delta is not necessarily a patch
> language the model writes. Likely architecture: LOCALISE a region -> PROJECT the sub-schema of S
> at that region -> GENERATE the fragment under ordinary constrained decoding against the projected
> sub-schema -> SPLICE and revalidate. Two motivating cases: (a) a Pydantic form where "change the
> answer to Q3" should regenerate only Q3's sub-model; (b) an Excel-like artifact where 10,000 rows
> are emitted 10 at a time. Added questions 7-11 below (sub-schema projection in practice; grammar
> caching across many small calls; compositionality of local validity to global validity;
> cross-fragment state; field-at-a-time generation). Items 1-6 stand; item 2 (keyword coverage) is
> now *more* central, because `required` / `uniqueItems` / `minItems` are exactly the keywords that
> break under fragment-wise generation.

### 2.1 OpenAI / Azure OpenAI Structured Outputs — the exact documented subset

Best primary source I could retrieve with the full table intact: **Microsoft Learn, "How to use
structured outputs with Azure OpenAI in Microsoft Foundry Models"**, page metadata says
`updated_at: 2026-08-24`.
https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs **[PRIMARY]**
(`platform.openai.com/docs/guides/structured-outputs` now 301-redirects to
`developers.openai.com/api/docs/guides/structured-outputs`, whose "supported schemas" section is
rendered behind collapsible JS and did not come back as text for me — see divergence note below.)

**Supported types (verbatim list):** String, Number, Boolean, Integer, Object, Array, Enum, anyOf.

**Root restriction (verbatim note): "Root objects can't be the `anyOf` type."** So the root must be
an object. **[PRIMARY]** — directly relevant to Q7: you cannot hand this API a bare scalar or a bare
array as the root of a projected sub-schema; you must wrap it in a single-property object.

**All fields must be required.** Optionality is emulated only via a union with null
(`"type": ["string","null"]`). **[PRIMARY]** So `required` is not *enforced by the decoder* so much
as *made vacuous by the API* — every property is required by construction. That is a very
significant point for our residue argument: OpenAI's answer to "how do we enforce `required`?" was
"make everything required and forbid optionality."

**`additionalProperties: false` is mandatory on every object.** **[PRIMARY]**

**Size limits (verbatim): "A schema can have up to 100 object properties total, with up to five
levels of nesting."** **[PRIMARY]**

**Key ordering:** output follows the order of properties in the supplied schema. **[PRIMARY]**

**Unsupported type-specific keywords (verbatim table):** **[PRIMARY]**

| Type | Unsupported keywords |
|---|---|
| String | `minLength`, `maxLength`, `pattern`, `format` |
| Number | `minimum`, `maximum`, `multipleOf` |
| Objects | `patternProperties`, `unevaluatedProperties`, `propertyNames`, `minProperties`, `maxProperties` |
| Arrays | `unevaluatedItems`, `contains`, `minContains`, `maxContains`, `minItems`, `maxItems`, `uniqueItems` |

Also absent from the supported-types list entirely, hence unsupported: **`oneOf`, `allOf`, `not`,
`if`/`then`/`else`, `dependentRequired`, `dependentSchemas`.** (Only `anyOf` is listed.)
**[INFERRED from the supported list being exhaustive.]**

**Supported:** `$defs`, `$ref`, and **recursive schemas** (both `"$ref": "#"` root recursion and
explicit `$defs` self-reference). **[PRIMARY]**

**Latency:** "The first request you make with any schema will have additional latency as our API
processes the schema, but subsequent requests with the same schema will not have additional
latency." — from OpenAI's own guide,
https://developers.openai.com/api/docs/guides/structured-outputs **[PRIMARY]**
This is an explicit statement that **grammar compilation is per-schema and cached server-side**, and
that a *novel* schema costs extra on first use. Load-bearing for Q3 and Q8: a schema you have used
before is free; a schema derived fresh from a document is not.

**Divergence to flag [SECONDHAND, needs verification]:** an OpenAI developer-community announcement
dated **21 May 2025** ("Structured Outputs gets nifty improvements",
https://community.openai.com/t/structured-outputs-gets-nifty-improvements/1266968) says OpenAI added
support for string length and format via **regex or formats like email**, **min/max ranges for
numbers**, and **min/max elements in arrays**. The post does not enumerate keywords. The Azure page
above (Aug 2026) still lists those as unsupported. So: **the OpenAI platform subset is probably now
larger than the Azure subset.** I could not extract the current OpenAI list verbatim because the
docs page hides it behind JS. **A human should re-check `developers.openai.com` directly.**
`uniqueItems`, `if/then/else`, `dependentRequired`, `propertyNames` were NOT mentioned in the
announcement and I have no evidence they were added.

### 2.2 llguidance / Guidance — the most complete open engine, and the most honest docs

Primary source: `guidance-ai/llguidance`, `docs/json_schema.md` and `README.md` (read raw from
GitHub, main branch). https://github.com/guidance-ai/llguidance **[PRIMARY]**

**Supported** (with their own per-keyword *percentage* support figures where given):
`type`, `const`, `enum`, `anyOf`, `oneOf` (**68%** — converted to `anyOf` only when provably
equivalent), `allOf` (**98%** — intersection of certain schemas unsupported), `$ref`
(**internal only**; external/remote `$ref` unsupported); arrays: `items`, `prefixItems`,
`minItems`, `maxItems`; objects: `properties`, `additionalProperties`, `patternProperties`
(**98%**, must be disjoint), **`required`**, `minProperties`/`maxProperties` (**90%**, limited);
strings: `minLength`, `maxLength`, `pattern` (**99%**, no lookarounds), `format` (**74%**, specific
formats only); numbers: `minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum`, `multipleOf`.

**Unsupported / ignored (verbatim list):** `not`; external/remote `$ref`; `propertyNames`;
**`dependentRequired`**; **`dependentSchemas`**; **`if`/`then`/`else`**; `contains`;
`minContains`/`maxContains`; **`uniqueItems`**; `unevaluatedProperties`; `unevaluatedItems`.

**Known departures from JSON Schema 2020-12 that they list themselves:**
1. **Property order is fixed to schema declaration order** (not arbitrary as JSON Schema permits).
2. String formats are enforced by default; unrecognised formats error.
3. **No unique-key enforcement** for `additionalProperties` / `patternProperties` keys.
4. `minProperties`/`maxProperties` only under restricted conditions.
5. Applicator precedence follows appearance order, violating keyword-independence semantics.
6. `allOf` intersection limits.

**This is the single most important structural observation in the whole audit** **[INFERRED]**:
llguidance can enforce `required` *only because it fixes property order*. Once the order of object
members is pinned to the schema's declaration order, "these keys must all appear" becomes a plain
sequence in a context-free grammar — no counting needed. The moment order is free, `required`
becomes a *permutation-with-required-subset* problem and the grammar blows up combinatorially. Every
engine that "supports required" does it by fixing order. `uniqueItems` has no equivalent trick and
**no engine supports it**.

**llguidance performance (README)** **[PRIMARY]**:
- ~**50 microseconds** CPU per token for a 128k tokenizer, with **negligible startup cost**.
- Full mask computation for a typical JSON schema ~**1.5 ms** (128k tokenizer) *without* the
  slicer optimisation; **average mask computation across JSON Schema Bench (2.5M tokens,
  10k schemas) is under 50 microseconds**.
- Tail: **<1% of masks exceed 1 ms; 0.001% exceed 10 ms** (and still under 30 ms).
- "With 16 cores and a 10 ms forward pass, llguidance can handle batch sizes up to 3200 without
  slowing down the model."
- Their characterisation of rivals: Outlines "pre-computes token masks for all automaton states...
  introducing significant startup cost and memory overhead"; **XGrammar pre-computation "often runs
  into seconds, and sometimes minutes."** **[PRIMARY, but this is a competitor's claim in a README
  — treat as advocacy, not measurement.]**
- Architecture: **Earley parser** over a **lexer built from derivatives of regular expressions**;
  mask computed by walking the **token trie**.

### 2.3 Google Gemini controlled generation

Primary: https://ai.google.dev/gemini-api/docs/structured-output **[PRIMARY]**, plus the Vertex/
Gemini Enterprise `Schema` reference https://docs.cloud.google.com/gemini-enterprise-agent-platform/reference/rest/v1/Schema

- The schema is a **subset of the OpenAPI 3.0 Schema Object**, not JSON Schema proper (the newer
  `responseJsonSchema` field is closer to JSON Schema).
- Supported per the docs: types `string, number, integer, boolean, object, array, null`;
  `title`, `description`; `properties`, `required`, `additionalProperties`; `enum`,
  `format` (date-time, date, time); `minimum`, `maximum`; `items`, `prefixItems`,
  **`minItems`, `maxItems`**; `$id`, `$defs`, `$ref`, `$anchor`; `anyOf`; **`oneOf` is accepted but
  interpreted the same as `anyOf`** (i.e. the exclusivity is silently dropped); plus the
  non-standard **`propertyOrdering`**.
- Recursion via `"$ref": "#"` is supported.
- **Root can be an object or an array.** **[PRIMARY]** — better than OpenAI for our purposes.
- Documented limitation: "**Very large or deeply nested schemas may be rejected**."
- No support documented for `uniqueItems`, `pattern`, `if`/`then`/`else`, `dependentRequired`,
  `allOf`, `not`, `const`, `multipleOf`, `minLength`/`maxLength`. **[PRIMARY, by absence]**
- **`oneOf` silently degraded to `anyOf` is a documented example of "under-constrained" behaviour in
  a production API**: you write an exclusive-choice schema, the engine enforces a weaker one, and
  nothing tells you.
- JSONSchemaBench measured Gemini at **86% on GlaiveAI but 7% on GitHub Easy** (Table 4 above) —
  the worst of the six engines.

### 2.4 llama.cpp GBNF + its JSON-Schema converter

Primary: `grammars/README.md` in ggml-org/llama.cpp (raw, master). **[PRIMARY]**

- GBNF = "GGML BNF", BNF extended with regex-like operators. Grammars are stateless and consume
  characters/tokens sequentially. The README does **not** state a formal expressiveness class.
- The bundled JSON-Schema-to-GBNF converter supports: `type`, `properties`, `required`, `items`,
  `minItems`, `maxItems`, `minimum`/`exclusiveMinimum`/`maximum`/`exclusiveMaximum`
  (**integers only**), `minLength`, `maxLength`, `pattern` (**must be anchored `^...$`**),
  `additionalProperties`, `$ref` (with limits), some `format`s.
- **Not supported / broken:** `uniqueItems`, `contains`, `minContains`, `patternProperties`,
  `if`/`then`/`else`, `dependentSchemas`, `not`, `prefixItems`, nested and remote `$ref` (C++
  version), `anyOf`/`oneOf` **cannot be mixed with `properties`**, float-typed min/max.
- Default `additionalProperties: false` "produces faster grammars + reduces hallucinations".
- Explicit performance warning: "Grammars currently have performance gotchas" — writing repetition
  as `x? x? x?` N times is pathological; use `x{0,N}`. This is the **counting/cardinality blow-up**
  showing up as an engineering warning in a production README. **[PRIMARY]**

### 2.5 vLLM — and the best available evidence of *silent* under-constraining

Primary: `vllm/v1/structured_output/backend_xgrammar.py`, main branch. **[PRIMARY]**

vLLM ships a function `has_xgrammar_unsupported_json_features()` that walks a schema and rejects
(so the request can fall back to another backend) on:
- numbers: **`multipleOf`**
- arrays: **`uniqueItems`, `contains`, `minContains`, `maxContains`**
- strings: `format` values outside {email, date, time, date-time, duration, ipv4, ipv6, hostname,
  uuid, uri, uri-reference, uri-template, json-pointer, relative-json-pointer}
- strings: **any combination of `pattern`/`format` together with `minLength`/`maxLength`**
- objects: **`patternProperties`, `propertyNames`**

The source comment for that last string case says, in effect: **xgrammar compiles the
`pattern`/`format` side and *silently drops* `minLength`/`maxLength`** — producing output that
violates the schema with no error. vLLM has to hand-maintain a denylist to stop that happening.
**[PRIMARY — this is direct evidence that "constrained decoding guarantees your schema" is false in
a widely deployed engine, during ordinary full-document generation.]**

Also from the source: `GrammarCompiler(cache_enabled=True, cache_limit_bytes=VLLM_XGRAMMAR_CACHE_MB,
max_threads=8)` — so **vLLM does cache compiled grammars in-process**, size-capped by an env var.
**[PRIMARY — directly answers part of Q8.]**

Backends offered: `xgrammar`, `guidance` (llguidance), `outlines`, `lm-format-enforcer`, and
`auto` (default), which picks per request. Docs at
https://docs.vllm.ai/en/latest/features/structured_outputs/ do **not** document the fallback rules,
the unsupported-feature lists, or the cache — you have to read the source. **[PRIMARY, negative]**

vLLM engineering blog, "Structured Decoding in vLLM: a gentle introduction" (14 Jan 2025),
https://vllm.ai/blog/2025-01-14-struct-decode-intro **[PRIMARY]**:
- In V0, guided decoding is a **logit processor on the critical sampling path**, so it **blocks
  other requests in the batch**. With the Outlines backend, **FSM compilation happens per request,
  synchronously, blocking the whole batch** — "compiling FSM is proven to be a relatively expensive
  task, making it a significant contributor to the increased TTFT."
- V1 moves it to the scheduler so non-structured requests are not blocked.
- XGrammar moves compilation out of Python into C with `pthread`.
- Chart claim: XGrammar gives **up to 5x improvement in TPOT under load** vs Outlines (chart, no
  table of numbers).

Red Hat developer article (3 Jun 2025),
https://developers.redhat.com/articles/2025/06/03/structured-outputs-vllm-guiding-ai-responses
**[PRIMARY, but vendor blog]**: qualitative guidance — **XGrammar "caches well, excels at long
generations... repeated schemas"; Guidance is for "multi-tenant, dynamic schemas" and fast TTFT.**
That maps exactly onto our Q8: if sub-grammars are reused, use XGrammar; if every request has a
fresh grammar, use llguidance.

### 2.6 SGLang

Primary: https://docs.sglang.io/advanced_features/structured_outputs.html **[PRIMARY]**
- Backends: **XGrammar (default)**, Outlines, llguidance. XGrammar handles JSON schema, regex and
  EBNF.
- **"Only one constraint parameter (`json_schema`, `regex`, or `ebnf`) can be specified for a
  request."** — you cannot compose two constraints in one call. Relevant to Q9: no built-in way to
  layer a cross-fragment constraint on top of a schema constraint.
- **Negative:** the SGLang docs list **no** unsupported JSON Schema features, say nothing about
  whether a bare array/scalar root is allowed, and say nothing about grammar caching. **[PRIMARY,
  negative]**
- SGLang's own earlier LMSYS blog, "Fast JSON Decoding for Local LLMs with Compressed Finite State
  Machine" (5 Feb 2024), https://www.lmsys.org/blog/2024-02-05-compressed-fsm/ describes
  **jump-forward decoding**: when the FSM has a single valid continuation, emit those tokens without
  a forward pass. Claimed ~3x faster JSON decoding. **[SECONDHAND — I read the search summary, not
  the blog itself; the 3x figure should be re-verified.]**

### 2.7 Independent benchmark: SqueezeBits, "Guided Decoding Performance on vLLM and SGLang"

https://blog.squeezebits.com/guided-decoding-performance-vllm-sglang **[PRIMARY, but a company
blog with charts and no numeric tables]**

Findings that bear directly on our Q8 (caching across many small calls):
- **On repeated schemas, XGrammar beats llguidance on throughput and TPOT** in both frameworks.
- **On dynamic (per-request unique) schemas, llguidance consistently beats XGrammar**, because
  **"XGrammar's caching strategy is neutralized"** when every request has a fresh schema.
- vLLM shows a significant throughput drop with guided decoding at batch size >= 8; SGLang loses
  much less by overlapping grammar work with GPU work.
- On complex schemas XGrammar shows "erratic behavior with frequent sharp drops ... severe CPU
  bottlenecks during mask generation."
- **No numeric tables** — charts only. **[negative on numbers]**

### 2.8 Anthropic Claude — Structured Outputs / strict tool use

Primary: https://platform.claude.com/docs/en/build-with-claude/structured-outputs **[PRIMARY]**
Two modes: `output_format` (JSON output) and `strict: true` on tool definitions (strict tool use).

**Supported:** types object/array/string/integer/number/boolean/null; `enum` (scalars only, no
complex types); `const`; `anyOf`; `allOf` (**`allOf` with `$ref` not supported**); `$ref`, `$defs`,
`definitions` (**internal only**); `default`; `required`; `additionalProperties` (**must be
`false`**); string `format` in {date-time, time, date, duration, email, hostname, uri, ipv4, ipv6,
uuid}; **`minItems` — only the values 0 and 1**.

**Unsupported (verbatim-ish list):** **recursive schemas**; complex types in `enum`; external `$ref`;
`minimum`, `maximum`, `multipleOf`; `minLength`, `maxLength`; **`maxItems`**, **`uniqueItems`**,
`minItems` other than 0/1; **`pattern`**; **`oneOf`**, **`not`**; **`if`/`then`/`else`**;
**`dependentRequired`**; **`propertyNames`**, **`patternProperties`**.

**Root must be an object.** Bare arrays and scalars are not allowed at root. All properties become
required; optionality is simulated with a nullable `anyOf`. **[PRIMARY]**

**Caching, stated explicitly and precisely — the best public statement of grammar-cache semantics
from any vendor** **[PRIMARY]**:
- "The first time you use a specific schema, there is additional latency while the grammar compiles."
- "**Compiled grammars are cached for 24 hours from last use**, making subsequent requests much
  faster."
- The cache is invalidated if you change **the JSON schema structure**, or **the set of tools in the
  request**. Changing only `name`/`description` does *not* invalidate.

Two direct consequences for our design **[INFERRED]**:
1. **A grammar derived from document D is a novel schema on every call and will never hit this
   cache.** Under the *original* patch framing that is a hard cost.
2. **A grammar projected from a fixed S at a fixed path is the same grammar every time and will hit
   the cache.** Under the *reframed* architecture it is free after the first use. The reframe turns
   the caching objection from fatal to nil.

Also: Anthropic is notably *stricter* than OpenAI here — no recursion, no `oneOf`, `minItems` only
0/1. So the "supported subset" is not converging across vendors; it is diverging.

### 2.9 Summary matrix — which whole-document keywords are enforced at decode time, anywhere

`Y` = enforced, `~` = partial/conditional, `N` = not enforced (rejected at compile time or silently
dropped). Compiled from the primary sources above.

| Keyword | Outlines | llguidance | XGrammar | llama.cpp GBNF | OpenAI SO | Gemini | Anthropic |
|---|---|---|---|---|---|---|---|
| `required` | ~ (order-fixed) | Y (order-fixed) | ~ | Y (order-fixed) | Y (all required, forced) | Y | Y (all required, forced) |
| `minItems`/`maxItems` | ~ (timeouts) | Y | ~ (repetition compression in XG-2) | Y (int only) | N (Azure list) / maybe Y since 5/2025 | Y | `minItems` 0/1 only; `maxItems` **N** |
| **`uniqueItems`** | **N** | **N** | **N** (vLLM denylists it) | **N** | **N** | **N** | **N** |
| `minimum`/`maximum`/`multipleOf` | ~ | Y | `multipleOf` **N** | int only | N (Azure) | min/max Y | **N** |
| `pattern` | Y | Y (no lookaround) | ~ (dropped w/ length) | Y (anchored only) | N (Azure) | **N** | **N** |
| `minLength`/`maxLength` | ~ | Y | **silently dropped when combined with pattern/format** | Y | N (Azure) | **N** | **N** |
| `oneOf` | ~ | ~ (68%) | ~ | mixing w/ properties broken | **N** | **accepted but treated as `anyOf`** | **N** |
| `anyOf` | Y | Y | Y | ~ | Y (not at root) | Y | Y |
| `allOf` | ~ | ~ (98%) | ~ | N | **N** | **N** | ~ (not with `$ref`) |
| `not` | **N** | **N** | **N** | **N** | **N** | **N** | **N** |
| `$ref` + recursion | ~ | internal only | ~ | broken for nested/remote | Y | Y | **N (no recursion)** |
| `additionalProperties` | Y | Y | Y | Y | must be false | Y | must be false |
| `propertyNames` | ~ | **N** | **N** (vLLM denylists) | **N** | **N** | **N** | **N** |
| `patternProperties` | ~ | ~ (disjoint only) | **N** (vLLM denylists) | **N** | **N** | **N** | **N** |
| **`dependentRequired`/`dependentSchemas`** | **N** | **N** | **N** | **N** | **N** | **N** | **N** |
| **`if`/`then`/`else`** | **N** | **N** | **N** | **N** | **N** | **N** | **N** |
| `const`/`enum` | Y | Y | Y | ~ | Y | Y (enum) | Y (scalars only) |
| `contains`/`min/maxContains` | N | **N** | **N** (vLLM denylists) | **N** | **N** | **N** | **N** |

**THE HEADLINE FINDING FOR OUR ARGUMENT.** Every keyword in the "residue" we worried about —
`uniqueItems`, `if/then/else`, `dependentRequired`, `dependentSchemas`, `not`, `propertyNames`,
`contains` — is **enforced by NO engine, in NO product, during ORDINARY full-document generation.**
`required` is only enforced because engines fix property order, which is itself a departure from
JSON Schema semantics. `minItems`/`maxItems` are the ones most engines *do* handle, and they are
also the ones flagged as causing timeouts (Outlines) and needing a special "repetition compression"
trick (XGrammar-2).

So: **the whole-document residue is not a new cost of going delta. It is the pre-existing,
universally-unenforced remainder of today's structured output.** Going fragment-wise adds only
`minItems`/`maxItems` on a containing array and `required` across a fragment boundary to that list.
Everything else was already yours to validate in ordinary code.

---

## 5. Distribution distortion (taken before section 4 because the papers overlap)

### 5.1 Park, Wang, Berg-Kirkpatrick, Polikarpova, D'Antoni — "Grammar-Aligned Decoding" (ASAp), NeurIPS 2024

- arXiv:2405.21047; NeurIPS 2024 proceedings
  https://proceedings.neurips.cc/paper_files/paper/2024/hash/2bdc2267c3d7d01523e2e17ac0a754f3-Abstract-Conference.html
  Full text read at https://arxiv.org/html/2405.21047v3 **[PRIMARY]**
  Code: https://github.com/ebmoon/transformers-GAD

**This paper contains the exact theoretical result our question 5 needs.**

- **The correct target distribution** is the LLM conditioned on grammaticality:
  `Q(w) = 1[w in L(G)] * P(w) / sum_{w'} 1[w' in L(G)] * P(w')`.
- Its exact left-to-right factorisation requires the **expected future grammaticality (EFG)**:
  `Q(w_i | w_<i) proportional to P(w_i | w_<i) * c(w_1..i)`, where `c` is the probability that the
  prefix can be completed *by this model* into a grammatical string.
- **Grammar-constrained decoding replaces `c` with a binary indicator** (can this prefix be
  completed *at all*?). That substitution is precisely the distortion. **[PRIMARY]**
- **Their worked Example 3** — the cleanest illustration I found anywhere. A binary-string grammar
  where both "0" and "1" are locally legal so GCD gives each 0.5, but only `00000` is grammatical
  after "0", a continuation the LLM assigns ~`0.45^5 ~ 1e-8`. GCD *traps* the sampler in the
  low-probability region: the final token comes out "1" **30%** of the time versus the LLM's
  **90%**. **[PRIMARY]**
- **Measured distortion, sum of squared differences between GCD expectations and true
  expectations** **[PRIMARY]**: SLIA benchmarks — **GCD 2.259 vs ASAp (2000 samples) 1.242**;
  INV-BV — **GCD 1.852 vs ASAp 0.802**.
- **Theorem 2**: ASAp's overapproximation of EFG converges to the exact EFG as sample count
  `m -> infinity`, giving asymptotically exact sampling from Q. So GAD is solved **only in the
  limit**, at the cost of many samples. Convergence varies wildly: some benchmarks near-zero KL by
  iteration 75, others "very slow" after 2,000 iterations. **Wall-clock is not reported.**
  **[PRIMARY]**
- **On exact EFG being intractable**: "the model's contribution generally does not factorize: ...
  the final conditional probability is a global potential function, defined by a non-linear neural
  network touching every variable." So there is no dynamic program for `c`. **[PRIMARY]**

**Does distortion scale with how restrictive the grammar is?** The paper does **not** state a
theorem to that effect and does **not** run a restrictiveness sweep. **[PRIMARY, negative — I looked
for exactly this and it is not there.]** But the *mechanism* is unambiguous, and it does imply the
direction **[INFERRED, mine]**: the error is `|1[completable] - c(prefix)|`. When the grammar is
loose, `c` is near 1 for almost every live prefix and the indicator is a good approximation. The
tighter the grammar, the more live-but-improbable prefixes exist, the further `c` falls below 1, and
the worse the substitution gets. **The distortion is largest exactly where the constraint is
tightest and where the model's own mass sits outside the allowed set.** A patch/delta grammar is
both very tight *and* far from pretraining mass, which is the worst quadrant. A *projected
sub-schema* grammar is not: it is the same shape of grammar the model already handles well, just
smaller, and the fragment's content distribution is ordinary JSON. **This is the strongest
theoretical argument I found for the reframed architecture over the patch-language architecture.**

### 5.2 Tam et al., "Let Me Speak Freely?" (EMNLP 2024 Industry Track) — and the dispute about it

- Zhi Rui Tam et al. (Appier), arXiv:2408.02442, https://aclanthology.org/2024.emnlp-industry.91/
  Full text read at https://arxiv.org/html/2408.02442v1 **[PRIMARY]**
- Their three conditions, ordered by strictness: **JSON-mode (strictest) > Format-Restricting
  Instructions (FRI) > NL-to-Format (loosest)**. Their headline claim: **"stricter format
  constraints generally lead to greater performance degradation in reasoning tasks."** **[PRIMARY]**
  This is the closest thing in the literature to a direct answer to our Q5 ("does distortion scale
  with restrictiveness?").
- **GSM8K, Table 1** (text vs JSON vs XML vs YAML) **[PRIMARY]**:
  Gemini 1.5 Flash 89.33 / 89.21 / 88.20 / 87.42; **Claude 3 Haiku 86.51 / 23.44 / 79.76 / 80.63**;
  **GPT-3.5 Turbo 75.99 / 49.25 / 45.06 / 73.85**; LLaMA 3 8B 75.13 / 48.90 / 56.74 / 46.08.
- **Last Letter Concatenation, Table 6** (mean, with SD over prompt variations in brackets):
  Gemini 65.45 (3.1) / JSON **77.02** (7.3); GPT-3.5 56.74 (7.1) / JSON 25.20 (29.1);
  Claude 3 Haiku 57.67 (21.1) / JSON 56.74 (16.7); LLaMA 3 8B 70.07 (5.3) / JSON 28.00 (12.2).
- **Shuffled Objects, Table 6**: Gemini text 58.21 / JSON **65.07** (JSON *better*); GPT-3.5 20.37 /
  20.93; Claude 3 Haiku 36.62 / **49.33** (JSON better); LLaMA 3 8B 27.01 / 15.72.
- **The direction is NOT consistent.** JSON helps Gemini and Claude on some tasks and destroys
  GPT-3.5 and LLaMA on others. The bracketed standard deviations across prompt variations are
  enormous — **Claude 3 Haiku JSON GSM8K 23.44 with SD 22.8**; GPT-3.5 XML 45.06 with SD 19.9;
  GPT-3.5 Last Letter JSON SD **29.1**. **[PRIMARY]** The prompt-to-prompt variance is often larger
  than the format effect they are claiming.
- Implementation: they cite Willard & Louf (2023) and Koo et al. (2024) and used HuggingFace
  **Text-Generation-Inference**; a large part of the study is API "JSON mode" on closed models,
  which is **not** grammar-constrained decoding at all. **[PRIMARY]** So the paper conflates
  three different things under "format restriction".

**The rebuttal:** .txt (dottxt, the Outlines company), "Say What You Mean: A Response to 'Let Me
Speak Freely'", https://blog.dottxt.ai/say-what-you-mean.html **[PRIMARY, but a vendor blog, not
peer-reviewed]**; discussion thread https://github.com/dottxt-ai/outlines/discussions/1117
- Their charge: Tam et al. used **different prompts for each condition**. The unstructured prompt
  contained an explicit output instruction ("The final answer is <answer>"); the structured prompt
  **omitted the schema and the tool definitions entirely**.
- Their re-run with matched prompting: **GSM8K unstructured 0.77 vs structured 0.78; Last Letter
  0.73 vs 0.77; Shuffle Object 0.41 vs 0.44** — structured wins all three. **[PRIMARY, vendor]**
- Their headline reversal: Tam et al. report **<10%** on Last Letter under JSON mode; .txt get
  **77%** on the same task with proper structured generation.
- They frame structured generation as "running our response parser as a generator."

**Third-party adjudication:** JSONSchemaBench (section 2.0) independently measured **+3.3 to +3.7
points from constrained decoding** on Last Letter, Shuffle Objects and GSM8K. **[PRIMARY, academic,
neutral]** That is a peer-reviewed academic result agreeing with the vendor rebuttal.

**My reading of the dispute [JUDGEMENT]:** Tam et al. measured *format-and-prompt*, not
*constraint*. The reproducible finding is that **switching output format changes accuracy a lot and
unpredictably**, and that **prompt/schema mismatch is the dominant term**. There is no clean
published evidence that grammar-constrained decoding per se degrades reasoning when the prompt is
matched. The clean theoretical statement of harm is DOMINO's (misalignment, -10.7 points, fixable)
and GAD's (EFG substitution, unfixable except in the limit).

**What NOBODY has measured, and we need:** a controlled sweep in which the *same* task is generated
under grammars of monotonically increasing restrictiveness, with distortion (KL to the unconstrained
conditional) and task accuracy plotted against a restrictiveness measure. I searched for this with
queries on "distortion vs grammar restrictiveness", "how constraint tightness affects constrained
decoding quality", "ablation grammar strictness constrained decoding" and found **nothing**.
**[NEGATIVE FINDING — this is an open, cheap, publishable experiment.]**

---

## 4. Theory limits — what token masking can and cannot enforce

### 4.1 The lookahead problem, stated properly

Masking is sound-and-complete only if the engine can answer, at every step: **"is this prefix
extendable to a string in the language?"** Complexity by class **[INFERRED from standard formal
language theory, with engine-level corroboration cited below]**:

| Constraint class | Prefix-extendability | Engine reality |
|---|---|---|
| Regular | O(1) after DFA construction (non-dead state) | Outlines' index |
| Deterministic CF (LALR(1)) | O(1) amortised per token via viable-prefix parsing | Outlines CFG mode, llama.cpp |
| General CF | poly (Earley, O(n^3) worst case) | llguidance, XGrammar |
| CF + counting/uniqueness | **not context-free**; needs unbounded state | **no engine does it** |
| Model-conditioned ("can *this LLM* complete it plausibly") | **#P-hard / NP-hard** — see 4.2 | ASAp approximates in the limit |

The "Mitigating Bias in Locally Constrained Decoding via Tractable Proposals" paper
(Dang, Song, H. Zhang, Zhao, Van den Broeck, Ermon; **ICML 2026**; arXiv:2606.01926;
https://starai.cs.ucla.edu/papers/DangICML26.pdf) states the CFG lookahead obstruction cleanly:
for CFG constraints, lookahead is hard because "the natural operational model is a pushdown
automaton (PDA) with an unbounded stack, yielding an infinite configuration space that makes direct
finite-state value computation ... inapplicable." **[SECONDHAND — from a search-result excerpt of the
paper; I did not fetch the PDF. Flagged.]**
Their fix: constraints given as **finite automata** can be **tensorised and run on the GPU**, giving
tractable SMC proposals that avoid "the global intractability and greedy distortion issues with
locally masked approaches." Benchmarks: **xLAM** (function-calling, JSON/Python-like syntax),
CommonGen, Spider.

### 4.2 The real hardness result — conditioning an autoregressive model on a global constraint

**"Hidden Biases in Conditioning Autoregressive Models"**, arXiv:2604.07855,
https://arxiv.org/html/2604.07855 **[PRIMARY]**:
- **Theorem 1: exact sentence-level MAP decoding over succinctly represented autoregressive models
  is NP-hard.** Hardness persists under unary position-wise constraints and metrical constraints.
- **Theorem 2: exact computation of the normalisation constant Z_L(theta) is #P-hard** — and this
  holds for **regular** constraints as simple as "**exactly length L and ending in eos**".
- MAP-THRESHOLD is NP-complete.
- Their characterisation: **prefix conditioning is free** (just keep generating), but **global
  constraints require continuation masses over exponentially many suffixes**, and general
  autoregressive models have no "bounded sufficient statistic" for those quantities.
- Consequence they draw: any approximate constrained procedure produces samples "distorted relative
  to the true constrained distribution, with no generic guarantee of complete coverage of the
  admissible solution space or of correct conditional probabilities over valid completions".

Corroborating earlier work: Zhang, Dang, Peng, Van den Broeck, **"Tractable Control for
Autoregressive Language Generation" (GeLaTo), ICML 2023**, PMLR v202,
https://proceedings.mlr.press/v202/zhang23g.html — "sampling from the conditional distribution
(text | alpha) is intractable for even the simplest lexical constraints alpha"; their answer is to
distil a **tractable probabilistic model (an HMM)** that *can* compute P(text | alpha) exactly and
use it to steer GPT-2. **[SECONDHAND — the UCLA PDF returned HTTP 403; I have the abstract-level
statement from multiple search summaries plus the PMLR listing. Flagged; a human should pull the
PDF.]**

**So there are two separate hardness stories and they must not be conflated** **[JUDGEMENT]**:
1. **Syntactic**: can this prefix be completed to *some* legal string? Cheap for regular and CF,
   impossible-as-stated for counting/uniqueness constraints.
2. **Probabilistic**: what is the *probability* the model completes it legally? #P-hard even for
   trivially regular constraints. This is the GAD/EFG problem, and **no production engine even
   attempts it** — they all use the binary indicator.

Our delta/fragment proposal only ever touches (1). We inherit (2) exactly as everyone else does.

### 4.3 Sound vs complete masking — the vocabulary that already exists

- **DOMINO's "minimally invasive"** (Def. 2.1, section 1.2) is the completeness side: the mask must
  not remove any output the unconstrained model could have produced. Naive masking is *not*
  minimally invasive because of subword misalignment, costing 10.7 GSM8K points.
- **SynCode** (Ugare, Suresh, Zhang, Singh, Misailovic — TMLR 2025; arXiv:2403.01632;
  https://arxiv.org/abs/2403.01632) explicitly claims both: **"provably sound — retains all
  syntactically valid tokens — and complete under specific conditions — rejecting every
  syntactically invalid token at every generation step"**. Mechanism: an offline **DFA mask store**
  built from the language's DFA plus an **incremental parser** over the partial output.
  **[SECONDHAND — abstract-level, from search results and the Illinois Experts listing; I did not
  fetch the full paper.]** The phrase "complete **under specific conditions**" is the tell: exact
  completeness is not free.
- **JSONSchemaBench's over-constrained / under-constrained failure counts (Table 6, section 2.0)**
  are the empirical version of the same distinction, and they show that in practice engines fail on
  **both** sides.

### 4.4 The counting/uniqueness constraints, specifically

- **uniqueItems over an unbounded array is not context-free.** No CFG-based masker can enforce it.
  **BUT** — and this matters enormously for the Excel case — **"the next value must differ from
  these k already-emitted values" IS regular**: it is the complement of a finite set of strings,
  recognised by a trie / Aho-Corasick automaton of size O(total length of the k values). So
  *uniqueness against a known finite set is decidable by exactly the machinery these engines already
  have.* What is not expressible is uniqueness among values *not yet chosen*. **[INFERRED, mine — I
  found no paper stating this; see section 10.]**
- **minItems/maxItems with concrete bounds are regular** but cost automaton states linear in the
  bound. This is why llama.cpp's README warns against writing `x? x? x?...` and why XGrammar-2
  needed "repetition compression" (99.6x, their Table 4).
- **required with unordered object members** is a permutation constraint: k! orderings. Every engine
  dodges it by **fixing property order** to schema-declaration order (llguidance says so explicitly;
  OpenAI/Azure documents "Structured outputs follow the same order as the provided schema"). Once
  order is fixed, `required` is a plain sequence and needs no counting at all.
- **if/then/else, dependentRequired, dependentSchemas** are cross-field dependencies. They are
  expressible in a CFG **only** if the discriminating field is emitted *before* the dependent ones —
  i.e. only if property order is fixed *and* the discriminator comes first. That is exactly
  XGrammar-2's "intra-request dynamism". No engine implements it for JSON Schema.

### 4.5 Related older theory worth knowing: the CP "GRAMMAR constraint" literature

There is a whole prior literature in constraint programming on exactly "grammar constraint plus
other constraints": e.g. Katsirelos, Narodytska, Walsh, **"Decompositions of Grammar Constraints"**
(arXiv:0903.0470), and **"Propagating Regular Counting Constraints"** (arXiv:1309.7145). Search
results surfaced a relevant hardness statement: **"testing disentailment of the constraint is as
hard as unrestricted CFG parsing"**, and that faster algorithms are blocked by CFG-parsing lower
bounds. **[SECONDHAND — the arXiv abstract page gave no technical content and I did not fetch the
PDFs. Flagged as a lead worth following: this literature has 15+ years of results on propagating a
grammar constraint jointly with ALLDIFFERENT (= uniqueItems) and the Global Cardinality Constraint
(= minItems/maxItems), which is precisely our residue, and the constrained-decoding literature
appears not to cite it at all.]**

---

## 6. Dynamic / state-conditioned grammars — prior work DOES exist, and more than expected

I expected this to be the big negative finding. It is not. **Grammars built at request time from
external data are an established, published, and now productionised technique.** The negative
finding is narrower and sharper: see 6.5.

### 6.1 GENRE — constrained beam search over a trie built from a knowledge base (2021)

- Nicola De Cao, Gautier Izacard, Sebastian Riedel, Fabio Petroni, **"Autoregressive Entity
  Retrieval", ICLR 2021**. https://github.com/facebookresearch/GENRE
  Follow-up: **mGENRE**, "Multilingual Autoregressive Entity Linking", TACL 2022,
  https://direct.mit.edu/tacl/article/doi/10.1162/tacl_a_00460/110051/
  **[SECONDHAND — I read the GENRE README and multiple paper summaries, not the ICLR paper.]**
- Mechanism: build a **prefix tree (trie) over the tokenised names of every entity in the knowledge
  base** (Wikipedia titles), then run **constrained beam search** against it, so the model can only
  emit a string that is an existing KB identifier.
- **This is state-conditioned constrained decoding, published in 2021.** The "state" is a knowledge
  base of ~6M Wikipedia titles. The constraint set is *external data*, not a static schema. It is
  precisely the mechanism our `trie(valid JSON Pointers into D)` idea proposes, five years earlier
  and in a different application.
- Downstream line of work: **GenIE** (generative information extraction, arXiv:2112.08340),
  **WebIE**, **Re3val**, **Fusion Entity Decoding** (NAACL 2024) — all trie-constrained generation
  over a live identifier set.

### 6.2 Trie Automata for Constrained Decoding over Large Finite Sets (2026) — the direct hit

- arXiv:2608.12574, https://arxiv.org/html/2608.12574 **[PRIMARY]**
- Names the exact problem: the **"cardinality wall"** — general-purpose constrained-decoding engines
  become impractically slow once a finite-set constraint exceeds ~1,000 items, because they apply
  uniform FSM compilation regardless of the constraint's shape.
- The finite sets they target come from **runtime/external sources**: tool registries
  (500-5,000+ APIs in agentic workflows), **ICD-10-CM medical codes (74,719 codes)**, product
  taxonomies (1,500+), KB entity linking (tens of thousands). They note these sets **change
  per-query in RAG scenarios, preventing amortisation of compilation costs** — which is our exact
  worry, named and addressed.
- **Compilation cost: O((N_chars + V) * l)** where N_chars is total characters in the enum set,
  V the vocabulary, l the max token length in characters. Empirically **30-67 ms for Qwen3-8B from
  K=10 to K=10,000; 67 ms at K=100,000; sub-100 ms up to K=10,000.**
- Crucially: **the dominant cost is tokenizer-dependent, not per-item**, so the Aho-Corasick
  automaton "can be built once per tokenizer and reused across all enum schemas." **[PRIMARY]**
- **Per-token masking: 0.65 microseconds** (effectively constant), vs **XGrammar 5.8 us (9x
  slower)** and **llguidance 73-141 us (110-215x slower)**.
- Their comparison table: compile at K=1,000 — **trie 33 ms, XGrammar 75 ms, llguidance 3 ms**;
  per-step mask — trie 0.65 us, XGrammar 5.8 us, llguidance 85-141 us; vLLM throughput at batch 256
  — **trie 219 req/s vs XGrammar 7.5 req/s** (29x end-to-end).
- They explicitly bless per-request construction: "For dynamic enum constraints (e.g.
  retrieval-augmented tool selection where the valid set changes per query), the trie's 33-40 ms
  compilation is fast enough to run on-the-fly without impacting serving latency, whereas
  XGrammar's 75-239 ms compilation at K>=1,000 adds perceptible delay." **[PRIMARY]**

**This is the single most useful engineering result for the original delta idea.** A trie over every
JSON Pointer in a large document is *exactly* a large finite string set. The measured answer to "how
big before it hurts?" is: **100,000 pointers compiles in 67 ms and masks at 0.65 us/token.** The
"delta grammar cannot be precompiled" objection is therefore **quantitatively survivable** even in
the original patch framing, and under the reframing it barely arises.

### 6.3 XGrammar-2 — dynamic tool catalogues in production (see 1.4)

Already covered above: per-request grammars assembled from a live tool set, JIT compilation
(~10 ms vs >1000 ms), cross-grammar caching of shared substructures, and *intra-request* grammar
switching driven by the model's own earlier output. ACM CAIS 2026.

### 6.4 Picard — incremental parsing against a live database schema (2021)

- Torsten Scholak, Nathan Schucher, Dzmitry Bahdanau, **"PICARD: Parsing Incrementally for
  Constrained Auto-Regressive Decoding from Language Models", EMNLP 2021**, arXiv:2109.05093.
  **[SECONDHAND — background knowledge plus search corroboration; I did not fetch the paper in this
  session. A human should confirm the specifics below.]**
- Picard rejects beam hypotheses at each step using an **incremental SQL parser that is
  parameterised by the actual database schema for the current question** — table and column names
  come from the live DB, so the "grammar" is different for every input. Three checking modes of
  increasing strictness: lexical, grammatical, and **SQL-schema-aware validity** (does this column
  exist in this table?).
- **This is state-conditioned constrained decoding against a live data instance, from 2021**, and it
  goes beyond a name-trie: it enforces *relational* facts (column belongs to table) that are not
  properties of a static grammar.

### 6.5 The actual negative finding — what nobody has done

I ran targeted searches for each of the following and found **no** prior work:

- **"constrained decoding conditioned on a document instance"** / "grammar derived from the current
  document" / "instance-conditioned grammar" — nothing. All the dynamic-grammar work above
  conditions on a *catalogue of names* (entities, tools, codes, columns), never on the *structure of
  a specific document being edited*.
- **"constrained decoding for JSON Patch / RFC 6902 / JSON Merge Patch"** — nothing.
- **Constrained decoding that carries state across separate generation calls** (a running
  used-value set for uniqueness, a running count for cardinality) — nothing. See section 10.
- **Compositional guarantees**: "if a fragment validates against a projected sub-schema and is
  spliced into a valid document, is the result valid?" — nothing. See section 9.

So the honest statement is: **state-conditioned constrained decoding is solved and productionised
for the case where the state is a flat set of legal strings. It is unstudied for the case where the
state is a structured document, and completely unstudied across call boundaries.**

---

## 2 (continued). Audit addenda — Outlines in detail, and two corrections

### 2.10 Outlines / outlines-core — read from the source

Primary: `dottxt-ai/outlines-core`, `src/json_schema/parsing.rs`, main branch (read raw).
https://github.com/dottxt-ai/outlines-core **[PRIMARY]**

Architecture: Outlines compiles a JSON Schema **to a regular expression**, then that regex to a DFA,
then builds an `Index` mapping (state -> allowed token set) over the whole vocabulary. Everything it
cannot express as a regex is, structurally, out of reach.

**Handled in the parser:** `type` (incl. type arrays), `properties`, `required`, `allOf`
(concatenation of regexes), `anyOf` and `oneOf` (both compiled to plain alternation `|`), `$ref`
(**local only**), `const`, `enum`, `prefixItems`, `items`, `minItems`, `maxItems`,
`minProperties`, `maxProperties`, `additionalProperties`, `pattern` (strips a leading `^` and
trailing `$`), `minLength`, `maxLength`, `format`, plus **non-standard** numeric-shape keywords
`minDigitsInteger` / `maxDigitsInteger` / `minDigitsFraction` / `maxDigitsFraction` /
`minDigitsExponent` / `maxDigitsExponent`.

**Explicitly errors on:**
- **`minimum`, `maximum`, `exclusiveMinimum`, `exclusiveMaximum` -> error
  `UnsupportedNumericBound`.** Outlines cannot enforce numeric ranges at all; it offers digit-count
  bounds instead. **[PRIMARY — this surprised me and is worth flagging: the most-cited constrained
  decoding library does not support `minimum`/`maximum`.]**
- External `$ref` -> `ExternalReferencesNotSupported`.
- **Recursion is capped at depth 3 (configurable) "to prevent exponential regex bloat".** So
  recursive schemas are *silently truncated*, not rejected: an instance deeper than 3 is
  unreachable. **[PRIMARY]** Separately, GitHub issue #330 reports `NotImplementedError` for
  recursive schemas with optional self-references, and `RecursionError` for recursion inside lists.

**Never mentioned in the parser, hence unsupported:** `not`, `if`/`then`/`else`,
`dependentRequired`, `dependentSchemas`, **`uniqueItems`**, `propertyNames`, `patternProperties`,
`contains`/`minContains`/`maxContains`, `unevaluatedProperties`/`unevaluatedItems`,
`multipleOf`. **[PRIMARY by absence]**

**`oneOf` is compiled to the same alternation as `anyOf`** — so the *exclusivity* of `oneOf` is
silently dropped, exactly as in Gemini. **[PRIMARY]**

**Property order is NOT fixed.** The parser "generates alternations for all valid property
permutations when properties lack required constraints." **[PRIMARY]** This is the single best
explanation for Outlines' measured pathologies: JSONSchemaBench Table 2 shows **3.5-8 s** grammar
compilation and **3.6-8.4 s** TTFT for Outlines against ~0.00 s for Guidance, and Table 6 lists
`minItems`, `maxItems`, `enum`, `array` as its timeout triggers. Permuting optional properties is
factorial; bounded repetition is linear in the bound; the regex-then-DFA pipeline pays for both up
front. **llguidance and OpenAI avoid this entirely by fixing property order.**

**Documented silent under-constraining:** `dottxt-ai/outlines` issue **#654**, "JSON schema
constraints not respected by outlines" — a Pydantic model with an `anyOf` requiring at least one of
two fields to be non-null; **Outlines generated `{}`**, which fails the schema and fails Pydantic
validation. The issue is **closed with no maintainer reply**.
https://github.com/dottxt-ai/outlines/issues/654 **[PRIMARY]**
Also issue **#1083**: Outlines treats `pattern` as **implicitly anchored**, which disagrees with the
JSON Schema spec (where `pattern` is an unanchored search). So a schema that passes a real validator
can be rejected by Outlines, and vice versa. **[PRIMARY]**

### 2.11 Correction to section 2.1 — OpenAI's current limits

The Azure Foundry page I used says "up to 100 object properties total, with up to five levels of
nesting." **OpenAI's own current limits are larger** (established independently from primary
OpenAI docs by another agent on this project, post-2025-07-11): **1,000 enum values, 5,000 object
properties, 5 nesting levels, 120,000 total characters** in the schema. Treat the 100-property
figure as an **Azure-specific or stale** number and the 5,000/5/120,000 figures as current for
OpenAI. The **5-level nesting limit is common to both** and is the one that bites us: a projected
sub-schema of a deep document is fine, but the *whole* document schema may not be expressible at
all — which is an argument *for* fragment-wise generation, not against it.

### 2.12 Correction / confirmation on Anthropic

Independently confirmed by another agent from primary Anthropic docs and consistent with what I read
at https://platform.claude.com/docs/en/build-with-claude/structured-outputs: strict tool use
supports `enum`, `const`, `anyOf`, `allOf`, `$ref`/`$defs`, and **rejects with HTTP 400**: recursive
schemas, external `$ref`, `minLength`/`maxLength`, `minimum`/`maximum`, and any array constraint
beyond `minItems` in {0, 1}. Rejection-at-compile-time (400) rather than silent dropping is the
*good* failure mode — you find out.

### 2.13 The three failure modes, named

The audit shows engines fail in three distinguishable ways, and conflating them is how the field
maintains the illusion of a guarantee:

1. **Rejected at compile time** (Anthropic 400, Outlines `UnsupportedNumericBound`, vLLM's
   `has_xgrammar_unsupported_json_features` denylist). Honest. You know.
2. **Silently dropped** — the engine accepts the schema, enforces a weaker language, and says
   nothing. Examples verified from primary sources: **XGrammar drops `minLength`/`maxLength` when
   combined with `pattern`/`format`** (vLLM source comment); **Gemini treats `oneOf` as `anyOf`**;
   **Outlines treats `oneOf` as `anyOf`**; **Outlines silently truncates recursion at depth 3**;
   **Outlines emitted `{}` against an `anyOf` that forbade it** (issue #654). JSONSchemaBench
   counts **38 under-constrained failure categories for XGrammar**.
3. **Over-constrained** — the engine forbids instances the schema allows. JSONSchemaBench counts 16
   for Outlines, 18 for llama.cpp, 7 for Guidance. DOMINO's subword misalignment is the systematic
   version, worth **-10.7 GSM8K points**.

**Mode 2 is the load-bearing one for our argument.** "Constrained decoding guarantees your schema"
is false today, in shipping products, for whole-document generation, and the keywords it is false
about are exactly the whole-document keywords.

---

## 3. Compilation cost — consolidated numbers

All figures below are gathered from the primary sources cited earlier in their own sections. This
is the answer to "can a grammar be compiled per request?"

### 3.1 Measured compilation / startup costs

| Engine | Grammar compile time | Source |
|---|---|---|
| llguidance / Guidance | **~0.00 s** (negligible; masks computed on the fly) | JSONSchemaBench Table 2 **[PRIMARY]** |
| llama.cpp GBNF | **~0.05 s** | JSONSchemaBench Table 2 **[PRIMARY]** |
| **Outlines** | **3.5-8 s**; TTFT 3.6-8.4 s | JSONSchemaBench Table 2 **[PRIMARY]** |
| XGrammar (v1) | 75 ms at K=1,000 enum; 75-239 ms at K>=1,000; ">1000 ms" for dynamic tool grammars | Trie-Automata paper; XGrammar-2 Fig. 8 **[PRIMARY]** |
| XGrammar (v1), competitor claim | "often runs into seconds, and sometimes minutes" | llguidance README **[PRIMARY but advocacy]** |
| XGrammar-2 (JIT) | **~10 ms** for dynamic tool-catalogue grammars | XGrammar-2 Fig. 8 **[PRIMARY]** |
| Trie automaton over K enum strings | **30-67 ms for K=10 .. 100,000**; sub-100 ms to K=10,000 | arXiv:2608.12574 **[PRIMARY]** |
| DOMINO precomputation | **1-5 s** typical grammars; **~20 s** for a C grammar | DOMINO Sec. 4.3 **[PRIMARY]** |
| OpenAI Structured Outputs | "additional latency" on first use of a schema; cached after | OpenAI docs **[PRIMARY, no number]** |
| Anthropic Structured Outputs | "additional latency while the grammar compiles"; cached **24 h from last use** | Anthropic docs **[PRIMARY, no number]** |

### 3.2 Per-token masking cost

| Engine | Per-token mask | Source |
|---|---|---|
| Trie automaton (finite set) | **0.65 us** | arXiv:2608.12574 **[PRIMARY]** |
| XGrammar | **<40 us** (JSON Schema, JSON CFG); <200 us (XML, Python DSL); 5.8 us on a pure enum | XGrammar Fig. 9; Trie-Automata **[PRIMARY]** |
| XGrammar-2 | **<250 us** | XGrammar-2 Fig. 7 **[PRIMARY]** |
| llguidance | **~50 us** average over JSONSchemaBench (2.5M tokens, 10k schemas); <1% >1 ms; 0.001% >10 ms; up to 1.5 ms unoptimised; 73-141 us on large enums | llguidance README; Trie-Automata **[PRIMARY]** |
| Per-token wall clock (end to end, llama.cpp backend) | Guidance 6-10 ms, llama.cpp 27-29 ms, Outlines 30-47 ms, unconstrained LM 15-17 ms | JSONSchemaBench Table 2 **[PRIMARY]** |

Note that Guidance's **6-10 ms/token beats the unconstrained LM's 15-17 ms** because of token
fast-forwarding: where the grammar determines the next characters, they are emitted without a
forward pass. **Constrained decoding can be net *faster* than free generation.** DOMINO measures the
same effect as **1.77x speedup on JSON-with-schema (Mistral 7B)**.

### 3.3 How compilation scales

- **Outlines** compiles schema -> regex -> DFA -> full-vocabulary index. Cost scales with the number
  of DFA states x |V|. Property permutation (it does *not* fix property order) and bounded
  repetition (`minItems`/`maxItems`) both inflate the DFA; those are exactly the keywords
  JSONSchemaBench Table 6 lists as its timeout triggers. Recursion is capped at depth 3 explicitly
  "to prevent exponential regex bloat."
- **XGrammar** precomputes an adaptive token-mask cache; memory 160 MB -> 0.46 MB after their
  optimisation for Llama-3.1 + JSON. Compilation dominates when grammars are not reused.
- **llguidance** computes masks lazily with an Earley parser, so **there is essentially nothing to
  compile**. This is why it wins on dynamic schemas and loses (slightly) on repeated ones.
- **Trie automata**: `O((N_chars + V) * l)`, and crucially **the V-dependent part is per-tokenizer,
  not per-constraint**, so it can be built once and reused for every enum. That is why 100,000
  strings still compiles in 67 ms.

### 3.4 The answer to "how big can a pointer trie get before it hurts?"

Directly measured, in the closest analogue that exists: **100,000 strings -> 67 ms compile,
0.65 us/token mask** (Trie Automata, arXiv:2608.12574). A JSON Pointer trie for a document with
100,000 addressable locations is therefore **not** the blocker. The blocker, if any, is that this
compile happens on the critical path of every request rather than once.

Mitigations that already exist in production:
- vLLM V1 compiles the grammar for a request **asynchronously** in the `StructuredOutputManager`,
  off the scheduler's critical path. **[PRIMARY — vLLM engineering blog "Inside vLLM: Anatomy of a
  High-Throughput LLM Inference System", https://vllm.ai/blog/2025-09-05-anatomy-of-vllm]**
- XGrammar-2's **cross-grammar cache**: shared sub-structures are reused across different requests'
  grammars; "if rules share the same lookahead assertion, it is a perfect cache hit and token mask
  caches can be reused directly; otherwise it is a partial cache hit requiring rechecking of
  uncertain tokens"; LRU eviction at the size limit. **[PRIMARY]**
- XGrammar-2's **JIT**: compile automaton states lazily and "avoid compilation for states that are
  never used." For a delta grammar this is close to ideal — a patch touches one path, so almost all
  of a big pointer trie would never be compiled at all.

---

# PART TWO — the reframed questions (7-11)

## 7. Sub-schema projection in practice: can you compile a grammar for an arbitrary sub-schema?

**Short answer: yes for every open-source engine; no for OpenAI and Anthropic at the root; yes for
Gemini for arrays but not scalars.** The friction is entirely at the API boundary of the two US
proprietary vendors, and it is a one-line wrapper.

### 7.1 Root-type restrictions, verified

| Engine | Root may be a bare array? | Root may be a bare scalar? | Source |
|---|---|---|---|
| Outlines | **Yes** — it compiles any schema to a regex; `type` is handled generically for string/number/integer/array/object/boolean/null | **Yes** | outlines-core `parsing.rs` **[PRIMARY]** |
| llguidance | **Yes** | **Yes** — JSON Schema is compiled to a Lark grammar with no root-type special case; `%json {...}` can be inlined anywhere in a grammar | llguidance `docs/json_schema.md`, `docs/syntax.md` **[PRIMARY]** |
| XGrammar | **Yes** | **Yes** — `compile_json_schema` takes any schema | XGrammar docs **[INFERRED: the docs URL I tried 404'd; asserted from the API shape and from Structural Tags treating JSONSchema as an *atomic type* embeddable anywhere. Flagged as unverified.]** |
| llama.cpp GBNF | **Yes** | **Yes** — the converter emits a GBNF root rule for whatever the schema says | grammars/README **[PRIMARY]** |
| vLLM / SGLang | inherits the backend | inherits the backend | — |
| **OpenAI Structured Outputs** | **NO — root must be an object**; "Root objects can't be the `anyOf` type" | **NO** | Azure/OpenAI docs **[PRIMARY]** |
| **Anthropic** | **NO — root must be an object** | **NO** | Anthropic docs **[PRIMARY]** |
| Gemini | **Yes** (object or array at root) | Not documented | ai.google.dev **[PRIMARY]** |

**Workaround for OpenAI/Anthropic is trivial and lossless**: wrap the fragment in
`{"type":"object","properties":{"value":<subschema>},"required":["value"],
"additionalProperties":false}` and unwrap on receipt. Cost: a few tokens of `{"value":` scaffolding
per call, which token fast-forwarding emits for free on open engines and which the proprietary APIs
charge you for.

### 7.2 The `$ref` problem — the one real piece of friction

A projected sub-schema is a *fragment of* S. If the fragment contains `"$ref": "#/$defs/Foo"`, that
pointer resolves against the **root of the document the fragment was cut from**, which no longer
exists. Every engine I audited supports **internal `$ref` only** and rejects external `$ref`
(llguidance `ExternalReferencesNotSupported` equivalent; Outlines
`ExternalReferencesNotSupported`; Anthropic rejects external `$ref` with 400).

So projection is **not** "hand the engine the subtree". It is:
1. take the subtree at path p,
2. compute its transitive `$ref` closure within S,
3. emit a new self-contained schema whose `$defs` carries that closure,
4. rewrite the `$ref` URIs to point at the new root.

That is a well-defined, purely mechanical schema operation (bundling / dereferencing). Tooling for
it already exists in the JSON Schema ecosystem — `$ref` bundling per the 2020-12 "Compound Schema
Document" convention, and library support in e.g. `json-schema-ref-parser`, `jsonref`,
`referencing`. **[INFERRED — I did not verify a specific library's behaviour in this session.]**

**Pydantic makes this nearly free.** A nested `BaseModel` is already a schema in its own right:
`SubModel.model_json_schema()` produces a self-contained document with its own `$defs`. So for the
form case, step (b) of the architecture is a method call, not an algorithm. `TypeAdapter(List[Row])`
likewise produces `{"type":"array","items":{...}}` directly — a bare-array root, which every open
engine accepts. **[PRIMARY for the Pydantic API shape: https://docs.pydantic.dev/latest/concepts/json_schema/]**

### 7.3 Structural Tags — the mechanism that already does fragment-wise constrained decoding

This is the most important thing I found for question 7, and I nearly missed it.

- MLC blog, **"XGrammar-2: Fast and Customizable Structured Generation for Tool Calling and
  Agents"**, 4 May 2026,
  https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation **[PRIMARY]**
- **Structural Tags** are "a JSON-based DSL that provides a unified, lightweight, and extensible way
  to describe the diverse structures agents need."
- **Atomic types, all first-class: JSON Schema, regular expression, literal string, token IDs.**
- **Combinators:**
  - `Sequence` — chain parts together;
  - `Tag` — a begin marker, constrained content, an end marker;
  - `AnyText` — arbitrary text until the enclosing tag's end marker;
  - `TriggeredTags` — free text by default; **once the model emits a trigger string, the output must
    follow the corresponding structured tag**;
  - `JSONSchema` — constrain content to a schema, with style options.
- **A JSON Schema can be nested as the content of a tag inside a larger structure.** Their DeepSeek
  example nests `JSONSchema(style="deepseek_xml")` inside a `Tag` inside `TriggeredTags`.
- **The constraint can switch based on the model's own earlier output** (that is exactly what
  `TriggeredTags` is).
- Shipped and integrated: **SGLang, vLLM, TensorRT-LLM and MLC-LLM** all integrate Structural Tags;
  XGrammar ships built-in tags for DeepSeek V4, Qwen 3.6, GPT-OSS. API:
  `response_format: {"type": "structural_tag", "format": {...}}`.
- Numbers: **up to 80x compilation speedup over XGrammar** for 10-500 tools; repetition compression
  **534 ms -> 5.37 ms (100x)** on complex JSON schemas; **cross-grammar cache finds ~50% structure
  reuse** compiling a 50-tool JSON Schema; **100% schema accuracy on BFCL-V3**.

**Why this matters to us [JUDGEMENT]:** Structural Tags is the industry's answer to *"constrain part
of the output against a schema, and choose which schema based on runtime information."* It is
already deployed in four serving engines. Our "project a sub-schema and generate only the fragment"
step is not a new capability request — it is a **JSONSchema atom inside a Sequence**, which the API
already accepts. What Structural Tags does **not** give us is the *localisation* step, the *splice*
step, or any *cross-fragment* guarantee. Those are ours to build.

---

## 8. Grammar caching across many small calls — the objection largely dissolves

The reframing is right and the evidence supports it strongly.

**A projected sub-grammar depends only on (S, path).** For a fixed Pydantic model the set of
distinct sub-schemas is finite and small — one per nested model, plus one per field type. For the
Excel case the "10 rows" grammar is `{"type":"array","items":Row,"minItems":10,"maxItems":10}`,
**byte-identical on every batch**. So:

- **Anthropic**: "Compiled grammars are cached for **24 hours from last use**"; invalidated only by
  a change to the schema structure or the tool set. A repeated sub-schema hits the cache every
  time. **[PRIMARY]**
- **OpenAI**: "The first request you make with any schema will have additional latency as our API
  processes the schema, but subsequent requests with the same schema will not have additional
  latency." **[PRIMARY]**
- **vLLM**: `GrammarCompiler(cache_enabled=True, cache_limit_bytes=VLLM_XGRAMMAR_CACHE_MB,
  max_threads=8)` — an in-process, size-capped compiled-grammar cache; and in V1 the per-request
  grammar is compiled **asynchronously**, off the scheduler's critical path. **[PRIMARY]**
- **XGrammar-2**: a **cross-grammar cache** keyed on automaton sub-structure with hierarchical
  hashing — "if rules share the same lookahead assertion, it is a perfect cache hit and token mask
  caches can be reused directly; otherwise it is a partial cache hit"; LRU eviction at the size
  limit; **~50% structure reuse** measured on a 50-tool schema. **[PRIMARY]**
- **SGLang / Outlines**: no documented cross-request grammar cache. Outlines' 3.5-8 s compile is
  paid per distinct schema; if you reuse the same compiled index object you pay once.
  **[PRIMARY, negative on documentation]**

**Independent confirmation of the shape of the trade-off**: SqueezeBits measured that **XGrammar
wins on repeated schemas and loses to llguidance on per-request-unique schemas**, because
"XGrammar's caching strategy is neutralized." **[PRIMARY, vendor-neutral blog]**

**Conclusion for the project [JUDGEMENT]:** the fragment architecture sits squarely in the
*repeated-schema* regime, which is the regime every engine is optimised for. The caching objection
that applied to a document-derived patch grammar **does not apply** to a schema-derived sub-grammar.
The one caveat is that many small calls each pay **prefill** for the prompt and the schema; that is
a prompt-caching problem, not a grammar-compilation problem, and the two should not be conflated.

---

## 9. Compositionality — local validity does not compose to global validity, and nobody has studied it

### 9.1 The literature search, and its result

I searched for prior work on whether a fragment generated against a projected sub-schema, spliced
into a valid document, yields a valid document. Queries used, all of which came back empty of
on-point work:

- `"sub-schema" OR "subschema" constrained decoding fragment generation splice compose "local
  validity" "global validity" JSON schema modular composition LLM`
- `compositional constrained decoding local global schema validity`
- `JSON Schema modular composition constrained generation fragment splice validate`
- `LLM long structured document generation "in chunks" OR "batches" schema validation assemble`

**Finding: there is no paper on the compositionality of constrained decoding.** The nearest things
in the literature are (a) JSON Schema's own composition keywords `$ref`/`allOf`/`anyOf`/`oneOf`,
which are about composing *schemas*, not about composing *generations*; and (b) engine notes that
"union types and recursive references are handled by fresh nonterminals when converting JSON schemas
to CFGs", which is a compilation detail. **[NEGATIVE FINDING, searched hard.]**

### 9.2 What is provable without any new theory

JSON Schema validity is **not** compositional in general, and the failure set is exactly
enumerable. **[INFERRED — mine, but it follows directly from the spec's semantics.]**

**Composes cleanly.** If the sub-schema at path p is reachable from the root by `properties`/`items`
edges only, and it contains no keyword that constrains anything outside itself, then a fragment
valid against it is valid in place. That covers `type`, `properties`, `enum`, `const`, `pattern`,
`format`, and all per-value bounds. **This is the overwhelming majority of real schemas** — and it
is the whole of the Pydantic form case, where "the answer to Q3" is a self-contained nested model.

**Does not compose, ranked by how likely it is to bite:**
1. **`required` on a sibling / on the containing object.** If localisation replaces a whole object,
   the fragment's own `required` covers it. If it replaces one property, `required` is untouched.
   Only *deleting* a property can break it — so the safe rule is *fragments may replace and add, but
   deletion must be checked against the parent's `required`*.
2. **`minItems`/`maxItems` on a containing array.** The Excel case: batch k must know the running
   total. This is a **counter**, held by the orchestrator, not by any grammar. Trivial in code.
3. **`uniqueItems` across batches.** The real one. Row 9,412 must not duplicate an id from batch 3.
   See section 10.
4. **`if`/`then`/`else`, `dependentRequired`, `dependentSchemas`, `oneOf` discrimination.** The
   discriminator may live outside the fragment. Two cases: if the discriminator is already fixed in
   D, the orchestrator can **specialise the sub-schema before compiling it** — resolve the `if` at
   projection time and hand the engine only the `then` branch. That is strictly *easier* than
   whole-document generation, where no engine handles these keywords at all. If the discriminator is
   itself being regenerated, it must be in the same fragment.
5. **Cross-references** (`$ref` to a sibling's value, `$data`-style references, foreign keys). Not
   expressible in JSON Schema at all; already validated in code today.

**The load-bearing observation [JUDGEMENT]:** every item on that "does not compose" list is on the
**"no engine enforces this anyway"** list from section 2.9. `uniqueItems`, `if/then/else`,
`dependentRequired`, `dependentSchemas`, `not`, `propertyNames` — **zero engines, zero products.**
So the compositionality gap does not *lose* a guarantee that anyone currently has. It moves work
from "post-generation validation the caller already had to do" to "post-splice validation the caller
still has to do", plus two genuinely new bits of bookkeeping (a running count, a running used-value
set) that live in ordinary code and are trivial.

The exception is `required` and `minItems`/`maxItems`, which llguidance and llama.cpp *do* enforce
today for whole-document generation. Fragment-wise generation demotes those two from
*decoder-enforced* to *orchestrator-enforced*. **That is the entire true cost of the reframed
architecture, and it is two integers.**

### 9.3 Something adjacent that does exist, and is worth citing

**TruncProof: A Guardrail for LLM-based JSON Generation under Token-Length Constraints**,
arXiv:2605.13076, https://arxiv.org/abs/2605.13076 **[PRIMARY — abstract only]**
- Problem: constrained JSON generation under a hard token budget either runs forever or gets
  truncated into malformed JSON.
- Method: exploits **LL(1) parser properties to efficiently estimate the minimum number of tokens
  needed to complete a grammatically valid output at each decoding step**, so generation can halt
  early while still closing every bracket.
- No numeric results in the abstract; **does not** address multi-call chunked generation.
- **Why it matters to us:** this is a *cost-aware lookahead* — "can I still finish inside my
  budget?" — computed cheaply over a grammar. It is the right primitive for deciding **where to cut
  a batch boundary** in the Excel case, and it is the only paper I found that computes a
  quantitative completion cost from the grammar rather than a boolean.

---

## 10. Cross-fragment state — nobody has done it, and I am confident about that

**Question:** is there any constrained-decoding work that carries state ACROSS separate generation
calls — a running set of already-used values to enforce uniqueness, a running count to enforce
cardinality?

**Answer: no. I searched specifically and found nothing.** Queries run, all empty of on-point work:

- `constrained decoding "across multiple calls" OR "multiple generations" enforce uniqueness
  previously generated values running state batched rows incremental structured output`
- `"stateful" constrained decoding grammar "already generated" avoid duplicates enum shrinking
  dynamic constraint update mid-generation`
- `constrained decoding uniqueItems enforce ALLDIFFERENT LLM`
- `carry grammar state between requests LLM structured output resume constraint`

**[NEGATIVE FINDING — high confidence. This is one of the two genuinely open things I found.]**

What exists, and why it is *not* this:

- **XGrammar's `GrammarMatcher` is stateful and caller-driven** — you feed it the last token and ask
  for the next bitmask, so a caller *could* thread state manually. But the state it carries is the
  automaton position within *one* generation; nothing in the API composes two matchers or carries a
  value-set between calls. **[PRIMARY, from the XGrammar API description.]**
- **llguidance uses an Earley parser with lazy automaton construction and no upfront DFA
  compilation**, which is precisely what makes a *new* grammar per call cheap. So the machinery to
  compile a fresh grammar every batch already exists and costs ~0 to start.
  **[PRIMARY, llguidance README / docs.rs.]**
- **GENRE / Trie Automata** build a constraint from an external finite set — but the set is fixed
  before generation and never updated by what the model produced.

### 10.1 Why the Excel `uniqueItems` case is easier than it looks [JUDGEMENT, mine]

The mechanism to enforce "this batch's ids must differ from the 9,400 already emitted" **already
exists and is measured**: it is the trie automaton of arXiv:2608.12574, complemented. Concretely:

- Maintain the used-id set U in the orchestrator (ordinary code).
- Before batch k, compile the constraint "id must not be any string in U" — i.e. the complement of a
  prefix trie over U. Aho-Corasick over |U| strings.
- Measured cost for this exact shape of constraint: **|U| = 100,000 compiles in 67 ms; masking costs
  0.65 microseconds per token.** The dominant term is per-tokenizer, not per-item, so it amortises.
- The one wrinkle: you want *negation* of a finite set inside a larger JSON grammar. Structural Tags
  gives you the composition point (a regex atom inside a Sequence). Whether any engine will accept a
  100k-alternative negated regex efficiently is **unverified and worth a bench**.

So: **cross-fragment uniqueness is not a research problem, it is an unbuilt feature.** Nobody has
built it because nobody has needed it — whole-document generation never had a fragment boundary to
carry state across.

### 10.2 Cardinality across batches is not even a grammar problem

`minItems`/`maxItems` on the containing array reduce, under batching, to an integer the orchestrator
holds. Batch k is generated against `{"type":"array","items":Row,"minItems":n_k,"maxItems":n_k}`
where n_k is chosen by the orchestrator. There is nothing to enforce at decode time beyond what the
per-batch grammar already enforces. **[JUDGEMENT]**

---

## 11. Field-at-a-time / iterative structured generation — the accuracy evidence is strongly in favour

This is the question where the evidence surprised me most, and it argues *for* the reframed
architecture on quality grounds, not just cost grounds.

### 11.1 The multiplicative-decay argument, stated and measured

**"From Unstructured Recall to Schema-Grounded Memory: Reliable AI Memory via Iterative,
Schema-Aware Extraction"**, arXiv:2604.27906, https://arxiv.org/html/2604.27906v1 **[PRIMARY]**
*(Scope caveat: the paper's application is agent memory, which is out of scope for this project. I
am citing its* method *and* measurements *, which are about iterative schema-constrained extraction
and are squarely in scope.)*

- **The argument (their Section 5.1):** for a record with m required fields each correct with
  probability q, the probability the whole record is correct is `prod q_i`. With **q = 0.97 and
  m = 20, single-pass object accuracy is ~0.54.** Iteration with per-field retry lifts it to
  **~0.98**. Their statement: in a one-shot setting the collapse "is unavoidable: there is no
  mechanism to interrupt the chain, catch an early error before it corrupts downstream conditioning,
  or retry a single field in isolation." **[PRIMARY]**
- **Their measured field-to-object collapse (Tables 5-7):**
  **Field F1 97.53% (+/-0.46) -> object accuracy 90.42% (+/-1.70) -> output accuracy 62.67%
  (+/-4.92).** **[PRIMARY]**
- **Iterative decomposition vs single-pass frontier models on the same insurance-claims dataset
  (output accuracy):** **GPT-5.5 (high reasoning) 44.00%; Gemini 3.1 Pro 61.67%; their iterative
  pipeline 62.67%.** **[PRIMARY]**
- **Their pipeline**: three stages — object detection, field detection, field-value extraction —
  with "validation gates, local retries, and stateful prompt control" (Sec. 6.1). Downstream prompts
  condition on **previously validated** decisions, so "errors caught by validation do not create a
  corrupted prefix for downstream fields" (Sec. 5.1). "Retries are applied only to fields that fail
  validation, concentrating additional work on uncertain fields rather than regenerating the whole
  object." **[PRIMARY — that last sentence is our thesis, arrived at independently, from a different
  starting point.]**
- **They are sceptical of constrained decoding**: "single-pass structured output often relies on
  grammar-constrained decoding, which can enforce format while still distorting the model's semantic
  distribution" (Sec. 6.1). They do **not** use constrained decoding, and they do **not** discuss
  whether cross-field constraints break under decomposition. **[PRIMARY, negative]**

### 11.2 Corroborating evidence

- **Cleanlab's structured-output benchmark work** reports that for per-field scoring, "the
  multiple-call LLM-as-Judge method consistently outperforms the single-call version, though at the
  cost of making many more LLM calls."
  https://cleanlab.ai/blog/tlm-structured-outputs-benchmark/ **[SECONDHAND — vendor blog, read via
  search summary only.]**
- Long-document generation practice (e.g. **Pap2Pat**, arXiv:2410.07009, outline-guided long patent
  generation) already chunks by outline and concatenates, because models cannot emit long documents
  in one call. **[SECONDHAND]** This is the Excel case in prose form, and it is standard practice.

### 11.3 The honest counterweight

I found **no** paper that runs the controlled comparison we actually want: *same schema, same model,
whole-object constrained generation vs fragment-wise constrained generation, measuring both task
accuracy and schema validity.* The decomposition papers do not use constrained decoding; the
constrained-decoding papers do not decompose. **[NEGATIVE FINDING.]** The two literatures do not
cite each other. That gap is where this project sits.

Also note the obvious cost the decomposition literature pays and does not always price: **many more
calls**, each paying prefill. The Excel case turns one 10,000-row generation into 1,000 calls. That
is a prompt-caching and batching problem, and it is the strongest practical objection to the
fragment architecture — not correctness, but request amplification.

---

## 5 (continued). Distortion addenda — does it scale with restrictiveness?

### 5.3 The one paper that varies restrictiveness and measures the effect

**"Constraint Tax in Open-Weight LLMs: An Empirical Study of Tool Calling Suppression Under
Structured Output Constraints"**, arXiv:2606.25605, https://arxiv.org/html/2606.25605v1
**[PRIMARY]**

- Models (their Table 4): Qwen3.6-35B-A3B, Qwen3.5-122B-A10B, GPT-OSS-20B, Nemotron 3 Super (120B),
  Qwen3.5-397B-A17B, Qwen3-VL-235B-Thinking, and GPT-5.4-mini as a proprietary baseline.
- Headline (their Table 7): under **joint constraints** (structured output format enforced *and* the
  task requiring a tool call), **tool invocation rate falls from 100% to 0% on every open-weight
  model tested — a 100% suppression rate.** GPT-5.4-mini maintained 100% invocation.
- **The restrictiveness sweep (their Table 8)** — they varied schema complexity across three levels:
  simple (1-3 fields), medium (5-10 fields), production-grade (20+ fields). **"Across all three
  schema categories, suppression behavior remained unchanged", tool invocation stayed at 0%
  regardless of schema complexity. No threshold effect.** **[PRIMARY]**

**How to read this for our question [JUDGEMENT]:** this is the only restrictiveness sweep I found,
and its answer is **"the effect is binary, not graded"** — the damage came from *imposing a
structured-output constraint at all*, not from how tight it was. Two caveats before leaning on it:
(1) it measures a specific behavioural interaction (structured output suppressing tool use) that is
partly a known API-level incompatibility — Azure's own docs say structured outputs are not supported
with parallel function calls and require `parallel_tool_calls: false`; (2) "schema complexity"
measured in *number of fields* is not the same axis as *restrictiveness of the language*. A 20-field
schema of free strings is a *looser* language than a 3-field schema of enums.

**So the state of the evidence on "does distortion scale with restrictiveness?" is:**

| Source | Finding | Kind |
|---|---|---|
| Tam et al. (EMNLP 2024) | "Stricter format constraints generally lead to greater performance degradation in reasoning tasks" — JSON-mode worse than FRI worse than NL-to-format | Claim, confounded by prompt mismatch |
| .txt rebuttal + JSONSchemaBench | With matched prompts the effect vanishes or reverses (+3.3 to +3.7 points) | Measurement, neutral third party for the latter |
| Park et al. GAD (NeurIPS 2024) | The distortion *mechanism* (indicator instead of EFG) gets worse the more the grammar prunes; distortion measured at 2.259 vs 1.242 (SLIA), 1.852 vs 0.802 (INV-BV) | Theory + measurement, but **no restrictiveness sweep** |
| Constraint Tax (2026) | Binary, not graded: 100% suppression at every schema size tested | Measurement, narrow behaviour |
| Beurer-Kellner et al. DOMINO (ICML 2024) | The big measured loss (-10.7 GSM8K points) came from **token misalignment**, an implementation artefact, and is fully recoverable | Measurement |

**Bottom line [JUDGEMENT]: there is no published evidence that a narrower grammar distorts more,
and there is one paper suggesting the effect is not graded at all. The strong, reproducible causes
of damage are (a) token misalignment, which good engines fix, and (b) prompt/schema mismatch, which
is the caller's fault. The GAD/EFG distortion is real and unfixable in principle, but nobody has
shown it tracks restrictiveness.**

For our purposes the relevant asymmetry is not restrictiveness but **familiarity**: a projected
sub-schema asks the model for ordinary JSON of a shape it has seen a billion times; a JSON Patch
operation list asks it for a shape that is rare in pretraining. The reframed architecture avoids
that risk entirely, and I found **no** measurement of how far off-distribution the patch-language
target is. **[NEGATIVE FINDING — worth a cheap experiment: compare unconstrained likelihood of the
patch form vs the fragment form for the same edit.]**

---

# What this means for the delta problem — MY JUDGEMENT

Everything in this section is my own reading, clearly separated from the evidence above.

## J1. The guarantee everyone thinks they have is much weaker than they think

Grammar-guided decoding promises exactly one thing: **at every step, the emitted token keeps the
string a prefix of some string in a regular or context-free language**. It says nothing about
semantics, nothing about cross-field relationships, and — crucially — nothing about the JSON Schema
keywords it cannot compile.

The audit in section 2 shows the gap is not marginal. On real-world schema corpora, **no engine
exceeds 41% empirical coverage on GitHub Hard, and the best on JSONSchemaStore is 38%**
(JSONSchemaBench Table 4). **XGrammar had 38 categories of under-constrained failure** — accepted
the schema, then produced output violating it. vLLM ships a hand-maintained denylist to stop
XGrammar silently dropping `minLength`/`maxLength`. Gemini and Outlines both silently degrade
`oneOf` to `anyOf`. Outlines silently truncates recursion at depth 3 and cannot enforce
`minimum`/`maximum` at all.

## J2. The "residue" is not a new cost of going delta. It is the status quo.

This is the finding that most changes the argument.

`uniqueItems`, `if`/`then`/`else`, `dependentRequired`, `dependentSchemas`, `not`, `propertyNames`,
`contains` — **enforced by zero engines, in zero products, during ordinary whole-document
generation.** Every single one. `required` is enforced only by the trick of **fixing property order**
to schema-declaration order, which is itself a departure from JSON Schema semantics that every
engine makes and only llguidance and OpenAI document.

So when we list what a fragment-wise architecture cannot guarantee, we are mostly listing what
nobody guarantees today. The honest statement of the *new* cost is narrow:

> Going fragment-wise demotes exactly two things from decoder-enforced to orchestrator-enforced:
> `required` across a fragment boundary, and `minItems`/`maxItems` on a containing array. Both are
> integers held in ordinary code. Everything else on the residue list was already the caller's job.

That is a far weaker objection than "you lose the guarantee."

## J3. The reframing kills the strongest objection to the original idea

The original framing had a real problem: a grammar derived from document D is a novel grammar on
every call, so it can never hit a compilation cache. **Anthropic caches compiled grammars for 24
hours from last use and invalidates on any schema-structure change; OpenAI charges extra latency for
a schema's first use and nothing thereafter.** A document-derived grammar loses both.

A **schema-projected** sub-grammar depends only on (S, path). For a Pydantic model the set of
distinct sub-schemas is finite and small. For the Excel case, the "10 rows" grammar is byte-identical
every batch. It hits every cache, everywhere. **The caching objection dissolves under the
reframing.**

And even in the original framing it was survivable: **a trie over 100,000 strings compiles in 67 ms
and masks at 0.65 microseconds per token** (arXiv:2608.12574), and llguidance has essentially zero
startup cost by design.

## J4. The mechanism we need is already shipping, under a name we did not know

**Structural Tags** (XGrammar-2, deployed in SGLang, vLLM, TensorRT-LLM and MLC-LLM) treats **JSON
Schema as a first-class atomic type composable inside a larger structure**, with a `TriggeredTags`
combinator that **switches the constraint based on the model's own earlier output**. That is step
(c) of the reframed architecture — generate a fragment under constrained decoding against a
projected sub-schema — already built, already integrated, already benchmarked (100% schema accuracy
on BFCL-V3).

We should stop describing this part of the plan as novel. It is not. What is missing around it is:
**localisation** (choosing the region), **projection** (cutting a self-contained sub-schema out of
S, including the `$ref` closure), **splice**, and **cross-fragment state**.

## J5. The two genuinely open things

Everything else I looked for either exists or is trivial. Two things do not exist:

1. **Constrained decoding that carries state across generation calls.** No paper, no library, no
   API. The Excel `uniqueItems` case needs it. I am confident this is a real gap (section 10). But
   it is an **unbuilt feature, not a research problem**: uniqueness against a *known finite set* is
   regular, and the exact machinery (an Aho-Corasick trie automaton over 100k strings, 67 ms compile,
   0.65 us/token) is published and measured. Someone has to wire it up.

2. **Compositionality of constrained generation.** There is no work on whether a fragment valid
   against a projected sub-schema, spliced into a valid document, yields a valid document. The
   constrained-decoding literature and the decomposed-extraction literature do not cite each other
   at all. A short paper that (a) characterises exactly which JSON Schema keywords are
   splice-stable, (b) gives an algorithm for projecting a self-contained sub-schema with its `$ref`
   closure, and (c) shows the residual obligations are decidable in code, would be the first of its
   kind. That is not a big theorem. It is a clean, correct, useful one.

## J6. The quality argument may be stronger than the cost argument

I went in expecting fragment-wise generation to be a cost optimisation with a correctness tax. The
evidence points the other way.

The multiplicative-decay result is the crux: **with per-field accuracy 0.97 and 20 fields,
single-pass object accuracy is ~0.54; iterative per-field generation with validation lifts it to
~0.98** (arXiv:2604.27906, Sec. 5.1). Measured on a real dataset: field F1 97.53% collapses to
object accuracy 90.42% and output accuracy 62.67%; their iterative pipeline beat GPT-5.5 with high
reasoning (44.00%) and Gemini 3.1 Pro (61.67%) at the record level.

Add the correctness argument from the problem statement — retyping untouched regions is an
opportunity to corrupt them, and a fragment that is never regenerated cannot be corrupted — and the
case is: **fragment-wise structured generation is more accurate, not just cheaper.** That is a much
better paper than "we saved output tokens."

## J7. Distortion is a real risk but the evidence does not support the version we feared

We worried that a narrower grammar distorts more, and that a patch language is far off-distribution.

- **Nobody has shown distortion scales with restrictiveness.** Tam et al. claim it, but their
  comparison is confounded by using different prompts per condition; .txt's re-run reverses the
  result and JSONSchemaBench independently measures constrained decoding *improving* accuracy by
  +3.3 to +3.7 points. The one paper that actually sweeps schema complexity finds a **binary, not
  graded** effect.
- **The reproducible causes of damage are token misalignment (-10.7 GSM8K points, fully fixed by
  DOMINO) and prompt/schema mismatch (the caller's fault).**
- **The unfixable distortion is real but orthogonal**: GCD substitutes an indicator for the expected
  future grammaticality, and computing the latter exactly is #P-hard. Everyone pays this. ASAp fixes
  it only in the limit, over thousands of samples.

The risk that *does* survive is the one we can avoid by construction: a **patch language is rare in
pretraining; a JSON fragment is not.** The reframed architecture sidesteps it. If anyone insists on
the patch framing, the cheap experiment is to compare the unconstrained likelihood the model assigns
to the patch form versus the fragment form of the same edit. Nobody has run it.

## J8. What I would actually build, and what I would claim

**Build:** LOCALISE -> PROJECT (with `$ref` closure) -> GENERATE via Structural Tags / a projected
sub-schema on any open engine -> SPLICE -> revalidate globally with an ordinary JSON Schema
validator, plus an orchestrator that holds (i) a running item count and (ii) a running used-value set
compiled to a trie automaton when `uniqueItems` is in play.

**Claim (a) is already solved:** fragment-level constrained generation against a sub-schema
(Structural Tags); state-conditioned grammars from a runtime catalogue (GENRE 2021, PICARD 2021,
Trie Automata 2026, XGrammar-2 2026); grammar caching for repeated sub-schemas (every vendor).

**Claim (b) is not worth solving:** enforcing the whole-document residue *at decode time*. No engine
does it, the constraints are not context-free, and post-hoc validation in code is cheap, exact and
already necessary.

**Claim (c) is genuinely open:** cross-call constrained decoding state, and the compositionality
theory. Those are the two things to write about.

---

# What I did NOT get to, and known weaknesses of this document

- **DOMINO's numbers were extracted by a fetch model from the ar5iv HTML, not read off the PDF by
  me.** The -10.7 GSM8K point drop, the 1.77x speedup and the 1-5 s precomputation figure should be
  eyeballed in the paper before being used in a write-up.
- **The GeLaTo (ICML 2023) hardness statement is secondhand** — the UCLA PDF returned HTTP 403. The
  equivalent statements in "Hidden Biases in Conditioning Autoregressive Models" (arXiv:2604.07855)
  *are* primary and can carry the argument on their own.
- **PICARD (EMNLP 2021) I did not fetch in this session.** The description in section 6.4 is from
  background knowledge plus search corroboration. Confirm before citing.
- **SynCode (TMLR 2025) I read only at abstract level.** The soundness/completeness claim and the
  phrase "complete under specific conditions" should be checked against the theorem statement.
- **The CP "GRAMMAR constraint" literature (Katsirelos/Narodytska/Walsh; Propagating Regular Counting
  Constraints) I identified but did not read.** I think it is the most valuable unexplored lead in
  this document: 15+ years of results on propagating a grammar constraint jointly with ALLDIFFERENT
  (= `uniqueItems`) and the Global Cardinality Constraint (= `minItems`/`maxItems`), which the
  constrained-decoding literature appears not to cite at all.
- **XGrammar's root-type flexibility is inferred, not verified** — the docs page 404'd. Someone
  should confirm `compile_json_schema` accepts a bare-array or bare-scalar root.
- **OpenAI's *current* supported-keyword list is not verified verbatim.** `platform.openai.com` now
  redirects to `developers.openai.com`, whose "supported schemas" section is behind JS and did not
  render. I used the Azure Foundry mirror (updated 2026-08-24) for the table and flagged the
  divergence caused by OpenAI's May 2025 additions (`pattern`/`format`, numeric ranges, array
  min/max). Re-check directly.
- **I did not survey the fine-tuning / RL alternative** ("Learning to Generate Structured Output with
  Schema Reinforcement Learning", ACL 2025, aclanthology.org/2025.acl-long.243; "Think Inside the
  JSON", arXiv:2502.14905). If a model can be trained to emit patches or fragments reliably, that
  changes the cost/benefit of decode-time enforcement. Out of my assignment, but worth someone's
  time.
- **I did not chase "Flexible and Efficient Grammar-Constrained Decoding" (arXiv:2502.05111),
  "Efficient Grammar-Constrained Decoding via Parser Stack Classification" (arXiv:2608.03065),
  "Earley-Driven Dynamic Pruning" (arXiv:2506.01151), or "Stay Within Your Bounds: Distance-Guided
  Decoding" (arXiv:2608.28229)**, all of which surfaced repeatedly and are probably relevant to
  compilation cost and lookahead.

---

# Sources consulted

Primary sources I fetched and read (or read via HTML rendering) in this session:

1. Willard & Louf, "Efficient Guided Generation for Large Language Models", arXiv:2307.09702 — https://ar5iv.labs.arxiv.org/html/2307.09702
2. Beurer-Kellner, Fischer, Vechev, "Guiding LLMs The Right Way" (DOMINO), ICML 2024, arXiv:2403.06988 — https://ar5iv.labs.arxiv.org/html/2403.06988
3. Dong et al., "XGrammar", arXiv:2411.15100 — https://arxiv.org/html/2411.15100
4. "XGrammar-2: Dynamic and Efficient Structured Generation Engine for Agentic LLMs", ACM CAIS 2026, arXiv:2601.04426 — https://arxiv.org/html/2601.04426v2
5. MLC blog, "XGrammar-2: Fast and Customizable Structured Generation for Tool Calling and Agents", 4 May 2026 — https://blog.mlc.ai/2026/05/04/xgrammar-2-fast-customizable-structured-generation
6. Geng et al., "JSONSchemaBench", arXiv:2501.10868 — https://arxiv.org/html/2501.10868v3
7. Microsoft Learn, "How to use structured outputs with Azure OpenAI in Microsoft Foundry Models" (updated 2026-08-24) — https://learn.microsoft.com/en-us/azure/foundry/openai/how-to/structured-outputs
8. OpenAI, "Structured model outputs" — https://developers.openai.com/api/docs/guides/structured-outputs
9. Anthropic, "Structured outputs" — https://platform.claude.com/docs/en/build-with-claude/structured-outputs
10. Google, "Structured output" (Gemini API) — https://ai.google.dev/gemini-api/docs/structured-output
11. llguidance `docs/json_schema.md` and `README.md` — https://github.com/guidance-ai/llguidance
12. llama.cpp `grammars/README.md` — https://github.com/ggml-org/llama.cpp
13. vLLM `vllm/v1/structured_output/backend_xgrammar.py` (main)
14. vLLM blog, "Structured Decoding in vLLM: a gentle introduction" — https://vllm.ai/blog/2025-01-14-struct-decode-intro
15. vLLM blog, "Inside vLLM: Anatomy of a High-Throughput LLM Inference System" — https://vllm.ai/blog/2025-09-05-anatomy-of-vllm
16. vLLM docs, "Structured Outputs" — https://docs.vllm.ai/en/latest/features/structured_outputs/
17. Red Hat Developer, "Structured outputs in vLLM: Guiding AI responses" — https://developers.redhat.com/articles/2025/06/03/structured-outputs-vllm-guiding-ai-responses
18. SGLang docs, "Structured Outputs" — https://docs.sglang.io/advanced_features/structured_outputs.html
19. SqueezeBits, "Guided Decoding Performance on vLLM and SGLang" — https://blog.squeezebits.com/guided-decoding-performance-vllm-sglang
20. outlines-core `src/json_schema/parsing.rs` — https://github.com/dottxt-ai/outlines-core
21. Outlines issues #654, #330, #1083 — https://github.com/dottxt-ai/outlines/issues/654
22. Park, Wang, Berg-Kirkpatrick, Polikarpova, D'Antoni, "Grammar-Aligned Decoding", NeurIPS 2024, arXiv:2405.21047 — https://arxiv.org/html/2405.21047v3
23. Tam et al., "Let Me Speak Freely?", EMNLP 2024 Industry, arXiv:2408.02442 — https://arxiv.org/html/2408.02442v1
24. .txt, "Say What You Mean: A Response to 'Let Me Speak Freely'" — https://blog.dottxt.ai/say-what-you-mean.html
25. "Hidden Biases in Conditioning Autoregressive Models", arXiv:2604.07855 — https://arxiv.org/html/2604.07855
26. "Trie Automata for Constrained Decoding over Large Finite Sets", arXiv:2608.12574 — https://arxiv.org/html/2608.12574
27. "TruncProof: A Guardrail for LLM-based JSON Generation under Token-Length Constraints", arXiv:2605.13076 — https://arxiv.org/abs/2605.13076
28. "Constraint Tax in Open-Weight LLMs", arXiv:2606.25605 — https://arxiv.org/html/2606.25605v1
29. "From Unstructured Recall to Schema-Grounded Memory: Reliable AI Memory via Iterative, Schema-Aware Extraction", arXiv:2604.27906 — https://arxiv.org/html/2604.27906v1
30. Pydantic docs, JSON Schema — https://docs.pydantic.dev/latest/concepts/json_schema/

Identified but NOT read in full (leads):
- Scholak, Schucher, Bahdanau, "PICARD", EMNLP 2021, arXiv:2109.05093
- Ugare et al., "SynCode", TMLR 2025, arXiv:2403.01632
- De Cao et al., "Autoregressive Entity Retrieval" (GENRE), ICLR 2021
- Zhang, Dang, Peng, Van den Broeck, "Tractable Control for Autoregressive Language Generation", ICML 2023 (PDF 403'd)
- Dang et al., "Mitigating Bias in Locally Constrained Decoding via Tractable Proposals", ICML 2026, arXiv:2606.01926
- Katsirelos, Narodytska, Walsh, "Decompositions of Grammar Constraints", arXiv:0903.0470; "Propagating Regular Counting Constraints", arXiv:1309.7145
- "Flexible and Efficient Grammar-Constrained Decoding", arXiv:2502.05111
- "Efficient Grammar-Constrained Decoding via Parser Stack Classification", arXiv:2608.03065
- "Earley-Driven Dynamic Pruning for Efficient Structured Decoding", arXiv:2506.01151
- "Stay Within Your Bounds: Distance-Guided Decoding for Guaranteed CFG Compliance", arXiv:2608.28229
- "The Hidden Cost of Structured Generation in LLMs: Draft-Conditioned Constrained Decoding", arXiv:2603.03305 (PDF would not extract)
- "Learning to Generate Structured Output with Schema Reinforcement Learning", ACL 2025
- LMSYS, "Fast JSON Decoding for Local LLMs with Compressed Finite State Machine" (jump-forward decoding) — https://www.lmsys.org/blog/2024-02-05-compressed-fsm/

END OF AGENT A REPORT.
