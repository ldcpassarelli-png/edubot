"""
EduBot — Modelos SQLAlchemy (async)
Mapeamento ORM das tabelas do banco de dados.
"""

import uuid
from datetime import datetime, date, time
from typing import Optional
from sqlalchemy import (
    String, Text, Boolean, Integer, Date, Time,
    DateTime, ForeignKey, Index, JSON, UniqueConstraint
)
from sqlalchemy.dialects.postgresql import UUID, JSONB
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


# ============================================================
# CAMADA 2 — Inteligência pedagógica (14 tabelas)
#
# Schema criado pela migration 0002. Ponte com a Camada 1 é por
# `aluno_telefone` STRING (não FK) — desacoplamento deliberado.
# Sem relationship() nesta fase: só colunas, FKs e constraints fiéis
# ao schema. Relacionamentos entram quando uma sessão futura precisar.
# ============================================================


# ---------- Bloco institucional (7) ----------

class Curso(Base):
    __tablename__ = "curso"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instituicao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class MateriaCamada2(Base):
    __tablename__ = "materia_camada2"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instituicao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    codigo: Mapped[Optional[str]] = mapped_column(String(50))
    categoria: Mapped[Optional[str]] = mapped_column(String(50))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Professor(Base):
    __tablename__ = "professor"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    instituicao_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[Optional[str]] = mapped_column(String(255))
    telefone_whatsapp: Mapped[Optional[str]] = mapped_column(String(20), unique=True)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class PlanoDeAula(Base):
    __tablename__ = "plano_de_aula"
    __table_args__ = (
        UniqueConstraint("materia_camada2_id", "semestre", name="uq_plano_materia_semestre"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    materia_camada2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materia_camada2.id", ondelete="CASCADE"), nullable=False
    )
    semestre: Mapped[str] = mapped_column(String(20), nullable=False)
    documento_url: Mapped[Optional[str]] = mapped_column(Text)
    documento_parseado: Mapped[Optional[dict]] = mapped_column(JSONB)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class UnidadeTematica(Base):
    __tablename__ = "unidade_tematica"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plano_de_aula_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plano_de_aula.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(500), nullable=False)
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Conceito(Base):
    __tablename__ = "conceito"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    unidade_tematica_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("unidade_tematica.id", ondelete="CASCADE"), nullable=False
    )
    nome: Mapped[str] = mapped_column(String(500), nullable=False)
    tipo: Mapped[Optional[str]] = mapped_column(String(50))
    ordem: Mapped[int] = mapped_column(Integer, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Aula(Base):
    __tablename__ = "aula"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    plano_de_aula_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("plano_de_aula.id", ondelete="CASCADE"), nullable=False
    )
    numero: Mapped[int] = mapped_column(Integer, nullable=False)
    data_prevista: Mapped[Optional[date]] = mapped_column(Date)
    titulo: Mapped[Optional[str]] = mapped_column(String(500))
    tipo_atividade: Mapped[Optional[str]] = mapped_column(String(50))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


# ---------- Bloco turma (coorte + 3) ----------
#
# Coorte (migration 0004) é a "turma-Insper" (grade fechada que o codigo_convite
# abre) ACIMA da Turma. Turma segue sendo classe-de-matéria (unidade do
# relatório). matricula e duvida foram repontadas pra coorte; duvida.turma_id
# virou nullable (mantendo a FK turma_id -> turma, CASCADE).

