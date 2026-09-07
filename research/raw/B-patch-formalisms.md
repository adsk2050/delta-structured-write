# B — Patch formalisms, schema theory, and incremental validation

**Agent B research file.** Topic: the formal-theory backbone for "emit a delta, not a
whole document" under a schema guarantee.

Rules I followed: primary sources where possible; every claim tagged
`[PRIMARY]` (I fetched and read the actual spec/paper/abstract) or
`[SECONDHAND]` (I only saw it cited/described elsewhere). Complexity results are
stated with the exact problem, fragment and bound.

Status: **COMPLETE.** Full source list at the end (§13). Verdicts on the three
conjectures are in §8 (Conjecture 2), §9.3 (Conjecture 3) and §9.1 (Conjecture 1).
My own judgement is in §12; what I did not reach is listed in §12.4.

### Contents
| § | topic |
|---|---|
| 1 | Patch / diff standards for tree data (RFC 6901/6902/7396/5261, JSON Predicate) |
| 2 | Static validation of patches — **negative result** |
| 3 | XML got there first: Flux, schema alteration, XQuery Update typing |
| 4 | Incremental validation — how cheap is "re-check afterwards" |
| 5 | JSON Schema theory — the complexity table, and whether `S@p` is definable |
| 6 | Compositionality: local tree grammars and transducer typechecking |
| 7 | Streaming validation — Segoufin & Vianu |
| 8 | **CONJECTURE 2 verdict** — the compositional fragment |
| 9 | Lenses / view update; **CONJECTURE 3 verdict**; **CONJECTURE 1 verdict** |
| 10 | Schema projection as a formal operator |
| 11 | XQuery Update static typing — what was proved, where they stopped |
| 12 | **What this means for the delta problem (my judgement)** |
| 13 | Sources consulted |
| 14 | **LATE ADDITION — Bourhis et al. PODS 2017 read at primary source. Corrects §5 and §9; adds an UNDECIDABILITY result. Read this before citing any complexity bound from §5.** |

### The three verdicts, in one place
- **CONJECTURE 1 (prefix-feasibility is intractable): CONFIRMED and sharpened.**
  Q2 *is* JSON Schema satisfiability, not merely as hard as it. PTIME-complete (Q1)
  vs PSPACE-complete (Q2, non-recursive) / EXPTIME-complete (Q2, recursive) —
  Bourhis et al. PODS 2017, Props. 7 and 10, read at primary source (§14).
  **And stronger than conjectured: with cross-position value equality plus recursion
  the problem is UNDECIDABLE, even without negation** (ibid., Prop. 4, by reduction
  from two-counter machine emptiness).
  Negation-free sub-case for JSON Schema itself: **OPEN**; NP-hard, matching Bourhis
  et al.'s Prop. 2 for the sister logic.
- **CONJECTURE 2 (the compositional fragment): CONFIRMED in substance, but the CLASS
  is prior work** — it is *shuffle-closedness* (Foster et al. TOPLAS 2007) =
  *local tree grammars* (Murata et al. ToIT 2005) = *local DTDs* (Balmin et al. TODS
  2004). The breaker list needs two corrections: it is right for insert/delete, too
  strong for in-place replacement, and misses `not`, `prefixItems`, `unevaluated*`.
  **The JSON Schema instance is unclaimed.**
- **CONJECTURE 3 (bounded streaming state): CONFIRMED**, with the real theorems in
  Segoufin & Vianu PODS 2002 plus a two-line Ω(m) fooling-set lower bound. One
  omission: a fourth memory term, **nesting depth**, and their dividing line is
  recursion rather than constraint kind.

---

## 1. Patch / diff standards for tree data

### 1.1 RFC 6901 — JSON Pointer  `[PRIMARY]`
Bryan (ed.), Zyp, Nottingham (ed.), April 2013, IETF Standards Track.
<https://www.rfc-editor.org/rfc/rfc6901.txt>

ABNF (verbatim):

```
json-pointer    = *( "/" reference-token )
reference-token = *( unescaped / escaped )
unescaped       = %x00-2E / %x30-7D / %x7F-10FFFF
escaped         = "~" ( "0" / "1" )
array-index     = %x30 / ( %x31-39 *(%x30-39) )
```

Key facts:
- **The pointer language is regular.** `*( "/" reference-token )` with
  `reference-token` a starred alternation of two character classes. No nesting, no
  recursion, no counting. So the set of pointers into a *fixed* document D is a
  finite set of strings, hence a trie / DFA. **The "path half" of the proposed
  decomposition is the easy half, and it is easy for a provable reason.**
- Escaping: `~` → `~0`, `/` → `~1`. Unescape order is load-bearing: "transforming
  any occurrence of the sequence `~1` to `/`, and then transforming any occurrence
  of the sequence `~0` to `~`" — the other order corrupts `~01`.
- Array indices: decimal, **no leading zeros** (`%x30 / (%x31-39 *(%x30-39))`). So
  `/items/007` is a *syntax* error, not a lookup miss. A trie gets this free.
- The `-` token: "exactly the single character '-', making the new referenced value
  the (nonexistent) member after the last array element." RFC 6901 itself says
  evaluating `-` "will always result in ... an error condition because by
  definition it refers to a nonexistent array element." It is only useful because
  RFC 6902's `add` redefines the error behaviour. **`-` is a hole RFC 6901 leaves
  and RFC 6902 fills.**
- Error classes: invalid pointer syntax; pointer referencing a nonexistent value.
  6901 does not say what to do about them; that is delegated to the consumer.

### 1.2 RFC 6902 — JSON Patch  `[PRIMARY]`
Bryan (Salesforce), Nottingham (Akamai), April 2013, IETF Standards Track.
<https://www.rfc-editor.org/rfc/rfc6902.txt> — media type `application/json-patch+json`.

Document shape: "A JSON Patch document is a JSON document that represents an
**array of objects**. Each object represents a single operation."

Operation set — exactly six; "Its value MUST be one of 'add', 'remove', 'replace',
'move', 'copy', or 'test'; other values are errors."

| op | required members | target must exist? | notes |
|---|---|---|---|
| `add` | `path`, `value` | **no** (that is the point) | object member: create or *replace*; array index: **insert** |
| `remove` | `path` | yes | |
| `replace` | `path`, `value` | yes | |
| `move` | `from`, `path` | `from` must exist | "the `from` location MUST NOT be a proper prefix of the `path` location" |
| `copy` | `from`, `path` | `from` must exist | |
| `test` | `path`, `value` | yes | pure guard, no mutation |

Array index shifting (verbatim):
- `add`: "Any elements at or above the specified index are shifted one position to
  the right"; "The specified index MUST NOT be greater than the number of elements
  in the array"; "If the '-' character is used to index the end of the array ...
  this has the effect of appending the value to the array".
- `remove`: "If removing an element from an array, any elements above the specified
  index are shifted one position to the left."

**Order dependence / non-commutativity.** §3: "Operations are applied
**sequentially in the order they appear in the array**. Each operation in the
sequence is applied to the target document; the resulting document becomes the
target of the next operation." With index shifting this makes JSON Patch **neither
commutative nor idempotent**: `[remove /a/0, remove /a/0]` deletes two elements.
This is *the* sharp edge for us — a decode-time validator must track a **simulated
document state that evolves within a single patch**, not just the original D. The
trie is not static across a multi-op patch.

**Atomicity.** §5: "If a normative requirement is violated by a JSON Patch
document, or if an operation is not successful, evaluation of the JSON Patch
document SHOULD terminate and application of the entire patch document SHALL NOT
be deemed successful." The spec ties this to HTTP PATCH atomicity (RFC 5789).
Practical consequence for us: **a patch is a transaction, so a post-hoc validity
check of the *result* is a legitimate abort point** — you never half-apply.

**`add` and the pointer error algorithm** — the one deliberate deviation: for
`add`, RFC 6902 "defines the error handling behavior for 'add' pointers to ignore
that error and add the value as specified. However, the object itself or an array
containing it does need to exist, and it remains an error for that not to be the
case." I.e. **`add` extends by exactly one level; it does not auto-vivify a path.**
`add /a/b/c` fails if `/a/b` is absent. This is decidable from D alone, so it
belongs in the trie.

**`test` comparison semantics** (§4.6) — structural/logical equality, not textual:
strings equal iff same number of Unicode characters and code points byte-equal;
numbers "numerically equal" (so `1` == `1.0`); arrays elementwise by position;
objects by same member count with key/value matching; literals identical.
"whitespace between the member values of an array is not significant."
**`test` is the only predicate op** — the built-in optimistic-concurrency
primitive, and the natural place to hang a "the model believed D looked like this"
assertion.

### 1.3 RFC 7386 / RFC 7396 — JSON Merge Patch  `[PRIMARY for 7386 text]`
Hoffman (VPN Consortium), Snell, October 2014, Standards Track.
<https://www.rfc-editor.org/rfc/rfc7386.txt> — media type `application/merge-patch+json`.
(Obsoletion relationship 7386 → 7396 verified separately below.)

Algorithm (verbatim from 7386):

```
define MergePatch(Target, Patch):
  if Patch is an Object:
    if Target is not an Object:
      Target = {}                       # ignore contents, set to empty Object
    for each Name/Value pair in Patch:
      if Value is null:
        if Name exists in Target: remove the Name/Value pair from Target
      else:
        Target[Name] = MergePatch(Target[Name], Value)
    return Target
  else:
    return Patch
```

Limitations, in the spec's own words:
- **`null` is overloaded.** "Null values in the merge patch are given special
  meaning to indicate the removal of existing values in the target." Therefore you
  *cannot set a field to JSON `null`*. The spec concedes the format "is not
  appropriate for all JSON syntaxes". For schema-governed output this is fatal
  wherever the schema has a nullable field — a large fraction of real schemas.
- **Arrays are opaque.** "It is not possible to patch part of a target that is not
  an object, such as to replace just some of the values in an array." Any change to
  any element re-emits the whole array. That destroys the main win, because long
  arrays (row sets, extracted records, tool-call lists) are exactly where deltas
  would pay.
- **Non-object patch = total replacement.** "If the patch is anything other than an
  object, the result will always be to replace the entire target with the entire
  patch."

Upside, and it is real: merge patch is a recursive map merge, not a sequence, so
within one patch there is no ordering problem; it needs no pointer language; and
its shape is *literally a sub-shape of S with everything optional*. A merge-patch
grammar is derivable from S by a purely local schema rewrite (`required` → ∅, add
`null` to every value type, drop array-internal structure). **No trie needed.** It
is the cheapest correct thing to constrain — and the least expressive. It is the
obvious baseline any paper here must beat or explain away.

### 1.4 RFC 5261 — XML Patch Operations  `[PRIMARY]`
Urpalainen (Nokia), September 2008, Standards Track.
<https://www.rfc-editor.org/rfc/rfc5261.txt>

- Ops: `<add>` (`sel` required, plus optional `type`, `pos` ∈ {before, after,
  prepend}), `<replace>` (`sel`), `<remove>` (`sel`, `ws`). Three ops, not six —
  **no move/copy/test.**
- Selector is **a restricted subset of XPath 1.0**: element/wildcard node tests,
  predicates (attribute comparison, string value, position), `id()`, comment/text/PI
  node tests, `namespace::` axis. **Prohibited: `namespace-uri()` and
  `local-name()`.** The restriction exists to keep selectors implementable — a
  precedent for us: *patch standards deliberately restrict their path language.*
- Ordering: "Patch operations will be applied sequentially in the document order."
  Same non-commutativity as JSON Patch. On error processing stops; a
  `<patch-ops-error>` element reports the condition.
- **Schema validity — the crucial sentence:** "The instance document elements based
  on these schema type definitions MUST be well formed and SHOULD be valid," and
  the framework itself does not validate schema compliance of the result;
  specifications referencing the framework must define that requirement.
  → **RFC 5261 explicitly punts schema preservation to the caller.** The tree-patch
  standard for the most schema-obsessed data format in wide use declines to
  guarantee validity of the result. Citable admission about the difficulty.

### 1.5 JSON Predicate — `draft-snell-json-test-07`  `[PRIMARY]`
James M. Snell. Published 2013-09-24, **expired 2014-03-28. Never became an RFC.**
Individual submission, "no formal standing in the IETF standards process."
<https://datatracker.ietf.org/doc/html/draft-snell-json-test-07>
Media type `application/json-patch-test+json`.

- **First-order predicates** (17): `contains`, `contains-`, `defined`, `ends`,
  `ends-`, `in`, `in-`, `less`, `matches`, `matches-`, `more`, `starts`, `starts-`,
  `test`, `test-`, `type`, `undefined`. Trailing `-` = case-insensitive variant.
  Each takes `op` + (usually) `path` + `value`. `defined`/`undefined` take no value —
  they test presence/absence, which is exactly the `required`-adjacent predicate.
- **Second-order predicates** (3): `and`, `or`, `not`, each with an `apply` array of
  nested predicates, and an optional `path` acting as a **root prefix for all
  contained predicates** (path factoring).
- **Integration with JSON Patch, two modes:**
  - inline as a top-level op — "When a JSON Predicate object within a JSON Patch
    document evaluates as false, processing of the JSON Patch Document MUST be
    handled exactly the same as an unsuccessful JSON Patch operation" (i.e. abort).
  - as `if` / `unless` members on an operation — conditional application, and
    crucially: "the processing of the complete Patch document does **not** fail if
    the stated condition is not met. The operation is considered to be successful
    even if the stated modification is not performed."
- Errors evaluate to `false` rather than raising.

**Why this matters to us.** JSON Predicate is a small, decidable, quantifier-free
boolean assertion language over JSON Pointers — essentially a *guard logic* for
patches. It is the closest thing in the standards world to "carry the precondition
your edit assumes". **It died in 2014.** Nobody standardised guarded tree edits for
JSON. That is a negative finding worth stating: the guard vocabulary exists as a
lapsed draft and has no successor.

### 1.6 Confirmation: RFC 7386 is obsoleted by RFC 7396  `[PRIMARY, datatracker]`
<https://datatracker.ietf.org/doc/rfc7386/> — status Proposed Standard, October 2014,
marked "Obsoleted by RFC 7396". Same title, same authors, same month; 7396 corrects
errors in 7386. **Cite RFC 7396 as the live JSON Merge Patch spec.** The algorithm
quoted above is unchanged in substance.

### 1.7 Summary table — what each patch language can and cannot express

| | RFC 6902 JSON Patch | RFC 7396 Merge Patch | RFC 5261 XML Patch |
|---|---|---|---|
| addressing | JSON Pointer (RFC 6901) | implicit, by object nesting | restricted XPath 1.0 |
| insert into array at index | **yes** | **no** | yes (`pos`) |
| delete array element | **yes** | **no** (whole array only) | yes |
| set a field to `null` | **yes** | **NO — reserved for delete** | n/a |
| move / copy | yes | no | no |
| guard (`test`) | yes | no | no |
| order matters | **yes** (sequential, index-shifting) | no (recursive merge) | yes |
| commutative | **no** | effectively yes | no |
| idempotent | **no** (`add`/`remove` on arrays) | yes | no |
| grammar derivable from S alone | no — needs D for pointers | **yes** — S with all-optional + nullable | no |
| spec guarantees schema validity of result | **no** | **no** | **no — explicitly delegated** |

**The single most important row is the last one.** None of the three tree-patch
standards says anything about preserving schema validity. RFC 5261 is the only one
that even raises the question, and it delegates it.

---

## 2. Static validation of patches — did anyone type-check a patch?

### 2.1 Negative result, stated loudly  `[my own searches]`

I ran targeted searches for a static, apply-free decision procedure for
"does this patch keep the document valid for S?" over JSON. Queries used
(WebSearch, Sept 2026), all in various combinations:

- `static type checking JSON Patch schema preserving update "JSON Schema" validity without applying patch`
- `typed patches / well-typed edits / type system for document updates`
- `schema-preserving update JSON`
- `static analysis JSON Patch schema`

