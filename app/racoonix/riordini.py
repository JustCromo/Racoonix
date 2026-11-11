"""Riordini: cosa ordinare ai fornitori.
Il magazzino e' il dato affidabile (lo toccano solo i dipendenti, sempre registrando),
lo scaffale invece lo osservano le persone."""
from datetime import datetime, timezone

from sqlalchemy.dialects.postgresql import insert

from . import db
from .lingua import testo_negozio
from .models import Notifica, Riordino

APERTI = ("da_ordinare", "ordinato")


def _adesso():
    return datetime.now(timezone.utc)


def riordino_aperto(prodotto_id):
    return db.session.scalar(db.select(Riordino).where(
        Riordino.prodotto_id == prodotto_id, Riordino.stato.in_(APERTI)))


def quantita_suggerita(prodotto_id):
    """La quantita' dell'ultimo ordine arrivato: il titolare la corregge se serve."""
    return db.session.scalar(
        db.select(Riordino.quantita).where(Riordino.prodotto_id == prodotto_id, Riordino.stato == "arrivato",
                                           Riordino.quantita.is_not(None))
        .order_by(Riordino.chiuso_il.desc()).limit(1))


def _tolto_dopo_ultimo_carico(prodotto):
    """Un 'Togli' dalla lista vale fino al prossimo carico, poi la soglia torna a contare."""
    ultimo = max((l.data_carico for l in prodotto.lotti), default=None)
    stmt = db.select(Riordino.id).where(Riordino.prodotto_id == prodotto.id, Riordino.stato == "annullato")
    if ultimo:
        stmt = stmt.where(Riordino.chiuso_il >= ultimo)
    return db.session.scalar(stmt.limit(1)) is not None


def apri_riordino(prodotto, origine, utente_id=None):
    """Mette il prodotto nella lista d'ordine. Mai due volte: ci pensa l'indice unico del db."""
    if prodotto.in_esaurimento or prodotto.stato != "attivo":
        return 0
    if origine == "soglia" and _tolto_dopo_ultimo_carico(prodotto):
        return 0
    risultato = db.session.execute(
        insert(Riordino).values(prodotto_id=prodotto.id, quantita=quantita_suggerita(prodotto.id),
                                stato="da_ordinare", origine=origine, segnalato_da=utente_id,
                                creato_il=_adesso())
        .on_conflict_do_nothing())
    if risultato.rowcount:
        _avvisa_admin(prodotto, origine, utente_id)
    return risultato.rowcount


def _avvisa_admin(prodotto, origine, utente_id):
    """Il titolare lo vede subito in Cose da fare, non solo quando apre la pagina Ordini."""
    from .models import Utente
    fornitore = prodotto.fornitore.ragione_sociale if prodotto.fornitore else testo_negozio("nessun fornitore")
    if origine == "segnalazione":
        chi = db.session.get(Utente, utente_id) if utente_id else None
        nota = testo_negozio("Finito anche in magazzino (segnalato da %(utente)s): da ordinare a %(fornitore)s",
                             utente=chi.username if chi else "?", fornitore=fornitore)
    else:
        nota = testo_negozio("Magazzino sotto la soglia di riordino: da ordinare a %(fornitore)s", fornitore=fornitore)
    db.session.execute(insert(Notifica).values(
        tipo="da_ordinare", prodotto_id=prodotto.id, ruolo_destinatario="admin", stato="aperta",
        nota=nota[:255], creata_il=_adesso()).on_conflict_do_nothing())


def chiudi_avviso(prodotto_id):
    """Quando il prodotto esce da 'da ordinare' (ordinato, tolto, arrivato) l'avviso non serve piu'."""
    for notifica in db.session.scalars(db.select(Notifica).filter_by(
            prodotto_id=prodotto_id, tipo="da_ordinare", stato="aperta")):
        notifica.stato, notifica.chiusa_il = "chiusa", _adesso()


def chiudi_riordini(prodotto_id, stati, nuovo_stato):
    for riordino in db.session.scalars(db.select(Riordino).where(
            Riordino.prodotto_id == prodotto_id, Riordino.stato.in_(stati))):
        riordino.stato = nuovo_stato
        riordino.chiuso_il = _adesso()
    chiudi_avviso(prodotto_id)


def merce_arrivata(prodotto_id):
    chiudi_riordini(prodotto_id, APERTI, "arrivato")
