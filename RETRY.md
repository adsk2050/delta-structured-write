# The retry experiment

[`EXPERIMENT.md`](EXPERIMENT.md) asked what regeneration does to fields nobody
asked about, and answered *nothing* — twelve consecutive turns, zero corrupted
leaves. This asks the other half of the question.

> Not **does regeneration corrupt what you did not ask for**, but **does
> regeneration reliably fix what you did** — and what does each way of asking
> cost to reach a valid document?

That gap was real. The integrity experiment never induced a failure, so the
retry path — the path a production system is on whenever a validator rejects
something — was completely untested.

```bash
uv run python scripts/run_retry.py --offline    # no API calls; asserts the invariants
uv run python scripts/run_retry.py --dry-run    # budget only
uv run python scripts/run_retry.py --sizes medium --seeds 3
uv run python scripts/analyse_retry.py
```

## Design

Two arms, sharing their first attempt so nothing about the comparison depends on
first-attempt luck.

| | |
|---|---|
| **shared** | one call: *"set status to resolved and record the outcome"*. Both arms branch from its output. |
| **whole** | on rejection, resend the document plus every violation; the model re-emits the entire document. This is Instructor's reask, and it is what essentially every production system does today. |
| **fragment** | on rejection, take each violation's repair path, project the sub-schema there, generate only that value, splice, recheck. |

Sharing the first attempt is not only cheaper. It removes first-attempt variance
from the comparison entirely, so any difference between the arms is a difference
in how they *repair*.

Both arms are shown **identical context** every time — the whole document and the
whole violation list. A real fragment-repair system would send far less, but
withholding input from one arm would confound the comparison with a prompt
effect. Everything measured here is therefore an output-side saving, which is the
conservative claim.

A "round" means the same thing in both arms: one pass over the outstanding
violations. The whole arm spends one call per round; the fragment arm spends one
call per violation. **That asymmetry is the point, not an oversight** — it is
what the architecture actually costs, and it is measured rather than hidden.

## The rules, and why there are three of them

The integrity experiment needed one invariant no schema can see. This one needs a
small *network* of them, because the effect it is looking for — a repair that
fixes one violation and creates another — cannot exist with a single rule. All
three are gated on `status == "resolved"`, so a form is valid until someone tries
to close it. That is an ordinary pre-submission gate.

| | rule | repairs at |
|---|---|---|
| **R1** | a resolved form carries a resolution of at least 20 characters | `/resolution` |
| **R2** | a high-confidence answer cites at least two exhibits | `/responses/i` |
| **R3** | a resolved form contains no low-confidence answers | `/responses/i` |

**R2 and R3 are coupled on purpose, and the coupling is the trap.** The obvious
repair for R3 is to promote the low-confidence answer — and a promotion to
`high` immediately owes R2 two exhibits, which a planted R3 response never has.
`medium` is the repair that costs nothing. So a careless fix creates work and a
careful one does not. `scripts/run_retry.py --offline` asserts both halves of
that offline, before any call is bought.

## Localisation is the part with research content

A retry loop can only be aimed if something tells it *where*. Two sources, and
the split between them is a finding rather than a detail:

- **Pydantic hands you the path for free.** `ValidationError.errors()[i]['loc']`
  is a JSON pointer. Nothing has to guess and no model has to write it.
- **But only if the validator is in the right place.** R2 is a property of a
  single response, so declaring it on `Response` yields `loc == ('responses', 3)`
  — exact. R1 and R3 need `status`, which lives on the form, so their `loc` is
  the empty tuple and points at nothing; the path has to be declared by hand on
  the rule.

> **Where you put the validator decides whether a retry can be targeted.** That
> is a concrete, actionable design rule, and it costs nothing to follow.

## Inducing the failure

The closure rules are **not** stated in the first-attempt prompt by default.
That is not a thumb on the scale — it is the ordinary production failure. The
business rules live in the validator, the prompt under-specifies, and the model
finds out only when the document comes back rejected. From the first repair
onward both arms see every violation spelled out, so nothing about the
comparison between the arms depends on this choice.

The alternative was measured first, and it is why the default is what it is:

| condition | episodes | valid on the first attempt |
|---|---|---|
| rules stated up front (`--rules-first`) | 2 (`small`, `large`) | **2/2** |
| rules withheld | 4 (`medium`) | 0/4 |

Told the rules, this model simply satisfies them — including fixing three
violations while retyping a 220-response, 16,895-token document in a single
pass. **The rules-stated condition produces no retry to study at all.** Worth
recording on its own: with the constraints in the prompt and a schema at decode
time, the failure this experiment exists to measure did not occur.

---

# Results — 2026-09-07

`gemini-3.5-flash`, 6 episodes, 21 steps, **20 free-tier calls — the exact daily
cap**. Data: `data/runs/retry.jsonl`, analysis: `scripts/analyse_retry.py`.

## The headline: oscillation did not happen

| arm | repair steps | steps that fixed something | **steps that introduced a new violation** | mean fixed/step | mean introduced/step |
|---|---|---|---|---|---|
| whole | 4 | 4 | **0** | 3.50 | **0.00** |
| fragment | 10 | 10 | **0** | 1.00 | **0.00** |