**Findings: nothing academic.** The results were, without exception, either
(a) blog posts recommending "validate the patch document itself against the
JSON-Patch meta-schema, then apply it and validate the result" (jsonpatch.com,
Zuplo, Medium, Broadcom API-Gateway docs), or (b) papers about a *different*
problem — JSON **subschema/containment** checking (Habib, Shinnar, Hirzel, Pradel,
"Finding Data Compatibility Bugs with JSON Subschema Checking", and the
"Type Safety with JSON Subschema" arXiv report, <https://arxiv.org/pdf/1911.12651>).

The industrial state of the art is literally: **apply the patch to a copy, run the
ordinary validator on the result, roll back on failure.** That is the design RFC
6902's atomicity clause makes safe, and it is what every API gateway does.

I am recording this as a **genuine gap for JSON specifically**. The analogous work
exists for XML (see §5) and was never carried across. Caveat on the strength of the
claim: absence of search hits is weaker evidence than a survey; but the JSON-Schema
theory community (Ghelli/Colazzo/Sartiani/Scherzinger et al., who have published
continuously on JSON Schema statics 2016-2025) has published on satisfiability,
inclusion, equivalence, witness generation and validation complexity — and, as far
as I can find, **never on updates**. That is the shape of a real hole, not a search
failure.

---

> **SCOPE NOTE (received mid-research).** The problem was reframed: the delta is not
> necessarily a patch language the model writes. The architecture is
> **localise a region → project the sub-schema S@p → generate the fragment under
> ordinary constrained decoding against the projection → splice → revalidate.**
> The theory question therefore becomes:
>
> **When does LOCAL schema-validity COMPOSE to GLOBAL schema-validity?**
> Given S, D ⊨ S, position p, fragment F ⊨ S@p — when is D[p := F] ⊨ S?
>
> Everything from §3 onward is written against that question. §1–2 stand as the
> fallback-design record.

---

## 3. XML got there first — updates, static typing, and "schema alteration"

This is the section I was told to push hardest on, and it pays off. **The XML
community solved a recognisable version of our problem between 2004 and 2010, in
different vocabulary, and reached conclusions that transfer.** The key term is
**schema alteration**: synthesising an *output* schema describing the result of an
update applied to an *input* schema.

### 3.1 Cheney, *Flux: FunctionaL Updates for XML* (extended report, arXiv 0807.1211)  `[PRIMARY — read via ar5iv HTML]`
<https://arxiv.org/abs/0807.1211> / <https://ar5iv.labs.arxiv.org/html/0807.1211>
(Journal/workshop lineage: Cheney, "LUX: A Lightweight, Statically Typed XML Update
Language", PLAN-X 2007, <https://homepages.inf.ed.ac.uk/jcheney/publications/cheney07planx.pdf>;
the PDF is DRM-locked so I read the arXiv extended report instead.)

**This is the closest existing result to what we want.** The soundness theorem,
verbatim as rendered:

> **Theorem 3 (Update soundness).** If Γ ⊢ᵃ {τ} s {τ′}, v ∈ ⟦τ⟧, and γ ∈ ⟦Γ⟧, then
> γ; v ⊢ s ⇒ᵁ v′ implies v′ ∈ ⟦τ′⟧.

In our words: **a well-typed update, applied to any document of declared input type
τ, produces a document of output type τ′ — statically, without applying it.** That
is exactly "type-check the edit" for XML. It exists. It has been available since
2007.

What it cost to get there:
- **The update language is deliberately crippled.** Flux handles insertion,
  deletion, renaming, replacement, recursive update procedures, conditional and
  sequential composition, and iteration over child nodes. It **excludes**: node
  identity / references (value semantics only), general pattern matching,
  side-effects inside queries, **unrestricted path expressions — only the child
  axis is allowed**, and absolute paths that jump back to the document root.
  Cheney's own framing: Flux "sacrifices expressiveness for semantic clarity and
  the ability to typecheck," explicitly in contrast to XQuery!/XQuery Update
  Facility, whose combination of imperative updates with functional query
  expressions gives "semantics highly sensitive to arbitrary choices."
- **Types are regular expression types with structural subtyping, XDuce-style.**
  Subtyping is the workhorse and is treated as a black box. **Cost: "this problem
  is EXPTIME-complete in general, [though] the algorithm is well-behaved in
  practice."**  ← This is a precise, citable bound, and it is the price of a static
  guarantee even in the tamed setting.
- Sound **and** complete in a specific sense: Theorems 4 and 5 establish that
  source-level typability holds **iff** the translated core expression typechecks —
  no false positives or negatives *in the translation*. (Note the scope: this is
  completeness of the source↔core correspondence, not completeness of the type
  system w.r.t. semantic validity preservation. Do not over-claim this in the paper.)
- Stated limitations: path-error analysis is intraprocedural; no pattern matching;
  completeness of path-error analysis is not proved in the presence of recursion.
- Later note in the same report: "Decidability of typechecking for the core language
  (with recursive types and functions) was later established by Cheney 2008."

**Transfer to JSON, and the honest caveat.** The `child-axis-only` restriction is
*precisely* JSON Pointer. Flux forbids exactly the thing JSON Pointer already
cannot do (no descendant axis, no predicates, no wildcards). So the JSON setting
starts inside Flux's tractable fragment for free. The gap is on the type side:
regular expression types over ordered element sequences are not JSON Schema.
JSON Schema has `oneOf`/`not`/`if-then-else`/`uniqueItems`/`dependentRequired`
and unordered object members with per-key types. Nobody has redone Flux for
JSON Schema. **That is a concrete, well-defined open problem and a good framing
for our paper: "Flux for JSON Schema".**

### 3.2 Benedikt & Cheney, *Semantics, Types and Effects for XML Updates* (DBPL 2009, LNCS 5708)  `[SECONDHAND — abstract/summary only; Springer chapter paywalled]`
<https://link.springer.com/chapter/10.1007/978-3-642-03793-1_1>

Reported contributions (I did not read the full text — flagged):
- Notes that static analysis and typechecking of XML updates was **lacking**, and
  that **"the typing rules in the current W3C proposal appear unsound for
  `transform` queries."**  ← W3C's own XQuery Update Facility type rules were
  *broken*. Worth citing as evidence that this is subtle even for standards bodies.
- Introduces **schema alteration**: synthesising an output schema describing the
  result of an update applied to an input schema.
- Gives a core language + semantics for W3C-style XML updates with an **effect
  analysis** plus schema alteration "that can be used as the basis for sound
  typechecking."

Note the word **sound** — not complete. The pattern across this whole literature is
sound-but-conservative static approximation, never sound-and-complete.

### 3.3 Related XML-update static analysis  `[SECONDHAND unless noted]`
- Bidoit-Tollu, Colazzo, Ulliana et al., **"Type-Based Detection of XML Query-Update
  Independence"** (arXiv 1205.6698, VLDB 2013 lineage). Decides, from types, whether
  a query is unaffected by an update. This is the *dual* of our problem and the
  natural formalism for "which parts of D can I leave alone". Directly relevant to
  the localisation step.
  <https://arxiv.org/pdf/1205.6698>
- Genevès/Layaïda et al. / Cirstea, Kirchner et al., **"Rewrite-based verification of
  XML updates"** (PPDP 2010), <https://dl.acm.org/doi/10.1145/1836089.1836105>.
- Bellia, Boldi et al. / Cerioli et al., **"Static Analysis of XML Document
  Adaptations"** (ER 2012) and **"Automata-based Static Analysis of XML Document
  Adaptation"** (arXiv 1210.2453) — automata-theoretic check that a *sequence of
  document adaptations* maps every document of schema S₁ into schema S₂.
  <https://arxiv.org/pdf/1210.2453>. This is the closest thing to "verify a patch
  script preserves a schema", and it is automata-based.

**Bottom line for §3.** The problem "update a tree, keep it schema-valid, decide it
statically" was posed, attacked and *partially solved* for XML. The solutions
required restricting the update language (Flux) or accepting sound-but-incomplete
analysis (Benedikt–Cheney, the automata work). **Nobody carried it to JSON Schema.**
Our contribution is not inventing the question; it is answering it for a schema
language whose operators (`oneOf`, `not`, `if/then/else`, `uniqueItems`,
`dependentRequired`, `$ref` recursion) are strictly nastier than regular expression
types over element sequences.

---

## 4. Incremental validation — how cheap is "just re-check afterwards"?

This matters more under the reframe: if revalidating after a local splice is cheap,
the decode-time guarantee becomes an optimisation, not a necessity.

### 4.1 Balmin, Papakonstantinou, Vianu, *Incremental validation of XML documents*, ACM TODS 29(4):710–751, 2004  `[PRIMARY-ish — abstract from IBM Research publication page; ACM DL returns 403]`
<https://doi.org/10.1145/1042046.1042050> · <https://research.ibm.com/publications/incremental-validation-of-xml-documents>

Setting: DTDs modelled as **extended context-free grammars**; **specialized DTDs**
decouple element *types* from element *tags*; **XML Schema** is abstracted as a
specialized DTD with restrictions on type assignment. Updates: **element tag
renamings, insertions, and deletions.**

Bounds, stated exactly:

| schema class | incremental bound | auxiliary structure |
|---|---|---|
| DTDs and XML Schemas | **O(m log n)** | **O(n)** |
| specialized DTDs | **O(m log² n)** | **O(n)** |
| **local DTDs** (identified practical subset) | **"practically constant time"**, maintaining only a list of counters | list of counters |

where **n = size of the document**, **m = number of updates**.

The authors describe this as "a significant improvement over brute-force
re-validation from scratch", with experiments against naive revalidation.

**This is the strongest single result for the "check afterwards" design.** Note two
things carefully:
1. The bound is **logarithmic in document size and linear in the number of edits**,
   not constant — and it needs an O(n) auxiliary index maintained alongside the
   document.
2. The **"local DTDs"** subset is the interesting one for us. Local = the type of an
   element is determined by its tag alone (no context). For local schemas,
   revalidation after an edit reduces to **maintaining counters**. That is the
   XML-side name for exactly the compositionality property we are chasing: **a
   schema is "local" iff local validity composes to global validity.** Our
   §6 characterisation should be explicitly framed as "what is the JSON Schema
   analogue of a local DTD?"

### 4.2 Barbosa, Mendelzon, Libkin, Mignet, Arenas, *Efficient Incremental Validation of XML Documents*, ICDE 2004, pp. 671–682  `[SECONDHAND — the Toronto PDF is DRM/compressed and would not extract; details from the Edinburgh Research Explorer record and search summary. FLAGGED — verify before citing a bound.]`
<https://www.research.ed.ac.uk/en/publications/efficient-incremental-validation-of-xml-documents/> ·
PDF (unreadable to my tools): <http://www.cs.toronto.edu/~marenas/publications/icde04.pdf>

Reported: incremental validation w.r.t. DTDs and XML Schema, considering
**insertions and deletions of *subtrees*, not only leaf/single-node updates**, and
additionally **validation of ID and IDREF attributes** (i.e. referential integrity).
For arbitrary schemas they give a **worst-case n log n time, linear space**
algorithm, "often far superior to revalidation from scratch."

Why this one matters more than Balmin for us: **subtree insertion is our splice
operation**, and **ID/IDREF is our cross-reference residue**. If they handled
referential integrity incrementally, that is direct evidence the hardest item on our
residue list is tractable in practice.

Related, also secondhand: **"Efficient Incremental Validation of XML Documents After
Composite Updates"** (XSym 2006, LNCS),
<https://link.springer.com/chapter/10.1007/11841920_8> — extends to *composite*
updates, i.e. a whole edit script rather than one edit. Also **"Incremental
Validation of String-Based XML Data in Databases, File Systems, and Streams"**
(ADBIS 2007), <https://link.springer.com/chapter/10.1007/978-3-540-75185-4_23>.
And a Microsoft patent, US 7,912,871, **"Incremental validation of key and keyref
constraints"** — XML Schema `key`/`keyref` maintained incrementally, i.e. the
industrial version of incremental referential-integrity checking.

### 4.3 Is there a JSON equivalent? — NEGATIVE FINDING  `[my own searches]`

Queries run (Sept 2026): `incremental validation JSON Schema after update revalidate
subtree local change research`; variants with "dynamic complexity", "revalidation",
"partial validation".

**I found no academic work on incremental JSON Schema validation.** What exists:
- **Blaze: Compiling JSON Schema for 10x Faster Validation** (PVLDB, 2025),
  <https://dl.acm.org/doi/10.14778/3773749.3773764> — *compilation*, not
  incrementality. Makes full revalidation ~10x faster; does not exploit locality.
- Practitioner advice to cache the compiled validator, and to stream-validate large
  documents.
- Blog-level descriptions of the *idea* of local revalidation (change a scalar →
  check its type; add a subtree → validate the subtree then re-check the parent's
  content model) — which is a restatement of Balmin's algorithm, uncited and
  unproved, on a vendor blog.

**So: the XML result exists and is sharp; the JSON result does not exist at all.**
That is a second concrete gap, and an easier one to fill than the static-typing gap.

---

## 5. JSON Schema theory — the complexity numbers, stated exactly

These are the numbers the paper must get right. **All of the following are quoted
from primary sources I read the text of** (PDF text extracted locally with
`pdftotext`; I read the actual sentences, not a summary).

### 5.1 The four results that matter

| # | problem | fragment | bound | source |
|---|---|---|---|---|
| R1 | **Validation** (data validation, "does J satisfy S") | Classical JSON Schema (≤ Draft-07) | **P-complete** (combined complexity); decidable in time O(\|S\|²·\|J\|) | Pezoa et al. WWW 2016; restated as P-complete by Attouche et al. 2024 citing both Pezoa 2016 and Bourhis 2017 |
| R2 | **Validation** | **Modern** JSON Schema (Draft 2020-12, with `$dynamicRef`/`$dynamicAnchor`) | **PSPACE-complete** | Attouche, Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, POPL/PACMPL 2024 |
| R3 | **Satisfiability** | recursive JSON Schema **without** `uniqueItems` | **EXPTIME-complete** | Bourhis, Reutter, Suárez, Vrgoč, PODS 2017 (upper+lower); EXPTIME-hardness already implied by Pezoa et al. 2016 |
| R4 | **Satisfiability** | recursive JSON Schema **with** `uniqueItems` | **in 2EXPTIME** (upper bound; matching lower bound not established) | Bourhis et al. PODS 2017 |

Plus the expressiveness result that explains why `uniqueItems` is the villain:

> **JSON Schema "cannot be captured by MSO or tree automata because of the
> `uniqueItems` constraints"**, while conversely **"JSON Schema can simulate tree
> automata. Hence, schema satisfiability is EXPTIME-hard."**
> — Attouche et al., PVLDB 15(13), §2, summarising Pezoa et al. 2016. `[PRIMARY — I read this sentence in the PVLDB PDF]`

### 5.2 Sources, verbatim

**Attouche, Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, "Witness Generation for
JSON Schema", PVLDB 15(13): 4002–4014, 2022.**  `[PRIMARY — full text read]`
<https://www.vldb.org/pvldb/vol15/p4002-sartiani.pdf> · doi:10.14778/3565838.3565852
· arXiv:2202.12849 · artifacts at doi:10.5281/zenodo.7106749

Related-work paragraph, verbatim:

> "Pezoa et al. introduced the first formalization of JSON Schema and showed that it
> cannot be captured by MSO or tree automata because of the uniqueItems constraints.
> While they focused on validation and proved that it can be decided in O(|S|²|J|)
> time, they also showed that JSON Schema can simulate tree automata. Hence, schema
> satisfiability is EXPTIME-hard."
>
> "In [Bourhis et al.] refined the analysis of Pezoa et al. They mapped JSON Schema
> onto an equivalent modal logic, called **recursive JSL**, and proved that
> **satisfiability is EXPTIME-complete for recursive schemas without uniqueItems**,
> and it is **in 2EXPTIME for recursive schemas with uniqueItems**."

(The `O(|S|²|J|)` is my reconstruction of a symbol the text extractor mangled to
"(| |2| |)"; the shape — quadratic in schema, linear in instance — is right, but
**re-check against Pezoa et al. before printing it.** FLAGGED.)

Their own contribution, verbatim:

> "The main contribution of this paper is an original **sound and complete algorithm
> for checking the satisfiability of an input schema S, generating a witness J when
> the schema is satisfiable. Our algorithm supports the whole language without
> uniqueItems.** While the existence of an algorithm for this specific problem
> follows from the results in [Bourhis et al.], where the problem is proved to be
> **EXPTIME-complete**, we are the first to explicitly describe an algorithm ...
> we detail each algorithm phase, show that each is in **O(2^poly(N))**."

> **Theorem 13 (Correctness and completeness).** "The witness generation algorithm is
> correct and complete: it returns a witness if, and only if, the schema admits a
> witness, and otherwise it indicates that the schema is not satisfiable."

On `uniqueItems` being deliberately excluded, verbatim:

> "We have left the implementation of the `uniqueItems` operator out of the scope of
> the current paper **in order to keep the size and complexity of this work under
> control**, but the fundamental techniques that we have designed ... still apply,
> with some important generalizations that we believe deserve a dedicated analysis."

In their experiments they "renamed all occurrences of `uniqueItems`, treating it as a
user-defined keyword" — i.e. they threw it away even on the corpus.

Scale of the empirical study: 6,427 unique real-world schemas cleaned from ~80K
crawled from GitHub, plus Snowplow / Washington Post / Kubernetes collections, a
synthetic set from JSON Schema Org, and a handwritten adversarial set. Timeout 3600 s.
Their finding: **"despite its exponential complexity, it behaves quite well even on
schemas with tens of thousands of nodes."**  ← This is the practical counterweight to
the EXPTIME bound and we should cite it that way.

Note also their remark on the automata route, verbatim:

> "classical reachability algorithms for alternating automata are designed to prove
> complexity upper bounds, not as practical tools. They are typically based on the
> exploration of all subsets of the state set of the automaton, hence on a sequence
> of complex operations on a set of sets whose dimension may be in the realm of
> 2^10,000."

**Directly relevant to us:** if anyone proposes "build an alternating tree automaton
for S and intersect it with the delta grammar", this sentence is the warning. The
automaton route is a proof device, not a decoder.

**Attouche, Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, "Validation of Modern
JSON Schema: Formalization and Complexity", arXiv:2307.10034v2 (1 Feb 2024);
published in PACMPL / ACM DL doi:10.1145/3632891.**  `[PRIMARY — full text read]`

Verbatim from the abstract and contributions:

> "data validation, which is expected to be an extremely efficient process, acquires,
> with Modern JSON Schema features, a **PSPACE** complexity. ... We then prove that
> its data validation problem is **PSPACE-complete**. We prove that the origin of the
> problem lies in the **Draft 2020-12 version of dynamic references**, and not in
> annotation-dependent validation. We study the schema and data complexities, showing
> that the problem is **PSPACE-complete with respect to the schema size even with a
> fixed instance** but is **in P when the schema is fixed and only the instance size
> is allowed to vary**."

> "validation was known to be **P-complete for Classical JSON Schema** [Bourhis et al.
> 2017; Pezoa et al. 2016]."

> **Corollary 6 (PSPACE-hardness).** "Validation in any fragment of Modern JSON Schema
> that includes `$dynamicRef`, `$dynamicAnchor`, `anyOf`, `allOf`, and `false`, is
> PSPACE-hard."

Proof route: reduction from **QBF validity** (Stockmeyer & Meyer 1973). The encoding
has linear size. Their PSPACE upper bound (Theorem 7) comes from a validation
algorithm whose call stack is bounded by O(n³).

They also show:
- **Annotation-dependent validation alone does NOT break P.** There is an explicit
  algorithm that runs in polynomial time "on any family of schemas where the number
  of dynamic references is bounded by a constant"; Draft 2019-09 validation is still
  in P because of its restrictions on dynamic references.
- Dynamic references can be **eliminated in favour of static references at the price
  of an exponential increase in schema size** (their §8).
- Their own framing: "this is the first time that we encounter a construct of a
  data-validation language whose complexity is not in P (unless P = PSPACE)."

**Bourhis, Reutter, Suárez, Vrgoč, "JSON: data model, query languages and schema
specification", PODS 2017, pp. 123–135; arXiv:1701.02221.**
`[SECONDHAND for the bounds — I read them quoted verbatim inside the Attouche PVLDB
paper, not in Bourhis et al. themselves. The arXiv abstract page gives only "we study
the complexity of basic computational tasks". FLAGGED — pull the PODS PDF before
final citation.]`
Contribution as reported: a formal data model for JSON, a navigational query language
(JSON navigational logic), and a **modal logic "recursive JSL" equivalent to JSON
Schema**, with a purpose-built class of **alternating tree automata**. That automaton
class is the formal object our "delta grammar" would have to be compared against.

**Pezoa, Reutter, Suárez, Ugarte, Vrgoč, "Foundations of JSON Schema", WWW 2016,
pp. 263–273.**  `[SECONDHAND — dl.acm.org paywalled, author PDF link
jreutter.sitios.ing.uc.cl/www16.pdf 301-redirects to a broken URL, ir.webis.de 404s.
Bounds taken from the Attouche verbatim quote above. FLAGGED.]`
doi:10.1145/2872427.2883029 · alternate copy: <https://dvrgoc.ing.puc.cl/data/json.pdf>

