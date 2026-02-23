import asyncio
import asyncpg
import os
from glob import glob

async def run():
    url = os.environ.get("DATABASE_URL", "postgresql://mas_vgfr_user:mas_vgfr_password@localhost:5432/mas_vgfr")
    # asyncpg expects postgresql:// not postgresql+asyncpg://
    url = url.replace("+asyncpg", "")
    print(f"Connecting to {url}")
    conn = await asyncpg.connect(url)
    
    files = sorted(glob("src/infrastructure/database/migrations/*.sql"))
    for f in files:
        print(f"Running {f}...")
        with open(f, "r") as sql_file:
            sql = sql_file.read()
            # Split commands by semicolon, or just execute the whole block
            try:
                await conn.execute(sql)
                print(f"Success: {f}")
            except Exception as e:
                print(f"Error in {f}: {e}")
                
    await conn.close()
    print("Done")

if __name__ == "__main__":
    asyncio.run(run())
