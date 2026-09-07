# 02 — Formulation

*Step 2 deliverable: the problem of [`01`](01-problem-plain-english.md) stated
precisely enough to prove things about, and to search the literature for.*

**Status of the claims below.** Definitions and the reduction in §5–§6 are
settled. Complexity claims marked ⚠ are conjectures pending the literature
review in [`03`](03-research.md); they are flagged, not asserted.

**A note on vocabulary.** No new terms are coined here. Where a concept already
has an accepted name in language theory, database theory, or constraint
programming, that name is used — *residual*, *local vs global consistency*,
*streaming validation*, *sound/complete approximation*. If any of these turn out
to fit badly, they should be renamed before the ideas spread.

---

## 1. Scope

**In scope.** Any output governed by a schema and produced repeatedly or in
pieces. Two anchor cases:

- **Edit regime** — a schema-governed document revised over many turns, each
  turn touching a small part (the form).
- **Construction regime** — a schema-governed document too large to emit in one
  generation, built from many pieces (the spreadsheet).

**Out of scope.** Code and prose editing (no schema). Agent memory and
conversational state (the user considers this solved). Unstructured output.

---

## 2. Preliminaries

**Values.** JSON values, treated as finite ordered trees:

```
J ::= null | Bool | Num | Str | [J, …, J] | {Str : J, …}
```

**Paths.** A path `p` is a finite sequence of steps, each an object key or an
array index — RFC 6901 JSON Pointer. Write:

| Notation | Meaning |
|---|---|
| `paths(D)` | the set of paths existing in `D` |
| `D[p]` | the subvalue of `D` at `p` |
| `D[p := v]` | `D` with the subvalue at `p` replaced by `v` |
| `D \ p` | everything in `D` outside `p` (the untouched remainder) |

`D[p := v]` is total on `paths(D)` and is the only update primitive needed;
insertion and deletion are handled by letting `p` address a container and `v` be
that container's new contents, or by extending paths with the RFC 6902 `-`
end-of-array token.

**Schemas.** A schema `S` denotes a set of values `⟦S⟧ ⊆ J`. Write `D ⊨ S` for
`D ∈ ⟦S⟧`. JSON Schema is the concrete language; a Pydantic model compiles to
one, so the formulation covers both.

**Serialisation.** `str(v)` is the JSON text of `v`; the model emits tokens whose
concatenation is such a text. Where it does not matter, value and text are
identified.

---

## 3. The status quo, formalised

A **constrained decoder** is a sampler `Model(c, G)` that, given context `c` and
a formal language `G`, returns a string in `L(G)`. Structured output today sets
`G = G_S`, a grammar compiled from `S`.

The guarantee constrained decoding actually provides is **prefix-validity**: at
every step the decoder masks to tokens that keep the emitted prefix extensible
within `L(G)`. It guarantees membership in `L(G)`, and nothing else.

That distinction matters, because `L(G_S) ≠ ⟦S⟧` in practice. Real compilers
approximate in *both* directions:

- **Over-approximation** (`L(G_S) ⊋ ⟦S⟧`) for anything a context-free grammar
  cannot count or compare: `uniqueItems`, `minItems`/`maxItems` beyond small
  bounds, `dependentRequired`, `if`/`then`/`else`, numeric bounds.
- **Under-approximation** (`L(G_S) ⊊ ⟦S⟧`) where a compiler fixes a canonical
  form — most commonly emitting object keys in schema order, which forbids valid
  documents whose keys are ordered differently.

Auditing which engines do which, for which keywords, was handed to the
literature review as a research question. It is load-bearing: **if today's
engines already fail to enforce whole-document constraints during full
generation, then failing to enforce them during fragment generation is not a new
cost.**

