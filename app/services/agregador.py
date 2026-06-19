"""
EduBot — Agregador semanal de dúvidas (Camada 2).

Primeiro elo onde "dado vira produto": junta as dúvidas soltas de uma turma numa
semana fechada e produz a ESTATÍSTICA AGREGADA que vira o relatório do professor.
A prosa de sugestão de ação é Sonnet (CC #6) — aqui só sai dado estruturado.

Faz duas coisas:
  1. Matching dúvida→conceito EM LOTE via Haiku (espelha o ClassificadorEngine).
     Só toca dúvida 'academica' com conceito_id IS NULL. Sem confiança → NULL.
     Chute é proibido: gravar conceito errado corromperia o relatório.
  2. Agrega (academica por unidade→conceito; organizacional em bloco separado) e
     grava em `relatorio` (upsert idempotente na UNIQUE turma_id+semana_inicio).

Privacidade (LGPD): o relatório é estatística PURA. Nenhuma mensagem crua de aluno
e nenhum telefone entram em `relatorio.conteudo` — só contagens.

Roda como script manual (app/scripts/agregar.py). Celery+Redis é a CC #8.
"""

import json
import logging
import uuid
from collections import Counter, defaultdict
from datetime import date, datetime, timedelta
from zoneinfo import ZoneInfo

import httpx
from pydantic import BaseModel, ValidationError
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import async_session
from app.models.database import (
    Aula, Conceito, Duvida, PlanoDeAula, Relatorio, Turma, UnidadeTematica,
)
from app.services.relatorio_gen import ProsaEngine, SubconceitoEngine, enriquecer

logger = logging.getLogger("edubot.agregador")

TZ = ZoneInfo("America/Sao_Paulo")
VERSAO_AGREGADOR = 1
EXPIRACAO_DIAS = 14


# ============================================================
# Prompt de matching — dúvida → conceito (em lote)
# ============================================================

SYSTEM_PROMPT_MATCHING = """Você associa dúvidas de alunos universitários a conceitos de um plano de aula.

Receberá uma lista numerada de dúvidas e uma lista de conceitos disponíveis (cada um com um código curto).

Para CADA dúvida, decida qual conceito melhor a representa. Se NENHUM conceito couber com confiança, devolva null para aquela dúvida — é melhor não associar do que associar errado.

Retorne APENAS um JSON válido, sem markdown, sem backticks, sem explicação.

Estrutura exata:
{"matches": [{"duvida_idx": <int>, "conceito_ref": "<codigo ou null>"}]}

Regras:
1. Inclua um item para CADA dúvida recebida.
2. conceito_ref = null quando nenhum conceito couber com confiança.
3. Use somente os códigos de conceito fornecidos.
4. Retorne SOMENTE o JSON. Nenhum texto antes ou depois."""


class _Match(BaseModel):
    duvida_idx: int
    conceito_ref: str | None = None


class _RespostaMatching(BaseModel):
    matches: list[_Match] = []


# ============================================================
# Engine — chamada ao Haiku (espelha ParserEngine/ClassificadorEngine)
# ============================================================

