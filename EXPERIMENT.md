# The integrity experiment

The one measurement that decides whether any of
[`notes/04-solution-approaches.md`](notes/04-solution-approaches.md) is worth
building. It appears never to have been run for schema-constrained output.

> Take a large Pydantic object. Change one leaf. Regenerate the whole thing.
> Diff every field that was supposed to be untouched. Repeat across turns.

## Why it is cheap

The fragment arm's integrity is **1.0 by construction** — bytes that are never
regenerated cannot change, and `scripts/smoke.py` asserts it offline. So the
experiment only has to measure the *baseline*. That asymmetry is the whole
reason this costs an hour of free-tier quota instead of a research budget.

## Two designs

The free tier allows 20 requests/day/model, so there are two grids rather than
one. Start thin; it is the only one that runs today.

| | thin | thick |
|---|---|---|
| sizes | `large` only | all three |
| seeds | 1 | 5 |
| turns | 10 | 10 |
| calls | **20 — one free-tier day** | 300 |
| paid cost | ~$0.89 (~$0.45 batched) | ~$6.32 (~$3.16 batched) |
| answers | does corruption appear, and does it compound across turns? | that, plus size scaling and variance |
| cannot answer | size effects, variance | — |

`large` is the thin design's size because that is where the effect should be
biggest, so a null result there is genuinely informative rather than merely
underpowered.

```bash
uv run python scripts/run_integrity.py --design thin --dry-run
uv run python scripts/run_integrity.py --design thin
uv run python scripts/run_integrity.py --design thick     # needs paid or a working key
```

## Design

Two arms, identical inputs, one pinned model.

| | baseline | fragment |
|---|---|---|
| model sees | whole document + instruction | whole document + instruction |
| model emits | the whole document | one `Response` object |
| constrained against | `DecodableReviewForm` | `Response` |
| validated against | `ReviewForm` (the real one) | `ReviewForm`, after splice |
| splice | none — output *is* the document | `dump → patch → model_validate` |

Independent variables: **document size** (3 levels) and **turn index** (1–10).
Turns run as a *chain* — the document carries forward, so corruption introduced
at turn 3 is still there at turn 8. That is the compounding effect DELEGATE-52
reports, and it cannot be seen by running turns independently.

Measured, per turn: untouched-region integrity, which leaves changed, whether
the requested edit actually landed, global validity, tokens in/out/thinking,
latency, and the safety walk's verdict.

## The corpus

`ReviewForm` is built to sit on the **unsolved** side of the line the literature
review drew. Dialogue state tracking solved delta updates for flat bags of
independent slots back in 2020 (SOM-DST, MinTL, and Rasa CALM in production).
What it never had to handle is what this form has on purpose:

- nesting (`Applicant`, and `Response` inside a list)
- a list whose elements are themselves objects
- cardinality constraints on that list
- **a cross-field invariant that leaves no trace in the JSON Schema** —
  `status == "resolved"` requires a `resolution`

| size | responses | tokens (measured) |
|---|---|---|
| small | 20 | 1,538 |
| medium | 70 | 5,276 |
| large | 220 | **16,895** |

The large size lands inside the 10–20K window notes/04 §5 asked for.

## Budget

Measured token counts, full grid (3 sizes × 5 seeds × 10 turns × 2 arms):

| size | arm | in/turn | out/turn | calls | tokens |
|---|---|---|---|---|---|
| small | baseline | 1,688 | 1,538 | 50 | 161,300 |
| small | fragment | 1,688 | 120 | 50 | 90,400 |
| medium | baseline | 5,426 | 5,276 | 50 | 535,100 |
| medium | fragment | 5,426 | 120 | 50 | 277,300 |
| large | baseline | 17,045 | 16,895 | 50 | 1,697,000 |
| large | fragment | 17,045 | 120 | 50 | 858,250 |

**300 calls, ~3.62M tokens.** Tokens were never the constraint. Requests are.

> ### ⚠ The free tier cannot run this. Measured, not assumed.
>
> Every secondary source says the Gemini free tier gives 1,500 requests/day.
> The API says otherwise. The actual 429 body, 2026-09-07:
>
> ```
> Quota exceeded for metric:
>   generativelanguage.googleapis.com/generate_content_free_tier_requests
> limit: 20, model: gemini-3.6-flash
> quotaId: GenerateRequestsPerDayPerProjectPerModel-FreeTier
> ```
>
> **20 requests per day, per model.** A 300-call grid would take 15 days on one
> model — and spreading it across models is exactly what the pinning rule
> forbids, since it would reintroduce the model effect the experiment exists to
> exclude.

**Paid is the fix, and it is cheap.** At the introductory rate for
`gemini-3.6-flash` — $0.75/M input, $3.75/M output, through 2026-12-31 — the
full grid is 2.42M input and 1.20M output:

