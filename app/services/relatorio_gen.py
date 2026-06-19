"""
EduBot — Enriquecimento do relatório semanal (Camada 2, CC #6).

Roda PÓS-agregação (depois que a CC #5 casou conceito_id e montou o JSON
estatístico). Faz duas coisas, nesta ordem:

  1. SUBCONCEITO (Haiku): para cada Conceito com volume >= 2, lê as dúvidas
     brutas daquele conceito e nomeia 2-4 subtemas recorrentes. O subconceito é
     o que faz o professor agir — o Conceito top-down do plano é ruído pra ele.
     Enxerta {nome, alunos_count, reincidentes_count} no JSONB, um nível abaixo
     do conceito. NULL honesto: sem subtema claro, lista vazia.

  2. PROSA (Sonnet): lê o conteúdo JÁ ENRIQUECIDO + taxonomia do plano +
     ponteiro de progresso + próximos marcos e escreve a "sugestão de ação" —
     ataca o PORQUÊ, tom de colega que conhece a turma. Grava em relatorio.prosa_acao.

Privacidade (LGPD): o texto bruto das dúvidas vai ao Haiku de forma TRANSITÓRIA
(igual o classificador da CC #4 e o matching da CC #5 já fazem) e NUNCA persiste.
Só {nome, alunos_count, reincidentes_count} entra no JSONB — estatística pura.
O prompt NÃO recebe material proprietário, só as dúvidas dos alunos.

Falha graciosa em tudo: erro de HTTP/JSON/validação loga e devolve None/[] — o
relatório continua válido, a página só não mostra aquele enriquecimento.
"""

import json
import logging
import os
import uuid
from collections import Counter
from datetime import date, datetime

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.database import (
    Aula, Duvida, MateriaCamada2, Professor, ProgressoTurma, Turma,
)

logger = logging.getLogger("edubot.relatorio_gen")

# Strings de modelo em constante única (config), não espalhadas. Troca fácil.
SUBCONCEITO_MODEL = os.getenv("SUBCONCEITO_MODEL", "claude-haiku-4-5-20251001")
PROSA_MODEL = os.getenv("PROSA_MODEL", "claude-sonnet-4-6")

# Volume mínimo de dúvidas num conceito pra valer a chamada de subconceito.
VOLUME_MINIMO_SUBCONCEITO = 2


# ============================================================
# Subconceito — prompt parametrizado por CATEGORIA de matéria
# ============================================================

_REGRAS_SUBCONCEITO = """Você recebe o nome de um CONCEITO de um plano de aula e uma lista numerada de dúvidas reais de alunos sobre esse conceito.

Sua tarefa: identificar de 1 a 4 SUBTEMAS recorrentes — o ponto específico dentro do conceito em que os alunos travam. O subtema é mais fino que o conceito: é o "porquê" concreto que se repete nas dúvidas.

Para cada subtema, liste os índices das dúvidas que pertencem a ele (uma dúvida pode entrar em no máximo um subtema; dúvidas que não formam um padrão claro ficam de fora).

Se NÃO houver um padrão claro de subtema (volume baixo, dúvidas dispersas), devolva lista vazia — é melhor não nomear do que inventar um subtema que não existe.

Retorne APENAS um JSON válido, sem markdown, sem backticks, sem explicação.

Estrutura exata:
{"subtemas": [{"nome": "<subtema curto e específico>", "duvida_idxs": [<int>, ...]}]}

Regras:
1. De 1 a 4 subtemas, ou 0 só se as dúvidas forem realmente dispersas (não force um segundo subtema onde só há um).
2. "nome" sai na LÍNGUA DO CONCEITO — uma frase curta, limpa e pedagógica que nomeia o ponto de travamento (ex.: "por que decompor risco sistemático e específico"). NÃO copie a escrita crua do aluno (abreviação, gíria, erro); reformule no vocabulário do plano de aula.
3. Use só os índices fornecidos. Cada índice em no máximo um subtema.
4. Retorne SOMENTE o JSON. Nenhum texto antes ou depois."""

