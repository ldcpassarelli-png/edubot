"""
EduBot — Classificador de mensagens (Camada 2).

Lê uma mensagem de ENTRADA já gravada e a transforma em zero, uma ou várias
linhas na tabela `duvida`, cada uma categorizada e ancorada numa turma.

Roda como BackgroundTask do FastAPI, DEPOIS da resposta ao aluno (a resposta é
isco e responde rápido sempre). Abre a PRÓPRIA sessão de banco — a sessão do
request já fechou quando o task roda.

Escopo CC #4: só classifica e grava dúvida. NÃO agrega, NÃO gera relatório,
NÃO popula embedding, NÃO calibra prompt por matéria (fast-follow pós-CC #7).
"""

import json
import logging
import uuid

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import async_session
from app.models.database import Matricula, ConsentimentoCamada2, Duvida

logger = logging.getLogger("edubot.classificador")

CATEGORIAS_VALIDAS = {"academica", "organizacional", "emocional", "social"}
# Categorias detectadas mas NÃO persistidas como `duvida` no MVP:
# - "social": ruído (saudação, agradecimento) — nunca foi dúvida.
# - "emocional": sinalização sensível, tratamento de agregação por evento temporal
#   (não por tópico) + risco de exposição individual — adiada até ter desenho próprio
#   (ver Decisão 3, Seção 4.5). Reversível: a mensagem crua fica em `mensagem`.
CATEGORIAS_NAO_PERSISTIDAS = {"social", "emocional"}


# ============================================================
# Prompt do sistema — classificação em 4 categorias
# ============================================================

SYSTEM_PROMPT = """Você classifica mensagens de alunos universitários enviadas por WhatsApp a um assistente acadêmico.

Uma mensagem pode conter zero, uma ou várias dúvidas/intenções distintas. Identifique cada uma.

Retorne APENAS um JSON válido, sem markdown, sem backticks, sem explicação alguma.

Estrutura exata do JSON:
{"duvidas": [{"categoria": "<codigo>", "texto_extraido": "<dúvida curta e clara>"}]}

Use EXATAMENTE um destes códigos de categoria por item:
- "academica": dúvida sobre conteúdo da matéria (um conceito, um exercício, uma teoria, "como faz", "o que é").
- "organizacional": logística do curso (data de prova, prazo de entrega, formato, sala, peso de nota).
- "emocional": sinalização de ansiedade, desânimo, sobrecarga ou estresse, SEM uma pergunta concreta.
- "social": ruído social sem dúvida (agradecimento, saudação, "valeu", "obrigado", "ok", "blz").

REGRAS OBRIGATÓRIAS:
1. Se houver várias dúvidas distintas na mesma mensagem, crie um item para CADA uma.
2. "texto_extraido" é uma versão curta e clara da dúvida, na mesma língua da mensagem.
3. Se a mensagem for só ruído social, retorne um único item com categoria "social".
4. Se não houver nada classificável, retorne {"duvidas": []}.
5. Retorne SOMENTE o JSON. Nenhum texto antes ou depois."""


# ============================================================
# Modelos de saída do classificador
# ============================================================

class DuvidaClassificada(BaseModel):
    categoria: str
    texto_extraido: str


class RespostaClassificador(BaseModel):
    duvidas: list[DuvidaClassificada] = []


# ============================================================
# Engine — chamada ao Haiku (espelha ParserEngine)
# ============================================================

