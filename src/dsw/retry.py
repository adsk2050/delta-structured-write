"""The retry experiment: when a structured output is rejected, what do you resend?

The integrity experiment asked what regeneration does to fields nobody asked
about, and answered "nothing" -- under constrained decoding the baseline arm was
perfect for twelve turns. This asks the other question. Not *does regeneration
corrupt what you did not ask for*, but *does regeneration reliably fix what you
did* -- and what it costs to find out.

Two arms, and they share their first attempt so nothing about the comparison
depends on first-attempt luck:

    shared    one call: "resolve this form and satisfy the closure rules"
    whole     on rejection, resend the document plus the violations; the model
              re-emits the entire document. This is Instructor's reask, and it
              is what essentially every production system does today.
    fragment  on rejection, take each violation's repair path, project the
              sub-schema there, generate only that value, splice, recheck.

Both arms are shown **identical context** -- the whole document and the whole
violation list -- every time. The fragment arm could be given far less, and a
real system would, but withholding input from one arm would confound the
comparison with a prompt effect. The saving measured here is therefore purely
on the output side, which is the conservative claim.

The metric this exists for is `introduced`: violations present after a repair
step that were not present before it. A whole-document reask is a fresh sample
of every field, so fixing violation A can break B; a fragment repair rewrites
one subtree and leaves the rest byte-identical, so the violation count outside
that subtree cannot move. Whether that difference shows up in practice is the
open question -- the harness does not assume it.
"""

from __future__ import annotations

import json
import time
from dataclasses import asdict, dataclass, field
from pathlib import Path as FsPath
from typing import Iterator

from pydantic import BaseModel

from .config import RUNS_DIR
from .constraints import (
    RULES_IN_PROSE, Violation, check_all, make_resolvable_form, pydantic_locs,
)
from .experiment import Throttle
from .forms import DecodableReviewForm, ReviewForm, SIZES
from .metrics import integrity_outside
from .projection import Path, classify_write, project, walk
from .providers import Provider
from .splice import splice

ARMS = ("whole", "fragment")


# --------------------------------------------------------------------------
# Localisation
# --------------------------------------------------------------------------

def localisation_of(violation: Violation, free_locs: set[tuple]) -> str:
    """How the repair path for this violation was obtained.

    `exact`          Pydantic's own ValidationError pointed at it. Free.
    `hinted`         we had to declare the path on the rule by hand.
    `unlocalisable`  no path at all; a fragment retry has nothing to aim at and
                     must fall back to rewriting the whole document.
    """
    if not violation.localisable:
        return "unlocalisable"
    return "exact" if violation.repair_paths[0] in free_locs else "hinted"


# --------------------------------------------------------------------------
# Prompts
# --------------------------------------------------------------------------

def _preamble(doc: DecodableReviewForm) -> str:
    return (
        "You are closing out a structured review form.\n\n"
        f"{RULES_IN_PROSE}\n\n"
        f"CURRENT FORM (JSON):\n{doc.model_dump_json(indent=None)}\n"
    )


def _violation_block(violations: list[Violation]) -> str:
    lines = "\n".join(f"  - [{v.rule}] {v.message}" for v in violations)
    return f"\nTHE FORM WAS REJECTED. Violations:\n{lines}\n"


def prompt_first(doc: DecodableReviewForm, state_rules: bool = False) -> str:
    """The first attempt, with or without the closure rules spelled out.

    Withholding them is the default because it is the ordinary production
    failure: the business rules live in the validator, the prompt
    under-specifies, and the model finds out only when the document comes back
    rejected. That is exactly the situation a reask loop exists for.

    Told the rules up front, this model simply satisfies them. Measured twice,
    at `small` and at `large` — three violations each, both fixed in a single
    pass — so the rules-stated condition produces no retry to study at all.
    Both arms see every violation spelled out from the first repair onward, so
    nothing about the comparison between them depends on this choice.
    """
    preamble = _preamble(doc) if state_rules else (
        "You are closing out a structured review form.\n\n"
        f"CURRENT FORM (JSON):\n{doc.model_dump_json(indent=None)}\n"
    )
    return preamble + (
        '\nTASK:\nSet `status` to "resolved" and record the outcome. Change as '
        "little else as possible. Return the COMPLETE updated form."
    )


def prompt_whole_repair(doc: DecodableReviewForm, violations: list[Violation]) -> str:
    return _preamble(doc) + _violation_block(violations) + (
        "\nTASK:\nFix every violation listed and return the COMPLETE updated "
        "form. Every other field must be reproduced exactly as given."
    )


