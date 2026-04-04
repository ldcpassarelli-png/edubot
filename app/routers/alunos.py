"""
EduBot — Router de alunos
CRUD de alunos, matérias e eventos acadêmicos.
"""

import uuid
from datetime import date, timedelta
from typing import Optional
from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.models.connection import get_db
from app.models.database import Aluno, Materia, EventoAcademico

router = APIRouter()


# ============================================================
# Schemas
# ============================================================

class CriarAlunoRequest(BaseModel):
    telefone_whatsapp: str
    nome: Optional[str] = None


class AlunoResponse(BaseModel):
    id: str
    nome: Optional[str]
    telefone_whatsapp: str
    onboarding_completo: bool
    qtd_materias: int = 0


class AdicionarMateriaRequest(BaseModel):
    """Request para adicionar matéria com eventos parseados."""
    materia: str
    professor: Optional[str] = None
    semestre: Optional[str] = None
    fonte: str = "manual"
    eventos: list[dict] = []


class EventoResumido(BaseModel):
    id: str
    data: str
    tipo: str
    titulo: str
    urgencia: str
    materia_nome: str
    dias_restantes: int


# ============================================================
# Endpoints de aluno
# ============================================================

@router.post("/alunos", response_model=AlunoResponse)
async def criar_ou_buscar_aluno(
    req: CriarAlunoRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Cria um novo aluno ou retorna o existente pelo telefone.
    Chamado durante onboarding no WhatsApp.
    """
    # Buscar existente
    result = await db.execute(
        select(Aluno).where(Aluno.telefone_whatsapp == req.telefone_whatsapp)
    )
    aluno = result.scalar_one_or_none()

    if aluno:
        # Contar matérias
        result_mat = await db.execute(
            select(Materia).where(Materia.aluno_id == aluno.id)
        )
        qtd = len(result_mat.scalars().all())

        return AlunoResponse(
            id=str(aluno.id),
            nome=aluno.nome,
            telefone_whatsapp=aluno.telefone_whatsapp,
            onboarding_completo=aluno.onboarding_completo,
            qtd_materias=qtd,
        )

    # Criar novo
    aluno = Aluno(
        telefone_whatsapp=req.telefone_whatsapp,
        nome=req.nome,
    )
    db.add(aluno)
    await db.flush()

    return AlunoResponse(
        id=str(aluno.id),
        nome=aluno.nome,
        telefone_whatsapp=aluno.telefone_whatsapp,
        onboarding_completo=False,
        qtd_materias=0,
    )


@router.post("/alunos/{aluno_id}/materias")
async def adicionar_materia(
    aluno_id: str,
    req: AdicionarMateriaRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Adiciona matéria com eventos ao aluno.
    Chamado após o parser extrair os dados e o aluno confirmar.
    """
    # Verificar aluno
    result = await db.execute(
        select(Aluno).where(Aluno.id == uuid.UUID(aluno_id))
    )
    aluno = result.scalar_one_or_none()
    if not aluno:
        raise HTTPException(status_code=404, detail="Aluno não encontrado.")

    # Criar matéria
    materia = Materia(
        aluno_id=aluno.id,
        nome=req.materia,
        professor=req.professor,
        semestre=req.semestre,
        fonte=req.fonte,
        dados_extraidos={"eventos_raw": req.eventos},
    )
    db.add(materia)
    await db.flush()

    # Criar eventos
    eventos_criados = 0
    for ev_data in req.eventos:
        try:
            evento = EventoAcademico(
                materia_id=materia.id,
                data=date.fromisoformat(ev_data["data"]),
                tipo=ev_data["tipo"],
                titulo=ev_data["titulo"],
                descricao=ev_data.get("descricao"),
                material_leitura=ev_data.get("material_leitura"),
                peso_nota=ev_data.get("peso_nota"),
                urgencia=ev_data.get("urgencia", "baixa"),
            )
            db.add(evento)
            eventos_criados += 1
        except (KeyError, ValueError) as e:
            continue  # Pula eventos com dados inválidos

    # Marcar onboarding como completo se é a primeira matéria
    if not aluno.onboarding_completo:
        aluno.onboarding_completo = True

    return {
        "materia_id": str(materia.id),
        "nome": materia.nome,
        "eventos_criados": eventos_criados,
        "mensagem": f"✅ {materia.nome} cadastrada com {eventos_criados} eventos!",
    }


@router.get("/alunos/{aluno_id}/proximos-eventos", response_model=list[EventoResumido])
async def listar_proximos_eventos(
    aluno_id: str,
    dias: int = 7,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista próximos eventos do aluno nos próximos N dias.
    Usado pelo chat interativo e notificações.
    """
    hoje = date.today()
    limite = hoje + timedelta(days=dias)

    result = await db.execute(
        select(EventoAcademico, Materia.nome)
        .join(Materia)
        .where(
            and_(
                Materia.aluno_id == uuid.UUID(aluno_id),
                EventoAcademico.data >= hoje,
                EventoAcademico.data <= limite,
            )
        )
        .order_by(EventoAcademico.data, EventoAcademico.urgencia.desc())
    )

    eventos = []
    for evento, materia_nome in result.all():
        eventos.append(EventoResumido(
            id=str(evento.id),
            data=evento.data.isoformat(),
            tipo=evento.tipo,
            titulo=evento.titulo,
            urgencia=evento.urgencia,
            materia_nome=materia_nome,
            dias_restantes=(evento.data - hoje).days,
        ))

    return eventos


@router.get("/alunos/{aluno_id}/eventos-hoje")
async def listar_eventos_hoje(
    aluno_id: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Lista eventos de hoje do aluno.
    Usado pela notificação diária matinal.
    """
    hoje = date.today()
    amanha = hoje + timedelta(days=1)

    # Eventos de hoje
    result_hoje = await db.execute(
        select(EventoAcademico, Materia.nome)
        .join(Materia)
        .where(
            and_(
                Materia.aluno_id == uuid.UUID(aluno_id),
                EventoAcademico.data == hoje,
            )
        )
        .order_by(EventoAcademico.urgencia.desc())
    )

    # Preview de amanhã (eventos importantes)
    result_amanha = await db.execute(
        select(EventoAcademico, Materia.nome)
        .join(Materia)
        .where(
            and_(
                Materia.aluno_id == uuid.UUID(aluno_id),
                EventoAcademico.data == amanha,
                EventoAcademico.urgencia.in_(["alta", "media"]),
            )
        )
        .order_by(EventoAcademico.urgencia.desc())
    )

    return {
        "data": hoje.isoformat(),
        "eventos_hoje": [
            {
                "tipo": ev.tipo,
                "titulo": ev.titulo,
                "descricao": ev.descricao,
                "material_leitura": ev.material_leitura,
                "urgencia": ev.urgencia,
                "materia": nome,
            }
            for ev, nome in result_hoje.all()
        ],
        "preview_amanha": [
            {
                "tipo": ev.tipo,
                "titulo": ev.titulo,
                "urgencia": ev.urgencia,
                "materia": nome,
            }
            for ev, nome in result_amanha.all()
        ],
    }
