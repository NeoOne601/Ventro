"""
Extraction Agent - Bounding-Box Aware RAG with Cross-Encoder Reranking
"""
from __future__ import annotations

import json
from typing import Any

import structlog
from sentence_transformers import CrossEncoder

from ...domain.interfaces import ILLMClient, IVectorStore

logger = structlog.get_logger(__name__)

EXTRACTION_SYSTEM_PROMPT = """You are a precise financial document extraction specialist.
Your task is to extract structured line items from financial documents.
Always respond with valid JSON. Include all extracted values with their exact text as found.
Never hallucinate or infer values not explicitly present in the document text."""

EXTRACTION_PROMPT_TEMPLATE = """Extract all line items from the following {doc_type} document text.

Document Text:
{text}

Return a JSON array of line items with this exact schema:
{{
  "line_items": [
    {{
      "description": "exact product/service description",
      "quantity": 0.0,
      "unit_price": 0.0,
      "total_amount": 0.0,
      "unit_of_measure": "unit/each/kg/etc",
      "part_number": "optional part number or null",
      "raw_text": "exact text as found",
      "row_index": 0,
      "confidence": 0.95
    }}
  ],
  "document_totals": {{
    "subtotal": 0.0,
    "tax_rate": 0.0,
    "tax_amount": 0.0,
    "total": 0.0,
    "currency": "USD"
  }},
  "document_metadata": {{
    "vendor_name": "",
    "document_number": "",
    "document_date": "",
    "payment_terms": ""
  }}
}}
"""


class ExtractionAgent:
    """
    Retrieves and extracts precise data from the vector database.
    Implements multi-hop reasoning, metadata-filtered semantic search,
    and Cross-Encoder reranking.
    """

    def __init__(self, llm: ILLMClient, vector_store: IVectorStore) -> None:
        self.llm = llm
        self.vector_store = vector_store
        self._reranker: CrossEncoder | None = None

    def _get_reranker(self) -> CrossEncoder:
        if self._reranker is None:
            self._reranker = CrossEncoder("cross-encoder/ms-marco-MiniLM-L-6-v2")
        return self._reranker

    async def _extract_from_text(self, text: str, doc_type: str) -> dict[str, Any]:
        """Use LLM to extract structured data from document text."""
        prompt = EXTRACTION_PROMPT_TEMPLATE.format(doc_type=doc_type, text=text[:8000])
        response = await self.llm.complete(
            prompt=prompt,
            system_prompt=EXTRACTION_SYSTEM_PROMPT,
            temperature=0.0,
            json_mode=True,
        )
        try:
            return json.loads(response)
        except json.JSONDecodeError:
            logger.warning("extraction_json_parse_failed", doc_type=doc_type)
            return {"line_items": [], "document_totals": {}, "document_metadata": {}}

    async def _fetch_document_chunks(
        self, document_id: str, collection_name: str, query_vector: list[float]
    ) -> list[dict[str, Any]]:
        """Fetch relevant chunks from vector store with bounding box metadata."""
        results = await self.vector_store.search(
            query_vector=query_vector,
            collection_name=collection_name,
            filters={"document_id": document_id},
            top_k=20,
        )
        return results

    async def run(self, state: dict[str, Any]) -> dict[str, Any]:
        """Execute extraction for all three document types."""
        from ...infrastructure.llm.embedding_model import get_embedding_model

        embedding_model = await get_embedding_model()

        # Extraction queries
        queries = {
            "po": ("line items purchase order quantity unit price", state["po_document_id"]),
            "grn": ("goods receipt quantity received units", state["grn_document_id"]),
            "invoice": ("invoice line items amount due tax total", state["invoice_document_id"]),
        }

        results: dict[str, Any] = {"extracted_citations": []}

        for doc_type, (query, doc_id) in queries.items():
            logger.info("extracting_document", doc_type=doc_type, doc_id=doc_id)

            if not doc_id:
                continue

            # Generate query embedding
            query_vector = await embedding_model.embed_query(query)

            # Retrieve relevant chunks with bounding boxes
            chunks = await self._fetch_document_chunks(doc_id, "mas_vgfr_docs", query_vector)

            if not chunks:
                logger.warning("no_chunks_found", doc_type=doc_type, doc_id=doc_id)
                results[f"{doc_type}_line_items"] = []
                continue

            # Rerank with Cross-Encoder for precision
            if len(chunks) > 5:
                reranker = self._get_reranker()
                pairs = [(query, c.get("payload", {}).get("text", "")) for c in chunks]
                scores = reranker.predict(pairs)
                ranked = sorted(zip(scores, chunks), key=lambda x: x[0], reverse=True)
                chunks = [c for _, c in ranked[:10]]

            # Aggregate text from top chunks
            full_text = "\n\n".join([c.get("payload", {}).get("text", "") for c in chunks])

            # LLM extraction
            extracted = await self._extract_from_text(full_text, doc_type)
            line_items = extracted.get("line_items", [])

            # Attach bounding box citations from retrieved chunks
            for item in line_items:
                for chunk in chunks:
                    payload = chunk.get("payload", {})
                    if item.get("raw_text", "") and item["raw_text"][:30] in payload.get("text", ""):
                        item["bbox"] = payload.get("bbox")
                        item["page"] = payload.get("page", 0)
                        item["document_id"] = doc_id
                        citation = {
                            "document_id": doc_id,
                            "document_type": doc_type,
                            "text": item.get("description", ""),
                            "value": str(item.get("total_amount", "")),
                            "bbox": payload.get("bbox"),
                            "page": payload.get("page", 0),
                        }
                        results["extracted_citations"].append(citation)
                        break

            results[f"{doc_type}_line_items"] = line_items
            results[f"{doc_type}_parsed"] = {
                "line_items": line_items,
                "totals": extracted.get("document_totals", {}),
                "metadata": extracted.get("document_metadata", {}),
                "document_id": doc_id,
            }

        return results
