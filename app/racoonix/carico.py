import re
import secrets
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from . import codici, db
from .auth import registra, richiede_ruolo
from .models import Categoria, Lotto, Notifica, Prodotto
from .notifiche import controlla_scaffali
from .catalogo import trova_per_gtin

bp = Blueprint("carico", __name__, url_prefix="/carico")
NOME_OK = re.compile(r"^[\w .,'()%/&+-]{2,120}$")
ID_OK = re.compile(r"^[0-9]{1,9}$")
PEZZI_OK = re.compile(r"^[0-9]{1,5}$")
KG_OK = re.compile(r"^[0-9]{1,4}([.,][0-9]{1,3})?$")
ERRORE_CODICE = "Codice non riconosciuto"
CHIAVE = "carico"


def _categorie():
    return db.session.scalars(
        db.select(Categoria).filter_by(attiva=True).order_by(Categoria.nome)).all()


def _id(testo):
    testo = (testo or "").strip()
    return int(testo) if ID_OK.match(testo) else None


def _quantita(testo, unita):
    """Pezzi interi, oppure kg con al massimo 3 decimali convertiti in grammi interi."""
    testo = (testo or "").strip()
    if not testo:
        return 0
    if unita == "pezzo":
        return int(testo) if PEZZI_OK.match(testo) else None
    if not KG_OK.match(testo):
        return None
    intero, _, decimali = testo.replace(",", ".").partition(".")
    return int(intero) * 1000 + int(decimali.ljust(3, "0"))


def _prodotto_da_info(info):
    if info.get("prodotto_id"):
        return db.session.get(Prodotto, info["prodotto_id"])
    if info.get("gtin"):
        return trova_per_gtin(info["gtin"])
    return None


def _mostra_form(info, prodotto, errori=None, valori=None, codice=200):
    return render_template("carico_form.html", info=info, prodotto=prodotto,
                           categorie=_categorie(), errori=errori or [],
                           valori=valori or {}, oggi=date.today()), codice


@bp.get("/")
@richiede_ruolo("magazziniere")
def pagina():
    session.pop(CHIAVE, None)
    sfusi = db.session.scalars(
        db.select(Prodotto)
        .where(Prodotto.codice_bilancia.is_not(None), Prodotto.stato == "attivo")
        .order_by(Prodotto.nome)).all()
    return render_template("carico.html", sfusi=sfusi)


@bp.post("/leggi")
@richiede_ruolo("magazziniere")
def leggi():
    try:
        info = codici.riconosci(request.form.get("codice"), current_app.config["BILANCIA_PREFISSI"])
    except codici.CodiceNonValido as errore:
        current_app.logger.info("carico: codice rifiutato (%s)", errore)
        flash(ERRORE_CODICE, "errore")
        return redirect(url_for(".pagina"))
    if info["tipo"] == "bilancia":
        flash("Etichetta della bilancia: si registra dalla sezione Banco", "errore")
        return redirect(url_for(".pagina"))
    info = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in info.items()}
    prodotto = _prodotto_da_info(info)
    if prodotto and prodotto.stato == "rimosso":
        flash("Prodotto non ammesso: contatta l'admin", "errore")
        return redirect(url_for(".pagina"))
    session[CHIAVE] = info
    return _mostra_form(info, prodotto)


@bp.post("/sfuso")
@richiede_ruolo("magazziniere")
def sfuso():
    pid = _id(request.form.get("prodotto_id"))
    prodotto = db.session.get(Prodotto, pid) if pid else None
    if prodotto is None or prodotto.stato != "attivo":
        flash(ERRORE_CODICE, "errore")
        return redirect(url_for(".pagina"))
    info = {"tipo": "manuale", "prodotto_id": prodotto.id, "gtin": None, "scadenza": None,
            "tipo_data": None, "lotto": None, "confezionamento": None, "peso_g": None}
    session[CHIAVE] = info
    return _mostra_form(info, prodotto)