| | tokens | rate | cost |
|---|---|---|---|
| input | 2,415,900 | $0.75/M | $1.81 |
| output | 1,203,450 | $3.75/M | $4.51 |
| | | **per full run** | **≈ $6.32** |

Batch mode halves it to ~$3.16, and the experiment is entirely batchable — it is
not interactive. Five full runs is roughly $32, or $16 batched.

`uv run python scripts/run_integrity.py --dry-run` recomputes the grid for any
configuration.

### If the free tier must be used

The largest design that fits 20 calls/day on one model is **1 size × 1 seed ×
10 turns × 2 arms = 20 calls/day**, i.e. one chain per arm per day. That is
enough to see whether corruption appears and whether it compounds across turns,
but not enough to separate size effects or estimate variance. Three days gives
3 seeds at one size, which is a real if thin result.

```bash
uv run python scripts/run_integrity.py --sizes large --seeds 1 --turns 10
```

## Choices, and why

**Model: `gemini-3.5-flash`, direct, pinned.** Getting here took four attempts,
all recorded in `config.py` so nobody re-treads them:

| candidate | outcome |
|---|---|
| `gemini-2.5-flash` | `404` — "no longer available to new users" |
| `gemini-3.6-flash` | works, but its 20-call free bucket was spent during setup |
| `gemini-3.7/3.8-flash` | reject `thinking_level` `minimal` **and** `low` with `400` |
| **`gemini-3.5-flash`** | **accepts `minimal`, zero thought tokens, fresh bucket** |

`gemini-flash-latest` is excluded on principle: an alias that moves would
reintroduce the very model effect the experiment exists to remove.

**Not OpenRouter, for the primary arm.** Its structured-output support is per
*endpoint*, not per model, and it documents that it "might fall back to
`json_object`". In an experiment *about* constrained decoding, a silent
downgrade from enforcement to a strong hint would invalidate the results with no
error surfacing. `OpenRouterProvider` exists for cross-checks and always reports
`constrained=False`, so a mixed log can never be misread.

**Not LangChain.** It chooses among function-calling, `json_mode` and
`json_schema` strategies depending on model and version. That choice *is* the
independent variable here, so it has to be ours.

**Not Inception Mercury, in the main arm.** Mercury is a *diffusion* LLM —
parallel token prediction with iterative refinement. That makes it genuinely
interesting to this research (in-place refinement is arguably a native delta
mechanism, and it is claimed to be better at strict formats) but it is a
different generation paradigm, so putting it in the main comparison would
confound the arm effect with a paradigm effect. It belongs in a follow-up, noted
in "Open threads" below.

**Thinking held at `minimal`.** Load-bearing. Left at default this model spent
**561 thinking tokens on a trivial one-object call**, and thinking bills as
output — the baseline arm's output count would have been a mixture of "document
retyped" and "reasoning done". `thinking_level="minimal"` yields zero thought
tokens; `thinking_budget=0` and `thinking_level="none"` are both **400 errors**
on Gemini 3.x. It cannot be switched off, only turned down. Thought tokens are
recorded per call anyway, so a future model ignoring the setting will show up in
the data rather than hide in it.

## A finding that fell out of the setup

Google's structured-output documentation lists `minItems` and `maxItems` as
supported. **They are not.** A list carrying either is rejected outright with
`400 INVALID_ARGUMENT` — at `max_length=50` as well as `400`. Not silently
dropped, as the audit found other engines do: refused.

This is handled by keeping **two** models rather than deleting the constraint:
`ReviewForm` carries the real constraints and does all validation;
`DecodableReviewForm` is the strictly weaker schema the decoder will accept and
is used only for generation. **The gap between what the decoder can promise and
what the schema actually requires therefore appears in the results instead of
being hidden by them** — which is the point, not a workaround.

## Running it

```bash
uv sync
uv run python scripts/smoke.py --offline   # no API calls; asserts the invariants
uv run python scripts/smoke.py             # one live call per arm
uv run python scripts/run_integrity.py --dry-run
uv run python scripts/run_integrity.py --pilot
uv run python scripts/run_integrity.py
uv run python scripts/analyse.py
```

Interrupting is safe: every turn is appended to `data/runs/integrity.jsonl` as it
completes, and completed chains are skipped on the next run. A chain that fails
mid-way stops rather than fabricating later turns from a broken document.

Retries happen **only** on 429 and 503 — transport failures where no sample was
drawn, so a retry is the same call rather than a second roll of the dice. A
malformed or wrong *output* is never retried; that would silently change what is
being measured.

## What the results should show

| | prediction | based on |
|---|---|---|
| baseline integrity < 1, worsening with size | DELEGATE-52: ~25% of content corrupted by end of long workflows | notes/03 §4 |
| baseline integrity worsening with turn | "each 1k-token increment progressively increases degradation", no plateau to 100 turns | notes/03 §4 |
| fragment integrity = 1.000 | by construction | asserted offline |
| output tokens ~140× lower at `large` | 16,895 vs 120 | measured above |
| some baseline outputs failing real-schema validation | `minItems`/`maxItems` unenforceable at decode time | §"A finding" above |

