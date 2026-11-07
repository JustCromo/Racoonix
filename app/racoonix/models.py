from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, text

from . import db


def adesso():
    return datetime.now(timezone.utc)


utenti_ruoli = db.Table(
    "utenti_ruoli",
    db.Column("utente_id", db.Integer, db.ForeignKey("utenti.id"), primary_key=True),
    db.Column("ruolo_id", db.Integer, db.ForeignKey("ruoli.id"), primary_key=True),
)


class Ruolo(db.Model):
    __tablename__ = "ruoli"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(30), unique=True, nullable=False)


class Utente(db.Model):
    __tablename__ = "utenti"
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(40), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    attivo = db.Column(db.Boolean, nullable=False, default=True)
    deve_cambiare_password = db.Column(db.Boolean, nullable=False, default=True)
    tentativi_falliti = db.Column(db.Integer, nullable=False, default=0)
    bloccato_fino = db.Column(db.DateTime(timezone=True))
    tema = db.Column(db.String(10), nullable=False, default="chiaro")
    token_sessione = db.Column(db.String(64))
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    ruoli = db.relationship("Ruolo", secondary=utenti_ruoli, lazy="selectin")

    __table_args__ = (
        CheckConstraint("tema IN ('chiaro','scuro')", name="ck_utente_tema"),
        CheckConstraint("tentativi_falliti >= 0", name="ck_utente_tentativi"),
    )

    def ha_ruolo(self, nome):
        return any(r.nome == nome for r in self.ruoli)


class Categoria(db.Model):
    __tablename__ = "categorie"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(50), unique=True, nullable=False)
    attiva = db.Column(db.Boolean, nullable=False, default=True)
    richiede_scadenza = db.Column(db.Boolean, nullable=False, default=True)
    giorni_freschezza = db.Column(db.Integer)
    sconto1_giorni = db.Column(db.Integer, nullable=False, default=0)
    sconto1_perc = db.Column(db.Integer, nullable=False, default=0)
    sconto2_giorni = db.Column(db.Integer, nullable=False, default=0)
    sconto2_perc = db.Column(db.Integer, nullable=False, default=0)

    __table_args__ = (
        CheckConstraint("giorni_freschezza IS NULL OR giorni_freschezza > 0", name="ck_cat_freschezza"),
        CheckConstraint("sconto1_giorni >= 0 AND sconto2_giorni >= 0", name="ck_cat_sconto_giorni"),
        CheckConstraint("sconto2_giorni <= sconto1_giorni", name="ck_cat_sconto_ordine"),
        CheckConstraint("sconto1_perc BETWEEN 0 AND 90 AND sconto2_perc BETWEEN 0 AND 90",
                        name="ck_cat_sconto_perc"),
    )


class Prodotto(db.Model):
    __tablename__ = "prodotti"
    id = db.Column(db.Integer, primary_key=True)
    gtin = db.Column(db.String(14), unique=True)
    codice_bilancia = db.Column(db.String(5), unique=True)
    nome = db.Column(db.String(120), nullable=False)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorie.id"), nullable=False)
    unita = db.Column(db.String(5), nullable=False, default="pezzo")
    prezzo_centesimi = db.Column(db.Integer)
    soglia_esposti = db.Column(db.Integer, nullable=False, default=5)
    giorni_preavviso = db.Column(db.Integer, nullable=False, default=3)
    giorni_validita = db.Column(db.Integer)
    sconto1_giorni = db.Column(db.Integer)
    sconto1_perc = db.Column(db.Integer)
    sconto2_giorni = db.Column(db.Integer)
    sconto2_perc = db.Column(db.Integer)
    stato = db.Column(db.String(20), nullable=False, default="in_attesa")
    nota_admin = db.Column(db.String(255))
    creato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    approvato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    categoria = db.relationship("Categoria")
    lotti = db.relationship("Lotto", back_populates="prodotto")

    __table_args__ = (
        CheckConstraint("stato IN ('in_attesa','da_correggere','attivo','rimosso')", name="ck_prodotto_stato"),
        CheckConstraint("unita IN ('pezzo','kg')", name="ck_prodotto_unita"),
        CheckConstraint("gtin IS NULL OR gtin ~ '^[0-9]{14}$'", name="ck_prodotto_gtin"),
        CheckConstraint("codice_bilancia IS NULL OR codice_bilancia ~ '^[0-9]{5}$'", name="ck_prodotto_bilancia"),
        CheckConstraint("gtin IS NOT NULL OR codice_bilancia IS NOT NULL", name="ck_prodotto_codice"),
        CheckConstraint("prezzo_centesimi IS NULL OR prezzo_centesimi >= 0", name="ck_prodotto_prezzo"),
        CheckConstraint("soglia_esposti >= 0 AND giorni_preavviso >= 0", name="ck_prodotto_soglie"),
        CheckConstraint("(sconto1_perc IS NULL OR sconto1_perc BETWEEN 0 AND 90) AND "
                        "(sconto2_perc IS NULL OR sconto2_perc BETWEEN 0 AND 90)", name="ck_prodotto_sconto_perc"),
        CheckConstraint("(sconto1_giorni IS NULL OR sconto1_giorni >= 0) AND "
                        "(sconto2_giorni IS NULL OR sconto2_giorni >= 0)", name="ck_prodotto_sconto_giorni"),
    )

    def fasce_sconto(self):
        """Fasce effettive: valori del prodotto se presenti, altrimenti della categoria."""
        c = self.categoria

        def scegli(proprio, ereditato):
            return proprio if proprio is not None else ereditato

        return [
            (scegli(self.sconto1_giorni, c.sconto1_giorni), scegli(self.sconto1_perc, c.sconto1_perc)),
            (scegli(self.sconto2_giorni, c.sconto2_giorni), scegli(self.sconto2_perc, c.sconto2_perc)),
        ]


