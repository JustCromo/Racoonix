"""Motore delle notifiche: a evento (magazzino e riordini) e a tempo (scadenze, sconti, freschezza)."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from . import db
from .formato import data_it, quantita
from .lingua import _, nella_lingua_del_negozio
from .models import Lotto, Notifica, Prodotto
from .regole import vendibile
from .riordini import apri_riordino, chiudi_riordini


def _adesso():
    return datetime.now(timezone.utc)


def _apri(tipo, prodotto_id, ruolo, nota, lotto_id=None, utente_id=None):
    """Crea la notifica solo se non ne esiste gia' una aperta uguale (ci pensa l'indice unico)."""
    risultato = db.session.execute(
        insert(Notifica).values(tipo=tipo, prodotto_id=prodotto_id, lotto_id=lotto_id, utente_id=utente_id,
                                ruolo_destinatario=ruolo, stato="aperta", nota=nota[:255],
                                creata_il=_adesso())
        .on_conflict_do_nothing())
    return risultato.rowcount


def _chiudi(prodotto_id, tipo):
    for notifica in db.session.scalars(db.select(Notifica).filter_by(
            prodotto_id=prodotto_id, tipo=tipo, stato="aperta")):
        notifica.stato = "chiusa"
        notifica.chiusa_il = _adesso()


def _gia_gestita(tipo, lotto_id, ruolo):
    return db.session.scalar(db.select(Notifica.id).filter_by(
        tipo=tipo, lotto_id=lotto_id, ruolo_destinatario=ruolo, stato="chiusa").limit(1)) is not None


def controlla_scaffali(prodotto_ids):
    """Dopo carichi, conteggi, rifornimenti e rimozioni. Guarda solo il magazzino, l'unico numero certo:
    lo scaffale lo osservano le persone, con "Sta finendo"."""
    oggi = date.today()
    prodotti = db.session.scalars(db.select(Prodotto).where(
        Prodotto.id.in_(list(prodotto_ids)), Prodotto.stato == "attivo")).all()
    for p in prodotti:
        magazzino = sum(l.qta_magazzino for l in p.lotti if vendibile(l, oggi))
        if magazzino == 0:
            _chiudi(p.id, "riempi")
        if p.in_esaurimento:
            chiudi_riordini(p.id, ("da_ordinare",), "annullato")
        elif p.soglia_riordino is not None and magazzino <= p.soglia_riordino:
            apri_riordino(p, "soglia")
    db.session.commit()


def _dove(ruolo, q, p, l, togli=False):
    """Il magazzino e' un numero certo; lo scaffale no, quindi li' si indica il lotto da controllare."""
    if ruolo == "dipendente":
        if togli:
            return _("dallo scaffale il lotto %(lotto)s", lotto=l.codice_lotto)
        return _("sullo scaffale il lotto %(lotto)s", lotto=l.codice_lotto)
    if togli:
        return _("%(quantita)s dal magazzino (lotto %(lotto)s)", quantita=quantita(q, p.unita), lotto=l.codice_lotto)
    return _("%(quantita)s in magazzino (lotto %(lotto)s)", quantita=quantita(q, p.unita), lotto=l.codice_lotto)


@nella_lingua_del_negozio
def controllo_giornaliero():
    """Scadenze, sconti e freschezza. Si puo' lanciare quante volte si vuole: non crea doppioni."""
    oggi = date.today()
    creati = 0
    lotti = db.session.scalars(
        db.select(Lotto).join(Prodotto)
        .where(Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0)
        .options(selectinload(Lotto.prodotto).selectinload(Prodotto.categoria))).all()

    for l in lotti:
        p = l.prodotto
        parti = [(r, q) for r, q in (("dipendente", l.qta_esposta), ("magazziniere", l.qta_magazzino)) if q > 0]

        if l.data_scadenza:
            giorni = (l.data_scadenza - oggi).days
            if giorni <= 0:
                for ruolo, q in parti:
                    creati += _apri("da_rimuovere", p.id, ruolo,
                                    _("Scaduto il %(data)s: togli %(dove)s", data=data_it(l.data_scadenza),
                                      dove=_dove(ruolo, q, p, l, togli=True)), l.id)
                continue
            if giorni <= p.giorni_preavviso:
                for ruolo, q in parti:
                    if not _gia_gestita("in_scadenza", l.id, ruolo):
                        creati += _apri("in_scadenza", p.id, ruolo,
                                        _("Scade il %(data)s (tra %(giorni)s gg): controlla %(dove)s",
                                          data=data_it(l.data_scadenza), giorni=giorni, dove=_dove(ruolo, q, p, l)), l.id)
        elif p.categoria.giorni_freschezza:
            limite = p.categoria.giorni_freschezza
            giorni = (oggi - l.data_carico.date()).days
            if giorni >= limite:
                for ruolo, q in parti:
                    recente = db.session.scalar(db.select(Notifica.id).where(
                        Notifica.tipo == "freschezza", Notifica.lotto_id == l.id,
                        Notifica.ruolo_destinatario == ruolo,
                        Notifica.creata_il >= _adesso() - timedelta(days=limite)).limit(1))
                    if recente is None:
                        creati += _apri("freschezza", p.id, ruolo,
                                        _("Arrivato da %(giorni)s giorni: controlla %(dove)s",
                                          giorni=giorni, dove=_dove(ruolo, q, p, l)), l.id)

    svuotate = db.session.scalars(
        db.select(Notifica).join(Lotto, Notifica.lotto_id == Lotto.id)
        .where(Notifica.stato == "aperta", (Lotto.qta_esposta + Lotto.qta_magazzino) == 0)).all()
    for notifica in svuotate:
        notifica.stato = "chiusa"
        notifica.chiusa_il = _adesso()
    db.session.commit()
    controlla_scaffali(db.session.scalars(db.select(Prodotto.id).where(
        Prodotto.stato == "attivo", or_(Prodotto.lotti.any(), Prodotto.id.in_(db.select(Notifica.prodotto_id).where(Notifica.stato == "aperta", Notifica.tipo.in_(("riempi",))))))).all())
    return creati
