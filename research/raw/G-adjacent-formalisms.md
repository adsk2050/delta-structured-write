# G — Adjacent Formalisms: Has a Neighbouring Field Already Solved This?

Status: COMPLETE. All 7 sections plus ranked list below. (Note: this research
run was interrupted mid-session-4-research by a session limit and resumed;
sections 1-3 survived the interruption untouched, sections 4-7 and the ranked
list were completed after resume, with section 6 promoted to top priority and
sections 2/4/5 compressed, per the resuming coordinator's instructions. File
was reordered into numeric order at the end for readability — no content was
changed in the reorder, only position.)

Assignment: for schema-governed LLM output (localise region -> project sub-schema
S@p -> generate fragment under constrained decoding -> splice -> revalidate globally),
survey neighbouring formalisms that define "deltas" over structured/schema-shaped data
and ask whether they transfer.

Sections:
1. JSON CRDTs / delta-state CRDTs
2. Operational Transformation
3. Tree edit distance / structural diff (esp. as an EVALUATION metric)
4. Incremental view maintenance / differential dataflow / DBSP
5. Delta encoding (VCDIFF, bsdiff, git packfiles, rsync)
6. Constraint decomposition & compositional/assume-guarantee verification
7. Database updates preserving integrity constraints (transactions as generate-check-revert)

Final: ranked list of which formalism is most worth borrowing from.

---

## 1. JSON CRDTs and delta-state CRDTs

### What is a "delta" there, exactly

