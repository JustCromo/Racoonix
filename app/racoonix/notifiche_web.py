from datetime import datetime, timezone

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, url_for)
from sqlalchemy.orm import selectinload

from . import db
from .auth import login_richiesto, registra, ruoli_attivi
from .carico import _quantita as leggi_quantita
from .models import Lotto, Notifica, Scarto
from .notifiche import controlla_scaffali, controllo_giornaliero
from .sconti import applica_programmati

bp = Blueprint("notifiche", __name__, url_prefix="/notifiche")
SEZIONI = [("admin", "Per te"), ("dipendente", "Dipendenti: scaffali e cassa"),
           ("magazziniere", "Magazzinieri: magazzino")]
URGENZA = {"reset_password": 0, "da_rimuovere": 1, "da_approvare": 2, "riempi": 3, "esaurito": 4,
           "sconto": 5, "in_scadenza": 6, "freschezza": 7, "da_correggere": 8}
AZIONI = {"da_rimuovere": {"rimosso"}, "esaurito": {"visto", "esaurimento"}, "sconto": {"bollino"},
          "in_scadenza": {"visto"}, "freschezza": {"ok", "deteriorato"}, "reset_password": {"ignora"}}
STORICO_MAX = 30


def _ruoli_visibili(ruoli):
    return [r for r, _ in SEZIONI if "admin" in ruoli or r in ruoli]


def conta_notifiche():
    if g.get("utente") is None:
        return {"notifiche_aperte": 0, "admin_attivo": False}
    ruoli = ruoli_attivi()
    totale = db.session.scalar(db.select(db.func.count(Notifica.id)).where(
        Notifica.stato == "aperta", Notifica.ruolo_destinatario.in_(_ruoli_visibili(ruoli))))
    return {"notifiche_aperte": totale, "admin_attivo": "admin" in ruoli}


def _dati(messaggio=None, esito="ok"):
    ruoli = ruoli_attivi()
    admin = "admin" in ruoli
    visibili = _ruoli_visibili(ruoli)
    opzioni = (selectinload(Notifica.prodotto), selectinload(Notifica.lotto),
               selectinload(Notifica.utente), selectinload(Notifica.chiusa_da_utente))
    aperte = db.session.scalars(db.select(Notifica).where(
        Notifica.stato == "aperta", Notifica.ruolo_destinatario.in_(visibili)).options(*opzioni)).all()
    sezioni = []
    for ruolo, titolo in SEZIONI:
        if ruolo not in visibili:
            continue
        mie = sorted((n for n in aperte if n.ruolo_destinatario == ruolo),
                     key=lambda n: (URGENZA.get(n.tipo, 9), n.creata_il))
        storico = []
        if admin:
            storico = db.session.scalars(
                db.select(Notifica).where(Notifica.stato == "chiusa", Notifica.ruolo_destinatario == ruolo)
                .order_by(Notifica.chiusa_il.desc()).limit(STORICO_MAX).options(*opzioni)).all()
        sezioni.append({"ruolo": ruolo, "titolo": titolo, "aperte": mie, "storico": storico})
    return {"sezioni": sezioni, "admin": admin, "messaggio": messaggio, "esito": esito}


def _vista(messaggio=None, esito="ok"):
    if request.headers.get("HX-Request") == "true":
        return render_template("_notifiche.html", **_dati(messaggio, esito))
    if messaggio:
        flash(messaggio, esito)
    return redirect(url_for(".pagina"))


@bp.get("/")
@login_richiesto
def pagina():
    try:
        controllo_giornaliero()
        applica_programmati()
    except Exception:
        db.session.rollback()
        current_app.logger.exception("controllo notifiche non riuscito")
    return render_template("notifiche.html", **_dati())


@bp.post("/<int:nid>/<azione>")
@login_richiesto
def agisci(nid, azione):
    notifica = db.get_or_404(Notifica, nid)
    ruoli = ruoli_attivi()
    if "admin" not in ruoli and notifica.ruolo_destinatario not in ruoli:
        abort(403)
    if azione not in AZIONI.get(notifica.tipo, set()):
        abort(404)
    if notifica.stato != "aperta":
        return _vista("Gia' gestita da qualcun altro", "errore")

    if azione in ("rimosso", "deteriorato"):
        if notifica.lotto_id is None:
            abort(404)
        lotto = db.session.get(Lotto, notifica.lotto_id, with_for_update=True)
        campo = "qta_esposta" if notifica.ruolo_destinatario == "dipendente" else "qta_magazzino"
        disponibile = getattr(lotto, campo)
        da_togliere = disponibile
        testo = (request.form.get("quantita") or "").strip()
        if azione == "deteriorato" and testo:
            da_togliere = leggi_quantita(testo, notifica.prodotto.unita)
            if not da_togliere or da_togliere > disponibile:
                return _vista("Quantita' non valida", "errore")
        if da_togliere > 0:
            setattr(lotto, campo, disponibile - da_togliere)
            db.session.add(Scarto(lotto_id=lotto.id, quantita=da_togliere,
                                  motivo="scaduto" if azione == "rimosso" else "deteriorato",
                                  utente_id=g.utente.id))
    if azione == "esaurimento":
        notifica.prodotto.in_esaurimento = True

    notifica.stato = "chiusa"
    notifica.chiusa_da = g.utente.id
    notifica.chiusa_il = datetime.now(timezone.utc)
    registra(f"notifica_{azione}", g.utente.id, f"notifica {notifica.id}, tipo {notifica.tipo}")
    db.session.commit()
    if azione in ("rimosso", "deteriorato"):
        controlla_scaffali([notifica.prodotto_id])
    return _vista("Fatto", "ok")
