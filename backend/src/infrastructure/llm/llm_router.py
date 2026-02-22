"""
LLM Router — Fallback Chain with Circuit Breaker
Wraps multiple LLM providers behind a single ILLMClient interface.

Fallback order is admin-configurable via LLM_FALLBACK_CHAIN env var.
Each provider has an independent circuit breaker that opens after N consecutive
failures and recovers automatically after a cooldown period.

Default chain: groq → ollama → rule_based
  - groq:       Fast cloud inference (requires GROQ_API_KEY)
  - ollama:     Local self-hosted (no external dependency)
  - rule_based: Minimal regex/heuristic extractor — always available,
                guaranteed non-empty result even if all LLMs are down

Usage (wired in dependencies.py):
    router = LLMRouter(providers=[groq_client, ollama_client, rule_based])
    # Agents use router exactly like any ILLMClient — no code changes needed
    result = await router.complete(prompt)
"""
from __future__ import annotations

import asyncio
import re
import time
from typing import Any, AsyncGenerator

import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)


# ─── Circuit Breaker ──────────────────────────────────────────────────────────

class CircuitBreaker:
    """
    Per-provider circuit breaker.
    States: CLOSED (healthy) → OPEN (tripped) → HALF_OPEN (testing recovery).
    """

    def __init__(self, name: str, max_failures: int, recovery_seconds: float) -> None:
        self.name = name
        self.max_failures = max_failures
        self.recovery_seconds = recovery_seconds
        self._failures = 0
        self._opened_at: float | None = None

    @property
    def is_open(self) -> bool:
        if self._opened_at is None:
            return False
        elapsed = time.monotonic() - self._opened_at
        if elapsed >= self.recovery_seconds:
            # Transition to HALF_OPEN — allow one test request
            logger.info("circuit_breaker_half_open", provider=self.name)
            self._opened_at = None
            self._failures = 0
            return False
        return True

    def record_success(self) -> None:
        self._failures = 0
        self._opened_at = None

    def record_failure(self) -> None:
        self._failures += 1
        if self._failures >= self.max_failures:
            if self._opened_at is None:
                self._opened_at = time.monotonic()
                logger.warning(
                    "circuit_breaker_opened",
                    provider=self.name,
                    failures=self._failures,
                )


# ─── Rule-Based Fallback Extractor ───────────────────────────────────────────

class RuleBasedExtractor(ILLMClient):
    """
    Minimum-viable extraction using pure regex patterns.
    Never fails. Returns structured JSON with whatever it can find.
    Used only when ALL LLM providers are unavailable.
    """

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
        **kwargs,
    ) -> str:
        """
        Extract key financial fields using pattern matching.
        Returns a minimal JSON string compatible with the extraction schema.
        """
        # Extract common financial patterns from the prompt text
        amounts = re.findall(r"\$[\d,]+\.?\d*|\d+[\.,]\d{2}\s*(?:USD|EUR|GBP|AED|INR|SAR)", prompt)
        dates = re.findall(
            r"\b\d{1,2}[/-]\d{1,2}[/-]\d{2,4}\b|\b(?:Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Oct|Nov|Dec)[a-z]*\.?\s+\d{1,2},?\s+\d{4}\b",
            prompt, re.IGNORECASE,
        )
        doc_nums = re.findall(r"(?:PO|GRN|INV|Invoice|Order)[-#\s]*([A-Z0-9-]{4,20})", prompt, re.IGNORECASE)

        # Build minimal compliant response
        import json
        result = {
            "line_items": [],
            "document_totals": {
                "subtotal": 0.0,
                "tax_rate": 0.0,
                "tax_amount": 0.0,
                "total": _parse_amount(amounts[-1]) if amounts else 0.0,
                "currency": "USD",
            },
            "document_metadata": {
                "vendor_name": "",
                "document_number": doc_nums[0] if doc_nums else "",
                "document_date": dates[0] if dates else "",
                "payment_terms": "",
            },
            "_extraction_method": "rule_based_fallback",
            "_warning": "All LLM providers unavailable. Results are regex-extracted and may be incomplete.",
        }
        logger.warning("rule_based_extractor_used", amounts_found=len(amounts), docs_found=len(doc_nums))
        return json.dumps(result)

    async def complete_json(self, prompt: str, temperature: float = 0.0) -> dict:
        import json
        return json.loads(await self.complete(prompt, temperature=temperature))

    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        from ...application.config import get_settings
        dims = get_settings().embedding_dimension
        return [0.0] * dims  # Zero vector — SAMR will flag this as an anomaly (correct behaviour)

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        result = await self.complete(prompt)
        yield result

    async def health_check(self) -> bool:
        return True  # Always healthy

    async def close(self) -> None:
        pass


def _parse_amount(s: str) -> float:
    try:
        return float(re.sub(r"[^\d.]", "", s))
    except (ValueError, TypeError):
        return 0.0