**JSON CRDT (Kleppmann & Beresford).** "A Conflict-Free Replicated JSON
Datatype," M. Kleppmann & A. R. Beresford, *IEEE Transactions on Parallel and
Distributed Systems* vol. 28 no. 10, 2017; also arXiv:1608.03960 (2016).
PRIMARY (verified via arXiv abstract page and author's own blog summary,
https://martin.kleppmann.com/2017/04/24/json-crdt.html). A "delta" here is one
of three primitive operations — insert, delete, assign — applied to an
arbitrarily nested JSON structure of lists and maps. Every operation carries a
unique ID; the algorithm defines merge semantics so that concurrent operations
commute into the same final state on every replica ("no updates are lost,"
"all replicas converge"). This is a value-level delta: a mutation to a JSON
tree, not a schema-aware or type-aware edit.

**Delta-state CRDTs.** Almeida, Shoker & Baquero, "Efficient State-based CRDTs
by Delta-Mutation," NETYS 2015 / arXiv:1410.2803; extended in Enes, Almeida,
Baquero & Leitao, "Efficient Synchronization of State-based CRDTs," ICDE 2019
/ arXiv:1803.02750. PRIMARY (verified via WebFetch of arXiv HTML, corroborated
by an independent web search summarizing the same definitions). Here "delta"
is given a precise algebraic meaning. State lives in a join-semilattice S. A
delta-mutator m^delta is a function S -> S such that applying an update is
`x' = x JOIN m^delta(x)` (join of current state with the delta), instead of
shipping the whole new state. A delta-CRDT is formally the triple (S, M^delta,
Q): semilattice, set of delta-mutators, set of queries. Deltas can be batched
into "delta-groups" before shipping. The entire framework's correctness
property is stated purely in lattice terms: idempotence, commutativity,
associativity of JOIN, i.e. convergence of a *value* to the least upper bound
of everything merged into it.

So across this whole family, "delta" = a small algebraic/operational
description of how the value changed, defined relative to a merge operator.
It is never defined relative to a schema.

### What correctness guarantee do they get — static or dynamic

The guarantee proved is Strong Eventual Consistency (SEC): replicas that have
received the same set of updates (in any order, with any interleaving) reach
identical state, achieved by making the merge operator idempotent, commutative
and associative (a join-semilattice). This is a static, algebraic guarantee
about convergence of the merge operator itself, proved once, at the level of
the data type, independent of any particular document instance. It is
emphatically not a guarantee about the convergent value being valid under any
externally imposed schema, and multiple primary/near-primary sources say so
explicitly:

- Automerge (github.com/automerge/automerge; docs at automerge.org). PRIMARY.
  Its `Table` type "does not currently enforce a schema, and by convention,
  row objects added to a table should have the same properties, but Automerge
  does not enforce this" — an explicit design choice, because different
  replicas may be running different app versions with different properties.
  Concurrent writes to the same key are resolved by picking a deterministic
  "winner" (by operation ID, not timestamp) per
  automerge.org/docs/reference/documents/conflicts/; the losing values are
  NOT discarded, they are kept in a side `conflicts` structure retrievable via
  `Automerge.getConflicts()`. The documentation for this mechanism never
  mentions type-checking or schema consistency — the CRDT layer is fully
  agnostic to whether a "winning" value is even the same type as a value it
  beat.

- automerge-jsonschema, Alex Good (github: alexjg — a core Automerge
  maintainer at Ink & Switch, confirmed via GitHub org membership and release
  history), https://alexjg.github.io/automerge-jsonschema/spec. PRIMARY, and
  the single most useful artifact found for this question. This is a
  purpose-built, restricted JSON Schema vocabulary for validating Automerge
  documents, and its own spec text explains exactly why plain JSON Schema
  fails on CRDT output. Direct quote: "It is possible to have two automerge
  arrays which contain less than maxContains values, but their merge contains
  more than maxContains." I.e. two documents that each individually satisfy a
  cardinality constraint can concurrently insert disjoint elements, and the
  merged document violates it — the constraint "does not distribute over
  merges." The spec's fix is to throw out every JSON Schema keyword that
  isn't provably merge-distributive: `contains` and `prefixItems` are
  explicitly excluded, and only a subset of keywords is kept on the theory
  that valid(A) AND valid(B) implies valid(A JOIN B). It also has to add a
  new, non-standard annotation (`automerge_type`) because standard JSON
  Schema cannot express Automerge's distinction between a plain
  (non-mergeable, LWW) `string` and a mergeable `text` — a distinction with no
  counterpart in JSON Schema at all. And validators are told to check only
  the deterministic "winning" branch of a conflicted document, silently
  ignoring the fact that the conflicting alternative values are still
  physically present in the document. This is about as close as the field
  gets to a formal admission that schema validity is not preserved by CRDT
  merge, full stop — someone had to design a strictly weaker schema
  language, with new keywords, specifically to route around the merge
  operator, and even that only handles the cardinality-style failure mode,
  not e.g. cross-field conditional constraints.

- Invariant preservation is a distinct, actively-researched problem layered
  on top of CRDTs, not a solved sub-case of convergence. "Invariant Safety
  for Distributed Applications" (arXiv:1903.02759, related to "IPA:
  Invariant-Preserving Applications for Weakly-Consistent Replicated
  Databases," arXiv:1802.08474) frames an application as (state, operations,
  merge function, invariant) and gives a worked example: a bank-balance CRDT
  where two replicas each independently make a valid withdrawal and the
  merged balance is -5, violating a "balance >= 0" invariant that both
  pre-merge states satisfied. SECONDHAND-ish (content read via automated PDF
  fetch/summarization; the cached PDF was not independently re-readable in
  this session as plain text to pull exact sentences, but the framing is
  corroborated across multiple independent search snippets describing the
  same paper). "Enforcing Safety and Invariants for Local-First Applications"
  (Programming Group, 2024,
  https://programming-group.com/assets/pdf/papers/2024_Consistent-Local-First-Software-Enforcing-Safety-and-Invariants-for-Local-First-Applications.pdf)
  is a 2024 paper whose entire premise is that CRDT convergence does not give
  you invariant preservation, proposing static analysis to catch
  invariant-violating merges — but (per fetch-tool summary, secondhand/
  lower-confidence) for particular classes of invariants, not a general
  schema language. The existence of this research line in 2024-2026 is
  itself evidence: if CRDT convergence implied schema/invariant preservation,
  this would not still be an open research topic seven-plus years after the
  JSON CRDT paper.

- Yjs (github.com/yjs/yjs; docs.yjs.dev). Searched but found no claim of
  schema enforcement on `Y.Map`/`Y.Array`/`Y.Xml` shared types; documentation
  frames shared types purely as auto-syncing Map/Array/Text primitives with
  no validation layer. Treated as a negative result (absence of evidence, not
  evidence of absence) — weaker than the Automerge findings above, which are
  affirmative.

### Does it transfer to schema-governed LLM output?

**DOES NOT TRANSFER.** This is one of the more confidently negative findings
in this whole survey.

- The entire CRDT correctness apparatus (join-semilattices, SEC proofs) is
  built to guarantee convergence of a value under concurrent, uncoordinated,
  commutative merges with no central arbiter. Our problem is different in a
  way that actually makes it easier, not harder: we have exactly one writer
  (the generation process) producing one fragment against one known projected
  sub-schema S@p, spliced into one known parent, with no concurrent edits to
  reconcile. We do not need commutativity or an algebraic merge operator at
  all — we need "does the spliced document satisfy S," a one-shot validity
  question, not a convergence question.
- The one part of the CRDT world that is on point — "does combining two valid
  pieces stay valid" — is exactly the part CRDT research shows is generally
  FALSE for ordinary schema constraints (the automerge-jsonschema
  `maxContains` example), and where it is rescued at all, it is rescued only
  for a hand-picked, merge-distributive subset of constraint types, which is
  precisely the shape of our own "known residue" (cardinality, `uniqueItems`,
  cross-field `required`) named in the shared context. This is a genuine,
  citable confirmation of the assignment's stated prior, not just an absence
  of a counterexample.
- What does transfer as a vocabulary/framing device: the CRDT literature's
  own move of separating "convergence of the merge operator" (static, proved
  once) from "invariant preservation of the merged value" (needs a second,
  separate mechanism — static analysis of which invariant classes are safe,
  or runtime re-validation) is a clean two-layer split that maps onto our own
  LOCALISE/GENERATE (value-level, like a CRDT operation) vs.
  revalidate-globally (invariant-level, exactly the open problem in the
  IPA/2024 local-first-safety line) structure. That framing is worth citing;
  the machinery underneath it (semilattices, delta-mutators) is not directly
  reusable, because our "operations" are LLM-generated JSON fragments, not
  algebraically-defined mutators with a proven join.

---

## 2. Operational Transformation (brief, as requested)

**What it is.** Originated in Ellis & Gibbs, "Concurrency Control in Groupware
Systems," ACM SIGMOD 1989 (the GROVE editor) — PRIMARY citation confirmed via
ACM DL record (dl.acm.org/doi/10.1145/67544.66963), full text not
independently re-fetched this session (paywalled/blocked), so treat the exact
paper content as secondhand via search-engine description, though the
citation and venue are solid. OT transforms a concurrent operation against
operations that happened concurrently elsewhere, so it can be applied to a
possibly-different document state and still produce the intended effect. It
became the basis of real production co-editors (Google Docs traces to the
Jupiter OT algorithm; per Wikipedia / secondary sources).

**Correctness properties.** Via Wikipedia (en.wikipedia.org/wiki/Operational_transformation,
SECONDHAND/secondary but a reasonable overview for a brief section): OT
targets three properties — **convergence** (replicas identical at
quiescence), **causality preservation** (respecting cause-effect order), and
**intention preservation** (an operation's effect matches what the user meant
even if applied against a different document state than the one it was
authored against). These are the classical CC/CP/IP correctness criteria.

**Why largely superseded by CRDTs.** Early OT algorithms had documented
convergence bugs under certain concurrent interleavings; this motivated
"post-OT," transformation-free approaches — WOOT, Logoot, Causal Trees, and
eventually the CRDT line proper (per secondary sources above; note also that
a "Real Differences between OT and CRDT..." line of papers, e.g.
arXiv:1905.01517/1905.01518, secondhand, pushes back on a simplistic "OT is
obsolete" narrative and argues the tradeoffs are more nuanced — flagged here
as a live academic disagreement rather than settled fact). Either way, OT is
not the dominant new-system choice today; CRDTs are more common for new
peer-to-peer / local-first designs.

**Does OT ever preserve schema/validity?** Checked specifically, including
tree/XML-structured extensions of OT (e.g. treeOPT-style systems and
arXiv:1512.05949, "TP1-valid Transformation Functions for Operations on
ordered n-ary Trees" — fetched, SECONDHAND via fetch-tool summarization of
the PDF). Finding: **no.** Even the tree-structured OT literature defines its
correctness purely as **TP1/TP2 structural-convergence properties**
("operations applied in different orders yield an identical final tree,"
positional/structural consistency), with node type, cardinality, and DTD/
schema-style constraints explicitly out of scope. The fetch-tool summary of
arXiv:1512.05949 states this plainly: "A valid tree could become invalid
after transformations if schema rules are violated — this work ensures
structural consistency only." No source found across this section claims OT
(character-level, or tree/XML-extended) ever incorporated a notion of schema
validity as a first-class correctness target.

**Verdict: DOES NOT TRANSFER.** Same shape of gap as CRDTs, for the same
reason — OT's correctness criteria (CC/CP/IP, or TP1/TP2 for trees) are about
operation-application order and structural convergence between concurrent
editors, not about a value satisfying an externally imposed schema. It adds
one thing CRDTs don't foreground — "intention preservation" — which is an
interesting *naming* of a property we implicitly want (a generated fragment
should reflect what was asked for, even though the surrounding document
differs from what the generator saw), but no mechanism here checks that
against a schema; it's checked against the *other operations*, not against a
validity predicate. Not worth borrowing machinery from; worth citing only as
"the neighbouring field that had the closest-sounding vocabulary and still
never touched validity."

---

## 3. Tree edit distance and structural diff (framed here as an EVALUATION metric)

### What is a "delta" there

**Zhang & Shasha**, "Simple Fast Algorithms for the Editing Distance Between
Trees and Related Problems," *SIAM Journal on Computing* 18(6):1245-1262,
1989. PRIMARY citation confirmed (multiple independent listings incl.
ScienceDirect record and a hosted PDF at grantjenks.com); full text not
independently re-read this session, so treat exact page/theorem numbers as
secondhand-via-citation-record, but the result itself is undisputed and
extremely well known. Defines **tree edit distance (TED)**: the minimum-cost
sequence of node insert/delete/relabel operations transforming one labeled,
ordered tree into another, computed via dynamic programming over "keyroots."
This is the tree generalization of Levenshtein string edit distance, and it
*is* a formally minimal delta by construction — unlike the CRDT/OT deltas
above, which are operational logs, not minimum-cost transformations.

**Modern algorithm.** Pawlik & Augsten, "RTED: A Robust Algorithm for the
Tree Edit Distance," VLDB 2012 (arXiv:1201.0230), and its successor **APTED**
("Efficient Computation of the Tree Edit Distance," ACM TODS 40(1), 2015;
"Tree Edit Distance: Robust and Memory-Efficient," Information Systems 56,
2016) — PRIMARY citations confirmed via VLDB/ACM records. APTED is the
current state of the art: worst-case **O(n^3) time, O(n^2) space**, provably
matching the best possible complexity for this family of algorithms at every
input instance (not just worst case). Practical upshot: exact minimum TED is
polynomial but cubic — fine for per-document evaluation on modest documents,
not something you would run as an inner-loop training signal on
10,000-row tables without approximation or sampling.

**Practical JSON diff tools do NOT compute true minimum tree edit
distance** — worth stating precisely because it's a common conflation.
Checked jsondiffpatch (github.com/benjamine/jsondiffpatch, PRIMARY, read
README directly): it diffs arrays via LCS (longest common subsequence), and
object-to-object correspondence inside arrays is resolved by a
developer-supplied `objectHash` function, falling back to dumb positional
matching if none is given. Its own docs make no claim of minimality or
optimality — it says "smart," not "minimal." The same is true in spirit of
**json-delta** (json-delta.readthedocs.io) and **deepdiff** — these are
practical, fast, heuristic structural-diff tools, not implementations of
Zhang-Shasha/APTED. **JSON Patch, RFC 6902** (IETF, April 2013,
rfc-editor.org/rfc/rfc6902.html — PRIMARY, confirmed) standardizes only the
*representation* of a patch (add/remove/replace/move/copy/test operations
addressed via JSON Pointer, RFC 6901) — it says nothing about how a minimal
patch is computed; that's left to whatever diff algorithm produces the
operation list. So: a real minimum-TED number and "the diff my JSON tool
printed" are two different things, and only the former has a formal
minimality guarantee.

### What correctness guarantee, static or dynamic

TED itself is not a correctness guarantee at all — it is a **measurement**,
computed after the fact, static in the sense that it's a pure function of two
fixed trees (no notion of "during" an edit). This is exactly why it's the
right category of tool for evaluation rather than for the generation
mechanism itself: it doesn't prevent or guarantee anything, it scores how far
apart two artifacts are.

### Does it transfer — and to what, exactly

**PARTIALLY TRANSFERS, and only to evaluation, not to generation or
validity-preservation.** This section is scoped by the assignment itself to
be about measurement rather than the core architecture, and that scoping is
correct: TED has nothing to say about schema validity (a tree can be
edit-distance-1 from a valid tree and still invalid, e.g. deleting a
`required` field is a single relabel/delete op). But as a metric for "did the
system change only what it should have," it is close to the natural
ground truth, with the caveat that JSON has commutative-object-key semantics
that a naive ordered-tree TED doesn't respect (two JSON objects that differ
only in key order are semantically identical but not tree-identical under
plain Zhang-Shasha, since it is defined for *ordered* trees).

