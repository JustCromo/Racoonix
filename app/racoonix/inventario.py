import re
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, url_for)
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from . import codici, db
from .auth import registra, richiede_ruolo
from .carico import _quantita as leggi_quantita
from .formato import quantita as mostra_quantita
from .models import Categoria, Lotto, Prodotto
from .prodotti import _chiudi_notifiche

bp = Blueprint("inventario", __name__, url_prefix="/inventario")
ID_OK = re.compile(r"^[0-9]{1,9}$")


def _stato_lotto(lotto, prodotto, oggi):
    if lotto.data_scadenza:
        if lotto.data_scadenza < oggi:
            return "scaduto"
        if lotto.data_scadenza == oggi:
            return "oggi"
        if lotto.data_scadenza <= oggi + timedelta(days=prodotto.giorni_preavviso):
            return "in_scadenza"
        return "ok"
    giorni = prodotto.categoria.giorni_freschezza
    if giorni and (oggi - lotto.data_carico.date()).days >= giorni:
        return "controllare"
    return "ok"


def _vendibile(lotto, oggi):
    return lotto.data_scadenza is None or lotto.data_scadenza > oggi


def _filtri(sorgente):
    q = (sorgente.get("q") or "").strip()[:100]
    categoria = (sorgente.get("categoria") or "").strip()
    return q, int(categoria) if ID_OK.match(categoria) else None


def _scheda(p, oggi):
    lotti = sorted((l for l in p.lotti if l.qta_esposta + l.qta_magazzino > 0),
                   key=lambda l: (l.data_scadenza is None, l.data_scadenza or oggi, l.data_carico))
    esposta = sum(l.qta_esposta for l in lotti)
    return {
        "p": p,
        "lotti": [{"l": l, "stato": _stato_lotto(l, p, oggi)} for l in lotti],
        "esposta": esposta,
        "magazzino": sum(l.qta_magazzino for l in lotti),
        "rifornibile": sum(l.qta_magazzino for l in lotti if _vendibile(l, oggi)),
        "sotto_soglia": p.stato == "attivo" and esposta <= p.soglia_esposti,
    }


def _cerca(q, categoria_id, tutti=False):
    stmt = (db.select(Prodotto).join(Categoria)
            .where(Prodotto.stato.in_(("attivo", "in_attesa")))
            .options(selectinload(Prodotto.lotti), selectinload(Prodotto.categoria))
            .order_by(Categoria.nome, Prodotto.nome).limit(200))
    if categoria_id:
        stmt = stmt.where(Prodotto.categoria_id == categoria_id)
    if not tutti:
        stmt = stmt.where(Prodotto.lotti.any((Lotto.qta_esposta + Lotto.qta_magazzino) > 0))
    if q:
        try:
            info = codici.riconosci(q, current_app.config["BILANCIA_PREFISSI"])
        except codici.CodiceNonValido:
            info = None
        if info and info.get("gtin"):
            stmt = stmt.where(Prodotto.gtin == info["gtin"])
        elif info and info.get("codice_bilancia"):
            stmt = stmt.where(Prodotto.codice_bilancia == info["codice_bilancia"])
        else:
            sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(Prodotto.nome.ilike(f"%{sicuro}%", escape="\\"))
    oggi = date.today()
    return [_scheda(p, oggi) for p in db.session.scalars(stmt)]


def _q_mostrabile(q):
    return "".join(c for c in q if c.isprintable())


@bp.get("/")
@richiede_ruolo("dipendente", "magazziniere")
def pagina():
    q, categoria_id = _filtri(request.args)
    categorie = db.session.scalars(db.select(Categoria).filter_by(attiva=True)
                                   .order_by(Categoria.nome)).all()
    return render_template("inventario.html", schede=_cerca(q, categoria_id, request.args.get("tutti") == "1"), categorie=categorie,
                           q=_q_mostrabile(q), categoria_id=categoria_id)


@bp.get("/risultati")
@richiede_ruolo("dipendente", "magazziniere")
def risultati():
    q, categoria_id = _filtri(request.args)
    return render_template("_risultati.html", schede=_cerca(q, categoria_id, request.args.get("tutti") == "1"),
                           q=_q_mostrabile(q), categoria_id=categoria_id)


def _risposta(prodotto, messaggio, esito, q, categoria_id):
    """Con htmx restituisce solo la scheda aggiornata, senza htmx fa il classico redirect."""
    if request.headers.get("HX-Request") == "true":
        return render_template("_scheda_prodotto.html", s=_scheda(prodotto, date.today()),
                               messaggio=messaggio, esito=esito,
                               q=_q_mostrabile(q), categoria_id=categoria_id)
    flash(messaggio, esito)
    return redirect(url_for(".pagina", q=q or None, categoria=categoria_id))


@bp.post("/<int:prodotto_id>/rifornisci")
@richiede_ruolo("dipendente", "magazziniere")
def rifornisci(prodotto_id):
    q, categoria_id = _filtri(request.form)
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    if prodotto.stato != "attivo":
        return _risposta(prodotto, "Prodotto non ancora approvato", "errore", q, categoria_id)
    quantita = leggi_quantita(request.form.get("quantita"), prodotto.unita)
    if not quantita:
        return _risposta(prodotto, "Quantita' non valida", "errore", q, categoria_id)

    oggi = date.today()
    lotti = db.session.scalars(
        db.select(Lotto)
        .where(Lotto.prodotto_id == prodotto.id, Lotto.qta_magazzino > 0,
               or_(Lotto.data_scadenza.is_(None), Lotto.data_scadenza > oggi))
        .order_by(Lotto.data_scadenza.asc().nulls_last(), Lotto.data_carico)
        .with_for_update()).all()
    disponibile = sum(l.qta_magazzino for l in lotti)
    if quantita > disponibile:
        return _risposta(prodotto, f"In magazzino ci sono solo {mostra_quantita(disponibile, prodotto.unita)}",
                         "errore", q, categoria_id)

    restante = quantita
    for lotto in lotti:
        sposta = min(restante, lotto.qta_magazzino)
        lotto.qta_magazzino -= sposta
        lotto.qta_esposta += sposta
        restante -= sposta
        if restante == 0:
            break

    if sum(l.qta_esposta for l in prodotto.lotti) > prodotto.soglia_esposti:
        _chiudi_notifiche(prodotto.id, "riempi")
    registra("rifornimento", g.utente.id, f"prodotto {prodotto.id}, quantita {quantita}")
    db.session.commit()
    return _risposta(prodotto, f"Spostati sullo scaffale: {mostra_quantita(quantita, prodotto.unita)}",
                     "ok", q, categoria_id)
