"""
EduBot — Serviço de comunicação com WhatsApp Business API (Meta Graph).

Responsabilidades:
- Enviar mensagens de texto ao aluno
- Baixar mídia (PDF) enviada pelo aluno via WhatsApp

Dependências de configuração:
- WA_ACCESS_TOKEN — token de acesso da API (Meta panel, 24h em dev)
- WA_PHONE_NUMBER_ID — ID do número de telefone Business (sandbox ou próprio)
"""

import os
import logging
from typing import Optional

import httpx

logger = logging.getLogger("edubot.whatsapp")

# ============================================================
# Configuração
# ============================================================

WA_ACCESS_TOKEN = os.getenv("WA_ACCESS_TOKEN", "")
WA_PHONE_NUMBER_ID = os.getenv("WA_PHONE_NUMBER_ID", "")
WA_GRAPH_VERSION = "v25.0"
WA_GRAPH_BASE = f"https://graph.facebook.com/{WA_GRAPH_VERSION}"

# Timeout generoso porque Meta pode ser lento em algumas regiões
HTTP_TIMEOUT = 30.0

# Tamanho máximo de mídia que aceitamos baixar (20 MB é o limite do Meta pra PDF)
MAX_MEDIA_BYTES = 20 * 1024 * 1024


# ============================================================
# Envio de mensagem de texto
# ============================================================

async def enviar_mensagem_texto(telefone: str, texto: str) -> bool:
    """
    Envia mensagem de texto simples via WhatsApp Business API.

    Args:
        telefone: número no formato internacional sem + (ex: "5511999999999")
        texto: conteúdo da mensagem (até 4096 chars)

    Returns:
        True se envio foi aceito pelo Meta (status 200).
        False caso contrário — erro é logado com detalhes.

    Nota: NÃO levanta exceção. Falha de envio é logada mas não quebra o fluxo,
    porque queremos sempre retornar 200 ao webhook do Meta (senão ele reenvia).
    """
    if not WA_ACCESS_TOKEN or not WA_PHONE_NUMBER_ID:
        logger.error(
            "🚨 WA_ACCESS_TOKEN ou WA_PHONE_NUMBER_ID não configurado. "
            "Não é possível enviar mensagem."
        )
        return False

    if not texto:
        logger.warning("Tentativa de enviar mensagem vazia — ignorando.")
        return False

    # Meta tem limite de 4096 chars por mensagem. Truncar com indicador.
    if len(texto) > 4096:
        logger.warning(f"Mensagem longa ({len(texto)} chars) — truncando para 4096.")
        texto = texto[:4090] + "[...]"

    url = f"{WA_GRAPH_BASE}/{WA_PHONE_NUMBER_ID}/messages"
    headers = {
        "Authorization": f"Bearer {WA_ACCESS_TOKEN}",
        "Content-Type": "application/json",
    }
    payload = {
        "messaging_product": "whatsapp",
        "recipient_type": "individual",
        "to": telefone,
        "type": "text",
        "text": {"body": texto, "preview_url": False},
    }

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            response = await client.post(url, headers=headers, json=payload)

        if response.status_code == 200:
            logger.info(f"📤 Mensagem enviada para {telefone} ({len(texto)} chars)")
            return True

        # Logar erros com detalhes pra diagnóstico
        _logar_erro_envio(response, telefone)
        return False

    except httpx.TimeoutException:
        logger.error(f"⏱️  Timeout ao enviar mensagem para {telefone}")
        return False

    except Exception as e:
        logger.error(f"Erro inesperado ao enviar mensagem para {telefone}: {e}", exc_info=True)
        return False


def _logar_erro_envio(response: httpx.Response, telefone: str) -> None:
    """Interpreta resposta de erro do Meta e loga com contexto útil."""
    status = response.status_code

    try:
        erro_body = response.json()
    except Exception:
        erro_body = {"raw": response.text[:500]}

    # Códigos comuns do Meta
    erro_meta = erro_body.get("error", {})
    codigo = erro_meta.get("code")
    mensagem = erro_meta.get("message", "sem mensagem")

    if status == 401 or codigo == 190:
        logger.error(
            f"🔑 WA_ACCESS_TOKEN inválido ou expirado. "
            f"Regenere no painel do Meta e atualize Railway. "
            f"Detalhes: {mensagem}"
        )
    elif codigo == 131030:
        logger.error(
            f"📵 Número {telefone} não está autorizado a receber mensagens "
            f"(dev mode do Meta). Adicione como recipient no painel."
        )
    elif status == 400:
        logger.error(f"❌ Requisição inválida para {telefone}: {mensagem}")
    elif status == 429:
        logger.error(f"🚦 Rate limit do Meta atingido.")
    else:
        logger.error(f"Erro ao enviar ({status}) para {telefone}: {erro_body}")


# ============================================================
# Download de mídia (PDF)
# ============================================================

async def baixar_midia(media_id: str) -> Optional[tuple[bytes, str]]:
    """
    Baixa mídia enviada pelo aluno via WhatsApp.

    Processo em 2 passos (como Meta exige):
      1. GET /{media_id} → retorna JSON com URL temporária assinada
      2. GET <url_temporaria> → retorna bytes do arquivo

    Args:
        media_id: ID da mídia fornecido no payload do webhook

    Returns:
        Tupla (bytes_do_arquivo, mime_type) em caso de sucesso.
        None se download falhar — erro é logado com detalhes.
    """
    if not WA_ACCESS_TOKEN:
        logger.error("🚨 WA_ACCESS_TOKEN não configurado. Não é possível baixar mídia.")
        return None

    if not media_id:
        logger.warning("baixar_midia chamado com media_id vazio.")
        return None

    headers = {"Authorization": f"Bearer {WA_ACCESS_TOKEN}"}

    try:
        async with httpx.AsyncClient(timeout=HTTP_TIMEOUT) as client:
            # Passo 1: pegar URL temporária
            meta_url = f"{WA_GRAPH_BASE}/{media_id}"
            resp_meta = await client.get(meta_url, headers=headers)

            if resp_meta.status_code != 200:
                logger.error(
                    f"Erro ao consultar metadata de mídia {media_id}: "
                    f"{resp_meta.status_code} — {resp_meta.text[:300]}"
                )
                return None

            meta_info = resp_meta.json()
            url_download = meta_info.get("url")
            mime_type = meta_info.get("mime_type", "application/octet-stream")
            tamanho = int(meta_info.get("file_size", 0))

            if not url_download:
                logger.error(f"Metadata de mídia {media_id} sem URL de download.")
                return None

            if tamanho > MAX_MEDIA_BYTES:
                logger.error(
                    f"Mídia {media_id} muito grande: {tamanho} bytes "
                    f"(limite {MAX_MEDIA_BYTES}). Abortando download."
                )
                return None

            # Passo 2: baixar bytes
            resp_arquivo = await client.get(url_download, headers=headers)

            if resp_arquivo.status_code != 200:
                logger.error(
                    f"Erro ao baixar mídia {media_id}: {resp_arquivo.status_code}"
                )
                return None

            bytes_arquivo = resp_arquivo.content
            logger.info(
                f"📥 Mídia baixada: {media_id} "
                f"({len(bytes_arquivo)} bytes, {mime_type})"
            )
            return bytes_arquivo, mime_type

    except httpx.TimeoutException:
        logger.error(f"⏱️  Timeout ao baixar mídia {media_id}")
        return None

    except Exception as e:
        logger.error(f"Erro inesperado ao baixar mídia {media_id}: {e}", exc_info=True)
        return None
