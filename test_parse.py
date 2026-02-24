import asyncio
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from sqlalchemy.future import select
from src.infrastructure.database.postgres_adapter import ReconciliationSessionORM, PostgreSQLAdapter

async def run():
    adapter = PostgreSQLAdapter("postgresql://mas_vgfr_user:mas_vgfr_password@localhost:5432/mas_vgfr")
    async with adapter.async_session() as db:
        result = await db.execute(select(ReconciliationSessionORM).where(ReconciliationSessionORM.id == '8b022f15-d091-4c34-888c-4896bcd868d1'))
        orm = result.scalar_one_or_none()
        if orm:
            try:
                from src.domain.entities import ReconciliationVerdict
                print("Status:", orm.status)
                print("Verdict JSON:", type(orm.verdict_json), bool(orm.verdict_json))
                v = ReconciliationVerdict(
                    session_id=orm.id,
                    po_document_id=orm.po_document_id,
                    grn_document_id=orm.grn_document_id,
                    invoice_document_id=orm.invoice_document_id,
                    status=orm.status
                )
                v.__dict__.update(orm.verdict_json)
                print("Successfully parsed verdict!")
            except Exception as e:
                print(f"ERROR: {e}")

asyncio.run(run())
