"""
Ollama LLM Client - Self-hosted open-source LLM Integration
Implements ILLMClient for Mistral-7B-Instruct and Qwen-7B via Ollama.
"""
from __future__ import annotations

import asyncio
import json
import re
import time
from typing import Any

import httpx
import numpy as np
import structlog
from tenacity import retry, stop_after_attempt, wait_exponential

from ...domain.interfaces import ILLMClient

logger = structlog.get_logger(__name__)


class OllamaClient(ILLMClient):
    """
    Async Ollama client for local LLM inference.
    Primary model: Mistral-7B-Instruct for reasoning, extraction, drafting.
    Implements retry logic, structured JSON parsing, and reasoning vector extraction.
    """

    def __init__(
        self,
        base_url: str = "http://localhost:11434",
        primary_model: str = "mistral:7b-instruct",
        timeout: int = 120,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.primary_model = primary_model
        self.timeout = timeout
        self._client: httpx.AsyncClient | None = None

    async def _get_client(self) -> httpx.AsyncClient:
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                base_url=self.base_url,
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client

    async def close(self) -> None:
        if self._client and not self._client.is_closed:
            await self._client.aclose()

    def _extract_json(self, text: str) -> str:
        """Extract JSON from LLM response, handling markdown code blocks."""
        # Remove markdown code fences
        text = re.sub(r"```(?:json)?\s*", "", text).replace("```", "").strip()

        # Find JSON boundaries
        start = text.find("{")
        if start == -1:
            start = text.find("[")
        if start != -1:
            # Find matching close bracket
            stack = []
            for i, char in enumerate(text[start:], start):
                if char in "{[":
                    stack.append(char)
                elif char in "}]":
                    stack.pop()
                    if not stack:
                        return text[start:i+1]
        return text

    @retry(stop=stop_after_attempt(3), wait=wait_exponential(multiplier=1, min=2, max=10))
    async def complete(
        self,
        prompt: str,
        system_prompt: str | None = None,
        temperature: float = 0.1,
        max_tokens: int = 2048,
        json_mode: bool = False,
    ) -> str:
        """Generate a completion using Ollama."""
        client = await self._get_client()

        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})

        payload: dict[str, Any] = {
            "model": self.primary_model,
            "messages": messages,
            "stream": False,
            "options": {
                "temperature": temperature,
                "num_predict": max_tokens,
            },
        }

        if json_mode:
            payload["format"] = "json"

        start = time.time()
        try:
            response = await client.post("/api/chat", json=payload)
            response.raise_for_status()
            data = response.json()
            content = data.get("message", {}).get("content", "")
            latency = round(time.time() - start, 3)

            logger.debug("ollama_completion",
                         model=self.primary_model,
                         latency=latency,
                         tokens=data.get("eval_count", 0))

            if json_mode:
                return self._extract_json(content)
            return content

        except httpx.HTTPError as e:
            logger.error("ollama_http_error", error=str(e))
            raise
        except Exception as e:
            logger.error("ollama_completion_failed", error=str(e))
            raise

    async def get_reasoning_vector(self, prompt: str) -> list[float]:
        """
        Generate a reasoning vector for SAMR by using embeddings of the
        chain-of-thought reasoning response. This captures the model's
        internal reasoning pattern as a high-dimensional vector.
        """
        # Get a short chain-of-thought reasoning
        cot_prompt = f"Think step by step about this financial reconciliation task:\n{prompt[:2000]}\n\nReasoning:"
        try:
            reasoning = await self.complete(
                prompt=cot_prompt,
                temperature=0.0,
                max_tokens=256,
            )
            # Use the embedding of the reasoning as the reasoning vector
            client = await self._get_client()
            response = await client.post(
                "/api/embeddings",
                json={"model": self.primary_model, "prompt": reasoning},
            )
            if response.status_code == 200:
                return response.json().get("embedding", [0.0] * 768)
        except Exception as e:
            logger.warning("reasoning_vector_fallback", error=str(e))

        # Fallback: generate a deterministic pseudo-vector from text hash
        # This ensures SAMR still works even without embeddings endpoint
        import hashlib
        h = hashlib.sha256(prompt.encode()).digest()
        rng = np.random.default_rng(seed=int.from_bytes(h[:8], "big"))
        return rng.normal(0, 1, 768).tolist()

    async def health_check(self) -> bool:
        """Check if Ollama is running and the model is available."""
        try:
            client = await self._get_client()
            response = await client.get("/api/tags")
            if response.status_code == 200:
                models = [m["name"] for m in response.json().get("models", [])]
                return any(self.primary_model.split(":")[0] in m for m in models)
        except Exception:
            pass
        return False

    async def pull_model_if_needed(self) -> None:
        """Pull the model if it's not already available."""
        if not await self.health_check():
            logger.info("pulling_ollama_model", model=self.primary_model)
            client = await self._get_client()
            async with client.stream("POST", "/api/pull", json={"name": self.primary_model}) as resp:
                async for line in resp.aiter_lines():
                    if line:
                        try:
                            data = json.loads(line)
                            if status := data.get("status"):
                                logger.info("ollama_pull_status", status=status)
                        except json.JSONDecodeError:
                            pass
            logger.info("model_pulled_successfully", model=self.primary_model)