### 5.3 What R1–R4 mean for the delta problem — the theorem-shaped claim

Read the table again with our architecture in mind.

**(a) Post-hoc revalidation is cheap. Full stop.** R1 says validating a whole document
against a Classical JSON Schema is **P-complete, O(|S|²·|J|)** — and even under
Modern JSON Schema, R2's *data complexity* (schema fixed, instance varying) **is in P**.
Since the schema in our setting is fixed and known, the relevant number is the data
complexity, and it is polynomial in every version of the language. Combined with
RFC 6902's atomicity (§1.2), **"apply, validate, roll back" is a polynomial-time,
always-correct safety net.** Any argument for a decode-time guarantee has to be an
argument about *cost of a retry* or *latency*, not about *feasibility of checking*.

**(b) But "can this partial delta still be completed?" is not validation — it is
satisfiability, and that is EXPTIME-complete.** This is the central formal point.
Constrained decoding is only sound if, at every prefix, the constraint engine can
answer *"does some continuation exist that yields a valid whole?"* For ordinary
whole-document generation against a *fixed* schema that question is answerable
because the grammar is precompiled once. For our problem the question becomes:
given S, document D, position p and a partial fragment F′, **does there exist a
completion F ⊒ F′ such that D[p := F] ⊨ S?** That is a satisfiability question over
S conditioned on a context, and by **R3 it is EXPTIME-complete already without
`uniqueItems`, and only known to be in 2EXPTIME with it.**

So, stated as the claim I think the paper should make:

> **A sound *and complete* delta/fragment grammar — one that rejects exactly the
> prefixes with no valid completion — cannot be computed in polynomial time in the
> schema, unless P = EXPTIME.** The decision problem it must solve at each step is
> JSON Schema satisfiability relativised to a context, which is EXPTIME-complete for
> recursive schemas without `uniqueItems` (Bourhis et al. 2017) and in 2EXPTIME with
> it.

Two honest caveats that must accompany that claim, or a referee will kill it:
1. **The hardness is in the *schema*, not the document.** These are combined/schema
   complexities. If S is fixed and small — which it is, for a Pydantic form — the
   exponential is a constant. The right practical framing is "precompile once per
   schema, at exponential cost in schema size", exactly as Attouche et al.'s
   experiments show (tens of thousands of nodes, tractable in practice).
2. **The hardness argument is about *completeness*, not soundness.** A *sound but
   incomplete* fragment grammar — never emits an invalid fragment, sometimes rejects
   a fragment that would have been fine — is cheap, and is what everyone in the XML
   world settled for (§3). The interesting research question is therefore **how much
   completeness you can buy at polynomial cost**, not whether you can have it all.

**(c) `uniqueItems` is the single operator that breaks the formal frame.** Pezoa et
al.'s result — JSON Schema is **not** capturable by MSO or by tree automata *because
of* `uniqueItems` — is the reason we cannot just say "compose two tree automata and
be done". Every automata-theoretic tool (closure under intersection, product
construction, the incremental-validation results of §4, the transducer typechecking
of §6) lives in the regular/MSO world and **`uniqueItems` is outside it.** Note also
that Attouche et al.'s state-of-the-art witness generator simply does not implement
it. Our residue list should be re-sorted with `uniqueItems` at the top, promoted from
"awkward" to "provably outside the automata framework".

**(d) `$dynamicRef` should be banned by our design, on evidence.** R2 says dynamic
references alone move *validation* from P-complete to PSPACE-complete, and that they
can be compiled away into static references at exponential blow-up in schema size. A
delta/fragment system should require Classical JSON Schema (or Draft 2019-09
restrictions). Pydantic-generated schemas are Classical in this sense, so this costs
us nothing in the motivating use case, and we can say so with a citation.
### 5.4 CORRECTION AND UPGRADE — the authoritative complexity table

I then found the consolidated table from the same group's survey/tutorial. **Use this
table, not my §5.1 reconstruction, in the paper.** It is finer-grained: it separates
recursion from `uniqueItems` and gives four rows.

**Baazizi, Colazzo, Ghelli, Sartiani (+ Scherzinger et al.), "Everything You Always
Wanted to Know About JSON Schema (But Were Afraid to Ask)", EDBT 2025 Tutorial
Paper.**  `[PRIMARY — full text read via pdftotext]`
<https://openproceedings.org/2025/conf/edbt/paper-T3.pdf>

> **Table 1: Complexity results for Classical JSON Schema.**
>
> | schema features | **Validation** | **Satisfiability** |
> |---|---|---|
> | no recursion, **no** `uniqueItems` | **PTIME-complete** | **PSPACE-complete** |
> | no recursion, **with** `uniqueItems` | **PTIME-complete** | **PSPACE-hard, in EXPSPACE** |
> | **recursion**, no `uniqueItems` | **PTIME-complete** | **EXPTIME-complete** |
> | **recursion**, with `uniqueItems` | **PTIME-complete** | **EXPTIME-hard, in 2EXPTIME** |

Accompanying text, verbatim:

> "Validation for Classical JSON Schema has been proved to be **PTIME-complete** by
> Pezoa et al. and by Bourhis et al., while satisfiability is **EXPTIME-hard and in
> 2-EXPTIME**. Bourhis et al. also proved that satisfiability is **EXPTIME-complete
> when `uniqueItems` is omitted**. **Since satisfiability and inclusion for Classical
> JSON Schema are equivalent, these results also apply to inclusion and
> equivalence.**"

Three things to take from this that I did not have before:

1. **Validation is PTIME-COMPLETE, not merely "in P", in all four rows.** So it is
   cheap in the complexity-class sense but **P-complete means it is not known to
   parallelise well** — it is inherently sequential. Irrelevant at our scale, but be
   precise if a referee reads carefully. (My earlier note of an `O(|S|²·|J|)` bound
   from the Attouche related-work paragraph: keep it as a concrete running time,
   but the *class* statement is PTIME-complete. A separate search result also
   states validation is **linear** in schema and document when `uniqueItems` is
   absent — plausible and consistent with PTIME-completeness, but I could not
   confirm it from the Pezoa text itself. FLAGGED.)

2. **Non-recursive schemas are PSPACE-complete for satisfiability, not EXPTIME.**
   This matters *enormously* for the Pydantic-form use case, which is almost always
   non-recursive. The honest headline is therefore:
   **satisfiability of the schemas we actually care about is PSPACE-complete**
   (PSPACE-hard/EXPSPACE if `uniqueItems` appears). Still super-polynomial, still
   enough to make a sound-and-complete fragment grammar infeasible in general — but
   do not say EXPTIME when the schema is a flat form.

3. **Containment ≡ satisfiability for Classical JSON Schema.** This is what licenses
   the whole "S@p projection" programme to be *stated* — asking "is every document
   valid for the projected sub-schema also acceptable in context?" is a containment
   question, and it costs the same as satisfiability. There is no cheaper back door.

### 5.5 Is "S@p" — the sub-schema at a path — even well-defined?  `[JUDGEMENT + evidence]`

The reframed architecture needs an operator `S@p` = "the schema that governs the
value at pointer p". **There is no such operator in the JSON Schema specification,
and for good reason.** What exists and what breaks:

**Works (the easy 80%):** for a path of plain `properties`/`items` steps through a
schema built only from `type`, `properties`, `items`, `$ref` to `$defs`, and
`required`, the sub-schema at p is just the syntactic sub-object you reach by walking
`properties/<key>` and `items` — and `$ref: "#/$defs/Foo"` gives you a *named*
sub-schema directly. **Pydantic gives us this for free**: every nested `BaseModel`
becomes a `$defs` entry, so for a nested-model field, `S@p` is literally
`S["$defs"][ModelName]`, a stand-alone schema you can hand to any constrained decoder
today. This is why the Excel/Pydantic use case looks tractable — the common case has
a syntactic answer.

**Breaks — and these are exactly our residue, restated as "projection is not a
function":**
- **`oneOf` / `anyOf` / `allOf` above p.** If p sits under a `oneOf`, there is no
  single sub-schema at p; there is one per branch. Projection returns a *set*, and
  which element is correct depends on a branch choice made elsewhere in D. With
  `allOf` you must intersect, and **JSON Schema has no syntactic intersection
  operator that stays inside the language for all keyword pairs** — `allOf` is the
  intersection, but you cannot in general fuse `allOf: [A, B]` into one flat schema
  without the canonicalisation machinery of Habib et al. / Attouche et al.
- **`if`/`then`/`else` and `dependentRequired` spanning the boundary.** The condition
  reads siblings of p; the consequence constrains p. So `S@p` is not a schema, it is
  a schema *parameterised by the sibling context* — a function from context to schema.
- **`not` above p.** Projection under negation is not compositional at all: a fragment
  being valid for the projected body of a `not` is precisely what you must avoid.
- **`uniqueItems` / `minItems` / `maxItems` / `minProperties` / `maxProperties` on the
  container of p.** These are constraints on the *container*, not on p, and no
  projection to p can carry them. Cardinality and uniqueness are the canonical
  non-projectable constraints.
- **`$ref` recursion and `$dynamicRef`.** A recursive `$ref` makes the "sub-schema at
  p" depend on the unfolding depth. `$dynamicRef` makes it depend on the *dynamic
  scope* — the resolution is not determined by the syntactic position at all. This
  is a second, independent reason to ban Modern JSON Schema's dynamic references from
  our design (see 5.3(d)).
- **Root-level `$ref` and `$defs` that are only reachable through combinators** —
  a practical Pydantic failure mode: a discriminated union serialises as
  `oneOf` + `discriminator`, and the sub-schema at a field inside the union is
  ambiguous until the discriminator value is fixed.

**So the correct formal shape of the operator is not `S@p : Schema`, it is**

> `S@(D, p) : Context → Schema`, i.e. **projection must be relativised to the
> document D and, in general, returns a set of candidate schemas indexed by the
> combinator choices made outside p.**

That is the honest statement, and I think it is a genuine contribution to write it
down precisely. The good news is that for the *ground* case — D is known, so every
`if`/`then`/`else` condition, every `oneOf` branch and every `dependentRequired`
antecedent that depends only on parts of D *outside* p can be **evaluated, not
symbolically carried**. Fixing D collapses the function to a single schema, except
for the parts of the condition that read *inside* p. That is a real and usable
restriction, and it is the JSON analogue of what §3's XML work called "schema
alteration relative to an input type".

---

## 6. Compositionality — the classical answer, in tree-grammar vocabulary

The reframed question ("when does local validity compose to global validity?") has
an exact classical answer, and it predates JSON by a decade. The name is
**local tree grammar**, and the surrounding theory is the Murata taxonomy.

### 6.1 Murata, Lee, Mani, Kawaguchi, *Taxonomy of XML Schema Languages using Formal Language Theory*, ACM Transactions on Internet Technology 5(4), 2005  `[PRIMARY — full text read via pdftotext]`
<https://pike.psu.edu/publications/toit05.pdf> · doi:10.1145/1111627.1111631

Definitions, verbatim:

> **Definition 2.4.** "Two different non-terminals A and B are said to be **competing**
> with each other if — one production rule has A in the left-hand side, — another
> production rule has B in the left-hand side, and — these two production rules share
> the same terminal in the right-hand side."
>
> **Definition 2.5.** "A **local tree grammar** is a regular tree grammar without
> competing non-terminals."
>
> **Definition 2.6.** A **single-type tree grammar** is a regular tree grammar such
> that (i) start symbols do not compete, and (ii) no two non-terminals occurring in
> the same content model compete.
>
> **Theorem 2.1.** "The class of regular tree languages properly includes the class of
> single-type tree languages, which in turn properly includes the class of local tree
> languages."

Correspondence to real schema languages: **local ≈ DTD; single-type ≈ W3C XML Schema
(strictly: XML Schema is *restrained-competition*, a slight relaxation, §6.3 of their
paper); regular ≈ RELAX NG / XDuce.**

**The closure table — this is the part that decides our question:**

> **Theorem 2.2.** "The class of single-type tree languages and that of local tree
> languages are **not closed under union**." (Stronger: the union of two *local* tree
> languages is not always even single-type.)
>
> **Theorem 2.3.** "The class of single-type tree languages and that of local tree
> languages are **not closed under set difference**."
>
> **Theorem 2.4.** "The class of single-type tree languages and that of local tree
> languages **are closed under intersection**."
>
> **Theorem 2.5.** "The class of regular tree languages is **closed under union,
> intersection, and set difference**" [Takahashi 1975].

And their own note on why closure matters, verbatim:

> "Type inference for XML programming or query languages ... are based on these
> operations. The **intersection** operation is typically used for the type inference
> of pattern matching ... The **difference** operation can be used for checking
> 'subtyping' or detecting if a tree language L₁ is a subset of another tree language
> L₂. That is, L₁ is a subtype of L₂ exactly when the set difference between L₁ and
> L₂ is empty."

**Why this is the answer to the compositionality question.** In a **local** tree
grammar, the type of a node is a function of its *tag alone* — no context, no
competition. Therefore, if you take a valid tree, cut out the subtree at position p,
and paste in **any** other tree whose root has the same tag and which is itself valid,
the result is valid. **Local ⇒ splicing is sound with no extra machinery.** In a
**single-type** grammar the type of a node is determined by its tag *plus its
parent's type*, so splicing is sound provided the fragment is generated against the
correct *contextual* type — one extra bit of context, computable top-down in one pass
(their Algorithm 2). In a general **regular** tree grammar the type is only
determined by a global interpretation, splicing is not locally checkable, and their
Algorithm 3 has to carry *sets* of non-terminals and prune on the way back up.

This maps our three-tier situation exactly:

| tree-grammar class | context needed to splice safely | JSON Schema analogue |
|---|---|---|
| **local** | none — tag alone | `type`/`properties`/`items`/scalars only |
| **single-type** | the parent's type (one non-terminal) | + non-recursive `$ref` to `$defs`, resolved `oneOf` above p |
| **regular** | a set of candidate types, resolved globally | `oneOf`/`anyOf`/`not`/`if-then-else` |
| **beyond regular** | not finitely summarisable | **`uniqueItems`, cross-references** |

### 6.2 Typechecking tree transducers — the frame for "does this edit language preserve S"

`[SECONDHAND for the bounds. The two PDFs I pulled (Frisch & Hosoya, "Towards
Practical Typechecking for Macro Tree Transducers", arXiv:cs/0701176; and the survey
arXiv:2409.03169) extracted with broken font encoding and I could not read the
theorem text. The numbers below come from search summaries and from the standard
statement of these results — VERIFY BEFORE CITING.]`

- **Milo, Suciu, Vianu, "Typechecking for XML transformers", PODS 2000 pp. 11–22;
  journal version JCSS 66(1), 2003.** Transformations modelled by a **k-pebble
  transducer**, types by **regular tree languages**. Main result: typechecking (given
  input type and output type, does every output of the program conform?) is
  **decidable** for this very wide class. Method: **inverse type inference** — compute
  the pre-image of the output type and check containment of the input type in it;
  this works because *the inverse image of a regular tree language under a k-pebble
  transducer is regular*.
- **Complexity: non-elementary.** The reported statements are (i) "the technique of
  inverse type inference ... has **non-elementary** complexity"; (ii) "**k-pebble tree
  transducers ... can be typechecked in (k+2)-fold exponential time**"; (iii) "the
  time complexity of typechecking an n-fold composition of macro tree transducers is
  **non-elementary**".
- **Forward type inference does not work.** Reported from Milo et al. 2003 / Suciu
  2002: *forward* type inference is **not complete**, because "the output type of a
  program may actually be a **non-regular** tree language that cannot be inferred."
  ← This is important and slightly counter-intuitive: you cannot in general compute
  "the schema of the result of applying this edit program". You can only *check* a
  proposed output type, by going backwards.
- Restricted classes recover tractability; **Martens & Neven, "Typechecking Top-Down
  Uniform Unranked Tree Transducers"** (ICDT 2003, LNCS 2572) is the standard entry
  point for the tractable-fragment programme, and **"The time complexity of
  typechecking tree-walking tree transducers"** (Acta Informatica, 2008) for the
  refined bounds. `[both SECONDHAND — abstracts only]`

**Does this give us a ready-made "edit language E preserves S" theorem?** *Formally
yes, practically no.* Model the splice-at-p operation as a transducer T_p; ask
whether T_p maps L(S) into L(S). That is exactly Milo–Suciu–Vianu typechecking, it is
decidable, and it is non-elementary. **And it is unavailable for JSON anyway**,
because Pezoa et al. showed JSON Schema is *not* a regular tree language once
`uniqueItems` is present — the entire framework assumes regular types. So the
transducer literature gives us the *shape* of the theorem and a decidability result
for the regular fragment, at a complexity nobody would run.

---

## 7. Streaming validation — the right theory for the bulk-generation case

This is the best-fitting classical result for the Excel / 10-rows-at-a-time case, and
it is a genuinely tight fit: **"generate batch k+1 given a bounded summary of batches
1..k" is streaming validation run backwards.**

### 7.1 Segoufin & Vianu, *Validating Streaming XML Documents*, PODS 2002, pp. 53–64  `[PRIMARY — full text read via pdftotext]`
<https://www.di.ens.fr/~segoufin/Papers/Mypapers/streaming-pods.pdf>

Setup, verbatim from the abstract:

> "This paper investigates the **on-line validation of streaming XML documents with
> respect to a DTD, under memory constraints**. We first consider validation using
> **constant memory, formalized by a finite-state automaton (fsa)**. ... The main
> results of the paper provide **conditions on the DTDs under which validation of
> either flavor can be done using an fsa**. For DTDs that cannot be validated by an
> fsa, we investigate two alternatives. The first relaxes the constant memory
> requirement by allowing **a stack bounded in the depth of the XML document**, while
> maintaining the deterministic, one-pass requirement. The second approach consists
> in **refining the DTD to provide additional information that allows validation by
> an fsa**."

Terminology: **strong validation** = also checks well-formedness; plain **validation**
= assumes the input is well-formed. A DTD is **(strongly) recognizable** if an fsa can
(strongly) validate it.

The theorems, verbatim:

> **Theorem 3.1.** "A specialized DTD is **strongly recognizable iff it is
> non-recursive**."
>
> **Theorem 3.2.** "Let T be a set of trees over Σ. The language L(T) is **regular iff
> there exists a non-recursive specialized DTD d such that T = SAT(d)**."
> (i.e. non-recursive specialized DTDs are *exactly* the type systems that admit
> constant-memory strong streaming validation — there is nothing else.)
>
> **Theorem 4.1.** gives an exact characterisation of recognizable DTDs **in the
> "fully recursive" case** (all element tags that lead to recursive tags are mutually
> recursive).
>
> **Theorem 4.2.** "Given a specialized fully recursive DTD d over fixed alphabet Σ,
> it is **decidable in EXPTIME whether d is recognizable**."
> — and, from the introduction, **"in polynomial time for DTDs using 1-unambiguous
> regular expressions, as required by XML Schema."**
>
> **Theorem 5.1.** "Let d be a specialized DTD. There exists a **deterministic pda**
> that accepts precisely L(d)" — "using a stack of depth bounded by the maximum
> number of unmatched open tags occurring as the input is read from left to right",
> i.e. **bounded by the depth of the tree**, not its size.

Two further results stated in the introduction, verbatim:

> "the construction of the standard fsa ... **always accepts only documents valid
> w.r.t. the DTD (but possibly more)**, and accepts precisely the documents valid
> w.r.t. the DTD, whenever the DTD is recognizable. The standard fsa can be
> constructed in **time exponential in the DTD**."
>
> "**for every DTD one can find a specialization of it which is recognizable.**
> Intuitively, this is obtained by **refining the tags of the original DTD to include
> more information useful for quick validation**. This provides a trade-off between
> 'accuracy' of the tags and the ability to perform efficient streaming validation."

And an honest open problem they leave, verbatim:

> "The conditions of Lemmas 4.2 and 4.4 are necessary in order for a DTD to be
> recognizable. The conditions of Theorem 4.3 are sufficient ... **The complete
> characterization of recognizable DTDs remains open.**"

**Why every one of these transfers to us.**
- Theorem 3.1 + 3.2 say the constant-memory-streamable schemas are **exactly the
  non-recursive ones**. Our motivating schemas (a Pydantic form, an Excel row schema)
  are non-recursive. **So the bulk-generation case sits precisely inside the class
  the theory says is safe.** That is a much stronger statement than "it seems to work".
- Theorem 5.1 says even the recursive ones are streamable with a stack **bounded by
  document depth**. JSON documents are shallow and wide — exactly the regime where a
  depth-bounded stack is effectively constant. So the cross-batch state for the Excel
  case is O(depth) plus whatever the non-local constraints need.
- The **specialization** result is the formal home for the coordinator's item 9
  ("what must the fragment carry"): *refine the tags to carry the information the
  validator needs*. In JSON terms: **pass the fragment a small annotation naming its
  contextual type / resolved branch**, and a schema that was not streamable becomes
  streamable. It is a trade-off, not a free lunch — Segoufin & Vianu say so
  explicitly — but it is a *named, proved* trade-off we can cite.
- Theorem 4.2's "polynomial for **1-unambiguous** regular expressions, as required by
  XML Schema" is the precedent for our design move of restricting the schema language
  to buy a decision procedure.

### 7.2 Successors  `[SECONDHAND]`
- **Segoufin & Sirangelo, "Constant-Memory Validation of Streaming XML Documents
  Against DTDs", ICDT 2007, LNCS 4353**,
  <https://link.springer.com/chapter/10.1007/11965893_21> — closes part of the gap
  Segoufin & Vianu left open, for constant memory. Should be read before final write-up.
- **"Stackless Processing of Streamed Trees", PODS 2021**,
  <https://dl.acm.org/doi/abs/10.1145/3452021.3458320> — modern successor on what can
  be done with no stack at all.
- **Streaming JSON Schema validation: I found no academic work.** Practitioner tools
  do incremental *parsing* of large JSON, and JSON Schema validators exist that work
  over a SAX-like event stream, but there is no characterisation of which JSON Schemas
  admit bounded-memory streaming validation. **This is the direct JSON analogue of
  Segoufin & Vianu and it is missing.** It is, in my judgement, the single most
  tractable and most publishable gap on this whole list.

---

# 8. ADJUDICATION OF THE THREE CONJECTURES

Read the verdict lines first. Everything after each verdict is the argument, with
sources marked `[PRIMARY]` / `[SECONDHAND]` / `[MINE]` (my own derivation — check it,
do not cite it as literature).

---

## CONJECTURE 2 — the compositional fragment

> **Claim under review.** For the JSON Schema fragment built only from `type`,
> `properties`, `items`, `enum`, `const`, non-recursive `$ref` and scalar
> constraints, the naive syntactic sub-schema `proj(S, p)` (descend through S
> following p) **equals** the residual `S/(D,p) = { v : D[p := v] ⊨ S }`, so
> splicing a locally-valid fragment is globally sound with no new machinery. And
> exactly these keywords break it: `required`, `minItems`/`maxItems`, `uniqueItems`,
> `dependentRequired`/`dependentSchemas`, `if`/`then`/`else`, `oneOf`/`anyOf`,
> `additionalProperties`/`propertyNames`.

### VERDICT: **CONFIRMED in substance, but the conjecture is stated too weakly in one direction and too strongly in another. It needs one added hypothesis and two corrections. The classical statement of it exists — for XML, not for JSON.**

- **Too strong:** the breaker list is only correct for **insertion and deletion**.
  Under **in-place replacement** — which is the "change the answer to Q3" case —
  `required`, `minItems`/`maxItems`, `dependentRequired`, `additionalProperties` and
  `propertyNames` are all **compositional after all**, and the safe fragment is
  correspondingly larger.
- **Too weak:** the list is missing **`not`**, **`prefixItems` / tuple-form `items`**,
  and Modern JSON Schema's **`unevaluatedProperties` / `unevaluatedItems`**.
- **Missing hypothesis:** `proj` must be *total* at p. It is undefined when p passes
  through `additionalProperties`, `patternProperties`, or a combinator.

### 8.2.1 Why the fragment works — the actual reason  `[MINE, but it is the standard argument]`

In the conjectured fragment, validation is a **conjunction of independent,
position-indexed constraints**. Precisely: for this fragment there is a function
`c(·)` from paths to "local constraints" such that

> `x ⊨ S`  ⟺  for every path q in x, the value `x@q` satisfies `c(q)` — where
> `c(q)` depends **only on q**, never on any other part of x.

That holds because every keyword in the fragment is either (i) a scalar predicate on
the node itself (`type`, `enum`, `const`, `minimum`, `pattern`, …) or (ii) a *routing*
keyword (`properties`, `items`, `$ref`) that says which sub-schema applies to which
child, and routes by **key or by "all elements"**, never by value and never by
position. And `c(q) = proj(S, q)` by construction.

Given that, the splice theorem is one line. Write `D' = D[p := v]`.
Paths in `D'` split into those **inside** p and those **outside**.
- Outside: `D'@q = D@q` and `c(q)` is unchanged (this is where the extra hypothesis
  bites — see the array caveat below), so those conjuncts hold because `D ⊨ S`.
- Inside: `q = p·r`, `D'@q = v@r`, and `c(p·r) = proj(proj(S,p), r)`, so those
  conjuncts hold exactly when `v ⊨ proj(S,p)`.

Hence `D[p := v] ⊨ S ⟺ v ⊨ proj(S,p)`, i.e. `proj(S,p) = S/(D,p)`. ∎

**The two corrections both come from breaking one of those two bullets.**

### 8.2.2 Correction 1 — the operation matters, and replacement is much safer than the conjecture assumes  `[MINE]`

Several keywords on the conjectured breaker list constrain **the shape of the
container** (which keys exist, how many elements), not **the values at positions**.
An in-place replacement changes no key set and no array length. So:

| keyword | breaks under **replace at existing p**? | breaks under **add / remove**? | why |
|---|---|---|---|
| `required` | **no** | **yes** | constrains the key *set*; replacement preserves it |
| `minItems` / `maxItems` | **no** | **yes** | constrains array *length* |
| `minProperties` / `maxProperties` | **no** | **yes** | constrains key count |
| `dependentRequired` | **no** | **yes** | antecedent and consequent are both about *presence* |
| `additionalProperties` | **no**, if p is a declared property | **yes** | governs *undeclared* keys |
| `propertyNames` | **no** | **yes** | constrains key strings |
| **`uniqueItems`** | **YES** | yes | the only *value-comparing* keyword in the list |
| **`dependentSchemas`** | **YES** | yes | consequent is a schema that can constrain p's value |
| **`if`/`then`/`else`** | **YES** | yes | both directions — see below |
| **`oneOf`/`anyOf`** | **YES** | yes | no single projection; `oneOf` is non-monotone |
| **`not`** (omitted from the conjecture) | **YES** | yes | projection is anti-monotone under negation |
| **`prefixItems`** / tuple `items` (omitted) | no | **YES** | index shifting relocates siblings |
| **`unevaluated*`** (omitted) | **YES** | yes | annotation-dependent; constraint at p depends on which *other* keywords matched |

So the honest characterisation is a **two-dimensional** one: *(fragment of the schema
language) × (which operation you allow)*. The conjectured breaker list is the correct
list for **insert/delete**; for **in-place replacement** the true breaker list shrinks
to exactly the keywords that let one position's *value* influence another's
constraint:

> **`uniqueItems`, `dependentSchemas`, `if`/`then`/`else`, `oneOf`/`anyOf`, `not`,
> `unevaluatedProperties`/`unevaluatedItems`.**

This is a materially better result than the conjecture, and it is the one that matters
for the Pydantic-form case, which is pure in-place replacement.

**Worked counterexamples** (so the paper can print them):

- `uniqueItems` — `S = {type:array, uniqueItems:true, items:{type:string}}`,
  `D = ["a","b"]`, `p = "/1"`, `v = "a"`. `v ⊨ proj(S,p) = {type:string}` but
  `D[p:=v] = ["a","a"] ⊭ S`. **proj ⊋ residual.**
- `if`/`then`/`else`, condition outside p — `S = {if:{properties:{kind:{const:"eu"}},
  required:["kind"]}, then:{properties:{vat:{pattern:"^[A-Z]{2}"}}},
  properties:{kind:{type:string}, vat:{type:string}}}`,
  `D = {kind:"eu", vat:"DE1"}`, `p = "/vat"`, `v = "1234"`.
  `v ⊨ proj(S,p) = {type:string}` but the spliced document violates `then`.
  **proj ⊋ residual.**
- `if`/`then`/`else`, condition **inside** p — same S, `p = "/kind"`, `D = {kind:"us",
  vat:"1234"}`, `v = "eu"`. Now flipping p's value activates `then`, which constrains
  a **sibling**. **residual ⊊ proj, and the failure is not even at p.**
- `oneOf` non-monotonicity — `S = {oneOf:[{properties:{a:{type:integer}}},
  {properties:{a:{type:number}}}]}`. Making the fragment at `/a` "better" (an integer
  rather than a float) makes the document satisfy **both** branches and therefore
  fail `oneOf`. This is the sharpest one: **improving a fragment can break the
  document**, which no monotone framework can model.
- `prefixItems` under insert — `S = {prefixItems:[{type:string},{type:integer}]}`,
  `D = ["a", 1]`, insert `"z"` at `/0`. Every element still satisfies *some* declared
  slot, but `D' = ["z","a",1]` fails because `/1` must now be an integer.

### 8.2.3 Correction 2 — `proj` is a partial function, and where it is undefined  `[MINE]`

`proj(S,p)` is only defined if every step of p is routed by a keyword that names it.
It is **undefined** (not merely wrong) when a step of p lands on:
- a key not in `properties` and not matched by `patternProperties` — then the governing
  schema is `additionalProperties`, which the naive descent does not visit;
- a key matched by **several** `patternProperties` — the governing schema is the
  *conjunction*, and JSON Schema has no flattening operator for it inside the fragment;
- any combinator (`allOf`/`anyOf`/`oneOf`/`not`/`if`) sitting *above* p — for `allOf`
  the answer is a conjunction, for the rest there is no single answer at all;
- a `$ref` cycle that does not consume a path segment (a schema whose `$ref` points at
  itself or a `$ref` cycle through `allOf`). For **guarded** recursion — every cycle
  passes through a `properties`/`items`/`prefixItems` step — `proj` terminates for any
  finite p, and non-recursive `$ref` is a special case. **This is the precise
  condition to put on `$ref`: guardedness, not non-recursion.** Pydantic's `$defs`
  references are always guarded, so recursive Pydantic models are fine here.

So the practitioner's decision procedure the conjecture asks for is real, and it is
this:

> **Walk the path from the root of S to p.** At each step, record the keyword that
> routes you. **Reject** (fall back to whole-document regeneration) if you ever pass
> a combinator (`anyOf`/`oneOf`/`not`/`if`), an `unevaluated*`, an
> `additionalProperties`/`patternProperties` step, or a `dependentSchemas`; **and**
> reject if any schema on that root-to-p path, or the schema at p's parent, carries
> `uniqueItems`. `allOf` is passable if you intersect. If the walk completes, splicing
> a fragment generated against `proj(S,p)` is **exactly** as safe as regenerating the
> whole document. If the edit is an insert or delete rather than a replacement, also
> reject on `required`, `min/maxItems`, `min/maxProperties`, `dependentRequired`,
> `propertyNames`, `additionalProperties`, and `prefixItems` anywhere on that path.

That is O(|p|) work over the schema, runnable in a few lines. It is sound, and it is
conservative (it will reject some safe cases, e.g. an `anyOf` all of whose branches
agree at p).

### 8.2.4 Has anyone characterised this? — YES for XML, THREE TIMES. NO for JSON.

This is the important literature answer, and the conjecture is a rediscovery of a
1990s–2000s idea in JSON clothing.

1. **Murata, Lee, Mani, Kawaguchi (ACM ToIT 2005) — `local tree grammar`.**
   `[PRIMARY, §6.1 above]`. Definition 2.5: "A local tree grammar is a regular tree
   grammar without competing non-terminals." Competing (Def. 2.4) = two production
   rules with different non-terminals on the left sharing the same *terminal* on the
   right. **No competition ⟺ a node's type is a function of its tag alone ⟺ splicing
   any valid same-tagged subtree preserves validity.** That is precisely the property
   the conjecture is naming. Local ≈ DTD. Their **Theorem 2.1** gives the strict
   hierarchy local ⊊ single-type ⊊ regular; **Theorem 2.4** says local and single-type
   are closed under intersection but (Theorems 2.2, 2.3) **not** under union or set
   difference. Read the closure table as: **`allOf` keeps you in the compositional
   class; `anyOf`/`oneOf` and `not` throw you out of it.** That is exactly the
   conjecture's breaker list, proved in 2005 for a different data model.
2. **Balmin, Papakonstantinou, Vianu (ACM TODS 2004) — `local DTDs`.**
   `[PRIMARY-ish, §4.1 above]`. They isolate "local DTDs" as the practical subset for
   which revalidation after an update is possible in "practically constant time by
   maintaining only a list of counters". Same class, arrived at from the incremental-
   validation side rather than the type side.
3. **Segoufin & Vianu (PODS 2002) — non-recursive specialized DTDs.**
   `[PRIMARY, §7.1 above]`. Theorem 3.2 characterises the type systems admitting
   constant-memory one-pass validation as *exactly* the non-recursive specialized
   DTDs. A different cut through the same idea: bounded context.
4. **Cheney's Flux (§3.1)** is the update-language version: its type system's
   soundness theorem is exactly "a well-typed edit maps τ into τ′", and the price was
   restricting the path language to the **child axis only** — which is what JSON
   Pointer already is.

**For JSON Schema, nobody has written this down.** I searched (Sept 2026) for a
compositional/local/splice-safe fragment of JSON Schema and found nothing: the JSON
Schema statics literature (Pezoa et al. 2016; Bourhis et al. 2017; Habib et al.
subschema checking; the whole Attouche/Baazizi/Colazzo/Ghelli/Sartiani/Scherzinger
programme 2021–2025) is about **validation, satisfiability, inclusion, equivalence
and witness generation of *whole* documents**. Updates, splicing and locality do not
appear. **The characterisation the conjecture asks for is a real, unclaimed, and
frankly small-enough-to-actually-prove contribution.** The right framing for a
referee is: *"we identify the local fragment of JSON Schema, in the sense of Murata
et al.'s local tree grammars, and show it is exactly the fragment for which
fragment-wise generation is sound."*

**One caveat that must go in the paper** (datum supplied by another agent, and it is
a good one): in **Pydantic**, cross-field constraints written as
`@model_validator(mode="after")` leave **zero trace in the generated JSON Schema**,
and Pydantic exposes no introspection API to detect that a model has one. So a
perfect characterisation of the compositional JSON Schema fragment **still does not
settle safety for a Pydantic model** — the model's real constraints can live entirely
outside the schema the analysis sees. The honest scope statement is: *the guarantee is
relative to the JSON Schema, and any validator logic outside it must be re-run after
the splice.* Which, conveniently, is cheap (§8.1 below).

---

# 9. LENSES AND THE VIEW-UPDATE PROBLEM — the right formalism, and where it stops

**Headline, up front, so nobody over-claims from this section:**

> The lens literature gives us (a) the exact vocabulary for our architecture, (b) a
> **named, formalised version of Conjecture 2's compositional fragment** — it is
> called **shuffle-closedness**, Foster et al. 2007 — and (c) forty years of
> negative results about when a view update is ill-defined. It does **not** give us
> splice soundness "for free from the laws": the three lens laws are *vacuously true*
> for a projection-splice at a fixed path, and all the content sits in the **typing**
> judgement, which is exactly the residual question restated. And the lens literature
> is **synthesis-oriented** (you write a lens in a typed combinator language and the
> types compose) while our problem is **analysis-oriented** (given someone else's
> Pydantic schema and a path, compute the view type). That direction mismatch is real
> and is the honest limit of the analogy.

## 9.1 The dictionary

**Foster, Greenwald, Moore, Pierce, Schmitt, "Combinators for Bidirectional Tree
Transformations: A Linguistic Approach to the View-Update Problem", ACM TOPLAS 29(3),
2007** (POPL 2005 extended abstract; PLAN-X 2004 preliminary).  `[PRIMARY — full text
read via pdftotext]`
<https://www.cis.upenn.edu/~bcpierce/papers/lenses-toplas-final.pdf> · doi:10.1145/1232420.1232424

> **Definition 3.1 [Lenses].** "A lens *l* comprises a partial function *l*↗ from V to
> V, called the **get** function of *l*, and a partial function *l*↘ from V × V to V,
> called the **putback** function of *l*."

| our thing | lens thing |
|---|---|
| document D | concrete view *c* ∈ C |
| schema S | the concrete type **C** |
| path/position p | the choice of lens (a projection lens `focus p`) |
| **PROJECT** step, `S@p` | the abstract type **A** |
| reading the old fragment `D@p` | **get**, *l*↗ |
| **SPLICE** step, `D[p := F]` | **putback**, *l*↘(F, D) |
| generated fragment F | modified abstract view *a* ∈ A |
| splice soundness | the **(Put)** typing condition |