> **Answered, and the answer is stronger than the hypothesis
> ([`03`](03-research.md) §1).** `uniqueItems`, `if`/`then`/`else`,
> `dependentRequired`, `dependentSchemas`, `not`, `propertyNames` and `contains`
> are enforced by **zero engines in zero products**. `required` is enforced only
> by fixing property order to schema-declaration order — itself a departure from
> JSON Schema semantics, and an instance of the under-approximation above. Best
> measured whole-schema coverage on hard schemas is **41%**.
>
> So the residue that §6.3 treats as the cost of going fragment-wise is largely
> **pre-existing**. What is genuinely new when a write is an *in-place
> replacement* reduces to two counting constraints: `required` across a fragment
> boundary, and `minItems`/`maxItems` on the containing array.

**Confirmed at the API surface, not just in the literature.** Building the
experiment for this repository turned up a fresh instance: Google's
structured-output documentation lists `minItems` and `maxItems` as supported,
and `gemini-3.6-flash` **rejects a schema carrying either with
`400 INVALID_ARGUMENT`** — refused outright rather than silently dropped
(measured 2026-09-07; see [`../EXPERIMENT.md`](../EXPERIMENT.md)). The gap
between documented and enforced coverage is live, current, and easy to trip
over.

### 3.1 Where this leaves constrained decoding in the argument

Worth stating plainly, because the reframing moved it. Constrained decoding
enters this formulation in **three distinct roles**, and conflating them causes
confusion:

| Role | Status |
|---|---|
| The **guarantee** the status quo provides (prefix-validity, this section) | the baseline to be matched, not beaten |
| The **mechanism** step P3 uses to emit a fragment (§5) | already solved and deployed — Structural Tags |
| A **candidate answer** to the residual problem — mask exactly against `S/(D,p)` | rejected: PSPACE-complete at best, undecidable at worst (§6.1, [`03`](03-research.md) §11) |

The third is the one the original note reached for, and the one the complexity
results rule out. The second is free. So constrained decoding is load-bearing
throughout — but as the *tool*, not as the *guarantee*.

---

## 4. The workload

A sequence of tasks produces `D₀, D₁, …, D_n`, every `D_i ⊨ S`.

Let `N = |str(D)|` in output tokens, `k` the size of the region that actually
changes, and `L_max` the model's maximum output tokens per response.

Two regimes, distinguished by which resource binds:

| | Edit regime | Construction regime |
|---|---|---|
| Shape | `D_{i-1} → D_i`, tree edit distance small | `∅ → D_n`, `N` very large |
| Binding cost | `n · N` output tokens for `Σ k` of real change | `N > L_max`: **not producible at all** |
| Extra risk | silent corruption of `D \ p` | drift and inconsistency across pieces |
| Example | the form | the spreadsheet |

The construction regime has the harder constraint, because `N > L_max` is not
an expense, it is an impossibility. No decoding-speed technique removes it.

---

## 5. The proposal: fragment-wise generation

Replace one large constrained generation with a sequence of small ones. A
**write step** is a triple `(p, A, F)`:

- `p` — the **target**, a path;
- `A` — the **enforced constraint**, a language the decoder can mask against;
- `F ~ Model(c_p, A)` — the **fragment**, constrained-decoded against `A`.

and the update is `D' = D[p := F]`.

Three sub-problems fall out, and they are cleanly separable:

- **(P1) Localisation** — choose `p` from the instruction. Either the system
  computes it, or the model chooses it under a constraint enumerating
  `paths(D)`. In the latter case the model still never free-writes a pointer; it
  selects from a finite menu the system built.
- **(P2) Projection** — compute `A` from `S`, `p` and `D`.
- **(P3) Composition** — establish that `D[p := F] ⊨ S`.

---

## 6. The central definition and the reduction

**Definition (residual schema).** For a schema `S`, a document `D ⊨ S` and a
path `p`, the **residual of `S` at `p` given `D`** is

```
    S / (D, p)  =  { v ∈ J  :  D[p := v] ⊨ S }
```

the set of values that keep the whole document valid, *in the context of this
document*. This is the residual (quotient) construction from language theory,
applied to trees and schemas rather than strings and automata.

**Proposition 1 (splice soundness, trivially).**
If `D ⊨ S` and `F ∈ S / (D, p)` then `D[p := F] ⊨ S`.
*Proof: by definition of the residual.* ∎

