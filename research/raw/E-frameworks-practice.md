# E — Frameworks & Practice: Prior Art in Engineering for Partial/Delta Structured Output

Agent E research log. Focus: what real tools and products already do (not papers).
Verdict target: (a) already solved, (b) not worth solving, (c) genuinely open.

Status: COMPLETE for sections 2-6 (this file). Note on section 1 and section 7: this research run hit a session-limit interruption partway through. The sub-research on those two sections had already finished at that point and was filed by the coordinator directly as sibling files in this directory: research/raw/E2-pydantic-projection.md (section 1, Pydantic sub-schema projection mechanics) and research/raw/E1-live-value-sets.md (section 7, constrained decoding over a live/dynamic value set). Their content is NOT duplicated in this file — see those two files for that material. Everything below (sections 2 through 6) was produced by this agent, either via sub-forks that reported back before the interruption or via this agent's own direct research after resuming.

---


## Table of Contents

1. Pydantic mechanics for sub-schema projection and splicing — SEE research/raw/E2-pydantic-projection.md (filed separately)
2. Structured-output libraries audit (Instructor, BAML, Outlines, Guidance, Marvin, Mirascope, DSPy, LangChain, LlamaIndex) — in this file, section 2
3. Transport deltas vs semantic deltas — in this file, section 3
4. Real semantic-delta production systems + agent state-update mechanisms (LangGraph, CrewAI, AutoGen) — in this file, section 4
5. Form filling / slot filling (DST) as classical analogue — in this file, section 5
6. Tool calls with large/repeated arguments — protocol support for partial args — in this file, section 6
7. Constrained decoding over a live/dynamic value set — SEE research/raw/E1-live-value-sets.md (filed separately)

Sections appear in this file in the order their research completed, not strictly numeric order (2 continues further down, after 3/4, once the Instructor/BAML/Outlines/Guidance sub-audit and the DST section were redone directly by this agent). Each section header below is numbered so the pieces can be reassembled by number regardless of physical position.

