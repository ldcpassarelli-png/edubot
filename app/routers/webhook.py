"""
EduBot — Webhook do WhatsApp Business API
Recebe mensagens dos alunos e processa (texto, PDF, imagem).
"""

import os
import logging
import hashlib
import hmac
from fastapi import APIRouter, Request, HTTPException, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select

from app.models.connection import get_db
from app.models.database import Aluno

logger = logging.getLogger("edubot.webhook")

router = APIRouter()

# Configurações do WhatsApp
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "edubot-verify-token")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")


# ============================================================
# Verificação do webhook (GET) — Meta envia isso pra validar
# ============================================================

@router.get("/webhook")
async def verificar_webhook(request: Request):
    """
    Endpoint de verificação do webhook do WhatsApp.
    Meta faz GET com hub.mode, hub.verify_token e hub.challenge.
    """
    params = request.query_params

    mode = params.get("hub.mode")
    token = params.get("hub.verify_token")
    challenge = params.get("hub.challenge")

    if mode == "subscribe" and token == VERIFY_TOKEN:
        logger.info("✅ Webhook verificado com sucesso!")
        return int(challenge)

    logger.warning(f"⚠️ Verificação falhou. Token: {token}")
    raise HTTPException(status_code=403, detail="Token inválido.")


# ============================================================
# Receber mensagens (POST) — toda mensagem chega aqui
# ============================================================

@router.post("/webhook")
async def receber_mensagem(request: Request):
    """
    Recebe mensagens do WhatsApp Business API.
    Processa texto, documentos (PDF) e imagens.
    """
    # Validar assinatura (segurança)
    if WA_APP_SECRET:
        signature = request.headers.get("x-hub-signature-256", "")
        body = await request.body()
        expected = "sha256=" + hmac.new(
            WA_APP_SECRET.encode(),
            body,
            hashlib.sha256,
        ).hexdigest()

        if not hmac.compare_digest(signature, expected):
            logger.warning("⚠️ Assinatura inválida no webhook!")
            raise HTTPException(status_code=403, detail="Assinatura inválida.")

    # Parsear payload
    payload = await request.json()

    try:
        # Extrair dados da mensagem
        entry = payload.get("entry", [])
        if not entry:
            return {"status": "ok"}

        changes = entry[0].get("changes", [])
        if not changes:
            return {"status": "ok"}

        value = changes[0].get("value", {})
        messages = value.get("messages", [])

        if not messages:
            # Pode ser status update (delivered, read) — ignorar
            return {"status": "ok"}

        mensagem = messages[0]
        telefone = mensagem.get("from", "")  # formato: 5511999999999
        msg_type = mensagem.get("type", "")
        msg_id = mensagem.get("id", "")

        logger.info(f"📩 Mensagem recebida de {telefone}: tipo={msg_type}")

        # ----------------------------------------------------------
        # Processar por tipo de mensagem
        # ----------------------------------------------------------

        if msg_type == "text":
            texto = mensagem.get("text", {}).get("body", "")
            await _processar_texto(telefone, texto, msg_id, request)

        elif msg_type == "document":
            doc = mensagem.get("document", {})
            mime_type = doc.get("mime_type", "")
            media_id = doc.get("id", "")
            if "pdf" in mime_type:
                await _processar_documento(telefone, media_id, msg_id, request)
            else:
                logger.info(f"Documento ignorado: {mime_type}")

        elif msg_type == "image":
            img = mensagem.get("image", {})
            media_id = img.get("id", "")
            mime_type = img.get("mime_type", "image/jpeg")
            await _processar_imagem(telefone, media_id, mime_type, msg_id, request)

        else:
            logger.info(f"Tipo de mensagem ignorado: {msg_type}")

    except Exception as e:
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)

    # Sempre retornar 200 pro WhatsApp não reenviar
    return {"status": "ok"}


# ============================================================
# Handlers internos
# ============================================================

async def _processar_texto(telefone: str, texto: str, msg_id: str, request: Request):
    """Processa mensagem de texto do aluno."""
    texto_lower = texto.strip().lower()

    # Comandos de onboarding
    if texto_lower in ("oi", "olá", "ola", "hey", "começar", "start"):
        logger.info(f"Onboarding iniciado para {telefone}")
        # TODO: Enviar mensagem de boas-vindas
        # TODO: Criar/buscar aluno no banco
        return

    # Confirmação pós-parsing
    if texto_lower in ("sim", "s", "yes", "confirma", "ok"):
        logger.info(f"Confirmação recebida de {telefone}")
        # TODO: Salvar eventos no banco
        return

    if texto_lower in ("não", "nao", "n", "no"):
        logger.info(f"Rejeição recebida de {telefone}")
        # TODO: Pedir que envie novamente
        return

    # Texto longo = possível plano de aula colado
    if len(texto) > 200:
        logger.info(f"Texto longo recebido de {telefone} — tentando parsear")
        parser = request.app.state.parser
        resultado = await parser.parsear_texto(texto)

        if resultado.sucesso:
            resumo = parser.gerar_resumo_confirmacao(resultado.dados)
            logger.info(f"Parser OK: {resultado.dados.materia}")
            # TODO: Enviar resumo via WhatsApp
            # TODO: Armazenar resultado temporariamente (Redis)
        else:
            logger.warning(f"Parser falhou: {resultado.erro}")
            # TODO: Enviar mensagem de erro
        return

    # Pergunta do chat interativo
    logger.info(f"Pergunta do chat: {texto[:100]}")
    # TODO: Processar com engine conversacional
    # TODO: Buscar contexto do aluno no banco
    # TODO: Responder via WhatsApp


async def _processar_documento(telefone: str, media_id: str, msg_id: str, request: Request):
    """Processa documento PDF enviado pelo aluno."""
    logger.info(f"PDF recebido de {telefone}, media_id={media_id}")
    # TODO: Baixar PDF via Media API do WhatsApp
    # TODO: Parsear com parser.parsear_pdf()
    # TODO: Enviar resumo de confirmação


async def _processar_imagem(
    telefone: str, media_id: str, mime_type: str, msg_id: str, request: Request
):
    """Processa foto de plano de aula."""
    logger.info(f"Imagem recebida de {telefone}, media_id={media_id}")
    # TODO: Baixar imagem via Media API do WhatsApp
    # TODO: Parsear com parser.parsear_imagem()
    # TODO: Enviar resumo de confirmação
