"""The agentic-loop experiment: what happens when the transcript accumulates.

[`notes/05`](../../notes/05-what-the-experiments-did-not-test.md) records why
this exists. The integrity and retry experiments both built each turn's prompt
from scratch, so a "12-turn chain" was twelve independent calls at a flat ~1.6%
of the context window. The compounding the literature reports is a function of
*accumulated context*, so it was structurally excluded from the design rather
than measured and found absent.

Here the transcript accumulates. Turn *n* sees turns 1..*n*-1 — instructions and
model outputs both — as real multi-turn `contents`. That single change is what
separates the two arms:

    whole arm      appends a full document to the transcript every turn, so its
                   context grows by roughly the document size per turn
    fragment arm   appends one block, so its context stays nearly flat

Both arms are also shown the **current document** each turn, so neither has to
reconstruct state from history and neither carries a retrieval disadvantage.
The only difference between them is transcript bulk. That isolates the variable
exactly.

A fair objection, worth stating rather than hiding: you could prune the
transcript instead. True — and that is a finding, not a rebuttal. The fragment
arm makes pruning unnecessary, and pruning is itself a lossy choice somebody has
to design.

**The prediction, recorded before the run so it can be wrong:** the arms track
each other for the first several turns, reproducing the earlier nulls as a
control, and then diverge as the whole arm's context grows.
"""

from __future__ import annotations

import json
import random
from dataclasses import asdict, dataclass, field
from pathlib import Path as FsPath
from typing import Iterator

from .config import RUNS_DIR
from .constraints import Violation
from .dossier import (
    DOSSIER_SIZES, DecodableBlock, DecodableDossier, make_dossier,
)
from .dossier_rules import (
    RULES_IN_PROSE, check_dossier, rule_summary, walk_blocks,
)
from .experiment import Throttle
from .metrics import integrity_outside
from .projection import Path, classify_write, project
from .providers import Provider
from .splice import splice

ARMS = ("whole", "fragment")


# --------------------------------------------------------------------------
# The edits
# --------------------------------------------------------------------------

@dataclass(frozen=True)
class Edit:
    """One turn's instruction, plus what has to be true afterwards to score it.

    Every edit targets a single block, and every edit is chosen so that doing it
    correctly requires consulting something *outside* that block — the source
    registry in the header, or the table's own declared width. A model that has
    stopped attending to the top of a long context can still write a plausible
    block; it cannot keep the references straight.
    """

    kind: str
    path: Path
    block_id: str
    instruction: str
    expect: dict


def _first_source(doc: DecodableDossier, rng: random.Random) -> str:
    return rng.choice([s.source_id for s in doc.sources])


def make_edit(doc: DecodableDossier, turn: int, seed: int = 0) -> Edit:
    """Deterministic given (document shape, turn, seed). Rotates the four kinds."""
    rng = random.Random((seed + 1) * 7919 + turn)
    blocks = list(walk_blocks(doc))

    findings = [(p, b) for p, b in blocks if b.kind == "finding"]
    tables = [(p, b) for p, b in blocks if b.kind == "table"]
    narratives = [(p, b) for p, b in blocks if b.kind == "narrative"]

    order = ["escalate", "add_row", "recite", "restate"]
    kind = order[turn % len(order)]
    if kind == "escalate" and not findings:
        kind = "restate"
    if kind == "add_row" and not tables:
        kind = "restate"
    if kind == "recite" and not narratives:
        kind = "restate"

    if kind == "escalate":
        path, block = rng.choice(findings)
        src = _first_source(doc, rng)
        return Edit(
            kind, path, block.block_id,
            instruction=(
                f"Raise the severity of finding `{block.block_id}` to "
                f'"critical". Because it becomes critical it must satisfy D1: '
                f"give it at least two citations and a non-empty remediation. "
                f"Every citation must name a source declared in `sources`."
            ),
            expect={"severity": "critical", "min_citations": 2,
                    "needs_remediation": True, "cited_source_hint": src},
        )

    if kind == "add_row":
        path, block = rng.choice(tables)
        width = len(block.columns or [])
        n_rows = len(block.rows or [])
        return Edit(
            kind, path, block.block_id,
            instruction=(
                f"Add one new row to table `{block.block_id}`. It declares "
                f"{width} columns, so the new row must have exactly {width} "
                f"cells (D3), and its `row_id` must not collide with any id "
                f"already in the dossier (D4)."
            ),
            expect={"rows": n_rows + 1, "width": width},
        )

    if kind == "recite":
        path, block = rng.choice(narratives)
        src = _first_source(doc, rng)
        return Edit(
            kind, path, block.block_id,
            instruction=(
                f"Rewrite the text of narrative block `{block.block_id}` to "
                f"state that the control is now formally approved, and cite "
                f"source `{src}` for it. Keep every other citation it already "
                f"has. Do not invent a source id."
            ),
            expect={"must_cite": src},
        )

    path, block = rng.choice(blocks)
    return Edit(
        "restate", path, block.block_id,
        instruction=(
            f"Rewrite the main prose of block `{block.block_id}` to be one "
            f"sentence shorter, keeping its meaning and its `kind`. Change "
            f"nothing else about it."
        ),
        expect={},
    )


