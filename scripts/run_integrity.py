"""Run the integrity experiment.

  uv run python scripts/run_integrity.py --pilot          # ~12 calls, sanity
  uv run python scripts/run_integrity.py                  # full grid, ~300 calls
  uv run python scripts/run_integrity.py --sizes large    # one size only

Safe to interrupt. Completed chains are skipped on the next run.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw.config import FREE_TIER_RPD, MODEL, RUNS_DIR
from dsw.experiment import ARMS, run
from dsw.forms import SIZES
from dsw.providers import get_provider

# Measured 2026-09-07 against gemini-3.6-flash, in tokens.
DOC_TOKENS = {"small": 1_538, "medium": 5_276, "large": 16_895}
PROMPT_OVERHEAD = 150
FRAGMENT_OUT = 120

# Two designs, because the free tier allows exactly 20 requests/day/model
# (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier, measured
# 2026-09-07 — not the 1,500 the secondary sources claim).
#
#   thin   fits one free-tier day exactly. One size, one seed, ten turns, both
#          arms. Answers: does corruption appear at all, and does it compound
#          across turns? Does NOT answer: size scaling, or variance.
#          `large` is the chosen size because that is where the effect should be
#          largest, so a null result there is genuinely informative.
#   thick  the full grid. Everything the thin design cannot separate.
DESIGNS = {
    "thin":  dict(sizes=["large"], seeds=1, turns=10),
    "thick": dict(sizes=["small", "medium", "large"], seeds=5, turns=10),
}


def estimate(sizes: tuple[str, ...], seeds: int, turns: int, arms: tuple[str, ...]) -> None:
    calls = len(sizes) * seeds * turns * len(arms)
    total = 0
    print(f"{'size':<8}{'arm':<10}{'in/turn':>9}{'out/turn':>9}{'calls':>7}{'tokens':>12}")
    for size in sizes:
        doc = DOC_TOKENS.get(size, 0)
        for arm in arms:
            out = doc if arm == "baseline" else FRAGMENT_OUT
            per = doc + PROMPT_OVERHEAD + out
            n = seeds * turns
            total += per * n
            print(f"{size:<8}{arm:<10}{doc + PROMPT_OVERHEAD:>9,}{out:>9,}{n:>7}{per * n:>12,}")
    # Paid rates for gemini-3.6-flash, introductory tier through 2026-12-31.
    in_tok = sum((DOC_TOKENS.get(s, 0) + PROMPT_OVERHEAD) * seeds * turns
                 for s in sizes for _ in arms)
    out_tok = sum((DOC_TOKENS.get(s, 0) if a == "baseline" else FRAGMENT_OUT)
                  * seeds * turns for s in sizes for a in arms)
    cost = in_tok / 1e6 * 0.75 + out_tok / 1e6 * 3.75
    days = -(-calls // FREE_TIER_RPD)
    print(f"\n  total: {calls} calls, ~{total:,} tokens "
          f"({in_tok:,} in / {out_tok:,} out)")
    print(f"  paid:  ~${cost:.2f} per run on {MODEL}  (~${cost / 2:.2f} batched)")
    print(f"  free:  {FREE_TIER_RPD} req/day/model -> "
          + ("fits one day" if calls <= FREE_TIER_RPD else f"{days} days"))


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=list(SIZES), choices=list(SIZES))
    ap.add_argument("--seeds", type=int, default=5)
    ap.add_argument("--turns", type=int, default=10)
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--provider", default="gemini", choices=["gemini", "openrouter"])
    ap.add_argument("--out", type=Path, default=RUNS_DIR / "integrity.jsonl")
    ap.add_argument("--design", choices=sorted(DESIGNS),
                    help="thin (20 calls, fits one free-tier day) or thick (300 calls)")
    ap.add_argument("--pilot", action="store_true",
                    help="one size, 3 turns, 2 seeds — proves the harness cheaply")
    ap.add_argument("--dry-run", action="store_true", help="print the budget and stop")
    args = ap.parse_args()

    if args.design:
        d = DESIGNS[args.design]
        args.sizes, args.seeds, args.turns = d["sizes"], d["seeds"], d["turns"]
    if args.pilot:
        args.sizes, args.seeds, args.turns = ["medium"], 2, 3

    sizes, arms = tuple(args.sizes), tuple(args.arms)
    estimate(sizes, args.seeds, args.turns, arms)
    if args.dry_run:
        return

    print(f"\nprovider={args.provider} model={MODEL}\nlog={args.out}\n")
    out = run(
        provider=get_provider(args.provider),
        sizes=sizes,
        seeds=tuple(range(args.seeds)),
        arms=arms,
        turns=args.turns,
        out=args.out,
    )
    print(f"\ndone -> {out}\n  uv run python scripts/analyse.py")


if __name__ == "__main__":
    main()
