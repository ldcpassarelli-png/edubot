"""
EduBot — Aplicação FastAPI principal
"""

import os
from dotenv import load_dotenv; load_dotenv()
import logging
from contextlib import asynccontextmanager
from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from slowapi.errors import RateLimitExceeded

from app.limiter import limiter
from app.routers import parser, alunos, webhook
from app.services.parser import ParserEngine
from app.services.classificador import ClassificadorEngine

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

    # Warning não-fatal: sem essas vars o bot recebe webhooks mas fica mudo
    if environment == "production":
        wa_token = os.getenv("WA_ACCESS_TOKEN", "")
        wa_phone_id = os.getenv("WA_PHONE_NUMBER_ID", "")
        if not wa_token:
            logger.warning(
                "🚨 WA_ACCESS_TOKEN não configurado! "
                "O bot vai receber mensagens do WhatsApp mas NÃO vai conseguir "
                "responder até essa variável ser configurada no Railway."
            )
        if not wa_phone_id:
            logger.warning(
                "🚨 WA_PHONE_NUMBER_ID não configurado! "
                "O bot vai receber mensagens do WhatsApp mas NÃO vai conseguir "
                "responder até essa variável ser configurada no Railway."
            )

    # Inicializa parser engine (compartilhado entre requests)
    app.state.parser = ParserEngine(
        api_key=api_key,
        model=os.getenv("PARSER_MODEL", "claude-haiku-4-5-20251001"),
    )

    # Inicializa classificador (Camada 2) — Haiku dedicado, cliente próprio.
    app.state.classificador = ClassificadorEngine(api_key=api_key)

    logger.info("✅ EduBot pronto!")
    yield

    # Shutdown
    await app.state.parser.close()
    await app.state.classificador.close()
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
# Rate limiting (Frente 3) — teto global no webhook
# ============================================================
app.state.limiter = limiter


async def _ratelimit_handler(request: Request, exc: RateLimitExceeded):
    """
    O webhook DEVE devolver 200 pro Meta mesmo quando o teto estoura — senão o
    Meta reenvia a mensagem e piora o loop. Só NÃO processa (não chama a API).
    Outras rotas (nenhuma limitada hoje) recebem 429 padrão.
    """
    if request.url.path == "/webhook":
        logger.warning("🧯 Teto de rate limit no /webhook — devolvendo 200 sem processar.")
        return JSONResponse(status_code=200, content={"status": "ok"})
    return JSONResponse(status_code=429, content={"detail": "rate limit exceeded"})


app.add_exception_handler(RateLimitExceeded, _ratelimit_handler)


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
