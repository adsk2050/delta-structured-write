"""Configuration: keys, model choice, and the free-tier budget we must stay inside.

The model is pinned deliberately. The whole point of the integrity experiment is
to compare *generation strategies*, so the model must not vary across arms or
across days. See `MODEL` below for why this one.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

REPO_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = REPO_ROOT / "data"
RUNS_DIR = DATA_DIR / "runs"

load_dotenv(REPO_ROOT / ".env")


# --------------------------------------------------------------------------
# Model choice
# --------------------------------------------------------------------------
# gemini-3.5-flash, direct via the Gemini API (see MODEL below; the reasons
# below are why a model of this family, the table after them is why this one).
# Three reasons, in order:
#
# 1. STABLE AND SUPPORTED. No `-preview` suffix, so it will not be swapped under
#    a multi-day experiment — and it is the model Google's own API names as the
#    migration target from the retired gemini-2.5-flash, so it is the current
#    workhorse rather than a soon-to-rotate alias. `gemini-flash-latest` is
#    explicitly rejected for the opposite reason: an alias that moves would
#    reintroduce the model effect the experiment exists to exclude.
# 2. FIRST-PARTY CONSTRAINED DECODING. `response_schema` is enforced by Google,
#    not brokered through a router. This matters more than it sounds — see
#    providers.py for why it disqualifies OpenRouter from the primary arm.
# 3. 65,536 OUTPUT TOKENS, which the baseline arm needs to retype a large
#    document in one response. Verified 2026-09-07 alongside a 1,048,576 input
#    limit.
#
# Two earlier choices did not survive contact with the API, both worth recording
# so nobody re-treads them:
#   gemini-2.5-flash  404 "no longer available to new users" — retired for new keys.
#   gemini-3.6-flash  works, and was Google's named migration target, but its
#                     20-request free-tier bucket was spent during setup probing.
#   gemini-3.7/3.8    reject thinking_level "minimal" AND "low" with 400, so
#                     thinking cannot be held down and output-token accounting
#                     would be polluted by reasoning tokens.
# gemini-3.5-flash accepts thinking_level="minimal" with zero thought tokens
# (verified 2026-09-07), is stable, and had an untouched daily bucket.
MODEL = "gemini-3.5-flash"

# Free-tier limits for the pinned model, from Google's published quotas.
# Treated as hard ceilings by the runner; it self-throttles below them.
RPM_LIMIT = 8           # deliberately under the published 10, for headroom
TPM_LIMIT = 200_000     # under the published 250K
RPD_LIMIT = 1_500       # paid tier

# MEASURED, not documented. The free tier gives 20 requests/day/model, per the
# API's own 429 body (quotaId GenerateRequestsPerDayPerProjectPerModel-FreeTier,
# quotaValue 20, 2026-09-07). Secondary sources claiming 1,500/day are wrong for
# this model. The quota is per *model*, so probing several models masks it.
FREE_TIER_RPD = 20


@dataclass(frozen=True)
class Keys:
    gemini: str | None
    openrouter: str | None
    inception: str | None

    @classmethod
    def from_env(cls) -> Keys:
        return cls(
            gemini=os.getenv("GEMINI_API_KEY"),
            openrouter=os.getenv("OPENROUTER_API_KEY"),
            inception=os.getenv("INCEPTION_API_KEY"),
        )

    def require(self, name: str) -> str:
        key = getattr(self, name)
        if not key:
            raise RuntimeError(
                f"{name.upper()}_API_KEY missing. Add it to {REPO_ROOT / '.env'}."
            )
        return key


KEYS = Keys.from_env()