**This exact gap is a live, current LLM-evaluation research topic, not a
solved textbook thing** — a directly on-point and encouraging finding:

- **STED and Consistency Scoring: A Framework for Evaluating LLM Structured
  Output Reliability**, arXiv:2512.23712 (OpenReview: rSCV1hTZvF). PRIMARY
  abstract read; deeper technical content (exact formula for the semantic/
  structural blend) not extracted this session (fetch tool returned only
  headline results and metric numbers, not the formula — flag as
  incompletely verified). What is confirmed from the abstract/results
  directly: STED is built specifically to fix plain TED for **JSON output
  evaluation** by blending "semantic flexibility" (differently-phrased but
  equal values, and implicitly key-order-agnostic object comparison) with
  "structural strictness," and the paper reports it beats plain TED,
  BERTScore, and DeepDiff on a synthetic benchmark (0.86-0.90 similarity for
  outputs that are semantically equivalent but not identical, ~0.0 for
  genuine structural breaks). It is used in that paper for **cross-run
  consistency scoring** (does the same LLM asked repeatedly produce
  equivalent JSON), which is an adjacent but different question from ours
  ("did one specific edit stay inside its intended region") — the metric
  machinery transfers, the specific use-case in the paper does not.
- **Generalized Tree Edit Distance (GTED): A Faithful Evaluation Metric for
  [Statement Autoformalization]**, arXiv:2507.07399. PRIMARY abstract/problem
  statement read (fetched, but formula-level detail is secondhand via
  fetch-tool summary of the PDF, not independently re-verified). Same
  pattern — plain TED penalizes structurally-different-but-semantically-equal
  trees, so the field is patching TED with domain-aware equivalence rules —
  but this instance is specific to formal-math proof syntax, not JSON/schema
  data, so treat it as **corroborating evidence that "plain TED needs a
  semantic layer for LLM eval" is a general, recurring finding**, not as a
  directly reusable metric for our problem.
- **Structure-BiEval**, arXiv:2601.19923 (Jan 2026) — found via search only,
  not fetched; noted here as a pointer to a third, very recent (weeks-old
  relative to today) paper in the same "decouple structure from content when
  evaluating LLM structured output" vein. Not independently verified beyond
  title/one-line description — listed as a lead for whoever picks this up
  next, not as a citable claim.

### What a good metric would actually be (synthesis, not one paper's answer)

Given the above, the honest recommendation for "did the system change only
what it should have" is a **small composite**, because no single existing
tool does the whole job:

1. **Canonicalize before diffing.** Sort object keys, so key-order noise
   (which every ordered-tree TED algorithm is sensitive to, per Zhang-Shasha's
   own "ordered trees" framing) doesn't register as a structural change.
2. **Compute exact TED (APTED, not a heuristic JS diff library) between the
   pre-edit and post-edit document**, restricted first to nodes *outside* the
   localized region p — this number should be exactly 0 if localization was
   respected; any nonzero value here is the direct, formal measurement of
   "changed something it shouldn't have." This is the piece none of the
   surveyed off-the-shelf JSON-diff tools (jsondiffpatch/json-delta/deepdiff)
   guarantee, because none of them compute true minimum TED — for this
   specific use (a strict boundary check, not a display diff), the
   heuristic-vs-exact gap matters and APTED/RTED should be used directly
   rather than a JS/py "diff" convenience library.
3. **Inside the region p**, TED between generated fragment and *some*
   reference is the wrong tool alone (per STED/GTED's shared finding that
   plain TED conflates "structurally different" with "wrong") — pair it with
   schema validation of the fragment (did it satisfy S@p) rather than
   distance-to-a-single-reference, since for generative tasks there is
   usually no unique correct fragment.
4. Report both numbers separately (out-of-region TED = containment/leakage
   metric; in-region validity = correctness metric) rather than a single
   blended score — the STED approach of blending them into one similarity
   number is well-suited to *its* use case (cross-run consistency of a whole
   document against itself) but would hide exactly the distinction ("did it
   leak outside its box" vs "was what's inside the box right") that our
   evaluation needs to keep visible.

---

## 4. Incremental view maintenance, differential dataflow, DBSP (kept short, per
instruction — confirming a prior expectation rather than opening a new line)

