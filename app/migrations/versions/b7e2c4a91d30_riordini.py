"""riordini, soglia di riordino, ultima conta; via la notifica esaurito

Revision ID: b7e2c4a91d30
Revises: 9c9bf7ad15d4
"""
from alembic import op
import sqlalchemy as sa

revision = "b7e2c4a91d30"
down_revision = "9c9bf7ad15d4"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("prodotti", sa.Column("soglia_riordino", sa.Integer(), nullable=True))
    op.add_column("prodotti", sa.Column("ultima_conta_il", sa.DateTime(timezone=True), nullable=True))
    op.execute("ALTER TABLE prodotti ADD CONSTRAINT ck_prodotto_riordino "
               "CHECK (soglia_riordino IS NULL OR soglia_riordino >= 0)")
    op.create_table(
        "riordini",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("prodotto_id", sa.Integer(), sa.ForeignKey("prodotti.id"), nullable=False),
        sa.Column("quantita", sa.Integer()),
        sa.Column("stato", sa.String(12), nullable=False),
        sa.Column("origine", sa.String(12), nullable=False),
        sa.Column("segnalato_da", sa.Integer(), sa.ForeignKey("utenti.id")),
        sa.Column("creato_il", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ordinato_da", sa.Integer(), sa.ForeignKey("utenti.id")),
        sa.Column("ordinato_il", sa.DateTime(timezone=True)),
        sa.Column("chiuso_il", sa.DateTime(timezone=True)),
        sa.CheckConstraint("stato IN ('da_ordinare','ordinato','arrivato','annullato')", name="ck_riordino_stato"),
        sa.CheckConstraint("origine IN ('segnalazione','soglia')", name="ck_riordino_origine"),
        sa.CheckConstraint("quantita IS NULL OR quantita > 0", name="ck_riordino_quantita"),
    )
    op.create_index("uq_riordino_aperto", "riordini", ["prodotto_id"], unique=True,
                    postgresql_where=sa.text("stato IN ('da_ordinare','ordinato')"))
    op.execute("DELETE FROM notifiche WHERE tipo = 'esaurito'")
    op.execute("ALTER TABLE notifiche DROP CONSTRAINT IF EXISTS ck_notifica_tipo")
    op.execute("ALTER TABLE notifiche ADD CONSTRAINT ck_notifica_tipo CHECK (tipo IN ('riempi','in_scadenza','da_rimuovere','da_approvare','sconto','freschezza','reset_password','dispositivo'))")


def downgrade():
    op.execute("ALTER TABLE notifiche DROP CONSTRAINT IF EXISTS ck_notifica_tipo")
    op.execute("ALTER TABLE notifiche ADD CONSTRAINT ck_notifica_tipo CHECK (tipo IN ('riempi','esaurito','in_scadenza','da_rimuovere','da_approvare','sconto','freschezza','reset_password','dispositivo'))")
    op.drop_index("uq_riordino_aperto", table_name="riordini")
    op.drop_table("riordini")
    op.execute("ALTER TABLE prodotti DROP CONSTRAINT IF EXISTS ck_prodotto_riordino")
    op.drop_column("prodotti", "ultima_conta_il")
    op.drop_column("prodotti", "soglia_riordino")