## 9.2 Which laws do we actually need? — **none of them.** It is the typing.

This is the part I was asked to be precise about, and the answer contradicts the
coordinator's guess (which was PutGet). Verbatim from Definition 3.2:

> **3.2 Definition [Well-behaved lenses].** "Let *l* be a lens and let C and A be
> subsets of V. We say that *l* is a **well behaved lens from C to A**, written
> *l* ∈ C ⇌ A, if it **maps arguments in C to results in A and vice versa**
>
>   *l*↗(C) ⊆ A   **(Get)**
>   *l*↘(A × C) ⊆ C   **(Put)**
>
> and its get and putback functions obey the following laws:
>
>   *l*↘(*l*↗ c, c) = c for all c ∈ C   **(GetPut)**
>   *l*↗(*l*↘(a, c)) = a for all (a,c) ∈ A × C   **(PutGet)**"

And the optional third:

> "*l*↘(a′, *l*↘(a, c)) = *l*↘(a′, c) for all a, a′ ∈ A and c ∈ C.   **(PutPut)** ...
> We say that a well-behaved lens that also satisfies PutPut is **very well behaved**."

**Now apply this to our splice lens.** Fix a path p and define
`get(D) = D@p`, `put(F, D) = D[p := F]`.

- **(Put) is *exactly* splice soundness**: `put(A × C) ⊆ C` reads "for every fragment
  F ∈ A and every document D ∈ C, `D[p := F]` is again in C." With C = ⟦S⟧ and
  A = ⟦S@p⟧ that is verbatim our Proposition. **It is a typing side-condition, not an
  equation.**
- **GetPut** — `D[p := D@p] = D` — is a **tautology** for an in-place splice. Free.
- **PutGet** — `(D[p := F])@p = F` — is a **tautology** for an in-place splice. Free.
  (It would *not* be free if the projection were lossy or rearranging, e.g. a view
  that renders a sub-object into a flat form. Note that for our purposes.)
- **PutPut** — `D[p := F′][p := F] ... ` i.e. `put(F′, put(F, D)) = put(F′, D)` — also a
  **tautology** for in-place splice at a fixed p. So our lens is even *very* well
  behaved, and this too is free.

> **Verdict on "do the laws give us splice soundness for free": NO.** For the
> trivial projection lens all three equational laws hold vacuously and carry zero
> information. **100% of the content is in the (Put) typing condition, and computing
> the largest A for which (Put) holds *is* the residual problem `S/(D,p)`.** The
> lens framework renames our question precisely and usefully; it does not answer it.