**What's a delta.** In Differential Dataflow (McSherry, F., Murray, D.G.,
Isaacs, R. & Isard, M., "Differential Dataflow," CIDR 2013 — PRIMARY,
confirmed via dblp; note the assignment's author list said "McSherry,
Murray, Isaacs, Abadi" but dblp's record for this specific CIDR 2013 paper
lists Isard, not Abadi, as the fourth author — flagging the correction
rather than silently using either) and in **DBSP** (Budiu, M., Chajed, T.,
McSherry, F., Ryzhyk, L. & Tannen, V., "DBSP: Automatic Incremental View
Maintenance for Rich Query Languages," VLDB 2023 / arXiv:2203.16684 —
PRIMARY, abstract fetched and quoted verbatim from arXiv), a delta is a
**change to a relation/stream, represented in the same algebraic universe as
the data itself** — DBSP's own framing (per its abstract, quoted directly):
*"we describe a simple but expressive language called DBSP for describing
computations over data streams [and] give a general algorithm for solving
the incremental view maintenance problem for arbitrary DBSP programs."* The
guarantee proved is that incremental evaluation (apply the delta) and
non-incremental evaluation (recompute from scratch) **agree** — a value-
equivalence theorem, extremely well-formalized (DBSP recasts IVM as stream
differentiation over commutative groups, per independent search-summary
description).

**Does it help maintain validity, not just a computed value? More nuanced
than the flat "no" this section expected going in — worth stating precisely
rather than forcing the expected answer.** The classical materialized-view
literature already contains the relevant trick: Ross, K.A., Srivastava, D.
& Sudarshan, S., "Materialized View Maintenance and Integrity Constraint
Checking: Trading Space for Time," SIGMOD 1996, pp. 447-458 (bibliographic
facts confirmed via dblp) — its own title says exactly what it does:
**model an integrity constraint as a materialized view whose result is
required to be empty** (e.g. "the view selecting all rows that violate
constraint C"), and then *constraint checking reduces to incrementally
maintaining that view*, reusing ordinary IVM machinery with no
constraint-specific mechanism needed. So the honest finding is: IVM/
differential-dataflow machinery does not natively distinguish "validity" from
"value" as separate concepts — but that's because it doesn't need to. A
validity check is just a query (does the "violations" view have zero rows?),
and if your constraint language is expressive enough to write that query,
ordinary IVM machinery maintains its truth value incrementally for free,
with the same value-equivalence guarantee as any other view. What it still
does **not** give is anything to do with *repairing* an update that would
break the constraint (it can tell you incrementally *that* consistency
broke, not fix it) — closer to a cheap early-warning check than to a
generation-time guarantee, and one only as expressive as whatever base
query language it's built on (DBSP claims quite broad coverage: full
relational queries, aggregation, monotonic and non-monotonic recursion).

**Verdict: PARTIALLY TRANSFERS — narrower than it first looks, but real.**
DOES NOT TRANSFER to the GENERATE step (nothing here helps produce a
schema-valid fragment). PARTIALLY TRANSFERS to the REVALIDATE step, as a
genuinely reusable idea for making "did splicing fragment f break global
validity" cheap to check incrementally rather than re-running full schema
validation over the whole document on every edit: encode "does this JSON
document violate constraint C" as a query over the document's structure
(most JSON Schema keywords are checkable as simple relational-style
predicates — existence, count, uniqueness — well within what
Datalog/relational-algebra-based IVM already covers per Ross/Srivastava/
Sudarshan and DBSP's stated scope), and let IVM machinery maintain that
check's truth value across edits instead of recomputing it from scratch each
time. This is an efficiency technique for the revalidation step, not a
formalism for the generation or splicing step, and not a validity
*guarantee* mechanism — it only ever tells you after the fact whether you
broke something, same as any other revalidation, just incrementally instead
of from scratch.

---

## 5. Delta encoding (vocabulary/cost-baseline only, per instruction)

**VCDIFF, RFC 3284** (Korn, D., MacDonald, J., Mogul, J. & Vo, K.-P., "The
VCDIFF Generic Differencing and Compression Data Format," IETF RFC 3284,
2002 — PRIMARY, standard RFC), **bsdiff** (Percival, C., binary diffing via
suffix-sorting for executables), **git's delta compression / packfiles**
(pack objects store many blobs as deltas against a similar base, chosen
heuristically by size/similarity, not schema-aware), and **rsync's rolling
checksum** (Tridgell & Mackerras, 1996, block-level rolling hash to find
matching regions between two files without both being present on one host)
are all **byte/line-level compression and transfer techniques**: minimize
bytes moved between two mostly-similar blobs. None has any concept of a
schema, a JSON tree, or a validity predicate — they operate below the
structure our problem lives at, on raw bytes or lines. Their entire value to
us is **vocabulary and cost intuition** (this is the field that established
what "small diff" and "reference/base + delta" mean as engineering terms,
and is a reasonable citation if the write-up needs a baseline for "delta
size relative to full-document size" cost framing), not technique — DOES
NOT TRANSFER as a mechanism, full stop, and no further time was spent
here per instruction.

---

## 6. Constraint decomposition and compositional generation

*(Promoted to top priority mid-run: another agent's constrained-decoding survey
flagged CP's joint handling of GRAMMAR/REGULAR with ALLDIFFERENT/GCC as the
single best unexplored lead, allegedly uncited in the LLM decoding
literature. This section chases that specifically, then the general
local-vs-global-consistency and assume-guarantee questions.)*

### The building blocks, individually (all confirmed, mostly primary bibliographic
records; original 1990s papers are scanned images with no text layer, so exact
wording is secondhand-via-citation-record even where the bibliographic facts
are solid and cross-corroborated)

- **REGULAR constraint.** Pesant, G., "A Regular Language Membership
  Constraint for Finite Sequences of Variables," CP 2004, LNCS 3258,
  pp. 482-495 (link.springer.com/chapter/10.1007/978-3-540-30201-8_36).
  Constrains a fixed-length sequence of finite-domain variables so that the
  sequence of values read off is a word in a given regular language.
  Filtering algorithm achieves **generalized arc consistency (GAC)** by
  unfolding the automaton into a layered directed multigraph (one layer per
  sequence position, one node per automaton state) and pruning
  variable/value pairs with no path from start to an accepting state — this
  is exactly "constrained decoding," independently invented in CP a full
  20 years before it was named that in the LLM literature. This is
  precisely the analogue of our schema/grammar S.

- **GRAMMAR constraint.** Sellmann, M., "The Theory of Grammar Constraints,"
  CP 2006; Quimper, C.-G. & Walsh, T., "Global Grammar Constraints," CP 2006
  (cquimper.github.io/publications/grammars_TR.pdf has a full technical
  report version). Generalizes REGULAR to full context-free languages:
  a sequence of variables must read off a word in a given CFG. GAC
  propagation runs in **cubic time**, matching CYK-parser complexity — CP's
  own framing is explicitly "propagation is like parsing, but considering
  all solutions rather than finding one." Follow-up work (Kadioglu &
  Sellmann, "Efficient Context-Free Grammar Constraints," AAAI 2008,
  cdn.aaai.org/AAAI/2008/AAAI08-049.pdf) improves the practical constant;
  "Decompositions of Grammar Constraints" (arXiv:0903.0470) and "Restricted
  Global Grammar Constraints" (arXiv:0906.5233) study cheaper propagation
  for grammar subclasses (deterministic/unambiguous CFGs) — directly
  relevant if a JSON Schema's structure can be compiled to a
  deterministic grammar, which most concrete schemas can.

