import asyncio
from logging.config import fileConfig

from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine
from alembic import context

# Loyihamizning Base va barcha modellarini import qilamiz — shu orqali
# Alembic "hozir modelda nima bor, bazada nima bor" ni solishtira oladi.
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from database import Base, DATABASE_URL
import models  # noqa: F401 — barcha model klasslari Base.metadata'ga ro'yxatdan o'tishi uchun kerak

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Modeldagi "haqiqat manbai" — shu orqali "avtomatik migratsiya yaratish"
# (autogenerate) ishlaydi: Alembic shu bilan bazani solishtiradi.
target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """SQL fayl sifatida (bazaga ulanmasdan) migratsiya yaratish uchun."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    context.configure(connection=connection, target_metadata=target_metadata)
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations():
    """Loyihamiz asyncpg (async) drayver ishlatgani uchun, migratsiyani
    ham async engine orqali bajaramiz."""
    connectable = create_async_engine(DATABASE_URL, poolclass=pool.NullPool)

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