def edit_applied(doc: DecodableDossier, edit: Edit) -> bool:
    """Did the requested change actually land? Judged on the block, not the prose."""
    from .splice import get_at

    try:
        node = get_at(doc.model_dump(mode="json"), edit.path)
    except (KeyError, IndexError, TypeError):
        return False
    e = edit.expect
    if edit.kind == "escalate":
        return (
            node.get("severity") == "critical"
            and len(node.get("citations") or []) >= e["min_citations"]
            and bool((node.get("remediation") or "").strip())
        )
    if edit.kind == "add_row":
        rows = node.get("rows") or []
        return len(rows) == e["rows"] and all(
            len(r.get("cells") or []) == e["width"] for r in rows
        )
    if edit.kind == "recite":
        return any(c.get("source_id") == e["must_cite"]
                   for c in (node.get("citations") or []))
    return True


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

SYSTEM = (
    "You are maintaining a structured assurance dossier across many edits.\n\n"
    f"{RULES_IN_PROSE}\n"
)


def _prompt(doc: DecodableDossier, edit: Edit, arm: str) -> str:
    pointer = "".join(f"/{s}" for s in edit.path)
    if arm == "whole":
        task = (
            "Apply the requested change and return the COMPLETE updated "
            "dossier. Every other field must be reproduced exactly as given."
        )
    else:
        task = (
            f"Return ONLY the single updated block at `{pointer}` "
            f"(block_id `{edit.block_id}`). Do not return the rest of the "
            f"dossier."
        )
    return (
        f"{SYSTEM}\n"
        f"CURRENT DOSSIER (JSON):\n{doc.model_dump_json(indent=None)}\n\n"
        f"REQUESTED CHANGE:\n{edit.instruction}\n\n"
        f"TASK:\n{task}"
    )


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

@dataclass
class TurnRecord:
    size: str
    n_sections: int
    n_blocks: int
    seed: int
    arm: str
    turn: int
    ok: bool
    edit_kind: str
    edit_path: str
    # the growth curve — the whole point of the experiment
    history_turns: int
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    cumulative_prompt_tokens: int
    cumulative_output_tokens: int
    # integrity
    integrity_rate: float | None
    integrity_perfect: bool | None
    corrupted_leaves: int | None
    added_leaves: int | None
    removed_leaves: int | None
    corrupted_sample: list[str] | None
    edit_applied: bool | None
    # the rules
    violations: int | None
    violations_by_rule: dict[str, int] | None
    new_violations: int | None
    violation_sample: list[str] | None
    # provenance
    latency_s: float
    model: str
    constrained: bool
    finish_reason: str | None
    truncated: bool
    safety_verdict: str
    error: str | None = None
    # Persisted so a chain can resume MID-WAY rather than only at its start.
    # Without this the free tier cannot run the experiment at all: 20 calls a
    # day against a 40-turn chain means dying at turn 20 and restarting from
    # turn 1 tomorrow, forever. `output_text` is what the transcript replay
    # needs; `document` is the state to carry forward.
    output_text: str | None = None
    document: str | None = None


