"""
EduBot — Modelos SQLAlchemy (async)
Mapeamento ORM das tabelas do banco de dados.
"""

import uuid
from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import (
    String, Text, Boolean, Integer, Date, Time,
    DateTime, ForeignKey, Index, JSON
)
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.orm import (
    DeclarativeBase, Mapped, mapped_column, relationship
)
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class Instituicao(Base):
    __tablename__ = "instituicao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    dominio_email: Mapped[Optional[str]] = mapped_column(String(255))
    plano: Mapped[str] = mapped_column(String(50), default="trial")
    max_alunos: Mapped[int] = mapped_column(Integer, default=50)
    contato_diretoria: Mapped[Optional[dict]] = mapped_column(JSON, default=dict)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    alunos: Mapped[list["Aluno"]] = relationship(back_populates="instituicao")


class Aluno(Base):
    __tablename__ = "aluno"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    nome: Mapped[Optional[str]] = mapped_column(String(255))
    telefone_whatsapp: Mapped[str] = mapped_column(
        String(20), unique=True, nullable=False
    )
    instituicao_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instituicao.id", ondelete="SET NULL")
    )
    timezone: Mapped[str] = mapped_column(String(50), default="America/Sao_Paulo")
    horario_notificacao_diaria: Mapped[time] = mapped_column(
        Time, default=time(7, 0)
    )
    dia_resumo_semanal: Mapped[str] = mapped_column(String(10), default="sexta")
    onboarding_completo: Mapped[bool] = mapped_column(Boolean, default=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    instituicao: Mapped[Optional["Instituicao"]] = relationship(back_populates="alunos")
    materias: Mapped[list["Materia"]] = relationship(
        back_populates="aluno", cascade="all, delete-orphan"
    )
    notificacoes: Mapped[list["NotificacaoLog"]] = relationship(
        back_populates="aluno", cascade="all, delete-orphan"
    )
    sessao: Mapped[Optional["ConversaSessao"]] = relationship(
        back_populates="aluno", cascade="all, delete-orphan", uselist=False
    )


class Materia(Base):
    __tablename__ = "materia"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aluno_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    professor: Mapped[Optional[str]] = mapped_column(String(255))
    semestre: Mapped[Optional[str]] = mapped_column(String(20))
    fonte: Mapped[str] = mapped_column(String(50), default="manual")
    blackboard_course_id: Mapped[Optional[str]] = mapped_column(String(255))
    raw_plan_url: Mapped[Optional[str]] = mapped_column(Text)
    dados_extraidos: Mapped[Optional[dict]] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    aluno: Mapped["Aluno"] = relationship(back_populates="materias")
    eventos: Mapped[list["EventoAcademico"]] = relationship(
        back_populates="materia", cascade="all, delete-orphan"
    )


class EventoAcademico(Base):
    __tablename__ = "evento_academico"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    materia_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materia.id", ondelete="CASCADE"), nullable=False
    )
    data: Mapped[date] = mapped_column(Date, nullable=False)
    tipo: Mapped[str] = mapped_column(String(50), nullable=False)
    titulo: Mapped[str] = mapped_column(String(500), nullable=False)
    descricao: Mapped[Optional[str]] = mapped_column(Text)
    material_leitura: Mapped[Optional[str]] = mapped_column(Text)
    peso_nota: Mapped[Optional[str]] = mapped_column(String(50))
    urgencia: Mapped[str] = mapped_column(String(10), default="baixa")
    notificado_diario: Mapped[bool] = mapped_column(Boolean, default=False)
    notificado_semanal: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    # Relacionamentos
    materia: Mapped["Materia"] = relationship(back_populates="eventos")


class NotificacaoLog(Base):
    __tablename__ = "notificacao_log"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aluno_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False
    )
    tipo: Mapped[str] = mapped_column(String(20), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    enviado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    status: Mapped[str] = mapped_column(String(20), default="enviado")
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    erro_detalhes: Mapped[Optional[str]] = mapped_column(Text)

    # Relacionamentos
    aluno: Mapped["Aluno"] = relationship(back_populates="notificacoes")


class ConversaSessao(Base):
    __tablename__ = "conversa_sessao"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aluno_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False
    )
    mensagens: Mapped[dict] = mapped_column(JSON, default=list)
    contexto: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )

    # Relacionamentos
    aluno: Mapped["Aluno"] = relationship(back_populates="sessao")
