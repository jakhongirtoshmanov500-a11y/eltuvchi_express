import asyncio
from sqlalchemy import text
from database import engine  # database.py dan engine ob'ektini import qiling

async def fix_database():
    async with engine.begin() as conn:
        print("Baza ustunlari tekshirilmoqda va yangilanmoqda...")
        await conn.execute(text("ALTER TABLE partner_profiles ADD COLUMN IF NOT EXISTS commission_rate FLOAT DEFAULT 10.0;"))
        await conn.execute(text("ALTER TABLE partner_profiles ADD COLUMN IF NOT EXISTS opening_time VARCHAR DEFAULT '09:00';"))
        await conn.execute(text("ALTER TABLE partner_profiles ADD COLUMN IF NOT EXISTS closing_time VARCHAR DEFAULT '23:00';"))
        print("✅ Baza muvaffaqiyatli yangilandi!")

if __name__ == "__main__":
    asyncio.run(fix_database())