"""Run the retry experiment.

  uv run python scripts/run_retry.py --offline     # no API calls; asserts the invariants
  uv run python scripts/run_retry.py --dry-run     # budget only
  uv run python scripts/run_retry.py --design thin
  uv run python scripts/analyse_retry.py

Safe to interrupt. A completed arm is skipped on the next run, and a shared
first attempt already on disk is reused rather than re-bought.
"""

from __future__ import annotations

import argparse
from pathlib import Path

from dsw.config import FREE_TIER_RPD, MODEL, RUNS_DIR
from dsw.constraints import (
    check_all, make_resolvable_form, planted_violations, pydantic_locs,
)
from dsw.forms import SIZES
from dsw.metrics import integrity_outside
from dsw.projection import classify_write, project
from dsw.providers import get_provider
from dsw.retry import ARMS, fragment_value, localisation_of, run
from dsw.splice import splice

DOC_TOKENS = {"small": 1_538, "medium": 5_276, "large": 16_895}
PROMPT_OVERHEAD = 400          # rules + violation block
FRAGMENT_OUT = 120

# The free tier is 20 requests/day/model (measured; see config.py), and one
# episode costs 1 shared call plus up to `max_rounds` whole-arm calls plus up to
# one fragment call per outstanding violation per round. So the grid is sized in
# episodes, not turns.
DESIGNS = {
    "thin":  dict(sizes=["small"], seeds=3, planted=2, max_rounds=2),
    "thick": dict(sizes=["small", "medium"], seeds=5, planted=4, max_rounds=3),
}


