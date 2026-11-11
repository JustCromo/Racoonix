"""codice di benvenuto (QR per il primo accesso)

Revision ID: f6c8d2e4b7a1
Revises: e5b7c3d9a1f2
"""
from alembic import op
import sqlalchemy as sa

revision = "f6c8d2e4b7a1"
down_revision = "e5b7c3d9a1f2"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("utenti", sa.Column("benvenuto_hash", sa.String(64), nullable=True))
    op.add_column("utenti", sa.Column("benvenuto_scade", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("utenti", "benvenuto_scade")
    op.drop_column("utenti", "benvenuto_hash")