class Lotto(db.Model):
    __tablename__ = "lotti"
    id = db.Column(db.Integer, primary_key=True)
    prodotto_id = db.Column(db.Integer, db.ForeignKey("prodotti.id"), nullable=False)
    codice_lotto = db.Column(db.String(20))
    data_scadenza = db.Column(db.Date)
    data_confezionamento = db.Column(db.Date)
    lotto_origine_id = db.Column(db.Integer, db.ForeignKey("lotti.id"))
    codice_etichetta = db.Column(db.String(13))
    qta_esposta = db.Column(db.Integer, nullable=False, default=0)
    qta_magazzino = db.Column(db.Integer, nullable=False, default=0)
    bollino_sconto = db.Column(db.Boolean, nullable=False, default=False)
    data_carico = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    caricato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    prodotto = db.relationship("Prodotto", back_populates="lotti")

    __table_args__ = (
        CheckConstraint("qta_esposta >= 0", name="ck_lotto_esposta"),
        CheckConstraint("qta_magazzino >= 0", name="ck_lotto_magazzino"),
    )


class Vendita(db.Model):
    __tablename__ = "vendite"
    id = db.Column(db.Integer, primary_key=True)
    data_ora = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"), nullable=False)
    totale_centesimi = db.Column(db.Integer, nullable=False, default=0)
    righe = db.relationship("RigaVendita", back_populates="vendita")

    __table_args__ = (CheckConstraint("totale_centesimi >= 0", name="ck_vendita_totale"),)


class RigaVendita(db.Model):
    __tablename__ = "righe_vendita"
    id = db.Column(db.Integer, primary_key=True)
    vendita_id = db.Column(db.Integer, db.ForeignKey("vendite.id"), nullable=False)
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"), nullable=False)
    quantita = db.Column(db.Integer, nullable=False)
    prezzo_unitario_centesimi = db.Column(db.Integer, nullable=False)
    sconto_perc = db.Column(db.Integer, nullable=False, default=0)
    totale_centesimi = db.Column(db.Integer, nullable=False)
    vendita = db.relationship("Vendita", back_populates="righe")

    __table_args__ = (
        CheckConstraint("quantita > 0", name="ck_riga_quantita"),
        CheckConstraint("prezzo_unitario_centesimi >= 0 AND totale_centesimi >= 0", name="ck_riga_importi"),
        CheckConstraint("sconto_perc BETWEEN 0 AND 90", name="ck_riga_sconto"),
    )


class Scarto(db.Model):
    __tablename__ = "scarti"
    id = db.Column(db.Integer, primary_key=True)
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"), nullable=False)
    quantita = db.Column(db.Integer, nullable=False)
    motivo = db.Column(db.String(20), nullable=False)
    data = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"), nullable=False)

    __table_args__ = (
        CheckConstraint("quantita > 0", name="ck_scarto_quantita"),
        CheckConstraint("motivo IN ('scaduto','non_conforme','deteriorato')", name="ck_scarto_motivo"),
    )


class Notifica(db.Model):
    __tablename__ = "notifiche"
    id = db.Column(db.Integer, primary_key=True)
    tipo = db.Column(db.String(20), nullable=False)
    prodotto_id = db.Column(db.Integer, db.ForeignKey("prodotti.id"), nullable=False)
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"))
    ruolo_destinatario = db.Column(db.String(30), nullable=False)
    stato = db.Column(db.String(10), nullable=False, default="aperta")
    nota = db.Column(db.String(255))
    creata_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    chiusa_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    chiusa_il = db.Column(db.DateTime(timezone=True))

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('riempi','esaurito','in_scadenza','da_rimuovere','da_approvare',"
            "'da_correggere','sconto','freschezza')",
            name="ck_notifica_tipo",
        ),
        CheckConstraint("ruolo_destinatario IN ('admin','magazziniere','dipendente')", name="ck_notifica_ruolo"),
        CheckConstraint("stato IN ('aperta','chiusa')", name="ck_notifica_stato"),
        Index(
            "uq_notifica_aperta",
            "tipo", "prodotto_id", "lotto_id", "ruolo_destinatario",
            unique=True,
            postgresql_where=text("stato = 'aperta'"),
            postgresql_nulls_not_distinct=True,
        ),
    )


class AuditLog(db.Model):
    __tablename__ = "audit_log"
    id = db.Column(db.Integer, primary_key=True)
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    azione = db.Column(db.String(50), nullable=False)
    dettaglio = db.Column(db.Text)
    ip = db.Column(db.String(45))
    data_ora = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
