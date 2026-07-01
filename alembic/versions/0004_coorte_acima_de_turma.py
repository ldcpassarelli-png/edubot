"""0004: entidade Coorte ACIMA de Turma (repontagem de matricula e duvida)

Revision ID: 0004
Revises: 0003
Create Date: 2026-06-30

Contexto (ratificado no chat 27-29/06, briefing Seção 10):
- Nasce `coorte` (a "turma-Insper" / grade fechada que o codigo_convite abre)
  ACIMA de `turma`. `turma` NÃO muda de significado: segue sendo classe-de-matéria
  e unidade do relatório.
- Schema aditivo. `turma`/`duvida`/`matricula` já estão POPULADAS (seed) → cada
  coluna NOT NULL nova entra como nullable → backfill → SET NOT NULL.
- `coorte` nasce vazia → suas colunas nascem NOT NULL inline.
- `matricula` é REPONTADA de turma para coorte (perde turma_id).
- `duvida` ganha coorte_id NOT NULL e tem turma_id RELAXADO para nullable
  (mantém a FK turma_id -> turma existente, CASCADE).

NOTA Alembic vs. receita:
- NÃO há `BEGIN/COMMIT` literal nem `UPDATE alembic_version` manual: o Alembic
  roda upgrade()/downgrade() em UMA transação no Postgres e emite o update de
  alembic_version dentro dela (online e `--sql` offline). Escrever isso à mão
  corromperia a contabilidade do Alembic. `ON_ERROR_STOP=1` é flag do psql na
  aplicação manual (Opção B), não pertence ao arquivo.
- DDL 100% à mão (sem autogenerate — ele não enxerga o índice UNIQUE parcial da
  0003 e injetaria regressão).
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0004"
down_revision: Union[str, None] = "0003"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ==========================================================
    # (1) CREATE TABLE coorte (nova/vazia → colunas NOT NULL inline)
    # ==========================================================
    op.create_table(
        "coorte",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("curso_id", UUID(as_uuid=True), nullable=False),
        sa.Column("letra", sa.String(20), nullable=False),
        sa.Column("semestre", sa.String(20), nullable=False),
        sa.Column("codigo_convite", sa.String(50), nullable=False),
        sa.Column("ativo", sa.Boolean, server_default="true"),
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["curso_id"], ["curso.id"], ondelete="RESTRICT", name="fk_coorte_curso"),
        sa.UniqueConstraint("curso_id", "letra", "semestre", name="uq_coorte_curso_letra_semestre"),
        sa.UniqueConstraint("codigo_convite", name="uq_coorte_codigo_convite"),
    )
    # Trigger updated_at (mesma função da 0001, reusada como curso/professor)
    op.execute(
        "CREATE TRIGGER trg_coorte_updated BEFORE UPDATE ON coorte "
        "FOR EACH ROW EXECUTE FUNCTION atualizar_updated_at();"
    )

    # ==========================================================
    # (2) INSERT coorte: 1 linha por (curso_id, letra, semestre) DISTINCT de turma.
    #     gen_random_uuid() é VOLÁTIL: roda por-linha. Por isso o DISTINCT vem numa
    #     subquery — gerar o codigo no mesmo SELECT DISTINCT quebraria o colapso
    #     (cada linha viraria "distinta" e nasceria 1 coorte por turma).
    # ==========================================================
    op.execute(
        """
        INSERT INTO coorte (curso_id, letra, semestre, codigo_convite)
        SELECT d.curso_id,
               d.letra,
               d.semestre,
               'AUTO-' || replace(gen_random_uuid()::text, '-', '')
        FROM (SELECT DISTINCT curso_id, letra, semestre FROM turma) d;
        """
    )

    # ==========================================================
    # (3) turma.coorte_id: add nullable → backfill → SET NOT NULL → FK → índice
    # ==========================================================
    op.add_column("turma", sa.Column("coorte_id", UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE turma
        SET coorte_id = c.id
        FROM coorte c
        WHERE turma.curso_id = c.curso_id
          AND turma.letra = c.letra
          AND turma.semestre = c.semestre;
        """
    )
    op.alter_column("turma", "coorte_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_turma_coorte", "turma", "coorte", ["coorte_id"], ["id"], ondelete="RESTRICT"
    )
    op.create_index("idx_turma_coorte", "turma", ["coorte_id"])

    # ==========================================================
    # (4) GUARDA + repontagem da matricula (turma → coorte)
    #
    # Guarda: se algum aluno está matriculado em >1 turma da MESMA coorte, o
    # colapso para (coorte_id, aluno_telefone) violaria a nova UNIQUE. Aborta
    # ANTES de mutar, com mensagem clara — em vez de estourar a constraint no meio.
    # Roda depois do passo 3 (precisa de turma.coorte_id já populado).
    # ==========================================================
    op.execute(
        """
        DO $$
        DECLARE
            v_dup int;
        BEGIN
            SELECT count(*) INTO v_dup FROM (
                SELECT 1
                FROM matricula m
                JOIN turma t ON m.turma_id = t.id
                GROUP BY t.coorte_id, m.aluno_telefone
                HAVING count(*) > 1
            ) x;
            IF v_dup > 0 THEN
                RAISE EXCEPTION
                    'Abortado: % par(es) (coorte, aluno) com >1 matricula — colapsar matricula para (coorte_id, aluno_telefone) violaria a UNIQUE. Resolver duplicatas antes de aplicar a 0004.',
                    v_dup;
            END IF;
        END $$;
        """
    )

    # Repontar: add coorte_id nullable → backfill via turma → dropa UNIQUE e FK
    # antigas → dropa turma_id → SET NOT NULL → FK nova (CASCADE) → UNIQUE nova.
    op.add_column("matricula", sa.Column("coorte_id", UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE matricula m
        SET coorte_id = t.coorte_id
        FROM turma t
        WHERE m.turma_id = t.id;
        """
    )
    op.drop_constraint("uq_matricula_turma_aluno", "matricula", type_="unique")
    # FK criada inline e sem nome na 0002 → nome-padrão do Postgres:
    op.drop_constraint("matricula_turma_id_fkey", "matricula", type_="foreignkey")
    op.drop_column("matricula", "turma_id")
    op.alter_column("matricula", "coorte_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_matricula_coorte", "matricula", "coorte", ["coorte_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint(
        "uq_matricula_coorte_aluno", "matricula", ["coorte_id", "aluno_telefone"]
    )
    # NB: não criei idx_matricula_coorte — a UNIQUE (coorte_id, aluno_telefone)
    # já indexa coorte_id como coluna líder; índice dedicado seria redundante.
    # idx_matricula_aluno_telefone (em aluno_telefone) da 0002 NÃO é tocado.

    # ==========================================================
    # (5) duvida: add coorte_id NOT NULL + RELAXA turma_id para nullable
    #     (mantém a FK turma_id -> turma existente, CASCADE)
    # ==========================================================
    op.add_column("duvida", sa.Column("coorte_id", UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE duvida
        SET coorte_id = t.coorte_id
        FROM turma t
        WHERE duvida.turma_id = t.id;
        """
    )
    op.alter_column("duvida", "coorte_id", existing_type=UUID(as_uuid=True), nullable=False)
    op.create_foreign_key(
        "fk_duvida_coorte", "duvida", "coorte", ["coorte_id"], ["id"], ondelete="CASCADE"
    )
    op.alter_column("duvida", "turma_id", existing_type=UUID(as_uuid=True), nullable=True)
    op.create_index("idx_duvida_coorte", "duvida", ["coorte_id"])

    # (6) alembic_version → '0004': emitido pelo próprio Alembic, na mesma transação.


def downgrade() -> None:
    # Ordem inversa do upgrade. Duas guardas explícitas (matricula reversível só
    # no caso 1 turma por coorte; duvida re-NOT-NULL).

    # ----- reverter (5) duvida -----
    op.drop_index("idx_duvida_coorte", table_name="duvida")
    op.drop_constraint("fk_duvida_coorte", "duvida", type_="foreignkey")
    op.drop_column("duvida", "coorte_id")
    # re-NOT-NULL turma_id. Falha de propósito se houver duvida com turma_id NULL
    # criada pós-0004 (não dá pra reconstruir o vínculo no escuro).
    op.alter_column("duvida", "turma_id", existing_type=UUID(as_uuid=True), nullable=False)

    # ----- reverter (4) matricula (turma <- coorte) -----
    # GUARDA: reverter só é determinístico se cada coorte agrupa exatamente 1
    # turma. Com >1 turma por coorte não dá pra saber a turma_id original.
    op.execute(
        """
        DO $$
        DECLARE
            v_multi int;
        BEGIN
            SELECT count(*) INTO v_multi FROM (
                SELECT 1 FROM turma GROUP BY coorte_id HAVING count(*) > 1
            ) x;
            IF v_multi > 0 THEN
                RAISE EXCEPTION
                    'Downgrade abortado: % coorte(s) agrupam >1 turma — reverter matricula coorte->turma seria ambiguo. Reverter manualmente.',
                    v_multi;
            END IF;
        END $$;
        """
    )
    op.add_column("matricula", sa.Column("turma_id", UUID(as_uuid=True), nullable=True))
    op.execute(
        """
        UPDATE matricula m
        SET turma_id = t.id
        FROM turma t
        WHERE t.coorte_id = m.coorte_id;
        """
    )
    op.alter_column("matricula", "turma_id", existing_type=UUID(as_uuid=True), nullable=False)
    # reconstruir FK e UNIQUE antigas (nomes idênticos ao estado 0003)
    op.create_foreign_key(
        "matricula_turma_id_fkey", "matricula", "turma", ["turma_id"], ["id"], ondelete="CASCADE"
    )
    op.create_unique_constraint(
        "uq_matricula_turma_aluno", "matricula", ["turma_id", "aluno_telefone"]
    )
    # remover o que a 0004 adicionou
    op.drop_constraint("uq_matricula_coorte_aluno", "matricula", type_="unique")
    op.drop_constraint("fk_matricula_coorte", "matricula", type_="foreignkey")
    op.drop_column("matricula", "coorte_id")

    # ----- reverter (3) turma -----
    op.drop_index("idx_turma_coorte", table_name="turma")
    op.drop_constraint("fk_turma_coorte", "turma", type_="foreignkey")
    op.drop_column("turma", "coorte_id")

    # ----- reverter (1)/(2) coorte -----
    # DROP TABLE leva o trigger trg_coorte_updated junto.
    op.drop_table("coorte")

    # alembic_version → '0003': emitido pelo próprio Alembic, na mesma transação.