# ─── LLM Router ───────────────────────────────────────────────────────────────

class LLMRouter(ILLMClient):
    """
    Routes LLM requests through an ordered provider chain with circuit breakers.

    On every call:
      1. Iterate providers in configured order
      2. Skip providers whose circuit breaker is OPEN
      3. Attempt the call with a per-provider timeout
      4. On success: record success, return result
      5. On failure: record failure (may open circuit), try next provider
      6. If all providers fail/are open: fall through to rule_based (always last)
    """

    def __init__(
        self,
        providers: list[tuple[str, ILLMClient]],   # [(name, client), ...]
        timeout_seconds: float = 45.0,
        max_failures: int = 3,
        recovery_seconds: float = 60.0,
    ) -> None:
        self._providers = providers
        self._timeout = timeout_seconds
        self._breakers: dict[str, CircuitBreaker] = {
            name: CircuitBreaker(name, max_failures, recovery_seconds)
            for name, _ in providers
        }
        logger.info(
            "llm_router_initialized",
            chain=[name for name, _ in providers],
            timeout=timeout_seconds,
        )

    def _active_providers(self) -> list[tuple[str, ILLMClient]]:
        """Return providers whose circuit breaker is closed, in order."""
        return [(n, c) for n, c in self._providers if not self._breakers[n].is_open]

    async def complete(
        self,
        prompt: str,
        system_prompt: str = "",
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
        **kwargs,
    ) -> str:
        last_error: Exception | None = None

        for name, client in self._active_providers():
            try:
                logger.debug("llm_router_trying", provider=name)
                result = await asyncio.wait_for(
                    client.complete(
                        prompt,
                        system_prompt=system_prompt,
                        temperature=temperature,
                        max_tokens=max_tokens,
                        json_mode=json_mode,
                        **kwargs,
                    ),
                    timeout=self._timeout,
                )
                self._breakers[name].record_success()
                logger.info("llm_router_success", provider=name)
                return result
            except asyncio.TimeoutError as e:
                last_error = e
                self._breakers[name].record_failure()
                logger.warning("llm_router_timeout", provider=name, timeout=self._timeout)
            except Exception as e:
                last_error = e
                self._breakers[name].record_failure()
                logger.warning("llm_router_error", provider=name, error=str(e))

        # Exhausted all providers — this should not normally happen because
        # RuleBasedExtractor is always in the chain and never fails
        logger.error("llm_router_all_providers_failed", last_error=str(last_error))
        raise RuntimeError(
            f"All LLM providers failed. Last error: {last_error}"
        ) from last_error

    async def complete_json(self, prompt: str, temperature: float = 0.0) -> dict:
        import json
        raw = await self.complete(prompt, temperature=temperature, json_mode=True)
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            # Try to extract JSON from markdown-fenced response
            match = re.search(r"\{.*\}", raw, re.DOTALL)
            if match:
                return json.loads(match.group())
            raise

    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        """Uses the first healthy provider for SAMR embedding."""
        for name, client in self._active_providers():
            try:
                vec = await asyncio.wait_for(
                    client.get_reasoning_vector(prompt),
                    timeout=self._timeout,
                )
                self._breakers[name].record_success()
                return vec
            except Exception as e:
                self._breakers[name].record_failure()
                logger.warning("llm_router_reasoning_vector_error", provider=name, error=str(e))

        # All providers failed — return zero vector (signals SAMR to flag anomaly)
        from ...application.config import get_settings
        return [0.0] * get_settings().embedding_dimension

    async def stream(self, prompt: str, **kwargs) -> AsyncGenerator[str, None]:
        """Stream from first healthy provider; fallback silently if needed."""
        for name, client in self._active_providers():
            try:
                if hasattr(client, "stream"):
                    async for chunk in client.stream(prompt, **kwargs):
                        yield chunk
                    self._breakers[name].record_success()
                    return
            except Exception as e:
                self._breakers[name].record_failure()
                logger.warning("llm_router_stream_error", provider=name, error=str(e))

        # Fallback: complete() as a single chunk
        result = await self.complete(prompt, **kwargs)
        yield result

    async def health_check(self) -> bool:
        """Returns True if at least one provider is healthy."""
        for name, client in self._providers:
            if not self._breakers[name].is_open:
                try:
                    ok = await asyncio.wait_for(client.health_check(), timeout=5.0)
                    if ok:
                        return True
                except Exception:
                    pass
        return False

    async def close(self) -> None:
        for _, client in self._providers:
            try:
                await client.close()
            except Exception:
                pass

    def provider_status(self) -> dict[str, dict]:
        """Admin-readable status of all providers and their circuit breakers."""
        return {
            name: {
                "circuit_breaker": "OPEN" if self._breakers[name].is_open else "CLOSED",
                "failures": self._breakers[name]._failures,
            }
            for name, _ in self._providers
        }
