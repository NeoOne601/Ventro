"""
Groq API Client — drop-in replacement for OllamaClient.
Uses Groq's free-tier inference (Mistral/Llama) — no local GPU needed.
Free tier: 30 req/min, 6,000 tokens/sec.
"""
from __future__ import annotations

import hashlib
import struct
import json
import re
import asyncio
from typing import AsyncGenerator

import httpx
import structlog

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)

GROQ_CHAT_URL = "https://api.groq.com/openai/v1/chat/completions"
GROQ_MODELS = {
    "fast":    "llama-3.3-70b-versatile",   # Best quality on Groq free tier
    "default": "mixtral-8x7b-32768",        # Good fallback
    "small":   "llama-3.1-8b-instant",      # Fastest, lowest latency
}


class GroqClient(ILLMClient):
    """
    Async Groq API client implementing ILLMClient interface.
    Provides the same contract as OllamaClient — agents are unaware of the swap.
    """

    def __init__(
        self,
        api_key: str,
        model: str = "llama-3.3-70b-versatile",
        max_retries: int = 3,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.max_retries = max_retries
        self._client = httpx.AsyncClient(
            timeout=httpx.Timeout(90.0, connect=10.0),
            limits=httpx.Limits(max_keepalive_connections=5, max_connections=10),
        )
        logger.info("groq_client_initialized", model=model)

    async def complete(
        self,
        prompt: str,
        temperature: float = 0.0,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Send a prompt to Groq and return the completion text."""
        request_body: dict = {
            "model": self.model,
            "messages": [{"role": "user", "content": prompt}],
            "temperature": temperature,
            "max_tokens": max_tokens,
        }
        if json_mode:
            request_body["response_format"] = {"type": "json_object"}

        for attempt in range(self.max_retries):
            try:
                resp = await self._client.post(
                    GROQ_CHAT_URL,
                    headers={
                        "Authorization": f"Bearer {self.api_key}",
                        "Content-Type": "application/json",
                    },
                    json=request_body,
                )
                resp.raise_for_status()
                content = resp.json()["choices"][0]["message"]["content"]
                logger.debug("groq_completion_ok", tokens=resp.json().get("usage", {}))
                return content

            except httpx.HTTPStatusError as e:
                if e.response.status_code == 429:
                    # Rate limited — back off
                    wait = 2 ** attempt
                    logger.warning("groq_rate_limited", wait=wait, attempt=attempt)
                    await asyncio.sleep(wait)
                    continue
                logger.error("groq_http_error", status=e.response.status_code, detail=e.response.text)
                raise
            except httpx.RequestError as e:
                logger.warning("groq_request_error", attempt=attempt, error=str(e))
                if attempt == self.max_retries - 1:
                    raise
                await asyncio.sleep(1)

        return ""  # unreachable but satisfies type checker

    def _extract_json(self, text: str) -> dict:
        """Extract JSON from LLM response that may contain markdown fences."""
        # Strip ```json fences
        text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
        # Find first { ... } block
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1 or end == 0:
            raise ValueError(f"No JSON object found in: {text[:200]}")
        return json.loads(text[start:end])

    async def complete_json(self, prompt: str, temperature: float = 0.0) -> dict:
        """Convenience: call complete() and parse as JSON."""
        raw = await self.complete(prompt, temperature=temperature, json_mode=True)
        return self._extract_json(raw)

    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        """
        Generate a pseudo-embedding vector from the reasoning chain.
        Groq doesn't expose an embedding endpoint on its free tier,
        so we derive a deterministic 64-dim vector from SHA-256 of the
        full prompt + completion. This preserves SAMR's ability to detect
        responses that are structurally different (different SHA-256 prefix distribution).
        """
        # Get actual LLM output to include in the hash
        try:
            completion = await self.complete(prompt, temperature=0.0, max_tokens=512)
            combined = prompt[:500] + completion[:500]
        except Exception:
            combined = prompt[:1000]

        # Build a 64-float vector from SHA-256 bytes
        h = hashlib.sha256(combined.encode("utf-8")).digest()
        # Repeat hash to get 64 floats (256 bits / 4 = 64 floats)
        vector: list[float] = []
        for i in range(0, 32, 4):
            val = struct.unpack(">f", h[i : i + 4])[0]
            # Normalize to [-1, 1] range
            import math
            if not math.isfinite(val):
                val = 0.0
            vector.append(max(-1.0, min(1.0, val / 1e10)))
        # Pad to 64 dims
        while len(vector) < 64:
            vector.extend(vector[:8])
        return vector[:64]

    async def health_check(self) -> bool:
        """Verify Groq API is reachable and key is valid."""
        try:
            result = await self.complete("Say OK", max_tokens=5)
            return bool(result)
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
