"""Talking to a model under a schema constraint.

Deliberately thin, and deliberately not LangChain. The experiment measures how
faithfully a model fills a schema, so anything that could silently change *how*
the schema constraint is requested is a confound rather than a convenience.
LangChain picks among function-calling, json_mode and json_schema strategies
depending on model and version; that choice is the independent variable here, so
it has to be ours.

The same reasoning rules OpenRouter out of the primary arm. Its structured-output
support is per *endpoint*, not per model — the same model served by a different
provider may not support it, and OpenRouter documents that it "might fall back to
json_object". A silent fall back from constrained decoding to a JSON-shaped hint
would invalidate the results without any error surfacing. It is kept here as a
second provider for cross-checks, with that caveat recorded in the response.
"""

from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from typing import Any, Protocol

import httpx
from pydantic import BaseModel

from .config import KEYS, MODEL


@dataclass
class Response:
    """One model call. `raw` is the text; `parsed` is it validated, if it validated."""

    text: str
    parsed: Any | None
    prompt_tokens: int
    output_tokens: int
    latency_s: float
    model: str
    finish_reason: str | None = None
    # True only when the provider guarantees schema enforcement rather than
    # requesting it. Recorded per call so a mixed run can never be read wrong.
    constrained: bool = True
    error: str | None = None
    meta: dict[str, Any] = field(default_factory=dict)

    @property
    def truncated(self) -> bool:
        r = (self.finish_reason or "").upper()
        return "MAX_TOKEN" in r or "LENGTH" in r


class Provider(Protocol):
    name: str

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel],
        max_output_tokens: int,
        history: list[tuple[str, str]] | None = None,
    ) -> Response: ...


class GeminiProvider:
    """Primary. `response_schema` is enforced by Google, not brokered."""

    name = "gemini"

    def __init__(self, model: str = MODEL) -> None:
        from google import genai

        self.model = model
        self._client = genai.Client(api_key=KEYS.require("gemini"))

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel],
        max_output_tokens: int = 65_536,
        history: list[tuple[str, str]] | None = None,
    ) -> Response:
        """`history` is [(role, text), ...] with role in {"user", "model"}.

        Passed as real multi-turn `contents` rather than concatenated into one
        string, so the accumulating transcript is billed and attended to the way
        an actual agentic loop's would be. The integrity and retry experiments
        both left this empty, which is precisely what
        `notes/05-what-the-experiments-did-not-test.md` is about: with no
        history the per-turn context never grows, and the degradation the
        literature attributes to long contexts cannot occur.
        """
        from google.genai import types

        started = time.perf_counter()
        contents = [
            types.Content(role=role, parts=[types.Part(text=text)])
            for role, text in (history or [])
        ]
        contents.append(
            types.Content(role="user", parts=[types.Part(text=prompt)])
        )
        # Thinking is held at "minimal" deliberately, and this is load-bearing.
        # Left at its default this model spent 561 thinking tokens on a trivial
        # one-object call — thinking is billed as output, so the baseline arm's
        # output count would have been a mixture of "document retyped" and
        # "reasoning done", destroying the comparison the experiment exists to
        # make. Measured 2026-09-07: `thinking_level="minimal"` yields zero
        # thought tokens. `thinking_budget=0` and `thinking_level="none"` are
        # both rejected with 400 on Gemini 3.x — it cannot be switched off, only
        # turned down.
        config = types.GenerateContentConfig(
            response_mime_type="application/json",
            response_schema=schema,
            max_output_tokens=max_output_tokens,
            temperature=0.0,
            thinking_config=types.ThinkingConfig(thinking_level="minimal"),
        )
        # Retry only transient *transport* failures — 429 quota and 503 overload.
        # In both cases no sample was drawn, so a retry is the same call, not a
        # second roll of the dice. A malformed or wrong *output* is never
        # retried: that would silently change what the experiment measures.
        attempts, resp, last_error = 0, None, None
        while attempts < 6:
            try:
                resp = self._client.models.generate_content(
                    model=self.model, contents=contents, config=config
                )
                break
            except Exception as exc:
                last_error = exc
                text = str(exc)
                transient = (
                    "429" in text or "RESOURCE_EXHAUSTED" in text
                    or "503" in text or "UNAVAILABLE" in text
                    # Dropped connections. Seen repeatedly on 17K-token
                    # generations, which take ~50s and evidently outlive some
                    # idle timeout on the path.
                    or "RemoteProtocolError" in text
                    or "Server disconnected" in text
                    or "incomplete chunked read" in text
                    or "ReadTimeout" in text or "ConnectError" in text
                    or type(exc).__name__ in {
                        "RemoteProtocolError", "ReadTimeout", "ConnectError",
                        "ReadError", "ServerError",
                    }
                )
                if not transient:
                    break
                attempts += 1
                time.sleep(min(2 ** attempts * 5, 120))

        if resp is None:
            return Response(
                text="",
                parsed=None,
                prompt_tokens=0,
                output_tokens=0,
                latency_s=time.perf_counter() - started,
                model=self.model,
                error=f"{type(last_error).__name__}: {last_error}",
                meta={"retries": attempts},
            )

        elapsed = time.perf_counter() - started
        usage = resp.usage_metadata
        finish = None
        if resp.candidates:
            finish = getattr(resp.candidates[0].finish_reason, "name", None) or str(
                resp.candidates[0].finish_reason
            )

        # `resp.parsed` is populated only when a Pydantic response_schema was used
        # AND the payload validated. A None here on a non-empty body is itself a
        # finding, so it is preserved rather than smoothed over.
        return Response(
            text=resp.text or "",
            parsed=resp.parsed,
            prompt_tokens=getattr(usage, "prompt_token_count", 0) or 0,
            output_tokens=getattr(usage, "candidates_token_count", 0) or 0,
            latency_s=elapsed,
            model=self.model,
            finish_reason=finish,
            constrained=True,
            # Recorded rather than assumed zero: if a future model ignores
            # "minimal", the run data will show it instead of hiding it.
            meta={
                "thought_tokens": getattr(usage, "thoughts_token_count", None) or 0,
                "retries": attempts,
            },
        )


