"""avviso all'admin per i prodotti da ordinare

Revision ID: e5b7c3d9a1f2
Revises: d4a9e1f7c2b8
"""
from alembic import op

revision = "e5b7c3d9a1f2"
down_revision = "d4a9e1f7c2b8"
branch_labels = None
depends_on = None

PRIMA = "'riempi','in_scadenza','da_rimuovere','da_approvare','sconto','freschezza','reset_password','dispositivo'"


def upgrade():
    op.execute("ALTER TABLE notifiche DROP CONSTRAINT IF EXISTS ck_notifica_tipo")
    op.execute(f"ALTER TABLE notifiche ADD CONSTRAINT ck_notifica_tipo CHECK (tipo IN ({PRIMA},'da_ordinare'))")


def downgrade():
    op.execute("DELETE FROM notifiche WHERE tipo = 'da_ordinare'")
    op.execute("ALTER TABLE notifiche DROP CONSTRAINT IF EXISTS ck_notifica_tipo")
    op.execute(f"ALTER TABLE notifiche ADD CONSTRAINT ck_notifica_tipo CHECK (tipo IN ({PRIMA}))")
