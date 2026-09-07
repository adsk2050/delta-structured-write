"""The dossier's invariants, and where each one is repaired.

Same shape as `constraints.py` — plain functions returning `Violation`s that
carry their own repair path — but chosen so the four rules fail in four
different ways. That variety is the point: `ReviewForm`'s three rules were all
local property checks, so they could all be repaired in place and none of them
tested the fallback case.

  D1  severe finding needs >= 2 citations and a remediation
      LOCAL. One block. Exactly the case already measured.
  D2  every citation names a declared source
      REFERENTIAL, and the reference spans the document: deep content must stay
      consistent with a registry declared in the header. This is the rule that
      should break first if the middle of a long context starts to blur.
  D3  every table row has as many cells as the table has columns
      STRUCTURAL. Displacement Rate in miniature.
  D4  ids are unique across the whole document
      GLOBAL, and NOT localisable to any single path. It is the `uniqueItems`
      case that no engine enforces, and it is the fallback `RETRY.md` could
      only assert at 0% because no rule in that corpus produced it.
  D5  a block's fields match the branch its `kind` names
      The enforcement gap made visible: the decoder is given a flattened block,
      so nothing at decode time stops a "table" arriving with `text` set.

D4 and D5 both have empty `repair_paths` on purpose. A fragment retry has
nothing to aim at, and the harness must fall back to the whole document. How
often that happens is now measurable rather than asserted.
"""

from __future__ import annotations

from collections import Counter
from typing import Iterator

from .constraints import Violation
from .dossier import (
    SEVERE, MIN_CITATIONS_FOR_SEVERE, DecodableBlock, DecodableDossier,
)
from .projection import Path

# Which fields belong to which branch. Anything else set is a D5 violation.
BRANCH_FIELDS: dict[str, frozenset[str]] = {
    "narrative": frozenset({"text", "citations"}),
    "table": frozenset({"caption", "columns", "rows"}),
    "finding": frozenset({"severity", "statement", "citations", "remediation"}),
}
_OPTIONAL_FIELDS = frozenset(
    {"text", "caption", "columns", "rows", "severity", "statement", "remediation"}
)


def walk_blocks(doc: DecodableDossier) -> Iterator[tuple[Path, DecodableBlock]]:
    """Every block in the document, with the path that addresses it.

    Yields in document order, so a violation list reads top to bottom and a
    reader can see *where* in the document the failures cluster — which is the
    whole question once context length is the independent variable.
    """
    for i, section in enumerate(doc.sections):
        for j, block in enumerate(section.blocks):
            yield ("sections", i, "blocks", j), block
        for k, sub in enumerate(section.subsections):
            for j, block in enumerate(sub.blocks):
                yield ("sections", i, "subsections", k, "blocks", j), block


def _pointer(path: Path) -> str:
    return "".join(f"/{s}" for s in path)


def check_dossier(doc: DecodableDossier) -> list[Violation]:
    """Every rule the dossier currently breaks, in document order."""
    out: list[Violation] = []
    declared = {s.source_id for s in doc.sources}

    for path, block in walk_blocks(doc):
        ptr = _pointer(path)

        # D5 — the branch shape the decoder could not enforce.
        allowed = BRANCH_FIELDS[block.kind]
        stray = sorted(
            f for f in _OPTIONAL_FIELDS - allowed
            if getattr(block, f, None) is not None
        )
        missing = sorted(
            f for f in allowed & _OPTIONAL_FIELDS
            if getattr(block, f, None) is None
            and not (block.kind == "finding" and f == "remediation")
        )
        if stray or missing:
            bits = []
            if missing:
                bits.append("missing " + ", ".join(missing))
            if stray:
                bits.append("carries " + ", ".join(stray) + " from another branch")
            out.append(Violation(
                "D5",
                f"block {block.block_id} at {ptr} declares kind "
                f"{block.kind!r} but {'; '.join(bits)}",
                (path,),
            ))

        # D1 — a severe finding must be backed and actionable.
        if block.kind == "finding" and block.severity in SEVERE:
            if len(block.citations) < MIN_CITATIONS_FOR_SEVERE:
                out.append(Violation(
                    "D1",
                    f"finding {block.block_id} at {ptr} is {block.severity} but "
                    f"cites {len(block.citations)} source(s); at least "
                    f"{MIN_CITATIONS_FOR_SEVERE} are required",
                    (path,),
                ))
            if not (block.remediation or "").strip():
                out.append(Violation(
                    "D1",
                    f"finding {block.block_id} at {ptr} is {block.severity} and "
                    f"must carry a remediation",
                    (path,),
                ))

        # D2 — referential integrity against the header registry.
        for c, cite in enumerate(block.citations):
            if cite.source_id not in declared:
                out.append(Violation(
                    "D2",
                    f"citation {c} of block {block.block_id} at {ptr} names "
                    f"source {cite.source_id!r}, which is not declared in "
                    f"`sources` (declared: {', '.join(sorted(declared))})",
                    (path,),
                ))

        # D3 — table rows must match the table's own width.
        if block.kind == "table" and block.columns is not None:
            width = len(block.columns)
            for r, row in enumerate(block.rows or []):
                if len(row.cells) != width:
                    out.append(Violation(
                        "D3",
                        f"row {row.row_id} of table {block.block_id} at {ptr} "
                        f"has {len(row.cells)} cells but the table declares "
                        f"{width} columns",
                        (path,),
                    ))

    # D4 — global uniqueness. No single path repairs it, so `repair_paths` is
    # empty and a fragment retry must fall back to the whole document.
    ids = (
        [s.source_id for s in doc.sources]
        + [s.section_id for s in doc.sections]
        + [t.subsection_id for s in doc.sections for t in s.subsections]
        + [b.block_id for _, b in walk_blocks(doc)]
        + [r.row_id for _, b in walk_blocks(doc) for r in (b.rows or [])]
    )
    for dup, n in sorted(Counter(ids).items()):
        if n > 1:
            out.append(Violation(
                "D4", f"id {dup!r} appears {n} times; ids must be unique "
                      f"across the whole dossier", ()
            ))

    return out


RULES_IN_PROSE = f"""\
DOSSIER RULES. All five must hold. None of them is in the JSON schema, so \
nothing will stop you emitting a dossier that breaks them.
  D1. Any finding with severity "high" or "critical" must cite at least \
{MIN_CITATIONS_FOR_SEVERE} sources AND carry a non-empty `remediation`.
  D2. Every citation's `source_id` must be one of the ids declared in the \
dossier's top-level `sources` list. Never invent a source id.
  D3. Every row of a table must have exactly as many `cells` as that table has \
`columns`.
  D4. Every id in the document -- source_id, section_id, subsection_id, \
block_id, row_id -- must be unique across the whole dossier.
  D5. A block's fields must match the branch its `kind` names: "narrative" has \
`text`; "table" has `caption`, `columns`, `rows`; "finding" has `severity`, \
`statement` and may have `remediation`. Fields belonging to other branches must \
be null."""


def rule_summary(violations: list[Violation]) -> dict[str, int]:
    """Counts per rule, for the per-turn record."""
    out: dict[str, int] = {}
    for v in violations:
        out[v.rule] = out.get(v.rule, 0) + 1
    return out
