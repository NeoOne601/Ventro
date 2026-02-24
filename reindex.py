import asyncio
from src.presentation.dependencies import get_qdrant, get_doc_processor, get_embedder, get_mongo
from src.application.config import get_settings

async def run():
    doc_ids = [
        '1fe903ac-3071-4662-b2e7-463c9baf805e',
        '2142b9f0-6367-449f-8095-09e159bdd384',
        'd63f2c59-1b45-4526-92d5-0f730d4e7867'
    ]
    
    settings = get_settings()
    qdrant = get_qdrant()
    await qdrant.ensure_collection()
    processor = get_doc_processor()
    embedder = get_embedder()
    
    for doc_id in doc_ids:
        print(f"Re-indexing {doc_id}...")
        path = f"/tmp/mas_vgfr_uploads/{doc_id}.pdf"
        try:
            parsed_doc = await processor.process_pdf(path, document_id=doc_id)
            chunks = await processor.chunk_document_for_embedding(parsed_doc)
            if chunks:
                texts = [c["payload"]["text"] for c in chunks]
                vectors = await embedder.embed_texts(texts)
                for chunk, vector in zip(chunks, vectors):
                    chunk["vector"] = vector
                
                await qdrant.delete_document(doc_id, settings.qdrant_collection_name)
                await qdrant.upsert_chunks(chunks, settings.qdrant_collection_name)
                print(f" -> Inserted {len(chunks)} chunks for {doc_id}")
        except Exception as e:
            print(f"Failed {doc_id}: {str(e)}")

asyncio.run(run())
