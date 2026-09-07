"""The closure rules, and the question of where a violation *points*.

The integrity experiment needed one invariant that no schema can see. The retry
experiment needs a small *network* of them, because the effect it is looking for
-- a repair that fixes one violation and creates another -- cannot exist with a
single rule. Three rules, all gated on `status == "resolved"`, so a freshly
generated form is valid and the whole rule set activates the moment a reviewer
tries to close it. That is an ordinary pre-submission gate, not a contrivance.

  R1  a resolved form carries a resolution
  R2  a high-confidence answer cites at least two exhibits
  R3  a resolved form has no low-confidence answers

The coupling that makes oscillation possible is between R2 and R3. The obvious
repair for R3 -- promote a low-confidence answer -- lands on `high` about half
the time by default, and a promotion to `high` immediately owes R2 two exhibits.
`medium` is the repair that costs nothing. So a careless fix creates work and a
careful one does not, which is exactly the behaviour the experiment measures
rather than assumes.

Each rule reports **where it is repaired**. That is the part with research
content: a retry loop can only be targeted if something tells it the path, and
`Violation.repair_paths` is that something. `pydantic_locs` below measures the
alternative -- what Pydantic's own `ValidationError.loc` would have given for
free -- because the difference between the two is a finding, not a detail.
"""

from __future__ import annotations

import random
from dataclasses import dataclass

from pydantic import BaseModel, ValidationError, model_validator

from .forms import Applicant, DecodableReviewForm, Response, Status
from .projection import Path

MIN_RESOLUTION_CHARS = 20
MIN_EVIDENCE_FOR_HIGH = 2


@dataclass(frozen=True)
class Violation:
    """One broken rule, and the path a targeted repair would write to.

    `repair_paths` empty means the rule is real but not localisable, in which
    case a fragment retry has nothing to aim at and must fall back to rewriting
    the whole document. How often that happens is measured, not assumed.
    """

    rule: str
    message: str
    repair_paths: tuple[Path, ...] = ()

    @property
    def key(self) -> tuple[str, str]:
        """Stable identity, so the same violation can be recognised across steps."""
        first = self.repair_paths[0] if self.repair_paths else ()
        return self.rule, "".join(f"/{s}" for s in first)

    @property
    def localisable(self) -> bool:
        return bool(self.repair_paths)


# --------------------------------------------------------------------------
# The rules
# --------------------------------------------------------------------------

def check_all(form: DecodableReviewForm) -> list[Violation]:
    """Every closure rule the form currently breaks. Empty means it may close.

    Deliberately a plain function over a validated model rather than a Pydantic
    validator. The generation schemas stay rule-free -- the decoder could not
    enforce these anyway -- so keeping the check outside the model is what lets
    the same instrument report *which* rule broke and *where* it is repaired.
    """
    if form.status != "resolved":
        return []

    out: list[Violation] = []
    resolution = (form.resolution or "").strip()

    if not resolution:
        out.append(Violation(
            "R1", "a resolved form must carry a resolution", (("resolution",),)
        ))
    elif len(resolution) < MIN_RESOLUTION_CHARS:
        out.append(Violation(
            "R1",
            f"the resolution must be at least {MIN_RESOLUTION_CHARS} characters "
            f"(it is {len(resolution)})",
            (("resolution",),),
        ))

    for i, r in enumerate(form.responses):
        if r.confidence == "high" and len(r.evidence) < MIN_EVIDENCE_FOR_HIGH:
            out.append(Violation(
                "R2",
                f"response {r.question_id} is high-confidence but cites "
                f"{len(r.evidence)} exhibit(s); at least "
                f"{MIN_EVIDENCE_FOR_HIGH} are required",
                (("responses", i),),
            ))
        if r.confidence == "low":
            out.append(Violation(
                "R3",
                f"response {r.question_id} is low-confidence, which a resolved "
                f"form may not contain",
                (("responses", i),),
            ))
    return out


RULES_IN_PROSE = f"""\
CLOSURE RULES. A form with status "resolved" must satisfy all three:
  R1. `resolution` must be present and at least {MIN_RESOLUTION_CHARS} characters.
  R2. every response with confidence "high" must list at least \
{MIN_EVIDENCE_FOR_HIGH} items in `evidence`.
  R3. no response may have confidence "low".
These rules are NOT part of the JSON schema. Nothing will stop you emitting a \
form that breaks them, so check them yourself."""


# --------------------------------------------------------------------------
# What Pydantic would have told us on its own
# --------------------------------------------------------------------------
# The rules above hand us a repair path. The question worth measuring is whether
# we needed to: a validator placed on the right model yields `loc` pointing
# straight at the offending node, and `loc` IS a JSON pointer. So R2, which is a
# property of a single response, is declared on Response and localises itself.
# R1 and R3 need `status`, which lives on the form, so their `loc` is the empty
# tuple and points at nothing. Where you put the validator decides whether a
# retry can be aimed.

