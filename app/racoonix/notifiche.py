"""Motore delle notifiche: a evento (scaffali) e a tempo (scadenze, sconti, freschezza)."""
from datetime import date, datetime, timedelta, timezone

from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.orm import selectinload

from . import db
from .formato import data_it, quantita
from .models import Lotto, Notifica, Prodotto
from .regole import perc_sconto, vendibile


def _adesso():
    return datetime.now(timezone.utc)


def _apri(tipo, prodotto_id, ruolo, nota, lotto_id=None):
    """Crea la notifica solo se non ne esiste gia' una aperta uguale (ci pensa l'indice unico)."""
    risultato = db.session.execute(
        insert(Notifica).values(tipo=tipo, prodotto_id=prodotto_id, lotto_id=lotto_id,
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
    """Dopo vendite, carichi e rimozioni: riempi lo scaffale oppure riordina."""
    oggi = date.today()
    prodotti = db.session.scalars(db.select(Prodotto).where(
        Prodotto.id.in_(list(prodotto_ids)), Prodotto.stato == "attivo")).all()
    for p in prodotti:
        validi = [l for l in p.lotti if vendibile(l, oggi)]
        esposta = sum(l.qta_esposta for l in validi)
        magazzino = sum(l.qta_magazzino for l in validi)
        if esposta > p.soglia_esposti:
            _chiudi(p.id, "riempi")
            _chiudi(p.id, "esaurito")
        elif magazzino > 0:
            _chiudi(p.id, "esaurito")
            _apri("riempi", p.id, "dipendente",
                  f"Sullo scaffale: {quantita(esposta, p.unita)}, in magazzino: {quantita(magazzino, p.unita)}")
        else:
            _chiudi(p.id, "riempi")
            _apri("esaurito", p.id, "magazziniere",
                  f"Sullo scaffale: {quantita(esposta, p.unita)} e magazzino vuoto: da riordinare")
    db.session.commit()


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
        dove = {"dipendente": "sullo scaffale", "magazziniere": "in magazzino"}

        if l.data_scadenza:
            giorni = (l.data_scadenza - oggi).days
            if giorni <= 0:
                for ruolo, q in parti:
                    creati += _apri("da_rimuovere", p.id, ruolo,
                                    f"Scaduto il {data_it(l.data_scadenza)}: togli {quantita(q, p.unita)} "
                                    f"{dove[ruolo]} (lotto {l.codice_lotto})", l.id)
                continue
            if giorni <= p.giorni_preavviso:
                for ruolo, q in parti:
                    if not _gia_gestita("in_scadenza", l.id, ruolo):
                        creati += _apri("in_scadenza", p.id, ruolo,
                                        f"Scade il {data_it(l.data_scadenza)} (tra {giorni} gg): "
                                        f"{quantita(q, p.unita)} {dove[ruolo]}", l.id)
            perc = perc_sconto(p, l, oggi)
            if perc > l.bollino_perc and l.qta_esposta > 0:
                creati += _apri("sconto", p.id, "dipendente",
                                f"Applica il bollino -{perc}% su {quantita(l.qta_esposta, p.unita)} "
                                f"(lotto {l.codice_lotto})", l.id)
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
                                        f"Arrivato da {giorni} giorni: controlla {quantita(q, p.unita)} "
                                        f"{dove[ruolo]}", l.id)

    svuotate = db.session.scalars(
        db.select(Notifica).join(Lotto, Notifica.lotto_id == Lotto.id)
        .where(Notifica.stato == "aperta", (Lotto.qta_esposta + Lotto.qta_magazzino) == 0)).all()
    for notifica in svuotate:
        notifica.stato = "chiusa"
        notifica.chiusa_il = _adesso()
    db.session.commit()
    controlla_scaffali(db.session.scalars(db.select(Prodotto.id).where(Prodotto.stato == "attivo", Prodotto.lotti.any())).all())
    return creati
