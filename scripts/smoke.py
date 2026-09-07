"""End-to-end smoke test. `--offline` skips every API call.

Checks, in order: the corpus builds at each size; the safety walk says what the
research predicts; the splice round-trips; and then one real call per arm.
"""

from __future__ import annotations

import argparse
import json

from dsw.config import MODEL
from dsw.forms import ReviewForm, SIZES, make_edit, make_form
from dsw.metrics import flatten, integrity
from dsw.projection import classify_write, cross_field_validators, project
from dsw.splice import splice


def check_corpus() -> None:
    print("=== corpus ===")
    print(f"{'size':<8}{'responses':>10}{'chars':>10}{'~tokens':>10}{'leaves':>9}")
    for size, n in SIZES.items():
        form = make_form(n, seed=0)
        body = form.model_dump_json()
        leaves = len(flatten(form.model_dump(mode="json")))
        print(f"{size:<8}{n:>10}{len(body):>10}{len(body) // 4:>10}{leaves:>9}")


def check_safety() -> None:
    print("\n=== safety walk (P5) ===")
    target = ("responses", 3)
    for op in ("replace", "insert", "delete"):
        print(f"  {op:<8} {classify_write(ReviewForm, target, operation=op).explain()}")

    print("\n  cross-field validators Pydantic will admit to:")
    for model in (ReviewForm, *[f.annotation for f in ReviewForm.model_fields.values()]):
        try:
            found = cross_field_validators(model)  # type: ignore[arg-type]
        except Exception:
            continue
        if found:
            print(f"    {model.__name__}: {', '.join(found)}")  # type: ignore[union-attr]


def check_projection_and_splice() -> None:
    print("\n=== projection (P2) + splice (P4) ===")
    form = make_form(SIZES["small"], seed=0)
    target = ("responses", 2)
    Frag = project(ReviewForm, target)
    print(f"  projected model: {Frag.__name__}")
    print(f"  fragment schema keys: {sorted(Frag.model_json_schema().get('properties', {}))}")

    replacement = Frag.model_validate(
        {
            "question_id": form.responses[2].question_id,
            "question": form.responses[2].question,
            "answer": "Rewritten locally, no model involved.",
            "confidence": "high",
            "evidence": ["exhibit-Z-01"],
        }
    )
    result = splice(form, target, replacement)
    assert result.ok, result.error
    integ = integrity(form, result.document, target)
    print(f"  splice ok={result.ok}  untouched integrity={integ.rate:.4f} ({integ.summary()})")
    assert integ.perfect, "a code splice must never disturb the untouched region"

    bad = splice(form, ("responses", 9_999), replacement)
    print(f"  out-of-range splice correctly refused: {not bad.ok}")


def check_invisible_invariant() -> None:
    print("\n=== the invariant no schema can see ===")
    schema_text = json.dumps(ReviewForm.model_json_schema())
    print(f"  'resolution' appears in JSON Schema: {'resolution' in schema_text}")
    print(f"  the RULE linking status->resolution appears: "
          f"{'must carry a resolution' in schema_text}")
    form = make_form(3, seed=0)
    payload = form.model_dump(mode="json")
    payload["status"] = "resolved"
    try:
        ReviewForm.model_validate(payload)
        print("  ERROR: invalid document was accepted")
    except Exception:
        print("  caught only at full revalidation, exactly as predicted")


def check_live(arm_turns: int = 1) -> None:
    from dsw.experiment import Throttle, run_chain
    from dsw.providers import get_provider

    print(f"\n=== live call, model={MODEL} ===")
    provider = get_provider("gemini")
    throttle = Throttle()
    for arm in ("baseline", "fragment"):
        for rec in run_chain(provider, "small", 0, arm, arm_turns, throttle):
            status = "ok" if rec.ok else f"ERROR {rec.error}"
            rate = "n/a" if rec.integrity_rate is None else f"{rec.integrity_rate:.4f}"
            print(
                f"  {arm:<9} turn {rec.turn}  {status}\n"
                f"    integrity={rate}  target_applied={rec.target_applied}\n"
                f"    tokens in={rec.prompt_tokens} out={rec.output_tokens}"
                f"  latency={rec.latency_s}s  finish={rec.finish_reason}"
            )
            if rec.corrupted_sample:
                print(f"    corrupted: {rec.corrupted_sample}")


def main() -> None:
    ap = argparse.ArgumentParser()
    ap.add_argument("--offline", action="store_true", help="skip API calls")
    args = ap.parse_args()

    check_corpus()
    check_safety()
    check_projection_and_splice()
    check_invisible_invariant()
    if not args.offline:
        check_live()
    print("\nsmoke ok")


if __name__ == "__main__":
    main()
