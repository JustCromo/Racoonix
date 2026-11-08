"""Banco: il banconiere legge l'etichetta della sua bilancia e Racoonix registra la vaschetta."""
import secrets
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)
from sqlalchemy import or_

from . import codici, db
from .auth import registra, richiede_ruolo
from .catalogo import trova_per_gtin
from .formato import data_it
from .formato import quantita as mostra
from .models import Lotto, Prodotto
from .notifiche import controlla_scaffali

bp = Blueprint("banco", __name__, url_prefix="/banco")
CHIAVE = "banco"
VALIDITA_MAX = 60


def _origini(prodotto, oggi, per_aggiornare=False):
    """Pezzi interi (non vaschette) ancora buoni, dal piu' vicino alla scadenza."""
    stmt = (db.select(Lotto)
            .where(Lotto.prodotto_id == prodotto.id, Lotto.lotto_origine_id.is_(None),
                   (Lotto.qta_esposta + Lotto.qta_magazzino) > 0,
                   or_(Lotto.data_scadenza.is_(None), Lotto.data_scadenza > oggi))
            .order_by(Lotto.data_scadenza.asc().nulls_last(), Lotto.data_carico))
    if per_aggiornare:
        stmt = stmt.with_for_update()
    return db.session.scalars(stmt).all()


@bp.get("/")
@richiede_ruolo("dipendente")
def pagina():
    session.pop(CHIAVE, None)
    return render_template("banco.html")


@bp.post("/leggi")
@richiede_ruolo("dipendente")
def leggi():
    grezzo = (request.form.get("codice") or "").strip()[:250]
    try:
        info = codici.riconosci(grezzo, current_app.config["BILANCIA_PREFISSI"])
    except codici.CodiceNonValido as errore:
        current_app.logger.info("banco: codice rifiutato (%s)", errore)
        flash("Codice non riconosciuto", "errore")
        return redirect(url_for(".pagina"))

    if info["tipo"] == "bilancia":
        prodotto = db.session.scalar(db.select(Prodotto).filter_by(codice_bilancia=info["codice_bilancia"]))
    elif info.get("peso_g") and info.get("gtin"):
        prodotto = trova_per_gtin(info["gtin"])
    else:
        flash("Al banco si leggono solo le etichette stampate dalla bilancia", "errore")
        return redirect(url_for(".pagina"))
    if prodotto is None or prodotto.stato != "attivo" or prodotto.unita != "kg":
        flash("Etichetta non collegata a un prodotto a peso del catalogo", "errore")
        return redirect(url_for(".pagina"))
    if not prodotto.giorni_validita:
        flash("Prodotto non gestito al banco: imposta i giorni di validita' nella sua scheda", "errore")
        return redirect(url_for(".pagina"))

    oggi = date.today()
    origini = _origini(prodotto, oggi)
    disponibile = sum(l.qta_esposta + l.qta_magazzino for l in origini)
    limite = min((l.data_scadenza for l in origini if l.data_scadenza), default=None)
    proposta = info["scadenza"] or oggi + timedelta(days=prodotto.giorni_validita)
    if limite and proposta > limite:
        proposta = limite

    session[CHIAVE] = {
        "prodotto_id": prodotto.id, "peso_g": info["peso_g"],
        "etichetta": grezzo if info["tipo"] == "bilancia" else None,
        "lotto": info.get("lotto"),
        "scadenza_codice": info["scadenza"].isoformat() if info["scadenza"] else None,
        "confezionamento": info["confezionamento"].isoformat() if info["confezionamento"] else None,
    }
    return render_template("banco_form.html", prodotto=prodotto, peso=info["peso_g"],
                           disponibile=disponibile, proposta=proposta, limite=limite, oggi=oggi, domani=oggi + timedelta(days=1),
                           scadenza_fissa=bool(info["scadenza"]))


@bp.post("/conferma")
@richiede_ruolo("dipendente")
def conferma():
    dati = session.get(CHIAVE)
    if not dati:
        flash("Operazione scaduta, rileggi l'etichetta", "errore")
        return redirect(url_for(".pagina"))
    prodotto = db.session.get(Prodotto, dati["prodotto_id"])
    peso, oggi = dati["peso_g"], date.today()

    if dati["scadenza_codice"]:
        scadenza = date.fromisoformat(dati["scadenza_codice"])
    else:
        try:
            scadenza = date.fromisoformat((request.form.get("scadenza") or "").strip())
        except ValueError:
            scadenza = None
    if scadenza is None or not oggi < scadenza <= oggi + timedelta(days=VALIDITA_MAX):
        flash("Data di scadenza non valida", "errore")
        return redirect(url_for(".pagina"))

    origini = _origini(prodotto, oggi, per_aggiornare=True)
    if sum(l.qta_esposta + l.qta_magazzino for l in origini) < peso:
        flash(f"Al banco non c'e' abbastanza {prodotto.descrizione} per {mostra(peso, 'kg')}", "errore")
        return redirect(url_for(".pagina"))

    restante, usati = peso, []
    for lotto in origini:
        for campo in ("qta_esposta", "qta_magazzino"):
            prendi = min(restante, getattr(lotto, campo))
            if prendi > 0:
                setattr(lotto, campo, getattr(lotto, campo) - prendi)
                restante -= prendi
                if lotto not in usati:
                    usati.append(lotto)
        if restante == 0:
            break
    limite = min((l.data_scadenza for l in usati if l.data_scadenza), default=None)
    if limite and scadenza > limite:
        db.session.rollback()
        flash(f"La vaschetta non puo' scadere dopo il prodotto da cui e' tagliata ({data_it(limite)})", "errore")
        return redirect(url_for(".pagina"))

    confezionamento = date.fromisoformat(dati["confezionamento"]) if dati["confezionamento"] else oggi
    codice_lotto = dati["lotto"] or f"BAN{oggi:%y%m%d}{secrets.token_hex(2).upper()}"
    filtro = {"prodotto_id": prodotto.id, "data_scadenza": scadenza, "data_confezionamento": confezionamento}
    if dati["etichetta"]:
        filtro["codice_etichetta"] = dati["etichetta"]
    else:
        filtro["codice_lotto"] = codice_lotto
    vaschetta = db.session.scalar(db.select(Lotto).filter_by(**filtro).where(Lotto.lotto_origine_id.is_not(None)))
    if vaschetta is None:
        vaschetta = Lotto(prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza,
                          data_confezionamento=confezionamento, lotto_origine_id=usati[0].id,
                          codice_etichetta=dati["etichetta"], qta_esposta=0, qta_magazzino=0,
                          caricato_da=g.utente.id)
        db.session.add(vaschetta)
    vaschetta.qta_esposta += peso

    registra("preincartato", g.utente.id,
             f"prodotto {prodotto.id}, {peso} g, scadenza {scadenza.isoformat()}, origine lotto {usati[0].id}")
    db.session.commit()
    session.pop(CHIAVE, None)
    controlla_scaffali([prodotto.id])
    flash(f"Vaschetta registrata: {prodotto.descrizione}, {mostra(peso, 'kg')}, scade il {data_it(scadenza)}", "ok")
    return redirect(url_for(".pagina"))
