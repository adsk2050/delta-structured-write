# 05 — What the experiments did not test

*Written 2026-09-07, immediately after the retry experiment returned its null.
This document records the user's rebuttal to the conclusion drawn in
[`RETRY.md`](../RETRY.md) and [`EXPERIMENT.md`](../EXPERIMENT.md), and the
redesign it forces. The rebuttal is correct on both counts and one of them is a
structural flaw in the instrument, not a limitation of its scope.*

---

## The conclusion being challenged

Three experiments produced three nulls, and I summarised them as:

> For schema-constrained output from a current frontier model, regeneration is
> simply reliable, and every surviving reason to generate fragments is economic.

## The rebuttal, in the user's words

> "I don't think this is true that it's reliable. I think for our test we haven't
> used the schema complicated enough. That is 1. 2 is that we are playing in the
> safe zone of the LLM context window. As the context window reaches its near,
> middle stuff is forgotten... if yes then we will only see the LLM start to make
> mistakes later in the agentic loop, not the start."

Both objections hold. The second is worse than stated.

---

## Objection 1 — the schema was not hard enough

`ReviewForm` is three levels deep and structurally boring:

```
ReviewForm
├── applicant : Applicant          (flat object)
├── responses : list[Response]     (list of flat objects)
└── scalars
```

Everything the literature review identified as *the* source of difficulty is
absent from it:

| difficulty | in `ReviewForm`? |
|---|---|
| discriminated unions / `oneOf` / `anyOf` | no |
| recursion, `$ref` cycles | no |
| nesting deeper than 3 | no |
| lists of lists, lists inside union branches | no |
| `uniqueItems` / value-equality constraints | no |
| cross-field invariants spanning **branches** | no — the one validator is a form-level pair |
| optional structure that changes what else is required | no |

[`notes/03`](03-research.md) has the number that makes this decisive.
**Displacement Rate** (arXiv:2608.25358): values produced correctly but placed at
the wrong structural position — GPT-4o **24.2%**, DeepSeek-V3 26.2%, Qwen2.5-7B
73.8% — and the paper's own finding is that *"structural fidelity degrades
earlier and faster than content accuracy."* Those numbers are **at highest
complexity**. We measured at the bottom of the complexity range and reported the
absence of an effect that is defined to appear at the top of it.

So the null says "a shallow schema is regenerated reliably". It does not say what
I claimed it said.

## Objection 2 — and this one is a defect in the instrument

The objection as put was about the context window. The reality is worse: **the
experiments had no accumulating context at all.**

`experiment.py:107` builds every turn's prompt from scratch:

```python
return (
    "You are editing a structured review form.\n\n"
    f"CURRENT FORM (JSON):\n{body}\n\n"      # the CURRENT document, nothing else
    f"REQUESTED CHANGE:\n{edit.instruction}\n\n"
    f"TASK:\n{task}"
)
```

There is no transcript. No prior turn, no prior output, no history. So the
"12-turn chain" was **twelve independent single-shot calls**, each with a flat
~17,000-token prompt on a 1,048,576-token window — about **1.6% of the window**,
turn 1 and turn 12 alike.

`EXPERIMENT.md` claims the chain design captures compounding:

> "Turns run as a *chain* — the document carries forward, so corruption
> introduced at turn 3 is still there at turn 8. That is the compounding effect
> DELEGATE-52 reports."

That conflates two different things. The **document state** carried forward, yes.
The **context** did not. And the compounding DELEGATE-52 measures is a function
of accumulated context, not of document lineage — its own phrasing is *"each 1k
token increment progressively increases degradation"* and *"no plateau to 100
turns"*. An experiment whose per-turn context is constant cannot exhibit it.

> **The mechanism the experiment set out to detect was structurally excluded
> from the design.** The null is not evidence against compounding. It is a
> measurement taken with the effect switched off.

### Is "lost in the middle" still real, or fixed?

Not fixed. Substantially *changed*, in a way that matters here.

- **Simple retrieval is saturated.** Needle-in-a-haystack — a lexically distinctive
  string planted in filler — is at or near 100% on frontier models across the
  advertised window. This is why NIAH stopped being informative, and it is
  probably the source of the impression that the problem is solved.
