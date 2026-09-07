"""The integrity experiment, and a runner that survives being interrupted.

The question, from notes/04 §5: take a large Pydantic object, change one leaf,
and measure what happens to everything that was *not* supposed to change.

Two arms, identical inputs:

  baseline   the model re-emits the whole document under the full schema
  fragment   the system picks the path, projects the sub-schema, the model emits
             only that fragment, and code splices it in

Everything is appended to JSONL as it happens. A killed run loses at most the
turn in flight, and re-running skips whatever already landed.
"""

from __future__ import annotations

import json
import time
from collections import deque
from dataclasses import asdict, dataclass
from pathlib import Path as FsPath
from typing import Iterator

from pydantic import BaseModel

from .config import RPM_LIMIT, RUNS_DIR, TPM_LIMIT
from .forms import (
    DecodableReviewForm, EditRequest, Response, ReviewForm, SIZES,
    make_edit, make_form,
)
from .metrics import integrity, target_applied
from .projection import classify_write, project
from .providers import Provider
from .splice import splice

ARMS = ("baseline", "fragment")


class Throttle:
    """Client-side rate limiting, kept strictly under the published free-tier quota.

    Hitting a 429 mid-experiment is not just an inconvenience — a retried call is
    a *second sample* from the model, so silently retrying would quietly change
    what is being measured. Staying under the limit avoids the question.
    """

    def __init__(self, rpm: int = RPM_LIMIT, tpm: int = TPM_LIMIT) -> None:
        self.rpm, self.tpm = rpm, tpm
        self._calls: deque[float] = deque()
        self._tokens: deque[tuple[float, int]] = deque()

    def _prune(self, now: float) -> None:
        while self._calls and now - self._calls[0] > 60:
            self._calls.popleft()
        while self._tokens and now - self._tokens[0][0] > 60:
            self._tokens.popleft()

    def wait(self, projected_tokens: int) -> None:
        while True:
            now = time.monotonic()
            self._prune(now)
            used = sum(t for _, t in self._tokens)
            if len(self._calls) < self.rpm and used + projected_tokens <= self.tpm:
                self._calls.append(now)
                return
            sleep_for = 1.0
            if self._calls:
                sleep_for = max(sleep_for, 60 - (now - self._calls[0]) + 0.05)
            time.sleep(min(sleep_for, 60))

    def record(self, tokens: int) -> None:
        self._tokens.append((time.monotonic(), tokens))


@dataclass
class TurnRecord:
    size: str
    n_responses: int
    seed: int
    arm: str
    turn: int
    ok: bool
    # what we came for
    integrity_rate: float | None
    integrity_perfect: bool | None
    corrupted_leaves: int | None
    added_leaves: int | None
    removed_leaves: int | None
    target_applied: bool | None
    globally_valid: bool
    # cost
    prompt_tokens: int
    output_tokens: int
    thought_tokens: int
    latency_s: float
    # provenance
    model: str
    constrained: bool
    finish_reason: str | None
    truncated: bool
    safety_verdict: str
    error: str | None = None
    corrupted_sample: list[str] | None = None


def _prompt(doc: ReviewForm, edit: EditRequest, arm: str) -> str:
    body = doc.model_dump_json(indent=None)
    if arm == "baseline":
        task = (
            "Apply the requested change and return the COMPLETE updated form. "
            "Every other field must be reproduced exactly as given."
        )
    else:
        task = (
            f"Return ONLY the single updated response object for index "
            f"{edit.target_index} (question {doc.responses[edit.target_index].question_id}). "
            "Do not return the rest of the form."
        )
    return (
        "You are editing a structured review form.\n\n"
        f"CURRENT FORM (JSON):\n{body}\n\n"
        f"REQUESTED CHANGE:\n{edit.instruction}\n\n"
        f"TASK:\n{task}"
    )


