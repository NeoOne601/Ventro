import asyncio
from src.infrastructure.vector_store.qdrant_adapter import QdrantAdapter
from src.infrastructure.llm.embedding_model import get_embedding_model
from src.application.config import get_settings

async def run():
    doc_id = '91d6f88d-1fb4-4271-9757-ddbbc5af200a'
    settings = get_settings()
    qdrant = QdrantAdapter(host="qdrant", port=6333, collection_name=settings.qdrant_collection_name, embedding_dim=settings.embedding_dimension)
    
    query = "line items purchase order quantity unit price"
    model = await get_embedding_model()
    vec = await model.embed_query(query)
    
    chunks = await qdrant.search(vec, "mas_vgfr_docs", filters={"document_id": doc_id}, top_k=5)
    print("Top 3 chunks for PO-2002:")
    for i, c in enumerate(chunks[:3]):
        print(f"--- Chunk {i} ---")
        print(repr(c.get('payload', {}).get('text', '')))

asyncio.run(run())