The whole-document reask never traded one violation for another. It fixed two
violations in one call three times, and **eight violations in one call** on the
high-density episode. Every repair was monotone.

That is the hypothesis this experiment was built to test, and it is not
supported. It is the same shape as the integrity null, and probably the same
cause: under constrained decoding, with the errors spelled out, this model does
what it is told and disturbs nothing else.

## Collateral damage did not happen either

| arm | steps | perfect | mean integrity | mean corrupted leaves |
|---|---|---|---|---|
| whole | 4 | **4/4** | 1.00000 | 0.00 |
| fragment | 10 | **10/10** | 1.00000 | 0.00 |

Every leaf outside the paths under repair survived byte-identical in both arms.
The fragment arm's 1.00000 is arithmetic and was asserted offline; the whole
arm's is a measurement, and it confirms the integrity experiment on the one path
that experiment never exercised.

## What does survive: the cost, and it is large

| episode | whole calls | whole out | frag calls | frag out | output ratio |
|---|---|---|---|---|---|
| `medium/0/p2` | 1 | 5,173 | 2 | 201 | 25.7× |
| `medium/1/p2` | 1 | 5,281 | 2 | 201 | 26.3× |
| `medium/2/p2` | 1 | 7,562 | 2 | 196 | 38.6× |
| `medium/0/p8` | 1 | 5,183 | 5 (of 8 needed) | 429 | 12.1× |

**Mean 25.7× fewer output tokens to repair, median 26.0×. 26.5 s → 9.0 s.**
Both arms reached a valid document in one round, so this is a straight saving
with no reliability cost attached to it.

## And a negative the harness was built to expose

**The fragment arm pays one call per violation, so its advantage shrinks as
violation density rises.** At three violations it is 2 calls against 1 and wins
26× on tokens. At nine violations it needs 8 calls against 1, and the token
advantage falls to roughly 6×. Extrapolate and there is a crossover where per-call
overhead — input tokens, round trips, rate limits — eats the whole saving.

This is not a flaw in the measurement; it is the shape of the architecture.
Coordinate descent costs one step per coordinate. **Batching sibling repairs into
a single projected call is the obvious fix and it is not built**, and it is the
first thing to build if this goes further.

## Where the repair path came from

| source | steps | share | rules |
|---|---|---|---|
| **exact** — `ValidationError.loc` pointed at it, free | 7 | **64%** | R2 |
| **hinted** — the rule had to declare the path by hand | 4 | 36% | R1, R3 |
| unlocalisable — no path; fragment retry cannot aim | 0 | 0% | — |

Nothing was unlocalisable, but that is a property of these three rules and should
not be generalised. The useful number is the 64/36 split, and its cause: the
per-item rule localised itself and the form-level rules could not.

## Caveats, stated plainly

- **n = 6 episodes, one model, one corpus.** The oscillation null is a null at
  low n. It is worth more than nothing because the high-density episode (nine
  violations, one call) is exactly where the effect was predicted largest, and it
  did not appear there either.
- **One episode is incomplete.** `medium/0/p8`'s fragment arm got 4 of 8 repairs
  in before the free tier's 20-call daily cap. Its 12.1× ratio is therefore a
  lower bound on calls and not a completed episode.
- **The corpus is synthetic and regular.** Same caveat as the integrity
  experiment, and the same fix: heterogeneous real content.
- **One unexplained observation.** `medium/2`'s whole-arm repair emitted 7,562
  output tokens against a 5,276-token document — 43% more than the document it
  was reproducing — with `finish_reason=STOP`, zero thought tokens, and perfect
  integrity. The output was correct. The token count is not explained.

## What this does to the argument

The retry path was pitched (in this repo's own conversation) as the strongest
remaining case for fragment generation, on the grounds that whole-document reask
is a random walk on validity while fragment repair is coordinate descent. **The
random-walk half is not supported.** This model's whole-document repairs were
monotone in every step measured, so the convergence guarantee the residual
analysis would have bought is a guarantee against something that did not occur.

What is left is the cost argument, again — 26× on repair output tokens, on a path
production systems are on constantly — now carrying a measured limit of its own
in the per-violation call cost.

Three experiments have now been run and the integrity-style argument has failed
all three times. The honest reading is that **for schema-constrained output from
a current frontier model, regeneration is simply reliable**, and every remaining
reason to generate fragments is economic.

## Follow-ups, in priority order

1. **Batch sibling repairs into one projected call.** Removes the only measured
   disadvantage. Cheap to build, and it changes the crossover point.
2. **Unconstrained arms.** Still the highest-value experiment in the repo, and
   now for both experiments at once: drop `response_mime_type` and see whether
   corruption and oscillation both appear where the constraint is absent.
3. **More episodes at high violation density.** The oscillation null rests on
   four whole-arm repair steps. Ten would be worth having.
4. **A rule that is genuinely unlocalisable** — a global counting or uniqueness
   constraint — to measure the fallback case at 0% instead of asserting it.
