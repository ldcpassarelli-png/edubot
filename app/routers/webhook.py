"""
EduBot — Webhook do WhatsApp Business API.

Fluxo:
  1. Meta faz POST em /webhook
  2. HMAC valida assinatura (Frente 1)
  3. Extrai mensagem do payload (telefone + tipo + conteúdo)
  4. Delega pro serviço de onboarding (máquina de estados)
  5. Envia resposta de volta pro aluno via WhatsApp API
  6. Retorna 200 pro Meta (sempre — senão ele reenvia)

Tipos suportados hoje:
  - text      → trata como resposta no fluxo de onboarding
  - document  → aceita apenas PDF; outros tipos recebem mensagem explicativa

Imagem, áudio, sticker, vídeo e localização NÃO são suportados neste escopo.
Eles recebem resposta gentil pedindo PDF.
"""

import os
import logging
import hashlib
import hmac
from fastapi import APIRouter, Depends, Request, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import get_db
from app.models.database import Mensagem
from app.services import onboarding, whatsapp

logger = logging.getLogger("edubot.webhook")

router = APIRouter()

# Configurações do WhatsApp
VERIFY_TOKEN = os.getenv("WA_VERIFY_TOKEN", "edubot-verify-token")
WA_APP_SECRET = os.getenv("WA_APP_SECRET", "")
ENVIRONMENT = os.getenv("ENVIRONMENT", "development")


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
# Verificação de assinatura HMAC
# ============================================================