The laws are not useless in general, though — they become load-bearing the moment the
projection is **lossy** (a view that hides fields the model must not touch) or
**rearranging** (a flattened view of a nested record, which is a plausible design for
making the LLM's job easier). In that regime PutGet is exactly the guarantee "the
model's fragment survives the splice unmangled", and GetPut is "an unedited region
comes back bit-identical". **If the design ever includes a non-identity projection —
and for prompting reasons it probably should — the laws stop being free and start
being the specification.** That is a good reason to keep the vocabulary.

## 9.3 Does the typed-lens result subsume CONJECTURE 2?  **Partly — and this is important.**

### The class in Conjecture 2 has a name in this literature: **shuffle-closed**.

Foster et al. hit our exact problem when typing their `map` combinator (map a lens
over every child of a tree), and their solution is a named closure condition. Verbatim:

> "one might naively expect that, if *l* has type C(m) ⇌ A(m) for each name m, then
> `map l` would have type C ⇌ A. **Unfortunately, for arbitrary C and A, the map lens
> is not guaranteed to be well-behaved at this type.** In particular, if doms(C), the
> set of domains of trees in C, is not equal to doms(A), then **the putback function
> can produce a tree that is not in C** ... This shows that the type of map must
> include the requirement that **doms(C) = doms(A)**."

> "A related problem arises when **the sets of trees A and C have dependencies between
> the names of children and the trees that may appear under those names.** ... [their
> example: A allows m under x only when p appears under y; C allows all four
> combinations] ... When we consider just the **projections** of C and A at specific
> names, we obtain the same sets of subtrees ... **But it is clearly not the case that
> `map id ∈ C ⇌ A`.**"

> "To avoid this error ... we require that the source and target sets in the type of
> map be **closed under the 'shuffling' of their children.** ... We say that T is
> **shuffle closed** iff T = T^⇕. ... Alternatively, **every shuffle-closed set T can
> be identified with a set of sets of names D and a function f from names to types,
> such that t ∈ T iff dom(t) ∈ D and t(n) ∈ f(n) for every name n ∈ dom(t).**"

**Read that last sentence again — it is Conjecture 2's fragment, verbatim, in 2007
type-theory clothing.** A shuffle-closed tree type is *exactly* one where validity
factors into (i) a constraint on the key set alone, and (ii) an independent per-name
type. That is the "conjunction of independent, position-indexed constraints" I gave
as the reason the fragment works (§8.2.1). And Foster et al.'s **two counterexamples
are our two breaker families**:
- `doms(C) ≠ doms(A)` is **`required`/`min–maxProperties`/`additionalProperties`** —
  the key-set constraints;
- "dependencies between the names of children and the trees under those names" is
  **`if`/`then`/`else`, `dependentSchemas`, `oneOf`** — the cross-field constraints.

### So the honest verdict:

> ### VERDICT on Conjecture 2, revised: **the CLASS is CONFIRMED BY PRIOR WORK — three independent times. The JSON SCHEMA INSTANCE of it is still unclaimed.**

Prior formulations of the same class, all `[PRIMARY]` and all read by me:
1. **shuffle-closed types** — Foster, Greenwald, Moore, Pierce, Schmitt, TOPLAS 2007
   (typing rule for `map`). Programming-languages framing.
2. **local tree grammars** — Murata, Lee, Mani, Kawaguchi, ACM ToIT 2005, Def. 2.5
   (no competing non-terminals). Formal-language framing. Plus the closure table:
   local/single-type closed under **intersection** but **not** under union or
   difference — i.e. `allOf` keeps you in, `anyOf`/`oneOf`/`not` throw you out.
3. **local DTDs** — Balmin, Papakonstantinou, Vianu, ACM TODS 2004: the subset
   admitting "practically constant time" revalidation "by maintaining only a list of
   counters". Incremental-validation framing.

**We must therefore not claim the concept as novel.** What is genuinely unclaimed, and
what the paper should claim:
- **which JSON Schema keyword sets induce shuffle-closed / local types**, and
- the **operation-sensitivity** (§8.2.2): the fragment is strictly larger for in-place
  replacement than for insert/delete, because `required`, `min/maxItems`,
  `min/maxProperties`, `dependentRequired`, `propertyNames` and
  `additionalProperties` are all *key-set / length* constraints — precisely Foster et
  al.'s `doms(C) = doms(A)` condition — which a replacement cannot disturb;
- the **decision procedure** (walk root→p, reject on a listed keyword) — a practical
  artefact none of the three formulations supplies for JSON Schema;
- `uniqueItems`, which is outside **all three** frameworks, because all three assume
  regular / MSO-definable tree types and Pezoa et al. proved `uniqueItems` is not
  (§5.1).

That is still a paper. It is a smaller and much more defensible paper than "we
discovered compositionality".

## 9.4 Edit lenses and delta lenses — closest match, and what they actually buy

`[PRIMARY for the framing sentence quoted; SECONDHAND for the internals — I read
abstracts/summaries, not the full papers. FLAGGED.]`

- **Hofmann, Pierce, Wagner, "Edit Lenses", POPL 2012**, Philadelphia, Jan 2012;
  ACM SIGPLAN Notices 47(1), doi:10.1145/2103621.2103715;
  <https://repository.upenn.edu/cis_papers/677/>.
  Their move: identify a notion of **"editable structure" — a set of states plus a
  MONOID of edits with a partial monoid action on the states** — and build lenses
  *between such structures*, so that the lens translates **edits to edits** rather
  than states to states. The stated guarantee shape: "when a valid edit happens on one
  document and it is converted through the lens, it should become a **valid edit** on
  the other document."
  **This is the closest formal match to a patch-based design in the whole
  literature.** If the paper keeps JSON Patch as a fallback delta language (§1), edit
  lenses are the right frame: a JSON Patch operation sequence *is* a monoid (free
  monoid on ops, with a partial action on documents — partial exactly because of the
  RFC 6902 preconditions in §1.2), and "valid edit ↦ valid edit" is the property we
  want.
  Follow-ups: **Hofmann, Pierce, Wagner, "Symmetric Lenses", POPL 2011**;
  **"Modular Edit Lenses"** (Hofmann; SSBX lecture notes,
  <https://www.cs.ox.ac.uk/projects/tlcbx/ssbx/hofmann.pdf>); **Hofmann, "Edit
  languages for information trees", ECEASST** — the tree instance, likely the most
  directly reusable.
- **Delta lenses — Diskin, Xiong, Czarnecki** (category-theoretic lenses whose
  arguments are *deltas*/morphisms rather than states). Unifying account:
  **Johnson & Rosebrugh, "Unifying Set-Based, Delta-Based and Edit-Based Lenses"**,
  BX 2016, CEUR-WS Vol-1571 paper 13, <https://ceur-ws.org/Vol-1571/paper_13.pdf> —
  read this one first; it is the map of the territory and will say precisely how
  edit lenses and delta lenses relate.
- **Boomerang** (Bohannon, Foster, Pierce, Pilkiewicz, Schmitt, POPL 2008) — lenses
  over **strings** with regular-language types; **quotient lenses** (Foster, Pilkiewicz,
  Pierce, ICFP 2008); **matching lenses** (Barbosa, Cretin, Foster, Greenberg, Pierce,
  ICFP 2010) — the last is about **alignment**: how to decide which piece of the new
  view corresponds to which piece of the old one. **Alignment is a problem we will
  have** the moment a fragment is a list and the model reorders it, and matching
  lenses are the place it was solved.

**Judgement:** edit lenses/delta lenses are a *good* fit for the fallback patch design
and a *neutral* fit for the localise-project-generate-splice design, because in the
latter our edit is always "replace the subtree at p", the simplest possible edit, and
the machinery for composing and aligning edits is not exercised. **Do not lead with
edit lenses.** Cite them as the formal home of the patch alternative.

## 9.5 The view-update problem — the classical negative results

Foster et al.'s §10 (verbatim, `[PRIMARY]`) is the best short map of this and it ties
the lens laws to the 1980s database results:

> "the set of all **well-behaved lenses is isomorphic to the set of dynamic views** in
> the sense of Gottlob, Paolini, and Zicari [1988]. Moreover, the set of **very well
> behaved lenses is isomorphic to the set of translators under constant complement**
> in the sense of Bancilhon and Spyratos [1981]."

> "Dayal and Bernstein's [1982] seminal theory of 'correct update translation' also
> adopts the more permissive position ... Their notion of '**exactly performing an
> update**' corresponds, intuitively, to our **PutGet** law."

> "**Hegner** [1990; 2004] ... introduces the term **closed view** for the stricter
> constant complement approach and **open view** for the looser approach adopted by
> dynamic views and in the present work."

> "Hegner [2004] also formalizes an additional condition on reasonableness ...
> **monotonicity of update translations**, in the sense that an update that only adds
> records from the view should be translated just into additions to the database."

They also state the three questions the field organises itself around, verbatim:

> "First, **how is a 'reasonable' translation of an update defined?** Second, what
> should we do about the possibility that, **for some update, there may be no
> reasonable way of translating its effect** to the underlying database? And third,
> how do we deal with the possibility that **there are many reasonable translations
> from which we must choose?**"

**Mapping the classical negatives onto which projections we must refuse:**

| classical condition | our version |
|---|---|
| **No translation exists** for some view update | The fragment F is valid for the projected schema but **no** document containing it is valid for S — the residual is empty at that position given D. Our system must **detect and refuse**, i.e. reject the fragment and fall back. |
| **Many translations exist** — the view update is *ambiguous* | Arises the moment the projection is **lossy or rearranging**. For the pure identity projection at a path it does **not** arise: `D[p := F]` is the unique translation. **This is the single biggest reason to keep the projection an identity-on-a-subtree.** |
| **Constant complement** (Bancilhon & Spyratos 1981) — the update must leave a fixed "complement" of the view unchanged | Our version: *the splice must not alter anything outside p*. For an in-place replacement this is automatic. It is exactly what a JSON Patch `replace` guarantees and what a `move` does not. |
| **Views that are inherently updatable** — commercial DBs allow updates only through select/project/restricted-join views | Our version: **only project through `properties`/`items`/`prefixItems`/`$ref`; refuse combinators, `additionalProperties`, `patternProperties`.** The database industry's answer to this problem is *a syntactic whitelist of view shapes*, which is precisely the decision procedure of §8.2.3. That is a strong precedent: **the practical answer to view update has always been "restrict the views", never "solve the general problem".** |
| Hegner's **monotonicity** | The `oneOf` non-monotonicity counterexample in §8.2.2 (making a fragment "better" flips it into two branches and breaks `oneOf`) is a failure of exactly this condition. Worth naming as such. |

Primary sources to cite directly (all `[SECONDHAND]` for me — I have them only through
Foster et al.'s §10, which is a careful and explicit account):
- **Bancilhon & Spyratos, "Update semantics of relational views", ACM TODS 6(4), 1981.**
- **Dayal & Bernstein, "On the correct translation of update operations on relational
  views", ACM TODS 7(3), 1982.**
- **Gottlob, Paolini, Zicari, "Properties and update semantics of consistent views",
  ACM TODS 13(4), 1988.**
- **Hegner, "Foundations of canonical update support for closed database views"
  (ICDT 1990); "An order-based theory of updates for closed database views" (AMAI 2004).**

## 9.6 Where the analogy breaks — say this plainly in the paper

1. **Lenses are written; our schemas are found.** Foster et al. are explicit that
   their approach is *linguistic*: "every expression simultaneously specifies both a
   get function and the corresponding putback", and "each combinator is accompanied by
   a **type declaration**, designed so that the well-behavedness and (for
   non-recursive lenses) totality of composite lens expressions can be verified by
   **straightforward, compositional checks**." That is **type checking of a program
   the programmer wrote**. We have no lens program. We have a Pydantic model someone
   else wrote and a path a router chose, and we must **infer** the view type. **There
   is no inference algorithm in this literature for "given C and a projection, compute
   the largest A".** That is the direction the field never needed and we do.
2. **Our `put` is not the problem; our `a` is.** In lens-land the hard, contested
   object is `put` — how do you push an arbitrary edited view back. In our setting
   `put` is trivially `D[p := F]`. The hard object is **producing `a` at all**: it is
   *sampled from a language model*, not computed. **Nothing in the lens literature
   constrains how the abstract view comes into being.** Lenses assume `a ∈ A` as a
   hypothesis; our entire engineering problem is *enforcing* that hypothesis during
   autoregressive sampling. So the lens framework covers the half of our problem that
   was already easy and is silent on the half that is hard.
3. **Totality vs. partiality.** Foster et al. work hard for **totality** — "the
   putback direction should be capable of putting back **any** possible updated
   version from the abstract set" — and note that "well-behavedness is rather trivial
   in the absence of totality." Our system is allowed to be *partial*: it may detect
   that a fragment cannot be spliced and fall back to whole-document regeneration.
   **That partiality is a resource we have and they did not**, and it is why our
   decision procedure can be conservative.
4. **No probability anywhere.** Lens theory is set-theoretic and deterministic. The
   distributional question — *does constraining the fragment to A distort the
   distribution relative to conditioning the full model on the whole document being
   valid?* — has no counterpart in this literature at all.
5. **Recursion.** Their own caveat, verbatim: "only recursion-free expressions can be
   shown total by completely compositional reasoning with types; for recursive lenses,
   more global arguments are required." Same wall we hit at guarded `$ref` (§8.2.3).

**Net:** cite lenses for the vocabulary, for **shuffle-closedness** (which
demonstrably pre-empts Conjecture 2's class), and for the view-update negative
results. Do **not** present the lens laws as giving splice soundness — they do not,
and a POPL-literate referee will see it immediately.

**PatchOptic (arXiv:2607.05483, July 2026)** — surfaced by another agent as framing
this architecture in optics vocabulary. I did not fetch it (session budget); it should
be read, and it is the right paper to position against. **[NOT READ — flagged.]**

---

## CONJECTURE 3 — bounded cross-batch streaming state

> **Claim under review.** The schemas admitting bounded cross-batch state are exactly
> those whose non-local constraints are **counting** (`minItems`/`maxItems` — a
> counter, O(log m)) or **propositional** (`required`, `if`/`then`/`else`,
> `dependentRequired` — a bit per pending obligation, O(|S|)); and constraints
> requiring **value equality across unboundedly many positions** (`uniqueItems`,
> foreign keys, referential integrity) provably need **Ω(m)** state.

### VERDICT: **CONFIRMED — the trichotomy is right and each of the three parts has a proper theorem behind it. Two corrections: (i) there is a FOURTH memory term the conjecture omits (nesting depth), and Segoufin & Vianu's boundary is drawn along RECURSION, not along constraint kind; (ii) the counting term is O(log m) bits only if the bound is written in binary and is part of the input — for a FIXED schema it is a constant, hence genuinely constant memory.**

### 9.3.1 The upper-bound side — Segoufin & Vianu, exactly  `[PRIMARY, full text read]`

**Segoufin & Vianu, "Validating Streaming XML Documents", PODS 2002, pp. 53–64.**
<https://www.di.ens.fr/~segoufin/Papers/Mypapers/streaming-pods.pdf>

Their memory model is the one we need: a **one-pass, left-to-right, deterministic**
reader with a fixed amount of memory *depending on the schema but not on the document
size*. That is exactly "generate batch k+1 given a bounded summary of batches 1..k".
A DTD is **recognizable** if an fsa can validate it (assuming well-formed input) and
**strongly recognizable** if the fsa also checks well-formedness.

The theorems, verbatim:

> **Theorem 3.1.** "A specialized DTD is **strongly recognizable iff it is
> non-recursive**."
>
> **Theorem 3.2.** "Let T be a set of trees over Σ. The language L(T) is **regular iff
> there exists a non-recursive specialized DTD d such that T = SAT(d)**."
>
> **Theorem 4.2.** "Given a specialized fully recursive DTD d over fixed alphabet Σ,
> it is **decidable in EXPTIME whether d is recognizable**." — and from the
> introduction, "**in polynomial time for DTDs using 1-unambiguous regular
> expressions, as required by XML Schema**."
>
> **Theorem 5.1.** "Let d be a specialized DTD. There exists a **deterministic pda**
> that accepts precisely L(d)" — "using a **stack of depth bounded by the maximum
> number of unmatched open tags** occurring as the input is read from left to right",
> i.e. bounded by the **depth** of the tree, not its size.

Plus, from the introduction, verbatim:

> "the **standard fsa** ... (i) always accepts only documents valid w.r.t. the DTD
> (**but possibly more**), and (ii) accepts precisely the documents valid w.r.t. the
> DTD, whenever the DTD is recognizable. The standard fsa can be constructed in
> **time exponential in the DTD**."
>
> "**for every DTD one can find a specialization of it which is recognizable.**
> Intuitively, this is obtained by **refining the tags of the original DTD to include
> more information useful for quick validation.** This provides a trade-off between
> 'accuracy' of the tags and the ability to perform efficient streaming validation."

And the honest gap they leave, verbatim:

> "The conditions of Lemmas 4.2 and 4.4 are necessary in order for a DTD to be
> recognizable. The conditions of Theorem 4.3 are sufficient ... **The complete
> characterization of recognizable DTDs remains open.**"

### 9.3.2 What that says about the conjecture's three classes

**(a) Counting — `minItems` / `maxItems`. CONFIRMED, with a sharpening.**
A bound written in binary as part of the input needs a counter of **O(log m)** bits =
an automaton with **m+1 states**. But in our setting **the schema is fixed**, so m is
a constant and the counter is **O(1)**. Formally, `{arrays of length between a and b}`
is a *regular* string language for any fixed a,b, so a counting-only schema is
recognizable in Segoufin & Vianu's sense. The one caveat: the *automaton* is linear in
the bound, so a schema with `maxItems: 10000` gives a 10001-state chain. This is the
same blow-up the constrained-decoding engines already hit (llama.cpp's repetition
warning; XGrammar's repetition compression). **So: constant memory, but the constant
is proportional to the numeric bound unless you special-case counters.**

**(b) Propositional — `required`, `if`/`then`/`else`, `dependentRequired`. CONFIRMED.**
Each is a *presence* obligation over the finitely many keys named in S. A subset of
pending obligations is **O(|S|) bits**, i.e. a state space of **2^O(|S|)**. Constant
w.r.t. document size, exponential in the schema. This matches Segoufin & Vianu's own
statement that "the standard fsa can be constructed in **time exponential in the
DTD**" — the exponential is in the schema, exactly as the conjecture supposes.

**(c) Value equality across unboundedly many positions — `uniqueItems`, foreign keys,
referential integrity. CONFIRMED, Ω(m), and there are two independent proofs.**

*Proof 1 — elementary fooling-set / communication argument.* `[MINE, but it is the
textbook argument; safe to print]* Consider `{type:array, uniqueItems:true,
items:{type:string, enum: e_1..e_n}}` and a one-pass validator with memory M. For each
subset A ⊆ {e_1..e_n}, feed the prefix consisting of the elements of A in a fixed
order. If two distinct subsets A ≠ B reached the same memory state, pick
x ∈ A △ B, say x ∈ A \ B: appending x must be **rejected** after A (duplicate) and
**accepted** after B — contradiction. Hence the validator has ≥ 2ⁿ distinguishable
states, i.e. **≥ n bits**, and with m ≤ n elements read, **Ω(m) bits**. The same
argument, with "IDs seen" in place of "values seen", gives Ω(m) for ID/IDREF and for
any foreign-key constraint. This is the streaming lower bound for **element
distinctness**, standardly obtained by reduction from **set disjointness**; see e.g.
the survey literature on streaming lower bounds
(<https://arxiv.org/pdf/2301.05658>, <http://web.cs.ucla.edu/~sherstov/pdf/mfcs-disjointness.pdf>).
`[the streaming/communication background is SECONDHAND; the fooling-set argument above
is self-contained and does not need it]`

*Proof 2 — the tree-language argument, and it is stronger.* Pezoa et al. (WWW 2016)
proved that **JSON Schema "cannot be captured by MSO or tree automata because of the
`uniqueItems` constraints"** (quoted verbatim in §5.2 from the Attouche et al. PVLDB
paper). Segoufin & Vianu's entire framework presupposes **regular** tree languages —
Theorem 3.2 is literally a statement about when L(T) is *regular*. So `uniqueItems`
is not merely expensive within their framework; **it is outside it.** No refinement of
tags, no specialization, no depth-bounded stack recovers it, because the target
language is not regular in the first place.

> **This is the cleanest formal statement available for the paper:** the counting and
> propositional constraints keep you inside the regular tree languages, where
> Segoufin & Vianu's constant-memory / depth-bounded-stack results apply verbatim;
> `uniqueItems` and referential integrity take you *out of* the regular tree
> languages (Pezoa et al.), and the Ω(m) lower bound follows by a two-line
> fooling-set argument.

### 9.3.3 Correction 1 — the missing fourth term: **nesting depth**

Segoufin & Vianu's dividing line is **recursion**, which the conjecture does not
mention at all. Theorem 3.1 says strongly recognizable ⟺ **non-recursive**; Theorem
5.1 says every specialized DTD is validated by a deterministic PDA with **stack depth
bounded by the document's nesting depth**. So the full memory budget for streaming
generation is:

| term | size | source |
|---|---|---|
| nesting stack | **O(depth × log \|S\|)** | Segoufin & Vianu Thm 5.1 |
| propositional obligations | **O(\|S\|)** bits (2^O(\|S\|) states) | folklore; consistent with their exponential fsa construction |
| counters | **O(log m)**, or **O(1)** for a fixed schema | folklore |
| value-equality memory | **Ω(m)** — unavoidable | fooling-set argument; Pezoa et al. non-regularity |

For our workloads this is very good news: **the Excel / bulk-rows case is a shallow,
wide, non-recursive schema**, so depth ≈ 2–3, the schema is fixed, and the first three
terms are all effectively constant. **The bulk-generation case sits precisely inside
the class Segoufin & Vianu prove is constant-memory streamable.** That is a real
theorem to lean on rather than a hand-wave — and it says the *only* thing that forces
unbounded cross-batch state is `uniqueItems` / uniqueness / referential integrity,
exactly as conjectured.

### 9.3.4 Correction 2 — the practical escape hatch is in the same paper

Segoufin & Vianu's **specialization** result — "for every DTD one can find a
specialization of it which is **recognizable** ... by **refining the tags** ... to
include more information useful for quick validation ... a **trade-off** between
'accuracy' of the tags and the ability to perform efficient streaming validation" —
is the formal home for the coordinator's item 9, *"what must the fragment carry?"*.
The answer the theory gives: **carry a refined tag — a small annotation naming the
fragment's contextual type / resolved branch / pending obligations.** It is a proved
trade-off, not free, and citing it lets us say *why* passing a context summary to each
batch is the right move rather than an ad-hoc hack.

**Note the practical exception that saves the uniqueness case anyway:** Ω(m) is a
lower bound on remembering *all* previously emitted values, but in the bulk case
**those values are already on disk** — we are assembling the document, so the "state"
is the document. The bound says you cannot compress it, not that you cannot have it.
The real cost is that the *decoder-side* constraint for batch k+1 must be rebuilt from
the k·b values already emitted — a trie / Aho–Corasick automaton of size proportional
to their total length. Linear, rebuildable incrementally, entirely practical at the
scale of a spreadsheet. **The theory forbids a bounded summary; it does not forbid
the obvious implementation.**

### 9.3.5 Successors to check before final write-up  `[NOT READ — flagged]`
- **Segoufin & Sirangelo, "Constant-Memory Validation of Streaming XML Documents
  Against DTDs", ICDT 2007, LNCS 4353**,
  <https://link.springer.com/chapter/10.1007/11965893_21> — closes part of the
  characterisation Segoufin & Vianu left open.
- **"Stackless Processing of Streamed Trees", PODS 2021**,
  <https://dl.acm.org/doi/abs/10.1145/3452021.3458320>.
- **Streaming JSON Schema validation: I found no academic work at all.** No
  characterisation of which JSON Schemas admit bounded-memory streaming validation
  exists. **This is the direct JSON analogue of Segoufin & Vianu (2002) and it is
  missing.** In my judgement it is the most tractable publishable gap on this list —
  the proof techniques transfer, and the bulk-generation use case supplies the
  motivation the XML paper had to argue for.

---

## CONJECTURE 1 — the hardness of prefix-feasibility

> **Claim under review.** Separate (Q1) MEMBERSHIP — given a complete value v, is
> `D[p:=v] ⊨ S`? — from (Q2) PREFIX-FEASIBILITY — given a partial text w, does some
> completion u make `parse(wu)` land in the residual? Q1 is cheap; Q2 is as hard as
> JSON Schema satisfiability with part of the value fixed, hence intractable in
> general, hence **no polynomial exact token mask exists for full JSON Schema**.

### VERDICT: **CONFIRMED, and it can be stated much more sharply than "as hard as". Q2 with the empty prefix IS JSON Schema satisfiability — not a reduction, an identity. So Q2 inherits the exact bounds of the EDBT-2025 table. The negation-free sub-question is NOT settled by the literature; I give an easy NP-hardness lower bound and flag the exact class as OPEN.**

### 9.1.1 Q1 is cheap — precisely how cheap

| setting | bound | source |
|---|---|---|
| full revalidation, Classical JSON Schema | **PTIME-complete** (combined); running time O(\|S\|²·\|J\|) | Pezoa et al. WWW 2016; Bourhis et al. PODS 2017; table in EDBT 2025 tutorial `[PRIMARY]` |
| full revalidation, Modern JSON Schema, **fixed schema** | **in P** (data complexity) | Attouche et al. 2024, verbatim `[PRIMARY]` |
| full revalidation, Modern JSON Schema, schema varying | **PSPACE-complete** | Attouche et al. 2024 `[PRIMARY]` |
| **incremental** revalidation after m local updates, XML DTD / XML Schema | **O(m log n)** time, O(n) auxiliary structure | Balmin, Papakonstantinou, Vianu, TODS 2004 `[PRIMARY-ish]` |
| **incremental**, specialized DTDs | **O(m log² n)**, O(n) auxiliary | same |
| **incremental**, **local** DTDs | "practically constant time … maintaining only a list of counters" | same |
| incremental with subtree insert/delete **and ID/IDREF** | **n log n** worst case, linear space | Barbosa et al. ICDE 2004 `[SECONDHAND]` |
| JSON equivalent of any incremental result | **does not exist** | my searches, §4.3 |

So Q1 is confirmed cheap, and *cheaper incrementally* is confirmed **for XML only**.
The JSON incremental result is a hole someone should fill; until then the honest
number for a JSON implementation is "full revalidation, PTIME-complete, O(|S|·|J|)".

### 9.1.2 Q2 — the identity, not a reduction  `[MINE — check the argument, it is short]`

Take any schema S′ whose satisfiability you want to decide. Set
`S = {type: "object", properties: {v: S′}}`, `D = {"v": <any value>}` if one exists —
or more simply take `p = ""` (the document root) and `S = S′`, `D` arbitrary. Then

  `S/(D, "") = { v : v ⊨ S′ }`

and **Q2 asked at the empty prefix** — "does some completion u make `parse(u)` land in
the residual?" — is literally

  **"does there exist a value v with v ⊨ S′?"  =  JSON Schema satisfiability of S′.**

So Q2 ⊇ satisfiability as a *special case*, with no encoding overhead at all. And the
converse direction holds too: for a non-empty prefix w, the already-fixed part of the
value is expressible in JSON Schema itself (`const` on the completed sub-values,
`properties`+`required` for the object keys already opened, `prefixItems` for array
positions already filled), so Q2(w) is satisfiability of a schema of size
|S′| + O(|w|). **Therefore Q2 and JSON Schema satisfiability are equivalent up to
linear-size reductions in both directions.** Hence, by the EDBT-2025 table (§5.4):

| schema features (Classical JSON Schema) | complexity of **Q2 / prefix-feasibility** |
|---|---|
| no recursion, no `uniqueItems` | **PSPACE-complete** |
| no recursion, with `uniqueItems` | **PSPACE-hard, in EXPSPACE** |
| recursion, no `uniqueItems` | **EXPTIME-complete** |
| recursion, with `uniqueItems` | **EXPTIME-hard, in 2EXPTIME** |

Note the row that matters most: **a flat Pydantic form is non-recursive, so the exact
bound for the motivating use case is PSPACE-complete, not EXPTIME.** Say PSPACE, not
EXPTIME, when talking about forms; say EXPTIME when the model is recursive.

> **Consequence, stated as the theorem the paper should carry:**
> **The Q1/Q2 gap is PTIME-complete vs PSPACE-complete (non-recursive) / EXPTIME-complete
> (recursive).** An *exact* (sound **and** complete) token mask must decide Q2 at every
> step; a *generate-then-validate* loop only ever decides Q1. **That gap is the formal
> reason "generate then validate" beats "constrain during decoding" for the general
> case, and it is a provable separation unless P = PSPACE.**

Three caveats that must ship with the theorem or a referee will (rightly) object:
1. **The hardness is in the schema, not the document.** These are combined/schema
   complexities. Compile once per schema and the exponential is amortised — which is
   exactly what Attouche et al.'s experiments show empirically: their EXPTIME
   satisfiability algorithm "behaves quite well even on schemas with tens of thousands
   of nodes" over 6,427 real GitHub schemas `[PRIMARY]`. **Do not present the bound as
   "this is impossible"; present it as "no polynomial-in-schema exact masker exists,
   and precompilation is the only route."**
2. **Soundness is cheap; completeness is what costs.** A mask that never *permits* an
   invalid continuation but sometimes *forbids* a valid one is polynomial (just use the
   syntactic projection and check local constraints). Every existing constrained-decoding
   engine already lives here. **The hardness is entirely about completeness.**
3. **Nothing here is specific to deltas.** Q2 for *whole-document* generation against a
   full JSON Schema is the same problem with `p = ""`. So this theorem does **not**
   distinguish our architecture from ordinary structured output — it explains why
   *neither* has an exact masker. That is an important honesty point: **the delta
   setting does not make prefix-feasibility harder; it makes it the same.** What the
   delta setting changes is the *size* of the thing you must re-emit on failure, which
   is an argument about retry cost, not about decidability.

### 9.1.3 The negation-free fragment — asked for separately, and NOT settled by the literature

The EDBT-2025 table splits by **recursion** and by **`uniqueItems`**, not by
negation. I could not find a published complexity for satisfiability of the
negation-free fragment of JSON Schema. What I can say:

- **Lower bound: NP-hard, by an easy reduction, and `not` is not needed.** `[MINE]`
  Encode 3-SAT. Variables become required boolean properties
  (`required:[x₁..xₙ]`, each `{"enum":[true,false]}`). A clause `(x₁ ∨ ¬x₂ ∨ x₃)`
  becomes
  `{"anyOf":[{"properties":{"x1":{"const":true}}},{"properties":{"x2":{"const":false}}},{"properties":{"x3":{"const":true}}}]}`.
  The formula is the `allOf` of its clauses. **No `not` keyword appears** — negative
  literals are expressed with `const:false`. The schema is satisfiable iff the formula
  is. So **the flat, non-recursive, negation-free fragment is already NP-hard**, and
  the hope that "real schemas avoid `not`, so this is easy" is false.
- **Upper bound: not obviously NP.** A witness can be forced to be exponentially large
  by numeric bounds written in binary (`minItems: 1000000`), so membership in NP needs
  either unary bounds or a succinct-witness argument. With numeric bounds bounded by a
  constant, NP membership is plausible. **I did not find this stated anywhere.**
- **Negation is eliminable anyway.** Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger,
  **"Not Elimination and Witness Generation for JSON Schema"** (arXiv:2104.14828, 2021)
  `[SECONDHAND — abstract only]` give an algorithm for **not-elimination** over JSON
  Schema, showing that operator pairs like `patternProperties`/`required` and
  `items`/`contains` are "almost dual under negation" (quoted from the PVLDB paper's
  own-prior-work paragraph, `[PRIMARY]`). If `not` can be eliminated, the negation-free
  fragment is **expressively complete for the whole language**, and the only thing
  restricting `not` buys is a change of *input size* — i.e. the fragment can only be
  easier by however much the elimination blows up. **That strongly suggests the
  negation-free fragment is not meaningfully easier, but I have not verified the
  blow-up factor.**

> **Sub-verdict: the exact complexity of satisfiability (hence Q2) for negation-free
> JSON Schema is OPEN as far as I can find. Lower bound NP-hard (easy, mine); no
> published matching upper bound; the not-elimination result suggests the gap to the
> general case is a size blow-up, not a class change.** If the paper wants one small,
> self-contained theorem of its own, **this is the best candidate on the list** —
> and the NP-hardness reduction above is three lines and needs no new machinery.

---

# 10. SCHEMA PROJECTION as a formal operator

## 10.1 The XML projection line, and the one paper that is our architecture exactly

**Marian & Siméon, "Projecting XML Documents", VLDB 2003, pp. 213–224**
`[SECONDHAND — abstract/summary only]`
<https://people.cs.rutgers.edu/~amelie/papers/2003/xmlprojection.pdf>
The founding paper. Given a query q over a document t, evaluate q on a *pruned* t′
instead. Mechanism: **path analysis** — infer the set of paths a query needs, prune
everything else at load time. Purely path-based; no schema.

**Benzaken, Castagna, Colazzo, Nguyen, "Type-Based XML Projection", VLDB 2006**
`[SECONDHAND]` (extended: "Optimizing XML querying using type-based document
projection", <https://arxiv.org/pdf/1104.2079>).
Adds the schema: assume documents are typed by a DTD, combine path extraction with
**type inference** to determine the **type names** of elements the query needs. That
set is called a **type-projector** and is used to prune at load time. This is the
operator we need in spirit: *"which parts of the schema does this position depend
on"*, computed by type inference rather than by syntax.

**Baazizi, Bidoit, Colazzo, Malla, Sahakyan, "Projection for XML Update
Optimization", EDBT 2011**  `[PRIMARY — full text read via pdftotext]`
<http://openproceedings.org/2011/conf/edbt/BaaziziBCMS11.pdf> · doi:10.1145/1951365.1951403

**This paper is our architecture, built and proved, in 2011, for XML.** Verbatim:

> "Our update scenario is designed as follows for an update u and a document t typed
> by a dtd D. **First, the projection t′ of t is built using a type-projector π.
> Second, the update u is performed over the projection t′, yielding the partial
> result u(t′).** ... The last step, called **Merge**, parses in a streaming and
> synchronized fashion both the original document t and u(t′) in order to produce the
> final result u(t)."

Their correctness theorem, verbatim:

> **Theorem 5.3.** "Let u be an update over D and π be the inferred type projector for
> u. Then for each p-tree t ⊨ D, we have: **Merge(t | u(π(t))) ≡ u(t)**."
>
> **Theorem 5.4 (Soundness of update type projector).** "u(π(t)) ≡_J (u(t)) where
> J = dom(u(t)) − [dom(t) − K(t,π)]."

And the resource bound, verbatim:

> "The **Merge** algorithm uses a **buffer whose size is upper bounded by the maximal
> depth of the input document t**."

— which is exactly Segoufin & Vianu's depth-bounded stack again (§7.1, Thm 5.1).
Three independent papers land on "depth, not size" as the memory bound for
streaming tree work. That is a robust fact worth stating once and reusing.

### The sentence that matters most to us, verbatim:

> **"It should be noted that the revalidation issue is not considered in this paper."**

**So: the XML community built localise → project → operate-on-projection → merge,
proved it computes the right answer, bounded its memory by document depth — and
explicitly declined to say anything about whether the result is still schema-valid.**
That is the third standards-or-literature source (after RFC 5261 §1.4 and Benedikt &
Cheney's observation about the W3C's unsound `transform` rules) to reach this exact
boundary and stop. It is strong, citable evidence that **schema-preservation under
projection-and-merge is a real, recognised, unclosed gap — not something we failed to
find.**

Their notion of soundness (Theorem 5.3) is *result-equivalence*: the pipeline computes
what the naive whole-document update would compute. **Ours is a different and
additional property**: the pipeline yields a *schema-valid* result. Those two are
orthogonal, and only the first has been proved. That distinction should be made
explicitly in the paper — it is a clean statement of what is new.

## 10.2 Is `S@p` well-defined for JSON Schema? — the answer, consolidated

(Detailed argument is in §5.5; here is the verdict.)

**No, not as a total function `Schema → Schema`.** The correct type of the operator is

> `proj : Schema × Document × Pointer ⇀ Schema` — **partial**, and **relativised to D**.

- **Total and syntactic** when the root→p path passes only `properties`, `items`,
  `prefixItems`, and guarded `$ref`. Pydantic gives this for the common case: a nested
  `BaseModel` field is `S["$defs"][ModelName]`, a stand-alone schema any constrained
  decoder accepts today.
- **Partial** — undefined — at `additionalProperties`, multiple matching
  `patternProperties`, and any combinator above p.
- **Requires D** at `if`/`then`/`else` and `dependentSchemas`, where fixing D lets you
  *evaluate* the antecedent instead of carrying it symbolically. **This is the single
  most useful practical observation in the whole projection story**: because we have
  the concrete document, every condition that reads only parts of D *outside* p
  collapses to a constant, and the projection becomes a plain schema again. Only
  conditions that read *inside* p stay symbolic.
- **Not recoverable at all** for `uniqueItems` and cross-references: no schema at p can
  express a constraint about p's siblings' values.
- `$ref` **guardedness**, not non-recursion, is the right side-condition (§8.2.3).
- **`$dynamicRef` must be banned**: its resolution depends on the dynamic scope, not
  the syntactic position, so `proj` is not even definable. This costs nothing —
  Pydantic emits Classical JSON Schema.

**Nobody has defined this operator for JSON Schema.** The type-based projection line
(Benzaken et al. 2006; Baazizi et al. 2011) defines the analogous operator for DTDs
via type inference, and that is the technique to port. It is a well-scoped piece of
work.

---

# 11. XQuery Update static typing — what they proved, where they gave up

Consolidating §3 with what I could reach afterwards.

**What was proved.**
- **Cheney, Flux / LUX** (PLAN-X 2007; ICFP 2008; extended report arXiv:0807.1211)
  `[PRIMARY]`. **Theorem 3 (Update soundness):** `Γ ⊢ᵃ {τ} s {τ′}`, `v ∈ ⟦τ⟧`,
  `γ ∈ ⟦Γ⟧`, `γ;v ⊢ s ⇒ᵁ v′` implies `v′ ∈ ⟦τ′⟧`. **A well-typed update maps a
  document of the input type to a document of the output type, decided statically.**
  This is the theorem we want, for XML, since 2007.
- The price: **child axis only**, no node identity, no pattern matching, no absolute
  paths, no side effects in queries. Cheney's own words: Flux "sacrifices
  expressiveness for semantic clarity and the ability to typecheck."
- The type machinery: **regular expression types with structural subtyping,
  XDuce-style**; subtyping is **EXPTIME-complete in general** though "well-behaved in
  practice". Related: **Cheney, "Regular Expression Subtyping for XML Query and Update
  Languages", ESOP 2008**, arXiv:0801.0714 `[NOT READ — flagged]`, which is the
  subtyping algorithm the whole thing rests on.
- **Benedikt & Cheney, "Semantics, Types and Effects for XML Updates", DBPL 2009,
  LNCS 5708** `[SECONDHAND — Springer paywalled; the author's TR link
  <http://homepages.inf.ed.ac.uk/jcheney/drafts/w3c-update-types-tr.pdf> now 404s]`.
  Contributions as reported: a core language + semantics for **W3C-style** updates
  (not Cheney's own restricted language), an **effect analysis**, and **schema
  alteration** — "synthesizing an output schema describing the result of an update
  applied to a given input schema" — "which can be used as the basis for **sound**
  typechecking for queries involving `transform`."
  **And the finding that should be quoted in our paper:** at the time the W3C had
  released **XQuery Update Facility 1.0** as a Candidate Recommendation, and
  **"the typing rules in the W3C proposal appeared unsound for `transform` queries"**
  — i.e. *the standards body's own static type rules for tree updates were wrong.*

**Where they gave up.**
1. **On expressiveness.** Nobody typechecks full XQuery Update Facility. Flux
   typechecks a restricted language; Benedikt & Cheney give a *sound* (not complete)
   analysis for a core of the W3C language.
2. **On completeness.** Every result in this line is sound-but-conservative. I found
   no sound-and-complete static schema-preservation checker for any tree update
   language. Consistent with the complexity picture: the exact problem is
   satisfiability-flavoured, and satisfiability is EXPTIME-complete for the analogous
   JSON fragment (§5.4).
3. **On recursion.** Cheney: "only recursion-free expressions can be shown total by
   completely compositional reasoning with types; for recursive lenses[/updates], more
   global arguments are required."
4. **On carrying it to JSON.** Nobody did. The JSON Schema statics community
   (2016–2025) has never published on updates.

**Other work in the same neighbourhood** `[SECONDHAND]`:
- **Bidoit-Tollu, Colazzo, Ulliana, "Type-Based Detection of XML Query-Update
  Independence"** (arXiv:1205.6698) — decides from types whether a query is unaffected
  by an update. The *dual* of our problem and the right formalism for the LOCALISE step
  ("which parts of D can I leave alone?").
- **"Rewrite-based verification of XML updates"**, PPDP 2010, doi:10.1145/1836089.1836105.
- **"Automata-based Static Analysis of XML Document Adaptation"**, arXiv:1210.2453 —
  automata-theoretic check that a *sequence* of adaptations maps every document of S₁
  into S₂. Closest thing to "verify a patch script preserves a schema."

---

# 12. WHAT THIS MEANS FOR THE DELTA PROBLEM — my judgement

**Clearly labelled as judgement.** Facts are above; this is what I think they add up to.

### 12.1 Is it (a) already solved, (b) not worth solving, or (c) genuinely open?

**(c), but a narrower (c) than the brief assumed, and the honest version of the paper
must give a lot of ground to prior work.**

- The **architecture** — localise, project, generate on the projection, splice, merge —
  is not new. Baazizi et al. (EDBT 2011) built it for XML and proved it computes the
  right answer with depth-bounded memory. **Cite them; do not re-derive.**
- The **compositional class** is not new. It is **shuffle-closedness** (Foster et al.,
  TOPLAS 2007) = **local tree grammars** (Murata et al., ToIT 2005) = **local DTDs**
  (Balmin et al., TODS 2004). Three independent 2004–2007 formulations. **Conjecture 2's
  concept is confirmed by prior work; only its JSON Schema instance is unclaimed.**
- The **static type-checking of tree edits** is not new either: Cheney's Flux proves
  exactly the soundness theorem we want, for a restricted XML update language, in 2007.
- What is **genuinely missing**, everywhere I looked:
  1. **Any of this for JSON Schema.** Not the local fragment, not incremental
     validation, not streaming validation, not update typing, not schema projection.
     The JSON Schema statics literature is complete on *whole-document* questions
     (validation, satisfiability, inclusion, equivalence, witness generation) and
     **empty on updates and locality**.
  2. **`uniqueItems`.** It is outside every framework the XML people built — not
     regular, not MSO-definable (Pezoa et al. 2016), excluded by the state-of-the-art
     witness generator (Attouche et al. 2022), and it forces Ω(m) streaming state.
     It is the single operator that makes JSON genuinely harder than XML here.
  3. **The probabilistic half.** Nothing in any of this literature says anything about
     a *sampled* fragment. Lenses, transducers, incremental validation all assume the
     new value is given.

### 12.2 The five things I would actually claim in the paper

1. **The Q1/Q2 separation, with exact bounds.** Membership (revalidate a spliced
   document) is **PTIME-complete**; prefix-feasibility (what an exact token mask must
   decide) **is** JSON Schema satisfiability, hence **PSPACE-complete for non-recursive
   schemas without `uniqueItems`** and **EXPTIME-complete for recursive ones**
   (Bourhis et al. 2017, via the EDBT-2025 table). **This is the formal reason to
   prefer generate-then-validate over exact decode-time constraint.** It is a clean,
   citable, correct separation and it is the paper's strongest theorem-shaped claim.
   Caveat it properly: the hardness is in the *schema*, so precompilation amortises it,
   and it applies equally to whole-document structured output — the delta setting does
   not make it worse.
2. **The local fragment of JSON Schema**, defined as the JSON instance of
   shuffle-closedness/local tree grammars, **plus the operation-sensitivity nobody has
   noted**: the safe fragment is strictly larger for in-place replacement (where
   `required`, `min/maxItems`, `dependentRequired`, `propertyNames`,
   `additionalProperties` are all harmless) than for insert/delete. Ship the O(|p|)
   root-to-p decision procedure (§8.2.3) as the practical artefact.
3. **A statement of the projection operator's real type** —
   `proj : Schema × Document × Pointer ⇀ Schema`, partial and D-relativised — with the
   observation that **fixing D collapses `if`/`then`/`else` and `dependentSchemas`
   whose antecedents live outside p**. That is the move that makes the operator usable
   in practice, and it is available only because we have the concrete document, which
   the schema-only literature did not.
4. **The bulk/streaming case sits inside a proved-safe class.** Segoufin & Vianu
   Theorem 3.1/3.2: constant-memory one-pass validation is possible **iff** the schema
   is non-recursive; Theorem 5.1: depth-bounded stack otherwise. Flat Excel-style
   schemas are non-recursive and shallow. So the cross-batch state is bounded, and the
   *only* thing that breaks it is value-equality across batches (`uniqueItems`,
   foreign keys), for which there is a two-line Ω(m) fooling-set lower bound. **A real
   theorem where the brief expected a hand-wave.**
5. **The negative survey result.** Three standards and literatures reached exactly our
   boundary and stopped: **RFC 5261** delegates schema validity of a patched XML
   document to the caller; **W3C XQuery Update Facility 1.0**'s own typing rules were
   found unsound for `transform` (Benedikt & Cheney 2009); **Baazizi et al. 2011**
   built projection-update-merge and wrote "the revalidation issue is not considered
   in this paper". That is a documented gap, not an absence of searching.

### 12.3 Design recommendations that fall out of the theory

- **Make the projection the identity on a subtree.** The moment it is lossy or
  rearranging, you inherit the view-update ambiguity problem (many valid translations),
  and PutGet/GetPut stop being free. Identity projection ⇒ unique translation.
- **Restrict to Classical JSON Schema. Ban `$dynamicRef`.** It moves *validation* from
  PTIME-complete to PSPACE-complete (Attouche et al. 2024) and makes `proj` undefinable.
  Costs nothing: Pydantic emits Classical.
- **Prefer in-place replacement over insert/delete** wherever the product allows. The
  safe schema fragment is materially larger, for a provable reason.
- **Use JSON Merge Patch (RFC 7396) as the fallback delta language, not JSON Patch,
  wherever arrays are not being restructured.** Its grammar is derivable from S alone
  by a local rewrite (all-optional + nullable), needs no document-derived trie, and is
  order-free. Its two fatal limits are documented and testable: no `null` values, no
  array-internal edits. Reach for RFC 6902 only when you need array surgery, and then
  accept that the constraint engine must simulate document state across ops.
- **Do the cheap thing: splice, then revalidate, then roll back.** Validation is
  PTIME-complete, RFC 6902 mandates atomicity, and there is no incremental JSON
  validator to be cleverer with. Decode-time constraint is an optimisation on *retry
  cost*, and should be argued for on those grounds, not on feasibility.
- **Pass each fragment a refined context tag.** Segoufin & Vianu's specialization
  result says every schema has a tag-refinement that becomes streamable, at the cost
  of tag "accuracy". That is the principled version of "tell the model which branch
  it's in".
- **Remember Pydantic's blind spot.** `@model_validator(mode="after")` constraints
  leave **no trace in the generated JSON Schema**, and Pydantic offers no introspection
  to detect them. So the compositionality guarantee is *relative to the JSON Schema*,
  and any Python-level validator must be re-run after the splice. State this as a scope
  limitation, not a footnote — it is the difference between "provably safe" and
  "provably safe with respect to the schema we can see."

### 12.4 What I did NOT reach — for whoever picks this up

- **PatchOptic (arXiv:2607.05483)** — not fetched. Should be read and positioned against.
- **Bourhis et al. PODS 2017 primary text** — I have their bounds only as quoted
  verbatim inside Attouche et al. (PVLDB 2022) and the EDBT 2025 tutorial table. Pull
  the PODS PDF before printing the EXPTIME/2EXPTIME statements.
- **Pezoa et al. WWW 2016 primary text** — all my links 301'd to broken URLs or 404'd.
  Same caveat: the `O(|S|²·|J|)` figure and the MSO/tree-automata claim are quoted
  secondhand (though from the same research group).
- **Barbosa et al. ICDE 2004 primary text** — PDF would not extract. The `n log n` /
  linear-space and ID/IDREF claims are secondhand.
- **Benedikt & Cheney DBPL 2009 primary text** — paywalled; author TR link is dead.
- **Milo/Suciu/Vianu and the tree-transducer complexity** — the `(k+2)`-fold
  exponential and non-elementary claims are secondhand; both PDFs I pulled had broken
  font encoding.
- **Segoufin & Sirangelo ICDT 2007**, the successor that closes part of the streaming
  characterisation — not read.
- **Johnson & Rosebrugh, "Unifying Set-Based, Delta-Based and Edit-Based Lenses"**
  (CEUR-WS Vol-1571 paper 13) — not read; it is the right map of the lens territory
  and would settle how edit lenses and delta lenses relate.
- **Complexity of satisfiability for negation-free JSON Schema** — I could not find it
  published. My NP-hardness reduction (§9.1.3) is easy and, I believe, correct; the
  upper bound is open.

---

# 13. SOURCES CONSULTED

`[PRIMARY]` = I read the actual text (fetched HTML, or PDF extracted locally with
`pdftotext` and read the sentences myself). `[SECONDHAND]` = abstract, citation, or
another paper's verbatim quotation only. `[NOT READ]` = identified but not obtained.

## Standards and drafts
| ref | status |
|---|---|
| RFC 6901 — JSON Pointer. Bryan (ed.), Zyp, Nottingham (ed.), Apr 2013. <https://www.rfc-editor.org/rfc/rfc6901.txt> | `[PRIMARY]` |
| RFC 6902 — JSON Patch. Bryan, Nottingham, Apr 2013. <https://www.rfc-editor.org/rfc/rfc6902.txt> | `[PRIMARY]` |
| RFC 7386 → **obsoleted by RFC 7396** — JSON Merge Patch. Hoffman, Snell, Oct 2014. <https://www.rfc-editor.org/rfc/rfc7386.txt>, <https://datatracker.ietf.org/doc/rfc7386/> | `[PRIMARY]` |
| RFC 5261 — An Extensible Markup Language (XML) Patch Operations Framework. Urpalainen, Sep 2008. <https://www.rfc-editor.org/rfc/rfc5261.txt> | `[PRIMARY]` |
| draft-snell-json-test-07 — JSON Predicate. Snell, Sep 2013, **expired Mar 2014, never an RFC**. <https://datatracker.ietf.org/doc/html/draft-snell-json-test-07> | `[PRIMARY]` |
| RFC 5789 — HTTP PATCH (atomicity, referenced by 6902) | `[SECONDHAND]` |

## JSON Schema theory
| ref | status |
|---|---|
| Baazizi, Colazzo, Ghelli, Sartiani, **"Everything You Always Wanted to Know About JSON Schema (But Were Afraid to Ask)"**, EDBT 2025 tutorial. <https://openproceedings.org/2025/conf/edbt/paper-T3.pdf> — **the authoritative complexity table (Table 1)** | `[PRIMARY]` |
| Attouche, Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, **"Witness Generation for JSON Schema"**, PVLDB 15(13):4002–4014, 2022. doi:10.14778/3565838.3565852 · arXiv:2202.12849 · <https://www.vldb.org/pvldb/vol15/p4002-sartiani.pdf> | `[PRIMARY]` |
| Attouche, Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, **"Validation of Modern JSON Schema: Formalization and Complexity"**, PACMPL 2024, doi:10.1145/3632891 · arXiv:2307.10034v2 | `[PRIMARY]` |
| Bourhis, Reutter, Suárez, Vrgoč, **"JSON: data model, query languages and schema specification"**, PODS 2017:123–135 · arXiv:1701.02221 | `[SECONDHAND]` — bounds via verbatim quotation in the two above |
| Pezoa, Reutter, Suárez, Ugarte, Vrgoč, **"Foundations of JSON Schema"**, WWW 2016:263–273, doi:10.1145/2872427.2883029 | `[SECONDHAND]` — all author-PDF links 301'd broken or 404'd |
| Baazizi, Colazzo, Ghelli, Sartiani, Scherzinger, **"Not Elimination and Witness Generation for JSON Schema"**, arXiv:2104.14828, 2021 | `[SECONDHAND]` |
| Attouche et al., **"Witness Generation for Classical JSON Schema"**, ACM TODS, doi:10.1145/3799416 | `[NOT READ]` |
| Habib, Shinnar, Hirzel, Pradel — JSON subschema / containment checking; "Type Safety with JSON Subschema", arXiv:1911.12651 | `[SECONDHAND]` |
| **Blaze: Compiling JSON Schema for 10x Faster Validation**, PVLDB, doi:10.14778/3773749.3773764 | `[SECONDHAND]` — compilation, not incrementality |

## XML: incremental validation, streaming, updates, projection
| ref | status |
|---|---|
| Segoufin & Vianu, **"Validating Streaming XML Documents"**, PODS 2002:53–64. <https://www.di.ens.fr/~segoufin/Papers/Mypapers/streaming-pods.pdf> | `[PRIMARY]` |
| Balmin, Papakonstantinou, Vianu, **"Incremental validation of XML documents"**, ACM TODS 29(4):710–751, 2004, doi:10.1145/1042046.1042050 | `[PRIMARY-ish]` — abstract + bounds from the IBM Research record; ACM DL 403s |
| Barbosa, Mendelzon, Libkin, Mignet, Arenas, **"Efficient Incremental Validation of XML Documents"**, ICDE 2004:671–682 | `[SECONDHAND]` — PDF would not extract |
| **"Efficient Incremental Validation of XML Documents After Composite Updates"**, XSym 2006, LNCS | `[NOT READ]` |
| Segoufin & Sirangelo, **"Constant-Memory Validation of Streaming XML Documents Against DTDs"**, ICDT 2007, LNCS 4353 | `[NOT READ]` |
| **"Stackless Processing of Streamed Trees"**, PODS 2021, doi:10.1145/3452021.3458320 | `[NOT READ]` |
| Murata, Lee, Mani, Kawaguchi, **"Taxonomy of XML Schema Languages using Formal Language Theory"**, ACM ToIT 5(4), 2005, doi:10.1145/1111627.1111631. <https://pike.psu.edu/publications/toit05.pdf> | `[PRIMARY]` |
| Cheney, **"Flux: FunctionaL Updates for XML (extended report)"**, arXiv:0807.1211 (ICFP 2008; PLAN-X 2007 as "LUX") | `[PRIMARY]` — read via ar5iv HTML |
| Cheney, **"Regular Expression Subtyping for XML Query and Update Languages"**, ESOP 2008, arXiv:0801.0714 | `[NOT READ]` |
| Benedikt & Cheney, **"Semantics, Types and Effects for XML Updates"**, DBPL 2009, LNCS 5708, doi:10.1007/978-3-642-03793-1_1 | `[SECONDHAND]` — paywalled; author TR link 404s |
| Bidoit-Tollu, Colazzo, Ulliana, **"Type-Based Detection of XML Query-Update Independence"**, arXiv:1205.6698 | `[SECONDHAND]` |
| **"Rewrite-based verification of XML updates"**, PPDP 2010, doi:10.1145/1836089.1836105 | `[SECONDHAND]` |
| **"Automata-based Static Analysis of XML Document Adaptation"**, arXiv:1210.2453 (+ ER 2012 version) | `[SECONDHAND]` |
| Marian & Siméon, **"Projecting XML Documents"**, VLDB 2003:213–224. <https://people.cs.rutgers.edu/~amelie/papers/2003/xmlprojection.pdf> | `[SECONDHAND]` |
| Benzaken, Castagna, Colazzo, Nguyen, **"Type-Based XML Projection"**, VLDB 2006; extended arXiv:1104.2079 | `[SECONDHAND]` |
| Baazizi, Bidoit, Colazzo, Malla, Sahakyan, **"Projection for XML Update Optimization"**, EDBT 2011, doi:10.1145/1951365.1951403. <http://openproceedings.org/2011/conf/edbt/BaaziziBCMS11.pdf> | `[PRIMARY]` |

## Tree transducers / typechecking
| ref | status |
|---|---|
| Milo, Suciu, Vianu, **"Typechecking for XML transformers"**, PODS 2000:11–22; JCSS 66(1), 2003 | `[SECONDHAND]` — ScienceDirect 403 |
| Frisch & Hosoya, **"Towards Practical Typechecking for Macro Tree Transducers"**, arXiv:cs/0701176 (INRIA RR) | `[SECONDHAND]` — PDF had broken font encoding |
| Martens & Neven, **"Typechecking Top-Down Uniform Unranked Tree Transducers"**, ICDT 2003, LNCS 2572; **"On the complexity of typechecking top-down XML transformations"**, TCS 336(1):153–180, 2005 | `[SECONDHAND]` |
| **"The time complexity of typechecking tree-walking tree transducers"**, Acta Informatica, doi:10.1007/s00236-008-0087-y | `[SECONDHAND]` — Springer auth redirect |
| **"Two or three things I know about tree transducers"**, arXiv:2409.03169 | `[NOT READ]` — broken font encoding |

## Lenses / bidirectional transformations / view update
| ref | status |
|---|---|
| Foster, Greenwald, Moore, Pierce, Schmitt, **"Combinators for Bidirectional Tree Transformations: A Linguistic Approach to the View-Update Problem"**, ACM TOPLAS 29(3), 2007 (POPL 2005). <https://www.cis.upenn.edu/~bcpierce/papers/lenses-toplas-final.pdf> · doi:10.1145/1232420.1232424 | `[PRIMARY]` — laws, `map` typing, **shuffle-closedness**, and §10's view-update survey all read directly |
| Hofmann, Pierce, Wagner, **"Edit Lenses"**, POPL 2012, doi:10.1145/2103621.2103715. <https://repository.upenn.edu/cis_papers/677/> | `[SECONDHAND]` |
| Hofmann, Pierce, Wagner, **"Symmetric Lenses"**, POPL 2011 | `[SECONDHAND]` |
| Hofmann, **"Modular Edit Lenses"**. <https://www.cs.ox.ac.uk/projects/tlcbx/ssbx/hofmann.pdf>; **"Edit languages for information trees"**, ECEASST | `[NOT READ]` |
| Diskin, Xiong, Czarnecki — **delta lenses** | `[SECONDHAND]` |
| Johnson & Rosebrugh, **"Unifying Set-Based, Delta-Based and Edit-Based Lenses"**, BX 2016, CEUR-WS Vol-1571 paper 13. <https://ceur-ws.org/Vol-1571/paper_13.pdf> | `[NOT READ]` — **read this first if picking up the lens thread** |
| Bohannon, Foster, Pierce, Pilkiewicz, Schmitt — **Boomerang**, POPL 2008; **quotient lenses**, ICFP 2008; Barbosa, Cretin, Foster, Greenberg, Pierce — **matching lenses**, ICFP 2010 | `[SECONDHAND]` |
| Bancilhon & Spyratos, **"Update semantics of relational views"**, ACM TODS 6(4), 1981 | `[SECONDHAND]` — via Foster et al. §10 |
| Dayal & Bernstein, **"On the correct translation of update operations on relational views"**, ACM TODS 7(3), 1982 | `[SECONDHAND]` — via Foster et al. §10 |
| Gottlob, Paolini, Zicari, **"Properties and update semantics of consistent views"**, ACM TODS 13(4), 1988 | `[SECONDHAND]` — via Foster et al. §10 |
| Hegner, closed/open views, ICDT 1990 and AMAI 2004 | `[SECONDHAND]` — via Foster et al. §10 |
| **PatchOptic**, arXiv:2607.05483, Jul 2026 | `[NOT READ]` — flagged for follow-up |

## Streaming lower bounds (background for the Ω(m) argument)
| ref | status |
|---|---|
| **"Streaming Lower Bounds and Asymmetric Set-Disjointness"**, arXiv:2301.05658 | `[SECONDHAND]` |
| Sherstov, **"Communication Complexity Theory: Thirty-Five Years of Set Disjointness"**, MFCS. <http://web.cs.ucla.edu/~sherstov/pdf/mfcs-disjointness.pdf> | `[SECONDHAND]` |
| (the fooling-set argument in §9.3.2 is self-contained and needs neither) | `[MINE]` |

## Negative-result searches (queries run, nothing found)
These are findings, not failures. All run via WebSearch, Sept 2026.

1. `static type checking JSON Patch schema preserving update "JSON Schema" validity
   without applying patch` — **nothing academic.** Only blog/vendor advice to
   "validate the patch against the JSON-Patch meta-schema, apply, revalidate the
   result", plus JSON *subschema/containment* papers, which are a different problem.
2. `typed patches` / `well-typed edits` / `type system for document updates` /
   `schema-preserving update JSON` — **nothing for JSON.** All hits are the XML
   literature of §3/§11.
3. `incremental validation JSON Schema after update revalidate subtree local change`
   — **no academic work on incremental JSON Schema validation.** Closest: Blaze
   (compilation, PVLDB), practitioner advice to cache the compiled validator, and one
   vendor blog restating Balmin's algorithm uncited.
4. Streaming/bounded-memory JSON Schema validation — **no characterisation exists.**
   No JSON analogue of Segoufin & Vianu.
5. A compositional / local / splice-safe fragment **of JSON Schema** — **nothing.**
   The JSON Schema statics literature (2016–2025) covers validation, satisfiability,
   inclusion, equivalence and witness generation of *whole documents*, and does not
   treat updates or locality at all.
6. Complexity of satisfiability for the **negation-free** fragment of JSON Schema —
   **not published as far as I can find.**

## The three "we stopped here" admissions in the literature — worth quoting in the paper
1. **RFC 5261 §** — the XML patch framework: instance documents "MUST be well formed
   and SHOULD be valid", and the framework itself does not validate schema compliance
   of the result; referencing specifications must define that requirement.
2. **Benedikt & Cheney, DBPL 2009** — at the time of XQuery Update Facility 1.0
   Candidate Recommendation, "the typing rules in the W3C proposal appeared **unsound**
   for `transform` queries."
3. **Baazizi, Bidoit, Colazzo, Malla, Sahakyan, EDBT 2011** — having built and proved
   project → update → merge: **"It should be noted that the revalidation issue is not
   considered in this paper."**
---

# 14. LATE ADDITION — Bourhis et al. PODS 2017 obtained as PRIMARY. Corrections and one major new result.

I got the arXiv PDF to extract on a second attempt. **Everything I had flagged as
`[SECONDHAND]` from this paper is now `[PRIMARY]`, one bound was *understated*, and
there is a result nobody quoted to me that changes the picture: with data-value
equality plus recursion, satisfiability is UNDECIDABLE.**

**Bourhis, Reutter, Suárez, Vrgoč, "JSON: data model, query languages and schema
specification", PODS 2017:123–135 · arXiv:1701.02221v1.**  `[PRIMARY — full text read
via pdftotext]`

Two formalisms: **JNL** (JSON Navigational Logic, the query language) and **JSL**
(JSON Schema Logic, the schema logic). `Unique` is their predicate for `uniqueItems`;
`EQ(·,·)` is data-value equality between two navigation paths.

> **Theorem 1.** "JSL and JSON Schema are equivalent in expressive power."
> (Precisely: "JSON Schema can be expressed in JSL. String-deterministic JSL can be
> expressed in JSON Schema.")
>
> **Theorem 3.** "Well-formed recursive JSL and well-formed recursive JSON Schema are
> equivalent in expressive power."

So JSL bounds *are* JSON Schema bounds. The schema results:

> **Proposition 7.** "The Satisfiability problem for **JSL** is **in EXPSPACE**, and
> **PSPACE-complete for expressions without Unique**."
>
> **Proposition 10.** "The Satisfiability problem for **recursive JSL** expressions is
> **in 2EXPTIME**, and **EXPTIME-complete for expressions without the Unique
> predicate**."

That is exactly the EDBT-2025 table (§5.4) — now confirmed at the primary source, and
the attribution is right: **the four-row table is Bourhis et al.'s Propositions 7 and
10.**

### 14.1 The `Unique` upper bounds are NOT known to be tight — say so

Verbatim, from their §"Satisfiability" discussion:

> "The most common way of building a satisfiability algorithm in schema formalisms for
> trees is to show that they are **equivalent to some class of tree automata** whose
> non-emptiness problem can be shown to be decidable. We use the same ideas, albeit we
> need to introduce **a specific model of automata that can capture our formalism**.
> Interestingly, we show that **the `Unique` predicate can also be handled in this
> case, albeit with an exponential blowup.** To show this we encode `Unique` as a
> **special local constraint** ... **Again, we do not know if this blowup is
> unavoidable.**"

Two things to take from this:
1. **The EXPSPACE and 2EXPTIME figures for `uniqueItems` are upper bounds with no
   matching lower bound, and the authors say so.** Do not write "2EXPTIME-complete".
   The correct phrasing is "EXPTIME-hard and in 2EXPTIME" (recursive) /
   "PSPACE-hard and in EXPSPACE" (non-recursive).
2. **`uniqueItems` was handled by encoding it as a "special local constraint" inside a
   purpose-built automaton model.** So it is not that `uniqueItems` is unhandleable —
   it is that it does not fit the *standard* tree automata, which is precisely Pezoa et
   al.'s MSO/tree-automata non-capturability result seen from the algorithmic side.
   The two statements are consistent and complementary; cite both.

### 14.2 MAJOR NEW RESULT — value equality + recursion ⇒ **UNDECIDABLE**, even without negation

This is the strongest negative result in the whole file and nothing in my earlier
sections anticipated it.

> **Proposition 4.** "The Satisfiability problem is **undecidable** for
> non-deterministic **recursive** JNL formulas, **even if they do not use negation**."

Proof route, verbatim: "We prove that the satisfiability for **positive** JSL queries
is undecidable. We reduce the problem of **emptiness of two counters machine**." The
encoding stores each counter as the *height* of a subtree and uses `EQ(Xc1, Xnext·Xc1·Xa)`
to force the increment/decrement relation between successive configurations.

**What this means for us.** The undecidability needs `EQ(·,·)` — *value equality
between two positions* — together with recursion. That combination is exactly:
- **cross-references / foreign keys** ("this field must equal that field elsewhere"),
- **`$ref`-recursive models** carrying such a constraint,
- and, in the Pydantic world, a `@model_validator` that compares two fields inside a
  self-referential model.

`uniqueItems` is a *weaker* form of the same thing (all-distinct rather than a
directed equality between two named paths), which is why it lands in EXPSPACE/2EXPTIME
rather than undecidability. **But the moment a design admits general cross-field value
equality plus recursion, the "can this be completed?" question is not merely
intractable — it is undecidable.** That is a hard wall and it should be stated as one:

> **There is no algorithm — of any complexity — that decides prefix-feasibility for a
> schema language with data-value equality and recursion.** (Bourhis et al. 2017,
> Prop. 4, by reduction from two-counter machine emptiness; holds even for the
> negation-free fragment.)

This strengthens **Conjecture 1** considerably: the conjecture said "intractable in
general"; the correct statement is "**intractable for JSON Schema, and undecidable for
any extension with cross-position value equality plus recursion**". Since real systems
*do* want referential integrity across a recursive document, this is the argument that
kills exact decode-time constraint for the general case outright, not merely on
complexity grounds.

### 14.3 The negation-free question — partially answered, at primary source

I flagged in §9.1.3 that the complexity of the *negation-free* fragment was not
published. Bourhis et al. answer it for the sister logic:

> **Proposition 2.** "The Satisfiability problem for **JNL** is **NP-complete**. It is
> **NP-hard even for formulas not using negation nor the equality operator**."

and they give the same intuition I derived independently in §9.1.3, verbatim:

> "It might be somewhat surprising that the positive fragment without data comparisons
> is not trivially satisfiable. This holds due to the fact that **each key in an object
> is unique**, so a formula of the form `X_a[X_1] ∧ X_a[X_b]` is unsatisfiable because
> it **forces the value of the key `a` to be both an array and a string at the same
> time**."

> **Sub-verdict, revised:** my NP-hardness reduction in §9.1.3 is **correct and
> matches a published result in spirit** — Bourhis et al. prove NP-hardness for the
> negation- and equality-free fragment of JNL, by exactly the mechanism I used
> (type-disjointness at a shared key, not logical negation). **What is still not
> published is the complexity for the negation-free fragment of JSON Schema / JSL
> itself.** Given Prop. 7 puts *full* non-recursive JSL at PSPACE-complete and Prop. 2
> puts negation-free JNL at NP-hard, the gap between NP and PSPACE for negation-free
> JSL is a small, well-posed, genuinely open question. **Still the best candidate for
> a self-contained theorem of our own.**

### 14.4 One more usable result: evaluation is linear without value equality

> **Proposition 3.** "The evaluation problem for JNL with non-determinism and recursion
> can be solved in **cubic time**, and in **linear time if the formula does not use
> predicate `EQ(·,·)`**."

Their method: JNL "is a syntactic variant of **PDL**" and JSON trees "can be viewed as
generalisations of Kripke structures", so classical PDL model checking applies; with
`EQ` present they fall back to a cubic PDL algorithm.

**Useful to us in two ways.** First, it reconfirms Q1 (membership/revalidation) is
cheap — **linear**, not merely PTIME-complete, once value comparisons are absent.
Second, the identification **JSON Schema ≈ PDL over Kripke structures** is the cleanest
one-line characterisation of the schema language available, and it explains every
complexity number in this file: PSPACE for non-recursive (modal logic satisfiability),
EXPTIME for recursive (PDL satisfiability), undecidable once you add data equality
(the classical wall for logics with data comparisons).

### 14.5 Corrections to apply to earlier sections of this file
1. **§5.1 / §5.2**: Bourhis et al. is now `[PRIMARY]`. Cite **Proposition 7** for the
   non-recursive row and **Proposition 10** for the recursive row.
2. **§5.4 / §9.1.2**: write "PSPACE-hard, in EXPSPACE" and "EXPTIME-hard, in 2EXPTIME"
   for the `uniqueItems` rows — the authors explicitly do not claim tightness.
3. **§9.1 (Conjecture 1)**: add the undecidability result (Prop. 4) as the extreme
   case. The verdict stays **CONFIRMED** and gets stronger.
4. **§9.3 (Conjecture 3)**: Prop. 4's `EQ` + recursion undecidability is the
   theoretical companion to the Ω(m) streaming bound — the same feature (value
   equality across positions) that forces unbounded memory also forces undecidability
   once recursion is added.
5. **§5.1's `O(|S|²·|J|)` validation figure** (reconstructed from a mangled Attouche
   quotation, attributed to Pezoa et al.) — Bourhis et al.'s Prop. 3 gives **linear**
   evaluation without `EQ`. Both are consistent with PTIME-completeness; prefer the
   primary-sourced statement, and still verify against Pezoa et al. before printing a
   specific polynomial.
