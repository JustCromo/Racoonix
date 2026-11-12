"""indirizzi bloccati dall'admin

Revision ID: a1b2c3d4e5f6
Revises: f6c8d2e4b7a1
"""
from alembic import op
import sqlalchemy as sa

revision = "a1b2c3d4e5f6"
down_revision = "f6c8d2e4b7a1"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "indirizzi_bloccati",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("rete", sa.String(50), nullable=False, unique=True),
        sa.Column("stato", sa.String(10), nullable=False),
        sa.Column("motivo", sa.String(200)),
        sa.Column("creato_da", sa.Integer(), sa.ForeignKey("utenti.id", ondelete="SET NULL")),
        sa.Column("creato_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("scade_il", sa.DateTime(timezone=True)),
        sa.CheckConstraint("stato IN ('bloccato','ignorato')", name="ck_indirizzo_stato"),
    )


def downgrade():
    op.drop_table("indirizzi_bloccati")
