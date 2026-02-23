import asyncio
import asyncpg
import uuid
import sys
from src.infrastructure.auth.password_handler import hash_password
roles = ['external_auditor', 'ap_analyst', 'ap_manager', 'finance_director', 'admin', 'developer', 'master']

async def seed():
    try:
        # Use database URL that is valid from inside the container
        conn = await asyncpg.connect("postgresql://mas_vgfr_user:mas_vgfr_password@postgres:5432/mas_vgfr")
    except Exception as e:
        print(f"Failed to connect to DB: {e}")
        sys.exit(1)

    org_id = str(uuid.uuid4())
    org_slug = "demo"
    print(f"Creating/verifying organisation '{org_slug}'...")
    
    # insert org if not exists
    await conn.execute(
        "INSERT INTO organisations (id, name, slug, plan) VALUES ($1, $2, $3, $4) ON CONFLICT (slug) DO NOTHING",
        org_id, "Demo Ventro Org", org_slug, "enterprise_plus"
    )
    # Get actual org_id
    org_id = await conn.fetchval("SELECT id::text FROM organisations WHERE slug = $1", org_slug)
    print(f"Org ID is {org_id}")
    
    hashed = hash_password("password123")
    
    # Create main demo user
    print("Creating demo@ventro.io...")
    await conn.execute(
        """
        INSERT INTO users (id, organisation_id, email, full_name, hashed_password, role)
        VALUES ($1, $2::uuid, $3, $4, $5, $6)
        ON CONFLICT (organisation_id, email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password
        """,
        str(uuid.uuid4()), org_id, "demo@ventro.io", "Demo Master", hashed, "master"
    )

    # insert 3 users per role
    count = 0
    for role in roles:
        for i in range(1, 4):
            email = f"{role.replace('_', '')}{i}@{org_slug}.io"
            user_id = str(uuid.uuid4())
            await conn.execute(
                """
                INSERT INTO users (id, organisation_id, email, full_name, hashed_password, role)
                VALUES ($1, $2::uuid, $3, $4, $5, $6)
                ON CONFLICT (organisation_id, email) DO UPDATE SET hashed_password = EXCLUDED.hashed_password
                """,
                user_id, org_id, email, f"{role.replace('_', ' ').title()} {i}", hashed, role
            )
            count += 1
            
    print(f"Seeding complete. Main user: demo@ventro.io. Generated {count} role-based users. Password is 'password123' for all.")

asyncio.run(seed())
