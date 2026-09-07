"""Read the run log and answer the question the experiment was built to answer.

Headline: of the leaves that were never supposed to change, how many survived —
and does that degrade with document size and with turn number?
"""

from __future__ import annotations

import argparse
import json
import statistics as stats
from collections import defaultdict
from pathlib import Path

from rich.console import Console
from rich.table import Table

from dsw.config import RUNS_DIR

console = Console()


def load(path: Path) -> list[dict]:
    if not path.exists():
        raise SystemExit(f"no run log at {path}; run scripts/run_integrity.py first")
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _mean(xs: list[float]) -> float:
    return stats.fmean(xs) if xs else float("nan")


def by_size_and_arm(rows: list[dict]) -> None:
    table = Table(title="Untouched-region integrity, by document size and arm")
    for col in ("size", "arm", "turns", "perfect turns", "mean integrity",
                "mean corrupted leaves", "target applied", "out tokens/turn"):
        table.add_column(col, justify="right" if col != "arm" else "left")

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["ok"]:
            groups[(r["size"], r["arm"])].append(r)

    order = {"small": 0, "medium": 1, "large": 2}
    for (size, arm) in sorted(groups, key=lambda k: (order.get(k[0], 9), k[1])):
        g = groups[(size, arm)]
        perfect = sum(1 for r in g if r["integrity_perfect"])
        table.add_row(
            size, arm, str(len(g)),
            f"{perfect}/{len(g)} ({perfect / len(g):.0%})",
            f"{_mean([r['integrity_rate'] for r in g]):.5f}",
            f"{_mean([r['corrupted_leaves'] for r in g]):.2f}",
            f"{sum(1 for r in g if r['target_applied'])}/{len(g)}",
            f"{_mean([r['output_tokens'] for r in g]):,.0f}",
        )
    console.print(table)


def by_turn(rows: list[dict]) -> None:
    """Does corruption compound as turns accumulate? The literature says yes."""
    table = Table(title="Does corruption compound with turns? (baseline arm)")
    table.add_column("turn", justify="right")
    for size in ("small", "medium", "large"):
        table.add_column(f"{size} integrity", justify="right")
        table.add_column(f"{size} perfect", justify="right")

    per: dict[tuple[str, int], list[dict]] = defaultdict(list)
    for r in rows:
        if r["ok"] and r["arm"] == "baseline":
            per[(r["size"], r["turn"])].append(r)

    turns = sorted({t for _, t in per})
    for turn in turns:
        cells: list[str] = [str(turn)]
        for size in ("small", "medium", "large"):
            g = per.get((size, turn), [])
            if not g:
                cells += ["-", "-"]
                continue
            perfect = sum(1 for r in g if r["integrity_perfect"])
            cells += [
                f"{_mean([r['integrity_rate'] for r in g]):.5f}",
                f"{perfect}/{len(g)}",
            ]
        table.add_row(*cells)
    console.print(table)


def economics(rows: list[dict]) -> None:
    table = Table(title="Cost, by size (per turn, means)")
    for col in ("size", "arm", "in", "out", "thoughts", "latency s", "out ratio vs fragment"):
        table.add_column(col, justify="right" if col != "arm" else "left")

    groups: dict[tuple[str, str], list[dict]] = defaultdict(list)
    for r in rows:
        if r["ok"]:
            groups[(r["size"], r["arm"])].append(r)

    order = {"small": 0, "medium": 1, "large": 2}
    for size in sorted({s for s, _ in groups}, key=lambda s: order.get(s, 9)):
        frag = groups.get((size, "fragment"), [])
        frag_out = _mean([r["output_tokens"] for r in frag]) if frag else float("nan")
        for arm in ("baseline", "fragment"):
            g = groups.get((size, arm), [])
            if not g:
                continue
            out = _mean([r["output_tokens"] for r in g])
            ratio = f"{out / frag_out:.1f}x" if frag_out and frag_out == frag_out else "-"
            table.add_row(
                size, arm,
                f"{_mean([r['prompt_tokens'] for r in g]):,.0f}",
                f"{out:,.0f}",
                f"{_mean([r['thought_tokens'] for r in g]):,.0f}",
                f"{_mean([r['latency_s'] for r in g]):.2f}",
                ratio,
            )
    console.print(table)


def failures(rows: list[dict]) -> None:
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        console.print("[green]no failed turns[/green]")
        return
    console.print(f"[yellow]{len(bad)} failed turn(s):[/yellow]")
    for r in bad[:15]:
        console.print(
            f"  {r['size']}/{r['seed']}/{r['arm']} turn {r['turn']}: "
            f"{(r['error'] or '')[:140]}"
        )


def corruption_shapes(rows: list[dict]) -> None:
    """What kind of thing does the model quietly change when it retypes?"""
    counts: dict[str, int] = defaultdict(int)
    for r in rows:
        if r["ok"] and r["arm"] == "baseline":
            for p in r.get("corrupted_sample") or []:
                # collapse array indices so /responses/17/answer -> /responses/*/answer
                key = "/".join("*" if seg.isdigit() else seg for seg in p.split("/"))
                counts[key] += 1
    if not counts:
        return
    table = Table(title="Where the baseline arm silently changed things")
    table.add_column("field"), table.add_column("times", justify="right")
    for k, v in sorted(counts.items(), key=lambda kv: -kv[1])[:15]:
        table.add_row(k, str(v))
    console.print(table)


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=RUNS_DIR / "integrity.jsonl")
    args = ap.parse_args()

    rows = load(args.log)
    console.print(f"[bold]{len(rows)}[/bold] turn records from {args.log}\n")
    by_size_and_arm(rows)
    console.print()
    by_turn(rows)
    console.print()
    economics(rows)
    console.print()
    corruption_shapes(rows)
    console.print()
    failures(rows)


if __name__ == "__main__":
    main()