async def _verificar_assinatura(request: Request) -> None:
    """
    Verifica a assinatura HMAC-SHA256 enviada pela Meta.
    Garante que a requisição realmente veio do WhatsApp.

    Em development sem WA_APP_SECRET: loga warning e deixa passar.
    Em production sem WA_APP_SECRET: bloqueia (defesa em profundidade).
    Com WA_APP_SECRET configurado: valida a assinatura.
    """
    if not WA_APP_SECRET:
        if ENVIRONMENT == "production":
            logger.error("🚨 WA_APP_SECRET não configurado em produção! Requisição bloqueada.")
            raise HTTPException(status_code=401, detail="Servidor mal configurado.")
        logger.warning(
            "⚠️ Webhook rodando SEM verificação de assinatura — modo desenvolvimento. "
            "Em produção, configure WA_APP_SECRET."
        )
        return

    # WA_APP_SECRET está configurado — verificar assinatura
    signature = request.headers.get("x-hub-signature-256")

    if not signature:
        logger.warning("🚨 Requisição sem header x-hub-signature-256 — possível ataque.")
        raise HTTPException(status_code=401, detail="Assinatura ausente.")

    if not signature.startswith("sha256="):
        logger.warning(f"🚨 Formato de assinatura inválido: {signature[:20]}")
        raise HTTPException(status_code=401, detail="Formato de assinatura inválido.")

    body = await request.body()
    expected = "sha256=" + hmac.new(
        WA_APP_SECRET.encode(),
        body,
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(signature, expected):
        logger.warning("🚨 Assinatura HMAC inválida — requisição rejeitada.")
        raise HTTPException(status_code=401, detail="Assinatura inválida.")


# ============================================================
# Receber mensagens (POST) — toda mensagem chega aqui
# ============================================================

@router.post("/webhook")
async def receber_mensagem(
    request: Request,
    db: AsyncSession = Depends(get_db),
):
    """
    Recebe mensagens do WhatsApp Business API.

    Sempre retorna 200 — se retornarmos erro, Meta reenviará a mensagem,
    causando processamento duplicado. Erros internos ficam nos logs.
    """
    await _verificar_assinatura(request)

    payload = await request.json()

    try:
        mensagem = _extrair_mensagem(payload)
        if mensagem is None:
            # Não era mensagem de aluno (pode ser status update: delivered, read)
            return {"status": "ok"}

        telefone = mensagem["telefone"]
        tipo = mensagem["tipo"]
        conteudo = mensagem["conteudo"]
        wam_id = mensagem.get("whatsapp_message_id")

        # Dedup: o Meta reenvia o webhook em caso de timeout. Se já
        # processamos esse whatsapp_message_id, ignoramos TUDO (não gravamos,
        # não rodamos onboarding, não respondemos) — senão a máquina de estados
        # avançaria duas vezes e o aluno receberia respostas repetidas.
        if wam_id and await _ja_processada(wam_id, db):
            logger.info(f"🔁 Mensagem {wam_id} já processada — ignorando reenvio do Meta.")
            return {"status": "ok"}

        logger.info(f"📩 Mensagem recebida de {telefone}: tipo={tipo}")

        # Grava a ENTRADA — fonte de verdade canônica das conversas (Camada 2)
        conteudo_texto, metadados = _conteudo_e_metadados(
            tipo, conteudo, mensagem.get("wa_timestamp")
        )
        await _gravar_mensagem(
            db, telefone, "entrada", conteudo_texto,
            whatsapp_message_id=wam_id, metadados=metadados,
        )

        # Tipos fora de escopo hoje — responde mas não processa
        if tipo in ("image", "audio", "video", "sticker", "location"):
            await _responder(
                db, telefone,
                "Por enquanto só consigo ler *PDF* e texto. 📎\n"
                "Pode me mandar o plano de aula como arquivo PDF?",
            )
            return {"status": "ok"}

        # Documento não-PDF (ex: docx, xlsx)
        if tipo == "document" and "pdf" not in conteudo.get("mime_type", "").lower():
            logger.info(
                f"Documento não-PDF ignorado de {telefone}: "
                f"{conteudo.get('mime_type')}"
            )
            await _responder(
                db, telefone,
                "Esse tipo de arquivo eu ainda não leio. 😕\n"
                "Por favor, me manda o plano de aula em *PDF*.",
            )
            return {"status": "ok"}

        # Tipo suportado (text ou document/pdf) — delega pro onboarding
        resposta = await onboarding.processar_mensagem(
            telefone=telefone,
            tipo=tipo,
            conteudo=conteudo,
            parser=request.app.state.parser,
            db=db,
        )

        if resposta:
            await _responder(db, telefone, resposta)

    except Exception as e:
        # Capturar tudo pra garantir 200 pro Meta.
        # Logamos exc_info pra diagnosticar via Railway logs.
        logger.error(f"Erro ao processar webhook: {e}", exc_info=True)

    return {"status": "ok"}


# ============================================================
# Helpers — persistência de mensagem (Camada 2)
# ============================================================

async def _ja_processada(whatsapp_message_id: str, db: AsyncSession) -> bool:
    """
    True se já existe uma mensagem gravada com esse whatsapp_message_id.

    Dedup feito na aplicação (o Meta reenvia webhooks). O UNIQUE parcial no
    banco fica para a migration 0003 — até lá, há uma janela de corrida estreita
    entre dois reenvios quase simultâneos. Aceitável para o MVP.
    """
    result = await db.execute(
        select(Mensagem.id).where(Mensagem.whatsapp_message_id == whatsapp_message_id)
    )
    return result.first() is not None


async def _gravar_mensagem(
    db: AsyncSession,
    telefone: str,
    direcao: str,
    conteudo: str,
    whatsapp_message_id: str | None = None,
    metadados: dict | None = None,
) -> Mensagem:
    """Grava uma linha em `mensagem` (entrada ou saída)."""
    msg = Mensagem(
        aluno_telefone=telefone,
        direcao=direcao,
        conteudo=conteudo or f"[{direcao}]",
        whatsapp_message_id=whatsapp_message_id,
        metadados=metadados or {},
    )
    db.add(msg)
    await db.flush()
    return msg


async def _responder(db: AsyncSession, telefone: str, texto: str) -> bool:
    """
    Envia uma resposta ao aluno e, se o Meta aceitar, grava a saída em `mensagem`.

    A saída grava com whatsapp_message_id NULL: enviar_mensagem_texto retorna só
    bool, e nesta sessão whatsapp.py fica intocado (decisão de arquitetura).
    Dívida registrada: quando notificações agendadas entrarem (CC #8), reavaliar
    mover o logging pro serviço de envio e capturar o id que o Meta devolve.
    """
    enviado = await whatsapp.enviar_mensagem_texto(telefone, texto)
    if enviado:
        await _gravar_mensagem(db, telefone, "saida", texto)
    return enviado


def _conteudo_e_metadados(
    tipo: str, conteudo: dict, wa_timestamp: str | None
) -> tuple[str, dict]:
    """
    Deriva o texto a gravar na coluna `conteudo` (NOT NULL) e os metadados (JSONB).

    Para texto: o corpo da mensagem. Para mídia: um marcador legível + os dados
    de mídia (media_id, mime_type) vão pros metadados, não pra coluna conteudo.
    """
    metadados: dict = {"tipo": tipo}
    if wa_timestamp:
        metadados["wa_timestamp"] = wa_timestamp

    if tipo == "text":
        texto = conteudo.get("texto", "") or "[texto vazio]"
    elif tipo == "document":
        nome = conteudo.get("filename") or "arquivo"
        texto = f"[documento] {nome}"
        metadados.update({k: v for k, v in conteudo.items() if v})
    elif tipo == "image":
        texto = "[imagem]"
        metadados.update({k: v for k, v in conteudo.items() if v})
    else:
        texto = f"[{tipo}]"

    return texto, metadados


# ============================================================
# Helpers
# ============================================================

def _extrair_mensagem(payload: dict) -> dict | None:
    """
    Extrai dados úteis do payload do Meta.

    Estrutura esperada:
        {
          "entry": [{
            "changes": [{
              "value": {
                "messages": [{
                  "from": "5511999999999",
                  "type": "text" | "document" | "image" | ...,
                  "text": {"body": "..."},
                  "document": {"id": "...", "mime_type": "..."},
                  ...
                }]
              }
            }]
          }]
        }

    Retorna dict com {telefone, tipo, conteudo} ou None se:
    - payload vazio/malformado
    - não há messages (ex: é status update de delivered/read)
    """
    entry = payload.get("entry", [])
    if not entry:
        return None

    changes = entry[0].get("changes", [])
    if not changes:
        return None

    value = changes[0].get("value", {})
    messages = value.get("messages", [])

    if not messages:
        # Status update (delivered, read, failed) — não é mensagem do aluno
        return None

    mensagem = messages[0]
    telefone = mensagem.get("from", "")
    tipo = mensagem.get("type", "")
    whatsapp_message_id = mensagem.get("id", "")
    wa_timestamp = mensagem.get("timestamp")

    if not telefone or not tipo:
        logger.warning(f"Mensagem sem telefone ou tipo: {mensagem}")
        return None

    # Montar conteúdo baseado no tipo
    conteudo: dict = {}

    if tipo == "text":
        conteudo = {"texto": mensagem.get("text", {}).get("body", "")}

    elif tipo == "document":
        doc = mensagem.get("document", {})
        conteudo = {
            "media_id": doc.get("id", ""),
            "mime_type": doc.get("mime_type", ""),
            "filename": doc.get("filename", ""),
        }

    elif tipo == "image":
        img = mensagem.get("image", {})
        conteudo = {
            "media_id": img.get("id", ""),
            "mime_type": img.get("mime_type", "image/jpeg"),
        }

    # Outros tipos (audio, video, sticker, location) ficam com conteudo={}
    # — o handler no POST trata esses casos explicitamente.

    return {
        "telefone": telefone,
        "tipo": tipo,
        "conteudo": conteudo,
        "whatsapp_message_id": whatsapp_message_id,
        "wa_timestamp": wa_timestamp,
    }
