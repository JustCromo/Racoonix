"""Sconti decisi dall'admin: manuali su un lotto oppure programmati sul prodotto."""
from datetime import date, datetime, timezone

from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from . import db
from .formato import data_it
from .formato import quantita as mostra
from .models import Lotto, Notifica, Prodotto, Sconto
from .notifiche import _apri
from .regole import perc_sconto


def _adesso():
    return datetime.now(timezone.utc)


def sconto_attivo(lotto):
    return db.session.scalar(db.select(Sconto).filter_by(lotto_id=lotto.id, attivo=True))


def togli_sconto(lotto):
    attuale = sconto_attivo(lotto)
    if attuale:
        attuale.attivo = False
        attuale.chiuso_il = _adesso()
    for notifica in db.session.scalars(db.select(Notifica).filter_by(
            lotto_id=lotto.id, tipo="sconto", stato="aperta")):
        notifica.stato = "chiusa"
        notifica.chiusa_il = _adesso()
    db.session.flush()


def crea_sconto(lotto, perc, quantita, origine, utente_id):
    togli_sconto(lotto)
    db.session.add(Sconto(lotto_id=lotto.id, perc=perc, quantita=quantita,
                          origine=origine, attivo=True, creato_da=utente_id))
    db.session.flush()
    p = lotto.prodotto
    _apri("sconto", p.id, "dipendente",
          f"Applica il bollino -{perc}% su {mostra(quantita, p.unita)} "
          f"(lotto {lotto.codice_lotto}, scade il {data_it(lotto.data_scadenza)})", lotto.id)


def applica_programmati():
    """Attiva gli sconti programmati sui lotti che hanno raggiunto la soglia. Idempotente."""
    oggi = date.today()
    finiti = db.session.scalars(
        db.select(Sconto).join(Lotto)
        .where(Sconto.attivo.is_(True),
               or_((Lotto.qta_esposta + Lotto.qta_magazzino) == 0, Lotto.data_scadenza <= oggi))).all()
    for sconto in finiti:
        sconto.attivo = False
        sconto.chiuso_il = _adesso()

    creati = 0
    lotti = db.session.scalars(
        db.select(Lotto).join(Prodotto)
        .where(Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0,
               Lotto.data_scadenza > oggi, or_(Prodotto.sconto1_perc > 0, Prodotto.sconto2_perc > 0))
        .options(selectinload(Lotto.prodotto))).all()
    for lotto in lotti:
        perc = perc_sconto(lotto.prodotto, lotto, oggi)
        if not perc:
            continue
        attuale = sconto_attivo(lotto)
        if attuale and attuale.perc >= perc:
            continue
        crea_sconto(lotto, perc, lotto.qta_esposta + lotto.qta_magazzino, "programmato", None)
        creati += 1
    db.session.commit()
    return creati
