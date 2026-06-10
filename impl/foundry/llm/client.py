"""Pluggable LLM client.

* Real Mistral via the ``mistralai`` SDK when ``MISTRAL_API_KEY`` is set.
* Otherwise a deterministic mock that returns canned responses based on
  the role-tagged prompt (good enough to demonstrate the pipeline end-to-end
  without hitting the network).

Constitution Principle V — the system never sets an internal rate cap below
the provider's actual limit. Adaptive backoff fires only on 429 / 503 +
``Retry-After``.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from dataclasses import dataclass, field
from typing import Any, Literal

import httpx
try:
    import truststore  # type: ignore
    truststore.inject_into_ssl()  # use macOS Keychain / system trust store
    _CA_BUNDLE: object = True  # let httpx use the (now-injected) default SSLContext
except Exception:  # noqa: BLE001
    try:
        import certifi  # type: ignore
        _CA_BUNDLE = certifi.where()
    except Exception:  # noqa: BLE001
        _CA_BUNDLE = True
import structlog

log = structlog.get_logger(__name__)

Tier = Literal["strong", "bulk"]


@dataclass
class LLMMessage:
    role: Literal["system", "user", "assistant", "tool"]
    content: str


@dataclass
class LLMResponse:
    text: str
    tokens_in: int = 0
    tokens_out: int = 0
    raw: dict[str, Any] = field(default_factory=dict)


class LLMClient:
    """Base interface."""

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: Tier = "bulk",
        json_mode: bool = False,
    ) -> LLMResponse:
        raise NotImplementedError


# ── Real Mistral client ────────────────────────────────────────────────────

class MistralClient(LLMClient):
    def __init__(
        self,
        api_key: str,
        strong_model: str = "mistral-large-latest",
        bulk_model: str = "mistral-small-latest",
        region: str = "eu",
    ):
        self.api_key = api_key
        self.strong_model = strong_model
        self.bulk_model = bulk_model
        # Mistral has one global API; "region" left for future per-region endpoints.
        self.base_url = "https://api.mistral.ai/v1"
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(60.0),
            headers={"Authorization": f"Bearer {api_key}"},
            verify=_CA_BUNDLE,
        )
        self._backoff_until = 0.0  # fleet-wide adaptive backoff (Principle V)

    async def aclose(self) -> None:
        await self._client.aclose()

    async def complete(
        self, messages: list[LLMMessage], *, tier: Tier = "bulk", json_mode: bool = False
    ) -> LLMResponse:
        model = self.strong_model if tier == "strong" else self.bulk_model
        payload: dict[str, Any] = {
            "model": model,
            "messages": [{"role": m.role, "content": m.content} for m in messages],
            "temperature": 0.2,
        }
        if json_mode:
            payload["response_format"] = {"type": "json_object"}

        for attempt in range(6):
            now = time.monotonic()
            if now < self._backoff_until:
                await asyncio.sleep(self._backoff_until - now)

            try:
                resp = await self._client.post(f"{self.base_url}/chat/completions", json=payload)
            except httpx.HTTPError as e:
                log.warning("mistral_network_error", attempt=attempt, error=str(e))
                await asyncio.sleep(min(30, 2**attempt + random.random()))
                continue

            if resp.status_code == 429 or resp.status_code >= 500:
                retry_after = float(resp.headers.get("Retry-After", "0") or 0)
                wait = retry_after if retry_after > 0 else min(30, 2**attempt + random.random())
                self._backoff_until = time.monotonic() + wait
                log.warning("mistral_backoff", status=resp.status_code, wait=wait)
                continue

            resp.raise_for_status()
            data = resp.json()
            choice = data["choices"][0]["message"]["content"]
            usage = data.get("usage", {})
            return LLMResponse(
                text=choice,
                tokens_in=usage.get("prompt_tokens", 0),
                tokens_out=usage.get("completion_tokens", 0),
                raw=data,
            )

        raise RuntimeError("Mistral: exhausted retries")


# ── Mock client (deterministic, demo-only) ─────────────────────────────────

class MockClient(LLMClient):
    """Deterministic role-aware mock that produces structurally valid outputs.

    The mock recognizes the role from a system prompt tag like ``[ROLE=triager]``
    and returns canned JSON or markdown the agent expects. Real evaluation
    quality requires a real model; the mock exists only to demonstrate that the
    architecture wires up correctly without an API key.
    """

    async def complete(
        self,
        messages: list[LLMMessage],
        *,
        tier: Tier = "bulk",
        json_mode: bool = False,
    ) -> LLMResponse:
        prompt = "\n".join(m.content for m in messages)
        role_match = re.search(r"\[ROLE=([a-z_]+)\]", prompt)
        role = role_match.group(1) if role_match else "unknown"

        text = _mock_response(role, prompt, json_mode)
        return LLMResponse(text=text, tokens_in=len(prompt) // 4, tokens_out=len(text) // 4)


def _mock_response(role: str, prompt: str, json_mode: bool) -> str:  # noqa: C901
    if role == "cartographer":
        doc_kind = re.search(r"\[DOC=([a-z_]+)\]", prompt)
        kind = doc_kind.group(1) if doc_kind else "overview"
        return _mock_security_doc(kind)

    if role == "detector":
        # Detector LLM-check returns JSON: {"is_vuln": bool, "rule_id": str, "reason": str}
        # Mock always says "yes" if the function body contains tainted-flow indicators.
        body_match = re.search(r"\[BODY\](.*?)\[/BODY\]", prompt, re.DOTALL)
        body = body_match.group(1) if body_match else ""
        is_vuln = bool(
            re.search(
                r"(execute\s*\(|os\.system|subprocess\..*shell=True|eval\(|pickle\.loads)",
                body,
            )
        )
        rule_match = re.search(r"\[RULE=([A-Z\-0-9]+)\]", prompt)
        rule = rule_match.group(1) if rule_match else "CWE-94"
        return json.dumps(
            {
                "is_vuln": is_vuln,
                "rule_id": rule,
                "reason": (
                    "Function body contains a known dangerous sink (mock judgment)."
                    if is_vuln
                    else "No dangerous sink detected (mock)."
                ),
            }
        )

    if role == "triager":
        # Triager returns: {"verdict": ..., "notes": ..., "citations": [...], "severity": ...}
        body_match = re.search(r"\[BODY\](.*?)\[/BODY\]", prompt, re.DOTALL)
        path_match = re.search(r"\[PATH=(.*?)\]", prompt)
        sym_match = re.search(r"\[SYMBOL=(.*?)\]", prompt)
        body = body_match.group(1) if body_match else ""
        path = path_match.group(1) if path_match else ""
        sym = sym_match.group(1) if sym_match else ""

        # Pick a real substring of the body as the citation excerpt — this is
        # what the DB-side gate validates. A real model can fabricate; the gate
        # rejects fabrications.
        excerpts = re.findall(r"(execute\(.+?\)|os\.system\(.+?\)|eval\(.+?\)|subprocess\..+?\))", body)
        citations = []
        if excerpts:
            citations.append(
                {"path": path, "symbol": sym, "excerpt": excerpts[0]}
            )
        verdict = "true-positive" if citations else "false-positive"
        return json.dumps(
            {
                "verdict": verdict,
                "notes": (
                    f"Sink reachable from caller; dangerous arg flows from untrusted source. ({sym})"
                    if verdict == "true-positive"
                    else "No reachable sink found in body."
                ),
                "citations": citations,
                "severity": "high" if verdict == "true-positive" else None,
            }
        )

    if role == "validator_poc":
        return json.dumps(
            {
                "artifact": "import requests; requests.post('http://localhost:8080/api', data={'q': \"1; DROP TABLE users; --\"})",
                "expected_impact": "users table dropped",
            }
        )

    if role == "validator_run":
        return json.dumps(
            {"observed_impact": "users table dropped", "log": "stdout: ok\nstderr: (empty)"}
        )

    if role == "orchestrator_converse":
        return "Mock orchestrator answer (set MISTRAL_API_KEY for real responses)."

    return "[mock] no canned response for role=" + role


def _mock_security_doc(kind: str) -> str:
    return {
        "overview": "# Architecture Overview (mock)\n\nA small Flask web app exposing /login and /search endpoints.",
        "attack_surface": "# Attack Surface (mock)\n\n- POST /login (unauthenticated)\n- GET /search?q= (unauthenticated)",
        "trust_boundaries": "# Trust Boundaries (mock)\n\n- Boundary B1: untrusted HTTP request → SQL query construction.",
        "data_flows": "# Data Flows (mock)\n\n- Request body → SQL string (no parameterization).",
        "threat_model": "# Threat Model (mock)\n\n- T1: SQL injection via /search and /login.",
    }.get(kind, "# (mock empty)")


# ── Factory ────────────────────────────────────────────────────────────────

def get_client(
    strong_model: str = "mistral-large-latest",
    bulk_model: str = "mistral-small-latest",
    region: str = "eu",
) -> LLMClient:
    api_key = os.environ.get("MISTRAL_API_KEY")
    if api_key:
        log.info("llm_client", provider="mistral", strong=strong_model, bulk=bulk_model)
        return MistralClient(api_key, strong_model, bulk_model, region)
    log.warning("llm_client", provider="mock", reason="MISTRAL_API_KEY not set")
    return MockClient()