- **ALLDIFFERENT.** Regin, J.-C., "A Filtering Algorithm for Constraints of
  Difference in CSPs," AAAI-94, pp. 362-367
  (cdn.aaai.org/AAAI/1994/AAAI94-055.pdf — scanned, unreadable by this
  session's tools; bibliographic facts cross-confirmed via ResearchGate/ACM/
  AAAI listings). GAC via bipartite-matching / strongly-connected-components
  on the value graph; time O(p^2 d^2) for p variables of domain size <= d
  (later work improves this — not chased further here, out of scope for a
  brief building-block summary). This is the formal home of `uniqueItems`.

- **Global Cardinality Constraint (GCC).** Regin, J.-C., "Generalized Arc
  Consistency for Global Cardinality Constraint," AAAI-96, pp. 209-215
  (same access caveat as above). Bounds, for every value v, how many
  variables may take value v, via a theorem from flow theory; GAC in
  O(|X|^2 |V|). This is the formal home of `minItems`/`maxItems`-style
  cardinality bounds (and, read per-value, of `uniqueItems` as the special
  case where every bound is [0,1]) — confirmed directly by the Global
  Constraint Catalog (gccat, sofdem.github.io/gccat/gccat/Calldifferent.html):
  **"An automaton implementation [of ALLDIFFERENT] counts the number of
  occurrences of each value and finally imposes that each value is taken at
  most one time"** — i.e. the CP field already treats ALLDIFFERENT as a
  special case of a counting constraint over an automaton substrate, which
  matters directly for the next question.

### The question that matters: is GRAMMAR/REGULAR ever propagated JOINTLY
with ALLDIFFERENT/GCC?

**Yes, in a specific and instructive form — but not in full generality, and I
did not find the clean single citation the lead hoped for.** Reporting both
what exists and what I could not find, as instructed.

**What exists:**

1. **COSTREGULAR** (Demassey, S., Pesant, G. & Rousseau, L.-M., 2006,
   "A Cost-Regular Based Hybrid Column Generation Approach," *Constraints*
   11(4), link.springer.com/article/10.1007/s10601-006-9003-7 — secondhand
   via search-engine summary of the primary abstract, corroborated across
   two independent listings). Generalizes REGULAR with a per-transition
   cost and a **cost/counter variable** equal to the total cost of the
   accepted word, propagated on the same layered graph via a shortest/
   longest-path style DP. This is the CP field's standard way of attaching
   an aggregate counting dimension to an automaton constraint, and it is
   the direct ancestor of:

