"""giorni d'ordine dei fornitori

Revision ID: c3f1a8e5b2d7
Revises: b7e2c4a91d30
"""
from alembic import op
import sqlalchemy as sa

revision = "c3f1a8e5b2d7"
down_revision = "b7e2c4a91d30"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("fornitori", sa.Column("giorni_ordine", sa.String(7), nullable=True))
    op.execute("ALTER TABLE fornitori ADD CONSTRAINT ck_fornitore_giorni "
               "CHECK (giorni_ordine IS NULL OR giorni_ordine ~ '^[0-6]{1,7}$')")


def downgrade():
    op.execute("ALTER TABLE fornitori DROP CONSTRAINT IF EXISTS ck_fornitore_giorni")
    op.drop_column("fornitori", "giorni_ordine")