(Sections appended below as sub-research completes. Each section retains per-claim source/URL/verification status per the assignment's output rules.)


---

## 6. Tool calls with large or repeated arguments — protocol support for partial args

**Headline finding: no vendor or protocol — MCP, OpenAI, Anthropic, or Gemini — supports semantic partial/incremental/delta-based tool-call arguments.** Every one of them requires the full argument object on every call, every time. What each vendor calls a "delta" (streaming) is a transport-level chunking of the same full generation, not a reduction in what the model generates. Clean, consistent negative result across all four ecosystems, checked from primary sources.

### 6.1 MCP (Model Context Protocol)

VERIFIED, primary: [MCP spec — Tools](https://modelcontextprotocol.io/specification/2025-06-18/server/tools).

`tools/call` request shape is fixed and total:
```json
{"jsonrpc": "2.0", "id": 2, "method": "tools/call",
 "params": {"name": "get_weather", "arguments": {"location": "New York"}}}
```
`params.arguments` is a plain JSON object matching the tool's `inputSchema` in full. No field/envelope/convention for referencing a prior call by ID and sending only changed keys. The spec's data types (`Tool`, `Tool Result`, `structuredContent`, `outputSchema`) validate a *complete* result against a *complete* schema in both directions. No mention of "patch"/"diff"/"delta"/"partial" in the tool-calling section.

### 6.2 OpenAI function/tool calling

VERIFIED, primary: [developers.openai.com/api/docs/guides/function-calling](https://developers.openai.com/api/docs/guides/function-calling).

- Streaming exposes `response.function_call_arguments.delta` events — JSON-string-fragment chunks of one single full generation, transport-level only.
- `previous_response_id` lets a new request continue a conversation and reuse **tool definitions**, but every tool call still carries a complete `arguments` object; the function-call-output round trip (`{"type": "function_call_output", "call_id": ..., "output": ...}`) has no "same as call X but change field Y" field.
- No diff-based or partial-args feature exists anywhere in this guide.

### 6.3 Anthropic tool use

VERIFIED, primary: [platform.claude.com/docs/en/agents-and-tools/tool-use/overview](https://platform.claude.com/docs/en/agents-and-tools/tool-use/overview).

- `tool_use` content block always carries a complete `input` object matching `input_schema`. No delta/patch mechanism in the round-trip.
- **Token-efficient tool use** (beta header `token-efficient-tools-2025-02-19`): mechanism itself is **NOT documented anywhere findable** — Anthropic states only the effect ("reduces output tokens by up to 70%, ~14% average" — [claude.com/blog/token-saving-updates](https://claude.com/blog/token-saving-updates), secondhand-corroborated). The dedicated doc page no longer resolves to its own content (redirects to a generic migration-guides fallback) and the feature is absent from the current tool-use overview navigation — consistent with it being scoped to Claude 3.7 Sonnet only, now retired ("has no effect on Claude 4+ models"). Treat as **legacy/dead**, not a live mechanism. Best-supported reading: an output-formatting/verbosity optimization (terser generation), not "send only changed fields vs. a previous call" — but documentation is too thin to fully rule out something cleverer either way.
- **Prompt caching vs. token-efficient tool use — precisely distinguished.** VERIFIED primary: [platform.claude.com/docs/en/build-with-claude/prompt-caching](https://platform.claude.com/docs/en/build-with-claude/prompt-caching). Tool definitions are cacheable via `cache_control: {"type": "ephemeral"}` on the last tool in the array. Direct quote: **"Output token generation: Prompt caching has no effect on output token generation. The response you receive is identical to what you would get if prompt caching were not used."** First request bills tool-definition tokens as `cache_creation_input_tokens`; later requests bill `cache_read_input_tokens`. Entirely an **input-side** optimization (server skips re-processing identical context) — unrelated to the model emitting a smaller/delta'd tool-call argument object. Do not conflate the two features.

### 6.4 Gemini function calling

VERIFIED, primary: [ai.google.dev/gemini-api/docs/function-calling](https://ai.google.dev/gemini-api/docs/function-calling).

Function calls return `{type, name, arguments}` as a complete object every time. Streaming chunks are transport-level only. No partial/incremental/diff mechanism. Parallel and compositional function calling are the only "multi-call" features; neither involves referencing or diffing against a prior call.

### 6.5 Explicit negative-result searches

Queries run: "incremental tool call arguments LLM", "partial function call arguments API", "diff tool call LLM API", "reuse previous tool call arguments LLM", "LLM tool call delta arguments", plus targeted GitHub-issue searches ("partial tool call", "diff-based tool call", "delta arguments" against openai/anthropic repos). No production feature, RFC, or open feature-request thread proposes semantic delta tool-call arguments. Every "delta"/"partial" hit was about streaming transport (chunked JSON reconstruction, `input_json_delta` parsing bugs in LiteLLM/LangChain/Ollama integrations) — never about generating less because a prior call already established most of the argument state. One search result noted OpenAI's API rejects a request with only a partial set of tool replies (400 error) — the API actively **enforces completeness** rather than tolerating partial state.

### Judgement (Agent E)

Strong evidence for verdict **(c) genuinely open** at the protocol/vendor layer. MCP, OpenAI, Anthropic, and Gemini were all designed around regenerating the whole argument object every call; none provide even a primitive for "same call, patch this field." The two adjacent features that look like progress — streaming argument deltas, prompt caching of tool schemas — are not: one saves latency to see tokens that are generated anyway, the other saves input-reprocessing cost, and neither reduces output tokens needed to re-specify an argument object. If LOCALISE→PROJECT→GENERATE→SPLICE is to reach the tool-calling surface, it has to be a client-side/application-layer wrapper — there is no vendor primitive to build on, and no evidence anyone is asking vendors for one.


---

## 3. Transport deltas vs semantic deltas

### 3.1 Anthropic streaming: `input_json_delta`

VERIFIED, primary: [Streaming Messages](https://platform.claude.com/docs/en/build-with-claude/streaming) (docs.claude.com, formerly docs.anthropic.com — auto-redirects), fetched directly.

Exact quote on what the delta carries:
> "The deltas for `tool_use` content blocks correspond to updates for the `input` field of the block. To support maximum granularity, the deltas are *partial JSON strings*, whereas the final `tool_use.input` is always an *object*."
>
> "You can accumulate the string deltas and parse the JSON once you receive a `content_block_stop` event, by using a library like Pydantic to do partial JSON parsing, or by using the SDKs, which provide helpers to access parsed incremental values."

Example event: `{"type":"content_block_delta","index":1,"delta":{"type":"input_json_delta","partial_json":"{\"location\": \"San Fra"}}}`.

Docs confirm the model emits input as it generates it, not faster/less of it:
> "Current models only support emitting one complete key and value property from `input` at a time. As such, when using tools, there may be delays between streaming events while the model is working."

**Fine-grained tool streaming** (`eager_input_streaming`, VERIFIED, [docs](https://platform.claude.com/docs/en/agents-and-tools/tool-use/fine-grained-tool-streaming)) makes the transport-only nature explicit:
> "Fine-grained tool streaming delivers a tool's input to your client as Claude generates it, without server-side buffering or JSON validation. Skipping the buffering step reduces the time to the first fragment of a large parameter..."
>
> "Without `eager_input_streaming`, the API buffers and validates each parameter value before streaming it back, so nothing prints for a large parameter until Claude has finished generating it."

The only variable this setting changes is when the client sees already-generated bytes; Claude still generates the complete parameter either way. `usage.output_tokens` in `message_delta` events is cumulative regardless of streaming mode — identical to a non-streamed call.

### 3.2 OpenAI streaming: function-call argument deltas

VERIFIED, primary: [Function calling guide](https://developers.openai.com/api/docs/guides/function-calling), fetched directly.

> "a series of events of type `response.function_call_arguments.delta` which will contain the delta of the arguments field"
>
> "When the model has finished calling the functions an event of type `response.function_call_arguments.done` will be emitted"

Framed purely as progress/UX: "you can surface progress by showing which function is called as the model fills its arguments, and even displaying the arguments in real time." Implementers are told to wait for full arguments before acting (per streaming events reference at developers.openai.com/api/reference/resources/responses/streaming-events — SECONDHAND, page exceeded fetch size limits, cross-checked via search).

VERIFIED, [Streaming responses guide](https://developers.openai.com/api/docs/guides/streaming-responses): "Streaming responses lets you start printing or processing the beginning of the model's output while it continues generating the full response." Explicit: generation is unaffected, only display timing changes.

### 3.3 Partial-JSON parsers (client-side, transport-only)

All PRIMARY, fetched directly from source repos/docs:

| Tool | Ecosystem | What it does | Key quote/detail |
|---|---|---|---|
| `partial-json-parser` (github.com/promplate/partial-json-parser, PyPI) | Python, zero-dep | Parses truncated JSON via Allow flags (STR/OBJ/ARR/NUM/BOOL...) | `loads('{"key": "v', STR \| OBJ)` returns `{'key': 'v'}` |
| `partial-json-parser-js` (github.com/promplate/partial-json-parser-js, npm: partial-json) | JS/TS | Same, JS port | "before receiving the last token of response, the JSON is broken... but we still want to stream the data to the user" |
| Pydantic `from_json(..., allow_partial=True)`, backed by jiter (github.com/pydantic/jiter) | Python | Parses incomplete JSON bytes against a Pydantic model mid-stream | Pydantic docs: "Pydantic's JSON parser offers support for partial JSON parsing... This feature is particularly beneficial for validating LLM outputs." jiter's own README does not itself prominently document partial_mode — the partial-parsing surface is documented at the Pydantic layer atop jiter. |
| Instructor `create_partial` (`instructor.Partial`) — python.useinstructor.com/concepts/partial/ | Python | Makes every field of a BaseModel Optional so a still-incomplete generation validates at every step | "Field level streaming provides incremental snapshots of the current state of the response model that are immediately useable." Full response is still generated in full. Explicit limitation: "Due to the streaming nature of the response model, we do not support validators." — cross-field/whole-object validators are dropped as the cost of accepting partial state. |
| `json_repair` (github.com/mangiucugna/json_repair, PyPI/npm) | Python + JS/TS ports | Repairs malformed/truncated JSON; stream_stable mode | "Repair malformed JSON from LLMs, APIs, logs, and user input." |

All five operate identically in kind: they take bytes the model already decided to emit in full, and let the client use a prefix before the stream closes. None reduce what the model computes or is billed for.

### 3.4 Explicit latency-not-tokens statement + pricing evidence

VERIFIED, Redis Inc. engineering blog, "Why your LLM app feels slow" (redis.io/blog/api-latency-llm-apps/, 2026-05-06, Jim Allen Wallace):
> "Streaming changes perception more than total runtime. Streaming and non-streaming responses can take the same wall-clock time but feel different because streaming lets users see tokens earlier. Without streaming, users see a multi-second blank screen, then everything at once. With streaming, that's a short initial wait plus progressive delivery."

Names the mechanism: TTFT (time-to-first-token) is a perception/UX metric layered on an unchanged autoregressive decode process — "LLM inference splits into a prefill phase... and a decode phase (generates tokens one at a time)."

Mechanical/pricing corroboration, both VERIFIED primary:
- Anthropic pricing (platform.claude.com/docs/en/about-claude/pricing): output tokens billed per-model at a flat MTok rate. Every pricing modifier is enumerated (prompt caching, batch -50%, fast mode premium, data residency 1.1x) — streaming is not among them. No streaming/non-streaming price differential exists.
- OpenAI pricing (developers.openai.com/api/docs/pricing): same structure, model-based per-token rates, no streaming-specific multiplier anywhere.

If streaming caused fewer generated tokens, it would be a pricing lever; it isn't one for either vendor — strong indirect proof streaming is purely a delivery/transport mechanism.

### Ready-to-use paragraph for the paper

Every major LLM API's "delta" is a transport delta, not a semantic one. Anthropic's `input_json_delta` and OpenAI's `response.function_call_arguments.delta` stream the same tool-call output the model would have produced in a single non-streamed response — Anthropic's own docs describe fine-grained tool streaming as removing "server-side buffering," which "reduces the time to the first fragment" of a value Claude has "finished generating" regardless of the setting. Client-side tools that make this usable before the stream closes — partial-json-parser, Pydantic/jiter's allow_partial=True ("particularly beneficial for validating LLM outputs"), Instructor's create_partial, and json_repair's stream_stable mode — all operate on bytes the model already committed to emitting in full; none reduce what is generated, and Instructor's Partial explicitly drops cross-field validators as the cost of accepting partial state. This is corroborated structurally: neither Anthropic's nor OpenAI's pricing pages carry any streaming-specific rate, because output-token billing is identical whether the response streams or not. Streaming is a latency win (lower time-to-first-token, better perceived responsiveness) with zero effect on tokens generated, generation time, or cost — the "delta" is in when bytes arrive at the client, never in how much computation happened upstream.

---

## 4. Real semantic-delta production systems + agent state-update mechanisms

### 4.1 Real semantic delta in production — headline finding

No production system was found. The only system that does what the delta problem describes (LLM generates an RFC 6902 JSON Patch against an existing object, applied mechanically, instead of regenerating the full document) is an academic research prototype, not a shipped product:

- **JSON Whisperer** (Lightricks + academic co-authors, EMNLP 2025). VERIFIED, arxiv.org/html/2510.04717v1, fetched primary. The LLM generates an RFC 6902 patch directly instead of regenerating the full JSON document. Their **EASE** encoding assigns arrays stable two-character keys (e.g. ax, cd) plus a display_order field specifically to avoid index-arithmetic errors LLMs make with positional array patches — a directly reusable trick for a SPLICE step. Reports 31% token reduction (42.5% cost reduction for Claude, 31.7% for GPT-4o-mini) vs. full regeneration, with edit quality within 5% of the full-regeneration baseline. Explicitly frames the problem the same way this research does: "current approaches regenerate entire structures for each edit." Dataset at github.com/emnlp2025/JSON-Whisperer/. Their own related-work section does not surface any production system doing this, corroborating the negative result independently.
- The paper's existence and framing (2025, "current approaches regenerate entire structures") is itself evidence the delta problem is recognized as open/unsolved as of last year, by researchers close to a real product company (Lightricks).

Practitioner-level (blog-tier, non-production) evidence people reach for this pattern anyway:
- devhelpr.com, "Generating and editing structured output (JSON) with LLMs." VERIFIED, fetched primary. Describes the JSON Patch (RFC 6902) approach directly: LLM emits an array of {op, path, value} operations, applied client-side with the fast-json-patch npm library. No schema-projection step, no discussion of constraining the LLM's patch generation against a sub-schema — the LLM is simply prompted to emit valid patch JSON and hopes for the best. Motivated by keeping a human in the loop, not by token/cost savings.
- theluk/llm-patcher (github.com/theluk/llm-patcher). VERIFIED, fetched primary. Close analog but for prose/text, not JSON/schema-constrained data: segments text into line/sentence IDs, has the LLM stream only "find/replace" operations against those IDs instead of the full text. 31 stars, 8 commits, a side project built on the Vercel AI Chatbot template, not production infrastructure. Evidence that "stable addressable IDs + patch ops" is a pattern independently reinvented for text; nobody has done the schema-constrained-data equivalent outside JSON Whisperer.

Red herring worth flagging: github.com/EndexAI/llm-patch. Despite the name and "structured outputs for llms" description, this is a stale, unmodified fork of Instructor (fork: true, 0 stars, 0 forks, last pushed 2024-06-24, homepage field points to python.useinstructor.com). No patch/diff functionality at all. Confirmed via GitHub API and README fetch. Surfaces near the top of "LLM patch" searches and could waste another researcher's time.

JSON Merge Patch (RFC 7396): searched specifically, found zero connection to LLM generation anywhere. Results are all generic RFC/library docs with no LLM angle. Clean negative.

### 4.2 Agent-framework state-update mechanisms (mechanism prior art, not memory)

**LangGraph — the closest shipped mechanism, with a critical caveat.** VERIFIED, docs.langchain.com/oss/python/langgraph/graph-api, fetched primary.

- Every node has signature State -> Partial State: it returns a dict containing only the keys it changed. LangGraph merges each changed key via new_value = reducer(left=current_state[key], right=node_update[key]).
- Reducer is declared per-field via Annotated: Annotated[list[str], add] or a custom merge function. No annotation means last-write-wins (full overwrite of that key).
- Command(update={"foo": "bar"}, goto="my_other_node") lets a node combine a partial state update with routing in one return value.
- Critical distinction: this is a build-time, developer-authored projection, not a runtime, LLM-chosen one. The set of keys that exist in State is fixed at graph-definition time by the developer. A node's code is written by the developer to return a specific subset of keys. The LLM inside a node can influence the value written to a key, but nothing in LangGraph lets the LLM itself decide which keys of State to touch at runtime the way a LOCALISE step would need (pick an arbitrary path into a schema, not a python dict key already enumerated in code by the developer). LangGraph solves SPLICE (merge a partial update into typed state, with per-field custom merge semantics) but not LOCALISE (an LLM autonomously choosing which region of a large/nested schema needs to change) or PROJECT (deriving a sub-schema to constrain generation of that fragment).
- Reported failure mode of the merge step (SECONDHAND, technetexperts.com blog, "LangGraph update_state Modifies Unexpected Fields," not cross-checked against LangGraph's own issue tracker, treat as anecdotal but plausible): calling update_state() with a partial dict against a historical/branched checkpoint can leak field values from the current thread's head state rather than the targeted parent checkpoint, because the default dict-merger fills in "missing" keys from ambient context. The fix shown is to always submit a fully-explicit dict (read full state, copy, mutate, write back) rather than trust the partial merge across branch points. Concrete evidence that "splice" is not free even in the simple dict-merge case, let alone under a nested schema with cross-field validators.

**CrewAI — no merge mechanism at all; direct imperative mutation.** VERIFIED, docs.crewai.com/concepts/flows, fetched primary.

- CrewAI Flow steps do not return partial updates. A @start()/@listen()-decorated method mutates self.state.field = value directly, in place, on a shared Pydantic (or dict) state object. No reducer, no merge function, no "partial dict gets combined with existing state" step anywhere.
- State updates are always hard-coded by the developer; the LLM never decides which fields of state to touch. Strictly weaker prior art than LangGraph for our purposes — it does not attempt the SPLICE abstraction at all, it is just "mutate a shared object."
- output_pydantic/output_json on a Task validate/coerce a task's full output against a Pydantic model. No partial-field mode.

**AutoGen (Microsoft) — no typed partial-merge mechanism found.** Searched microsoft.github.io/autogen docs and GitHub discussions. AutoGen's "state" concept is about serializing/restoring an agent's entire conversational state (save/load, JSON-serializable blob) across a pause, not partial/typed field updates. No reducer or merge-on-write concept found. SECONDHAND/aggregated search snippets only, not a full doc fetch — lower confidence than the LangGraph/CrewAI findings, but the absence is consistent across every query tried.

The successor **Microsoft Agent Framework** (learn.microsoft.com/en-us/agent-framework/workflows/) uses a Pregel-style bulk-synchronous-parallel model: typed executors connected by typed edges, processing in supersteps, passing typed messages downstream (VERIFIED via search snippets of primary pages). Structurally close to LangGraph's node model but message-passing rather than shared-state-with-reducers. No documented reducer/merge-on-partial-update mechanism analogous to LangGraph's Annotated[..., reducer] was found. One secondary blog's mention of "delta proposals rather than direct overwrites" for conflict resolution could not be corroborated in Microsoft's own docs on a follow-up check — flagged explicitly as an uncorroborated claim, not reported as a finding.

**OpenAI Agents SDK — explicitly no merge mechanism (clean negative, verified primary).** VERIFIED, openai.github.io/openai-agents-python/context/. RunContextWrapper.context is, in the docs' own words, "a plain local Python object" the developer creates, and which is read from, written to and called methods on — imperative mutation, no typed partial-update/reducer/merge concept, and explicitly not sent to the LLM (so the LLM cannot drive field-level updates to it even indirectly).

**Semantic Kernel — no finding.** Briefly searched per scope, not rabbit-holed. Nothing about typed partial-state merging specific to Semantic Kernel surfaced (results dominated by unrelated patent filings and an unrelated LangGraph blog post). Treat as "not found," not "confirmed absent" — would need a direct doc fetch to be a real negative result.

### 4.3 Negative-result queries tried (empty or near-empty)

- "JSON Merge Patch" RFC 7396 LLM generate structured output — zero LLM connection found, only generic RFC/library results.
- LLM "update only changed fields" structured output API — no framework or product found.
- "incremental structured output" LLM generation database record update — returned dbt incremental materialization (a data-engineering concept, unrelated) and unrelated constrained-decoding papers; nothing about incremental/delta generation of a single record.
- Semantic Kernel typed state partial update merge process — no relevant results.
- AutoGen Microsoft agent state typed partial update reducer — no reducer/typed-partial-merge concept found, only generic save/load whole-state serialization.
- OpenAI Agents SDK handoff typed state partial update context — confirmed negative, explicitly a plain mutable object.
- General "LLM JSON Patch production" / "LLM generate diff instead of full document" family: the only non-blog, non-toy hit across all phrasings was JSON Whisperer (a paper), reinforcing that this is research-stage, not deployed.

### Judgement (Agent E)

1. SPLICE (merging a generated fragment back into the full object) is the one sub-step with real shipped precedent — LangGraph's Annotated[Type, reducer] mechanism is a legitimate, production-grade answer to "how do I combine a fragment with an existing typed object," including custom per-field merge semantics beyond naive overwrite. An implementation of the paper's SPLICE step should look at LangGraph's reducer API as a design template, and at the technetexperts.com-reported bug as a warning about history/branching edge cases in naive dict-merge splicing.
2. LOCALISE and PROJECT have no production precedent found anywhere. Every agent framework with a "partial update" story (LangGraph; arguably Microsoft Agent Framework's typed messages) fixes the update surface at developer build time, not at LLM run time. Nobody ships "the LLM looks at a large schema and a change request, and decides at runtime which sub-region of the schema to constrain the next generation against." This is the load-bearing gap: the architecture's novelty is not SPLICE, it is LOCALISE+PROJECT chosen dynamically by the model itself.
3. JSON Whisperer is the strongest single piece of evidence that GENERATE-a-fragment is viable and valuable (31% token reduction, quality within 5% of full regen) — but it is paper-stage (EMNLP 2025), operates on raw JSON rather than a Pydantic/JSON-Schema-typed object, and does not do schema projection — it patches against the whole document's structure with array-stabilization tricks, not against a narrowed sub-schema. It validates the economic case for the delta problem without solving the LOCALISE/PROJECT half.
4. Verdict contribution: (c) genuinely open, specifically for the LOCALISE+PROJECT half of the pipeline. SPLICE is closer to solved-in-practice (borrow from LangGraph reducers / JSON Whisperer's EASE array encoding). The complete LOCALISE-PROJECT-GENERATE-SPLICE pipeline, run end-to-end and schema-driven with the model itself choosing the region, has no shipped analog in anything found — every framework either regenerates the whole object (the default everywhere) or hard-codes the update surface at development time (LangGraph, CrewAI, Microsoft Agent Framework). That gap between "developer pre-declares the partial-update surface" and "the model discovers it at runtime from the diff between old value and change request" is, as far as this search went, unaddressed in production engineering.

---

## 2. Structured-output libraries audit

Question for every library: can you generate ONE FIELD or one sub-object against ONLY its own (sub-)schema, and splice it back into a larger object? Is "update this existing object" a first-class operation, or is generation always whole-schema?

This part covers Marvin, Mirascope, DSPy, LangChain structured output, and LlamaIndex (Instructor, BAML, Outlines, Guidance follow in a separate pass below).

**Headline finding for this batch: none of the five support field-level or sub-schema-only generation, and none has a first-class "update this existing object" operation. All five are whole-object-generation-only.** Clean, consistent negative result.

### 2.1 Marvin (github.com/PrefectHQ/marvin, askmarvin.ai)

- `marvin.cast(data, target_type, instructions=...)` casts unstructured input to a target type (str to T). Always a fresh conversion; no existing-instance parameter. VERIFIED, askmarvin.ai/functions/cast.
- `marvin.extract(data, target, instructions=..., agent=..., thread=..., context=...)` transforms str to list[T]. No parameter for an existing/partial instance to fill or update. Docs explicitly say "for complex extraction patterns, consider creating a custom task" — no built-in decomposition primitive. VERIFIED, askmarvin.ai/functions/extract, primary doc fetched directly.
- `marvin.generate(...)` generates structured objects from a description — fresh whole-object generation. VERIFIED via search snippet (askmarvin.ai/functions/generate), consistent with extract/cast pattern.
- `MarvinModel` (marvin.utilities.models) is a base Pydantic model for internal Marvin use (strictness, Pydantic v2 features). No sub-schema projection or partial/optional-ising utility. VERIFIED, askmarvin.ai/api-reference/marvin-utilities-models.
- Marvin 3.0 runs on Pydantic AI for LLM interaction (SECONDHAND, search snippet, not deep-verified).
- CANNOT do: no field-level generation, no sub-schema projection, no "fill this one field of an existing object" mode, no patch/update operation anywhere in the public API surface (extract/cast/generate/@ai_model). Confirmed by direct primary-source reads of the extract and cast function-reference pages and the README.
- Negative queries tried with nothing found: "Marvin partial extraction," "Marvin update existing model," "Marvin patch Pydantic instance."

### 2.2 Mirascope (mirascope.com, github.com/Mirascope/mirascope)

- `@llm.call(provider, model, response_model=Book, stream=True)` — response_model generation is always whole-object. VERIFIED, fetched directly from the primary Structured Outputs guide (mirascope.com/docs/v1/guides/getting-started/structured-outputs): "the output is now a Book instance" — no merge-with-existing-data language, no field-subset example anywhere on the page.
- Streaming (stream=True plus response_model) yields progressively-filling instances of the same object (title=None author=None, then title='...' author='Patrick', then full object), exposed via constructed_response_model once exhausted. This is Instructor-style transport-level partial-JSON re-parsing of one ongoing generation, not separate per-field LLM calls — the model still generates the whole object once, the client just sees it fill in. SECONDHAND for the exact mechanism (search-snippet synthesis; mirascope.com/docs/mirascope/learn/streams and mirascope.com/learn/streams both 404'd on direct fetch), but the behavior description is corroborated by two independent search-result summaries and consistent with how every other framework's "partial streaming" works.
- stream={"partial_tools": True} streams intermediate partial tool-call arguments/deltas — same transport-delta caveat. SECONDHAND (search snippet, primary doc page 404'd).
- CANNOT do: no single-field-against-its-own-schema generation, no patch/update of an existing instance. Verification gap flagged: the "no partial support" conclusion rests on one primary page plus consistent secondhand corroboration, not an exhaustive doc crawl (the newer /docs/mirascope/learn/* doc tree persistently 404'd).
- Negative queries tried: "Mirascope field-level generation," "Mirascope update existing response_model," "Mirascope patch Pydantic object."

### 2.3 DSPy (dspy.ai, github.com/stanfordnlp/dspy)

- Signatures (dspy.Signature, inline string form "location, mood -> haiku, haiku_title", and class-based Signature subclasses) define input/output field sets as one unit. VERIFIED, dspy.ai/getting-started/expanding-signatures/, fetched directly.
- Pydantic-typed output fields: DSPy signatures accept "richer types – like Pydantic models, TypedDicts, or dataclasses" as field annotations; per the diving-deeper doc, "types are declared here but coerced elsewhere" — parsing happens in dspy/adapters/utils.py::parse_value, with retry-on-raw-string-if-Pydantic-validation-fails. VERIFIED, dspy.ai/diving-deeper/signatures-in-depth/, fetched directly — mechanism confirmed, a worked BaseModel-as-output-field code example was not found on the page.
- No sub-field generation primitive: nothing in Signatures, TypedPredictor, or the adapter layer lets you generate one output field alone against its own schema, or re-generate/patch a single field of an already-produced output. Both fetched pages have no such example. DSPy PR #1655 (TypedPredictorSignature built from Pydantic models — SECONDHAND, GitHub PR title/description only) is about building a whole signature from a Pydantic model's fields, not projecting a sub-schema.
- Manual multi-call decomposition exists as a pattern, not a schema-driven feature. DSPy's "Composing Modules" doc (dspy.ai/getting-started/composing-modules/ — SECONDHAND, search-snippet only) describes agent-style pipelines: a dspy.Predict loop for tool selection, then a ChainOfThought "synthesis" module assembling a final answer from prior steps, plus "when one LM call has too much variance, DSPy can sample several calls, then pick or combine them." This is hand-written task decomposition (the developer writes a forward() method calling multiple modules and combining results in Python) — the general composability pattern common to all agent frameworks, not an automatic schema-projection mechanism. Relevant as prior art for "assemble a big structured result from several small LLM calls," but it does not touch the sub-schema-constrained-decoding half of the problem — DSPy does not derive a sub-call's output schema from the parent schema; the developer defines each sub-call's Signature independently by hand.
- CANNOT do: no automatic sub-schema projection, no field-level constrained regeneration, no patch/update-existing-output operation. Confirmed via two directly-fetched primary pages.
- Negative queries tried: "DSPy field-level generation," "DSPy update existing signature output," "DSPy partial Pydantic model," "DSPy sub-schema."

### 2.4 LangChain (with_structured_output(), PydanticOutputParser)

- with_structured_output() full signature, VERIFIED, fetched directly from reference.langchain.com/python/langchain-core/language_models/chat_models/BaseChatModel/with_structured_output:
  with_structured_output(self, schema, *, include_raw=False, **kwargs) -> Runnable[LanguageModelInput, dict|BaseModel]
  Docstring: "Model wrapper that returns outputs formatted to match the given schema." No parameter accepts an existing instance, a field name, or a schema subset — schema is always the complete target schema. include_raw only toggles whether the raw LLM message is returned alongside the parsed object.
- create_agent(..., response_format=...), VERIFIED, docs.langchain.com/oss/python/langchain/structured-output — same story: response_format takes a full type/schema (ToolStrategy[T], ProviderStrategy[T], type[T], or JSON Schema dict); result lands whole in structured_response. The fetched page states there is no "update existing object" or "fill single field" operation, and suggests the only workaround is to "restructure your schema to contain only desired fields" (manually author a smaller schema yourself) or do "custom post-processing logic outside LangChain's native structured output."
- Legacy PydanticOutputParser — same whole-schema pattern (format-instructions string built from full model_json_schema(), parses full JSON back into the full model). Not independently deep-verified this pass, but consistent with the two pages fetched.
- Adjacent, not the same thing: LangChain's extraction how-to material (extraction_long_text — SECONDHAND, search snippets only, notebook 404'd on both WebFetch and gh api) describes running full, independent, whole-schema extractions per input chunk in parallel via .batch(), then combining the list of results in application code, not via the LLM. This is the "bulk table" scenario's input side (splitting a long document) rather than the output-schema side (splitting a large target schema); each chunk still gets the entire target Pydantic schema, applied to a smaller slice of input text, and the merge is naive concatenation in Python.
- CANNOT do: no field-level generation, no sub-schema-only constrained decoding, no patch/update-existing-instance operation, in either the modern with_structured_output/create_agent APIs or (by architectural implication) the legacy PydanticOutputParser/extraction-chain APIs.
- Negative queries tried: "LangChain partial structured output field," "LangChain update existing Pydantic instance," "LangChain patch structured output."

### 2.5 LlamaIndex (docs.llamaindex.ai / developers.llamaindex.ai)

- as_structured_llm(OutputClass), VERIFIED, developers.llamaindex.ai/python/framework/understanding/extraction/structured_llms/, fetched directly — wraps any LLM into a "structured LLM" that always responds with instances of OutputClass. Usage: sllm = llm.as_structured_llm(Invoice). Supports chat/stream/achat/astream "exactly like a regular LLM class." The streaming variants are, by every indication and by analogy to every other framework in this survey, transport-level progressive fill of a single whole-object generation, not field-level sub-calls — but this specific mechanism claim is inference by analogy, not directly verified (the page does not spell out the streaming mechanism explicitly); flagged.
- structured_predict(...) — a convenience method on every LLM class for one-line prompt-template + structured-output calls. Existence and purpose VERIFIED at a high level; full signature not reached (referenced a separate "Structured Prediction" page not fetched).
- PydanticProgram family (text-completion and function-calling variants), VERIFIED, developers.llamaindex.ai/python/framework/module_guides/querying/structured_outputs/pydantic_program/, fetched directly — "a generic abstraction that takes in an input string and converts it to a structured Pydantic object type." All three sub-types (Text Completion, Function Calling, Prepackaged) are complete-object conversions. No partial/patch mode documented.
- FunctionCallingProgram.from_defaults(output_cls=Album, prompt_template_str=..., verbose=True), VERIFIED, developers.llamaindex.ai/python/examples/output_parsing/function_program/, fetched directly, exact code quoted from page — output_cls is always the full target class; no field-subset or existing-instance parameter exists in the constructor.
- The fetched page's own suggested workaround for wanting field-level control: "define a smaller Pydantic model containing only the field you need" — the user manually authors a narrower schema themselves; LlamaIndex provides no automated sub-schema projection or splicing mechanism to do this from a parent schema.
- CANNOT do: no built-in sub-object/single-field generation against an isolated schema, no update/patch-existing-object operation, across as_structured_llm, structured_predict, and the entire PydanticProgram family. Confirmed via three independently-fetched primary doc pages, all consistent.
- Not reached this pass (flagged for follow-up): LlamaIndex's "Guidance Pydantic Program" wrapper (developers.llamaindex.ai/python/examples/output_parsing/guidance_pydantic_program/) — LlamaIndex's integration with Guidance's hole-filling model might expose more granular control than LlamaIndex's native programs, since Guidance itself supports interleaved fill-the-hole generation (see section 2, Guidance subsection below). Not fetched in this pass.
- Negative queries tried: "LlamaIndex partial Pydantic program," "LlamaIndex update existing structured object," "LlamaIndex patch field."

### 2.6 Summary table (this batch)

| Library | Field/sub-object generation against isolated schema? | Update/patch existing instance? | Verification |
|---|---|---|---|
| Marvin | No | No | Primary (extract, cast, models API-ref pages) |
| Mirascope | No | No | Primary (v1 structured-outputs guide) + secondhand corroboration for streaming mechanism; newer doc tree partially unreachable (404s) |
| DSPy | No (manual multi-module composition exists but is hand-authored, not schema-driven) | No | Primary (expanding-signatures, signatures-in-depth pages) |
| LangChain | No | No | Primary (reference.langchain.com signature page, docs.langchain.com structured-output page) |
| LlamaIndex | No | No | Primary (structured_llms, pydantic_program, function_program pages, all fetched directly) |

Every one of the five libraries treats structured generation as atomic and whole-schema. The only "partiality" any of them exposes (Mirascope, and by inference LlamaIndex) is transport-level streaming of a single ongoing whole-object generation — the model still generates every token of the full object, the client just observes the parse progressively. Not a semantic delta; does not save tokens/cost/latency (consistent with section 3's transport-vs-semantic-delta finding).

The one recurring manual workaround across libraries (LangChain, LlamaIndex) is: the user hand-authors a smaller Pydantic model containing only the fields they want, and re-runs a full (but now smaller-schema) generation call. No library automates deriving that smaller model from a path/pointer into the parent schema, and no library then splices the result back into a parent instance — that composition is left entirely to user code in every case surveyed.


---

## 2 (continued). Instructor and BAML in depth

Redone directly by this agent after the original Instructor/BAML/Outlines/Guidance sub-fork died mid-run to a session-limit interruption (it got as far as confirming Outlines before dying, without returning usable content, so all four are covered fresh here).

### 2.7 Instructor (python.useinstructor.com, PyPI: instructor)

- Exact current API: **`client.create_partial(response_model=MeetingInfo, messages=[...], stream=True)`**. VERIFIED, fetched directly from python.useinstructor.com/concepts/partial/. For models using `Literal` types, a `PartialLiteralMixin` must also be mixed in (`from instructor.dsl.partial import PartialLiteralMixin`), because "jiter throws an error otherwise if it encounters an incomplete Literal value while it's being streamed in."
- Scope confirmed precisely: this is **always a partial view of one single whole-object generation**, not independent generation of separate fields against separate schemas. Docs: "Field level streaming provides incremental snapshots of the current state of the response model," and "you can iterate over these incremental updates. The last value yielded by the generator represents the completed extraction." Mechanically this works by making every field of the target `BaseModel` `Optional` under the hood and re-parsing the accumulating JSON string on each chunk (via jiter's partial-JSON support) — the model is still asked to produce, and does produce, the complete object in one generation call; `create_partial` only changes what the *client* is allowed to treat as valid mid-stream.
- No "update this existing object" or "regenerate just this field" operation exists anywhere in Instructor's docs. Confirmed by direct fetch — no mention found.
- Explicit limitation, verbatim: "Due to the streaming nature of the response model, we do not support validators since they would not be able to be applied to the streaming response." This is Instructor hitting the exact "global constraint residue" problem head-on and simply dropping cross-field/whole-object validation as the price of partial support, rather than solving it — directly relevant to the paper's revalidate-globally step.

### 2.8 BAML (BoundaryML) — docs.boundaryml.com, github.com/BoundaryML/baml

**Schema language.** BAML types are defined in `.baml` files using a class-based syntax with field-level annotations, e.g. (VERIFIED, docs.boundaryml.com/guide/introduction/what-is-baml, fetched directly):
```
class WeatherAPI {
  city string @description("the user's city")
  timeOfDay string @description("As an ISO8601 timestamp")
}
```
Every BAML "function" is a typed prompt: typed parameters in, a typed return value out, compiled to native types in the target language's generated client (`baml_client`).

**Schema-Aligned Parsing (SAP).** VERIFIED via WebSearch of docs.boundaryml.com and boundaryml.com/blog/schema-aligned-parsing (secondhand for the blog post itself, but the mechanism description is consistent and specific): SAP is a parser, not a generation-time constraint — it runs AFTER the LLM has produced raw output and repairs/aligns it to the target schema using "custom edit distance algorithms." It fixes broken JSON (missing brackets, trailing commas), strips markdown code-fence wrapping, and tolerates chain-of-thought reasoning text preceding the actual structured answer. Reported effect: "achieves valid, type-correct objects 98% of the time with no post-processing," and claims "SAP + GPT-3.5 turbo beats GPT-4o + structured outputs" on cost/accuracy. SAP is squarely a robustness/error-tolerance mechanism (closer in kind to `json_repair`, section 3) — it does not do sub-schema projection or partial generation; it is about salvaging one full generation that came back malformed, not about generating less.

**Streaming / partial types.** VERIFIED, docs.boundaryml.com/guide/baml-basics/streaming, fetched directly. BAML's code generator emits a parallel `partial_types` module: "By default, BAML will convert all Class fields into nullable fields, and fill those fields with non-null values as much as possible given the tokens received so far." Two attributes control this per-field or per-class:
- `T` (no attribute) streams as `Partial[T]?` — nullable and partial.
- `T @stream.done` streams as `T?` — nullable, but only ever appears once fully complete (never a partial value).
- `T @stream.not_null` streams as `Partial[T]` — always present once any sub-field is known, but may still be partial.
- `T @stream.done @stream.not_null` streams as `T` — always present and always complete.

Confirmed explicitly to be **transport-level progressive parsing of ONE ongoing generation**, not independent sub-object generation: "BAML gives you fine-grained control of how it fixes this partial JSON and transforms it into a series of semantically valid partial objects" — a single LLM call's output, incrementally re-parsed and re-validated against nullable variants of the real schema as bytes arrive. No isolated field generation, no "update this object" operation documented anywhere on the page.

**TypeBuilder / `@@dynamic` — runtime schema construction, but additive-only.** VERIFIED, docs.boundaryml.com/guide/baml-advanced/dynamic-types and docs.boundaryml.com/ref/baml_client/type-builder, fetched directly. This is BAML's closest analogue to Pydantic's `create_model()` — a way to build/modify a schema at runtime instead of only at `.baml`-file compile time, for cases like "categories pulled from a database" (directly relevant to section 7's live-value-set question, filed separately in E1). Mechanics:
```
enum Category {
  VALUE1
  VALUE2
  @@dynamic
}
```
```python
from baml_client.type_builder import TypeBuilder
tb = TypeBuilder()
tb.Category.add_value('VALUE3')
tb.User.add_property('email', tb.string())
```
Confirmed this is **purely additive**: `add_value`, `add_property`, and constructing wholly new types are the only operations found. No evidence anywhere in the docs of using TypeBuilder to carve a PROJECTION (subset) out of an existing type, constrain generation to that sub-schema alone, and splice the result back — the opposite direction (narrowing) is not what TypeBuilder is for. All types added via TypeBuilder must be reachable from the BAML function's declared return type; unreferenced standalone types have no effect.

**Open gap, directly relevant: dynamic types and semantic streaming don't compose.** VERIFIED, github.com/BoundaryML/baml/issues/2980, fetched directly, status OPEN as of 2026-09-07, no maintainer response or linked PR. The reporter wants to attach `@stream.done`/`@stream.not_null` semantic-streaming annotations to types built at runtime via TypeBuilder, the same way they work on statically `.baml`-defined classes. Currently: "streaming metadata compiles without errors... but produces no runtime effect on dynamic types" — an "asymmetric functionality" where static classes fully support semantic streaming but dynamic (runtime-constructed) types do not. This is a concrete, citable, currently-open instance of exactly the seam this research project is investigating: the tooling for "generate against a schema known at compile time" and the tooling for "generate against a schema built at runtime" are two separate code paths in a real, actively-maintained production framework, and they have not yet been unified even for the easier case (adding streaming semantics to an additively-extended schema) — let alone for the harder case (a schema narrowed/projected at runtime, which BAML does not support at all).

### Judgement so far (Instructor + BAML)

Both libraries confirm the section 3 finding from a different angle: every "partial" feature in shipped structured-output tooling is a transport-level view into one whole-object generation (Instructor's `Optional`-ising re-parse, BAML's `partial_types` progressive nullable-fill), and both explicitly drop cross-object/cross-field guarantees to get it (Instructor: no validators during streaming; BAML: SAP repairs shape but doesn't reason about semantic cross-field constraints, and `@stream.not_null` only gates on structural presence, not validity). Neither library treats "generate one field/sub-object against its own isolated schema, then splice" as an operation at all. BAML's TypeBuilder is the most interesting adjacent capability in this entire audit so far because it does runtime schema construction in a shipped, actively-developed product — but it only grows schemas (add a field, add an enum value), and issue #2980 is direct, dated (open, unresolved) evidence that even BAML's own maintainers have not yet connected runtime-constructed schemas to the rest of their partial-generation machinery.

---

## 2 (continued). Outlines and Guidance in depth

### 2.9 Outlines (dottxt-ai/outlines, dottxt-ai.github.io/outlines)

**Current API.** VERIFIED, dottxt-ai.github.io/outlines/reference/generation/json/, fetched directly. Historic (pre-1.0) API: `generate.json(model, User)` where `User` is a Pydantic `BaseModel`, a JSON-schema string, or even a plain function signature (Outlines will constrain output to valid kwargs for that function and let you call it: `generator = generate.json(model, add); result = generator(prompt); add(**result)`). VERIFIED via WebSearch of the v1.0.0 release notes (github.com/dottxt-ai/outlines/releases/tag/1.0.0): as of Outlines 1.0, the `models.*`/`generate.*` module-function style is deprecated in favor of `from_openai(...)`, `from_transformers(...)` style loaders that wrap a native inference-library client/engine, and you call the loaded model object directly with a schema rather than building a separate `generate.json(...)` generator — a naming/ergonomics change, not a capability change relevant to this research.

**Fragment/sub-schema generation: not supported.** No mechanism found, in either API era, for constraining generation to a schema fragment carved out of a larger nested model, or for field-at-a-time/resume-mid-object generation. Every documented path takes one complete schema (Pydantic model, JSON-schema string, or function signature) and produces one complete object matching it in one generation call.

**Dynamic schema construction — real, citable friction, now partially addressed.** VERIFIED via GitHub API (`gh api repos/dottxt-ai/outlines/issues/1383`), fetched directly, full issue body and comment thread read. Issue #1383, "Dynamic schema creation" (opened 2025-01-18 by @just-cameron, a CONTRIBUTOR, closed 2025-02-07 via PR #1390). This is a first-party account of hitting almost exactly the projection/runtime-schema problem this research is about, worth quoting at length because it is unusually on-point:

> "Pydantic can make it difficult to program with Outlines when the schema must be modified in-place... When you give this to the model, it will make up an ID that may not be unique. What I would like to do instead is: `class CalendarEvent(BaseModel): id: Literal['abc']; description: str; date: datetime`. This will force the model to use the ID I provide... This is difficult to do, currently. I wrote an example of how to dynamically create Pydantic models, but it is quite clunky and does not have a convenient user interface."

The issue also names three more scenarios that map directly onto this research's motivating cases: "changing enums within larger classes" (our LOCALISE+PROJECT case), building schemas conditional on a prior model response (our "ask the LLM to work out which part is needed" case), and wanting a plain dict instead of "a gigantic models/ directory packed with tiny Pydantic classes" for throwaway sub-schemas (our SPLICE-target ergonomics problem). The reporter's own workaround code (included in the issue, quoted in full below) uses **`pydantic.create_model()`** to build a parameterized model at runtime — i.e., the community's own answer to "how do I get Outlines to constrain against a schema I only know at runtime" is exactly the Pydantic `create_model()` mechanism documented in section 1 (filed separately as E2-pydantic-projection.md), self-described as "clunky":
```python
from pydantic import create_model
def LimitedList(max_items: int = 5, min_items: int = 0):
    return create_model(
        "LimitedList",
        items=(list[Task], Field(max_length=max_items, min_length=min_items))
    )
limited_class = LimitedList(max_items=10, min_items=9)
list_generator = outlines.generate.json(model, limited_class)
```
**Resolution reveals a scope mismatch worth flagging.** The issue was closed by PR #1390, "Add `genson` integration for json generation" (VERIFIED, `gh api repos/dottxt-ai/outlines/pulls/1390`, body: "This PR aims at integrating support of the `genson` package (in `generate.json`) to be able to use dynamic json schema generation as proposed in #1383"). **GenSON is a schema-inference library — it derives a JSON Schema FROM example data/objects, not a mechanism for projecting a sub-schema OUT OF an existing parent schema.** So Outlines' own maintainers, faced with a user request that included "changing enums within larger classes" (a projection ask), resolved the issue by shipping a different capability (schema-from-examples) that does not address the projection/narrowing use case at all. As far as this research can determine, Outlines still has no built-in projection primitive as of this writing — `create_model()` by hand remains the state of the art, exactly as the Pydantic mechanics section (E2) would predict.

**Negative-result queries tried, no further hits:** "outlines constrain generation sub-schema fragment", "outlines partial JSON schema generation field", "outlines resume generation existing object".

### 2.10 Guidance (guidance-ai/guidance) — the most relevant library found in this audit

**Pydantic/JSON-schema-constrained generation confirmed.** VERIFIED, github.com/guidance-ai/guidance README, fetched directly:
```python
from pydantic import BaseModel, Field
from guidance import json as gen_json

class BloodPressure(BaseModel):
    systolic: int = Field(gt=300, le=400)
    diastolic: int = Field(gt=0, le=20)
    location: str = Field(max_length=50)
    model_config = dict(extra="forbid")

lm += gen_json(name="bp", schema=BloodPressure)
```
README states plainly: "A JSON schema is actually a context free grammar, and hence it can be used to constrain an LLM using Guidance" — confirming `schema=` accepts a JSON Schema directly, not only a Pydantic class, so a hand-projected sub-schema (e.g. from `create_model()`, per section 1/E2) can be fed to `gen_json` with no extra glue code.

**The interleaved fixed-text/generation model — the core mechanism, confirmed with primary examples.** VERIFIED, raw README fetch. Guidance's `lm` objects are immutable; every `+=` returns a new state built from the previous one plus either literal text or a constrained-generation call:
```python
lm += "You are a teenager"
lm += "How old are you?"
lm += gen("lm_age", regex=r"\d+", temperature=0.8)
```
```python
lm += f"<{tag}>"
lm += _gen_text()
lm += f"</{tag}>"
```
```python
lm += question + "\n"
for i, choice in enumerate(choices):
    lm += f"{chr(i+ASCII_OFFSET)} : {choice}\n"
lm += select([chr(i + ASCII_OFFSET) for i in range(len(choices))])
```
Because state is immutable and additive, anything already in `lm` before a `gen()`/`select()` call is a **true fixed prefix** — it is not re-generated, re-sampled, or re-validated; only the newly-appended `gen(...)`/`select(...)` span is sampled by the model, constrained against whatever grammar/regex/schema it's given. This mechanically is a general-purpose "hole filling" primitive: nothing in the API restricts the literal spans to being plain prose. **Given this, hand-writing exactly the pattern this research needs — `lm += '{"field1": "foo", "field2": ' + gen("field2", regex=...) + '}'` — is a direct, unremarkable application of the demonstrated primitives**, not a stretch; the README's own HTML-tag and multiple-choice examples are structurally identical (fixed delimiter, hole, fixed delimiter).

**But: no dedicated "edit one field of existing JSON" cookbook example was found.** This capability is implied and mechanically straightforward from the primitives shown, not demonstrated as a named pattern anywhere I could locate in the README or via search of the repo's notebooks/cookbook. So the honest finding is two-sided: Guidance is the only library in this entire audit whose primitives naturally compose into the LOCALISE-PROJECT-GENERATE-SPLICE pattern by hand (fixed prefix = everything before the edited field, `gen_json(schema=projected_sub_schema)` = the GENERATE step against a PROJECT-ed schema, and the immutable `lm` object itself = a natural SPLICE point) — but nobody, including Guidance's own maintainers, appears to have packaged this into a documented, schema-driven "patch this one field of a larger typed object" feature. It is buildable, not built.

**`select()` with runtime-built option lists.** VERIFIED, README: `lm += select(["A", "B", "C", "D"], name="model_selection")`. `select()` takes a plain Python list, so a runtime/live-data-built list is trivially possible mechanically (no special API needed — ordinary Python) — but the README itself shows only static literal lists, no example explicitly framed around a live/database-sourced option set. (This question is primarily section 7's territory, filed separately as E1-live-value-sets.md — noted here only because it surfaced directly while reading the same README passage as `gen_json`/`select`.)

**Negative-result queries tried:** "guidance-ai JSON editing cookbook", "guidance-ai partial regeneration existing object", "guidance-ai update one field pattern" — no dedicated example or tutorial found for any of these beyond the general-purpose primitives described above.

### Judgement (Outlines + Guidance)

Outlines is a clean negative for this research's core question (no fragment/sub-schema generation, dynamic-schema issue resolved with a scope-mismatched feature) but issue #1383 is one of the best pieces of qualitative evidence found in this whole audit that real users hit this exact wall and reach for `create_model()` as the only, "clunky" way out — independent, practitioner-sourced corroboration of the Pydantic-mechanics section's central mechanism. Guidance is the one library in the entire structured-output survey (Instructor, BAML, Outlines, Marvin, Mirascope, DSPy, LangChain, LlamaIndex, and Guidance itself) whose primitives are general enough that a developer COULD hand-roll the full LOCALISE-PROJECT-GENERATE-SPLICE pipeline on top of them today, entirely in userland, using only documented public API (`gen_json(schema=...)` against a hand-projected sub-schema, spliced in via ordinary string/dict manipulation of the immutable `lm` state). That nobody has shipped this as a first-class, schema-driven "patch one field" feature — in Guidance or anywhere else surveyed — is itself the headline finding: the low-level mechanism has existed in a popular, actively-maintained library for years, and the higher-level orchestration (LOCALISE: which field changed; PROJECT: derive its sub-schema automatically from the parent; SPLICE: merge back with revalidation) has still not been built and packaged by anyone. This is strong support for verdict (c), genuinely open, specifically at the orchestration layer rather than the low-level constrained-decoding layer.

---

## 2 (summary). Structured-output library audit — consolidated across all nine libraries

| Library | Field/sub-schema generation in isolation? | "Update existing object" first-class op? | Closest relevant capability |
|---|---|---|---|
| Instructor | No (whole-object only; "partial" = transport re-parse) | No | `create_partial()` streaming; drops validators |
| BAML | No | No | `TypeBuilder`/`@@dynamic` — additive-only runtime schema growth; SAP is post-hoc repair, not projection |
| Outlines | No | No | Dynamic-schema issue #1383 resolved with GenSON (schema-from-examples), not projection; community workaround is raw `create_model()` |
| Guidance | Not packaged, but the primitives compose to build it by hand | No (buildable, not built) | `gen_json(schema=...)` + immutable fixed-prefix `lm +=` composition — the strongest raw material found in this survey |
| Marvin | No | No | None found |
| Mirascope | No | No | Transport-level partial streaming only (Instructor-like) |
| DSPy | No (manual multi-module composition exists, hand-authored per call) | No | `Signature` composition pattern — developer manually decomposes, not schema-driven |
| LangChain | No | No | Documented workaround: hand-author a smaller Pydantic model yourself |
| LlamaIndex | No | No | Same hand-authored-smaller-model workaround; Guidance-backed program variant not explored |

**Cross-library pattern, stated once:** every library treats structured generation as atomic and whole-schema per call. Where "partial" or "streaming" exists (Instructor, BAML, Mirascope, likely LlamaIndex), it is uniformly a transport-level progressive reveal of ONE generation already committed to producing the full object — never a second, smaller, independently-schema-constrained generation call for a sub-part. Where users have wanted true sub-schema projection (Outlines #1383) or runtime schema flexibility (BAML TypeBuilder issue #2980), maintainers have shipped adjacent-but-different capabilities (schema-from-examples, additive schema growth) rather than the projection/narrowing operation itself. The one recurring manual workaround, named explicitly in LangChain's and LlamaIndex's own docs, is: the developer hand-writes a smaller Pydantic model containing only the fields wanted, and re-runs a full (now smaller-schema) call — i.e., humans already do the PROJECT step by hand, in code, ahead of time; nobody has automated deriving that smaller model from a path/pointer into a parent schema at runtime, and nobody splices the result back into a parent instance for you.

Verdict contribution from this section: **(c) genuinely open**. The GENERATE-against-a-sub-schema step is trivially available everywhere (any of these libraries will happily generate against a small hand-written model). What is missing everywhere, without exception, is the automation of PROJECT (deriving that small model from a parent schema plus a path/change-request) and the packaging of LOCALISE+PROJECT+GENERATE+SPLICE as one operation. Guidance is the only library whose low-level primitives are general enough to build this today without fighting the framework; that nobody has is itself evidence of an open gap rather than a solved-and-adopted problem.

---

## 5. Form filling and slot filling — the closest classical analogue

Bottom line up front: **this is the strongest "already solved, in older vocabulary" finding in this entire audit.** Dialogue State Tracking (DST) research named and solved the "update one slot, keep the rest, stay coherent" problem years before LLM-era structured output existed, using precisely a LOCALISE (which slot changed) + GENERATE (a value for just that slot) + SPLICE (merge into the running belief state) decomposition — and at least one current production dialogue framework (Rasa) ships this pattern today, with an LLM in the loop.

### 5.1 Classical DST: two competing formulations, named precisely

**Full-state-every-turn (the "regenerate everything" baseline).** TRADE — Transferable Multi-Domain State Generator, Wu et al., ACL 2019, arxiv.org/abs/1905.08743 (VERIFIED via search of the paper's own abstract/description, not a full text fetch — SECONDHAND for exact wording, but the architecture claim is corroborated across every source found). TRADE's "state generator" module regenerates (domain, slot, value) triplets using a copy mechanism against the accumulated dialogue history, run fresh each turn. TRADE is a canonical, heavily-cited DST baseline, and it is architecturally the direct analogue of "regenerate the whole structured object every time" — worth stating plainly in the paper as evidence that even DST research defaulted to full-state regeneration first, same as today's LLM structured output.

**Turn-level state-change / delta prediction (the precise name the assignment asked for).** SOM-DST — "Efficient Dialogue State Tracking by Selectively Overwriting Memory," Kim et al., ACL 2020, arxiv.org/abs/1911.03906, code at github.com/clovaai/som-dst (VERIFIED via direct search-result synthesis of the paper's own abstract and ACL Anthology listing). SOM-DST treats the dialogue state as a fixed-size memory and factors DST into two explicit steps: **(1) predict a state OPERATION for every slot** — the operation vocabulary includes CARRYOVER (keep the previous value, no generation needed), UPDATE (generate a new value), DELETE, and DONTCARE — **(2) generate a new value only for slots whose predicted operation is UPDATE**, "of which only a few are generated according to the predicted state operations," explicitly framed by the authors as fixing "the inefficiency of prior approaches that predict dialogue state from scratch at every turn." This is, structurally, exactly LOCALISE (the operation-prediction step decides which slots changed) + GENERATE (a value only for the changed ones) + SPLICE (overwrite just those slots in the fixed-size memory) — from 2020, in the dialogue-systems literature, with "efficiency" as the paper's own stated motivation in its title. SOM-DST reports state-of-the-art joint goal accuracy at the time (51.72% MultiWOZ 2.0, 53.01% MultiWOZ 2.1) while generating far fewer tokens per turn than TRADE-style full regeneration.

**Generation-length framed explicitly as the metric, one paper earlier.** MinTL — "Minimalist Transfer Learning for Task-Oriented Dialogue Systems," Lin et al., EMNLP 2020, arxiv.org/abs/2009.12005, github.com/zlinao/MinTL (VERIFIED via search-result synthesis of paper description). Introduces **Levenshtein belief spans (Lev)**: instead of a copy-mechanism "carryover" of the full previous state, MinTL represents the state update as an edit-distance-style span so state tracking runs "with a minimal generation length." This is the DST literature independently arriving at an edit/patch representation for exactly the reason this research cares about — fewer tokens generated per turn — a full three years before the LLM-structured-output delta question was being asked of GPT-4-class models.

### 5.2 The LLM era re-derives the same answer, for a related but distinct reason

VERIFIED, arxiv.org/html/2304.06556, fetched directly (HTML version; the PDF did not extract cleanly). "Are LLMs All You Need for Task-Oriented Dialogue?", Hudeček & Dušek, SIGDial 2023. Section 3.2, "Domain Detection and State Tracking," exact quote:

> "Our preliminary experiments showed that LLMs struggle to output all active slot values at every turn consistently. Therefore, we model only state updates, following the MinTL approach [Lin et al. (2020)]. Here, the model only generates the slot-value pairs that have changed in current turn."

Two things worth stating precisely for the paper: (1) this explicitly cites and follows MinTL's delta representation, so the LLM-era DST literature did not reinvent this, it inherited it from pre-LLM work; (2) **the stated motivation is reliability, not (only) token efficiency** — the authors report LLMs are worse at consistently emitting a large full-state object than at emitting just the changed slots, an empirical/accuracy argument distinct from (and additive to) the cost/latency argument this research otherwise leads with. No explicit token-count/cost analysis was found in this paper comparing the two approaches head to head (checked directly; not present) — the efficiency case for delta-DST rests on MinTL's earlier "minimal generation length" framing (5.1) plus this paper's reliability finding, not on a single paper making both arguments at once.

### 5.3 A shipped production framework doing exactly this today: Rasa Pro / CALM

VERIFIED, rasa.com/docs/reference/config/components/llm-command-generators/, fetched directly. Rasa's current (2026) architecture, CALM (Conversational AI with Language Models), replaces classification-based NLU with an **LLM Command Generator** that outputs a small, fixed vocabulary of plain-text commands, one per line, including:
```
start flow transfer_money
set slot recipient_account Freddy
disambiguate flows list_contacts add_contact remove_contact
cancel flow
repeat message
```
The critical rule, quoted directly from the prompt template documented on the page: **"For every slot value the user mentions, output exactly one `set slot slot_name value` command. Do not skip any."** This means the LLM never emits a full dialogue-state object — it emits one `set slot` command per changed slot, and Rasa's runtime applies each command against the persisted slot store (documented separately at rasa.com/docs/pro/build/assistant-memory/, "slots are your long-term memory in a conversation"). This is a real, actively-maintained, commercially supported production system (Rasa Pro) where an LLM's structured-ish output is, by construction, already a delta — SetSlot commands are the SPLICE target's natural unit, and the LLM is never asked to restate slots it isn't changing. It is worth being precise about the difference from this research's target problem: Rasa's commands are a small closed **plain-text DSL**, not JSON-Schema/Pydantic-typed structured output, and the "schema" (which slots exist, their types) is fixed at bot-design time by the developer, not derived at runtime from an arbitrary nested schema the way this research's PROJECT step would need. So Rasa solves the LOCALISE+SPLICE-via-typed-operation problem for a flat, developer-defined slot set — it does not solve schema projection over an arbitrary nested Pydantic model. (2026 changelog evidence, SECONDHAND from search snippet only, not independently fetched: Rasa has been actively extending this exact mechanism, including a `slot_mappings_allow_llm_fill` helper controlling which slots an LLM is allowed to fill and MCP-exposed `set_slot_*` tools — consistent with, but not independently verified beyond, the primary command-generator doc above.)

### 5.4 Modern LLM form-filling / document-AI products — mixed, honestly inconclusive evidence

This part of the search did not turn up the same quality of primary, citable evidence as 5.1-5.3. Reporting plainly rather than overstating:

- **Azure Document Intelligence + LLM correction loops.** SECONDHAND (search-result synthesis, primary pages not fetched directly — the specific workflow write-ups found were third-party integration blogs, not Microsoft's own docs). The described pattern is a **side-by-side comparison UI**: Azure's extracted value and an LLM's extracted value are shown per disputed field, a human picks one or types a correction, and the correction is a plain data write — no LLM regeneration of anything is described as happening on correction, full or partial. Consistent with "(c) plain non-LLM field write" from the assignment's own predicted taxonomy, but not independently verified against Microsoft's own documentation, so treat as a plausible-but-unconfirmed data point, not a citation-grade finding.
- **AWS Textract human-in-the-loop.** SECONDHAND (search synthesis). Textract's own human-review integration (Amazon Augmented AI / A2I) is noted in search results as effectively deprecated ("no longer open to new customers," "Google's Document AI Human-in-the-Loop deprecated January 2024") — i.e., the major cloud vendors' own first-party correction-loop tooling is being wound down, not extended, and neither ever had an LLM-regenerate-on-correction feature documented as far as this search found.
- **Production LLM document-processing pipeline (Alan, health insurance).** SECONDHAND ONLY — the primary blog post (medium.com/alan/lessons-from-running-an-llm-document-processing-pipeline-in-production) returned HTTP 403 on direct fetch (Medium blocks automated fetches); everything here is from a search-engine-generated summary of that page, not a verified quote, and should be treated as low-confidence. The summary states LLM output is validated against a Pydantic schema, and on validation failure the document goes to human review with "the best-effort extraction... retained so the reviewer has a starting point rather than starting from scratch" — i.e., on failure, a human patches the malformed object directly; no description found (even secondhand) of the system calling the LLM again for just the failing field. This is the closest thing found to a direct answer to the assignment's "field 7 gets corrected — regenerate everything or patch?" question, and the (low-confidence) answer is: **neither, exactly** — a human free-edits the retained best-effort JSON rather than the LLM regenerating any part of it.
- **Cell-level review in AI table/spreadsheet extraction products** (unstract.com, extend.ai, docupipe.ai — all SECONDHAND, search-snippet only, no primary page fetched). Multiple such products offer cell-level **confidence scores that focus human review** ("a 50-cell table with 2 uncertain cells requires reviewing only 2 cells, not all 50") — this is a real, repeated pattern, but it is a review/attention optimization (which cells does a human need to look at), not evidence that a correction to one cell triggers a scoped LLM regeneration of only that cell. No product was found, even secondhand, that documents "user edits cell (3,7); we re-prompt the LLM constrained to just that cell's schema" as a named feature.

### 5.5 Explicit negative-result queries

- `"form autofill" LLM regenerate single field user correction structured extraction` — dominated by patent filings (autofill patents going back to 1998) and one relevant blog (marmelab.com AI+Wikipedia form autocompletion) not deep-checked for this specific question; no product documented an LLM-rescoped-regeneration-on-correction feature.
- `"human in the loop" structured extraction correction "one field" regenerate LLM extraction pipeline production` — mostly returned academic papers (KYC extraction, clinical extraction, legal extraction), reinforcing that this remains largely a research-stage question even in the document-AI/extraction space, not just in general structured-output tooling (consistent with section 4's finding).
- `document AI correction loop LLM regenerate` (asked as part of the broader sweep) — no product page found describing scoped re-generation on a per-field correction.
- `conversational form filling LLM update one answer` — returned Rasa-adjacent and general chatbot-form results already covered in 5.3; nothing beyond that.

### Judgement (Agent E)

Section 5 is the one place in this whole file where the verdict leans toward **partially (a) already solved** rather than **(c) open** — but only for a narrower problem than the paper's full architecture. Dialogue State Tracking solved "decide which slot changed, generate a value only for that slot, merge it into a persisted state" as a research problem by 2020 (SOM-DST, MinTL) and the LLM-era DST literature adopted the same delta framing by 2023, for both efficiency and reliability reasons (Hudeček & Dušek). Rasa Pro's CALM architecture is genuine, current, production-grade prior art for exactly this pattern with an LLM in the loop (SetSlot commands). The gap between this precedent and the paper's target problem is precise and worth stating carefully: DST's "slots" are always a **flat, developer-declared, fixed-at-design-time set of named fields with known types** — closer to LangGraph's channel keys (section 4) than to an arbitrary, deeply nested, runtime Pydantic schema. Nobody in the DST world does PROJECT (deriving a sub-schema for an arbitrary nested path from a parent schema) because DST schemas don't have the kind of nesting/recursion/discriminated-union structure section 1/E2 describes — DST solved the flat-slot version of this problem thoroughly; the paper's harder case (arbitrary nested schema, LOCALISE by diffing an old value against a change request rather than by classifying a fixed slot list) remains open, consistent with sections 2 and 4's findings. Form-filling/document-AI products (5.4) did not yield comparably strong evidence either way — this sub-area is honestly under-evidenced relative to DST, and should be reported as inconclusive rather than stretched to fit a narrative.

---

## Overall verdict for this file (sections 2-6) — judgement, clearly labelled as judgement

Scope reminder: this file covers structured-output libraries (2), transport-vs-semantic deltas (3), production semantic-delta systems and agent state-update mechanisms (4), form-filling/DST (5), and tool-call protocol support (6). Sections 1 (Pydantic projection mechanics) and 7 (constrained decoding over live value sets) are filed separately as research/raw/E2-pydantic-projection.md and research/raw/E1-live-value-sets.md.

**(a) Already solved — narrowly, for flat/developer-declared schemas.** Dialogue State Tracking (section 5) solved "detect which field changed, generate a value only for it, merge into persisted state" for flat slot sets by 2020 (SOM-DST's state-operation prediction, MinTL's Levenshtein belief spans), and at least one current production framework (Rasa Pro/CALM) ships an LLM-driven version of exactly this today via `SetSlot` commands. LangGraph (section 4) independently solves the SPLICE half — merging a partial update into typed state via per-field reducers — in production, for arbitrary Python/Pydantic state, today. If the paper's scope were "flat or shallow typed state, update surface known in advance," the honest answer is this is already solved and shipping, just under different names (slot filling, state reducers) in different communities that don't cite each other.

**(c) Genuinely open — for the paper's actual target.** The paper's harder claim — an LLM autonomously LOCALISING which region of an arbitrary, deeply nested, possibly-recursive schema needs to change (without a developer having pre-enumerated the possible update sites), PROJECTing a sub-schema for exactly that region on the fly, GENERATING against it, and SPLICing back with global revalidation — has no shipped precedent anywhere this file's five sections looked:
- No structured-output library (section 2: Instructor, BAML, Outlines, Guidance, Marvin, Mirascope, DSPy, LangChain, LlamaIndex — nine libraries, one negative result each) treats sub-schema projection as an operation. The one library whose primitives could support it if hand-assembled (Guidance) has not packaged it, and its own maintainers have not built it either.
- No agent framework (section 4: LangGraph, CrewAI, AutoGen, Microsoft Agent Framework, OpenAI Agents SDK) lets the model itself choose the update surface at runtime; every one fixes it at developer build time.
- No vendor tool-calling protocol (section 6: MCP, OpenAI, Anthropic, Gemini) has any notion of a partial/delta argument object; every one requires the full object every call.
- DST (section 5) never needed PROJECT because its slot sets are flat and small; it is not evidence against the harder problem, only silent on it.
- The one production-adjacent system that does emit a real RFC 6902 patch against arbitrary JSON (JSON Whisperer, section 4) is a 2025 research paper, not a shipped product, and does not do schema projection — it patches the whole document's structure with array-stabilization tricks, not a narrowed sub-schema.

**(b) Not worth solving — no evidence for this either way from this file's sections.** Nothing found suggests the problem is a non-issue in practice; if anything, the volume of adjacent, partial solutions (transport streaming, DST deltas, LangGraph reducers, BAML's additive TypeBuilder, Outlines' still-open dynamic-schema friction) suggests real, repeated demand for something in this space that nobody has fully assembled.

**Net verdict contribution from sections 2-6: mostly (c), with a well-scoped exception carved out as (a).** The paper should state precisely where the line falls: flat typed state with a build-time-known update surface is solved (cite DST/Rasa/LangGraph); an LLM dynamically discovering and projecting an arbitrary nested sub-schema at generation time, then splicing back with global revalidation, is not solved anywhere in production engineering as of this research (2026-09).

---

Status: SECTIONS 2, 3, 4, 5, 6 COMPLETE. Sections 1 and 7 filed separately per coordinator (see note at top of file). This file is done from this agent's side.