# Cada categoria ganha uma linha de contexto de domínio no topo. Começa em
# 'financas' (categoria do seed); as demais herdam o mesmo corpo de regras.
_CONTEXTO_CATEGORIA = {
    "financas": "O domínio é finanças (teoria de carteiras, risco, retorno, modelos de precificação). Subtemas costumam ser confusões de mecânica vs. intuição, ou a fronteira entre dois conceitos próximos.",
    "administracao": "O domínio é administração e gestão. Subtemas costumam ser a aplicação prática de um framework ou a diferença entre conceitos que parecem sinônimos.",
    "marketing": "O domínio é marketing. Subtemas costumam ser quando/por que aplicar uma ferramenta, não o que ela é.",
    "gos": "O domínio é gestão de operações e suprimentos. Subtemas costumam ser cálculo vs. interpretação, ou trade-offs entre indicadores.",
    "econometria": "O domínio é econometria e estatística aplicada. Subtemas costumam ser pressupostos de um modelo ou leitura de um resultado.",
}
_CONTEXTO_PADRAO = "Subtemas costumam ser o ponto específico de mecânica ou de intuição em que os alunos travam dentro do conceito."


def _system_prompt_subconceito(categoria_materia: str | None) -> str:
    contexto = _CONTEXTO_CATEGORIA.get(
        (categoria_materia or "").strip().lower(), _CONTEXTO_PADRAO
    )
    return f"{contexto}\n\n{_REGRAS_SUBCONCEITO}"


class _Subtema(BaseModel):
    nome: str
    duvida_idxs: list[int] = []


class _RespostaSubconceito(BaseModel):
    subtemas: list[_Subtema] = []


class SubconceitoEngine:
    """Agrupa dúvidas de um conceito em subtemas via Claude Haiku."""

    def __init__(self, api_key: str, model: str = SUBCONCEITO_MODEL):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()

    async def agrupar(
        self,
        conceito_nome: str,
        duvidas: list[tuple[int, str]],   # (idx, texto_extraido)
        categoria_materia: str | None = None,
    ) -> list[_Subtema] | None:
        """
        Devolve a lista de subtemas (cada um com os índices das dúvidas).

        - [] quando não há padrão claro (NULL honesto).
        - None em FALHA GRACIOSA (HTTP/JSON/validação): o chamador não enxerta
          subconceito naquele conceito e segue em frente.
        """
        if not duvidas:
            return []

        idxs_validos = {i for i, _ in duvidas}
        lista_duvidas = "\n".join(f"[{i}] {t}" for i, t in duvidas)

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
                    "system": _system_prompt_subconceito(categoria_materia),
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"CONCEITO: {conceito_nome}\n\n"
                                f"DÚVIDAS DOS ALUNOS:\n{lista_duvidas}"
                            ),
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

            parsed = _RespostaSubconceito(**json.loads(json_limpo))

        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.error(f"Subconceito falhou para '{conceito_nome}' — fica no nível do conceito: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado no subconceito de '{conceito_nome}': {e}", exc_info=True)
            return None

        # Sanitiza: só índices conhecidos, cada um uma vez, subtema sem índice sai.
        vistos: set[int] = set()
        limpos: list[_Subtema] = []
        for s in parsed.subtemas:
            idxs = [i for i in s.duvida_idxs if i in idxs_validos and i not in vistos]
            vistos.update(idxs)
            if not idxs or not s.nome.strip():
                continue
            limpos.append(_Subtema(nome=s.nome.strip(), duvida_idxs=idxs))
        return limpos


# ============================================================
# Prosa — sugestão de ação (Sonnet)
# ============================================================

SYSTEM_PROMPT_PROSA = """Você é um colega experiente do professor de uma disciplina universitária. Acabou de olhar o padrão de dúvidas da turma na última semana e vai escrever para o professor uma SUGESTÃO DE AÇÃO curta.

Sua escrita ataca o PORQUÊ, não o O QUÊ. Não diga "revise o conceito X"; diga o que parece estar por trás das dúvidas — onde a turma entendeu a mecânica mas não a intuição, onde dois conceitos próximos estão se confundindo, o que vale retomar antes do próximo marco.

Tom: de colega que conhece a turma, direto e respeitoso. Nada de jargão de consultoria, nada de bullet points, nada de elogio vazio.

Regras:
1. Escreva de 2 a 4 parágrafos, em português brasileiro.
2. Baseie-se SOMENTE nos dados fornecidos (conceitos, subtemas, sinais de não-consolidação, progresso, próximos marcos). NÃO invente número, nome de aluno ou dúvida que não esteja ali.
3. Quando houver sinal de não-consolidação (alunos que voltaram ao mesmo subtema), trate isso como o ponto mais importante.
4. Se houver um próximo marco (prova, entrega), conecte a sugestão a ele.
5. Não cite nomes nem telefones de alunos — você só tem o padrão agregado da turma.
6. Retorne apenas a prosa. Sem título, sem assinatura, sem markdown."""


