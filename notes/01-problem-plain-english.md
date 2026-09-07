# 01 — The problem, in plain English

*Step 1 deliverable. No jargon, worked examples. Written from
[`00-original-note.md`](00-original-note.md), then revised after the user
supplied the two motivating examples in §1 and §4.*

---

## 1. The situation

You have a form. It is defined by a Pydantic model, which means it has a
schema — a fixed shape that any valid filled-in form must have.

```python
class Response(BaseModel):
    question_id: str
    answer: str
    confidence: Literal["low", "medium", "high"]
    evidence: list[str]

class Form(BaseModel):
    applicant: Applicant
    responses: list[Response]   # 40 of them
    reviewer_notes: str | None
```

The form is filled in. Forty answers, a few thousand tokens of JSON. Then the
user says:

> "Change the answer to Q3."

**Today the model has to write the whole form out again.** All forty responses.
The applicant block it was not asked to touch. The thirty-nine answers that were
already right. To change one answer it re-types the entire document.

That is the problem.

## 2. Why it is bad

**It is slow.** Text comes out of a model one token at a time. A 4,000-token
form takes 4,000 steps, whether one answer changed or all forty did. In a loop
where the user corrects one field at a time, this is the dominant cost.

**It is expensive.** Output tokens cost several times what input tokens cost,
and unlike input they cannot be cached. Showing the model the old form is nearly
free. Making it re-type the form is not.

**It is unsafe, and this is the part people underestimate.** When a model
re-types thirty-nine answers it was not asked to change, sometimes it changes
them. It paraphrases an answer. It drops the fourth item from an evidence list.
It flips a `confidence` from `medium` to `high`. It gets bored and writes
`"...remaining responses unchanged..."`. Nothing warns you, because the output
is still valid JSON in exactly the right shape. It is just quietly wrong.

The blast radius of an edit should be the edit. Today it is the whole document.

## 3. What we want instead

The system works out that "Q3" means `responses[2]`. It asks the model for
**only that piece** — and it constrains that small generation against **that
piece's own schema**, the `Response` model:

```json
{ "question_id": "Q3",
  "answer": "The 2024 filing was amended in March.",
  "confidence": "high",
  "evidence": ["exhibit-B", "p.14"] }
```

Then it drops that object into slot 2 of `responses` in ordinary Python. Sixty
tokens instead of four thousand. Everything else is byte-identical to what it
was before — not "probably unchanged", but *identical*, because nothing retyped
it.

Note what the model did **not** have to do. It did not write a patch, or a path,
or a diff. It answered one small, well-posed question. The system did the
bookkeeping.

## 4. The second shape of the same problem

The user's other example is not an edit at all.

An agent is building a spreadsheet with 10,000 rows, and the rows have a schema.
Asking for all 10,000 in one generation is bad and, past a certain size,
impossible — every model has a hard ceiling on how many tokens one response can
contain. Long generations also degrade: they drift, repeat, truncate, or trail
off into "…". So instead:

> generate 10 rows. Then the next 10. Then the next 10.

Each batch is a small, schema-valid fragment. The system assembles them.

Same underlying idea — **stop making the model emit the whole object** — but the
economics and the failure modes are different, so it is worth keeping the two
cases apart. Call them the **edit case** (the form) and the **construction
case** (the spreadsheet).

## 5. The catch

Structured output is trustworthy today because of **constrained decoding**.
While the model generates, at every step, the system computes which next
characters could still lead to a valid document and forbids all the others. The
model *cannot* emit malformed JSON or an unknown field, the way you cannot type
a letter into a calculator. It is a hard guarantee, not a polite request in the
prompt, and it is why people build on structured output at all.

That machinery is built around **one whole document matching one schema**.

The moment the model is producing a fragment instead of a document, the
guarantee has nothing to attach to. So the question is:

> **What exactly do we constrain the model against, when it is writing a piece
> rather than the whole thing?**

The promising answer — and this is the whole reframing — is: **the piece's own
schema.** A `Response` is a schema. Ten rows is a schema (`list[Row]` with
exactly ten items). If the system can work out *which* piece is in play and
*what schema that piece has*, then the generation step is ordinary constrained
decoding on a smaller schema. Nothing new is needed for that step.

So the hard parts are not where the original note assumed. They are:

1. **Working out which piece** — turning "change the answer to Q3" into
   `responses[2]`.
2. **Working out the piece's schema** — cutting `S` down to the sub-schema at
   that spot. Easy for a nested Pydantic model. Harder when the schema has
   unions, recursion, or "this field is required only if that one is set".
3. **Making sure the whole still holds after you splice the piece in.**

## 6. Where it actually gets hard

Point 3 is the real research content.

Some rules live *inside* a piece, and checking them locally is enough:
`confidence` must be one of three strings, `evidence` must be a list of strings.
Constrained decoding on the sub-schema handles those completely.

Other rules span the **whole document**, and a fragment cannot see them:

- **Required siblings.** Deleting a field is fine locally, invalid globally.
- **Uniqueness across batches.** Row 9,412 must not reuse an id emitted back in
  batch 3 — but batch 3 is long gone from the current call.
- **Counts.** "Between 1 and 50 responses." Adding one piece can break that.
- **Conditional rules.** "If `status` is `resolved`, `resolution` must not be
  null." The two fields can sit in different fragments.
- **Cross-references.** A row points at an id in another table that no fragment
  has produced yet.

These are the rules that can be broken *from a distance*. They are the reason
this is a research problem and not a weekend of plumbing.

There is a second hard part worth naming: **is a smaller ask actually more
accurate?** Intuitively yes — a short focused generation should beat a long
sprawling one. But it might not be, and that is a measurement, not an opinion.

## 7. The fallback the original note also mentions

> *"or maybe after the JSON file is edited we check the full schema"*

Don't try to guarantee anything while generating. Generate the fragment, splice
it in, then validate the finished document. If it fails, retry.

Much easier to build. It trades a **guarantee** for a **retry loop** — the exact
trade constrained decoding exists to avoid. Whether that is acceptable depends
on how often it fails and how bad a bad state is. It is a real candidate answer,
not a consolation prize, and part of the research is finding out how cheap that
final check can be made.

## 8. The question, in one paragraph

*Given a schema `S`, a document `D` that satisfies it, and an instruction to
change something — or an instruction to build something too big to emit at
once — can the system decide which region is in play, derive the schema of just
that region, have the model generate only that fragment under ordinary
constrained decoding, and splice it back with a guarantee that the whole
document still satisfies `S`? Which parts of that guarantee are achievable, and
which are provably not? And is the result cheaper, faster and more accurate than
emitting the whole object?*

## 9. Three possible endings

All three are respectable outcomes. Finding out which is true is the job.

| Ending | What it would mean |
|---|---|
| **Already solved** | The pieces exist and have not been assembled. Write it up, build it, move on. |
| **Not worth solving** | Something else — cheap re-generation tricks, caching — already removes the pain, and fragments add fragility for little gain. |
| **Open** | A real gap. Then state it precisely and say what a solution must do. |

---

*Next: [`02-formulation.md`](02-formulation.md) — the same problem stated
precisely. Then [`03-research.md`](03-research.md), then
[`04-solution-approaches.md`](04-solution-approaches.md).*
