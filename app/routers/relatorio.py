"""
EduBot — Rota pública do relatório semanal (Camada 2, CC #6).

GET /r/{token} — serve a página do relatório pedagógico pelo próprio app FastAPI
(embrião natural da Camada 3). Jinja2 server-side puro; Chart.js só via CDN.

Token UUID com validade de 14 dias. Link inexistente ou expirado NÃO quebra:
serve uma página limpa "relatório indisponível" (200, nunca 500). O gráfico de
histórico mostra só as semanas <= a do token (nunca futuro).

Privacidade: a página lê o JSONB já agregado (estatística pura) + a prosa. Nenhum
texto cru de aluno e nenhum telefone trafegam — eles nunca entraram no relatório.
"""

import os
import uuid
from datetime import datetime

from fastapi import APIRouter, Depends, Request
from fastapi.responses import HTMLResponse
from fastapi.templating import Jinja2Templates
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.connection import get_db
from app.models.database import (
    Aula, Curso, MateriaCamada2, Matricula, PlanoDeAula, Professor,
    ProgressoTurma, Relatorio, Turma,
)
from app.services.agregador import TZ

router = APIRouter()

_TEMPLATES_DIR = os.path.join(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "templates"
)
templates = Jinja2Templates(directory=_TEMPLATES_DIR)

_MESES = ["jan", "fev", "mar", "abr", "mai", "jun",
          "jul", "ago", "set", "out", "nov", "dez"]


def _dd_mm(d) -> str:
    return f"{d.day:02d}/{d.month:02d}"


def _dd_mes(d) -> str:
    return f"{d.day:02d}/{_MESES[d.month - 1]}"


def _dd_mm_aaaa(d) -> str:
    return f"{d.day:02d}/{d.month:02d}/{d.year}"


def _indisponivel(request: Request, motivo: str) -> HTMLResponse:
    """Página limpa para token inexistente/expirado — sempre 200, nunca erro."""
    return templates.TemplateResponse(
        "relatorio_indisponivel.html",
        {"request": request, "motivo": motivo},
        status_code=200,
    )


