import asyncio
from src.infrastructure.llm.groq_client import GroqClient
from src.application.agents.extraction_agent import ExtractionAgent
from src.application.config import get_settings
from src.presentation.dependencies import get_qdrant

async def run():
    settings = get_settings()
    llm = GroqClient(settings.groq_api_key, model='llama-3.3-70b-versatile')
    qdrant = get_qdrant()
    agent = ExtractionAgent(llm, qdrant)
    
    state = {
        "po_document_id": "d63f2c59-1b45-4526-92d5-0f730d4e7867",
        "grn_document_id": "2142b9f0-6367-449f-8095-09e159bdd384",
        "invoice_document_id": "1fe903ac-3071-4662-b2e7-463c9baf805e"
    }
    
    res = await agent.run(state)
    citations = res.get("extracted_citations", [])
    print(f"Found {len(citations)} citations:")
    for c in citations:
        print(f"{c['document_type']} - {c['text']}: {c['bbox']}")

asyncio.run(run())