If baseline integrity comes back at or near 1.000 across all sizes and turns,
**the strongest argument in notes/04 collapses** and the honest conclusion is
that the cost case has to carry the idea alone. That outcome is worth having.

## Open threads

- **Mercury / diffusion follow-up.** Does a diffusion LLM, which refines in
  place, corrupt untouched regions less than an autoregressive one? Same harness,
  one extra provider, and directly relevant to the thesis.
- **The construction regime** (10 rows at a time) is not built. It needs the
  bounded carry from notes/04 §3 — counter, obligation bits, exclusion trie —
  and the quadratic-input trap makes it a different experiment.
- **`response_json_schema`** may allow passing a raw schema dict, which would
  let the decodable/real split be computed automatically instead of hand-written.

---

# Results — first run, 2026-09-07

`gemini-3.5-flash`, thin design, `large` = 16,895 tokens, 1 seed, 12 baseline
turns and 1 fragment turn. Data: `data/runs/`, analysis:
`uv run python scripts/analyse.py --log data/runs/combined.jsonl`.

| arm | turns | perfect integrity | mean integrity | corrupted leaves | edit applied | out tokens | latency |
|---|---|---|---|---|---|---|---|
| baseline | 12 | **12/12 (100%)** | 1.00000 | 0.00 | 12/12 | 16,869 | 54.5 s |
| fragment | 1 | 1/1 (100%) | 1.00000 | 0.00 | 1/1 | **98** | **4.35 s** |

## The cost case is confirmed, and it is bigger than predicted

**172× fewer output tokens. 12.5× lower latency.** Both measured, both on
identical inputs. The estimate in the budget section was near-exact — predicted
17,045 in / 16,895 out, actual 16,972 / 16,869 — so the cost model can be
trusted for extrapolation.

## The integrity case is NOT supported

This is the important result and it goes against the argument in
[`notes/04`](notes/04-solution-approaches.md).

**Twelve consecutive turns, zero corrupted leaves.** The model retyped a
~17,000-token document twelve times, applying a different targeted edit each
time, and every single field it was not asked to change came back
byte-identical. No drift, no elision, no paraphrase, no dropped array element.
Turn 12 was as clean as turn 1 — no compounding.

The prediction from the literature was ~25% of content corrupted by the end of a
long workflow (DELEGATE-52) and a 13% rate of lazy elision (Aider). Neither
appeared.

### The most likely explanation, and why it matters

**Constrained decoding is probably what prevents it.** The corruption evidence in
notes/03 §4 comes from *unconstrained* or free-text regeneration — agentic
document workflows, code editing with search/replace. This baseline arm
regenerates **under a schema constraint enforced at decode time**. The grammar
fixes the key set, the types, and the structure, so the model has far less room
to drift, elide, or paraphrase a field into a different shape.

If that reading holds, it does not destroy the thesis — it **relocates** it:

> The integrity argument applies to *unconstrained* regeneration. For structured
> output that is already constrained-decoded, the reason to generate fragments is
> **cost and latency**, and that reason is worth 172×.

That is a cleaner and more defensible claim than the one notes/04 makes, and it
is falsifiable: run the same grid with the schema constraint removed from the
baseline arm and see whether corruption appears.

### What this result cannot support

One seed, one size, one model, a synthetic document with regular repeating
structure. Regular structure is plausibly easier to copy faithfully than
heterogeneous real content. The thick design exists to separate exactly these.
**A null at n=1 is evidence, not proof** — but it is a null at the size and depth
where the effect was predicted to be *largest*, which makes it worth more than a
null at the easy end.

## Follow-ups this result makes worth running, in priority order

1. **Unconstrained baseline arm.** Same grid, `response_mime_type` dropped so the
   baseline is free-text JSON. If corruption appears there and not here, the
   relocation above is confirmed and becomes the paper's finding.
2. **Heterogeneous corpus.** Replace the generated sentences with real,
   irregular prose. Tests whether regular structure is doing the work.
3. **Thick design.** Size scaling and variance.
4. **Mercury / diffusion arm.** Does in-place refinement behave differently?

## Operational notes from the run

- ~55 s per 17K-token generation. Two chains died on `RemoteProtocolError`
  (dropped connection) before that was added to the retry set; long generations
  outlive some idle timeout on the path.
- Output tokens drift down slightly across turns (16,883 → 16,846). That is the
  corpus, not the model: each edit replaces a three-clause answer with a
  two-clause one, so the document genuinely shrinks. Not drift.
- Zero thought tokens on every call, confirming `thinking_level="minimal"` holds.