class Coorte(Base):
    __tablename__ = "coorte"
    __table_args__ = (
        UniqueConstraint("curso_id", "letra", "semestre", name="uq_coorte_curso_letra_semestre"),
        UniqueConstraint("codigo_convite", name="uq_coorte_codigo_convite"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    curso_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("curso.id", ondelete="RESTRICT"), nullable=False
    )
    letra: Mapped[str] = mapped_column(String(20), nullable=False)
    semestre: Mapped[str] = mapped_column(String(20), nullable=False)
    codigo_convite: Mapped[str] = mapped_column(String(50), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Turma(Base):
    __tablename__ = "turma"
    __table_args__ = (
        UniqueConstraint(
            "materia_camada2_id", "curso_id", "letra", "semestre",
            name="uq_turma_materia_curso_letra_semestre",
        ),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    materia_camada2_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("materia_camada2.id", ondelete="RESTRICT"), nullable=False
    )
    curso_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("curso.id", ondelete="RESTRICT"), nullable=False
    )
    coorte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coorte.id", ondelete="RESTRICT"), nullable=False
    )
    letra: Mapped[str] = mapped_column(String(20), nullable=False)
    semestre: Mapped[str] = mapped_column(String(20), nullable=False)
    professor_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("professor.id", ondelete="SET NULL")
    )
    horario: Mapped[Optional[str]] = mapped_column(String(100))
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class ProgressoTurma(Base):
    __tablename__ = "progresso_turma"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    turma_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turma.id", ondelete="CASCADE"), nullable=False, unique=True
    )
    aula_atual_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aula.id", ondelete="SET NULL")
    )
    confirmado_pelo_professor: Mapped[bool] = mapped_column(Boolean, default=False)
    data_ultima_atualizacao: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


class Matricula(Base):
    __tablename__ = "matricula"
    __table_args__ = (
        UniqueConstraint("coorte_id", "aluno_telefone", name="uq_matricula_coorte_aluno"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    coorte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coorte.id", ondelete="CASCADE"), nullable=False
    )
    aluno_telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    ativo: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------- Bloco consentimento (1) ----------

class ConsentimentoCamada2(Base):
    __tablename__ = "consentimento_camada2"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aluno_telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    versao_texto: Mapped[str] = mapped_column(String(20), nullable=False)
    consentiu: Mapped[bool] = mapped_column(Boolean, nullable=False)
    data_consentimento: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False
    )
    data_revogacao: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    texto_aceito: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), onupdate=func.now()
    )


# ---------- Bloco captura (3) ----------

class Mensagem(Base):
    __tablename__ = "mensagem"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    aluno_telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    direcao: Mapped[str] = mapped_column(String(10), nullable=False)
    conteudo: Mapped[str] = mapped_column(Text, nullable=False)
    whatsapp_message_id: Mapped[Optional[str]] = mapped_column(String(255))
    recebida_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    metadados: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Duvida(Base):
    __tablename__ = "duvida"

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    mensagem_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("mensagem.id", ondelete="CASCADE"), nullable=False
    )
    turma_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turma.id", ondelete="CASCADE")
    )
    coorte_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("coorte.id", ondelete="CASCADE"), nullable=False
    )
    categoria: Mapped[str] = mapped_column(String(20), nullable=False)
    conceito_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("conceito.id", ondelete="SET NULL")
    )
    aula_id: Mapped[Optional[uuid.UUID]] = mapped_column(
        UUID(as_uuid=True), ForeignKey("aula.id", ondelete="SET NULL")
    )
    texto_extraido: Mapped[str] = mapped_column(Text, nullable=False)
    embedding: Mapped[Optional[dict]] = mapped_column(JSONB)
    consentimento_camada2: Mapped[bool] = mapped_column(Boolean, nullable=False)
    aluno_telefone: Mapped[str] = mapped_column(String(20), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )


class Relatorio(Base):
    __tablename__ = "relatorio"
    __table_args__ = (
        UniqueConstraint("turma_id", "semana_inicio", name="uq_relatorio_turma_semana"),
    )

    id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), primary_key=True, default=uuid.uuid4
    )
    turma_id: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), ForeignKey("turma.id", ondelete="CASCADE"), nullable=False
    )
    semana_inicio: Mapped[date] = mapped_column(Date, nullable=False)
    semana_fim: Mapped[date] = mapped_column(Date, nullable=False)
    token_acesso: Mapped[uuid.UUID] = mapped_column(
        UUID(as_uuid=True), nullable=False, unique=True, default=uuid.uuid4
    )
    expira_em: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    conteudo: Mapped[dict] = mapped_column(JSONB, nullable=False)
    prosa_acao: Mapped[Optional[str]] = mapped_column(Text)
    gerado_em: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    enviado_ao_professor_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    acessado_em: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
