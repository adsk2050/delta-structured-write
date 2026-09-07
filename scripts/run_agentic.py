"""Run the agentic-loop experiment.

  uv run python scripts/run_agentic.py --offline    # no API calls; asserts the invariants
  uv run python scripts/run_agentic.py --dry-run    # the growth curve and the bill
  uv run python scripts/run_agentic.py --size small --turns 20
  uv run python scripts/analyse_agentic.py

The independent variable is the accumulating transcript, so `--turns` is the one
number that must not be cut for budget: the effect being looked for is defined
to appear late. See notes/05-what-the-experiments-did-not-test.md.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw.agentic import ARMS, edit_applied, make_edit, run
from dsw.config import FREE_TIER_RPD, MODEL, RUNS_DIR
from dsw.dossier import DOSSIER_SIZES, DecodableBlock, DecodableDossier, make_dossier
from dsw.dossier_rules import check_dossier, walk_blocks
from dsw.metrics import integrity_outside
from dsw.projection import project
from dsw.providers import get_provider
from dsw.splice import get_at, splice

# Paid rates for the pinned model, introductory tier through 2026-12-31.
RATE_IN, RATE_OUT = 0.75, 3.75


def _doc_tokens(size: str, seed: int = 0) -> int:
    return len(make_dossier(DOSSIER_SIZES[size], seed=seed).model_dump_json()) // 4


def estimate(sizes, seeds: int, turns: int, arms, max_history: int | None) -> None:
    """The growth curve, and the bill it implies.

    Worth reading rather than skipping: the quadratic input term is not an
    accounting nuisance here, it is the mechanism the experiment is testing.
    The whole arm pays it and the fragment arm does not.
    """
    print(f"{'size':<8}{'arm':<10}{'turns':>6}{'in tokens':>13}{'out tokens':>12}"
          f"{'final ctx':>11}{'calls':>7}")
    tot_in = tot_out = calls = 0
    for size in sizes:
        doc = _doc_tokens(size)
        for arm in arms:
            per_turn_out = doc if arm == "whole" else max(doc // 40, 150)
            in_tok = out_tok = 0
            ctx = 0
            INSTRUCTION = 70      # a remembered user turn is the instruction only
            for t in range(turns):
                kept = t if max_history is None else min(t, max_history)
                # The current dossier is injected fresh each turn; a remembered
                # turn contributes its instruction plus that turn's output. So
                # the whole arm's history grows by a document per turn and the
                # fragment arm's by one block. That gap is the experiment.
                ctx = doc + 300 + kept * (INSTRUCTION + per_turn_out)
                in_tok += ctx
                out_tok += per_turn_out
            n = seeds * turns
            tot_in += in_tok * seeds
            tot_out += out_tok * seeds
            calls += n
            print(f"{size:<8}{arm:<10}{turns:>6}{in_tok * seeds:>13,}"
                  f"{out_tok * seeds:>12,}{ctx:>11,}{n:>7}")

    cost = tot_in / 1e6 * RATE_IN + tot_out / 1e6 * RATE_OUT
    days = -(-calls // FREE_TIER_RPD)
    print(f"\n  {calls} calls, {tot_in:,} in / {tot_out:,} out")
    print(f"  paid:  ~${cost:.2f} on {MODEL}  (~${cost / 2:.2f} batched)")
    print(f"  free:  {FREE_TIER_RPD} req/day/model -> "
          + ("fits one day" if calls <= FREE_TIER_RPD else f"{days} days"))
    if max_history is None:
        print("  note:  the whole arm's input term is quadratic in turns. That is "
              "the\n         mechanism under test, not an accounting artifact.")


def offline_check(sizes, seeds: int, turns: int) -> None:
    """Assert everything that does not need the API."""
    checks = 0
    for size in sizes:
        for seed in range(seeds):
            doc = make_dossier(DOSSIER_SIZES[size], seed=seed)
            assert not check_dossier(doc), (
                f"{size}/{seed}: a fresh dossier must satisfy every rule, got "
                + "; ".join(v.message for v in check_dossier(doc)[:3])
            )
            blocks = list(walk_blocks(doc))
            assert blocks, "no blocks"

            kinds = {b.kind for _, b in blocks}
            assert kinds == {"narrative", "table", "finding"}, (
                f"{size}/{seed}: all three block kinds must occur, got {kinds}"
            )

            for turn in range(1, turns + 1):
                edit = make_edit(doc, turn, seed=seed)
                # The path must address a real block, and projecting it must
                # yield the block schema rather than a wrapper.
                node = get_at(doc.model_dump(mode="json"), edit.path)
                assert node["block_id"] == edit.block_id
                assert project(DecodableDossier, edit.path) is DecodableBlock, (
                    "a block path must project to DecodableBlock"
                )
                # An identity splice disturbs nothing outside its own subtree.
                r = splice(doc, edit.path, node)
                assert r.ok and r.document is not None, r.error
                assert integrity_outside(doc, r.document, (edit.path,)).perfect
                checks += 1

            # A correct escalation satisfies the edit; an incomplete one does not.
            esc = next((make_edit(doc, t, seed=seed) for t in range(1, turns + 1)
                        if make_edit(doc, t, seed=seed).kind == "escalate"), None)
            if esc is not None:
                node = get_at(doc.model_dump(mode="json"), esc.path)
                good = {**node, "severity": "critical",
                        "citations": (node["citations"] * 2)[:2] or
                                     [{"source_id": doc.sources[0].source_id,
                                       "locator": "§1.1", "quote": "q"}] * 2,
                        "remediation": "Assign an owner and re-test."}
                assert edit_applied(splice(doc, esc.path, good).document, esc)
                bad = {**good, "remediation": None}
                assert not edit_applied(splice(doc, esc.path, bad).document, esc)

            # D4 really is global and really is unlocalisable.
            dup = doc.model_dump(mode="json")
            dup["sections"][0]["blocks"][0]["block_id"] = \
                dup["sections"][0]["blocks"][1]["block_id"]
            d4 = [v for v in check_dossier(DecodableDossier.model_validate(dup))
                  if v.rule == "D4"]
            assert d4, "duplicating a block_id must raise D4"
            assert not d4[0].repair_paths, "D4 must be unlocalisable"

            # D2 fires when a citation names a source that is not declared.
            ref = doc.model_dump(mode="json")
            for _, b in walk_blocks(DecodableDossier.model_validate(ref)):
                if b.citations:
                    break
            ref["sections"][0]["blocks"][0]["citations"] = [
                {"source_id": "SRC-999", "locator": "§1.1", "quote": "q"}
            ]
            ref["sections"][0]["blocks"][0]["kind"] = "narrative"
            ref["sections"][0]["blocks"][0]["text"] = "t"
            for f in ("caption", "columns", "rows", "severity", "statement",
                      "remediation"):
                ref["sections"][0]["blocks"][0][f] = None
            d2 = [v for v in check_dossier(DecodableDossier.model_validate(ref))
                  if v.rule == "D2"]
            assert d2, "an undeclared source_id must raise D2"
            assert d2[0].repair_paths, "D2 must be localisable to its block"

    print(f"offline: OK  ({checks} edit/splice invariants across "
          f"{len(sizes) * seeds} dossiers)")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["small"],
                    choices=list(DOSSIER_SIZES))
    ap.add_argument("--seeds", type=int, default=1)
    ap.add_argument("--turns", type=int, default=20)
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--max-history-turns", type=int, default=None,
                    help="truncate the transcript to the last N turns; omit to "
                         "keep everything, which is the condition under test")
    ap.add_argument("--provider", default="gemini", choices=["gemini", "openrouter"])
    ap.add_argument("--out", type=Path, default=RUNS_DIR / "agentic.jsonl")
    ap.add_argument("--offline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    args = ap.parse_args()

    sizes, arms = tuple(args.sizes), tuple(args.arms)

    if args.offline:
        offline_check(sizes, args.seeds, args.turns)
        return

    estimate(sizes, args.seeds, args.turns, arms, args.max_history_turns)
    if args.dry_run:
        return

    print(f"\nprovider={args.provider} model={MODEL}\nlog={args.out}\n")
    out = run(
        provider=get_provider(args.provider),
        sizes=sizes,
        seeds=tuple(range(args.seeds)),
        arms=arms,
        turns=args.turns,
        max_history_turns=args.max_history_turns,
        out=args.out,
    )
    print(f"\ndone -> {out}\n  uv run python scripts/analyse_agentic.py")


if __name__ == "__main__":
    main()
