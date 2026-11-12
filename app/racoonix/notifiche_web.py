from datetime import datetime, timezone

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, url_for)
from sqlalchemy.orm import selectinload

from . import db
from .auth import login_richiesto, registra, ruoli_attivi
from .carico import _quantita as leggi_quantita
from .lingua import _, _l
from .models import Lotto, Notifica, Scarto
from .notifiche import controlla_scaffali, controllo_giornaliero
from .sconti import applica_programmati

bp = Blueprint("notifiche", __name__, url_prefix="/notifiche")
SEZIONI = [("admin", _l("Per te")), ("dipendente", _l("Dipendenti: scaffali")),
           ("magazziniere", _l("Magazzinieri: magazzino"))]
URGENZA = {"dispositivo": 0, "reset_password": 0, "da_rimuovere": 1, "da_approvare": 2, "da_ordinare": 2, "riempi": 3,  # nosec B105 - priorita' della notifica, non una password
           "sconto": 5, "in_scadenza": 6, "freschezza": 7}
AZIONI = {"da_rimuovere": {"rimosso"}, "sconto": {"bollino"},
          "in_scadenza": {"verifica"}, "freschezza": {"ok", "deteriorato"}, "reset_password": {"ignora"},
          "da_ordinare": {"visto"}, "riempi": {"rifornito"}}
STORICO_MAX = 30


def _ruoli_visibili(ruoli):
    return [r for r, _x in SEZIONI if "admin" in ruoli or r in ruoli]


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
        return _vista(_("Gia' gestita da qualcun altro"), "errore")

    if azione == "rifornito":
        from .formato import quantita as mostra_quantita
        from .inventario import sposta_sullo_scaffale
        prodotto = notifica.prodotto
        quantita = leggi_quantita(request.form.get("quantita"), prodotto.unita)
        if not quantita:
            return _vista(_("Scrivi quanti ne hai messi sullo scaffale"), "errore")
        errore, _movimenti = sposta_sullo_scaffale(prodotto, quantita)
        if errore:
            return _vista(errore, "errore")
        return _vista(_("Spostati sullo scaffale: %(quantita)s", quantita=mostra_quantita(quantita, prodotto.unita)), "ok")

    if azione in ("rimosso", "deteriorato", "verifica"):
        if notifica.lotto_id is None:
            abort(404)
        lotto = db.session.get(Lotto, notifica.lotto_id, with_for_update=True)
        # Il magazzino e' un numero certo: una differenza e' una rettifica da registrare.
        # Lo scaffale no: i clienti comprano, quindi conta solo quello che il dipendente trova.
        scaffale = notifica.ruolo_destinatario == "dipendente"
        campo = "qta_esposta" if scaffale else "qta_magazzino"
        registrato = getattr(lotto, campo)
        unita = notifica.prodotto.unita
        testo = (request.form.get("quantita") or "").strip()
        if azione == "verifica":
            if not testo:
                return _vista(_("Scrivi quanti ne restano (0 se sono finiti)"), "errore")
            contati = leggi_quantita(testo, unita)
            if contati is None:
                return _vista(_("Quantita' non valida"), "errore")
            setattr(lotto, campo, contati)
            if not scaffale and contati != registrato:
                registra("rettifica", g.utente.id,
                         f"lotto {lotto.id} {campo}: {registrato} -> {contati} (verifica scadenza)")
        else:
            if scaffale and not testo:
                return _vista(_("Scrivi quanti ne hai trovati (0 se non ce n'erano)"), "errore")
            da_togliere = leggi_quantita(testo, unita) if testo else registrato
            if da_togliere is None or (not scaffale and azione == "deteriorato" and da_togliere > registrato):
                return _vista(_("Quantita' non valida"), "errore")
            if azione == "rimosso":
                setattr(lotto, campo, 0)
                if not scaffale and da_togliere != registrato:
                    registra("rettifica", g.utente.id,
                             f"lotto {lotto.id} {campo}: registrati {registrato}, trovati {da_togliere} (rimozione)")
            else:
                setattr(lotto, campo, max(0, registrato - da_togliere))
            if da_togliere > 0:
                db.session.add(Scarto(lotto_id=lotto.id, quantita=da_togliere,
                                      motivo="scaduto" if azione == "rimosso" else "deteriorato",
                                      utente_id=g.utente.id))

    notifica.stato = "chiusa"
    notifica.chiusa_da = g.utente.id
    notifica.chiusa_il = datetime.now(timezone.utc)
    registra(f"notifica_{azione}", g.utente.id, f"notifica {notifica.id}, tipo {notifica.tipo}")
    db.session.commit()
    if azione in ("rimosso", "deteriorato", "verifica"):
        controlla_scaffali([notifica.prodotto_id])
    return _vista(_("Fatto"), "ok")


@bp.get("/lista")
def lista():
    """Ricaricata in automatico dalla pagina. Senza sessione non restituisce niente (204)."""
    if g.get("utente") is None:
        return "", 204
    return render_template("_notifiche.html", **_dati())


@bp.get("/contatore")
def contatore():
    if g.get("utente") is None:
        return "", 204
    return render_template("_contatore.html")