def prompt_fragment_repair(
    doc: DecodableReviewForm, violations: list[Violation], target: Violation
) -> str:
    pointer = "".join(f"/{s}" for s in target.repair_paths[0])
    return _preamble(doc) + _violation_block(violations) + (
        f"\nTASK:\nReturn ONLY the replacement value for `{pointer}`, fixing "
        f"this one violation:\n  [{target.rule}] {target.message}\n"
        "Do not return the rest of the form."
    )


# --------------------------------------------------------------------------
# Records
# --------------------------------------------------------------------------

@dataclass
class StepRecord:
    """One model call inside one episode."""

    size: str
    n_responses: int
    seed: int
    planted: int
    rules_first: bool   # were the closure rules stated on the first attempt?
    arm: str            # "shared" | "whole" | "fragment"
    round: int          # 0 = the shared first attempt
    call: int           # call index within the round (fragment does several)
    ok: bool
    # the question
    violations_before: int
    violations_after: int | None
    fixed: int | None
    introduced: int | None          # the oscillation metric
    violations_after_keys: list[str] | None
    # what was aimed at
    target_rule: str | None
    target_path: str | None
    localisation: str | None
    # collateral
    integrity_rate: float | None
    corrupted_leaves: int | None
    corrupted_sample: list[str] | None
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
    safety_verdict: str | None
    error: str | None = None
    document: str | None = None     # stored on the shared step only, for resume


def _keys(violations: list[Violation]) -> set[tuple[str, str]]:
    return {v.key for v in violations}


def _base(resp, size: str, n: int, seed: int, planted: int, arm: str,
          rnd: int, call: int, rules_first: bool) -> dict:
    return dict(
        size=size, n_responses=n, seed=seed, planted=planted, arm=arm,
        round=rnd, call=call, rules_first=rules_first,
        prompt_tokens=resp.prompt_tokens, output_tokens=resp.output_tokens,
        thought_tokens=int(resp.meta.get("thought_tokens", 0) or 0),
        latency_s=round(resp.latency_s, 3), model=resp.model,
        constrained=resp.constrained, finish_reason=resp.finish_reason,
        truncated=resp.truncated,
    )


def _failed(base: dict, before: int, error: str, safety: str | None = None) -> StepRecord:
    return StepRecord(
        ok=False, violations_before=before, violations_after=None,
        fixed=None, introduced=None, violations_after_keys=None,
        target_rule=None, target_path=None, localisation=None,
        integrity_rate=None, corrupted_leaves=None, corrupted_sample=None,
        safety_verdict=safety, error=error, **base,
    )


# --------------------------------------------------------------------------
# The fragment value
# --------------------------------------------------------------------------

def fragment_value(path: Path, parsed: BaseModel) -> object:
    """Unwrap what `project` produced back into a plain spliceable value.

    `project` returns the target model untouched when the target *is* a model,
    and wraps a scalar in a one-field object otherwise, because Gemini requires
    an object at the root of a structured response. The splice needs the value,
    not the wrapper.
    """
    target, _ = walk(DecodableReviewForm, path)
    payload = parsed.model_dump(mode="json")
    if isinstance(target, type) and issubclass(target, BaseModel):
        return payload
    return payload["value"]


# --------------------------------------------------------------------------
# The two repair loops
# --------------------------------------------------------------------------

