"""lingua scelta da ogni utente

Revision ID: d4a9e1f7c2b8
Revises: c8e26372accd
"""
from alembic import op
import sqlalchemy as sa

revision = "d4a9e1f7c2b8"
down_revision = "c8e26372accd"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("utenti", sa.Column("lingua", sa.String(5), nullable=True))
    op.execute("ALTER TABLE utenti ADD CONSTRAINT ck_utente_lingua CHECK (lingua IS NULL OR lingua IN ('it','en'))")


def downgrade():
    op.execute("ALTER TABLE utenti DROP CONSTRAINT IF EXISTS ck_utente_lingua")
    op.drop_column("utenti", "lingua")
