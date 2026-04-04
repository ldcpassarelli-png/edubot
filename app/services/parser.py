"""
EduBot — Parser Engine
Extrai dados estruturados de planos de aula usando Claude Haiku 4.5.
Suporta: texto puro, PDF (via extração de texto), imagem (via OCR).
"""

import json
import base64
import logging
from datetime import datetime
from typing import Optional
from pydantic import BaseModel, Field
import httpx

logger = logging.getLogger("edubot.parser")

# ============================================================
# Modelos de dados
# ============================================================

class EventoExtraido(BaseModel):
    """Um evento acadêmico extraído do plano de aula."""
    data: str = Field(description="Data no formato YYYY-MM-DD")
    tipo: str = Field(description="prova|quiz|case|trabalho|seminario|aula|leitura")
    titulo: str = Field(description="Título curto do evento")
    descricao: Optional[str] = Field(default=None, description="Descrição completa")
    material_leitura: Optional[str] = Field(default=None, description="Material para ler")
    peso_nota: Optional[str] = Field(default=None, description="Peso na nota")
    urgencia: str = Field(default="baixa", description="alta|media|baixa")


class PlanoExtraido(BaseModel):
    """Resultado completo da extração de um plano de aula."""
    materia: str
    professor: Optional[str] = None
    semestre: Optional[str] = None
    eventos: list[EventoExtraido] = []
    raw_response: Optional[str] = Field(default=None, exclude=True)


class ResultadoParsing(BaseModel):
    """Resultado do parsing com metadados."""
    sucesso: bool
    dados: Optional[PlanoExtraido] = None
    erro: Optional[str] = None
    tempo_processamento_ms: int = 0
    tokens_usados: int = 0


# ============================================================
# Prompt do sistema para extração
# ============================================================

SYSTEM_PROMPT = """Você é um parser de planos de aula acadêmicos brasileiros. Sua tarefa é extrair TODOS os eventos do plano fornecido.

Retorne APENAS um JSON válido, sem markdown, sem backticks, sem explicação alguma.

Estrutura exata do JSON:
{
  "materia": "nome da matéria",
  "professor": "nome do professor ou null",
  "semestre": "período ou null",
  "eventos": [
    {
      "data": "YYYY-MM-DD",
      "tipo": "prova|quiz|case|trabalho|seminario|aula|leitura",
      "titulo": "título curto e descritivo",
      "descricao": "descrição completa da atividade",
      "material_leitura": "material para ler, ou null",
      "peso_nota": "peso na nota se mencionado, ou null",
      "urgencia": "alta|media|baixa"
    }
  ]
}

REGRAS OBRIGATÓRIAS:
1. Se a data não tiver ano, assuma o ano corrente.
2. Classificação de urgência:
   - alta: provas, entregas de trabalho, apresentações
   - media: quizzes, cases, leituras obrigatórias
   - baixa: aulas regulares, leituras opcionais
3. Extraia TODOS os eventos, incluindo aulas regulares.
4. Se houver múltiplos eventos na mesma data (ex: aula + entrega), crie entradas SEPARADAS.
5. Datas devem estar no formato ISO YYYY-MM-DD.
6. Se um quiz for mencionado como "possível" ou "surpresa", inclua com tipo "quiz" e note na descrição.
7. Retorne SOMENTE o JSON. Nenhum texto antes ou depois."""


# ============================================================
# Classe principal do parser
# ============================================================

