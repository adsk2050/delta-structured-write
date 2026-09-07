# C — Empirical Evidence: Can LLMs Emit Correct Partial Output?

Status: IN PROGRESS. Agent C. Started 2026-09-07.

Scope: Evidence on whether LLMs can reliably produce targeted/partial edits
(diffs, patches, fragments) rather than whole-object regeneration. Code-editing
evidence is gathered as TRANSFERRED evidence (labeled), since almost all hard
numbers live there, not in JSON/schema-governed generation. Key asymmetry to
track throughout: JSON Pointer addressing into a schema-known doc is more
constrainable than a source-file line number (legal paths are enumerable),
so code-editing failure rates are a probable UPPER BOUND on difficulty for
our problem, not a direct estimate.

---

## 1. Aider edit-format benchmarks (whole vs diff vs udiff vs diff-fenced)

Source: https://aider.chat/docs/leaderboards/edit.html (Aider "code editing leaderboard", Paul Gauthier / Aider-AI). Fetched via WebFetch (primary source, page summarized by fetch tool — numbers below cross-checked against search snippets, but re-verify exact table cells before final write-up).

**Methodology**: 133 small Exercism Python coding exercises. Model must both solve the exercise AND correctly edit the source file, unaided. Two metrics per model: (a) % exercises completed correctly, (b) % of responses that used the correct/well-formed edit format. Two attempts allowed (2nd gets failing test output). Note: this is the older "133-exercise" Python-only leaderboard; Aider later moved to a harder 225-exercise "polyglot" benchmark (C++/Go/Java/JS/Python/Rust) — see below.

**Selected leaderboard rows (edit.html, historical snapshot reached via fetch)**:
| Model | Correct | Format compliance | Edit format |
|---|---|---|---|
| o1 | 84.2% | 99.2% | diff |
| Claude 3.5 Sonnet (latest, ~2024-10) | 84.2% | 99.2% | diff |
| Gemini Exp-1206 | 80.5% | 100.0% | whole |
| o1-preview | 79.7% | 93.2% | diff |
| Claude 3.5 Sonnet (older, ~2024-06) | 77.4% | 99.2% | diff |
| (tail of table) | as low as 14.3% | — | mixed |

Key qualitative point from Aider's own docs: "whole" format is easiest for the model (lowest cognitive/format burden) but token-expensive and caps file size; diff-family formats are "much more efficient, using far fewer tokens" but historically induce format-compliance failures in weaker models. Aider auto-selects the format per model — it defaults weaker/lesser-known models to "whole" specifically BECAUSE they cannot reliably produce diffs. This is itself evidence: the tool's own routing logic encodes "diff-following is a capability that not all models have."

**GPT-3.5/GPT-4 whole vs diff, from https://aider.chat/docs/benchmarks.html (primary, Aider benchmarks writeup)**:
- GPT-3.5 (0301, Feb 2023) — whole format: 46% success (1st attempt); diff format: 30%. Absolute drop ≈ -16pp, relative drop ≈ -35%.
- GPT-3.5 (0613, June 2023) — whole format: 39%; diff format: 19%. Absolute drop ≈ -20pp, relative drop ≈ -51%.
- So for GPT-3.5-class models, switching whole→diff roughly HALVED the relative success rate in the June model. This is a large, concrete "diff tax."
- Reported failure modes at the diff format specifically: GPT-3.5 would sometimes place the ENTIRE original file in the "ORIGINAL" block and the entire updated file in the "UPDATED" block (i.e., degenerating a diff back into a whole-file emission — evidence the model "wanted" to do whole-file replacement and the diff format was fighting its natural mode). Function-calling variants showed outright hallucinated/invalid JSON, including dumping a whole Python file into a field meant for structured key-value data.
- Methodology note: 133 Exercism Python exercises, 2 attempts (2nd gets failing test output), noted run-to-run variance even at temperature=0 (API non-determinism).

**Unified diff results, from https://aider.chat/docs/unified-diffs.html (primary, "Unified diffs make GPT-4 Turbo 3x less lazy")**:
- This piece is about *laziness* (model eliding code with comments like "# ... rest of code ...") more than raw correctness, but laziness is a partial-output-fidelity failure mode directly relevant to us.
- GPT-4 Turbo (gpt-4-1106-preview): SEARCH/REPLACE format → 20% of 12 "laziness-provoking" tasks showed lazy elision; unified-diff format → only 61%... 

  CORRECTION NEEDED: the fetch summary phrased this ambiguously ("61% with lazy comments" reads like laziness INCREASED). Re-check primary source directly before citing — the aider blog post's actual headline claim is "3x less lazy," i.e. unified diff should REDUCE the lazy rate, not raise it to 61%. Flagging this as UNVERIFIED PENDING RE-FETCH. Do not cite the "61%" figure until confirmed which direction it points.
