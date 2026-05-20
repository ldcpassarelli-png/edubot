"""
EduBot — Alembic env.py (async, asyncpg)

Segurança: este script RECUSA rodar contra URLs que contenham
'railway.app' ou 'up.railway'. Se DATABASE_URL não existir,
usa fallback local (localhost:5432).
"""

import asyncio
import os
import sys

from alembic import context
from sqlalchemy import pool
from sqlalchemy.ext.asyncio import create_async_engine

# Garante que imports de app/ funcionem
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.models.database import Base

# ============================================================
# Resolver URL do banco com proteção contra produção
# ============================================================

DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://edubot:edubot@localhost:5432/edubot",
)

# Proteção: NUNCA rodar contra Railway/produção
_BLOCKED_PATTERNS = ["railway.app", "up.railway", "railway.internal"]
for pattern in _BLOCKED_PATTERNS:
    if pattern in DATABASE_URL:
        raise RuntimeError(
            f"\U0001f6a8 BLOQUEADO: DATABASE_URL contém '{pattern}'. "
            f"Alembic NUNCA deve rodar contra produção. "
            f"Use um banco local ou de teste."
        )

target_metadata = Base.metadata


def run_migrations_offline() -> None:
    """Gera SQL sem conectar (para review manual)."""
    context.configure(
        url=DATABASE_URL,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
    )
    with context.begin_transaction():
        context.run_migrations()


def do_run_migrations(connection):
    """Executa migrations com conexão ativa."""
    context.configure(
        connection=connection,
        target_metadata=target_metadata,
    )
    with context.begin_transaction():
        context.run_migrations()


async def run_async_migrations() -> None:
    """Cria engine async e roda migrations."""
    connectable = create_async_engine(
        DATABASE_URL,
        poolclass=pool.NullPool,
    )

    async with connectable.connect() as connection:
        await connection.run_sync(do_run_migrations)

    await connectable.dispose()


def run_migrations_online() -> None:
    """Entry point para modo online (async)."""
    asyncio.run(run_async_migrations())


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