class ParserEngine:
    """Motor de parsing de planos de aula usando Claude API."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        """
        Args:
            api_key: Chave da API Anthropic
            model: Modelo a usar (Haiku pra velocidade, Sonnet pra precisão)
        """
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.client = self.client = httpx.AsyncClient(timeout=120.0)

    async def close(self):
        """Fecha o cliente HTTP."""
        await self.client.aclose()

    # ----------------------------------------------------------
    # Método principal: parsear texto
    # ----------------------------------------------------------
    async def parsear_texto(self, texto: str) -> ResultadoParsing:
        """
        Extrai eventos de um plano de aula em texto.

        Args:
            texto: Conteúdo do plano de aula (texto puro)

        Returns:
            ResultadoParsing com dados extraídos ou erro
        """
        if not texto or not texto.strip():
            return ResultadoParsing(
                sucesso=False,
                erro="Texto vazio. Envie o conteúdo do plano de aula."
            )

        inicio = datetime.now()

        try:
            response = await self.client.post(
                self.api_url,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model,
                    "max_tokens": 4000,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Extraia todos os eventos deste plano de aula:\n\n{texto}"
                        }
                    ],
                },
            )

            response.raise_for_status()
            data = response.json()

            # Extrair texto da resposta
            texto_resposta = ""
            for bloco in data.get("content", []):
                if bloco.get("type") == "text":
                    texto_resposta += bloco["text"]

            # Limpar e parsear JSON
            json_limpo = texto_resposta.strip()
            json_limpo = json_limpo.removeprefix("```json").removeprefix("```")
            json_limpo = json_limpo.removesuffix("```").strip()

            dados_parseados = json.loads(json_limpo)
            plano = PlanoExtraido(**dados_parseados, raw_response=texto_resposta)

            # Calcular tempo
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)

            # Tokens usados
            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            logger.info(
                f"Parser OK: {plano.materia} — "
                f"{len(plano.eventos)} eventos em {tempo_ms}ms "
                f"({tokens} tokens)"
            )

            return ResultadoParsing(
                sucesso=True,
                dados=plano,
                tempo_processamento_ms=tempo_ms,
                tokens_usados=tokens,
            )

        except httpx.HTTPStatusError as e:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            logger.error(f"Erro HTTP na API: {e.response.status_code}")
            return ResultadoParsing(
                sucesso=False,
                erro=f"Erro na API Claude: {e.response.status_code}",
                tempo_processamento_ms=tempo_ms,
            )

        except json.JSONDecodeError as e:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            logger.error(f"Erro ao parsear JSON da resposta: {e}")
            return ResultadoParsing(
                sucesso=False,
                erro="A IA retornou dados em formato inválido. Tente novamente.",
                tempo_processamento_ms=tempo_ms,
            )

        except Exception as e:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            logger.error(f"Erro inesperado no parser: {e}")
            return ResultadoParsing(
                sucesso=False,
                erro=f"Erro inesperado: {str(e)}",
                tempo_processamento_ms=tempo_ms,
            )

    # ----------------------------------------------------------
    # Parsear PDF (extrai texto primeiro)
    # ----------------------------------------------------------
    async def parsear_pdf(self, pdf_bytes: bytes) -> ResultadoParsing:
        """
        Extrai eventos de um plano de aula em PDF.
        Envia o PDF direto pra Claude como documento.

        Args:
            pdf_bytes: Bytes do arquivo PDF

        Returns:
            ResultadoParsing com dados extraídos ou erro
        """
        if not pdf_bytes:
            return ResultadoParsing(
                sucesso=False,
                erro="PDF vazio."
            )

        inicio = datetime.now()

        try:
            # Codificar PDF em base64
            pdf_b64 = base64.b64encode(pdf_bytes).decode("utf-8")

            response = await self.client.post(
                self.api_url,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model,
                    "max_tokens": 8000,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "document",
                                    "source": {
                                        "type": "base64",
                                        "media_type": "application/pdf",
                                        "data": pdf_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": "Extraia todos os eventos deste plano de aula.",
                                },
                            ],
                        }
                    ],
                },
            )

            response.raise_for_status()
            data = response.json()

            texto_resposta = ""
            for bloco in data.get("content", []):
                if bloco.get("type") == "text":
                    texto_resposta += bloco["text"]

            json_limpo = texto_resposta.strip()
            json_limpo = json_limpo.removeprefix("```json").removeprefix("```")
            json_limpo = json_limpo.removesuffix("```").strip()

            # Se o JSON veio cortado, tenta consertar
            try:
                dados_parseados = json.loads(json_limpo)
            except json.JSONDecodeError:
                # Tenta fechar o JSON truncado
                if '"eventos": [' in json_limpo:
                    # Remove último evento incompleto e fecha o array/objeto
                    ultimo_fecha = json_limpo.rfind("}")
                    if ultimo_fecha > 0:
                        json_limpo = json_limpo[:ultimo_fecha + 1] + "]}"
                        dados_parseados = json.loads(json_limpo)
                    else:
                        raise
                else:
                    raise
            plano = PlanoExtraido(**dados_parseados, raw_response=texto_resposta)

            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            logger.info(
                f"Parser PDF OK: {plano.materia} — "
                f"{len(plano.eventos)} eventos em {tempo_ms}ms"
            )

            return ResultadoParsing(
                sucesso=True,
                dados=plano,
                tempo_processamento_ms=tempo_ms,
                tokens_usados=tokens,
            )

        except Exception as e:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            logger.error(f"Erro no parser PDF: {e}")
            return ResultadoParsing(
                sucesso=False,
                erro=f"Erro ao processar PDF: {str(e)}",
                tempo_processamento_ms=tempo_ms,
            )

    # ----------------------------------------------------------
    # Parsear imagem (foto do plano de aula)
    # ----------------------------------------------------------
    async def parsear_imagem(self, img_bytes: bytes, media_type: str = "image/jpeg") -> ResultadoParsing:
        """
        Extrai eventos de uma foto do plano de aula.
        Claude faz OCR + extração em um único passo.

        Args:
            img_bytes: Bytes da imagem
            media_type: Tipo MIME (image/jpeg, image/png, image/webp)

        Returns:
            ResultadoParsing com dados extraídos ou erro
        """
        if not img_bytes:
            return ResultadoParsing(
                sucesso=False,
                erro="Imagem vazia."
            )

        inicio = datetime.now()

        try:
            img_b64 = base64.b64encode(img_bytes).decode("utf-8")

            response = await self.client.post(
                self.api_url,
                headers={
                    "Content-Type": "application/json",
                    "x-api-key": self.api_key,
                    "anthropic-version": "2023-06-01",
                },
                json={
                    "model": self.model,
                    "max_tokens": 4000,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": [
                                {
                                    "type": "image",
                                    "source": {
                                        "type": "base64",
                                        "media_type": media_type,
                                        "data": img_b64,
                                    },
                                },
                                {
                                    "type": "text",
                                    "text": "Esta é uma foto de um plano de aula. Extraia todos os eventos.",
                                },
                            ],
                        }
                    ],
                },
            )

            response.raise_for_status()
            data = response.json()

            texto_resposta = ""
            for bloco in data.get("content", []):
                if bloco.get("type") == "text":
                    texto_resposta += bloco["text"]

            json_limpo = texto_resposta.strip()
            json_limpo = json_limpo.removeprefix("```json").removeprefix("```")
            json_limpo = json_limpo.removesuffix("```").strip()

            dados_parseados = json.loads(json_limpo)
            plano = PlanoExtraido(**dados_parseados, raw_response=texto_resposta)

            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            usage = data.get("usage", {})
            tokens = usage.get("input_tokens", 0) + usage.get("output_tokens", 0)

            logger.info(
                f"Parser IMG OK: {plano.materia} — "
                f"{len(plano.eventos)} eventos em {tempo_ms}ms"
            )

            return ResultadoParsing(
                sucesso=True,
                dados=plano,
                tempo_processamento_ms=tempo_ms,
                tokens_usados=tokens,
            )

        except Exception as e:
            tempo_ms = int((datetime.now() - inicio).total_seconds() * 1000)
            logger.error(f"Erro no parser imagem: {e}")
            return ResultadoParsing(
                sucesso=False,
                erro=f"Erro ao processar imagem: {str(e)}",
                tempo_processamento_ms=tempo_ms,
            )

    # ----------------------------------------------------------
    # Gerar resumo de confirmação (para o bot confirmar com o aluno)
    # ----------------------------------------------------------
    def gerar_resumo_confirmacao(self, plano: PlanoExtraido) -> str:
        """
        Gera mensagem de confirmação formatada para WhatsApp.

        Args:
            plano: Dados extraídos do plano

        Returns:
            Mensagem formatada para envio
        """
        # Contadores por tipo
        contagem = {}
        for ev in plano.eventos:
            contagem[ev.tipo] = contagem.get(ev.tipo, 0) + 1

        # Ícones por tipo
        icones = {
            "prova": "🔴",
            "quiz": "⚡",
            "case": "📖",
            "trabalho": "📝",
            "seminario": "🎤",
            "aula": "📚",
            "leitura": "📄",
        }

        # Montar mensagem
        linhas = [f"Achei isso no seu plano de *{plano.materia}*:\n"]

        for tipo, qtd in sorted(contagem.items(), key=lambda x: x[1], reverse=True):
            icone = icones.get(tipo, "📌")
            nome = tipo.capitalize()
            if qtd > 1:
                nome += "s" if tipo != "quiz" else "zes"
            linhas.append(f"{icone} {qtd} {nome}")

        # Destacar eventos de alta urgência
        eventos_importantes = [e for e in plano.eventos if e.urgencia == "alta"]
        if eventos_importantes:
            linhas.append("\n⚠️ *Atenção especial:*")
            for ev in eventos_importantes:
                info = f"• {ev.titulo} — {ev.data}"
                if ev.peso_nota:
                    info += f" ({ev.peso_nota})"
                linhas.append(info)

        linhas.append("\nTá tudo certo? (sim/não)")

        return "\n".join(linhas)