def estimate(sizes, seeds: int, planted: int, max_rounds: int, arms) -> None:
    """Worst-case call and token budget. Real runs come in well under it."""
    violations = planted + 1
    per_episode = 1
    if "whole" in arms:
        per_episode += max_rounds
    if "fragment" in arms:
        per_episode += max_rounds * violations
    episodes = len(sizes) * seeds
    calls = episodes * per_episode

    print(f"{'size':<8}{'arm':<10}{'in/call':>9}{'out/call':>9}{'calls':>7}{'tokens':>12}")
    in_tok = out_tok = 0
    for size in sizes:
        doc = DOC_TOKENS.get(size, 0)
        for arm in ("shared", *arms):
            n_calls = seeds * (
                1 if arm == "shared"
                else max_rounds if arm == "whole"
                else max_rounds * violations
            )
            out = FRAGMENT_OUT if arm == "fragment" else doc
            inp = doc + PROMPT_OVERHEAD
            in_tok += inp * n_calls
            out_tok += out * n_calls
            print(f"{size:<8}{arm:<10}{inp:>9,}{out:>9,}{n_calls:>7}"
                  f"{(inp + out) * n_calls:>12,}")

    cost = in_tok / 1e6 * 0.75 + out_tok / 1e6 * 3.75
    days = -(-calls // FREE_TIER_RPD)
    print(f"\n  {episodes} episodes, {violations} violations each "
          f"(R1 + {planted} planted), <= {max_rounds} rounds")
    print(f"  worst case: {calls} calls, ~{in_tok + out_tok:,} tokens "
          f"({in_tok:,} in / {out_tok:,} out)")
    print(f"  paid:  ~${cost:.2f} on {MODEL}  (~${cost / 2:.2f} batched)")
    print(f"  free:  {FREE_TIER_RPD} req/day/model -> "
          + ("fits one day" if calls <= FREE_TIER_RPD else f"{days} days worst case"))


def offline_check(sizes, seeds: int, planted: int) -> None:
    """Assert every invariant that does not need the API. Costs nothing.

    The fragment arm's central claim -- that a splice cannot disturb anything
    outside its own subtree -- is arithmetic, not an empirical result, so it is
    asserted here rather than measured with paid calls.
    """
    checks = 0
    for size in sizes:
        n = SIZES[size]
        for seed in range(seeds):
            form = make_resolvable_form(n, seed=seed, planted=planted)

            assert not check_all(form), "an under_review form must start clean"

            resolved = form.model_copy(update={"status": "resolved"})
            vs = check_all(resolved)
            assert len(vs) == planted + 1, (
                f"{size}/{seed}: expected {planted + 1} violations, got {len(vs)}: "
                + ", ".join(v.rule for v in vs)
            )
            assert {v.rule for v in vs} == {"R1", "R2", "R3"}, (
                f"{size}/{seed}: all three rules must fire, got "
                f"{sorted({v.rule for v in vs})}"
            )
            assert planted_violations(form) == vs

            free = set(pydantic_locs(resolved))
            kinds = {v.rule: localisation_of(v, free) for v in vs}
            assert kinds["R2"] == "exact", (
                "R2 is declared on Response, so Pydantic must localise it for free"
            )
            assert kinds["R1"] == "hinted" and kinds["R3"] == "hinted", (
                "R1/R3 are form-level, so their loc is () and the path must be declared"
            )

            # Splice preserves everything outside its own subtree, exactly.
            for v in vs:
                path = v.repair_paths[0]
                assert project(type(resolved), path) is not None
                current = _value_at(resolved, path)
                result = splice(resolved, path, current)
                assert result.ok and result.document is not None, result.error
                integ = integrity_outside(resolved, result.document, (path,))
                assert integ.perfect, f"splice at {path} disturbed {integ.summary()}"
                assert classify_write(type(resolved), path, "replace").operation == "replace"
                checks += 1

            # A repaired fragment fixes its own violation and touches nothing else.
            fixed = splice(resolved, ("responses", _first_r3(vs)),
                           {**_value_at(resolved, ("responses", _first_r3(vs))),
                            "confidence": "medium"})
            assert fixed.ok, fixed.error
            after = check_all(fixed.document)
            assert len(after) == len(vs) - 1, (
                f"a correct R3 repair must remove exactly one violation, "
                f"{len(vs)} -> {len(after)}"
            )

            # ...and the careless repair is genuinely a trap: promoting to
            # "high" trades an R3 violation for an R2 one, which is the
            # oscillation the experiment is looking for.
            idx = _first_r3(vs)
            node = _value_at(resolved, ("responses", idx))
            careless = splice(resolved, ("responses", idx),
                              {**node, "confidence": "high"})
            assert careless.ok, careless.error
            swapped = check_all(careless.document)
            assert len(swapped) == len(vs), "the careless R3 repair must not reduce the count"
            assert any(v.rule == "R2" and v.repair_paths[0] == ("responses", idx)
                       for v in swapped), "the careless repair must create an R2 violation"

    print(f"offline: OK  ({checks} splice invariants, "
          f"{len(sizes) * seeds} episodes checked)")


def _value_at(doc, path):
    from dsw.splice import get_at
    return get_at(doc.model_dump(mode="json"), path)


def _first_r3(violations) -> int:
    for v in violations:
        if v.rule == "R3":
            return v.repair_paths[0][1]
    raise AssertionError("no R3 violation planted")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--sizes", nargs="+", default=["small"], choices=list(SIZES))
    ap.add_argument("--seeds", type=int, default=3)
    ap.add_argument("--planted", type=int, default=2,
                    help="response-level violations to plant; total is this + 1 (R1)")
    ap.add_argument("--max-rounds", type=int, default=2)
    ap.add_argument("--rules-first", action="store_true",
                    help="state the closure rules on the first attempt too. "
                         "Measured twice: the model then satisfies them and "
                         "no retry ever happens, which is why it is not the default.")
    ap.add_argument("--arms", nargs="+", default=list(ARMS), choices=list(ARMS))
    ap.add_argument("--provider", default="gemini", choices=["gemini", "openrouter"])
    ap.add_argument("--out", type=Path, default=RUNS_DIR / "retry.jsonl")
    ap.add_argument("--design", choices=sorted(DESIGNS))
    ap.add_argument("--offline", action="store_true",
                    help="assert the invariants without touching the API")
    ap.add_argument("--dry-run", action="store_true", help="print the budget and stop")
    args = ap.parse_args()

    if args.design:
        d = DESIGNS[args.design]
        args.sizes, args.seeds = d["sizes"], d["seeds"]
        args.planted, args.max_rounds = d["planted"], d["max_rounds"]

    sizes, arms = tuple(args.sizes), tuple(args.arms)

    if args.offline:
        offline_check(sizes, args.seeds, args.planted)
        return

    estimate(sizes, args.seeds, args.planted, args.max_rounds, arms)
    if args.dry_run:
        return

    print(f"\nprovider={args.provider} model={MODEL}\nlog={args.out}\n")
    out = run(
        provider=get_provider(args.provider),
        sizes=sizes,
        seeds=tuple(range(args.seeds)),
        planted=args.planted,
        arms=arms,
        max_rounds=args.max_rounds,
        rules_first=args.rules_first,
        out=args.out,
    )
    print(f"\ndone -> {out}\n  uv run python scripts/analyse_retry.py")


if __name__ == "__main__":
    main()
