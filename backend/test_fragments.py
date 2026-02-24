import asyncio
from src.presentation.dependencies import get_qdrant
from src.infrastructure.llm.embedding_model import get_embedding_model
from src.application.config import get_settings

async def run():
    doc_id = 'd63f2c59-1b45-4526-92d5-0f730d4e7867'
    qdrant = get_qdrant()
    
    query = "line items purchase order quantity unit price"
    model = await get_embedding_model()
    vec = await model.embed_query(query)
    
    chunks = await qdrant.search(vec, "mas_vgfr_docs", filters={"document_id": doc_id}, top_k=2)
    print("Top chunk fragments for PO:")
    for i, c in enumerate(chunks[:1]):
        payload = c.get('payload', {})
        print(f"--- Chunk {i} ---")
        print("Chunk BBOX:", payload.get('bbox'))
        frags = payload.get('fragments', [])
        print(f"Num fragments: {len(frags)}")
        for f in frags[:20]:
            print(f"  Frag: {repr(f.get('text'))} -> {f.get('bbox')}")

asyncio.run(run())