@bp.post("/conferma")
@richiede_ruolo("magazziniere")
def conferma():
    info = session.get(CHIAVE)
    if not info:
        flash("Carico scaduto, rileggi il codice", "errore")
        return redirect(url_for(".pagina"))
    prodotto = _prodotto_da_info(info)
    if prodotto and prodotto.stato == "rimosso":
        flash("Prodotto non ammesso: contatta l'admin", "errore")
        return redirect(url_for(".pagina"))

    f = request.form
    errori = []
    if prodotto is None:
        nome = (f.get("nome") or "").strip()
        unita = f.get("unita")
        cid = _id(f.get("categoria_id"))
        categoria = db.session.get(Categoria, cid) if cid else None
        if not NOME_OK.match(nome):
            errori.append("Nome non valido")
        if categoria is None or not categoria.attiva:
            errori.append("Categoria non valida")
        if unita not in ("pezzo", "kg"):
            errori.append("Unita' non valida")
    else:
        categoria, unita = prodotto.categoria, prodotto.unita

    attivo = prodotto is not None and prodotto.stato == "attivo"
    esposta = _quantita(f.get("esposta"), unita) if attivo else 0
    magazzino = _quantita(f.get("magazzino"), unita)
    if esposta is None or magazzino is None:
        errori.append("Quantita' non valida")
    elif esposta + magazzino <= 0:
        errori.append("Inserisci almeno una quantita'")

    oggi = date.today()
    scadenza = None
    if info.get("scadenza"):
        scadenza = date.fromisoformat(info["scadenza"])
    else:
        testo = (f.get("scadenza") or "").strip()
        if testo:
            try:
                scadenza = date.fromisoformat(testo)
            except ValueError:
                errori.append("Data di scadenza non valida")
        elif categoria is not None and categoria.richiede_scadenza:
            errori.append("Questa categoria richiede la data di scadenza")
    if scadenza and scadenza < oggi:
        errori.append("Prodotto gia' scaduto: non si puo' caricare")
    if scadenza and scadenza > oggi + timedelta(days=3650):
        errori.append("Data di scadenza non plausibile")

    codice_lotto = info.get("lotto") or (f.get("lotto") or "").strip()
    if codice_lotto and not codici.LOTTO_OK.match(codice_lotto):
        errori.append("Lotto non valido")

    if errori:
        return _mostra_form(info, prodotto, errori, f, 400)

    if not codice_lotto:
        codice_lotto = f"INT{oggi:%y%m%d}{secrets.token_hex(2).upper()}"

    if prodotto is None:
        prodotto = Prodotto(gtin=info.get("gtin"), nome=nome, categoria_id=categoria.id,
                            unita=unita, stato="in_attesa", creato_da=g.utente.id,
                            soglia_esposti=5 if unita == "pezzo" else 2000)
        db.session.add(prodotto)
        db.session.flush()
        db.session.add(Notifica(tipo="da_approvare", prodotto_id=prodotto.id,
                                ruolo_destinatario="admin"))

    lotto = db.session.scalar(db.select(Lotto).filter_by(
        prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza))
    if lotto is None:
        confezionamento = info.get("confezionamento")
        lotto = Lotto(prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza,
                      data_confezionamento=date.fromisoformat(confezionamento) if confezionamento else None,
                      qta_esposta=0, qta_magazzino=0, caricato_da=g.utente.id)
        db.session.add(lotto)
    lotto.qta_esposta += esposta
    lotto.qta_magazzino += magazzino

    registra("carico", g.utente.id,
             f"prodotto {prodotto.id}, lotto {codice_lotto}, esposta {esposta}, magazzino {magazzino}")
    db.session.commit()
    session.pop(CHIAVE, None)
    controlla_scaffali([prodotto.id])
    flash(f"Caricato: {prodotto.nome}", "ok")
    return redirect(url_for(".pagina"))
