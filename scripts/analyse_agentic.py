"""Read the agentic-loop log and look for the divergence.

The earlier experiments asked "is integrity 1.0?" and got yes. This one asks a
different question, and it is a question about a *trajectory*: does integrity
stay at 1.0 as the transcript grows, and if it does not, at what context size
does it break?

So the output is per-turn curves, not per-arm averages. An average over forty
turns would hide exactly the effect being looked for.
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
from collections import Counter, defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from dsw.config import RUNS_DIR

console = Console()
ARMS = ("whole", "fragment")


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"no run log at {path}; run scripts/run_agentic.py first")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _mean(xs) -> float:
    return stats.fmean(xs) if xs else float("nan")


def trajectory(rows: list[dict]) -> None:
    """The curve. This is the whole experiment."""
    by = defaultdict(dict)
    for r in rows:
        if r["ok"]:
            by[r["turn"]][r["arm"]] = r
    if not by:
        return

    t = Table(title="Per-turn trajectory — context size against integrity")
    for c in ("turn", "whole ctx", "whole integ", "whole viol", "whole applied",
              "frag ctx", "frag integ", "frag viol", "frag applied"):
        t.add_column(c, justify="right")

    for turn in sorted(by):
        w, f = by[turn].get("whole"), by[turn].get("fragment")

        def cells(r):
            if not r:
                return ["-", "-", "-", "-"]
            integ = f"{r['integrity_rate']:.5f}"
            style = "" if r["integrity_perfect"] else "[red]"
            end = "" if r["integrity_perfect"] else "[/red]"
            return [
                f"{r['prompt_tokens']:,}",
                f"{style}{integ}{end}",
                str(r["violations"]),
                "yes" if r["edit_applied"] else "[red]NO[/red]",
            ]

        t.add_row(str(turn), *cells(w), *cells(f))
    console.print(t)


def divergence(rows: list[dict]) -> None:
    """The first turn at which each arm stopped being perfect."""
    t = Table(title="Where each arm first broke")
    for c in ("arm", "turns", "first imperfect turn", "context there",
              "first violation turn", "first missed edit", "perfect turns"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    for arm in ARMS:
        steps = sorted((r for r in rows if r["arm"] == arm and r["ok"]),
                       key=lambda r: r["turn"])
        if not steps:
            continue
        bad = next((r for r in steps if not r["integrity_perfect"]), None)
        viol = next((r for r in steps if r["violations"]), None)
        missed = next((r for r in steps if not r["edit_applied"]), None)
        t.add_row(
            arm, str(len(steps)),
            str(bad["turn"]) if bad else "never",
            f"{bad['prompt_tokens']:,}" if bad else "—",
            str(viol["turn"]) if viol else "never",
            str(missed["turn"]) if missed else "never",
            f"{sum(1 for r in steps if r['integrity_perfect'])}/{len(steps)}",
        )
    console.print(t)


def by_context_band(rows: list[dict]) -> None:
    """Integrity bucketed by how much context was in play — the causal variable."""
    bands = [(0, 25_000), (25_000, 50_000), (50_000, 100_000),
             (100_000, 200_000), (200_000, 10 ** 9)]
    t = Table(title="Integrity by context size (both arms pooled and split)")
    for c in ("context band", "arm", "turns", "perfect", "mean integrity",
              "mean corrupted leaves", "mean violations"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    for lo, hi in bands:
        for arm in ARMS:
            band = [r for r in rows if r["ok"] and r["arm"] == arm
                    and lo <= r["prompt_tokens"] < hi]
            if not band:
                continue
            label = f"{lo // 1000}K–{hi // 1000}K" if hi < 10 ** 9 else f"{lo // 1000}K+"
            t.add_row(
                label, arm, str(len(band)),
                f"{sum(1 for r in band if r['integrity_perfect'])}/{len(band)}",
                f"{_mean([r['integrity_rate'] for r in band]):.5f}",
                f"{_mean([r['corrupted_leaves'] for r in band]):.2f}",
                f"{_mean([r['violations'] for r in band]):.2f}",
            )
    console.print(t)


def rules_broken(rows: list[dict]) -> None:
    t = Table(title="Which rule broke, by arm")
    for c in ("arm", "D1 local", "D2 referential", "D3 structural",
              "D4 global", "D5 branch shape"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    for arm in ARMS:
        steps = [r for r in rows if r["arm"] == arm and r["ok"]]
        if not steps:
            continue
        tot: Counter = Counter()
        for r in steps:
            tot.update(r["violations_by_rule"] or {})
        t.add_row(arm, *[str(tot.get(k, 0)) for k in ("D1", "D2", "D3", "D4", "D5")])
    console.print(t)

    sample = [r for r in rows if r["ok"] and r["violation_sample"]]
    if sample:
        console.print("\n[bold]First violations seen[/bold]")
        for r in sample[:4]:
            console.print(f"  {r['arm']:<9} t{r['turn']:<3} ctx={r['prompt_tokens']:,}")
            for m in r["violation_sample"][:2]:
                console.print(f"      {m}")


def cost(rows: list[dict]) -> None:
    t = Table(title="Cumulative cost of the loop")
    for c in ("arm", "turns", "input tokens", "output tokens", "final context",
              "total latency"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    totals = {}
    for arm in ARMS:
        steps = sorted((r for r in rows if r["arm"] == arm and r["ok"]),
                       key=lambda r: r["turn"])
        if not steps:
            continue
        last = steps[-1]
        totals[arm] = (last["cumulative_prompt_tokens"],
                       last["cumulative_output_tokens"])
        t.add_row(
            arm, str(len(steps)),
            f"{last['cumulative_prompt_tokens']:,}",
            f"{last['cumulative_output_tokens']:,}",
            f"{last['prompt_tokens']:,}",
            f"{sum(r['latency_s'] for r in steps):.0f}s",
        )
    console.print(t)
    if len(totals) == 2:
        wi, wo = totals["whole"]
        fi, fo = totals["fragment"]
        console.print(
            f"\n  [bold]input {wi / max(fi, 1):.1f}× · output {wo / max(fo, 1):.1f}×[/bold]"
            "   (the input ratio is the one the earlier experiments could not show)"
        )


def errors(rows: list[dict]) -> None:
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        return
    console.print(f"\n[bold red]{len(bad)} failed turn(s)[/bold red]")
    for r in bad:
        console.print(f"  {r['arm']:<9} t{r['turn']}: {(r['error'] or '')[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=RUNS_DIR / "agentic.jsonl")
    args = ap.parse_args()
    rows = load(args.log)
    console.print(f"[dim]{len(rows)} turns from {args.log}[/dim]\n")
    trajectory(rows)
    divergence(rows)
    by_context_band(rows)
    rules_broken(rows)
    cost(rows)
    errors(rows)


if __name__ == "__main__":
    main()
