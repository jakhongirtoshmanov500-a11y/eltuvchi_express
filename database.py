import os
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase

# Environment'dan DATABASE_URL ni o'qiymiz
DATABASE_URL = os.getenv(
    "DATABASE_URL", 
    "postgresql+asyncpg://eltuvchi_db_user:Vux5iwDVAAmBJRHe1APpM87QgQhRij4i@dpg-da81hes9v7es739e7qa0-a/eltuvchi_db"
)

# Render taqdim etgan postgres:// prefiksini asyncpg drayveri uchun moslashtiramiz
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql+asyncpg://", 1)
elif DATABASE_URL.startswith("postgresql://") and not DATABASE_URL.startswith("postgresql+asyncpg://"):
    DATABASE_URL = DATABASE_URL.replace("postgresql://", "postgresql+asyncpg://", 1)

engine = create_async_engine(DATABASE_URL, echo=True)

AsyncSessionLocal = async_sessionmaker(
    bind=engine, 
    class_=AsyncSession, 
    expire_on_commit=False
)

class Base(DeclarativeBase):
    pass

async def get_db():
    async with AsyncSessionLocal() as session:
        yield session