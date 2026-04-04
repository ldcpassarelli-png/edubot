"""
EduBot — Configuração do banco de dados (async SQLAlchemy)
"""

import os
from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)

# URL do banco — usa variável de ambiente, fallback pra local
DATABASE_URL = os.getenv(
    "DATABASE_URL",
    "postgresql+asyncpg://edubot:edubot@localhost:5432/edubot"
)

# Engine async
engine = create_async_engine(
    DATABASE_URL,
    echo=os.getenv("SQL_DEBUG", "false").lower() == "true",
    pool_size=10,
    max_overflow=20,
)

# Session factory
async_session = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


async def get_db() -> AsyncSession:
    """Dependency injection para FastAPI — fornece sessão do banco."""
    async with async_session() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()