- GPT-4 (gpt-4-0613): SEARCH/REPLACE baseline 26% vs unified-diff 59% on the (whole-file?) benchmark — again same ambiguity about which metric increased; 28% of files exceeded the 8k context window in one condition, capping achievable score at 72%. RE-VERIFY.
- Reasons Aider's writeup gives for unified diffs working better than SEARCH/REPLACE specifically for GPT-4-class models (this part is qualitative and safe to cite):
  - Unified diff is `git diff`'s native output format → heavily represented in pretraining data (distributional familiarity argument — same argument Cursor makes, see below, but Cursor draws the OPPOSITE conclusion for full-file vs diff; worth flagging as a live disagreement between two credible practitioner sources).
  - Unified diffs avoid JSON/function-call-style escaping overhead.
  - Diff format seems to push the model into a more "mechanical," rule-following completion mode ("writing textual data intended to be read by a program, not talking to a person"), which appears to suppress lazy shortcuts.

ACTION ITEM (for whoever verifies before final synthesis): re-fetch https://aider.chat/docs/unified-diffs.html directly and pull the exact laziness percentages and their direction; the WebFetch summarizer's phrasing was internally inconsistent (says "61%" is the unified-diff result right after saying unified diff caused "3X reduction" — these can't both be lazy-rate-up readings, most likely 61% is a CORRECTNESS or NON-lazy rate, need the actual table).


### Aider unified-diffs.html — corrected after re-fetch

Source: https://aider.chat/docs/unified-diffs.html (primary, re-fetched directly; prose not tabular, results stated in running text, dated ~Dec 2023 per Aider blog cadence — confirm exact byline date before final cite).

Confirmed: the percentages are TASK SUCCESS rates (higher = better), not laziness rates. Laziness is reported separately as a raw task count out of a fixed lazy-prone task set.

- GPT-4 Turbo (gpt-4-1106-preview): SEARCH/REPLACE baseline score 20%. Unified-diff format raised score to 61%. Separately, laziness (elision via "...rest of code..." placeholder comments) dropped 3x: from lazy behavior on 12 tasks down to 4 tasks.
- GPT-4 (gpt-4-0613, June 2023): SEARCH/REPLACE baseline 26% -> unified diff 59%.
- These are bigger jumps than "3x less lazy" alone suggests: the underlying benchmark score roughly TRIPLED for GPT-4 Turbo (20%->61%) and MORE THAN DOUBLED for GPT-4-0613 (26%->59%) when switching SEARCH/REPLACE to unified diff, on Aider's own task set.
- Important caveat in the same page: 28% of files in one condition exceeded GPT-4's 8k context window, which mechanically capped achievable score at 72% -- part of the SEARCH/REPLACE deficit is a context-length artifact of that era's small context windows, not purely format difficulty. Modern frontier models have far larger context windows, so this specific magnitude of gap is expected to shrink for that reason alone, independent of any format-following improvement. Do not over-read 2023-era GPT-4 numbers as timeless.

Qualitative causal claims from Aider's writeup (cite as the AUTHOR'S claim, not independently measured): unified diff outperforms SEARCH/REPLACE because (a) unified diff is git diff's native output format, hence overrepresented in pretraining, (b) it avoids JSON/escaping overhead, (c) it pushes the model into a more "mechanical" completion mode that suppresses laziness/elision shortcuts. NOTE: this is IN TENSION with Cursor's finding (below) that full-file rewrite beats diffs for files under ~400 lines. The two practitioner sources disagree on the direction of the effect, likely because they optimize different regimes (Aider: avoid laziness/elision on medium files with GPT-4-Turbo-era models; Cursor: avoid positional/line-number errors on arbitrary-size files, using a dedicated small apply-model as the actual patch-applier rather than asking the frontier model to emit an exact patch). Flag this tension explicitly in synthesis -- the answer looks regime-dependent, not universal.

---

## 5. JSON Patch / structured-delta generation by LLMs -- FOUND A DIRECT HIT (prediction of absence was wrong)

**"JSON Whisperer: Efficient JSON Editing with LLMs"** -- Sarel Duanis, Asnat Greenstein-Messica, Eliya Habba (Lightricks; Habba also Hebrew University). EMNLP 2025 Industry Track. arXiv:2510.04717 (dated 2025-10-06). Also at aclanthology.org/2025.emnlp-industry.88.pdf. Fetched primary (arxiv HTML v1).

THIS IS THE PAPER -- a direct empirical study of LLMs emitting RFC 6902 JSON Patch vs full JSON regeneration.

**Task/dataset**: ~400 examples, JSON "scenes" from a film-production-platform domain, generated using Claude Sonnet. Four complexity tiers: Simple (single field change), Creative (new content generation), Complex (multiple related element modifications), List Manipulation (reordering/filtering).