- **Everything harder than retrieval is not.** RULER's finding is that *effective*
  context is far below advertised context once the task requires aggregation,
  multi-hop, or tracking rather than lookup. NoLiMa's is that when the target
  requires semantic inference instead of lexical overlap, accuracy falls off
  sharply well before the nominal limit.
- **Faithful reproduction is in the second category, not the first.** Retyping a
  document without drift is not retrieval; it is exhaustive, position-sensitive
  copying, and it degrades with the amount of material in play.

*(Flagging honestly: this is a fast-moving area and my knowledge has a cutoff.
The claim above is directional. It should not go into a paper without a current
citation check — but it does not need to be true for the redesign to be right,
because the design flaw stands on its own.)*

The user's prediction follows directly: **errors appear late in an agentic loop,
not at the start.** We only ever measured the start, twelve times.

---

## The asymmetry this exposes — and it favours the thesis

There is a further consequence neither of us stated, and it may be the most
important thing in this document.

In a real agentic loop the transcript accumulates. Each turn appends the
instruction *and the model's output*. The two arms therefore grow their context
at wildly different rates:

| turn | whole-document arm | fragment arm |
|---|---|---|
| 1 | ~17K | ~17K |
| 10 | ~170K | ~18K |
| 20 | ~340K | ~19K |
| 40 | **~680K — near the window** | **~21K** |

The baseline arm does not merely spend more output tokens. **It poisons its own
context**, at roughly the document size per turn, until it is operating in
exactly the degraded regime the literature describes — while the fragment arm
stays flat and never leaves the safe zone.

If that is right, the integrity argument was never wrong. It was **measured in
the one configuration where it cannot appear**, because a flat-context loop
denies the baseline arm the chance to degrade.

Note the relationship to the **quadratic input trap** already recorded in
[`notes/04`](04-solution-approaches.md) §3 and `CHECKPOINT.md`: 1,000 chunked
calls that each see all prior output cost \$102.50 input against \$10.00 output.
That was filed as a *risk to our design*. It is also the mechanism by which the
baseline arm loses — the baseline pays it in full and the fragment arm barely
pays it at all. Same phenomenon, opposite sign, and only one side of it had been
written down.

---

## What this changes

| claim | status |
|---|---|
| "cost: 172× on edits, 26× on repairs" | **stands** — measured, arms identical, no context effect involved |
| "collateral damage is zero" | **stands, but only at 1.6% context and depth-3 schema** |
| "oscillation does not occur" | **stands, same two qualifiers** |
| "regeneration is simply reliable" | **withdrawn.** Unsupported at the complexity and context where it was supposed to fail |
| "every surviving reason to fragment is economic" | **withdrawn** as premature |

The three nulls are still real results. They are results about *shallow schemas
in short contexts*, and they should be reported that way.

## The experiment that actually settles it

Both objections point at one design, so build one experiment:

**A long agentic loop, over a structurally hard schema, with a genuinely
accumulating transcript, run to a large fraction of the window.**

| | |
|---|---|
| **schema** | deep nesting, discriminated unions, bounded recursion, lists inside union branches, invariants spanning branches — [`src/dsw/dossier.py`](../src/dsw/dossier.py) |
| **loop** | the transcript accumulates. Turn *n* sees turns 1..*n*−1, instructions and outputs both. This is the variable that was missing. |
| **arms** | whole-document regeneration vs fragment generation, identical instructions, same model |
| **turns** | enough for the baseline's context to reach a large fraction of the window — this is the point, so it cannot be cut for budget |
| **measured per turn** | untouched-region integrity, violations, structural displacement, prompt tokens (the growth curve itself), output tokens, latency |

**The prediction, stated before running so it can be wrong:** the two arms track
each other for the first several turns — reproducing the existing nulls, which is
the control — and then diverge, with baseline integrity falling as its context
grows, while the fragment arm stays flat because its context never grows.

If they never diverge, the reliability conclusion survives a much harder test
than it has faced so far, and that is worth knowing too.