def _repair_whole(
    provider: Provider, doc: DecodableReviewForm, violations: list[Violation],
    size: str, n: int, seed: int, planted: int, rnd: int, throttle: Throttle,
    rules_first: bool,
) -> tuple[DecodableReviewForm | None, StepRecord]:
    prompt = prompt_whole_repair(doc, violations)
    throttle.wait(len(prompt) // 4 * 2)
    resp = provider.generate(prompt, DecodableReviewForm, max_output_tokens=65_536)
    throttle.record(resp.prompt_tokens + resp.output_tokens)
    base = _base(resp, size, n, seed, planted, "whole", rnd, 0, rules_first)
    before = _keys(violations)

    if resp.error or resp.parsed is None:
        return None, _failed(base, len(violations),
                             resp.error or "provider returned no parseable object")
    try:
        new_doc = DecodableReviewForm.model_validate(resp.parsed.model_dump(mode="json"))
    except Exception as exc:
        # Not an error: a document the real schema forbids is a result.
        return None, _failed(base, len(violations),
                             f"repair failed real-schema validation: {exc}")

    after = check_all(new_doc)
    # "Untouched" is everything outside the union of paths the violations point
    # at -- the whole arm was licensed to write to all of them.
    targets = tuple(p for v in violations for p in v.repair_paths) or ((),)
    integ = integrity_outside(doc, new_doc, targets)
    return new_doc, StepRecord(
        ok=True,
        violations_before=len(violations), violations_after=len(after),
        fixed=len(before - _keys(after)), introduced=len(_keys(after) - before),
        violations_after_keys=sorted(f"{r}{p}" for r, p in _keys(after)),
        target_rule=None, target_path=None, localisation=None,
        integrity_rate=round(integ.rate, 6),
        corrupted_leaves=len(integ.corrupted),
        corrupted_sample=sorted(integ.corrupted)[:10] or None,
        safety_verdict=None, **base,
    )


def _repair_fragment(
    provider: Provider, doc: DecodableReviewForm, violations: list[Violation],
    target: Violation, size: str, n: int, seed: int, planted: int,
    rnd: int, call: int, free_locs: set[tuple], throttle: Throttle,
    rules_first: bool,
) -> tuple[DecodableReviewForm | None, StepRecord]:
    path = target.repair_paths[0]
    pointer = "".join(f"/{s}" for s in path)
    loc_kind = localisation_of(target, free_locs)
    safety = classify_write(DecodableReviewForm, path, operation="replace").explain()

    schema = project(DecodableReviewForm, path)
    prompt = prompt_fragment_repair(doc, violations, target)
    throttle.wait(len(prompt) // 4 + 300)
    resp = provider.generate(prompt, schema, max_output_tokens=4_096)
    throttle.record(resp.prompt_tokens + resp.output_tokens)
    base = _base(resp, size, n, seed, planted, "fragment", rnd, call, rules_first)
    before = _keys(violations)

    if resp.error or resp.parsed is None:
        rec = _failed(base, len(violations),
                      resp.error or "provider returned no parseable object", safety)
        rec.target_rule, rec.target_path, rec.localisation = target.rule, pointer, loc_kind
        return None, rec

    result = splice(doc, path, fragment_value(path, resp.parsed))
    if not result.ok or result.document is None:
        rec = _failed(base, len(violations), result.error or "splice failed", safety)
        rec.target_rule, rec.target_path, rec.localisation = target.rule, pointer, loc_kind
        return None, rec

    new_doc = result.document
    after = check_all(new_doc)
    integ = integrity_outside(doc, new_doc, (path,))
    return new_doc, StepRecord(
        ok=True,
        violations_before=len(violations), violations_after=len(after),
        fixed=len(before - _keys(after)), introduced=len(_keys(after) - before),
        violations_after_keys=sorted(f"{r}{p}" for r, p in _keys(after)),
        target_rule=target.rule, target_path=pointer, localisation=loc_kind,
        integrity_rate=round(integ.rate, 6),
        corrupted_leaves=len(integ.corrupted),
        corrupted_sample=sorted(integ.corrupted)[:10] or None,
        safety_verdict=safety, **base,
    )


# --------------------------------------------------------------------------
# One episode
# --------------------------------------------------------------------------

def run_episode(
    provider: Provider,
    size: str,
    seed: int,
    planted: int,
    arms: tuple[str, ...],
    max_rounds: int,
    throttle: Throttle,
    rules_first: bool = False,
    resume_document: str | None = None,
) -> Iterator[StepRecord]:
    """One first attempt, then a repair loop per arm from the same starting point.

    The first attempt is shared and logged once. That is not only cheaper: it
    removes first-attempt variance from the comparison entirely, so any
    difference between the arms is a difference in how they repair.
    """
    n = SIZES[size]
    start = make_resolvable_form(n, seed=seed, planted=planted)

    if resume_document is not None:
        doc1 = DecodableReviewForm.model_validate_json(resume_document)
    else:
        prompt = prompt_first(start, state_rules=rules_first)
        throttle.wait(len(prompt) // 4 * 2)
        resp = provider.generate(prompt, DecodableReviewForm, max_output_tokens=65_536)
        throttle.record(resp.prompt_tokens + resp.output_tokens)
        base = _base(resp, size, n, seed, planted, "shared", 0, 0, rules_first)
        expected = len(check_all(start.model_copy(update={"status": "resolved"})))

        if resp.error or resp.parsed is None:
            yield _failed(base, expected,
                          resp.error or "provider returned no parseable object")
            return
        try:
            doc1 = DecodableReviewForm.model_validate(resp.parsed.model_dump(mode="json"))
        except Exception as exc:
            yield _failed(base, expected, f"first attempt failed validation: {exc}")
            return

        after = check_all(doc1)
        integ = integrity_outside(
            start, doc1,
            tuple(p for v in check_all(start.model_copy(update={"status": "resolved"}))
                  for p in v.repair_paths) + (("status",),),
        )
        yield StepRecord(
            ok=True,
            violations_before=expected, violations_after=len(after),
            fixed=None, introduced=None,
            violations_after_keys=sorted(f"{r}{p}" for r, p in _keys(after)),
            target_rule=None, target_path=None, localisation=None,
            integrity_rate=round(integ.rate, 6),
            corrupted_leaves=len(integ.corrupted),
            corrupted_sample=sorted(integ.corrupted)[:10] or None,
            safety_verdict=None, document=doc1.model_dump_json(), **base,
        )

    if not check_all(doc1):
        return  # the first attempt got it right; there is nothing to retry

    for arm in arms:
        doc = doc1
        for rnd in range(1, max_rounds + 1):
            violations = check_all(doc)
            if not violations:
                break
            free_locs = set(pydantic_locs(doc))

            if arm == "whole":
                doc_next, rec = _repair_whole(
                    provider, doc, violations, size, n, seed, planted, rnd,
                    throttle, rules_first,
                )
                yield rec
                if doc_next is None:
                    break
                doc = doc_next
                continue

            # Fragment: one call per outstanding localisable violation, so a
            # "round" means the same thing in both arms and rounds-to-valid is
            # a fair comparison. Calls and tokens are then the honest cost.
            targets = [v for v in violations if v.localisable]
            if not targets:
                yield _failed(
                    _base(_null_response(provider), size, n, seed, planted,
                          "fragment", rnd, 0, rules_first),
                    len(violations),
                    "no violation carries a repair path; fragment retry cannot aim",
                )
                break
            broke = False
            for call, target in enumerate(targets):
                doc_next, rec = _repair_fragment(
                    provider, doc, check_all(doc), target, size, n, seed,
                    planted, rnd, call, free_locs, throttle, rules_first,
                )
                yield rec
                if doc_next is None:
                    broke = True
                    break
                doc = doc_next
                if not check_all(doc):
                    break
            if broke:
                break


class _NullResponse:
    prompt_tokens = output_tokens = 0
    latency_s = 0.0
    constrained = True
    finish_reason = None
    truncated = False
    meta: dict = {}

    def __init__(self, model: str) -> None:
        self.model = model


def _null_response(provider: Provider):
    """A zero-cost stand-in, so a step that never reached the API still logs."""
    return _NullResponse(getattr(provider, "model", "n/a"))


# --------------------------------------------------------------------------
# The grid
# --------------------------------------------------------------------------

def run(
    provider: Provider,
    sizes: tuple[str, ...] = ("small",),
    seeds: tuple[int, ...] = (0, 1, 2),
    planted: int = 2,
    arms: tuple[str, ...] = ARMS,
    max_rounds: int = 3,
    rules_first: bool = False,
    out: FsPath | None = None,
) -> FsPath:
    """Run the episode grid, appending as we go, reusing anything already on disk."""
    out = out or (RUNS_DIR / "retry.jsonl")
    out.parent.mkdir(parents=True, exist_ok=True)

    # Resume at episode granularity, and reuse a shared first attempt even when
    # the arms after it died -- that call is the expensive one and it is
    # deterministic given the episode, so re-buying it would be waste.
    shared: dict[tuple, str] = {}
    done: set[tuple] = set()
    if out.exists():
        for line in out.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            r = json.loads(line)
            key = (r["size"], r["seed"], r["planted"], r.get("rules_first", True))
            if r["arm"] == "shared" and r["ok"] and r.get("document"):
                shared[key] = r["document"]
            if r["arm"] in ARMS and r["ok"] and r["violations_after"] == 0:
                done.add(key + (r["arm"],))

    throttle = Throttle()
    with out.open("a", encoding="utf-8") as fh:
        for size in sizes:
            for seed in seeds:
                key = (size, seed, planted, rules_first)
                todo = tuple(a for a in arms if key + (a,) not in done)
                if not todo:
                    print(f"skip  {size}/{seed}/p{planted} (both arms complete)")
                    continue
                print(f"run   {size}/{seed}/p{planted} arms={todo} ...", flush=True)
                for rec in run_episode(
                    provider, size, seed, planted, todo, max_rounds, throttle,
                    rules_first=rules_first, resume_document=shared.get(key),
                ):
                    fh.write(json.dumps(asdict(rec)) + "\n")
                    fh.flush()
                    flag = "" if rec.ok else "  ERROR"
                    va = "-" if rec.violations_after is None else rec.violations_after
                    intro = "" if not rec.introduced else f"  INTRODUCED={rec.introduced}"
                    print(
                        f"      {rec.arm:<8} r{rec.round}.{rec.call}"
                        f"  viol {rec.violations_before}->{va}"
                        f"  out={rec.output_tokens:>6}{intro}{flag}"
                    )
                    if rec.error:
                        print(f"        {rec.error[:160]}")
    return out