class ProsaEngine:
    """Gera a prosa de sugestão de ação via Claude Sonnet."""

    def __init__(self, api_key: str, model: str = PROSA_MODEL):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.client = httpx.AsyncClient(timeout=90.0)

    async def close(self):
        await self.client.aclose()

    async def gerar(self, brief: str) -> str | None:
        """Recebe o briefing textual já montado; devolve a prosa ou None."""
        if not brief or not brief.strip():
            return None
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
                    "system": SYSTEM_PROMPT_PROSA,
                    "messages": [{"role": "user", "content": brief}],
                },
            )
            response.raise_for_status()
            data = response.json()
            texto = ""
            for bloco in data.get("content", []):
                if bloco.get("type") == "text":
                    texto += bloco["text"]
            texto = texto.strip()
            return texto or None
        except (httpx.HTTPError, KeyError) as e:
            logger.error(f"Prosa falhou — relatório fica sem sugestão de ação: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado na prosa: {e}", exc_info=True)
            return None


# ============================================================
# Montagem do briefing da prosa (a partir do conteúdo JÁ enriquecido)
# ============================================================

def _montar_brief_prosa(
    materia_nome: str, turma_letra: str, semana_inicio: date, semana_fim: date,
    conteudo: dict, aula_atual: str | None, proximos_marcos: list[str],
) -> str:
    linhas: list[str] = []
    linhas.append(f"Disciplina: {materia_nome} — turma {turma_letra}")
    linhas.append(f"Semana de referência: {semana_inicio.isoformat()} a {semana_fim.isoformat()}")
    if aula_atual:
        linhas.append(f"A turma está atualmente na aula: {aula_atual}")
    if proximos_marcos:
        linhas.append("Próximos marcos: " + "; ".join(proximos_marcos))

    ac = conteudo.get("academica", {})
    totais = ac.get("totais", {})
    linhas.append(
        f"\nVolume da semana: {totais.get('duvidas', 0)} dúvidas acadêmicas de "
        f"{totais.get('alunos_distintos', 0)} alunos distintos."
    )

    linhas.append("\nOnde a turma travou (unidade > conceito > subtemas):")
    for u in ac.get("unidades", []):
        linhas.append(f"- Unidade: {u.get('unidade_nome')}")
        for c in u.get("conceitos", []):
            linhas.append(
                f"  - Conceito: {c.get('conceito_nome')} "
                f"({c.get('volume')} dúvidas, {c.get('alunos_distintos')} alunos)"
            )
            for s in c.get("subconceitos", []):
                reinc = s.get("reincidentes_count", 0)
                marca = f" — NÃO-CONSOLIDAÇÃO: {reinc} aluno(s) voltaram a esse ponto" if reinc else ""
                linhas.append(
                    f"    * Subtema: {s.get('nome')} "
                    f"({s.get('alunos_count')} alunos){marca}"
                )

    nc = ac.get("nao_classificadas", {}).get("volume", 0)
    if nc:
        linhas.append(f"\n{nc} dúvida(s) acadêmica(s) não casaram com nenhum conceito do plano.")

    org = conteudo.get("organizacional", {}).get("volume", 0)
    if org:
        linhas.append(f"{org} dúvida(s) organizacional(is) (logística: prazos, formato, prova).")

    return "\n".join(linhas)


# ============================================================
# Orquestração do enriquecimento
# ============================================================

