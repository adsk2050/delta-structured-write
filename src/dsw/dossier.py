"""A structurally hard corpus, built to sit where `ReviewForm` did not.

[`notes/05`](../../notes/05-what-the-experiments-did-not-test.md) records why
this exists. `ReviewForm` is three levels deep, has no unions, no recursion, no
lists inside lists and one flat cross-field rule, so the three nulls it produced
say only that *shallow* schemas are regenerated reliably. Every property the
literature blames for structural failure was missing from it.

`Dossier` puts them all back:

  depth 5            Dossier -> Section -> SubSection -> Block -> Citation
  a union            three block kinds, discriminated on `kind`
  list inside list   TableBlock.rows[].cells[]
  a union in a list  Section.blocks is a list of union members
  bounded recursion  SubSection repeats Section's block structure

and four invariants that no JSON Schema can express, chosen so that each one
fails in a *different* way:

  D1  a high or critical finding needs >= 2 citations and a remediation
      -> local to one block. Repairable in place.
  D2  every citation's `source_id` must name a source declared in the dossier
      header -> REFERENTIAL, and the reference spans the whole document. This
      is the one that should break first when the middle of a long context
      starts to blur, because the deep content must stay consistent with a
      registry declared far away.
  D3  every row of a table must have exactly as many cells as the table has
      columns -> structural, and it is Displacement Rate in miniature.
  D4  every id in the document must be unique -> GLOBAL. It is the
      `uniqueItems` case, it is not localisable to any one path, and it is
      therefore the fallback case `RETRY.md` could only assert at 0%.

The strict/decodable split is the same idiom `forms.py` established, and for the
same reason: `Block` is a genuine discriminated union, which engines are
documented to degrade (Gemini and Outlines both flatten `oneOf` to `anyOf`), so
generation runs against a flattened `DecodableBlock` whose branch shape is
checked afterwards. The gap between what the decoder promises and what the
schema means stays visible in the results instead of being hidden by them.
"""

from __future__ import annotations

import random
from typing import Annotated, Literal

from pydantic import BaseModel, Field

Severity = Literal["info", "low", "medium", "high", "critical"]
DossierStatus = Literal["draft", "in_review", "signed_off"]
BlockKind = Literal["narrative", "table", "finding"]
SEVERE: frozenset[str] = frozenset({"high", "critical"})
MIN_CITATIONS_FOR_SEVERE = 2


# --------------------------------------------------------------------------
# Leaves
# --------------------------------------------------------------------------

class Source(BaseModel):
    """A declared source. Lives in the dossier header; cited from anywhere."""

    source_id: str
    title: str
    publisher: str


class Citation(BaseModel):
    source_id: str
    locator: str
    quote: str


class TableRow(BaseModel):
    row_id: str
    cells: list[str]


# --------------------------------------------------------------------------
# The union
# --------------------------------------------------------------------------

class NarrativeBlock(BaseModel):
    kind: Literal["narrative"] = "narrative"
    block_id: str
    text: str
    citations: list[Citation] = Field(default_factory=list)


class TableBlock(BaseModel):
    kind: Literal["table"] = "table"
    block_id: str
    caption: str
    columns: list[str]
    rows: list[TableRow]


class FindingBlock(BaseModel):
    kind: Literal["finding"] = "finding"
    block_id: str
    severity: Severity
    statement: str
    citations: list[Citation] = Field(default_factory=list)
    remediation: str | None = None


Block = Annotated[
    NarrativeBlock | TableBlock | FindingBlock, Field(discriminator="kind")
]


class SubSection(BaseModel):
    subsection_id: str
    heading: str
    blocks: list[Block]


class Section(BaseModel):
    section_id: str
    heading: str
    blocks: list[Block]
    subsections: list[SubSection]


class Dossier(BaseModel):
    dossier_id: str
    title: str
    status: DossierStatus
    sources: list[Source]
    sections: list[Section]
    summary: str | None = None


# --------------------------------------------------------------------------
# The decodable twin
# --------------------------------------------------------------------------
# A flattened block: every branch's fields present and optional, `kind` carrying
# the branch. Strictly weaker than the union, and the branch shape becomes one
# more invariant the decoder cannot enforce (D5 in `dossier_rules.py`).

class DecodableBlock(BaseModel):
    kind: BlockKind
    block_id: str
    # narrative
    text: str | None = None
    # table
    caption: str | None = None
    columns: list[str] | None = None
    rows: list[TableRow] | None = None
    # finding
    severity: Severity | None = None
    statement: str | None = None
    remediation: str | None = None
    # shared by narrative and finding
    citations: list[Citation] = Field(default_factory=list)


class DecodableSubSection(BaseModel):
    subsection_id: str
    heading: str
    blocks: list[DecodableBlock]


class DecodableSection(BaseModel):
    section_id: str
    heading: str
    blocks: list[DecodableBlock]
    subsections: list[DecodableSubSection]


