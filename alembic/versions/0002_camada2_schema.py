"""Camada 2: 14 tabelas novas (institucional, turma, consentimento, captura)

Revision ID: 0002
Revises: 0001
Create Date: 2026-05-20
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID, JSONB

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================
    # Bloco 1 — Institucional (7 tabelas)
    # ==========================================================

    # --- curso ---
    op.create_table(
        "curso",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("instituicao_id", UUID(as_uuid=True), sa.ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_curso_instituicao", "curso", ["instituicao_id"])

    # --- materia_camada2 ---
    op.create_table(
        "materia_camada2",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("instituicao_id", UUID(as_uuid=True), sa.ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("codigo", sa.String(50), nullable=True),
        sa.Column("categoria", sa.String(50), nullable=True),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_materia_camada2_instituicao", "materia_camada2", ["instituicao_id"])
    op.create_index("idx_materia_camada2_ativo", "materia_camada2", ["ativo"], postgresql_where=sa.text("ativo = true"))

    # --- professor ---
    op.create_table(
        "professor",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("instituicao_id", UUID(as_uuid=True), sa.ForeignKey("instituicao.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=True),
        sa.Column("telefone_whatsapp", sa.String(20), nullable=True, unique=True),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_professor_instituicao", "professor", ["instituicao_id"])

    # --- plano_de_aula ---
    op.create_table(
        "plano_de_aula",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("materia_camada2_id", UUID(as_uuid=True), sa.ForeignKey("materia_camada2.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semestre", sa.String(20), nullable=False),
        sa.Column("documento_url", sa.Text, nullable=True),
        sa.Column("documento_parseado", JSONB, nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("materia_camada2_id", "semestre", name="uq_plano_materia_semestre"),
    )

    # --- unidade_tematica ---
    op.create_table(
        "unidade_tematica",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plano_de_aula_id", UUID(as_uuid=True), sa.ForeignKey("plano_de_aula.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(500), nullable=False),
        sa.Column("ordem", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_unidade_plano_ordem", "unidade_tematica", ["plano_de_aula_id", "ordem"])

    # --- conceito ---
    op.create_table(
        "conceito",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("unidade_tematica_id", UUID(as_uuid=True), sa.ForeignKey("unidade_tematica.id", ondelete="CASCADE"), nullable=False),
        sa.Column("nome", sa.String(500), nullable=False),
        sa.Column("tipo", sa.String(50), nullable=True),
        sa.Column("ordem", sa.Integer, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_conceito_unidade_ordem", "conceito", ["unidade_tematica_id", "ordem"])

    # --- aula ---
    op.create_table(
        "aula",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("plano_de_aula_id", UUID(as_uuid=True), sa.ForeignKey("plano_de_aula.id", ondelete="CASCADE"), nullable=False),
        sa.Column("numero", sa.Integer, nullable=False),
        sa.Column("data_prevista", sa.Date, nullable=True),
        sa.Column("titulo", sa.String(500), nullable=True),
        sa.Column("tipo_atividade", sa.String(50), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_aula_plano_numero", "aula", ["plano_de_aula_id", "numero"])
    op.create_index("idx_aula_data_prevista", "aula", ["data_prevista"])

    # ==========================================================
    # Bloco 2 — Turma (3 tabelas)
    # ==========================================================

    # --- turma ---
    op.create_table(
        "turma",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("materia_camada2_id", UUID(as_uuid=True), sa.ForeignKey("materia_camada2.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("curso_id", UUID(as_uuid=True), sa.ForeignKey("curso.id", ondelete="RESTRICT"), nullable=False),
        sa.Column("letra", sa.String(20), nullable=False),
        sa.Column("semestre", sa.String(20), nullable=False),
        sa.Column("professor_id", UUID(as_uuid=True), sa.ForeignKey("professor.id", ondelete="SET NULL"), nullable=True),
        sa.Column("horario", sa.String(100), nullable=True),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("materia_camada2_id", "curso_id", "letra", "semestre", name="uq_turma_materia_curso_letra_semestre"),
    )
    op.create_index("idx_turma_professor", "turma", ["professor_id"])
    op.create_index("idx_turma_ativo", "turma", ["ativo"], postgresql_where=sa.text("ativo = true"))

    # --- progresso_turma ---
    op.create_table(
        "progresso_turma",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("turma_id", UUID(as_uuid=True), sa.ForeignKey("turma.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("aula_atual_id", UUID(as_uuid=True), sa.ForeignKey("aula.id", ondelete="SET NULL"), nullable=True),
        sa.Column("confirmado_pelo_professor", sa.Boolean, server_default="false"),
        sa.Column("data_ultima_atualizacao", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )

    # --- matricula ---
    op.create_table(
        "matricula",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("turma_id", UUID(as_uuid=True), sa.ForeignKey("turma.id", ondelete="CASCADE"), nullable=False),
        sa.Column("aluno_telefone", sa.String(20), nullable=False),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("turma_id", "aluno_telefone", name="uq_matricula_turma_aluno"),
    )
    op.create_index("idx_matricula_aluno_telefone", "matricula", ["aluno_telefone"])

    # ==========================================================
    # Bloco 3 — Consentimento (1 tabela)
    # ==========================================================

    # --- consentimento_camada2 ---
    op.create_table(
        "consentimento_camada2",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("aluno_telefone", sa.String(20), nullable=False),
        sa.Column("versao_texto", sa.String(20), nullable=False),
        sa.Column("consentiu", sa.Boolean, nullable=False),
        sa.Column("data_consentimento", sa.DateTime(timezone=True), nullable=False),
        sa.Column("data_revogacao", sa.DateTime(timezone=True), nullable=True),
        sa.Column("texto_aceito", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_consentimento_aluno_telefone", "consentimento_camada2", ["aluno_telefone"])

    # ==========================================================
    # Bloco 4 — Captura (3 tabelas)
    # ==========================================================

    # --- mensagem ---
    op.create_table(
        "mensagem",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("aluno_telefone", sa.String(20), nullable=False),
        sa.Column("direcao", sa.String(10), nullable=False),
        sa.Column("conteudo", sa.Text, nullable=False),
        sa.Column("whatsapp_message_id", sa.String(255), nullable=True),
        sa.Column("recebida_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("metadados", JSONB, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_mensagem_aluno_recebida", "mensagem", ["aluno_telefone", "recebida_em"])
    op.create_index("idx_mensagem_direcao_recebida", "mensagem", ["direcao", "recebida_em"])
    op.create_index("idx_mensagem_whatsapp_id", "mensagem", ["whatsapp_message_id"])

    # --- duvida ---
    op.create_table(
        "duvida",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("mensagem_id", UUID(as_uuid=True), sa.ForeignKey("mensagem.id", ondelete="CASCADE"), nullable=False),
        sa.Column("turma_id", UUID(as_uuid=True), sa.ForeignKey("turma.id", ondelete="CASCADE"), nullable=False),
        sa.Column("categoria", sa.String(20), nullable=False),
        sa.Column("conceito_id", UUID(as_uuid=True), sa.ForeignKey("conceito.id", ondelete="SET NULL"), nullable=True),
        sa.Column("aula_id", UUID(as_uuid=True), sa.ForeignKey("aula.id", ondelete="SET NULL"), nullable=True),
        sa.Column("texto_extraido", sa.Text, nullable=False),
        sa.Column("embedding", JSONB, nullable=True),
        sa.Column("consentimento_camada2", sa.Boolean, nullable=False),
        sa.Column("aluno_telefone", sa.String(20), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
    )
    op.create_index("idx_duvida_turma_created", "duvida", ["turma_id", "created_at"])
    op.create_index("idx_duvida_turma_conceito_created", "duvida", ["turma_id", "conceito_id", "created_at"])
    op.create_index("idx_duvida_turma_categoria", "duvida", ["turma_id", "categoria"])
    op.create_index(
        "idx_duvida_consentimento",
        "duvida",
        ["consentimento_camada2"],
        postgresql_where=sa.text("consentimento_camada2 = true"),
    )

    # --- relatorio ---
    op.create_table(
        "relatorio",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("turma_id", UUID(as_uuid=True), sa.ForeignKey("turma.id", ondelete="CASCADE"), nullable=False),
        sa.Column("semana_inicio", sa.Date, nullable=False),
        sa.Column("semana_fim", sa.Date, nullable=False),
        sa.Column("token_acesso", UUID(as_uuid=True), nullable=False, unique=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("expira_em", sa.DateTime(timezone=True), nullable=False),
        sa.Column("conteudo", JSONB, nullable=False),
        sa.Column("gerado_em", sa.DateTime(timezone=True), nullable=False, server_default=sa.text("now()")),
        sa.Column("enviado_ao_professor_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("acessado_em", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.UniqueConstraint("turma_id", "semana_inicio", name="uq_relatorio_turma_semana"),
    )

    # ==========================================================
    # Triggers de updated_at (função já existe da 0001)
    # ==========================================================
    op.execute("CREATE TRIGGER trg_curso_updated BEFORE UPDATE ON curso FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_materia_camada2_updated BEFORE UPDATE ON materia_camada2 FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_professor_updated BEFORE UPDATE ON professor FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_plano_de_aula_updated BEFORE UPDATE ON plano_de_aula FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_turma_updated BEFORE UPDATE ON turma FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_progresso_turma_updated BEFORE UPDATE ON progresso_turma FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_matricula_updated BEFORE UPDATE ON matricula FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")
    op.execute("CREATE TRIGGER trg_consentimento_camada2_updated BEFORE UPDATE ON consentimento_camada2 FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();")


def downgrade() -> None:
    # Triggers primeiro (dependem das tabelas)
    op.execute("DROP TRIGGER IF EXISTS trg_consentimento_camada2_updated ON consentimento_camada2")
    op.execute("DROP TRIGGER IF EXISTS trg_matricula_updated ON matricula")
    op.execute("DROP TRIGGER IF EXISTS trg_progresso_turma_updated ON progresso_turma")
    op.execute("DROP TRIGGER IF EXISTS trg_turma_updated ON turma")
    op.execute("DROP TRIGGER IF EXISTS trg_plano_de_aula_updated ON plano_de_aula")
    op.execute("DROP TRIGGER IF EXISTS trg_professor_updated ON professor")
    op.execute("DROP TRIGGER IF EXISTS trg_materia_camada2_updated ON materia_camada2")
    op.execute("DROP TRIGGER IF EXISTS trg_curso_updated ON curso")

    # NÃO dropar atualizar_updated_at() — pertence à 0001

    # Tabelas em ordem reversa de dependência
    op.drop_table("relatorio")
    op.drop_table("duvida")
    op.drop_table("mensagem")
    op.drop_table("consentimento_camada2")
    op.drop_table("matricula")
    op.drop_table("progresso_turma")
    op.drop_table("turma")
    op.drop_table("aula")
    op.drop_table("conceito")
    op.drop_table("unidade_tematica")
    op.drop_table("plano_de_aula")
    op.drop_table("professor")
    op.drop_table("materia_camada2")
    op.drop_table("curso")
