"""0003: prosa_acao em relatorio + UNIQUE parcial em mensagem.whatsapp_message_id

Revision ID: 0003
Revises: 0002
Create Date: 2026-06-18
"""
from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa

revision: str = "0003"
down_revision: Union[str, None] = "0002"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # (a) prosa de sugestão de ação gerada pelo Sonnet (CC #6)
    op.add_column("relatorio", sa.Column("prosa_acao", sa.Text(), nullable=True))

    # (b) dedup definitivo de webhook reenviado: UNIQUE parcial substitui o
    # índice normal criado pela 0002. O índice parcial também serve de lookup,
    # então não há redundância — é troca, não adição.
    op.drop_index("idx_mensagem_whatsapp_id", table_name="mensagem")
    op.create_index(
        "idx_mensagem_whatsapp_id",
        "mensagem",
        ["whatsapp_message_id"],
        unique=True,
        postgresql_where=sa.text("whatsapp_message_id IS NOT NULL"),
    )


def downgrade() -> None:
    # Reverte exatamente: UNIQUE parcial volta a ser índice normal; coluna sai.
    op.drop_index("idx_mensagem_whatsapp_id", table_name="mensagem")
    op.create_index("idx_mensagem_whatsapp_id", "mensagem", ["whatsapp_message_id"])
    op.drop_column("relatorio", "prosa_acao")
