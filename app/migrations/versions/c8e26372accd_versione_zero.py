"""versione zero

Revision ID: c8e26372accd
Revises: 
Schema completo di Racoonix (gestionale autonomo, senza cassa).

"""
from alembic import op
import sqlalchemy as sa


# revision identifiers, used by Alembic.
revision = 'c8e26372accd'
down_revision = None
branch_labels = None
depends_on = None


def upgrade():
    # Generata da Alembic a partire dai modelli e revisionata.
    op.create_table('categorie',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=50), nullable=False),
    sa.Column('attiva', sa.Boolean(), nullable=False),
    sa.Column('richiede_scadenza', sa.Boolean(), nullable=False),
    sa.Column('giorni_freschezza', sa.Integer(), nullable=True),
    sa.Column('sconto1_giorni', sa.Integer(), nullable=False),
    sa.Column('sconto1_perc', sa.Integer(), nullable=False),
    sa.Column('sconto2_giorni', sa.Integer(), nullable=False),
    sa.Column('sconto2_perc', sa.Integer(), nullable=False),
    sa.CheckConstraint('giorni_freschezza IS NULL OR giorni_freschezza > 0', name='ck_cat_freschezza'),
    sa.CheckConstraint('sconto1_giorni >= 0 AND sconto2_giorni >= 0', name='ck_cat_sconto_giorni'),
    sa.CheckConstraint('sconto1_perc BETWEEN 0 AND 90 AND sconto2_perc BETWEEN 0 AND 90', name='ck_cat_sconto_perc'),
    sa.CheckConstraint('sconto2_giorni <= sconto1_giorni', name='ck_cat_sconto_ordine'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('fornitori',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('ragione_sociale', sa.String(length=120), nullable=False),
    sa.Column('partita_iva', sa.String(length=11), nullable=True),
    sa.Column('telefono', sa.String(length=30), nullable=True),
    sa.Column('email', sa.String(length=120), nullable=True),
    sa.Column('giorni_ordine', sa.String(length=7), nullable=True),
    sa.Column('attivo', sa.Boolean(), nullable=False),
    sa.CheckConstraint("giorni_ordine IS NULL OR giorni_ordine ~ '^[0-6]{1,7}$'", name='ck_fornitore_giorni'),
    sa.CheckConstraint("partita_iva IS NULL OR partita_iva ~ '^[0-9]{11}$'", name='ck_fornitore_piva'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('partita_iva'),
    sa.UniqueConstraint('ragione_sociale')
    )
    op.create_table('impostazioni',
    sa.Column('chiave', sa.String(length=50), nullable=False),
    sa.Column('valore', sa.String(length=255), nullable=False),
    sa.Column('aggiornata_il', sa.DateTime(timezone=True), nullable=False),
    sa.PrimaryKeyConstraint('chiave')
    )
    op.create_table('ruoli',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=30), nullable=False),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('nome')
    )
    op.create_table('utenti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('username', sa.String(length=40), nullable=False),
    sa.Column('password_hash', sa.String(length=255), nullable=False),
    sa.Column('attivo', sa.Boolean(), nullable=False),
    sa.Column('eliminato', sa.Boolean(), nullable=False),
    sa.Column('deve_cambiare_password', sa.Boolean(), nullable=False),
    sa.Column('tentativi_falliti', sa.Integer(), nullable=False),
    sa.Column('bloccato_fino', sa.DateTime(timezone=True), nullable=True),
    sa.Column('tema', sa.String(length=10), nullable=False),
    sa.Column('token_sessione', sa.String(length=64), nullable=True),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("tema IN ('chiaro','scuro')", name='ck_utente_tema'),
    sa.CheckConstraint('tentativi_falliti >= 0', name='ck_utente_tentativi'),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('username')
    )
    op.create_table('audit_log',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utente_id', sa.Integer(), nullable=True),
    sa.Column('azione', sa.String(length=50), nullable=False),
    sa.Column('dettaglio', sa.Text(), nullable=True),
    sa.Column('ip', sa.String(length=45), nullable=True),
    sa.Column('data_ora', sa.DateTime(timezone=True), nullable=False),
    sa.ForeignKeyConstraint(['utente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('dispositivi_accesso',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('utente_id', sa.Integer(), nullable=False),
    sa.Column('token_hash', sa.String(length=64), nullable=False),
    sa.Column('descrizione', sa.String(length=80), nullable=False),
    sa.Column('nome', sa.String(length=60), nullable=True),
    sa.Column('stato', sa.String(length=12), nullable=False),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('approvato_da', sa.Integer(), nullable=True),
    sa.Column('approvato_il', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ultimo_uso', sa.DateTime(timezone=True), nullable=True),
    sa.Column('ultimo_ip', sa.String(length=45), nullable=True),
    sa.CheckConstraint("stato IN ('in_attesa','approvato','revocato')", name='ck_dispaccesso_stato'),
    sa.ForeignKeyConstraint(['approvato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['utente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('utente_id', 'token_hash', name='uq_dispaccesso')
    )
    with op.batch_alter_table('dispositivi_accesso', schema=None) as batch_op:
        batch_op.create_index('ix_dispaccesso_token', ['token_hash'], unique=False)

    op.create_table('sottocategorie',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('nome', sa.String(length=50), nullable=False),
    sa.Column('attiva', sa.Boolean(), nullable=False),
    sa.ForeignKeyConstraint(['categoria_id'], ['categorie.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('categoria_id', 'nome', name='uq_sottocategoria')
    )
    op.create_table('utenti_ruoli',
    sa.Column('utente_id', sa.Integer(), nullable=False),
    sa.Column('ruolo_id', sa.Integer(), nullable=False),
    sa.ForeignKeyConstraint(['ruolo_id'], ['ruoli.id'], ),
    sa.ForeignKeyConstraint(['utente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('utente_id', 'ruolo_id')
    )
    op.create_table('prodotti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('gtin', sa.String(length=14), nullable=True),
    sa.Column('codice_bilancia', sa.String(length=5), nullable=True),
    sa.Column('nome', sa.String(length=120), nullable=False),
    sa.Column('marca', sa.String(length=60), nullable=True),
    sa.Column('categoria_id', sa.Integer(), nullable=False),
    sa.Column('sottocategoria_id', sa.Integer(), nullable=True),
    sa.Column('fornitore_id', sa.Integer(), nullable=True),
    sa.Column('unita', sa.String(length=5), nullable=False),
    sa.Column('formato_pezzi', sa.Integer(), nullable=False),
    sa.Column('formato_quantita', sa.Integer(), nullable=True),
    sa.Column('formato_unita', sa.String(length=2), nullable=True),
    sa.Column('prezzo_centesimi', sa.Integer(), nullable=True),
    sa.Column('in_esaurimento', sa.Boolean(), nullable=False),
    sa.Column('soglia_riordino', sa.Integer(), nullable=True),
    sa.Column('ultima_conta_il', sa.DateTime(timezone=True), nullable=True),
    sa.Column('giorni_preavviso', sa.Integer(), nullable=False),
    sa.Column('sconto1_giorni', sa.Integer(), nullable=True),
    sa.Column('sconto1_perc', sa.Integer(), nullable=True),
    sa.Column('sconto2_giorni', sa.Integer(), nullable=True),
    sa.Column('sconto2_perc', sa.Integer(), nullable=True),
    sa.Column('stato', sa.String(length=20), nullable=False),
    sa.Column('creato_da', sa.Integer(), nullable=True),
    sa.Column('approvato_da', sa.Integer(), nullable=True),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.CheckConstraint("codice_bilancia IS NULL OR codice_bilancia ~ '^[0-9]{5}$'", name='ck_prodotto_bilancia'),
    sa.CheckConstraint("formato_unita IS NULL OR formato_unita IN ('g','ml','pz')", name='ck_prodotto_formato_u'),
    sa.CheckConstraint("gtin IS NULL OR gtin ~ '^[0-9]{14}$'", name='ck_prodotto_gtin'),
    sa.CheckConstraint("stato IN ('in_attesa','attivo','rimosso')", name='ck_prodotto_stato'),
    sa.CheckConstraint("unita IN ('pezzo','kg')", name='ck_prodotto_unita'),
    sa.CheckConstraint('(formato_quantita IS NULL) = (formato_unita IS NULL)', name='ck_prodotto_formato'),
    sa.CheckConstraint('(sconto1_giorni IS NULL OR sconto1_giorni >= 0) AND (sconto2_giorni IS NULL OR sconto2_giorni >= 0)', name='ck_prodotto_sconto_giorni'),
    sa.CheckConstraint('(sconto1_perc IS NULL OR sconto1_perc BETWEEN 0 AND 90) AND (sconto2_perc IS NULL OR sconto2_perc BETWEEN 0 AND 90)', name='ck_prodotto_sconto_perc'),
    sa.CheckConstraint('formato_pezzi >= 1', name='ck_prodotto_pezzi'),
    sa.CheckConstraint('formato_quantita IS NULL OR formato_quantita > 0', name='ck_prodotto_formato_q'),
    sa.CheckConstraint('giorni_preavviso >= 0', name='ck_prodotto_preavviso'),
    sa.CheckConstraint('gtin IS NOT NULL OR codice_bilancia IS NOT NULL', name='ck_prodotto_codice'),
    sa.CheckConstraint('prezzo_centesimi IS NULL OR prezzo_centesimi >= 0', name='ck_prodotto_prezzo'),
    sa.CheckConstraint('soglia_riordino IS NULL OR soglia_riordino >= 0', name='ck_prodotto_riordino'),
    sa.ForeignKeyConstraint(['approvato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['categoria_id'], ['categorie.id'], ),
    sa.ForeignKeyConstraint(['creato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['fornitore_id'], ['fornitori.id'], ),
    sa.ForeignKeyConstraint(['sottocategoria_id'], ['sottocategorie.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('codice_bilancia'),
    sa.UniqueConstraint('gtin')
    )
    op.create_table('codici_aggiuntivi',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prodotto_id', sa.Integer(), nullable=False),
    sa.Column('gtin', sa.String(length=14), nullable=False),
    sa.Column('descrizione', sa.String(length=60), nullable=True),
    sa.CheckConstraint("gtin ~ '^[0-9]{14}$'", name='ck_codice_gtin'),
    sa.ForeignKeyConstraint(['prodotto_id'], ['prodotti.id'], ),
    sa.PrimaryKeyConstraint('id'),
    sa.UniqueConstraint('gtin')
    )
    op.create_table('lotti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prodotto_id', sa.Integer(), nullable=False),
    sa.Column('codice_lotto', sa.String(length=20), nullable=True),
    sa.Column('data_scadenza', sa.Date(), nullable=True),
    sa.Column('qta_esposta', sa.Integer(), nullable=False),
    sa.Column('qta_magazzino', sa.Integer(), nullable=False),
    sa.Column('data_carico', sa.DateTime(timezone=True), nullable=False),
    sa.Column('caricato_da', sa.Integer(), nullable=True),
    sa.CheckConstraint('qta_esposta >= 0', name='ck_lotto_esposta'),
    sa.CheckConstraint('qta_magazzino >= 0', name='ck_lotto_magazzino'),
    sa.ForeignKeyConstraint(['caricato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['prodotto_id'], ['prodotti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('riordini',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('prodotto_id', sa.Integer(), nullable=False),
    sa.Column('quantita', sa.Integer(), nullable=True),
    sa.Column('stato', sa.String(length=12), nullable=False),
    sa.Column('origine', sa.String(length=12), nullable=False),
    sa.Column('segnalato_da', sa.Integer(), nullable=True),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('ordinato_da', sa.Integer(), nullable=True),
    sa.Column('ordinato_il', sa.DateTime(timezone=True), nullable=True),
    sa.Column('chiuso_il', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("origine IN ('segnalazione','soglia')", name='ck_riordino_origine'),
    sa.CheckConstraint("stato IN ('da_ordinare','ordinato','arrivato','annullato')", name='ck_riordino_stato'),
    sa.CheckConstraint('quantita IS NULL OR quantita > 0', name='ck_riordino_quantita'),
    sa.ForeignKeyConstraint(['ordinato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['prodotto_id'], ['prodotti.id'], ),
    sa.ForeignKeyConstraint(['segnalato_da'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('riordini', schema=None) as batch_op:
        batch_op.create_index('uq_riordino_aperto', ['prodotto_id'], unique=True, postgresql_where=sa.text("stato IN ('da_ordinare','ordinato')"))

    op.create_table('notifiche',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('tipo', sa.String(length=20), nullable=False),
    sa.Column('prodotto_id', sa.Integer(), nullable=True),
    sa.Column('lotto_id', sa.Integer(), nullable=True),
    sa.Column('utente_id', sa.Integer(), nullable=True),
    sa.Column('ruolo_destinatario', sa.String(length=30), nullable=False),
    sa.Column('stato', sa.String(length=10), nullable=False),
    sa.Column('nota', sa.String(length=255), nullable=True),
    sa.Column('creata_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('chiusa_da', sa.Integer(), nullable=True),
    sa.Column('chiusa_il', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("ruolo_destinatario IN ('admin','magazziniere','dipendente')", name='ck_notifica_ruolo'),
    sa.CheckConstraint("stato IN ('aperta','chiusa')", name='ck_notifica_stato'),
    sa.CheckConstraint("tipo IN ('riempi','in_scadenza','da_rimuovere','da_approvare','sconto','freschezza','reset_password','dispositivo')", name='ck_notifica_tipo'),
    sa.CheckConstraint('prodotto_id IS NOT NULL OR utente_id IS NOT NULL', name='ck_notifica_soggetto'),
    sa.ForeignKeyConstraint(['chiusa_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['lotto_id'], ['lotti.id'], ),
    sa.ForeignKeyConstraint(['prodotto_id'], ['prodotti.id'], ),
    sa.ForeignKeyConstraint(['utente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('notifiche', schema=None) as batch_op:
        batch_op.create_index('uq_notifica_aperta', ['tipo', 'prodotto_id', 'lotto_id', 'utente_id', 'ruolo_destinatario'], unique=True, postgresql_where=sa.text("stato = 'aperta'"), postgresql_nulls_not_distinct=True)

    op.create_table('scarti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lotto_id', sa.Integer(), nullable=False),
    sa.Column('quantita', sa.Integer(), nullable=False),
    sa.Column('motivo', sa.String(length=20), nullable=False),
    sa.Column('data', sa.DateTime(timezone=True), nullable=False),
    sa.Column('utente_id', sa.Integer(), nullable=False),
    sa.CheckConstraint("motivo IN ('scaduto','non_conforme','deteriorato')", name='ck_scarto_motivo'),
    sa.CheckConstraint('quantita > 0', name='ck_scarto_quantita'),
    sa.ForeignKeyConstraint(['lotto_id'], ['lotti.id'], ),
    sa.ForeignKeyConstraint(['utente_id'], ['utenti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    op.create_table('sconti',
    sa.Column('id', sa.Integer(), nullable=False),
    sa.Column('lotto_id', sa.Integer(), nullable=False),
    sa.Column('perc', sa.Integer(), nullable=False),
    sa.Column('quantita', sa.Integer(), nullable=False),
    sa.Column('origine', sa.String(length=12), nullable=False),
    sa.Column('attivo', sa.Boolean(), nullable=False),
    sa.Column('creato_da', sa.Integer(), nullable=True),
    sa.Column('creato_il', sa.DateTime(timezone=True), nullable=False),
    sa.Column('chiuso_il', sa.DateTime(timezone=True), nullable=True),
    sa.CheckConstraint("origine IN ('manuale','programmato')", name='ck_sconto_origine'),
    sa.CheckConstraint('perc BETWEEN 1 AND 90', name='ck_sconto_perc'),
    sa.CheckConstraint('quantita > 0', name='ck_sconto_quantita'),
    sa.ForeignKeyConstraint(['creato_da'], ['utenti.id'], ),
    sa.ForeignKeyConstraint(['lotto_id'], ['lotti.id'], ),
    sa.PrimaryKeyConstraint('id')
    )
    with op.batch_alter_table('sconti', schema=None) as batch_op:
        batch_op.create_index('uq_sconto_attivo', ['lotto_id'], unique=True, postgresql_where=sa.text('attivo'))



def downgrade():
    # Generata da Alembic a partire dai modelli e revisionata.
    with op.batch_alter_table('sconti', schema=None) as batch_op:
        batch_op.drop_index('uq_sconto_attivo', postgresql_where=sa.text('attivo'))

    op.drop_table('sconti')
    op.drop_table('scarti')
    with op.batch_alter_table('notifiche', schema=None) as batch_op:
        batch_op.drop_index('uq_notifica_aperta', postgresql_where=sa.text("stato = 'aperta'"), postgresql_nulls_not_distinct=True)

    op.drop_table('notifiche')
    with op.batch_alter_table('riordini', schema=None) as batch_op:
        batch_op.drop_index('uq_riordino_aperto', postgresql_where=sa.text("stato IN ('da_ordinare','ordinato')"))

    op.drop_table('riordini')
    op.drop_table('lotti')
    op.drop_table('codici_aggiuntivi')
    op.drop_table('prodotti')
    op.drop_table('utenti_ruoli')
    op.drop_table('sottocategorie')
    with op.batch_alter_table('dispositivi_accesso', schema=None) as batch_op:
        batch_op.drop_index('ix_dispaccesso_token')

    op.drop_table('dispositivi_accesso')
    op.drop_table('audit_log')
    op.drop_table('utenti')
    op.drop_table('ruoli')
    op.drop_table('impostazioni')
    op.drop_table('fornitori')
    op.drop_table('categorie')