async def _duvidas_brutas_do_conceito(
    db: AsyncSession, turma_id: uuid.UUID, conceito_id: uuid.UUID,
    inicio_tz: datetime, fim_tz: datetime,
) -> list[Duvida]:
    """Dúvidas academicas consentidas daquele conceito na janela (texto bruto)."""
    return list((await db.execute(
        select(Duvida).where(
            Duvida.turma_id == turma_id,
            Duvida.categoria == "academica",
            Duvida.consentimento_camada2.is_(True),
            Duvida.conceito_id == conceito_id,
            Duvida.created_at >= inicio_tz,
            Duvida.created_at < fim_tz,
        )
    )).scalars().all())


async def enriquecer(
    db: AsyncSession,
    turma: Turma,
    conteudo: dict,
    aulas: list[Aula],
    *,
    subc_engine: SubconceitoEngine | None,
    prosa_engine: ProsaEngine | None,
    inicio_tz: datetime,
    fim_tz: datetime,
    semana_inicio: date,
    semana_fim: date,
) -> str | None:
    """
    Enriquece `conteudo` IN PLACE com subconceitos e devolve a prosa (ou None).

    Ordem: subconceito primeiro (enxerta no JSONB), prosa depois (lê o JSONB já
    enriquecido). Cada engine None → pula aquela etapa, sem quebrar o relatório.
    """
    # Contexto da matéria (categoria para o prompt + nome para o briefing).
    materia = (await db.execute(
        select(MateriaCamada2).where(MateriaCamada2.id == turma.materia_camada2_id)
    )).scalar_one_or_none()
    materia_nome = materia.nome if materia else "Disciplina"
    categoria_materia = materia.categoria if materia else None

    # ---- Passo 1: subconceito por conceito-com-volume ----
    if subc_engine is not None:
        for u in conteudo.get("academica", {}).get("unidades", []):
            for c in u.get("conceitos", []):
                c.setdefault("subconceitos", [])
                if c.get("volume", 0) < VOLUME_MINIMO_SUBCONCEITO:
                    continue
                conceito_id = uuid.UUID(c["conceito_id"])
                duvidas = await _duvidas_brutas_do_conceito(
                    db, turma.id, conceito_id, inicio_tz, fim_tz
                )
                if len(duvidas) < VOLUME_MINIMO_SUBCONCEITO:
                    continue

                # Anonimização: índice → telefone, mas o telefone NUNCA vai ao LLM.
                tel_por_idx = {i: d.aluno_telefone for i, d in enumerate(duvidas)}
                entrada = [(i, d.texto_extraido) for i, d in enumerate(duvidas)]

                subtemas = await subc_engine.agrupar(
                    c["conceito_nome"], entrada, categoria_materia
                )
                if not subtemas:   # None (falha) ou [] (NULL honesto)
                    continue

                # Contagens calculadas em Python (mais honesto que pedir ao LLM).
                subc_json = []
                for s in subtemas:
                    tels = [tel_por_idx[i] for i in s.duvida_idxs]
                    contagem = Counter(tels)
                    subc_json.append({
                        "nome": s.nome,
                        "alunos_count": len(contagem),
                        "reincidentes_count": sum(1 for n in contagem.values() if n >= 2),
                    })
                c["subconceitos"] = subc_json

    # ---- Passo 2: prosa (lê o conteúdo já enriquecido) ----
    if prosa_engine is None:
        return None

    progresso = (await db.execute(
        select(ProgressoTurma).where(ProgressoTurma.turma_id == turma.id)
    )).scalar_one_or_none()
    aula_atual = None
    if progresso and progresso.aula_atual_id:
        aula_atual = next(
            (a.titulo for a in aulas if a.id == progresso.aula_atual_id), None
        )

    # Próximos marcos: aulas com data prevista DEPOIS da semana de referência
    # (nunca passado), em ordem; pega os 3 primeiros para não inundar o prompt.
    futuras = sorted(
        [a for a in aulas if a.data_prevista and a.data_prevista > semana_fim],
        key=lambda a: a.data_prevista,
    )
    proximos_marcos = [
        f"{a.titulo} ({a.data_prevista.isoformat()})"
        for a in futuras[:3] if a.titulo
    ]

    brief = _montar_brief_prosa(
        materia_nome, turma.letra, semana_inicio, semana_fim,
        conteudo, aula_atual, proximos_marcos,
    )
    return await prosa_engine.gerar(brief)
