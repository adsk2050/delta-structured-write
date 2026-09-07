"""Read the retry log and answer what the retry experiment was built to answer.

Headline: when a structured output is rejected, does resending the whole
document repair it more reliably than repairing the fragment that broke -- and
what does each cost to get to a valid document?

The metric to look at first is `introduced`: violations that appear *because of*
a repair step. It is the one number the integrity experiment could not produce,
because that experiment never induced a failure.
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
        raise SystemExit(f"no run log at {path}; run scripts/run_retry.py first")
    return [json.loads(l) for l in path.read_text(encoding="utf-8").splitlines() if l.strip()]


def _mean(xs) -> float:
    return stats.fmean(xs) if xs else float("nan")


def _episodes(rows: list[dict]) -> dict[tuple, dict[str, list[dict]]]:
    """Group steps by episode, then by arm, preserving order."""
    out: dict[tuple, dict[str, list[dict]]] = defaultdict(lambda: defaultdict(list))
    for r in rows:
        out[(r["size"], r["seed"], r["planted"])][r["arm"]].append(r)
    return out


def first_attempt(rows: list[dict]) -> None:
    shared = [r for r in rows if r["arm"] == "shared"]
    if not shared:
        return
    ok = [r for r in shared if r["ok"]]
    clean = [r for r in ok if r["violations_after"] == 0]
    t = Table(title="The shared first attempt (one call per episode, both arms branch from it)")
    for c in ("episodes", "succeeded", "valid first time", "mean violations left",
              "mean out tokens", "mean latency"):
        t.add_column(c, justify="right")
    t.add_row(
        str(len(shared)), str(len(ok)), f"{len(clean)}/{len(ok)}",
        f"{_mean([r['violations_after'] for r in ok]):.2f}",
        f"{_mean([r['output_tokens'] for r in ok]):,.0f}",
        f"{_mean([r['latency_s'] for r in ok]):.1f}s",
    )
    console.print(t)


def per_arm(rows: list[dict]) -> None:
    eps = _episodes(rows)
    t = Table(title="Repairing a rejected document, per arm")
    for c in ("arm", "episodes", "reached valid", "mean rounds", "mean calls",
              "mean out tokens", "mean latency", "steps that introduced a new violation"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"

    for arm in ARMS:
        n = solved = 0
        rounds, calls, out_tok, lat = [], [], [], []
        introduced_steps = introduced_total = total_steps = 0
        for _, by_arm in eps.items():
            steps = by_arm.get(arm) or []
            if not steps:
                continue
            n += 1
            good = [s for s in steps if s["ok"]]
            if good and good[-1]["violations_after"] == 0:
                solved += 1
                rounds.append(good[-1]["round"])
            calls.append(len(steps))
            out_tok.append(sum(s["output_tokens"] for s in steps))
            # Successful steps only: a failed step's latency is dominated by
            # the transport back-off sleep, which is not generation time.
            lat.append(sum(s["latency_s"] for s in good))
            for s in good:
                total_steps += 1
                if s["introduced"]:
                    introduced_steps += 1
                    introduced_total += s["introduced"]
        if not n:
            continue
        t.add_row(
            arm, str(n), f"{solved}/{n}",
            f"{_mean(rounds):.2f}" if rounds else "n/a",
            f"{_mean(calls):.2f}",
            f"{_mean(out_tok):,.0f}", f"{_mean(lat):.1f}s",
            f"{introduced_steps}/{total_steps}  ({introduced_total} violations)",
        )
    console.print(t)


def oscillation(rows: list[dict]) -> None:
    t = Table(title="Oscillation — did a repair step create work?")
    for c in ("arm", "repair steps", "fixed >0", "introduced >0",
              "net violations removed", "mean fixed/step", "mean introduced/step"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    for arm in ARMS:
        steps = [r for r in rows if r["arm"] == arm and r["ok"]]
        if not steps:
            continue
        fixed = [s["fixed"] or 0 for s in steps]
        intro = [s["introduced"] or 0 for s in steps]
        t.add_row(
            arm, str(len(steps)),
            str(sum(1 for f in fixed if f)), str(sum(1 for i in intro if i)),
            str(sum(fixed) - sum(intro)),
            f"{_mean(fixed):.2f}", f"{_mean(intro):.2f}",
        )
    console.print(t)


def collateral(rows: list[dict]) -> None:
    """Integrity on the retry path — the question the integrity experiment left open."""
    t = Table(title="Collateral damage per repair step (outside the paths being repaired)")
    for c in ("arm", "steps", "perfect", "mean integrity", "mean corrupted leaves"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    for arm in ARMS:
        steps = [r for r in rows if r["arm"] == arm and r["ok"]
                 and r["integrity_rate"] is not None]
        if not steps:
            continue
        perfect = sum(1 for s in steps if s["corrupted_leaves"] == 0)
        t.add_row(
            arm, str(len(steps)), f"{perfect}/{len(steps)}",
            f"{_mean([s['integrity_rate'] for s in steps]):.5f}",
            f"{_mean([s['corrupted_leaves'] for s in steps]):.2f}",
        )
    console.print(t)

    worst = sorted(
        (r for r in rows if r["ok"] and r.get("corrupted_sample")),
        key=lambda r: -(r["corrupted_leaves"] or 0),
    )[:5]
    if worst:
        console.print("\n[bold]Worst collateral, by step[/bold]")
        for r in worst:
            console.print(
                f"  {r['arm']:<9} seed {r['seed']} r{r['round']}.{r['call']}  "
                f"{r['corrupted_leaves']} leaves  e.g. "
                + ", ".join(r["corrupted_sample"][:4])
            )


def localisation(rows: list[dict]) -> None:
    steps = [r for r in rows if r["arm"] == "fragment" and r["localisation"]]
    if not steps:
        return
    counts = Counter(s["localisation"] for s in steps)
    by_rule = Counter((s["target_rule"], s["localisation"]) for s in steps)
    t = Table(title="Where the repair path came from")
    for c in ("source", "steps", "share", "rules"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    meaning = {
        "exact": "Pydantic's ValidationError.loc pointed at it — free",
        "hinted": "the rule had to declare the path by hand",
        "unlocalisable": "no path; fragment retry cannot aim",
    }
    for kind, n in counts.most_common():
        rules = ", ".join(sorted({r for (r, k) in by_rule if k == kind}))
        t.add_row(f"{kind}  ({meaning[kind]})", str(n),
                  f"{n / len(steps):.0%}", rules)
    console.print(t)


def cost_to_valid(rows: list[dict]) -> None:
    """Tokens and calls spent on repair only, whole vs fragment, per episode."""
    eps = _episodes(rows)
    t = Table(title="Cost of repair per episode (the shared first attempt excluded)")
    for c in ("episode", "whole calls", "whole out", "frag calls", "frag out",
              "output ratio", "whole valid", "frag valid"):
        t.add_column(c, justify="right")
    t.columns[0].justify = "left"
    ratios = []
    for (size, seed, planted), by_arm in sorted(eps.items()):
        w, f = by_arm.get("whole") or [], by_arm.get("fragment") or []
        if not w and not f:
            continue
        wo, fo = sum(s["output_tokens"] for s in w), sum(s["output_tokens"] for s in f)
        ratio = wo / fo if fo else float("nan")
        if fo and wo:
            ratios.append(ratio)
        done = lambda ss: ("yes" if ss and ss[-1]["ok"] and ss[-1]["violations_after"] == 0
                           else "no" if ss else "-")
        t.add_row(f"{size}/{seed}/p{planted}", str(len(w)), f"{wo:,}",
                  str(len(f)), f"{fo:,}",
                  f"{ratio:.1f}x" if fo else "n/a", done(w), done(f))
    console.print(t)
    if ratios:
        console.print(
            f"\n  [bold]mean output-token ratio (whole / fragment): "
            f"{_mean(ratios):.1f}x[/bold]   median {stats.median(ratios):.1f}x"
        )


def errors(rows: list[dict]) -> None:
    bad = [r for r in rows if not r["ok"]]
    if not bad:
        return
    console.print(f"\n[bold red]{len(bad)} failed step(s)[/bold red]")
    for r in bad:
        console.print(f"  {r['arm']:<9} seed {r['seed']} r{r['round']}.{r['call']}: "
                      f"{(r['error'] or '')[:200]}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--log", type=Path, default=RUNS_DIR / "retry.jsonl")
    args = ap.parse_args()
    rows = load(args.log)
    console.print(f"[dim]{len(rows)} steps from {args.log}[/dim]\n")
    first_attempt(rows)
    per_arm(rows)
    oscillation(rows)
    collateral(rows)
    localisation(rows)
    cost_to_valid(rows)
    errors(rows)


if __name__ == "__main__":
    main()
