"""
Classification Agent - Pre-Reconciliation Document Validation
Acts as a security and integrity gate. Ensures users uploaded the correct document types
into the corresponding file slots before substantive extraction begins.
"""
from __future__ import annotations

import asyncio
import json
from typing import Any

import structlog

from ...domain.interfaces import ILLMClient, IVectorStore
from ...infrastructure.security.prompt_sanitizer import sanitize_document_text

logger = structlog.get_logger(__name__)

CLASSIFICATION_SYSTEM_PROMPT = """You are a financial document validator.
Your purpose is to quickly examine a text snippet and determine if it appears to belong to the expected document class.
Because you are only seeing a partial snippet of the document (often just the header or first few items), you should be lenient. As long as there are strong indicators or titles matching the expected type, consider it valid even if other standard elements are missing.
You must respond with valid JSON containing a boolean "is_valid" and a string "rationale"."""

CLASSIFICATION_PROMPT_TEMPLATE = """Determine if the following text snippet is from a {doc_type}.

Text Snippet:
{text}

Return JSON with this exact schema:
{{
  "is_valid": true_or_false,
  "rationale": "One brief sentence explaining why it appears to be or not be a {doc_type}."
}}
"""


class ClassificationAgent:
    """Verifies semantic document types before extraction to prevent human upload errors."""

    def __init__(self, llm: ILLMClient, vector_store: IVectorStore) -> None:
        self.llm = llm
        self.vector_store = vector_store

    async def _fetch_first_chunk(self, document_id: str, collection_name: str = "mas_vgfr_docs") -> str:
        """Fetch essentially the first page/snippet of the document for cheap classification."""
        try:
            if hasattr(self.vector_store, "get_by_filter"):
                results = await self.vector_store.get_by_filter(
                    collection_name=collection_name,
                    filters={"document_id": document_id},
                    limit=3,
                )
            else:
                # We don't need semantic search here, just grab any chunk belonging to the doc
                # to see the header/initial text. We do a dummy search vector [0.1]*dim
                dummy_vector = [0.1] * 768  # Assuming Nomic-embed-text dim
                results = await self.vector_store.search(
                    query_vector=dummy_vector,
                    collection_name=collection_name,
                    filters={"document_id": document_id},
                    top_k=3,
                )
            if not results:
                return ""
            
            # Combine up to top 3 chunks to get enough context near the "top" of the document
            full_text = "\n".join([chunk.get("payload", {}).get("text", "") for chunk in results])
            return full_text
        except Exception as e:
            logger.error("classification_chunk_fetch_failed", doc_id=document_id, error=str(e))
            return ""

    async def _validate_document(self, doc_id: str, expected_type: str) -> tuple[str, dict[str, Any]]:
        """Validate a single document against its expected type."""
        if not doc_id:
            return expected_type, {"is_valid": False, "rationale": "No document ID provided."}
            
        logger.info("validating_document", doc_type=expected_type, doc_id=doc_id)
        
        text = await self._fetch_first_chunk(doc_id)
        if not text.strip():
            return expected_type, {"is_valid": False, "rationale": "Could not extract readable text from document."}

        # Sanitize text like the ExtractionAgent to prevent prompt injection
        sanitized = sanitize_document_text(text, source=f"classification_{expected_type}", doc_id=doc_id)
        
        prompt = CLASSIFICATION_PROMPT_TEMPLATE.format(
            doc_type=expected_type.replace('_', ' ').title(),
            text=sanitized.cleaned_text[:2000]  # Limit context for speed and cost
        )
        
        try:
            # Use extremely low temperature for deterministic validation
            response = await self.llm.complete(
                prompt=prompt,
                system_prompt=CLASSIFICATION_SYSTEM_PROMPT,
                temperature=0.0,
                json_mode=True
            )
            result = json.loads(response)
            
            # Fallback type check just in case LLM wanders
            if not isinstance(result.get("is_valid"), bool):
                result["is_valid"] = str(result.get("is_valid")).lower() == "true"
                
            return expected_type, result
            
        except Exception as e:
            logger.error("classification_llm_failed", doc_type=expected_type, error=str(e))
            return expected_type, {"is_valid": False, "rationale": f"Internal validation error: {str(e)}"}

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """
        Execute concurrent validation over all uploaded documents.
        Returns a dict of validation errors if any document fails.
        """
        validations = {
            "purchase_order": state.get("po_document_id", ""),
            "goods_receipt_note": state.get("grn_document_id", ""),
            "invoice": state.get("invoice_document_id", "")
        }
        
        tasks = [
            self._validate_document(doc_id, expected_type)
            for expected_type, doc_id in validations.items() if doc_id
        ]
        
        if not tasks:
            return {"classification_errors": ["No documents provided for validation."]}
            
        outcomes = await asyncio.gather(*tasks, return_exceptions=False)
        
        errors = []
        for expected_type, result in outcomes:
            if not result.get("is_valid", False):
                human_type = expected_type.replace('_', ' ').title()
                rationale = result.get('rationale', 'Unknown reason.')
                errors.append(f"Validation Failed for {human_type}: {rationale}")
                
        logger.info(
            "classification_completed",
            total_checked=len(tasks),
            failures=len(errors)
        )
        
        return {"classification_errors": errors}