@router.get("/r/{token}", response_class=HTMLResponse)
async def ver_relatorio(token: str, request: Request, db: AsyncSession = Depends(get_db)):
    try:
        token_uuid = uuid.UUID(token)
    except ValueError:
        return _indisponivel(request, "nao_encontrado")

    rel = (await db.execute(
        select(Relatorio).where(Relatorio.token_acesso == token_uuid)
    )).scalar_one_or_none()
    if rel is None:
        return _indisponivel(request, "nao_encontrado")

    agora = datetime.now(TZ)
    if rel.expira_em < agora:
        return _indisponivel(request, "expirado")

    # ---- contexto institucional (joins; materializado em valores planos) ----
    turma = (await db.execute(
        select(Turma).where(Turma.id == rel.turma_id)
    )).scalar_one_or_none()

    materia = curso = professor = aula_atual = proxima_aula = None
    total_alunos = 0
    if turma is not None:
        materia = (await db.execute(
            select(MateriaCamada2).where(MateriaCamada2.id == turma.materia_camada2_id)
        )).scalar_one_or_none()
        curso = (await db.execute(
            select(Curso).where(Curso.id == turma.curso_id)
        )).scalar_one_or_none()
        if turma.professor_id:
            professor = (await db.execute(
                select(Professor).where(Professor.id == turma.professor_id)
            )).scalar_one_or_none()
        total_alunos = (await db.execute(
            select(func.count()).select_from(Matricula).where(
                Matricula.turma_id == turma.id, Matricula.ativo.is_(True)
            )
        )).scalar_one()

        plano = (await db.execute(
            select(PlanoDeAula).where(
                PlanoDeAula.materia_camada2_id == turma.materia_camada2_id,
                PlanoDeAula.semestre == turma.semestre,
            )
        )).scalar_one_or_none()
        if plano is not None:
            # próxima aula = 1ª com data prevista DEPOIS da semana de referência.
            proxima_aula = (await db.execute(
                select(Aula).where(
                    Aula.plano_de_aula_id == plano.id,
                    Aula.data_prevista > rel.semana_fim,
                ).order_by(Aula.data_prevista).limit(1)
            )).scalar_one_or_none()

        progresso = (await db.execute(
            select(ProgressoTurma).where(ProgressoTurma.turma_id == turma.id)
        )).scalar_one_or_none()
        if progresso and progresso.aula_atual_id:
            aula_atual = (await db.execute(
                select(Aula).where(Aula.id == progresso.aula_atual_id)
            )).scalar_one_or_none()

    # ---- "onde a turma travou": 1 card por conceito COM subtema ----
    conteudo = rel.conteudo or {}
    ac = conteudo.get("academica", {})
    blocos = []
    for u in ac.get("unidades", []):
        for c in u.get("conceitos", []):
            subs = c.get("subconceitos", [])
            if not subs:
                continue
            blocos.append({
                "unidade": u.get("unidade_nome", ""),
                "conceito": c.get("conceito_nome", ""),
                "volume": c.get("volume", 0),
                "alunos": c.get("alunos_distintos", 0),
                "subtemas": subs,
                "_reinc": max((s.get("reincidentes_count", 0) for s in subs), default=0),
            })
    # Cards mais urgentes primeiro: não-consolidação, depois volume.
    blocos.sort(key=lambda b: (-b["_reinc"], -b["volume"]))

    # ---- histórico do gráfico: só semanas <= a do token (nunca futuro) ----
    historico = (await db.execute(
        select(Relatorio).where(
            Relatorio.turma_id == rel.turma_id,
            Relatorio.semana_inicio <= rel.semana_inicio,
        ).order_by(Relatorio.semana_inicio)
    )).scalars().all()
    chart_labels = [_dd_mm(h.semana_inicio) for h in historico]
    chart_data = [
        (h.conteudo or {}).get("academica", {}).get("totais", {}).get("duvidas", 0)
        for h in historico
    ]

    paragrafos = [p.strip() for p in (rel.prosa_acao or "").split("\n\n") if p.strip()]

    # ---- marca primeiro acesso (get_db commita ao final) ----
    if rel.acessado_em is None:
        rel.acessado_em = agora

    ctx = {
        "request": request,
        "materia_nome": materia.nome if materia else "Disciplina",
        "turma_letra": turma.letra if turma else "",
        "professor_nome": professor.nome if professor else None,
        "curso_nome": curso.nome if curso else None,
        "semestre": turma.semestre if turma else "",
        "semana_label": f"{_dd_mm(rel.semana_inicio)} – {_dd_mm(rel.semana_fim)}",
        "total_duvidas": ac.get("totais", {}).get("duvidas", 0),
        "alunos_com_duvida": ac.get("totais", {}).get("alunos_distintos", 0),
        "total_alunos": total_alunos,
        "conceitos_travando": ac.get("totais", {}).get("conceitos_com_duvida", 0),
        "proxima_aula_titulo": proxima_aula.titulo if proxima_aula else None,
        "proxima_aula_data": (
            _dd_mes(proxima_aula.data_prevista)
            if proxima_aula and proxima_aula.data_prevista else None
        ),
        "aula_atual_titulo": aula_atual.titulo if aula_atual else None,
        "blocos": blocos,
        "nao_classificadas": ac.get("nao_classificadas", {}).get("volume", 0),
        "organizacional": conteudo.get("organizacional", {}).get("volume", 0),
        "chart_labels": chart_labels,
        "chart_data": chart_data,
        "paragrafos": paragrafos,
        "expira_label": _dd_mm_aaaa(rel.expira_em.astimezone(TZ)),
    }
    return templates.TemplateResponse("relatorio.html", ctx)