class AgregadorEngine:
    """Casa dúvidas a conceitos via Claude Haiku, em lote (1 call por turma)."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        self.api_url = "https://api.anthropic.com/v1/messages"
        self.client = httpx.AsyncClient(timeout=60.0)

    async def close(self):
        await self.client.aclose()

    async def mapear_conceitos(
        self,
        duvidas: list[tuple[int, str]],     # (idx, texto_extraido)
        conceitos: list[tuple[str, str]],   # (ref, nome)
    ) -> dict[int, str] | None:
        """
        Recebe dúvidas numeradas + conceitos com refs curtos; devolve {idx: ref}.

        Só inclui os índices casados COM CONFIANÇA. Índice ausente do dict = NULL
        (deliberado: não casou). Devolve None em FALHA GRACIOSA (HTTP, JSON
        malformado, validação) — o chamador deixa tudo NULL e não levanta.
        """
        if not duvidas or not conceitos:
            return {}

        lista_duvidas = "\n".join(f"[{i}] {t}" for i, t in duvidas)
        lista_conceitos = "\n".join(f"{ref}: {nome}" for ref, nome in conceitos)
        refs_validos = {ref for ref, _ in conceitos}

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
                    "system": SYSTEM_PROMPT_MATCHING,
                    "messages": [
                        {
                            "role": "user",
                            "content": (
                                f"CONCEITOS DISPONÍVEIS:\n{lista_conceitos}\n\n"
                                f"DÚVIDAS:\n{lista_duvidas}"
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

            parsed = _RespostaMatching(**json.loads(json_limpo))

        except (httpx.HTTPError, json.JSONDecodeError, ValidationError, KeyError) as e:
            logger.error(f"Matching falhou — todas as dúvidas ficam sem conceito: {e}")
            return None
        except Exception as e:
            logger.error(f"Erro inesperado no matching: {e}", exc_info=True)
            return None

        resultado: dict[int, str] = {}
        for m in parsed.matches:
            if not m.conceito_ref:
                continue
            ref = m.conceito_ref.strip()
            if ref.lower() in {"null", "none", ""}:
                continue
            if ref not in refs_validos:
                logger.warning(
                    f"conceito_ref desconhecido '{ref}' (idx {m.duvida_idx}) — ignorado, fica NULL."
                )
                continue
            resultado[m.duvida_idx] = ref
        return resultado


# ============================================================
# Janela da semana (domingo anterior → sábado, fuso SP)
# ============================================================

def calcular_janela(data_ref: date) -> tuple[date, date]:
    """
    Janela = semana FECHADA anterior ao domingo de referência.

    Acha o domingo da semana de `data_ref`; a janela coberta vai de domingo−7
    (domingo) até domingo−1 (sábado). Um relatório gerado no domingo cobre a
    semana que terminou no sábado anterior.
    """
    dias_desde_domingo = (data_ref.weekday() + 1) % 7  # weekday: seg=0..dom=6
    domingo_ref = data_ref - timedelta(days=dias_desde_domingo)
    semana_inicio = domingo_ref - timedelta(days=7)   # domingo anterior
    semana_fim = domingo_ref - timedelta(days=1)      # sábado
    return semana_inicio, semana_fim


def _limites_tz(semana_inicio: date, semana_fim: date) -> tuple[datetime, datetime]:
    """Limites half-open [domingo 00:00, próximo domingo 00:00) no fuso SP."""
    inicio = datetime(semana_inicio.year, semana_inicio.month, semana_inicio.day, tzinfo=TZ)
    fim_exclusivo = (
        datetime(semana_fim.year, semana_fim.month, semana_fim.day, tzinfo=TZ)
        + timedelta(days=1)
    )
    return inicio, fim_exclusivo


def _data_local(dt: datetime) -> date:
    """Converte um timestamp aware para a data-calendário no fuso SP."""
    return dt.astimezone(TZ).date()


def _inferir_aula(data_duvida: date, aulas: list[Aula]) -> uuid.UUID | None:
    """Aula com data_prevista mais recente <= data da dúvida. Senão NULL (D4)."""
    candidatas = [a for a in aulas if a.data_prevista is not None and a.data_prevista <= data_duvida]
    if not candidatas:
        return None
    return max(candidatas, key=lambda a: a.data_prevista).id


# ============================================================
# Carga de taxonomia da turma
# ============================================================

async def _carregar_taxonomia(db: AsyncSession, turma: Turma):
    """Plano (materia+semestre da turma) → unidades, conceitos, aulas."""
    plano = (await db.execute(
        select(PlanoDeAula).where(
            PlanoDeAula.materia_camada2_id == turma.materia_camada2_id,
            PlanoDeAula.semestre == turma.semestre,
        )
    )).scalar_one_or_none()
    if plano is None:
        return None, [], [], []

    unidades = (await db.execute(
        select(UnidadeTematica)
        .where(UnidadeTematica.plano_de_aula_id == plano.id)
        .order_by(UnidadeTematica.ordem)
    )).scalars().all()

    conceitos = []
    if unidades:
        conceitos = (await db.execute(
            select(Conceito)
            .where(Conceito.unidade_tematica_id.in_([u.id for u in unidades]))
            .order_by(Conceito.ordem)
        )).scalars().all()

    aulas = (await db.execute(
        select(Aula).where(Aula.plano_de_aula_id == plano.id)
    )).scalars().all()

    return plano, list(unidades), list(conceitos), list(aulas)


# ============================================================
# Passe 1 — matching em lote (UPDATE em duvida.conceito_id/aula_id)
# ============================================================

async def _rodar_matching(
    db: AsyncSession, engine: AgregadorEngine, turma_id: uuid.UUID,
    inicio_tz: datetime, fim_tz: datetime,
    conceitos: list[Conceito], aulas: list[Aula],
) -> int:
    """Casa academicas consentidas e ainda NULL. Re-run estável (só toca NULL, D3)."""
    duvidas = (await db.execute(
        select(Duvida).where(
            Duvida.turma_id == turma_id,
            Duvida.categoria == "academica",
            Duvida.consentimento_camada2.is_(True),
            Duvida.conceito_id.is_(None),
            Duvida.created_at >= inicio_tz,
            Duvida.created_at < fim_tz,
        )
    )).scalars().all()

    if not duvidas:
        return 0
    if not conceitos:
        logger.info("Turma sem taxonomia — nada a casar, dúvidas ficam NULL.")
        return 0

    ref_por_conceito = {f"c{i + 1}": c for i, c in enumerate(conceitos)}
    id_por_ref = {ref: c.id for ref, c in ref_por_conceito.items()}
    lista_conceitos = [(ref, c.nome) for ref, c in ref_por_conceito.items()]
    lista_duvidas = [(i, d.texto_extraido) for i, d in enumerate(duvidas)]

    mapping = await engine.mapear_conceitos(lista_duvidas, lista_conceitos)
    if mapping is None:
        logger.warning("Matching devolveu None (falha graciosa) — dúvidas permanecem NULL.")
        return 0

    casadas = 0
    for i, d in enumerate(duvidas):
        ref = mapping.get(i)
        if ref is None:
            continue  # não casou com confiança → fica NULL
        d.conceito_id = id_por_ref[ref]
        d.aula_id = _inferir_aula(_data_local(d.created_at), aulas)
        casadas += 1

    await db.commit()
    return casadas


# ============================================================
# Passe 2 — agregação (monta o JSON estatístico)
# ============================================================

async def _montar_conteudo(
    db: AsyncSession, turma_id: uuid.UUID, inicio_tz: datetime, fim_tz: datetime,
    unidades: list[UnidadeTematica], conceitos: list[Conceito],
    semana_inicio: date, semana_fim: date,
) -> dict:
    """Só dúvidas com consentimento=true (snapshot na própria linha, D1)."""
    duvidas = (await db.execute(
        select(Duvida).where(
            Duvida.turma_id == turma_id,
            Duvida.consentimento_camada2.is_(True),
            Duvida.created_at >= inicio_tz,
            Duvida.created_at < fim_tz,
        )
    )).scalars().all()

    academicas = [d for d in duvidas if d.categoria == "academica"]
    organizacionais = [d for d in duvidas if d.categoria == "organizacional"]

    conceitos_validos = {c.id for c in conceitos}
    conceitos_por_unidade: dict[uuid.UUID, list[Conceito]] = defaultdict(list)
    for c in conceitos:
        conceitos_por_unidade[c.unidade_tematica_id].append(c)

    por_conceito: dict[uuid.UUID, list[Duvida]] = defaultdict(list)
    nao_classificadas = 0
    for d in academicas:
        if d.conceito_id is not None and d.conceito_id in conceitos_validos:
            por_conceito[d.conceito_id].append(d)
        else:
            nao_classificadas += 1

    unidades_json = []
    conceitos_com_duvida = 0
    for u in unidades:
        conceitos_json = []
        for c in conceitos_por_unidade.get(u.id, []):
            ds = por_conceito.get(c.id, [])
            if not ds:
                continue
            conceitos_com_duvida += 1
            telefones = [d.aluno_telefone for d in ds]
            recorrentes = sum(1 for n in Counter(telefones).values() if n >= 2)
            dist = Counter(_data_local(d.created_at).isoformat() for d in ds)
            conceitos_json.append({
                "conceito_id": str(c.id),
                "conceito_nome": c.nome,
                "volume": len(ds),
                "alunos_distintos": len(set(telefones)),
                "alunos_recorrentes": recorrentes,
                "distribuicao_temporal": dict(sorted(dist.items())),
            })
        if conceitos_json:
            unidades_json.append({
                "unidade_id": str(u.id),
                "unidade_nome": u.nome,
                "ordem": u.ordem,
                "conceitos": conceitos_json,
            })

    org_dist = Counter(_data_local(d.created_at).isoformat() for d in organizacionais)

    return {
        "meta": {
            "versao_agregador": VERSAO_AGREGADOR,
            "gerado_em": datetime.now(TZ).isoformat(),
            "semana_inicio": semana_inicio.isoformat(),
            "semana_fim": semana_fim.isoformat(),
        },
        "academica": {
            "totais": {
                "duvidas": len(academicas),
                "alunos_distintos": len({d.aluno_telefone for d in academicas}),
                "conceitos_com_duvida": conceitos_com_duvida,
            },
            "unidades": unidades_json,
            "nao_classificadas": {"volume": nao_classificadas},
        },
        "organizacional": {
            "volume": len(organizacionais),
            "distribuicao_temporal": dict(sorted(org_dist.items())),
        },
    }


# ============================================================
# Persistência — upsert idempotente em relatorio
# ============================================================

async def _upsert_relatorio(
    db: AsyncSession, turma_id: uuid.UUID,
    semana_inicio: date, semana_fim: date, conteudo: dict, prosa: str | None,
) -> None:
    """
    UNIQUE(turma_id, semana_inicio) garante idempotência. Re-run ATUALIZA a linha;
    token_acesso e created_at NÃO são tocados (o token pode já ter ido ao professor).
    """
    agora = datetime.now(TZ)
    stmt = pg_insert(Relatorio).values(
        turma_id=turma_id,
        semana_inicio=semana_inicio,
        semana_fim=semana_fim,
        token_acesso=uuid.uuid4(),
        expira_em=agora + timedelta(days=EXPIRACAO_DIAS),
        conteudo=conteudo,
        prosa_acao=prosa,
        gerado_em=agora,
    ).on_conflict_do_update(
        index_elements=["turma_id", "semana_inicio"],
        set_={
            "semana_fim": semana_fim,
            "conteudo": conteudo,
            "prosa_acao": prosa,
            "gerado_em": agora,
            "expira_em": agora + timedelta(days=EXPIRACAO_DIAS),
        },
    )
    await db.execute(stmt)
    await db.commit()


# ============================================================
# Orquestração
# ============================================================

async def processar_agregacao(
    turma_id: uuid.UUID, data_ref: date, engine: AgregadorEngine,
    *, subc_engine: SubconceitoEngine | None = None,
    prosa_engine: ProsaEngine | None = None,
) -> None:
    """
    Matching → agregação → enriquecimento → upsert. Abre a própria sessão; nunca levanta.

    subc_engine/prosa_engine default None: sem eles, pula o enriquecimento e o
    comportamento é idêntico ao da CC #5 (estatística pura, prosa NULL).
    """
    semana_inicio, semana_fim = calcular_janela(data_ref)
    inicio_tz, fim_tz = _limites_tz(semana_inicio, semana_fim)

    async with async_session() as db:
        try:
            turma = (await db.execute(
                select(Turma).where(Turma.id == turma_id)
            )).scalar_one_or_none()
            if turma is None:
                logger.warning(f"Turma {turma_id} não existe — pulando.")
                return

            _, unidades, conceitos, aulas = await _carregar_taxonomia(db, turma)

            casadas = await _rodar_matching(
                db, engine, turma_id, inicio_tz, fim_tz, conceitos, aulas
            )
            conteudo = await _montar_conteudo(
                db, turma_id, inicio_tz, fim_tz, unidades, conceitos,
                semana_inicio, semana_fim,
            )
            prosa = await enriquecer(
                db, turma, conteudo, aulas,
                subc_engine=subc_engine, prosa_engine=prosa_engine,
                inicio_tz=inicio_tz, fim_tz=fim_tz,
                semana_inicio=semana_inicio, semana_fim=semana_fim,
            )
            await _upsert_relatorio(
                db, turma_id, semana_inicio, semana_fim, conteudo, prosa
            )

            logger.info(
                f"Agregador: turma {turma_id} | semana {semana_inicio}..{semana_fim} | "
                f"{casadas} casada(s), {conteudo['academica']['totais']['duvidas']} academica(s), "
                f"{conteudo['organizacional']['volume']} organizacional(is)."
            )
        except Exception as e:
            await db.rollback()
            logger.error(f"Erro ao agregar turma {turma_id}: {e}", exc_info=True)


async def turmas_com_duvidas(data_ref: date) -> list[uuid.UUID]:
    """Turmas com ao menos uma dúvida consentida na janela (pra rodar todas)."""
    semana_inicio, semana_fim = calcular_janela(data_ref)
    inicio_tz, fim_tz = _limites_tz(semana_inicio, semana_fim)
    async with async_session() as db:
        rows = (await db.execute(
            select(Duvida.turma_id).where(
                Duvida.consentimento_camada2.is_(True),
                Duvida.created_at >= inicio_tz,
                Duvida.created_at < fim_tz,
            ).distinct()
        )).scalars().all()
    return list(rows)