Proposition 1 looks vacuous, and that is exactly its value: it shows the
difficulty is not "how do we guarantee validity". It relocates the entire
problem into one place.

> **Reduction.** Fragment-wise generation with a global validity guarantee is
> equivalent to *computing, or soundly approximating, the residual `S / (D, p)`
> and compiling it into a decoding constraint.*

Everything else — patch languages, diff formats, splice mechanics — is
downstream engineering. This is the object to study.

### 6.1 Two different questions about the residual

Constrained decoding does not need membership in the residual. It needs
membership *of every prefix*. Separate the two:

- **(Q1) Membership.** Given a complete `v`, is `v ∈ S / (D, p)`? This is just
  `D[p := v] ⊨ S` — ordinary schema validation. **Cheap**, and cheaper still
  incrementally, since only the ancestors of `p` and the constraints mentioning
  `p` need rechecking (this is the classical incremental-validation setting;
  bounds to be confirmed in `03`).
- **(Q2) Prefix-feasibility.** Given a partial text `w`, does there exist a
  completion `u` with `parse(wu) ∈ S / (D, p)`? This is what a token mask must
  answer at every step.

**Conjecture 1 ⚠.** Q2 is as hard as JSON Schema satisfiability with part of the
value fixed, and is therefore intractable in general — no polynomial-time exact
token mask exists for full JSON Schema. *Pending: the exact complexity of JSON
Schema satisfiability and containment, and whether the negation-free fragment is
better behaved.*

The gap between Q1 and Q2 is the formal reason the "just validate afterwards"
design is attractive: **it only ever needs the easy direction.**

### 6.2 Sound, complete, exact

Let `A` be the constraint actually enforced, `T = S / (D, p)` the truth.

| | Condition | Meaning | Failure mode |
|---|---|---|---|
| **Sound** | `⟦A⟧ ⊆ T` | everything permitted is genuinely valid | over-restrictive: forbids legal fragments, distorts the model |
| **Complete** | `⟦A⟧ ⊇ T` | nothing valid is forbidden | permissive: lets an invalid splice through |
| **Exact** | both | — | — |

Today's whole-document engines are, per §3, *neither* — over-approximating value
constraints and under-approximating key order. A fragment-wise system is
therefore not obliged to achieve exactness to be an improvement; it is obliged
to be **no worse, and honest about where it sits.**

### 6.3 Where the genuine novelty is

The residual differs from the naive syntactic sub-schema `S@p` — descend through
`S` following `p` — precisely on constraints whose satisfaction depends on parts
of the document *outside* `p`. In the standard constraint-programming
vocabulary these are the **non-local** constraints, and the standard fact
applies: **local consistency does not imply global consistency.**

Which JSON Schema keywords are non-local:

| Keyword | Why it straddles the boundary |
|---|---|
| `required` | a sibling's presence is decided elsewhere |
| `minItems` / `maxItems` | cardinality of the container, not the element |
| `uniqueItems` | needs every other element, including ones in other fragments |
| `dependentRequired` / `dependentSchemas` | explicitly couples two fields |
| `if` / `then` / `else` | the condition may live outside `p` |
| `oneOf` / `anyOf` | the branch may be fixed by context outside `p` |
| `additionalProperties` / `propertyNames` | constrains the sibling key set |
| application-level invariants (Pydantic `model_validator(mode="after")`, cross-references, foreign keys) | arbitrary, and outside JSON Schema entirely |

**Conjecture 2 ⚠.** For the fragment of JSON Schema built only from `type`,
`properties`, `items`, `enum`, `const`, `$ref` without recursion through the
target, and scalar constraints, the syntactic sub-schema *equals* the residual,
and splicing is sound with no extra machinery. Every keyword in the table above
breaks this equality.

