"""Baseline: schema Camada 1 (6 tabelas existentes)

Revision ID: 0001
Revises: None
Create Date: 2026-05-16
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # --- Extension ---
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto"')

    # --- instituicao ---
    op.create_table(
        "instituicao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("dominio_email", sa.String(255), nullable=True),
        sa.Column("plano", sa.String(50), server_default="trial"),
        sa.Column("max_alunos", sa.Integer, server_default="50"),
        sa.Column("contato_diretoria", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- aluno ---
    op.create_table(
        "aluno",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("nome", sa.String(255), nullable=True),
        sa.Column("telefone_whatsapp", sa.String(20), nullable=False, unique=True),
        sa.Column("instituicao_id", UUID(as_uuid=True), sa.ForeignKey("instituicao.id", ondelete="SET NULL"), nullable=True),
        sa.Column("timezone", sa.String(50), server_default="America/Sao_Paulo"),
        sa.Column("horario_notificacao_diaria", sa.Time, server_default="07:00"),
        sa.Column("dia_resumo_semanal", sa.String(10), server_default="sexta"),
        sa.Column("onboarding_completo", sa.Boolean, server_default="false"),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_aluno_telefone", "aluno", ["telefone_whatsapp"])
    op.create_index("idx_aluno_instituicao", "aluno", ["instituicao_id"])
    op.create_index("idx_aluno_ativo", "aluno", ["ativo"], postgresql_where=sa.text("ativo = true"))

    # --- materia ---
    op.create_table(
        "materia",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("aluno_id", UUID(as_uuid=True), sa.ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("professor", sa.String(255), nullable=True),
        sa.Column("semestre", sa.String(20), nullable=True),
        sa.Column("fonte", sa.String(50), server_default="manual"),
        sa.Column("blackboard_course_id", sa.String(255), nullable=True),
        sa.Column("raw_plan_url", sa.Text, nullable=True),
        sa.Column("dados_extraidos", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_materia_aluno", "materia", ["aluno_id"])

    # --- evento_academico ---
    op.create_table(
        "evento_academico",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("materia_id", UUID(as_uuid=True), sa.ForeignKey("materia.id", ondelete="CASCADE"), nullable=False),
        sa.Column("data", sa.Date, nullable=False),
        sa.Column("tipo", sa.String(50), nullable=False),
        sa.Column("titulo", sa.String(500), nullable=False),
        sa.Column("descricao", sa.Text, nullable=True),
        sa.Column("material_leitura", sa.Text, nullable=True),
        sa.Column("peso_nota", sa.String(50), nullable=True),
        sa.Column("urgencia", sa.String(10), server_default="baixa"),
        sa.Column("notificado_diario", sa.Boolean, server_default="false"),
        sa.Column("notificado_semanal", sa.Boolean, server_default="false"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_evento_materia", "evento_academico", ["materia_id"])
    op.create_index("idx_evento_data", "evento_academico", ["data"])
    op.create_index("idx_evento_tipo", "evento_academico", ["tipo"])
    op.create_index(
        "idx_evento_notificacao_diaria",
        "evento_academico",
        ["data", "notificado_diario"],
        postgresql_where=sa.text("notificado_diario = false"),
    )

    # --- notificacao_log ---
    op.create_table(
        "notificacao_log",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("aluno_id", UUID(as_uuid=True), sa.ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False),
        sa.Column("tipo", sa.String(20), nullable=False),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("enviado_em", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("status", sa.String(20), server_default="enviado"),
        sa.Column("whatsapp_message_id", sa.String(255), nullable=True),
        sa.Column("erro_detalhes", sa.Text, nullable=True),
    )
    op.create_index("idx_notificacao_aluno", "notificacao_log", ["aluno_id"])
    op.create_index("idx_notificacao_enviado", "notificacao_log", ["enviado_em"])

    # --- conversa_sessao ---
    op.create_table(
        "conversa_sessao",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("aluno_id", UUID(as_uuid=True), sa.ForeignKey("aluno.id", ondelete="CASCADE"), nullable=False),
        sa.Column("mensagens", JSONB, server_default=sa.text("'[]'::jsonb")),
        sa.Column("contexto", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_conversa_aluno", "conversa_sessao", ["aluno_id"])

    # --- Triggers de updated_at ---
    op.execute("""
        CREATE OR REPLACE FUNCTION atualizar_updated_at()
        RETURNS TRIGGER AS $$
        BEGIN
            NEW.updated_at = now();
            RETURN NEW;
        END;
        $$ LANGUAGE plpgsql;
    """)
    op.execute("CREATE TRIGGER trg_aluno_updated BEFORE UPDATE ON aluno FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_materia_updated BEFORE UPDATE ON materia FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_conversa_updated BEFORE UPDATE ON conversa_sessao FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")

    # --- Views ---
    op.execute("""
        CREATE OR REPLACE VIEW proximos_eventos AS
        SELECT
            e.id AS evento_id, e.data, e.tipo, e.titulo, e.descricao,
            e.material_leitura, e.peso_nota, e.urgencia,
            m.nome AS materia_nome, m.professor,
            a.id AS aluno_id, a.nome AS aluno_nome,
            a.telefone_whatsapp, a.horario_notificacao_diaria,
            (e.data - CURRENT_DATE) AS dias_restantes
        FROM evento_academico e
        JOIN materia m ON e.materia_id = m.id
        JOIN aluno a ON m.aluno_id = a.id
        WHERE e.data >= CURRENT_DATE
          AND e.data <= CURRENT_DATE + INTERVAL '7 days'
          AND a.ativo = true
        ORDER BY e.data ASC, e.urgencia DESC;
    """)
    op.execute("""
        CREATE OR REPLACE VIEW eventos_hoje AS
        SELECT
            e.id AS evento_id, e.data, e.tipo, e.titulo, e.descricao,
            e.material_leitura, e.peso_nota, e.urgencia,
            m.nome AS materia_nome,
            a.id AS aluno_id, a.telefone_whatsapp,
            a.horario_notificacao_diaria
        FROM evento_academico e
        JOIN materia m ON e.materia_id = m.id
        JOIN aluno a ON m.aluno_id = a.id
        WHERE e.data = CURRENT_DATE
          AND a.ativo = true
          AND e.notificado_diario = false
        ORDER BY a.id, e.urgencia DESC;
    """)


def downgrade() -> None:
    # Views primeiro (dependem das tabelas)
    op.execute("DROP VIEW IF EXISTS eventos_hoje")
    op.execute("DROP VIEW IF EXISTS proximos_eventos")

    # Triggers
    op.execute("DROP TRIGGER IF EXISTS trg_conversa_updated ON conversa_sessao")
    op.execute("DROP TRIGGER IF EXISTS trg_materia_updated ON materia")
    op.execute("DROP TRIGGER IF EXISTS trg_aluno_updated ON aluno")
    op.execute("DROP FUNCTION IF EXISTS atualizar_updated_at()")

    # Tabelas em ordem reversa de dependência
    op.drop_table("conversa_sessao")
    op.drop_table("notificacao_log")
    op.drop_table("evento_academico")
    op.drop_table("materia")
    op.drop_table("aluno")
    op.drop_table("instituicao")