2. **Regular counting constraints.** Beldiceanu, N., Flener, P., Pearson, J.
   & Van Hentenryck, P., "Propagating Regular Counting Constraints," AAAI
   2013 / arXiv:1309.7145. PRIMARY — abstract fetched and quoted verbatim
   from arXiv. This is the closest direct hit to the lead's question. A
   "regular counting constraint" bounds **how many times a regular-language
   pattern occurs** in a sequence, modeled via a counter-DFA (cDFA). Exact
   quote: *"We show how to enforce domain consistency in polynomial time for
   atmost and atleast regular counting constraints based on the frequent
   case of a cDFA with only accepting states and a single counter that can
   be incremented by transitions. We also prove that the satisfaction of
   exact regular counting constraints is NP-hard."* This gives a **sharp,
   precise, directly citable complexity boundary** for joint
   grammar-plus-counting propagation: **at-most / at-least bounds on top of
   a regular-language constraint are polynomial; an exact-count bound on top
   of the same constraint is NP-hard.** That boundary lands EXACTLY on our
   own residue: `minItems`/`maxItems` (inequality-shaped cardinality) sit on
   the tractable side; `minItems == maxItems` (an exact-count requirement,
   which is how you'd spell "exactly N items" in JSON Schema) sits on the
   provably-intractable side. This is a genuine, load-bearing, transferable
   result, not a loose analogy.

3. **Global Sequencing Constraint (GSC).** Regin, J.-C. & Puget, J.-F.,
   "A Filtering Algorithm for Global Sequencing Constraints," CP 1997,
   pp. 32-46 (link.springer.com/content/pdf/10.1007/BFb0017428.pdf).
   A genuine historical instance of jointly constraining (a) global
   occurrence counts of values (GCC-shaped) and (b) a sliding-window count
   over every length-q sub-sequence (a REGULAR-flavored, local-pattern
   constraint — e.g. "every 7-day window contains >= 2 days off"). Per
   secondary description, Regin & Puget's own solution is **not** a bespoke
   joint filtering algorithm from first principles — it is **an automatic
   reformulation of GSC in terms of GCC**, reusing Regin's 1996 GCC filtering
   algorithm on a transformed constraint network. This is a real, useful
   precedent for us: when you cannot design a joint filtering algorithm
   directly, *reduce the joint constraint to one you already know how to
   filter*. Follow-up: "Flow-Based Propagators for the SEQUENCE and Related
   Global Constraints" (arXiv:0909.4452, secondhand, not deeply chased)
   extends this line.

4. **The generic route: automaton-based reformulation in gccat.** The
   Global Constraint Catalog (sofdem.github.io/gccat) documents a **generic
   automaton-based decomposition** used to express many global constraints
   uniformly, including ALLDIFFERENT and GCC themselves (per the quote
   above). Per search-summary description, this generic route is "well
   suited to table constraint based linearization" rather than to achieving
   the strongest possible consistency level — i.e., you CAN compose almost
   any automaton-shaped constraint with almost any counting-shaped
   constraint by building a joint automaton/table, but genericity is bought
   by giving up the tight GAC guarantees that Regin's bespoke ALLDIFFERENT/
   GCC algorithms achieve. This is an important honest caveat: "can be
   composed" and "can be composed at full GAC, cheaply" are different
   claims, and the literature is candid about that gap.

**What I did NOT find, despite direct searches (reporting as a negative
result, as instructed):** a single paper giving a bespoke, full-generality,
full-GAC joint filtering algorithm for "arbitrary context-free GRAMMAR
constraint AND full multi-value GCC/ALLDIFFERENT, propagated together as one
constraint, at the same strength each achieves alone." Queries tried and
coming up empty on this specific combination: `"grammar constraint" combined
"alldifferent" OR "global cardinality constraint" joint propagation
constraint programming`; `complexity conjunction context-free grammar
constraint alldifferent NP-hard global constraints`; `"regular constraint"
combined "global cardinality" automaton values count each variable distinct
filtering algorithm`; `"regular constraint" "alldifferent" combined automaton
counting NP-hard OR polynomial propagation`. What these searches surfaced
instead is the material in points 1-4 above (single-counter regular-counting
results, GCC-via-reduction precedent, and a generic-but-weaker automaton
substrate) plus a general theoretical warning found along the way: enforcing
GAC on a single global constraint can itself be NP-hard depending on the
constraint (Bessiere et al., "The Complexity of Global Constraints," AAAI
2004, cited via search summary — source PDF unreadable this session, scanned/
compressed), and conjunctions of even two copies of the *same* polynomial
constraint are not automatically polynomial (Bessiere, Katsirelos,
Narodytska, Quimper & Walsh, "Propagating Conjunctions of AllDifferent
Constraints," AAAI 2010, ojs.aaai.org/index.php/AAAI/article/view/7554 —
first polynomial **bound**-consistency, not full GAC, algorithm for the
conjunction of just *two* ALLDIFFERENTs, via an extension of Hall's theorem;
GAC for that conjunction is a strictly stronger ask). The honest overall
message: **conjoining global constraints is a recognized hard problem in CP
itself**, tractability is established case by case, and the specific
grammar+cardinality case is tractable only in the restricted single-counter/
at-most-at-least form found above, not proven in general. The coordinator's
lead is real and worth the field's attention, but "CP already has a ready-made
algorithm for GRAMMAR ∧ ALLDIFFERENT at full strength" would overstate what
is actually published.

### Local consistency vs. global consistency, and when local reasoning
suffices

**Freuder, E.C., "A Sufficient Condition for Backtrack-Free Search,"
*Journal of the ACM* 29(1):24-32, 1982** (dl.acm.org/doi/10.1145/322290.322292
— paywalled, not independently re-read this session; the result below is
textbook-standard and cross-confirmed via Wikipedia's "Local consistency"
article, which itself states it descriptively without attributing every
clause to Freuder by name, so treat the *attribution of the exact theorem
statement* as secondhand even though the *existence and content* of the
result is not in doubt — this is genuinely foundational CSP theory, in
Russell & Norvig AIMA and Dechter's "Constraint Processing" textbook).

The core fact, confirmed with a concrete counterexample: **local consistency
does not imply global consistency.** An arc-consistent (or even path-
consistent) CSP instance can still have *no solution* — the textbook example:
three variables x1, x2, x3 each pairwise arc-consistent (x1=1 consistent with
x2=1, and with x3=1) where the *triple* (x1=1, x2=1, x3=1) is nonetheless
jointly inconsistent, because pairwise consistency was checked in isolation
from the third variable. Enforcing consistency at level k only guarantees
that *k*-tuples extend consistently, not that a full solution exists or that
generation can proceed by purely local decisions.

Freuder's positive result is the other half, and it is the genuinely useful
part for us: define the **width** of a constraint graph under a variable
ordering (roughly: for each variable, how many of its already-placed
neighbors constrain it). Then **strong k-consistency, for k strictly greater
than the graph's width, guarantees backtrack-free search** — i.e., there is
an ordering and a consistency level at which purely local, left-to-right
decisions never need to be undone. This is a precise, checkable condition for
exactly the question we care about: **when is it safe to generate a fragment
locally and never have to backtrack because of something elsewhere in the
document?**

### Assume-guarantee / compositional verification

Foundational citations, confirmed via search (not independently re-read
primary text this session — treat as secondhand-but-well-corroborated,
these are canonical, frequently-recapitulated results): **Pnueli, A., "In
Transition from Global to Modular Temporal Reasoning about Programs,"
in *Logic and Models of Concurrent Systems*, NATO ASI Series F13, pp.
123-144, 1984** (the founding assume-guarantee idea: each component assumes
some behavior of its environment and, under that assumption, guarantees its
own behavior); **Clarke, E.M., Long, D.E. & McMillan, K.L., "Compositional
Model Checking," LICS 1989**, pp. 353-362 (made this algorithmic/practical
for model checking). The core idea: to verify a system built from components
M1, M2 satisfies a global property, find an **interface assumption A** such
that (i) M1 satisfies the property *given* A about M2's behavior, and (ii) M2
actually *guarantees* A. Neither component needs the other's full internals
in view — only the interface A.

### Does this transfer? (explicit verdicts)

**GRAMMAR/REGULAR constrained decoding itself: TRANSFERS, and already has
(independently) — this is confirmed prior art, not a new idea.** The REGULAR
constraint's layered-graph GAC algorithm (Pesant 2004) IS constrained
decoding: restrict a sequence of variables (tokens/fields) to those
extendable to an accepting run, invented in CP 20+ years before the LLM
decoding literature reinvented the special case. Whether *our* constrained-
decoding agent already has this citation is out of my scope to check (their
survey, not mine) but it is unambiguously the right citation for that
section, and its cubic-time GRAMMAR generalization is the right citation for
schemas complex enough to need context-free (not just regular) power.

**Joint GRAMMAR/REGULAR + ALLDIFFERENT/GCC propagation: PARTIALLY
TRANSFERS.** Confirmed real, precise, and directly useful for the
**inequality-shaped** slice of our residue (`minItems`/`maxItems`,
`uniqueItems` read as "at most 1 per value") via the regular-counting-
constraints at-most/at-least result — this is a genuine, citable, positive
transfer with a sharp tractability boundary. It does NOT transfer for
**exact-count** constraints (the same paper proves that NP-hard), and it
does NOT transfer as a single off-the-shelf "run this one algorithm"
answer for the fully general case — what exists is single-counter results,
a reduction-based precedent (GSC-to-GCC), and a generic-but-weaker automaton
substrate, not a unified strong algorithm. Report this nuance faithfully
rather than the cleaner story the lead hoped for.

**Freuder's width/backtrack-free-search condition: TRANSFERS AS A DIAGNOSTIC,
which is a genuinely new, concrete, and (as far as I can tell from this
session's searches) unobvious idea worth flagging prominently.** It gives us
something we did not have before this section: a **formal, checkable
condition for exactly the question "is it safe to generate this region
locally?"** Concretely — build the constraint dependency graph of schema S
(nodes = fields/subtrees, edges = any JSON Schema keyword that couples two
nodes: `required` listing a sibling, `uniqueItems` over an array,
cross-field `if`/`then`/`dependentRequired`, etc.). For a candidate
localized region p, the relevant "width" is how many *outside-p* nodes
constrain nodes inside p. Where that width is small (or zero — the common
case for a well-designed form section or an independent table row), local
generation against S@p alone is provably safe in Freuder's sense. Where it
is large (a `required` list spanning the whole object, a global
`uniqueItems` over the whole table), that is a formal proof that no
purely-local scheme (however good the sub-schema projection) can succeed
without also carrying cross-region information — this gives our own
project's "known residue" a rigorous name (**wide dependency edges in the
schema's constraint graph**) instead of just an empirical list of JSON
Schema keywords that happen to be troublesome, and it gives a route to
*computing*, per schema and per candidate split point, whether a given
localization is safe before generation is even attempted.

**Assume-guarantee reasoning: TRANSFERS AS THE RIGHT SHAPE FOR A SOLUTION —
the strongest single conceptual borrow in this whole section, and I agree
with the lead that flagged it, though I want to state precisely what
carries over versus what is a fresh design problem.** What transfers is the
*structure*: don't project S down to "the local sub-schema and nothing else"
(today's candidate architecture, per the shared context) — project it to
**a local sub-schema PLUS an interface assumption A** that the fragment
generator must additionally satisfy, where A encodes exactly the
non-local constraints touching region p (e.g. "must not reuse any of these
N values already used elsewhere in the array," "at least K of these named
sibling fields must end up populated," "this field's value must be
consistent with sibling field X = <value>"). This reframes PROJECT from a
purely syntactic sub-schema extraction into an assume-guarantee interface
derivation, and it composes naturally with the GRAMMAR+GCC result above: a
well-formed interface A of the at-most/at-least shape can be folded directly
into the fragment's automaton/grammar constraint at GENERATE time (tractable,
per the regular-counting-constraints result), while the final revalidation
step is exactly the "guarantee is discharged" check assume-guarantee
requires. What does NOT transfer automatically, and is a genuine research
gap rather than something to borrow ready-made: assume-guarantee's classical
setting has both components' behaviors and the assumption A fixed in advance
by a verifier who can inspect all of M1, M2; ours has to *derive* A
automatically from a JSON Schema for an arbitrary split point p, on the fly,
which is closer to automated interface synthesis / automated compositional
reasoning (a much harder, less settled sub-area — not chased further here,
flagged as the real open problem rather than papered over).

---

## 7. Database updates preserving integrity constraints

### What is a "delta" there

A **transaction**: a bounded sequence of INSERT/UPDATE/DELETE operations,
bracketed by BEGIN and COMMIT/ROLLBACK, that the system treats as a single
unit. This is a different granularity than every other section in this
survey — not a single edit, but a *scope* within which multiple edits may
happen and be provisionally invalid before the scope closes.

### What correctness guarantee, static or dynamic

**Dynamic, and enforced, not merely checked — this is the sharpest
methodological difference from every other section in this file.**
Haerder, T. & Reuter, A., "Principles of Transaction-Oriented Database
Recovery," *ACM Computing Surveys* 15(4):287-317, 1983 (PRIMARY citation
confirmed via ACM record and multiple corroborating listings; this is the
paper that coined **ACID**). Consistency in ACID is defined precisely as
"transactions make only correct changes to the state of resources" (per
search-summary description of the paper, corroborated across multiple
independent sources — treat exact wording as secondhand, the substance as
solid textbook fact) — i.e. the DBMS's central promise already *is* "a
committed state satisfies the declared integrity constraints," enforced
mechanically: a transaction that would leave the constraint violated is
**refused at commit and rolled back**, not merely flagged. This is a runtime
enforcement mechanism with a real undo/abort primitive behind it, not a
static proof.

### The transaction analogy: is "attempt, check, abort" the honest answer?

**Giving this the fair hearing the assignment asked for: largely yes, and
the DB field arrived at exactly this pattern deliberately, with a specific,
well-understood mechanism for controlling WHEN validity must hold — which
maps unusually well onto our multi-fragment / bulk-write case.**

**DEFERRABLE constraints.** SQL standard, implemented in PostgreSQL and
Oracle (PRIMARY, confirmed via PostgreSQL's own documentation,
postgresql.org/docs/current/sql-set-constraints.html, and cross-checked
against a detailed practitioner write-up at begriffs.com/posts/2017-08-27-deferrable-sql-constraints.html).
A constraint declared `DEFERRABLE INITIALLY DEFERRED` is **not checked
per-statement**; it is checked once, at COMMIT. Quote (begriffs.com, direct):
*"Any statement inside a transaction is free to violate constraints. However
at commit time the constraints will be checked, and the transaction will
fail if any constraints do not hold."* This exists precisely because some
valid end-states are **not reachable by any sequence of individually-valid
intermediate states** under immediate checking. The canonical examples,
directly quoted/paraphrased from the same source, are worth listing because
each has a near-exact counterpart in our own problem:

- **Cyclic foreign keys** (table A row references table B row and vice
  versa) — neither row can be inserted first under immediate checking.
  Counterpart: two fragments in different parts of a document that
  reference each other (referential integrity residue, named explicitly in
  the shared context).
- **Swapping unique values** ("swapping teachers without deferring the
  uniqueness constraint on `teacher_id`, we would need to assign a
  temporary teacher to a class") — no single-row UPDATE order avoids a
  transient duplicate. Counterpart: regenerating two elements of a
  `uniqueItems` array so they exchange values, or more generally any
  bulk-table batch (the assignment's own motivating example 2) where a
  batch of 10 rows must jointly satisfy a table-wide uniqueness or
  cardinality constraint that no single row can be checked against in
  isolation.
- **Renumbering an ordered list** (incrementing position numbers creates
  momentary duplicate positions) — direct counterpart to reordering/
  re-indexing array elements under a schema that constrains position or
  sequence.
- **Out-of-order ingestion** (child rows loaded before parent rows exist) —
  counterpart to generating a fragment that references a sibling fragment
  not yet generated.

The mechanism is exactly "generate (here: write) optimistically, defer the
check, validate everything at the end, abort the whole unit if it fails" —
which is precisely the assignment's own candidate architecture's last step
("splice -> revalidate globally"), plus the one thing that architecture is
not explicitly described as having: **an abort/rollback path as a first-class,
expected outcome**, not a failure case bolted on afterward. The DB field's
34+ years of experience with DEFERRABLE constraints is essentially a
worked answer to "how do you let multiple pieces stay temporarily invalid
against each other, on purpose, without giving up the guarantee that the
final state is fully valid" — which is exactly what SPLICE-then-REVALIDATE
needs when GENERATE necessarily works on one fragment at a time.

**The honest limitation of the analogy:** a database's "abort" is close to
free — undo logs / MVCC give you the pre-transaction state back cheaply, so
retrying costs little more than the wasted writes. Our "abort" (reject a
generated fragment and regenerate) costs a fresh model call, which is
orders of magnitude more expensive than a DB rollback. So the pattern
transfers structurally but not in its cost profile — which argues for
front-loading as much validity as GENERATE can cheaply guarantee (constrained
decoding against S@p, and against whatever interface assumption A the
PROJECT step can derive — see section 6) and reserving the transaction-style
abort/retry for the residue that genuinely cannot be checked locally, rather
than leaning on abort/retry as the primary mechanism the way a DB safely can.

### Static analysis of whether an update CAN violate a constraint

This sub-line of the DB literature is a close cousin of section 6's
"local vs. global consistency" material, arrived at independently, and is
worth citing on its own terms because it targets exactly the question "given
I'm only changing region p, what's the minimum I must re-check":

- **Nicolas, J.-M., "Logic for Improving Integrity Checking in Relational
  Data Bases," *Acta Informatica* 18(3):227-253, 1982.** PRIMARY citation
  confirmed (link.springer.com/article/10.1007/BF00263192). Foundational
  result: given a database known to already satisfy a constraint, and a
  specific parameterized update, derive a **simplified form of the
  constraint** — one that refers only to the changed data — sufficient to
  check in the new state whether the *original, full* constraint still
  holds. This is the direct DB-theory analogue of "don't revalidate the
  whole document, derive the minimal check implied by the fact that only
  region p changed and the rest was already known-valid."
- **Christiansen, H. & Martinenghi, D., "On Simplification of Database
  Integrity Constraints," *Fundamenta Informaticae* 71(4):371-417, 2006.**
  Confirmed via search-summary (secondhand — direct fetch of the ACM record
  was blocked, 403). Gives this simplification project a formal ceiling, and
  it is a genuinely sharp, transferable boundary: **"ideality of
  simplification is strictly related to query containment; an ideal
  [sound and complete] simplification procedure can only exist in database
  languages for which query containment is decidable."** In other words,
  "can we always reduce a global revalidation to a cheap local one, without
  ever being wrong" is not free — it is exactly as hard as a specific,
  named decision problem (query containment) in whatever language the
  constraints are written in, and for sufficiently expressive constraint
  languages that problem is undecidable. This is a second, independent
  confirmation (arrived at from a completely different formal direction than
  section 6's CP-complexity results) of the same shape of finding: cheap
  local revalidation is achievable for restricted constraint languages and
  provably not achievable in general — the question is never "can we avoid
  full revalidation" in the abstract, it's "how expressive is S allowed to
  be before we can't."

### Does it transfer?

**PARTIALLY-TO-STRONGLY TRANSFERS, and this is the most directly actionable
engineering pattern found in the whole survey, even though it is the least
novel one.** Three distinct, honest verdicts bundled in this section:

- **The abort/rollback engineering pattern itself: TRANSFERS.** Not a new
  algorithm, but a validated, decades-old operational discipline for exactly
  our GENERATE -> SPLICE -> REVALIDATE shape, including the underused piece
  (deferred checking as a *controlled, intentional* relaxation, not a bug)
  and a direct answer to why "generate fragment against local sub-schema
  only" cannot be the whole story for cross-fragment constraints: those
  constraints are, in DB vocabulary, exactly the ones that must be declared
  DEFERRABLE because no per-statement (per-fragment) check order can satisfy
  them. The honest caveat is cost, not shape: our retries are expensive LLM
  calls, not cheap log-based rollbacks, so this pattern should be the
  fallback net, not the primary mechanism.
- **Constraint simplification (Nicolas; Christiansen & Martinenghi): PARTIALLY
  TRANSFERS**, as a target to aim for rather than a ready-made algorithm —
  their techniques are specific to relational/logic-based query languages,
  not JSON Schema, so nothing here is directly reusable code or algorithm,
  but the theorem shape (simplification-to-local-check exists iff a specific
  decision problem is decidable in your constraint language) is exactly the
  right question to ask of JSON Schema's constraint vocabulary, and
  independently corroborates section 6's finding that tractability of
  "local-suffices" reasoning is real but constraint-language-dependent, not
  universal.
- **ACID "Consistency" as a definition: TRANSFERS as vocabulary, not as
  mechanism** — it is the right word for the property we want
  (schema-validity of the committed/spliced document) and names the
  enforcement-vs-checking distinction cleanly, but the DBMS mechanism behind
  it (write-ahead logs, MVCC snapshots, cheap physical undo) has no
  counterpart in LLM generation and would need to be designed from scratch
  if a true "abort mid-generation" primitive were ever wanted rather than
  "reject and regenerate the whole fragment."

---

## Ranked list: which neighbouring formalism is most worth borrowing from

**This whole section is my judgement, synthesizing sections 1-7 above — not
a claim attributed to any cited source.**

**1. Assume-guarantee / compositional verification (section 6) — take the
SHAPE of the fix, not any algorithm.** The single highest-value idea in this
survey. It says PROJECT is currently under-specified: extracting a syntactic
sub-schema S@p is only half of what a sound decomposition needs. The other
half is an **interface assumption A** — a small, explicit statement of what
the fragment is allowed to assume about the rest of the document (and, by
construction, what the rest of the document must be checked to guarantee).
This reframes the "known residue" (cross-field required, uniqueItems across
batches, cardinality, conditional dependencies, referential integrity) from
an ad hoc list of hard cases into one well-defined missing artifact: nobody
is computing A. Concretely actionable: PROJECT(S, p) should return (S@p, A),
not just S@p.

**2. Freuder's width / backtrack-free-search condition (section 6) — take it
as a pre-flight diagnostic, cheap and immediately usable even before A is
designed.** Build the dependency graph of schema S (edges = any keyword
coupling two nodes across the localisation boundary), and check whether the
width at candidate split point p is small. This is a **static, computable-
today** yes/no answer to "is naive localise-and-generate even safe here,"
independent of whatever generation mechanism is used — the cheapest possible
win from this whole survey, and the one most worth prototyping first because
it requires no change to GENERATE at all, only an analysis pass over S.

**3. CP's regular-counting-constraint tractability boundary (section 6) —
take the specific complexity result, not just the inspiration.** Beldiceanu/
Flener/Pearson/Van Hentenryck's polynomial-for-at-most/at-least,
NP-hard-for-exact result (arXiv:1309.7145) is directly reusable as a design
rule: when the interface assumption A (from #1) is expressible as inequality-
shaped bounds (which `minItems`/`maxItems`/`uniqueItems` naturally are), it
can in principle be folded straight into GENERATE's constrained decoding at
polynomial cost, using the same automaton/layered-graph substrate as REGULAR/
GRAMMAR constrained decoding. When A would require an exact-count guarantee,
this result says up front not to expect a cheap constrained-decoding fix —
route that case to #4 instead, rather than spending effort trying to force
it into the decoder.

**4. Database deferred constraints + transaction abort/retry (section 7) —
take it as the fallback path for whatever #1-3 cannot close, and take it
seriously rather than as an admission of defeat.** For the genuinely
non-local residue (or the exact-count case #3 flags as intractable to
decode around), the field's actual answer, arrived at independently and
validated over decades, is: let GENERATE proceed against S@p (+ A where
available), splice, and check the true global constraint at the end,
aborting/retrying the specific violating fragment if it fails — exactly the
assignment's own candidate architecture's last step, now backed by an
explicit "this is a known-sound pattern with a name" rather than treated as
a fallback of last resort. The one thing to import explicitly, not just
the pattern: **deferred, not immediate, checking is a deliberate design
choice** with named conditions for when it's required (the cyclic-FK /
swap / reorder / out-of-order-ingestion cases in section 7) — worth using
that same taxonomy to decide, per constraint, whether it can be checked
fragment-locally (immediate) or must wait for the full splice (deferred).

**Lower-ranked but real, for different questions than "how do we generate
correctly":**

**5. Tree edit distance, APTED + a JSON-aware/order-agnostic layer, in the
STED style (section 3) — take it for EVALUATION, explicitly not for
generation.** The right tool for measuring "did the system change only what
it should have," with the specific recipe given in section 3 (canonicalize,
then exact TED outside region p should be exactly zero; validate, don't
diff, inside region p). Useful for building the test suite / benchmark for
whatever architecture gets built, not for the architecture itself.

**6. IVM/materialized-view-as-constraint-check (section 4) — take it as a
possible efficiency trick for REVALIDATE only**, if global revalidation ever
becomes a measured bottleneck: encode schema constraints as queries whose
emptiness = validity, and let IVM machinery maintain that emptiness
incrementally rather than re-running full validation after every splice.
Speculative and not chased deeply enough this session to be more than a
"worth a spike" note.

**Not worth borrowing from, confirmed with citations rather than assumed:**
JSON CRDTs (section 1) and Operational Transformation (section 2) — both
solve a materially different problem (convergence of concurrent,
uncoordinated edits with no arbiter) and both are shown, with direct
citation, to have no notion of schema validity at all; delta encoding
(section 5) operates below the structural level we need and offers
vocabulary only.