class DecodableDossier(BaseModel):
    """What the decoder is actually given. See the module docstring."""

    dossier_id: str
    title: str
    status: DossierStatus
    sources: list[Source]
    sections: list[DecodableSection]
    summary: str | None = None


# --------------------------------------------------------------------------
# Seeded generation
# --------------------------------------------------------------------------

_AREAS = [
    "access control", "data residency", "incident response", "key management",
    "vendor oversight", "change control", "logging", "resilience",
    "privacy notices", "retention", "secure build", "threat modelling",
]
_PUBLISHERS = ["ISO", "NIST", "ENISA", "internal audit", "the platform team"]
_VERBS = ["is documented", "was reviewed", "remains outstanding",
          "has been remediated", "is tracked", "awaits sign-off"]
_COLUMNS = [
    ["control", "owner", "status"],
    ["asset", "classification", "location", "reviewed"],
    ["risk", "likelihood", "impact"],
]


def _sentence(rng: random.Random, area: str) -> str:
    return (f"The {area} programme {rng.choice(_VERBS)} and is overseen by "
            f"{rng.choice(_PUBLISHERS)}.")


def _citation(rng: random.Random, sources: list[Source]) -> Citation:
    src = rng.choice(sources)
    return Citation(
        source_id=src.source_id,
        locator=f"§{rng.randint(1, 12)}.{rng.randint(1, 9)}",
        quote=f"…{rng.choice(_AREAS)} shall be reviewed at least annually…",
    )


def _blocks(
    rng: random.Random, sources: list[Source], prefix: str, n: int
) -> list[DecodableBlock]:
    out: list[DecodableBlock] = []
    for i in range(n):
        bid = f"{prefix}-B{i + 1}"
        kind = rng.choice(["narrative", "narrative", "table", "finding"])
        area = rng.choice(_AREAS)
        if kind == "narrative":
            out.append(DecodableBlock(
                kind="narrative", block_id=bid,
                text=_sentence(rng, area),
                citations=[_citation(rng, sources) for _ in range(rng.randint(1, 2))],
            ))
        elif kind == "table":
            cols = rng.choice(_COLUMNS)
            out.append(DecodableBlock(
                kind="table", block_id=bid,
                caption=f"{area.title()} register",
                columns=list(cols),
                rows=[
                    TableRow(
                        row_id=f"{bid}-R{r + 1}",
                        # Exactly len(cols): D3 holds in a freshly built dossier.
                        cells=[f"{rng.choice(_AREAS)}-{rng.randint(10, 99)}"
                               for _ in cols],
                    )
                    for r in range(rng.randint(2, 3))
                ],
            ))
        else:
            severity: Severity = rng.choice(["info", "low", "medium", "high"])
            n_cit = MIN_CITATIONS_FOR_SEVERE if severity in SEVERE else rng.randint(1, 2)
            out.append(DecodableBlock(
                kind="finding", block_id=bid, severity=severity,
                statement=f"{area.title()} gap: {_sentence(rng, area)}",
                citations=[_citation(rng, sources) for _ in range(n_cit)],
                remediation=(f"Assign an owner for {area} and re-test."
                             if severity in SEVERE else None),
            ))
    return out


def make_dossier(
    n_sections: int,
    seed: int = 0,
    subsections_per_section: int = 2,
    blocks_per_container: int = 2,
    n_sources: int = 6,
) -> DecodableDossier:
    """A valid dossier. Every rule in `dossier_rules.py` holds on a fresh one.

    Size is set by `n_sections`; the shape is held constant so document size can
    be varied without varying structural difficulty.
    """
    rng = random.Random(seed)
    sources = [
        Source(
            source_id=f"SRC-{i + 1:03d}",
            title=f"{rng.choice(_AREAS).title()} standard {rng.randint(1000, 9999)}",
            publisher=rng.choice(_PUBLISHERS),
        )
        for i in range(n_sources)
    ]

    sections: list[DecodableSection] = []
    for s in range(n_sections):
        sid = f"S{s + 1:02d}"
        sections.append(DecodableSection(
            section_id=sid,
            heading=f"{rng.choice(_AREAS).title()} controls",
            blocks=_blocks(rng, sources, sid, blocks_per_container),
            subsections=[
                DecodableSubSection(
                    subsection_id=f"{sid}-{t + 1}",
                    heading=f"{rng.choice(_AREAS).title()} detail",
                    blocks=_blocks(rng, sources, f"{sid}-{t + 1}",
                                   blocks_per_container),
                )
                for t in range(subsections_per_section)
            ],
        ))

    return DecodableDossier(
        dossier_id=f"DOS-{seed:04d}",
        title=f"Assurance dossier {seed:04d}",
        status="in_review",
        sources=sources,
        sections=sections,
        summary=None,
    )


# Named sizes, measured at run time rather than assumed.
DOSSIER_SIZES: dict[str, int] = {"small": 3, "medium": 8, "large": 20}
