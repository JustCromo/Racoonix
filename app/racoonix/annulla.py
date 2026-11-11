"""'Annulla' per un minuto dopo un carico o un rifornimento: chi sbaglia un numero lo corregge subito.
L'operazione da annullare resta nella sessione di chi l'ha fatta, quindi nessun altro puo' annullarla."""
import time

from flask import Blueprint, flash, g, redirect, request, session, url_for

from . import db
from .auth import login_richiesto, registra
from .lingua import _

bp = Blueprint("annulla", __name__)
DURATA = 60
CHIAVE = "annullabile"


def ricorda(tipo, **dati):
    session[CHIAVE] = {"tipo": tipo, "utente": g.utente.id, "scade": time.time() + DURATA, **dati}


def disponibile(tipo=None):
    voce = session.get(CHIAVE)
    if not voce or voce.get("scade", 0) < time.time() or voce.get("utente") != getattr(g.get("utente"), "id", None):
        return None
    return voce if tipo in (None, voce.get("tipo")) else None


@bp.post("/annulla")
@login_richiesto
def annulla():
    from .models import CodiceAggiuntivo, Lotto, Notifica, Prodotto, Riordino
    from .notifiche import controlla_scaffali
    voce = disponibile()
    session.pop(CHIAVE, None)
    if voce is None:
        flash(_("Non c'e' piu' niente da annullare: e' passato troppo tempo"), "errore")
        return redirect(request.referrer if request.referrer and request.referrer.startswith(request.host_url) else url_for("home"))

    if voce["tipo"] == "carico":
        lotto = db.session.scalar(db.select(Lotto).filter_by(id=voce["lotto_id"]).with_for_update())
        if lotto is None or lotto.qta_esposta < voce["esposta"] or lotto.qta_magazzino < voce["magazzino"]:
            flash(_("Non si puo' annullare: la merce e' gia' stata spostata o contata"), "errore")
            return redirect(url_for("carico.pagina"))
        lotto.qta_esposta -= voce["esposta"]
        lotto.qta_magazzino -= voce["magazzino"]
        prodotto_id = lotto.prodotto_id
        if voce["lotto_nuovo"] and lotto.qta_esposta == 0 and lotto.qta_magazzino == 0:
            for notifica in db.session.scalars(db.select(Notifica).filter_by(lotto_id=lotto.id)):
                db.session.delete(notifica)
            db.session.delete(lotto)
        for rid, stato in voce.get("riordini", []):
            riordino = db.session.get(Riordino, rid)
            if riordino and riordino.stato == "arrivato":
                riordino.stato, riordino.chiuso_il = stato, None
        db.session.flush()
        prodotto = db.session.get(Prodotto, prodotto_id)
        if voce["prodotto_nuovo"] and prodotto and not prodotto.lotti:
            for notifica in db.session.scalars(db.select(Notifica).filter_by(prodotto_id=prodotto.id)):
                db.session.delete(notifica)
            for codice in db.session.scalars(db.select(CodiceAggiuntivo).filter_by(prodotto_id=prodotto.id)):
                db.session.delete(codice)
            db.session.delete(prodotto)
        registra("carico_annullato", g.utente.id, f"prodotto {prodotto_id}, lotto {voce['lotto_id']}")
        db.session.commit()
        controlla_scaffali([prodotto_id])
        flash(_("Carico annullato"), "ok")
        return redirect(url_for("carico.pagina"))

    # rifornimento: la merce torna dallo scaffale al magazzino, lotto per lotto
    lotti = {l.id: l for l in db.session.scalars(db.select(Lotto).where(
        Lotto.id.in_([lid for lid, _q in voce["movimenti"]])).with_for_update())}
    if any(lid not in lotti or lotti[lid].qta_esposta < q for lid, q in voce["movimenti"]):
        flash(_("Non si puo' annullare: lo scaffale e' gia' cambiato"), "errore")
        return redirect(url_for("inventario.pagina", q=voce.get("cerca", "")))
    for lid, q in voce["movimenti"]:
        lotti[lid].qta_esposta -= q
        lotti[lid].qta_magazzino += q
    registra("rifornimento_annullato", g.utente.id, f"prodotto {voce['prodotto_id']}")
    db.session.commit()
    controlla_scaffali([voce["prodotto_id"]])
    flash(_("Rifornimento annullato: la merce torna in magazzino"), "ok")
    return redirect(url_for("inventario.pagina", q=voce.get("cerca", "")))
