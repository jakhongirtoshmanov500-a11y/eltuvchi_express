import os
from dotenv import load_dotenv
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# .env faylidan environment o'zgaruvchilarini yuklaymiz
load_dotenv()

# MUHIM: Endi hech qanday parol kodda hardcode qilinmagan.
# DATABASE_URL albatta .env faylida yoki server (Render) muhitida
# environment variable sifatida berilishi shart.
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError(
        "DATABASE_URL topilmadi! Uni .env fayliga yoki server sozlamalariga "
        "(Render -> Environment) qo'shing. Masalan:\n"
        "DATABASE_URL=postgresql+asyncpg://user:parol@host/dbname"
    )

# Render taqdim etgan postgres:// prefiksini asyncpg drayveri uchun moslashtiramiz
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

# Production'da echo=True ko'p log chiqaradi va sekinlashtiradi,
# shuning uchun buni ham environment orqali boshqaramiz.
DEBUG_SQL = os.getenv("DEBUG_SQL", "false").lower() == "true"

engine = create_async_engine(
    DATABASE_URL,
    echo=DEBUG_SQL,
    pool_pre_ping=True,   # uzilib qolgan ulanishlarni avtomatik tekshiradi
    pool_size=5,
    max_overflow=10,
)

AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