class OpenRouterProvider:
    """Cross-check only. Schema enforcement is best-effort — see module docstring."""

    name = "openrouter"
    URL = "https://openrouter.ai/api/v1/chat/completions"

    def __init__(self, model: str = "google/gemini-2.5-flash") -> None:
        self.model = model
        self._key = KEYS.require("openrouter")

    def generate(
        self,
        prompt: str,
        schema: type[BaseModel],
        max_output_tokens: int = 65_536,
        history: list[tuple[str, str]] | None = None,
    ) -> Response:
        messages = [
            {"role": "assistant" if r == "model" else "user", "content": t}
            for r, t in (history or [])
        ]
        messages.append({"role": "user", "content": prompt})
        body = {
            "model": self.model,
            "messages": messages,
            "max_tokens": max_output_tokens,
            "temperature": 0.0,
            "response_format": {
                "type": "json_schema",
                "json_schema": {
                    "name": schema.__name__,
                    "strict": True,
                    "schema": schema.model_json_schema(),
                },
            },
        }
        started = time.perf_counter()
        try:
            r = httpx.post(
                self.URL,
                headers={"Authorization": f"Bearer {self._key}"},
                json=body,
                timeout=300.0,
            )
            r.raise_for_status()
            payload = r.json()
        except Exception as exc:
            return Response(
                text="",
                parsed=None,
                prompt_tokens=0,
                output_tokens=0,
                latency_s=time.perf_counter() - started,
                model=self.model,
                constrained=False,
                error=f"{type(exc).__name__}: {exc}",
            )

        elapsed = time.perf_counter() - started
        choice = payload["choices"][0]
        text = choice["message"]["content"] or ""
        usage = payload.get("usage", {})

        parsed = None
        try:
            parsed = schema.model_validate(json.loads(text))
        except Exception:
            pass

        return Response(
            text=text,
            parsed=parsed,
            prompt_tokens=usage.get("prompt_tokens", 0),
            output_tokens=usage.get("completion_tokens", 0),
            latency_s=elapsed,
            model=self.model,
            finish_reason=choice.get("finish_reason"),
            # Never claim enforcement here: OpenRouter may route to an endpoint
            # that downgrades json_schema to json_object without telling us.
            constrained=False,
            meta={"provider_routed_to": payload.get("provider")},
        )


def get_provider(name: str = "gemini") -> Provider:
    if name == "gemini":
        return GeminiProvider()
    if name == "openrouter":
        return OpenRouterProvider()
    raise ValueError(f"unknown provider {name!r}; expected 'gemini' or 'openrouter'")