**Models tested**: Claude Sonnet and GPT-4o-mini. Zero-shot and DSPy-optimized few-shot prompting compared.

**Headline result**: "patch generation with EASE reduces token usage by 31% while maintaining edit quality within 5% of full regeneration." I.e. patches are NOT more accurate than full regeneration -- roughly as accurate (within 5%) while cheaper/faster. This is a direct, if soft, answer to item 6 (does smaller output help accuracy): for naive RFC 6902 patch generation, smaller output =~ same accuracy, not better accuracy, unless array-addressing is also fixed (EASE, below).

**Token counts (their Table 1, per request)**:
| Model | Condition | Input tok | Output tok |
|---|---|---|---|
| Claude Sonnet | Full regen | 918 | 918 |
| Claude Sonnet | Diff/patch | 1,890 | 529 |
| GPT-4o-mini | Full regen | 677 | 677 |
| GPT-4o-mini | Diff/patch | 1,500 | 464 |

Shape to note: patch mode roughly DOUBLES/TRIPLES input tokens (must show current doc + instructions to compute the diff against) while cutting output tokens ~40-45%. Relevant to item 7 (net economics): if input tokens are cheap/cacheable and output tokens are the expensive/serial/uncacheable ones (our project's framing), this trade is a clear net win on latency and $ even though TOTAL token count can go up. Net dollar cost: Claude $13.80/1000 req (full) vs $7.94/1000 (diff) = -42.5%; GPT-4o-mini $0.41 (full) vs $0.28 (diff) = -31.7%. Latency: Claude 11.62s (full) vs 6.70s (diff) = -42.3%; GPT-4o-mini 8.26s (full) vs 5.66s (diff) = -31.5%.

**EASE method** (the paper's contribution -- "Explicitly Addressed Sequence Encoding"): central finding is that raw RFC 6902 JSON Patch against array-indexed JSON is exactly where LLMs struggle, and it is fixable by a REPRESENTATION change, not a model/training change:
- Problem: JSON Patch ops addressing array elements by numeric index require index arithmetic -- after op N shifts array positions, op N+1's index must account for the shift. "LLMs struggle with array index arithmetic... frequently miscalculate these shifts or conflate zero-based and one-based indexing."
- Fix: EASE transforms arrays into key-value maps with stable short identifiers (e.g. "ax", "cd") plus a separate "display_order" field encoding sequence as a string (e.g. "ab,cd,ef"). Every patch op then addresses a STABLE KEY instead of a POSITION, making operations order-invariant -- earlier deletes/inserts in the same patch no longer perturb later operations' addresses.
- Result: "EASE encoding consistently outperforms standard list indexing across all instruction categories, with the most pronounced improvements in complex instructions and list manipulations" (exact delta-accuracy numbers not captured in this fetch pass -- see action item).

**Failure modes documented (useful for our "known residue" list)**:
1. Missed related updates across siblings: "When editing a character's attributes across multiple scenes, models generating patches often update some occurrences while overlooking others" -- cross-fragment referential consistency (a "known residue" our brief already names) is empirically confirmed as an observed failure mode, not just a theoretical worry.
2. Array index arithmetic failures: index shift miscalculation and 0-vs-1-based confusion (illustrated with a removal-then-reference example in their Figure 1).

ACTION ITEM: exact EASE-vs-raw-index accuracy delta numbers (Figure 3 / per-tier accuracy table) were not captured verbatim in this pass -- fetch summarized qualitatively. Re-fetch arxiv 2510.04717 (or the EMNLP PDF) specifically for the Figure 3 numeric deltas if time remains.

**This overturns our item-5 negative-result prior**: it is NOT true that "there is little or nothing." At least one direct, peer-reviewed (EMNLP 2025 industry track), primary-source, numeric benchmark of LLMs emitting RFC 6902 JSON Patch exists. It is recent (Oct 2025) and domain-specific (film-production JSON), small (~400 examples, 2 models), industry-track (Lightricks) -- cite as "one direct study exists, is recent and narrow, cross-domain generalizability unverified," not as "well-established." The initial hypothesis that this space is empty should NOT be asserted in the final synthesis without this correction.

## 5b. PatchOptic -- closely related prior work, WITH strong positive numbers (flag for whole-project relevance, not just item 5)

**"PatchOptic for Shared-State LLM Workflows with Projected Views and Verified Structured Updates"** -- Zhaoyu Bai, Jiaqi Cai. arXiv:2607.05483v1, submitted 2026-07-06 ("24 pages, 13 figures, including appendix"). Fetched primary (arxiv HTML v1; PDF direct fetch failed due to binary/stream encoding, HTML version worked).

**IMPORTANT FLAG FOR SYNTHESIS**: this paper's architecture is extremely close to our project's candidate architecture (LOCALISE -> PROJECT sub-schema -> GENERATE fragment -> SPLICE -> revalidate globally). PatchOptic frames it as "optics" (bidirectional accessors / lens pattern from functional programming): each workflow step declares a projected READ view, an authorized WRITE region, and a patch-source region; a runtime verifier checks the declared contract before commit. This is aimed at multi-step AGENTIC workflows over shared state (not specifically single-shot schema-governed JSON/form editing), so it is adjacent, not identical, to our scope -- but it is close enough that the final synthesis should treat this as a serious existing-solution candidate for the "(a) already solved" branch of our verdict question, at least for the agentic-workflow variant of the problem. NOTE also explicitly OUT OF SCOPE overlap risk: our brief excludes "agent memory/state" from scope, and PatchOptic is precisely about shared agentic workflow state -- so it sits just outside our stated scope boundary, but its RESULTS (below) are still the best direct empirical evidence anywhere in this research pass for "does localizing generation to a projected sub-view help correctness," so I'm including it as evidence, flagged clearly.

**PatchBench**: their benchmark, 46 cases across multiple domains (one domain example surfaced: medical/clinical records -- "medical_L2_copy_rationale_to_summary" case). Strong actor = GPT-5-mini; weak actor = local Mistral 7B at temperature=0.

**Headline live-run numbers (their Table 5, "Unconstrained" baseline = full-context/no-projection vs "PatchOptic" = projected-view + verified-patch condition)**:

| Metric | Actor | Unconstrained | PatchOptic | Delta |
|---|---|---|---|---|
| Semantic pass rate | GPT-5-mini (strong) | 0.609 +/- 0.041 | 0.779 +/- 0.032 | +17.0pp |
| Content/quality score | GPT-5-mini (strong) | 0.925 +/- 0.020 | 0.927 +/- 0.032 | ~flat (preserved) |
| Leak rate (exposure of protected/hidden fields) | GPT-5-mini (strong) | 0.315 +/- 0.021 | 0.002 +/- 0.007 | -31.3pp |
| Mean tokens | GPT-5-mini (strong) | 817.5 +/- 5.4 | 718.6 +/- 3.2 | -12.1% |
| Semantic pass rate | Mistral 7B local (weak) | 0.560 | 0.690 | +13.0pp |
| Leak rate | Mistral 7B local (weak) | 0.239 | 0.000 | -23.9pp |
| Mean tokens | Mistral 7B local (weak) | 986.2 | 829.3 | -15.9% |

**This is the single strongest piece of evidence found in this whole research pass that localizing/projecting generation IMPROVES correctness rather than merely preserving it**: semantic pass rate rose ~17 points for the strong actor and ~13 points for the weak actor when moving from full-context unconstrained generation to a projected-view + verified-patch condition, while token cost simultaneously fell (~12-16%) and leakage of protected content collapsed to near zero. Content/quality score was flat (preserved, not traded away). Caveat: this is ONE paper, ONE benchmark (46 cases, expanded via repeated live runs -- "5,520 live runs" mentioned for the GPT-5-mini/PatchOptic leak-rate condition, so the per-condition N is much larger than 46 via resampling), ONE research group, arXiv preprint dated July 2026 (very recent, not yet clearly peer-reviewed/published at a venue as far as this fetch could tell -- CONFIRM peer-review status before citing as established). Domain is agentic shared-state workflows (e.g., medical records), not schema-governed form/table editing specifically.

**Runtime verification blocking rate**: "Settings without phase/scope verifier checks produce 2.2-3.1 unsafe accepts per round, while settings with phase/scope verifier checks produce none" (Table 6) -- i.e., in their harness, adding the runtime contract-verification step reduced unsafe accepts from 2-3 per round to zero.

**Patch-source enforcement / adversarial rejection**: "Verify Only and PatchOptic reject all nine such [compromised patch] artifacts with the implementation diagnostic patch_read_scope_violation" -- 9/9 adversarial artifacts using hidden/unauthorized sources were caught.

**Residual failure mode (directly relevant to our "known residue" list)**: even under PatchOptic's projection, ONE leak case survived: "medical_L2_copy_rationale_to_summary. In that case, the actor introduced a clinical differential term that matched the protected internal differential even though the projected view hid that field." This is 1 case out of 5,520 live runs (0.2% residual leak rate) -- and it is a NEW failure mode not on our brief's original "known residue" list: the model INFERRED/reconstructed hidden content through reasoning rather than copying it verbatim, so hiding a field from the projected view does not guarantee the model cannot reproduce semantically-equivalent content if it can infer it from what IS visible. Worth adding to the project's residue list: "semantic inference of hidden-field content from visible context, even when the field itself is correctly excluded from the projection."

ACTION ITEM: verify publication venue/peer-review status of PatchOptic before final synthesis cites it as more than an arXiv preprint; it is very recent (July 2026) and I could not confirm a venue.

---

## OpenAI apply_patch -- V4A format, confirmed rationale

Source: multiple secondary sources (OpenAI's own developers.openai.com/api/docs/guides/tools-apply-patch page gave format/grammar but explicitly NO stated rationale when fetched directly -- see below; rationale below is from secondary blog/community sources describing the V4A format, treat as SECONDHAND unless noted).

- Format name: "V4A diff format" (OpenAI's own term, used in Codex CLI / apply_patch tool). Grammar: patches are file-oriented, delimited by `*** Update File:`/`*** Add File:`/`*** Delete File:` markers, with `@@` hunk anchors and unified-diff-style `+`/`-`/context lines -- but CONTEXT-ANCHORED rather than line-number-anchored: "lines prefixed with a single space are 'context' lines that are not changed but are used to locate the position of the patch" (secondhand, multiple sources agree on this description).
- STATED RATIONALE (secondhand, consistent across sources, not found verbatim on OpenAI's own primary docs page in this fetch pass): context-matching instead of line numbers is deliberate because "file contents may change between when a model generates a patch and when it's applied, making static line numbers unreliable... patches remain valid even if the file has been modified since the model analyzed it." This is the SAME direction of design choice as Anthropic's str_replace (below): both frontier labs converged on STRING/CONTEXT matching over POSITIONAL (line-number) addressing for their production edit tools. Given our brief's framing ("the choices of the people with the most data are evidence"), this is a significant converged signal: two independent frontier labs, building production tools used by millions of real agent sessions, both rejected line-number addressing in favor of content-anchored matching.
- Primary OpenAI docs page (developers.openai.com/api/docs/guides/tools-apply-patch) fetched directly: confirms apply_patch "lets [models] create, update, and delete files in your codebase using structured diffs" and that "the patch language is a stripped-down, file-oriented diff format designed to be easy to parse and safe to apply" -- but the page as fetched gave NO explicit accuracy/reliability numbers and NO explicit line-numbers-vs-context rationale sentence; it points to reference implementations (openai-agents-python / openai-agents-js repos) as the authoritative grammar source rather than spelling out the grammar in prose. ACTION ITEM: if precise grammar needed, pull the actual grammar/parser from the openai-agents-python or openai/codex GitHub repos (codex-rs/core/prompt_with_apply_patch_instructions.md was surfaced by search and looks like the actual prompt-level spec given to the model -- worth a direct fetch if more precision is needed later).

## Anthropic text editor tool -- confirmed primary-source details (fetched directly, platform.claude.com)

- Tool name: `str_replace_based_edit_tool`. Commands: `view` (read file/dir, optional `view_range` line range), `str_replace` (old_str/new_str exact string match), `create` (whole-file write), `insert` (insert_text after insert_line).
- CONFIRMED DESIGN CHOICE: `str_replace` requires old_str to match EXACTLY ONE location in the file. This is explicit, primary-sourced: "Successfully replaced text at exactly one location" is the success message; documented error cases are "Error: Found 3 matches for replacement text. Please provide more context to make a unique match" (multiple-match case) and "Error: No match found for replacement" (zero-match case). This is a hard uniqueness constraint enforced by the harness, not a soft preference -- i.e., Anthropic's own production tool treats "old_str matched more than once" as a HARD FAILURE requiring the model to retry with more context, not a silent pick-first-match. This is strong evidence that exact-string addressing has a real, commonly-hit failure mode (ambiguous match) that needed explicit error-and-retry handling in the product.
- No `view_range`/positional addressing is used for the actual EDIT (only for the read-side `view` command and `insert`'s insert_line); the WRITE side (`str_replace`) is 100% content-addressed, never line-number-addressed. This directly supports item 4's framing: even where Anthropic's tool exposes line numbers at all (for `view`/`insert`), it deliberately does NOT let the model address the thing it's OVERWRITING by line number -- only by exact string match. Insert (add-only, not overwrite) is the one command that is line-number addressed, arguably because getting an insert point off-by-one is lower-stakes (worst case: misplaced new content, still inspectable) than getting a replacement off-by-one (worst case: silently deletes/corrupts the wrong span).
- Version history (change log, primary-sourced table): `text_editor_20241022` (2024-10-22, Claude Sonnet 3.5, included `undo_edit`) -> `text_editor_20250124` (2025-01-24/03-13, Sonnet 3.7, same capabilities) -> `text_editor_20250429` (2025-04-29, Claude 4, REMOVED `undo_edit`, renamed around str_replace-based architecture) -> `text_editor_20250728` (2025-07-28, adds optional `max_characters` truncation param). Notably the tool DROPPED `undo_edit` at the Claude-4 generation -- worth noting as a (unexplained in the docs) simplification of the command surface over time, not an expansion.
- Pricing note: text_editor_20250429 costs an extra 700 input tokens per request as tool-definition overhead (primary-sourced pricing table) -- small but non-zero fixed overhead for using the structured edit tool at all, relevant context for item 7's net-economics accounting.
- Best-practice guidance in the docs explicitly tells INTEGRATORS to implement the uniqueness check themselves ("Handle unique text replacement carefully... ensure that there is exactly one match") with sample code for counting matches -- i.e. Anthropic pushes responsibility for detecting the ambiguous-match failure mode onto the calling application, not onto the model itself. There is no claimed numeric error rate for how often Claude's str_replace calls fail uniqueness or no-match in practice; this remains UNQUANTIFIED in Anthropic's own docs (a gap -- searched but did not find a published ambiguous-match/no-match rate for str_replace_based_edit_tool specifically).

---

## 4. Positional addressing error rates -- STRONG direct quantified evidence found

**"To Diff or Not to Diff? Structure-Aware and Adaptive Output Formats for Efficient LLM-based Code Editing"** -- Wei Cheng, Yongchang Cao, Chen Shen, Binhua Li, Jue Chen, Yongbin Li, Wei Hu. arXiv:2604.27296, submitted 2026-04-30. Fetched primary (arxiv HTML). This is the single best controlled, quantified, RECENT (2026) comparison of addressing schemes found in this entire research pass.

**Full abstract (verbatim)**: "Large Language Models (LLMs) are increasingly used for code editing, yet the prevalent full-code generation paradigm suffers from severe efficiency bottlenecks, posing challenges for interactive coding assistants that demand low latency and cost. Despite the predominant focus on scaling model capabilities, the edit format itself has been largely overlooked in model training. In this paper, we begin with a systematic study of conventional diff formats and reveal that fragile offsets and fragmented hunks make generation highly unnatural for LLMs. To address it, we introduce BlockDiff and FuncDiff, two structure-aware diff formats that represent changes as block-level rewrites of syntactically coherent units such as control structures and functions. Furthermore, we propose AdaEdit, a general adaptive edit strategy that trains LLMs to dynamically choose the most token-efficient format between a given diff format and full code. Extensive experiments demonstrate that AdaEdit paired with structure-aware diff formats consistently matches the accuracy of full-code generation, while reducing both latency and cost by over 30% on long-code editing tasks."

**Main accuracy table (their Table 1, model = Qwen2.5-Coder-7B, pass@1 %, averaged across EditEval / CanItEdit / HumanEvalFix / Aider-1 / Aider-2)**:

| Format | Addressing scheme | Average pass@1 |
|---|---|---|
| Base model (no edit format, i.e. no fine-tune) | -- | 48.70 |
| **FullCode** (whole-file regen) | none (baseline) | **57.07** |
| MinUniDiff | line-number indexed, minimal | **14.07** |
| UniDiff | line-number indexed (even with line numbers given in the input) | 33.15 (this fetch; a second figure of "37.66% avg" for a numbered-input variant was also reported in the same pass -- both numbers describe line-number-indexed formats performing far below FullCode; use whichever exact sub-variant is being compared, but the DIRECTION and MAGNITUDE -- a 20-43 point collapse from line-number addressing -- is the load-bearing finding) |
| ContentDiff | content/context-addressed (conceptually same family as str_replace / apply_patch context matching) | 54.43 |
| BlockDiff | structure-aware, syntactic-unit block addressing | 55.98 |
| BlockDiff + AdaEdit | structure-aware + adaptive full/diff selection | 57.61 |
| FuncDiff | structure-aware, function-level block addressing | 57.32 |
| FuncDiff + AdaEdit | structure-aware + adaptive selection | **57.95** (best overall, slightly beats FullCode) |

**This is the cleanest available quantified answer to item 4 and a major input to item 6.** Holding model and tasks fixed, only the ADDRESSING SCHEME varies:
- Line-number addressing (MinUniDiff/UniDiff): catastrophic, 14-33% avg pass@1, a 24-43 point absolute collapse vs FullCode's 57.07%. The paper's own diagnosis, direct quote: "LLMs struggle to generate precise line numbers and offsets, and this issue persists even when the input code is explicitly numbered" -- i.e. giving the model numbered input does NOT fix the problem, so this is not merely an input-formatting fix, it looks like a more fundamental generation-side weakness at producing correct numeric offsets.
- Content/context addressing (ContentDiff): 54.43%, closes most (but not all) of the gap to FullCode -- only a ~2.6pp residual gap. Their diagnosis of the RESIDUAL gap: "fragmented hunks break the syntactic integrity of code" and "generating such disjointed snippets is fundamentally unnatural" for LLMs -- i.e. even content-addressed diffs still fragment code into fragments that cross syntactic boundaries, which itself costs a little accuracy.
- Structure-aware addressing (BlockDiff/FuncDiff, i.e. address by syntactic UNIT such as "this function" rather than by line range or bare string context): FULLY closes the gap and slightly exceeds FullCode (57.3-58.0% vs 57.07%), especially once paired with AdaEdit's adaptive full-vs-diff format selection.
- **Direct analogy to our project**: line-number addressing is analogous to a raw array-index/offset-based patch address; content/string addressing is analogous to Anthropic's str_replace and OpenAI's apply_patch; structure-aware/unit addressing is analogous to exactly our proposed JSON Pointer / schema-path addressing (`/responses/2/answer` names a SCHEMA-DEFINED UNIT, not a byte offset or raw line count). If the ordering (line-number worst, content-match better, structural-unit best) generalizes, it is a strong a-priori argument FOR our project's JSON-Pointer-into-known-schema approach specifically, and is direct evidence for the brief's own stated "key asymmetry" hypothesis (JSON Pointer into a schema-known doc is more constrainable than a source-file line number) -- this paper is the closest thing found to an actual controlled test of that asymmetry, albeit still in the code domain (transferred evidence, not native JSON/schema evidence).

**Efficiency number (their Table 3, long-code subset, CanItEdit problems >300 tokens, n=80)**: FullCode 39.75% pass@1 at 648.30 tokens vs FuncDiff+AdaEdit 40.69% pass@1 at 481.63 tokens -- i.e. accuracy slightly UP (not just flat) while tokens down ~26%. This is a second independent paper (after JSON Whisperer) finding that a well-designed partial-output format can match or slightly beat full regeneration on accuracy while cutting tokens substantially -- accumulating evidence for a real, if modest, "smaller-output-helps" effect PROVIDED the addressing scheme is well-matched to the document's structure.

**AdaEdit's own routing accuracy**: >90% accuracy picking the cheaper-but-sufficient format (diff vs full) per instance, "95%+ when allowing 20% token deviation" (their Figure 6) -- relevant as a proxy for our project's own "when do we localize vs regenerate whole" routing decision; suggests that decision is itself learnable to high accuracy, not a fundamentally hard problem.

**Secondhand corroboration (Medium blog post by Suraj Potnuru, "Context Over Line Numbers: A Robust Way to Apply LLM Code Diffs", and unnamed academic sources surfaced in search snippets, not independently fetched/verified primary -- treat as color, not as a separate data point)**: "LLMs often generate diffs with incorrect hunk header line numbers, where the modified lines are correct but the headers (@@ -old,+new @@) don't align with the source file... one principal cause of mistakes in both GPT-3.5 and GPT-4 was line numbering. The models often consider the start of the code to be after the function definition, and sometimes the line number counting is inconsistent within the model's own answer." Practical mitigation described (secondhand): don't trust hunk headers at all, match on context and adjust offsets programmatically as hunks are applied, plus a "deterministic patch correction algorithm... using a minimal edit distance heuristic instead of relying on the LLM to self-correct trivial alignment errors." This mitigation pattern (cheap deterministic reconciliation of an approximate model output) is the SAME pattern as the fast-apply models in item 2 -- another instance of "don't ask the generator to be exactly right about position; ask a cheap mechanism to reconcile."

---

## Benchmark-validity caveat that affects how to read EVERY code-editing number above

**"Edit, But Verify: An Empirical Audit of Instructed Code-Editing Benchmarks"** -- arXiv:2604.05100, submitted ~2026-04. Fetched primary (arxiv HTML). Audits CanItEdit and EDIT-Bench (an EDIT-Bench sourced from Copilot Arena, 108 core problems, Python + JS).

**Central relevant finding for us**: "EDIT-Bench exhibits low test coverage with 59% of low-coverage suites unable to detect modifications outside edit regions." I.e., in the majority of low-coverage cases, THE BENCHMARK'S OWN TEST SUITE CANNOT TELL whether the model corrupted code outside the region it was supposed to touch. This is exactly the "silent corruption of untouched regions" failure our project brief names as a top-level cost of full regeneration -- and this audit says existing code-editing benchmarks are frequently unable to detect it even when it happens. Practical implication: published pass@1 numbers for diff-style editing (including some cited above) likely OVERSTATE real correctness, because a model that both (a) makes the requested edit and (b) silently breaks something adjacent can still pass the test suite in a large fraction of cases. This is a load-bearing caveat for the whole literature review, not just this file -- recommend flagging prominently in synthesis.

Other findings from the same audit (context, lower priority for us): both benchmarks skew hard towards Python (CanItEdit 105/105 Python; EDIT-Bench 89.8% Python, 10.2% JS, 0% TypeScript/Java/C#/Go/Rust) and toward "algorithm design" / AI-ML tasks relative to real-world PR distributions (CanItEdit 68.6% algorithm-design tasks vs ~18% real-world share; EDIT-Bench 36.1% AI/ML vs ~7% real-world share); documentation/testing/build/maintenance edits are 0% represented in both despite being 31.4% of real human PRs. Of 15 EDIT-Bench problems unsolved by all 40 models tested, 11 (73%) were traced to benchmark artifacts (bad tests, infra bugs, impossible assertions) rather than genuine model incapacity -- a reminder that "0% pass rate" headlines in this literature can be benchmark bugs, not model limits. A prior citation within this audit (Liu et al., 2023, EvalPlus-style test augmentation on HumanEval) found that adding rigorous tests LOWERED measured pass@k by 19.3-28.9 percentage points versus the original under-tested benchmark -- direct precedent for "better test coverage reveals substantially worse true accuracy than originally reported," reinforcing the same caveat.

---

## 8. Training models to emit edits (partial progress, Coeditor)

**Coeditor: Leveraging Repo-level Diffs for Code Auto-editing** -- Jiayi Wei, Greg Durrett, Isil Dillig (UT Austin). ICLR 2024 Spotlight. arXiv:2305.18584. Fetched primary (arxiv abstract page).

**Abstract point**: motivates the work by noting "most prior work on generative models for code focuses solely on creating new code, overlooking the distinctive needs of editing existing code" -- i.e. as of 2023, base code models were not trained on the editing distribution at all, only the generation distribution; Coeditor is trained specifically on repo-level diffs (1650 open-source Python projects) using a line-diff format plus static-analysis-derived context, to close that gap.

**Numeric result (single-round setting)**: exact-match accuracy 34.7% (GPT-3.5 / existing open code-completion baselines) -> 60.4% (Coeditor, fine-tuned specifically for repo-level diff editing). Absolute gain +25.7pp, relative gain +74%. This is a big, direct, primary-sourced data point for item 8's central question ("does training close the gap"): yes, substantially -- but only WITH dedicated fine-tuning on the edit distribution; prompting a general-purpose model to emit diffs (zero/few-shot) is not the same regime as a model actually trained to do so, and the gap between those regimes here is large (+25.7pp exact match).

SECONDHAND (from an earlier WebSearch AI summary, not yet independently re-verified against the primary abstract/paper text in this pass -- flag as needing confirmation before citing as certain): "Coeditor automates editing 46.7% of the changed lines, saving the user 28.6% of keystrokes measured by an edit distance metric." This is commonly repeated as Coeditor's headline result; likely accurate (matches the paper's known framing as an IDE-autocomplete-style auto-editing tool) but ACTION ITEM: verify against full paper text (not just abstract) before final citation, since abstract fetch did not surface this exact figure.

**Multi-round**: abstract states Coeditor gets "substantial gains by iteratively conditioning on additional user edits" but does not quantify this in the abstract itself -- ACTION ITEM if precision needed: pull the multi-round numbers from the paper body/tables, not just abstract.

---

## 2b. EfficientEdit -- academic fast-apply analogue (speculative decoding for edits)

**"EfficientEdit: Accelerating Code Editing via Edit-Oriented Speculative Decoding"** (also referenced under a "Reuse or Generate?" working title in one secondary listing) -- ASE 2025 Research Papers track. arXiv:2506.02780. Found via search, not yet primary-fetched in full (only search-snippet level in this pass -- ACTION ITEM: primary-fetch arxiv.org/abs/2506.02780 if more precision is needed).

**Reported numbers (secondhand, from search snippets of what appears to be the paper's own claims, not independently verified against primary text yet)**: speedups up to 10.38x on CanItEdit and 13.09x on "CodeIF-Bench" versus standard autoregressive decoding; "up to 90.6% higher speedup" than a baseline called FastFixer; up to 8x speedup on Qwen2.5-Coder-32B-Instruct and ~13x on DeepSeek-Coder-33B-Instruct. Central quality claim: "maintains or even improves Pass@1 quality compared to autoregressive decoding" -- i.e. another data point where a mechanism specialized for the EDIT distribution (here: speculative decoding using the original code as a draft, verified/corrected dynamically) does not trade quality for speed, similar in spirit to Cursor's/Morph's commercial fast-apply models but from academic literature with a published venue (ASE 2025) rather than a company blog. This strengthens item 2's overall pattern: multiple independent groups (Cursor, Morph, and now EfficientEdit's academic authors) converge on "decouple WHAT changes (frontier model, imprecise ok) from HOW it's mechanically applied (cheap/fast specialized mechanism, precision-critical)" as the working solution, rather than asking one model to both decide and precisely emit the change in one pass.
