"""
EduBot — Aplicação FastAPI principal
"""

import os
from dotenv import load_dotenv; load_dotenv()
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.routers import parser, alunos, webhook
from app.services.parser import ParserEngine

# Logging
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(name)s | %(levelname)s | %(message)s",
)
logger = logging.getLogger("edubot")


# ============================================================
# Lifespan — inicializa e fecha recursos
# ============================================================
@asynccontextmanager
async def lifespan(app: FastAPI):
    """Gerencia ciclo de vida da aplicação."""
    # Startup
    logger.info("🎓 EduBot iniciando...")

    environment = os.getenv("ENVIRONMENT", "development")
    logger.info(f"Ambiente: {environment}")

    api_key = os.getenv("ANTHROPIC_API_KEY", "")
    if not api_key:
        logger.warning("⚠️ ANTHROPIC_API_KEY não configurada!")

    # Em produção, WA_APP_SECRET é obrigatório — sem ele, qualquer pessoa
    # pode enviar webhooks falsos fingindo ser a Meta/WhatsApp
    if environment == "production" and not os.getenv("WA_APP_SECRET", ""):
        raise RuntimeError(
            "ERRO FATAL: WA_APP_SECRET não está configurado. "
            "Em produção, essa variável é obrigatória para verificar "
            "a autenticidade das mensagens do WhatsApp. "
            "Configure WA_APP_SECRET ou mude ENVIRONMENT para 'development'."
        )

    if environment == "production" and not os.getenv("INTERNAL_API_KEY", ""):
        raise RuntimeError(
            "ERRO FATAL: INTERNAL_API_KEY não está configurada. "
            "Em produção, essa variável é obrigatória para autenticar "
            "endpoints administrativos (/alunos/*, /parser/*). "
            "Configure INTERNAL_API_KEY ou mude ENVIRONMENT para 'development'."
        )

    # Inicializa parser engine (compartilhado entre requests)
    app.state.parser = ParserEngine(
        api_key=api_key,
        model=os.getenv("PARSER_MODEL", "claude-haiku-4-5-20251001"),
    )

    logger.info("✅ EduBot pronto!")
    yield

    # Shutdown
    await app.state.parser.close()
    logger.info("👋 EduBot encerrado.")


# ============================================================
# App FastAPI
# ============================================================
app = FastAPI(
    title="EduBot API",
    description="API do copiloto acadêmico EduBot — organização via WhatsApp",
    version="0.1.0",
    lifespan=lifespan,
)

# CORS (liberar frontend em dev)
app.add_middleware(
    CORSMiddleware,
    allow_origins=os.getenv("CORS_ORIGINS", "*").split(","),
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# ============================================================
# Rotas
# ============================================================
app.include_router(parser.router, prefix="/api/v1", tags=["Parser"])
app.include_router(alunos.router, prefix="/api/v1", tags=["Alunos"])
app.include_router(webhook.router, tags=["WhatsApp Webhook"])


@app.get("/health")
async def health_check():
    """Health check para monitoring."""
    return {"status": "ok", "service": "edubot", "version": "0.1.0"}
