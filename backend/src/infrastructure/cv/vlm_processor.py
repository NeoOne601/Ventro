"""
Visual Language Model (VLM) Processor
Uses Qwen2-VL or InternVL2 via Ollama for structured data extraction
from scanned documents, handwritten content, and image-heavy PDFs.

This is the second-tier processor — invoked after OCR when:
  - Tables are present in scanned pages, OR
  - Handwritten annotations are detected, OR
  - Document contains charts/stamps that carry financial meaning
"""
from __future__ import annotations

import base64
import io
import json
import re
from typing import Any

import httpx
import structlog

logger = structlog.get_logger(__name__)

# Supported Ollama VLM models (tested with Ollama ≥ 0.3)
SUPPORTED_VLM_MODELS = {
    "qwen2-vl":    "qwen2-vl:7b-instruct",   # Best multilingual, 50+ languages
    "internvl2":   "internvl2:8b",            # Strong document QA
    "llava":       "llava:13b",               # General vision fallback
    "moondream":   "moondream:latest",        # Lightweight, fast
}

DEFAULT_VLM_MODEL = "qwen2-vl:7b-instruct"

FINANCIAL_EXTRACTION_PROMPT = """You are a financial document analyst. 
Analyze this document image and extract ALL financial data in structured JSON format.

Return ONLY valid JSON with this exact structure:
{
  "document_language": "<ISO 639-1 code e.g. en, ar, hi, zh, ja>",
  "document_type_hint": "<invoice|purchase_order|goods_receipt|unknown>",
  "vendor_name": "<string or null>",
  "buyer_name": "<string or null>",
  "document_number": "<string or null>",
  "document_date": "<YYYY-MM-DD or null>",
  "currency": "<ISO 4217 code e.g. USD, EUR, INR, SAR, JPY>",
  "subtotal": <number or null>,
  "tax_amount": <number or null>,
  "total_amount": <number or null>,
  "line_items": [
    {
      "description": "<string>",
      "quantity": <number>,
      "unit_price": <number>,
      "total": <number>,
      "unit_of_measure": "<string>",
      "part_number": "<string or null>"
    }
  ],
  "additional_charges": [],
  "handwriting_detected": <true|false>,
  "extraction_confidence": <0.0-1.0>
}

Be precise with numbers. If a field is not visible or not applicable, use null.
Do not add any text outside the JSON."""


class VLMProcessor:
    """
    Visual Language Model processor for extracting structured data
    from complex scanned financial documents.
    
    Uses Ollama-hosted Qwen2-VL-7B by default — a 7B parameter model
    strong at multilingual document understanding.
    """

    def __init__(
        self,
        ollama_base_url: str = "http://localhost:11434",
        model: str = DEFAULT_VLM_MODEL,
        timeout: int = 120,
    ) -> None:
        self.ollama_base_url = ollama_base_url.rstrip("/")
        self.model = model
        self.timeout = timeout
        self._client = httpx.AsyncClient(timeout=httpx.Timeout(timeout))
        logger.info("vlm_processor_initialized", model=model)

    def _encode_image(self, image_bytes: bytes) -> str:
        """Base64 encode image bytes for Ollama API."""
        return base64.b64encode(image_bytes).decode("utf-8")

    def _extract_json_from_response(self, text: str) -> dict:
        """Extract JSON from VLM response, handling markdown fences."""
        text = re.sub(r"```(?:json)?", "", text).strip().strip("`")
        start = text.find("{")
        end = text.rfind("}") + 1
        if start == -1:
            raise ValueError(f"No JSON in VLM response: {text[:300]}")
        return json.loads(text[start:end])

    async def extract_financial_data(
        self,
        page_image_bytes: bytes,
        prompt: str = FINANCIAL_EXTRACTION_PROMPT,
        language_hint: str | None = None,
    ) -> dict[str, Any]:
        """
        Send a rendered PDF page image to the VLM for financial data extraction.
        Returns structured dict with all extracted financial fields.
        """
        lang_addendum = (
            f"\nNote: This document is likely in {language_hint}. Extract accordingly."
            if language_hint else ""
        )

        try:
            resp = await self._client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt + lang_addendum,
                    "images": [self._encode_image(page_image_bytes)],
                    "stream": False,
                    "options": {
                        "temperature": 0.0,
                        "num_predict": 2048,
                    },
                },
            )
            resp.raise_for_status()
            response_text = resp.json().get("response", "")
            result = self._extract_json_from_response(response_text)
            logger.info(
                "vlm_extraction_complete",
                model=self.model,
                language=result.get("document_language"),
                confidence=result.get("extraction_confidence"),
                line_items=len(result.get("line_items", [])),
            )
            return result

        except httpx.ConnectError:
            logger.warning(
                "vlm_ollama_unavailable",
                hint=f"Pull model: ollama pull {self.model}",
            )
            return {"error": "VLM unavailable", "extraction_confidence": 0.0}
        except json.JSONDecodeError as e:
            logger.error("vlm_json_parse_failed", error=str(e))
            return {"error": "JSON parse failed", "extraction_confidence": 0.0}
        except Exception as e:
            logger.error("vlm_extraction_failed", error=str(e))
            return {"error": str(e), "extraction_confidence": 0.0}

    async def detect_language(self, page_image_bytes: bytes) -> str:
        """
        Quick language detection pass on the first page.
        Returns ISO 639-1 code: 'en', 'ar', 'hi', 'zh', 'ja', etc.
        """
        prompt = (
            "Look at this document image. What language is it written in? "
            "Respond with ONLY the ISO 639-1 two-letter language code (e.g. en, ar, hi, zh, ja, ko, ru, de). "
            "Nothing else."
        )
        try:
            resp = await self._client.post(
                f"{self.ollama_base_url}/api/generate",
                json={
                    "model": self.model,
                    "prompt": prompt,
                    "images": [self._encode_image(page_image_bytes)],
                    "stream": False,
                    "options": {"temperature": 0.0, "num_predict": 10},
                },
            )
            resp.raise_for_status()
            lang = resp.json().get("response", "en").strip().lower()[:2]
            logger.debug("vlm_language_detected", lang=lang)
            return lang if re.match(r"^[a-z]{2}$", lang) else "en"
        except Exception:
            return "en"

    async def health_check(self) -> bool:
        """Verify VLM model is available in Ollama."""
        try:
            resp = await self._client.get(f"{self.ollama_base_url}/api/tags")
            models = [m["name"] for m in resp.json().get("models", [])]
            return any(self.model in m for m in models)
        except Exception:
            return False

    async def close(self) -> None:
        await self._client.aclose()
