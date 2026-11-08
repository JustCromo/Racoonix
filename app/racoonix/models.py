from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, Index, UniqueConstraint, text

from . import db
from .formato import misura


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
    eliminato = db.Column(db.Boolean, nullable=False, default=False)
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
    sottocategorie = db.relationship("Sottocategoria", back_populates="categoria",
                                     order_by="Sottocategoria.nome")

    __table_args__ = (
        CheckConstraint("giorni_freschezza IS NULL OR giorni_freschezza > 0", name="ck_cat_freschezza"),
        CheckConstraint("sconto1_giorni >= 0 AND sconto2_giorni >= 0", name="ck_cat_sconto_giorni"),
        CheckConstraint("sconto2_giorni <= sconto1_giorni", name="ck_cat_sconto_ordine"),
        CheckConstraint("sconto1_perc BETWEEN 0 AND 90 AND sconto2_perc BETWEEN 0 AND 90",
                        name="ck_cat_sconto_perc"),
    )


class Sottocategoria(db.Model):
    __tablename__ = "sottocategorie"
    id = db.Column(db.Integer, primary_key=True)
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorie.id"), nullable=False)
    nome = db.Column(db.String(50), nullable=False)
    attiva = db.Column(db.Boolean, nullable=False, default=True)
    categoria = db.relationship("Categoria", back_populates="sottocategorie")

    __table_args__ = (UniqueConstraint("categoria_id", "nome", name="uq_sottocategoria"),)


class Fornitore(db.Model):
    __tablename__ = "fornitori"
    id = db.Column(db.Integer, primary_key=True)
    ragione_sociale = db.Column(db.String(120), unique=True, nullable=False)
    partita_iva = db.Column(db.String(11), unique=True)
    telefono = db.Column(db.String(30))
    email = db.Column(db.String(120))
    attivo = db.Column(db.Boolean, nullable=False, default=True)

    __table_args__ = (
        CheckConstraint("partita_iva IS NULL OR partita_iva ~ '^[0-9]{11}$'", name="ck_fornitore_piva"),
    )