class ClassificadorEngine:
    """Classifica uma mensagem de aluno em dúvidas usando Claude Haiku."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()

    async def classificar(self, texto: str) -> list[DuvidaClassificada] | None:
        """
        Retorna a lista de dúvidas classificadas (categorias válidas).

        - [] quando não há nada classificável.
        - None em FALHA GRACIOSA (erro HTTP, JSON malformado, validação): o
          chamador não grava dúvida nenhuma e a `mensagem` crua fica intacta.
        """
        if not texto or not texto.strip():
            return []

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
                    "max_tokens": 1024,
                    "system": SYSTEM_PROMPT,
                    "messages": [
                        {
                            "role": "user",
                            "content": f"Classifique esta mensagem de aluno:\n\n{texto}",
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

            parsed = RespostaClassificador(**json.loads(json_limpo))

        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.error(f"Classificador falhou — captura sem classificar: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado no classificador: {e}", exc_info=True)
            return None

        # Descarta itens com categoria fora do enum (defesa contra resposta do modelo)
        validas: list[DuvidaClassificada] = []
        for item in parsed.duvidas:
            cat = item.categoria.strip().lower()
            if cat not in CATEGORIAS_VALIDAS:
                logger.warning(f"Categoria desconhecida '{item.categoria}' — item descartado.")
                continue
            item.categoria = cat
            validas.append(item)
        return validas


# ============================================================
# Resolução de turma e consentimento (na aplicação)
# ============================================================

async def _resolver_turma(db: AsyncSession, aluno_telefone: str) -> uuid.UUID | None:
    """
    Resolve a turma do aluno via `matricula` ativa (ponte por telefone-string).

    0 matrículas → None (estado esperado HOJE; ninguém tem matrícula até a CC #7).
    2+ matrículas → None (guarda defensiva: gravar na turma errada corromperia o
    relatório de um professor; adiar preserva o dado bruto, reclassificável).
    """
    result = await db.execute(
        select(Matricula.turma_id).where(
            Matricula.aluno_telefone == aluno_telefone,
            Matricula.ativo.is_(True),
        )
    )
    turmas = result.scalars().all()

    if len(turmas) == 0:
        logger.info(f"Sem matrícula ativa para {aluno_telefone} — captura sem classificar.")
        return None
    if len(turmas) > 1:
        logger.warning(
            f"{len(turmas)} matrículas ativas para {aluno_telefone} — guarda defensiva, não classifica."
        )
        return None
    return turmas[0]


async def _resolver_consentimento(db: AsyncSession, aluno_telefone: str) -> bool:
    """
    Snapshot do consentimento no momento da criação da dúvida.

    Última linha por `data_consentimento`. True só se consentiu e não revogou.
    Ausência, false explícito e revogado → todos False (mesmo comportamento).
    """
    result = await db.execute(
        select(ConsentimentoCamada2)
        .where(ConsentimentoCamada2.aluno_telefone == aluno_telefone)
        .order_by(ConsentimentoCamada2.data_consentimento.desc())
        .limit(1)
    )
    linha = result.scalar_one_or_none()
    return bool(linha and linha.consentiu and linha.data_revogacao is None)


# ============================================================
# Orquestração — roda no BackgroundTask
# ============================================================

async def processar_classificacao(
    mensagem_id: uuid.UUID,
    aluno_telefone: str,
    texto: str,
    engine: ClassificadorEngine,
) -> None:
    """
    Classifica uma mensagem de entrada e grava as dúvidas resultantes.

    Abre a PRÓPRIA sessão (a do request já fechou). Nunca levanta: em qualquer
    erro, loga e dá rollback — a `mensagem` crua já está commitada pelo request.
    """
    async with async_session() as db:
        try:
            turma_id = await _resolver_turma(db, aluno_telefone)
            if turma_id is None:
                return

            duvidas = await engine.classificar(texto)
            if not duvidas:
                # None (falha graciosa) ou [] (nada a gravar). mensagem crua intacta.
                return

            consentiu = await _resolver_consentimento(db, aluno_telefone)

            criadas = 0
            for item in duvidas:
                if item.categoria in CATEGORIAS_NAO_PERSISTIDAS:
                    continue  # social e emocional: detectadas, não persistidas no MVP
                db.add(
                    Duvida(
                        mensagem_id=mensagem_id,
                        turma_id=turma_id,
                        categoria=item.categoria,
                        texto_extraido=item.texto_extraido,
                        consentimento_camada2=consentiu,
                        aluno_telefone=aluno_telefone,
                    )
                )
                criadas += 1

            await db.commit()
            logger.info(
                f"Classificador: {criadas} dúvida(s) gravada(s) para {aluno_telefone} "
                f"(turma {turma_id})."
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Erro ao classificar mensagem {mensagem_id}: {e}", exc_info=True)