def run_chain(
    provider: Provider,
    size: str,
    seed: int,
    arm: str,
    turns: int,
    throttle: Throttle,
) -> Iterator[TurnRecord]:
    """One evolving document, `turns` sequential edits. Yields a record per turn.

    The document carries forward, so corruption introduced at turn 3 is still
    present at turn 8 — which is the compounding effect the literature reports
    and the reason turns are run as a chain rather than independently.
    """
    n = SIZES[size]
    doc = make_form(n, seed=seed)
    # The decoder is given the weaker schema it will actually accept; the real
    # ReviewForm, constraints and all, is what the result is validated against.
    schema: type[BaseModel] = (
        DecodableReviewForm if arm == "baseline" else Response
    )

    for turn in range(1, turns + 1):
        edit = make_edit(doc, turn, seed=seed)
        target = ("responses", edit.target_index)
        safety = classify_write(ReviewForm, target, operation="replace")
        prompt = _prompt(doc, edit, arm)

        # Rough projection for the throttle: prompt is ~1 token per 4 chars, and
        # the baseline arm emits roughly the document again.
        projected = len(prompt) // 4 + (len(prompt) // 4 if arm == "baseline" else 200)
        throttle.wait(projected)

        resp = provider.generate(prompt, schema, max_output_tokens=65_536)
        throttle.record(resp.prompt_tokens + resp.output_tokens)

        base = dict(
            size=size, n_responses=n, seed=seed, arm=arm, turn=turn,
            prompt_tokens=resp.prompt_tokens, output_tokens=resp.output_tokens,
            thought_tokens=int(resp.meta.get("thought_tokens", 0) or 0),
            latency_s=round(resp.latency_s, 3), model=resp.model,
            constrained=resp.constrained, finish_reason=resp.finish_reason,
            truncated=resp.truncated, safety_verdict=safety.explain(),
        )

        if resp.error or resp.parsed is None:
            yield TurnRecord(
                ok=False, integrity_rate=None, integrity_perfect=None,
                corrupted_leaves=None, added_leaves=None, removed_leaves=None,
                target_applied=None, globally_valid=False,
                error=resp.error or "provider returned no parseable object",
                **base,
            )
            return  # the chain's state is broken; do not fabricate later turns

        if arm == "baseline":
            # Re-validate against the REAL schema. A failure here is a result,
            # not an error: it means constrained decoding produced a document
            # the schema forbids, which is precisely what we are looking for.
            try:
                new_doc = ReviewForm.model_validate(resp.parsed.model_dump(mode="json"))
            except Exception as exc:
                yield TurnRecord(
                    ok=False, integrity_rate=None, integrity_perfect=None,
                    corrupted_leaves=None, added_leaves=None, removed_leaves=None,
                    target_applied=None, globally_valid=False,
                    error=f"baseline output failed real-schema validation: {exc}",
                    **base,
                )
                return
        else:
            result = splice(doc, target, resp.parsed)
            new_doc, ok, err = result.document, result.ok, result.error
            if not ok:
                yield TurnRecord(
                    ok=False, integrity_rate=None, integrity_perfect=None,
                    corrupted_leaves=None, added_leaves=None, removed_leaves=None,
                    target_applied=None, globally_valid=False, error=err, **base,
                )
                return

        integ = integrity(doc, new_doc, target)
        applied = target_applied(
            new_doc, target,
            {"answer": edit.new_answer, "confidence": edit.new_confidence},
        )
        yield TurnRecord(
            ok=True,
            integrity_rate=round(integ.rate, 6),
            integrity_perfect=integ.perfect,
            corrupted_leaves=len(integ.corrupted),
            added_leaves=len(integ.added),
            removed_leaves=len(integ.removed),
            target_applied=applied,
            globally_valid=True,
            corrupted_sample=sorted(integ.corrupted)[:10] or None,
            **base,
        )
        doc = new_doc


def run(
    provider: Provider,
    sizes: tuple[str, ...] = ("small", "medium", "large"),
    seeds: tuple[int, ...] = (0, 1, 2, 3, 4),
    arms: tuple[str, ...] = ARMS,
    turns: int = 10,
    out: FsPath | None = None,
) -> FsPath:
    """Run the grid, appending as we go, skipping chains already on disk."""
    out = out or (RUNS_DIR / "integrity.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    done: set[tuple[str, int, str]] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            # Only a chain that reached the final turn *successfully* is done.
            # A chain that died transiently must be re-runnable, or one dropped
            # connection permanently poisons that cell.
            if r["ok"] and r["turn"] == turns:
                done.add((r["size"], r["seed"], r["arm"]))

    throttle = Throttle()
    with out.open("a", encoding="utf-8") as fh:
        for size in sizes:
            for seed in seeds:
                for arm in arms:
                    if (size, seed, arm) in done:
                        print(f"skip  {size}/{seed}/{arm} (already complete)")
                        continue
                    print(f"run   {size}/{seed}/{arm} ...", flush=True)
                    for rec in run_chain(provider, size, seed, arm, turns, throttle):
                        fh.write(json.dumps(asdict(rec)) + "\n")
                        fh.flush()
                        flag = "" if rec.ok else "  ERROR"
                        rate = "n/a" if rec.integrity_rate is None else f"{rec.integrity_rate:.4f}"
                        print(
                            f"      turn {rec.turn:>2}  integrity={rate}"
                            f"  out={rec.output_tokens:>6}{flag}"
                        )
    return out