class Prodotto(db.Model):
    __tablename__ = "prodotti"
    id = db.Column(db.Integer, primary_key=True)
    gtin = db.Column(db.String(14), unique=True)
    codice_bilancia = db.Column(db.String(5), unique=True)
    nome = db.Column(db.String(120), nullable=False)
    marca = db.Column(db.String(60))
    categoria_id = db.Column(db.Integer, db.ForeignKey("categorie.id"), nullable=False)
    sottocategoria_id = db.Column(db.Integer, db.ForeignKey("sottocategorie.id"))
    fornitore_id = db.Column(db.Integer, db.ForeignKey("fornitori.id"))
    unita = db.Column(db.String(5), nullable=False, default="pezzo")
    formato_pezzi = db.Column(db.Integer, nullable=False, default=1)
    formato_quantita = db.Column(db.Integer)
    formato_unita = db.Column(db.String(2))
    prezzo_centesimi = db.Column(db.Integer)
    aliquota_iva = db.Column(db.Integer, nullable=False, default=22)
    in_esaurimento = db.Column(db.Boolean, nullable=False, default=False)
    soglia_esposti = db.Column(db.Integer, nullable=False, default=5)
    giorni_preavviso = db.Column(db.Integer, nullable=False, default=3)
    giorni_validita = db.Column(db.Integer)
    sconto1_giorni = db.Column(db.Integer)
    sconto1_perc = db.Column(db.Integer)
    sconto2_giorni = db.Column(db.Integer)
    sconto2_perc = db.Column(db.Integer)
    stato = db.Column(db.String(20), nullable=False, default="in_attesa")
    creato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    approvato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    categoria = db.relationship("Categoria")
    sottocategoria = db.relationship("Sottocategoria")
    fornitore = db.relationship("Fornitore")
    lotti = db.relationship("Lotto", back_populates="prodotto")
    codici_aggiuntivi = db.relationship("CodiceAggiuntivo", back_populates="prodotto",
                                        cascade="all, delete-orphan")

    __table_args__ = (
        CheckConstraint("stato IN ('in_attesa','attivo','rimosso')", name="ck_prodotto_stato"),
        CheckConstraint("unita IN ('pezzo','kg')", name="ck_prodotto_unita"),
        CheckConstraint("gtin IS NULL OR gtin ~ '^[0-9]{14}$'", name="ck_prodotto_gtin"),
        CheckConstraint("codice_bilancia IS NULL OR codice_bilancia ~ '^[0-9]{5}$'", name="ck_prodotto_bilancia"),
        CheckConstraint("gtin IS NOT NULL OR codice_bilancia IS NOT NULL", name="ck_prodotto_codice"),
        CheckConstraint("prezzo_centesimi IS NULL OR prezzo_centesimi >= 0", name="ck_prodotto_prezzo"),
        CheckConstraint("aliquota_iva IN (4, 5, 10, 22)", name="ck_prodotto_iva"),
        CheckConstraint("formato_pezzi >= 1", name="ck_prodotto_pezzi"),
        CheckConstraint("formato_quantita IS NULL OR formato_quantita > 0", name="ck_prodotto_formato_q"),
        CheckConstraint("formato_unita IS NULL OR formato_unita IN ('g','ml','pz')", name="ck_prodotto_formato_u"),
        CheckConstraint("(formato_quantita IS NULL) = (formato_unita IS NULL)", name="ck_prodotto_formato"),
        CheckConstraint("soglia_esposti >= 0 AND giorni_preavviso >= 0", name="ck_prodotto_soglie"),
        CheckConstraint("giorni_validita IS NULL OR giorni_validita > 0", name="ck_prodotto_validita"),
        CheckConstraint("(sconto1_perc IS NULL OR sconto1_perc BETWEEN 0 AND 90) AND "
                        "(sconto2_perc IS NULL OR sconto2_perc BETWEEN 0 AND 90)", name="ck_prodotto_sconto_perc"),
        CheckConstraint("(sconto1_giorni IS NULL OR sconto1_giorni >= 0) AND "
                        "(sconto2_giorni IS NULL OR sconto2_giorni >= 0)", name="ck_prodotto_sconto_giorni"),
    )

    @property
    def formato_testo(self):
        if not self.formato_quantita or not self.formato_unita:
            return ""
        singolo = misura(self.formato_quantita, self.formato_unita)
        return f"{self.formato_pezzi} × {singolo}" if self.formato_pezzi > 1 else singolo

    @property
    def descrizione(self):
        return " · ".join(x for x in (self.marca, self.nome, self.formato_testo) if x)

    @property
    def prezzo_misura(self):
        """Prezzo per unita' di misura (obbligatorio in etichetta): (centesimi, 'kg'|'l'|'pz')."""
        if self.prezzo_centesimi is None:
            return None
        if self.unita == "kg":
            return self.prezzo_centesimi, "kg"
        if not self.formato_quantita or not self.formato_unita:
            return None
        totale = self.formato_quantita * self.formato_pezzi
        if self.formato_unita == "pz":
            return (self.prezzo_centesimi + totale // 2) // totale, "pz"
        per_mille = (self.prezzo_centesimi * 1000 + totale // 2) // totale
        return per_mille, "kg" if self.formato_unita == "g" else "l"

    def fasce_sconto(self):
        """Fasce dello sconto programmato dall'admin sul prodotto (0 = nessuna fascia)."""
        return [(self.sconto1_giorni or 0, self.sconto1_perc or 0),
                (self.sconto2_giorni or 0, self.sconto2_perc or 0)]


class CodiceAggiuntivo(db.Model):
    __tablename__ = "codici_aggiuntivi"
    id = db.Column(db.Integer, primary_key=True)
    prodotto_id = db.Column(db.Integer, db.ForeignKey("prodotti.id"), nullable=False)
    gtin = db.Column(db.String(14), unique=True, nullable=False)
    descrizione = db.Column(db.String(60))
    prodotto = db.relationship("Prodotto", back_populates="codici_aggiuntivi")

    __table_args__ = (CheckConstraint("gtin ~ '^[0-9]{14}$'", name="ck_codice_gtin"),)


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
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    dispositivo_id = db.Column(db.Integer, db.ForeignKey("dispositivi.id"))
    totale_centesimi = db.Column(db.Integer, nullable=False, default=0)
    righe = db.relationship("RigaVendita", back_populates="vendita")

    __table_args__ = (
        CheckConstraint("totale_centesimi >= 0", name="ck_vendita_totale"),
        CheckConstraint("utente_id IS NOT NULL OR dispositivo_id IS NOT NULL", name="ck_vendita_origine"),
    )


class RigaVendita(db.Model):
    __tablename__ = "righe_vendita"
    id = db.Column(db.Integer, primary_key=True)
    vendita_id = db.Column(db.Integer, db.ForeignKey("vendite.id"), nullable=False)
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"), nullable=False)
    quantita = db.Column(db.Integer, nullable=False)
    prezzo_unitario_centesimi = db.Column(db.Integer, nullable=False)
    sconto_perc = db.Column(db.Integer, nullable=False, default=0)
    totale_centesimi = db.Column(db.Integer, nullable=False)
    aliquota_iva = db.Column(db.Integer, nullable=False)
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
    prodotto_id = db.Column(db.Integer, db.ForeignKey("prodotti.id"))
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"))
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    ruolo_destinatario = db.Column(db.String(30), nullable=False)
    stato = db.Column(db.String(10), nullable=False, default="aperta")
    nota = db.Column(db.String(255))
    creata_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    chiusa_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    chiusa_il = db.Column(db.DateTime(timezone=True))
    prodotto = db.relationship("Prodotto")
    lotto = db.relationship("Lotto")
    utente = db.relationship("Utente", foreign_keys=[utente_id])
    chiusa_da_utente = db.relationship("Utente", foreign_keys=[chiusa_da])

    __table_args__ = (
        CheckConstraint(
            "tipo IN ('riempi','esaurito','in_scadenza','da_rimuovere','da_approvare',"
            "'sconto','freschezza','reset_password','dispositivo')",
            name="ck_notifica_tipo",
        ),
        CheckConstraint("ruolo_destinatario IN ('admin','magazziniere','dipendente')", name="ck_notifica_ruolo"),
        CheckConstraint("stato IN ('aperta','chiusa')", name="ck_notifica_stato"),
        CheckConstraint("prodotto_id IS NOT NULL OR utente_id IS NOT NULL", name="ck_notifica_soggetto"),
        Index(
            "uq_notifica_aperta",
            "tipo", "prodotto_id", "lotto_id", "utente_id", "ruolo_destinatario",
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


class Sconto(db.Model):
    """Sconto deciso dall'admin su un lotto: manuale oppure generato da una programmazione."""
    __tablename__ = "sconti"
    id = db.Column(db.Integer, primary_key=True)
    lotto_id = db.Column(db.Integer, db.ForeignKey("lotti.id"), nullable=False)
    perc = db.Column(db.Integer, nullable=False)
    quantita = db.Column(db.Integer, nullable=False)
    venduti = db.Column(db.Integer, nullable=False, default=0)
    origine = db.Column(db.String(12), nullable=False)
    attivo = db.Column(db.Boolean, nullable=False, default=True)
    creato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    chiuso_il = db.Column(db.DateTime(timezone=True))
    lotto = db.relationship("Lotto")

    __table_args__ = (
        CheckConstraint("perc BETWEEN 1 AND 90", name="ck_sconto_perc"),
        CheckConstraint("quantita > 0", name="ck_sconto_quantita"),
        CheckConstraint("venduti >= 0 AND venduti <= quantita", name="ck_sconto_venduti"),
        CheckConstraint("origine IN ('manuale','programmato')", name="ck_sconto_origine"),
        Index("uq_sconto_attivo", "lotto_id", unique=True, postgresql_where=text("attivo")),
    )

    @property
    def residuo(self):
        return self.quantita - self.venduti


class Dispositivo(db.Model):
    """Cassa o bilancia collegata via API. Della chiave si salva solo l'impronta SHA-256."""
    __tablename__ = "dispositivi"
    id = db.Column(db.Integer, primary_key=True)
    nome = db.Column(db.String(60), unique=True, nullable=False)
    tipo = db.Column(db.String(10), nullable=False)
    token_hash = db.Column(db.String(64), unique=True, nullable=False)
    prefisso = db.Column(db.String(12), nullable=False)
    attivo = db.Column(db.Boolean, nullable=False, default=True)
    archiviato = db.Column(db.Boolean, nullable=False, default=False)
    creato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    ultimo_uso = db.Column(db.DateTime(timezone=True))

    __table_args__ = (CheckConstraint("tipo IN ('cassa','bilancia')", name="ck_dispositivo_tipo"),)


class RichiestaApi(db.Model):
    """Memoria delle operazioni gia' eseguite: la stessa transazione non viene mai applicata due volte."""
    __tablename__ = "richieste_api"
    id = db.Column(db.Integer, primary_key=True)
    dispositivo_id = db.Column(db.Integer, db.ForeignKey("dispositivi.id"), nullable=False)
    chiave = db.Column(db.String(64), nullable=False)
    codice_http = db.Column(db.Integer, nullable=False)
    risposta = db.Column(db.Text, nullable=False)
    creata_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)

    __table_args__ = (UniqueConstraint("dispositivo_id", "chiave", name="uq_richiesta_api"),)


class Impostazione(db.Model):
    """Impostazioni del negozio salvate nel db (es. guida al primo avvio nascosta)."""
    __tablename__ = "impostazioni"
    chiave = db.Column(db.String(50), primary_key=True)
    valore = db.Column(db.String(255), nullable=False)
    aggiornata_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso, onupdate=adesso)


class DispositivoAccesso(db.Model):
    """Dispositivo personale da cui un utente puo' entrare, approvato dall'admin.
    Del browser si salva solo una descrizione breve; della chiave solo l'impronta."""
    __tablename__ = "dispositivi_accesso"
    id = db.Column(db.Integer, primary_key=True)
    utente_id = db.Column(db.Integer, db.ForeignKey("utenti.id"), nullable=False)
    token_hash = db.Column(db.String(64), nullable=False)
    descrizione = db.Column(db.String(80), nullable=False)
    nome = db.Column(db.String(60))
    stato = db.Column(db.String(12), nullable=False, default="in_attesa")
    creato_il = db.Column(db.DateTime(timezone=True), nullable=False, default=adesso)
    approvato_da = db.Column(db.Integer, db.ForeignKey("utenti.id"))
    approvato_il = db.Column(db.DateTime(timezone=True))
    ultimo_uso = db.Column(db.DateTime(timezone=True))
    ultimo_ip = db.Column(db.String(45))
    utente = db.relationship("Utente", foreign_keys=[utente_id],
                             backref=db.backref("dispositivi_accesso", order_by="DispositivoAccesso.creato_il"))

    __table_args__ = (
        CheckConstraint("stato IN ('in_attesa','approvato','revocato')", name="ck_dispaccesso_stato"),
        UniqueConstraint("utente_id", "token_hash", name="uq_dispaccesso"),
        Index("ix_dispaccesso_token", "token_hash"),
    )
