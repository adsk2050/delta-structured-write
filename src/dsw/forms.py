"""The corpus: a nested Pydantic form, and a seeded generator for filled instances.

The shape is chosen to sit on the *unsolved* side of the line found in the
literature review. Dialogue state tracking already solved delta updates for flat
bags of independent slots (SOM-DST, MinTL, Rasa CALM). What it never had to
handle — and what makes this a real test — is nesting, a list whose elements are
themselves objects, cardinality constraints on that list, and a cross-field
invariant that leaves no trace in the JSON Schema.

`ReviewForm` has all four, on purpose:
  * nesting            Applicant, and Response inside a list
  * list-of-objects    responses: list[Response]
  * cardinality        min_length / max_length on responses
  * invisible invariant  the model_validator below
"""

from __future__ import annotations

import random
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator

Confidence = Literal["low", "medium", "high"]
Status = Literal["draft", "submitted", "under_review", "resolved"]


class Applicant(BaseModel):
    applicant_id: str
    full_name: str
    organisation: str
    country: str
    tier: Literal["standard", "priority", "gold"]


class Response(BaseModel):
    question_id: str
    question: str
    answer: str
    confidence: Confidence
    evidence: list[str] = Field(default_factory=list)


class ReviewForm(BaseModel):
    """A filled review form.

    The `model_validator` below is the point of the whole class. It encodes
    "a resolved form must have a resolution", which is a perfectly ordinary
    business rule and which is **completely invisible** in
    `ReviewForm.model_json_schema()`. No constrained decoder can enforce it and
    no projection can see it, so it is the honest test of whether the final
    revalidation step is load-bearing.
    """

    form_id: str
    title: str
    status: Status
    applicant: Applicant
    responses: Annotated[list[Response], Field(min_length=1, max_length=400)]
    reviewer_notes: str | None = None
    resolution: str | None = None

    @model_validator(mode="after")
    def _resolved_needs_resolution(self) -> ReviewForm:
        if self.status == "resolved" and not self.resolution:
            raise ValueError("a resolved form must carry a resolution")
        return self


class DecodableReviewForm(BaseModel):
    """`ReviewForm` minus the constraints the decoder refuses to accept.

    Measured 2026-09-07 against gemini-3.6-flash: a list carrying `minItems`
    /`maxItems` is **rejected outright with HTTP 400**, not silently ignored —
    at max=50 as well as max=400. Google's own structured-output documentation
    lists both keywords as supported, so this is a live instance of the
    coverage gap the literature review found across every engine.

    Keeping both models is deliberate and is part of the instrument, not a
    workaround. Generation is constrained by *this* schema, which is strictly
    weaker; validation always runs against the real `ReviewForm`. So the gap
    between what the decoder can promise and what the schema actually requires
    is visible in the results rather than hidden by them.
    """

    form_id: str
    title: str
    status: Status
    applicant: Applicant
    responses: list[Response]
    reviewer_notes: str | None = None
    resolution: str | None = None


# --------------------------------------------------------------------------
# Seeded generation of filled instances
# --------------------------------------------------------------------------

_TOPICS = [
    "data retention", "subprocessor disclosure", "incident response",
    "encryption at rest", "access review cadence", "vendor onboarding",
    "backup restoration testing", "least-privilege enforcement",
    "log immutability", "key rotation", "change management",
    "business continuity", "penetration testing", "asset inventory",
    "secure development lifecycle", "third-party risk scoring",
]
_CLAUSES = [
    "documented in the security addendum",
    "reviewed quarterly by the compliance lead",
    "enforced through automated policy checks",
    "covered by the parent organisation's programme",
    "tracked in the internal risk register",
    "audited annually by an external assessor",
    "handled by the platform team under a standing runbook",
    "subject to a documented exception approved by the CISO",
]
_ORGS = ["Northwind Systems", "Aldergate Health", "Peregrine Logistics",
         "Cobalt Analytics", "Fenwick Materials", "Tessellate Labs"]
_COUNTRIES = ["India", "Germany", "Canada", "Japan", "Brazil", "Netherlands"]
_NAMES = ["Priya Raman", "Tomas Lindqvist", "Amara Okonjo",
          "Kenji Watanabe", "Sofia Duarte", "Rafael Moreau"]


def _sentence(rng: random.Random, n_clauses: int) -> str:
    topic = rng.choice(_TOPICS)
    clauses = rng.sample(_CLAUSES, k=min(n_clauses, len(_CLAUSES)))
    return f"The {topic} process is " + ", and ".join(clauses) + "."


def make_form(n_responses: int, seed: int = 0, answer_clauses: int = 3) -> ReviewForm:
    """Build a deterministic filled form with `n_responses` responses.

    `answer_clauses` tunes answer length, and therefore document size, without
    changing the document's shape — so size can be varied as an independent
    variable while everything structural is held fixed.
    """
    rng = random.Random(seed)
    responses = [
        Response(
            question_id=f"Q{i + 1}",
            question=f"Describe how {rng.choice(_TOPICS)} is governed.",
            answer=_sentence(rng, answer_clauses),
            confidence=rng.choice(["low", "medium", "high"]),
            evidence=[
                f"exhibit-{rng.choice('ABCDEFGH')}-{rng.randint(10, 99)}"
                for _ in range(rng.randint(1, 3))
            ],
        )
        for i in range(n_responses)
    ]
    return ReviewForm(
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


# Sizes are named rather than numeric so results stay comparable if the
# generator's verbosity is ever retuned. Actual token counts are measured at
# run time and recorded per call, never assumed.
SIZES: dict[str, int] = {"small": 20, "medium": 70, "large": 220}


class EditRequest(BaseModel):
    """One turn's instruction, plus the ground truth needed to score it."""

    target_index: int
    instruction: str
    new_answer: str
    new_confidence: Confidence

    @property
    def path(self) -> tuple[str | int, ...]:
        return ("responses", self.target_index)


def make_edit(form: ReviewForm, turn: int, seed: int = 0) -> EditRequest:
    """Pick a response to rewrite. Deterministic given (form size, turn, seed)."""
    rng = random.Random((seed + 1) * 100_003 + turn)
    idx = rng.randrange(len(form.responses))
    qid = form.responses[idx].question_id
    new_answer = (
        f"Updated at turn {turn}: " + _sentence(rng, 2)
    )
    new_conf: Confidence = rng.choice(["low", "medium", "high"])
    return EditRequest(
        target_index=idx,
        instruction=(
            f"Change the answer to {qid} to exactly: {new_answer!r} "
            f"and set its confidence to {new_conf!r}. Change nothing else."
        ),
        new_answer=new_answer,
        new_confidence=new_conf,
    )