class StrictResponse(Response):
    """R2 as Pydantic sees it -- a per-item rule, so `loc` is exact."""

    @model_validator(mode="after")
    def _high_needs_evidence(self) -> StrictResponse:
        if self.confidence == "high" and len(self.evidence) < MIN_EVIDENCE_FOR_HIGH:
            raise ValueError(
                f"high confidence requires >= {MIN_EVIDENCE_FOR_HIGH} evidence items"
            )
        return self


class StrictReviewForm(BaseModel):
    """R1 and R3 as Pydantic sees them -- form-level, so `loc` is `()`."""

    form_id: str
    title: str
    status: Status
    applicant: Applicant
    responses: list[StrictResponse]
    reviewer_notes: str | None = None
    resolution: str | None = None

    @model_validator(mode="after")
    def _closure(self) -> StrictReviewForm:
        if self.status != "resolved":
            return self
        if not (self.resolution or "").strip():
            raise ValueError("a resolved form must carry a resolution")
        if any(r.confidence == "low" for r in self.responses):
            raise ValueError("a resolved form may not contain low-confidence responses")
        return self


def pydantic_locs(form: DecodableReviewForm) -> list[tuple[str | int, ...]]:
    """The `loc` tuples Pydantic produces for the same document.

    Recorded alongside our own repair paths so the write-up can say how much of
    the localisation came free from the validator and how much had to be
    declared by hand.
    """
    try:
        StrictReviewForm.model_validate(form.model_dump(mode="json"))
    except ValidationError as exc:
        return [tuple(e["loc"]) for e in exc.errors()]
    return []


# --------------------------------------------------------------------------
# A form with a known number of planted violations
# --------------------------------------------------------------------------

def make_resolvable_form(
    n_responses: int,
    seed: int = 0,
    planted: int = 4,
    answer_clauses: int = 3,
) -> DecodableReviewForm:
    """A valid `under_review` form that breaks exactly `planted` + 1 rules once resolved.

    Violation count is the variable the retry loop is most sensitive to, so it is
    planted rather than left to the seed generator. Half the planted violations
    are R2 (high confidence, one exhibit) and half are R3 (low confidence); R1
    always fires because `resolution` starts empty, which is why the total is
    `planted` + 1.

    Every other response is made clean on purpose. A form where a third of the
    rows are broken would measure the model's stamina, not the retry mechanism.
    """
    from .forms import _COUNTRIES, _NAMES, _ORGS, _TOPICS, _sentence

    if planted > n_responses:
        raise ValueError(f"cannot plant {planted} violations in {n_responses} responses")

    rng = random.Random(seed)
    faulty = sorted(rng.sample(range(n_responses), k=planted))
    split = planted // 2 + planted % 2
    r2_faults = set(faulty[:split])    # high confidence, one exhibit
    r3_faults = set(faulty[split:])    # low confidence

    responses: list[Response] = []
    for i in range(n_responses):
        if i in r2_faults:
            confidence, n_evidence = "high", 1
        elif i in r3_faults:
            # Exactly one exhibit, so the trap is deterministic rather than
            # left to the seed: promoting this response to "high" always trades
            # its R3 violation for an R2 one, while "medium" always costs
            # nothing. A low-confidence answer citing a single exhibit is the
            # natural shape anyway.
            confidence, n_evidence = "low", 1
        else:
            # Clean: medium is unconditionally fine, high is fine with two.
            confidence = rng.choice(["medium", "medium", "high"])
            n_evidence = 2 if confidence == "high" else rng.randint(1, 2)
        responses.append(Response(
            question_id=f"Q{i + 1}",
            question=f"Describe how {rng.choice(_TOPICS)} is governed.",
            answer=_sentence(rng, answer_clauses),
            confidence=confidence,  # type: ignore[arg-type]
            evidence=[
                f"exhibit-{rng.choice('ABCDEFGH')}-{rng.randint(10, 99)}"
                for _ in range(n_evidence)
            ],
        ))

    return DecodableReviewForm(
        form_id=f"RF-{seed:04d}",
        title=f"Vendor security review {seed:04d}",
        status="under_review",
        applicant=Applicant(
            applicant_id=f"AP-{seed:04d}",
            full_name=rng.choice(_NAMES),
            organisation=rng.choice(_ORGS),
            country=rng.choice(_COUNTRIES),
            tier=rng.choice(["standard", "priority", "gold"]),
        ),
        responses=responses,
        reviewer_notes="Initial pass complete; awaiting clarifications.",
    )


def planted_violations(form: DecodableReviewForm) -> list[Violation]:
    """What `check_all` *would* report once the form is resolved. For dry runs."""
    return check_all(form.model_copy(update={"status": "resolved"}))