> **Corrected after the literature review — see [`03`](03-research.md) §11.**
> The table above is right for *insert* and *delete* but **too strong for
> in-place replacement**. `required`, `minItems`/`maxItems`, `dependentRequired`,
> `propertyNames` and `additionalProperties` are key-set and length constraints,
> and replacing the value at an existing path changes neither the sibling key set
> nor the array length. The safe fragment is therefore materially **larger** than
> stated here, and largest precisely in the form case, where the operation is
> almost always replacement. The table also **misses three breakers**: `not`,
> `prefixItems` / tuple-form `items`, and the `unevaluated*` keywords.
> The class itself turns out to be prior work under three names —
> shuffle-closedness, local tree grammars, local DTDs — though the JSON Schema
> instance is unclaimed.

If Conjecture 2 holds, it gives the practical decision procedure: **compute the
non-local keywords on the path from the root to `p`; if there are none, fragment
generation is exactly as safe as full generation and needs nothing new.** That
would make a large share of real schemas — including plain Pydantic form models
— free.

---

## 7. The construction regime

The spreadsheet case is not editing. The document does not exist yet; it is
assembled from fragments `F₁, …, F_m` generated in separate calls.

**Assembly soundness.** We want: if each `F_j` satisfies its enforced constraint
`A_j`, then `assemble(F₁,…,F_m) ⊨ S`.

Here `A_j` cannot depend only on `S`. It must depend on what earlier fragments
emitted — otherwise nothing can stop batch 940 from reusing an id from batch 3.
So `A_j = α(S, j, σ_j)` where `σ_j` is a **state** summarising `F₁…F_{j-1}`.

This is exactly the setting of **streaming validation**: can a document be
validated by an automaton that sees it once, left to right, in bounded memory?
The question for us is the same question in generation form.

**Question (bounded state).** For which schemas is `|σ_j|` bounded independently
of `m`?

- `minItems`/`maxItems`: a counter. **O(log m)** — bounded, cheap.
- `required`, `if/then/else`, `dependentRequired`: a bit per pending obligation.
  **O(|S|)** — bounded, cheap.
- `uniqueItems`, foreign keys, referential integrity: needs every value emitted
  so far. **Ω(m)** — *not* bounded. There is no small summary; exact enforcement
  requires carrying the whole set, and an approximate one (a Bloom filter, say)
  trades soundness for size.

**Conjecture 3 ⚠.** The bounded-state schemas are exactly those whose non-local
constraints are counting or propositional, and the unbounded ones exactly those
requiring value equality across unboundedly many positions. *Pending: the
streaming-validation literature, which has this result for XML in some form.*

This is a clean, checkable dividing line, and it is the sharpest formal content
in the construction regime.

---

## 8. Cost model

For one turn, with `N` = document tokens, `k` = fragment tokens, `c_in`,
`c_out`, `c_cached` the per-token prices, `α` a speculative-decoding acceptance
speedup:

| | Output tokens | Input tokens | Serial steps | Feasible when |
|---|---|---|---|---|
| Full regeneration | `N` | `≈N` (cacheable) | `N` | `N ≤ L_max` |
| Full regen + speculation | `N` (still billed) | `≈N` | `≈N/α` | `N ≤ L_max` |
| Fragment | `k + O(\|p\|)` | `≈N` (cacheable) | `k` | always |

Three consequences follow directly, and they should be stated separately because
they have different strengths:

1. **Speculative decoding attacks latency, not billing.** It reduces serial
   steps; the output tokens are still produced and still charged. So the
   *money* argument for fragments survives even if the *speed* argument is
   neutralised. (Numbers to be confirmed in `03`.)
2. **Nothing about decoding speed removes `L_max`.** In the construction regime
   fragmentation is not an optimisation, it is the only way through.
3. **Speculation needs a draft.** It helps when the new output resembles
   something already available — the form edit. It does nothing for 10,000
   genuinely new rows.

### 8.1 The guarantee full regeneration structurally cannot give

Define **untouched-region integrity**:

```
    integrity  =  Pr[ D' \ p  ==  D \ p ]
```