def _keys(vs: list[Violation]) -> set[tuple[str, str]]:
    return {(v.rule, v.message) for v in vs}


# --------------------------------------------------------------------------
# One chain
# --------------------------------------------------------------------------

def run_chain(
    provider: Provider,
    size: str,
    seed: int,
    arm: str,
    turns: int,
    throttle: Throttle,
    max_history_turns: int | None = None,
    resume: list[dict] | None = None,
) -> Iterator[TurnRecord]:
    """One dossier, `turns` sequential edits, with a transcript that accumulates.

    `max_history_turns` truncates the transcript to the most recent N turns. It
    exists so the "just prune the transcript" objection can be run as its own
    condition rather than argued about. `None` means keep everything, which is
    the condition the experiment is about.
    """
    n_sections = DOSSIER_SIZES[size]
    doc = make_dossier(n_sections, seed=seed)
    n_blocks = len(list(walk_blocks(doc)))
    schema: type = DecodableDossier if arm == "whole" else DecodableBlock

    history: list[tuple[str, str]] = []
    cum_in = cum_out = 0
    prev_violations: set[tuple[str, str]] = _keys(check_dossier(doc))
    start_turn = 1

    # Replay whatever already landed, without spending a call on any of it.
    for rec in resume or []:
        doc_then = DecodableDossier.model_validate_json(rec["document"])
        history.append(("user", make_edit(doc, rec["turn"], seed=seed).instruction))
        history.append(("model", rec["output_text"]))
        doc = doc_then
        cum_in, cum_out = rec["cumulative_prompt_tokens"], rec["cumulative_output_tokens"]
        prev_violations = _keys(check_dossier(doc))
        start_turn = rec["turn"] + 1
    if resume:
        print(f"      resumed at turn {start_turn} "
              f"({len(history) // 2} turns of transcript replayed, 0 calls)")

    for turn in range(start_turn, turns + 1):
        edit = make_edit(doc, turn, seed=seed)
        safety = classify_write(DecodableDossier, edit.path, operation="replace")
        prompt = _prompt(doc, edit, arm)

        sent = history if max_history_turns is None else history[-2 * max_history_turns:]
        projected = (
            sum(len(t) for _, t in sent) // 4
            + len(prompt) // 4
            + (len(prompt) // 4 if arm == "whole" else 400)
        )
        # `sent` carries instructions and prior outputs only; `prompt` carries
        # the current dossier. See the note where history is appended below.
        throttle.wait(projected)

        resp = provider.generate(
            prompt,
            DecodableDossier if arm == "whole" else project(DecodableDossier, edit.path),
            max_output_tokens=65_536,
            history=sent,
        )
        throttle.record(resp.prompt_tokens + resp.output_tokens)
        cum_in += resp.prompt_tokens
        cum_out += resp.output_tokens

        base = dict(
            size=size, n_sections=n_sections, n_blocks=n_blocks, seed=seed,
            arm=arm, turn=turn, edit_kind=edit.kind,
            edit_path="".join(f"/{s}" for s in edit.path),
            history_turns=len(sent) // 2,
            prompt_tokens=resp.prompt_tokens, output_tokens=resp.output_tokens,
            thought_tokens=int(resp.meta.get("thought_tokens", 0) or 0),
            cumulative_prompt_tokens=cum_in, cumulative_output_tokens=cum_out,
            latency_s=round(resp.latency_s, 3), model=resp.model,
            constrained=resp.constrained, finish_reason=resp.finish_reason,
            truncated=resp.truncated, safety_verdict=safety.explain(),
        )

        def failed(err: str) -> TurnRecord:
            return TurnRecord(
                ok=False, integrity_rate=None, integrity_perfect=None,
                corrupted_leaves=None, added_leaves=None, removed_leaves=None,
                corrupted_sample=None, edit_applied=None, violations=None,
                violations_by_rule=None, new_violations=None,
                violation_sample=None, error=err, **base,
            )

        if resp.error or resp.parsed is None:
            yield failed(resp.error or "provider returned no parseable object")
            return

        if arm == "whole":
            try:
                new_doc = DecodableDossier.model_validate(
                    resp.parsed.model_dump(mode="json")
                )
            except Exception as exc:
                yield failed(f"whole output failed validation: {exc}")
                return
            output_text = new_doc.model_dump_json()
        else:
            result = splice(doc, edit.path, resp.parsed.model_dump(mode="json"))
            if not result.ok or result.document is None:
                yield failed(result.error or "splice failed")
                return
            new_doc = result.document
            output_text = resp.parsed.model_dump_json()

        integ = integrity_outside(doc, new_doc, (edit.path,))
        vs = check_dossier(new_doc)
        now = _keys(vs)
        yield TurnRecord(
            ok=True,
            integrity_rate=round(integ.rate, 6),
            integrity_perfect=integ.perfect,
            corrupted_leaves=len(integ.corrupted),
            added_leaves=len(integ.added),
            removed_leaves=len(integ.removed),
            corrupted_sample=sorted(integ.corrupted)[:10] or None,
            edit_applied=edit_applied(new_doc, edit),
            violations=len(vs),
            violations_by_rule=rule_summary(vs),
            new_violations=len(now - prev_violations),
            violation_sample=[v.message[:160] for v in vs[:5]] or None,
            output_text=output_text, document=new_doc.model_dump_json(),
            **base,
        )

        # The transcript grows here, and this is the experiment.
        #
        # The user turn stored is the *instruction*, not the whole prompt. The
        # prompt restates the current dossier, and storing that would make both
        # arms' history grow by a document per turn — which would destroy the
        # only difference between them. Injecting current state fresh and
        # keeping instructions in history is also what agent frameworks
        # actually do. So the whole arm's transcript grows by a document per
        # turn and the fragment arm's by one block, which is the variable.
        history.append(("user", edit.instruction))
        history.append(("model", output_text))
        prev_violations = now
        doc = new_doc


def run(
    provider: Provider,
    sizes: tuple[str, ...] = ("small",),
    seeds: tuple[int, ...] = (0,),
    arms: tuple[str, ...] = ARMS,
    turns: int = 20,
    max_history_turns: int | None = None,
    out: FsPath | None = None,
) -> FsPath:
    """Run the grid, appending as we go, skipping chains already complete."""
    out = out or (RUNS_DIR / "agentic.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    done: set[tuple] = set()
    landed: dict[tuple, list[dict]] = {}
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["size"], r["seed"], r["arm"])
            if r["ok"] and r.get("document"):
                landed.setdefault(key, []).append(r)
            if r["ok"] and r["turn"] == turns:
                done.add(key)
    # Keep the longest unbroken prefix of successful turns, so a chain that
    # failed and was re-run cannot be replayed from an inconsistent state.
    for key, recs in landed.items():
        seen: dict[int, dict] = {}
        for r in recs:
            seen[r["turn"]] = r
        prefix, t = [], 1
        while t in seen:
            prefix.append(seen[t])
            t += 1
        landed[key] = prefix

    throttle = Throttle()
    with out.open("a", encoding="utf-8") as fh:
        for size in sizes:
            for seed in seeds:
                for arm in arms:
                    if (size, seed, arm) in done:
                        print(f"skip  {size}/{seed}/{arm} (already complete)")
                        continue
                    print(f"run   {size}/{seed}/{arm} ...", flush=True)
                    for rec in run_chain(provider, size, seed, arm, turns,
                                         throttle, max_history_turns,
                                         resume=landed.get((size, seed, arm))):
                        fh.write(json.dumps(asdict(rec)) + "\n")
                        fh.flush()
                        flag = "" if rec.ok else "  ERROR"
                        rate = ("n/a" if rec.integrity_rate is None
                                else f"{rec.integrity_rate:.5f}")
                        print(
                            f"      t{rec.turn:>2}  ctx={rec.prompt_tokens:>7,}"
                            f"  integrity={rate}"
                            f"  viol={rec.violations if rec.violations is not None else '-'}"
                            f"  out={rec.output_tokens:>6}{flag}"
                        )
                        if rec.error:
                            print(f"        {rec.error[:160]}")
    return out