Under fragment-wise generation this is **1 by construction** — the bytes outside
`p` are never regenerated, so they cannot change. Under full regeneration it is
some value below 1 that no amount of prompting drives to 1, because the model is
re-emitting those bytes from a distribution.

This is qualitatively different from the cost arguments. Cost is a matter of
degree and could be eroded by better inference. Integrity is a matter of kind.
**If the empirical corruption rate under full regeneration is non-negligible,
this alone justifies the work**, and measuring that rate is the single most
valuable experiment in the whole programme.

---

## 9. What a solution must deliver

1. A **projection operator** `π(S, p, D) → A`, sound or with its unsoundness
   characterised, computable in time polynomial in `|S| + |D|`.
2. **Compilation** of `A` to a decoder mask at acceptable overhead. Note that if
   `A` depends only on `S` and `p` — the Conjecture 2 case — the set of possible
   `A` is finite and precompilable, and per-request compilation cost vanishes.
   In the construction regime the batch grammar is *identical* every batch.
3. A **localisation** mechanism (P1) with measured accuracy.
4. An **assembly rule** for the construction regime with an explicit state `σ`,
   plus a stated policy for the unbounded-state constraints.
5. A **residual check**: what to validate after splicing, and proof that it is
   cheap — the incremental-validation result.
6. **Evidence** on tokens, latency, and error rate, including integrity.

---

## 10. Metrics

| Metric | Definition | Why |
|---|---|---|
| Untouched-region integrity | `Pr[D' \ p == D \ p]` | the guarantee full regen cannot give (§8.1) |
| Localisation accuracy | correct `p` chosen | isolates P1 as a failure source |
| Fragment validity | `F ∈ ⟦A⟧` | should be 1 under constrained decoding; if not, the compiler is wrong |
| Global validity | `D' ⊨ S` | measures the residual gap directly |
| Semantic correctness | is `D'` what was *asked for* | validity is not correctness |
| Tree edit distance | `d(D', D_intended)` | graded version of integrity; Zhang–Shasha |
| Output tokens, latency, cost | — | the economic case |
| Repair rate | retries needed after a failed global check | the true cost of the fallback design |

---

## 11. Hypotheses

- **H1 (economics).** Fragment generation reduces output tokens by roughly
  `N/k`, and speculative decoding does not close the *cost* gap.
- **H2 (integrity).** Full regeneration corrupts untouched regions at a
  non-negligible, measurable rate that grows with `N`. Fragment generation drives
  it to zero by construction.
- **H3 (projection is easy in practice).** For a large share of real schemas —
  Pydantic form models especially — the residual equals the syntactic
  sub-schema, so no new decoding machinery is needed (Conjecture 2).
- **H4 (localisation is the bottleneck).** Once P2 is free, the dominant error
  source is P1: choosing the wrong target. Errors move from "the model wrote
  something invalid" to "the model changed the wrong thing" — a *less* detectable
  failure, which is a real argument against the approach and must be tested.
- **H5 (bounded state).** In the construction regime, counting and propositional
  constraints are enforceable across batches with small state; value-equality
  constraints (`uniqueItems`, foreign keys) are not, and must be handled by
  carrying the set explicitly or by post-hoc repair.
- **H6 (smaller is more accurate).** A short focused generation is more accurate
  than the same content inside a long one. Plausible, unverified, and the whole
  approach is more attractive if true.

---

## 12. Open questions, in priority order

1. Is the residual computable, and at what cost? (Conjecture 1)
2. Which JSON Schema fragment is compositional? (Conjecture 2) — **the most
   useful result to have, because it is a decision procedure practitioners can
   run.**
3. Which schemas admit bounded streaming state? (Conjecture 3)
4. How cheap is incremental revalidation after a splice?
5. What is the real corruption rate of full regeneration? (H2)
6. Can models localise reliably? (H4)
7. Does the narrower constraint distort the model's distribution more than a
   whole-document constraint does?

---

*Next: [`03-research.md`](03-research.md) — what the literature says about each
of these. Raw agent reports in [`../research/raw/`](../research/raw/).*
