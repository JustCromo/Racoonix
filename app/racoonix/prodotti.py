import re
from datetime import datetime, timezone

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import db
from .auth import registra, richiede_ruolo
from .models import Categoria, Notifica, Prodotto, Scarto

bp = Blueprint("prodotti", __name__, url_prefix="/admin/prodotti")
NOME_OK = re.compile(r"^[\w .,'()%/&+-]{2,120}$")
ID_OK = re.compile(r"^[0-9]{1,9}$")
PREZZO_OK = re.compile(r"^[0-9]{1,5}([.,][0-9]{1,2})?$")


def centesimi(testo):
    testo = (testo or "").strip()
    if not PREZZO_OK.match(testo):
        return None
    intero, _, decimali = testo.replace(",", ".").partition(".")
    return int(intero) * 100 + int(decimali.ljust(2, "0"))


def _chiudi_notifiche(prodotto_id, tipo):
    aperte = db.session.scalars(db.select(Notifica).filter_by(
        prodotto_id=prodotto_id, tipo=tipo, stato="aperta"))
    for notifica in aperte:
        notifica.stato = "chiusa"
        notifica.chiusa_da = g.utente.id
        notifica.chiusa_il = datetime.now(timezone.utc)


def _in_attesa(prodotto_id):
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    return prodotto if prodotto.stato == "in_attesa" else None


@bp.get("/attesa")
@richiede_ruolo("admin")
def attesa():
    prodotti = db.session.scalars(db.select(Prodotto).filter_by(stato="in_attesa")
                                  .order_by(Prodotto.creato_il)).all()
    categorie = db.session.scalars(db.select(Categoria).filter_by(attiva=True)
                                   .order_by(Categoria.nome)).all()
    return render_template("prodotti_attesa.html", prodotti=prodotti, categorie=categorie)


@bp.post("/<int:prodotto_id>/approva")
@richiede_ruolo("admin")
def approva(prodotto_id):
    prodotto = _in_attesa(prodotto_id)
    if prodotto is None:
        flash("Prodotto gia' gestito", "errore")
        return redirect(url_for(".attesa"))
    nome = (request.form.get("nome") or "").strip()
    cid = (request.form.get("categoria_id") or "").strip()
    categoria = db.session.get(Categoria, int(cid)) if ID_OK.match(cid) else None
    prezzo = centesimi(request.form.get("prezzo"))
    if not NOME_OK.match(nome) or categoria is None or prezzo is None:
        flash("Dati non validi: controlla nome, categoria e prezzo", "errore")
        return redirect(url_for(".attesa"))
    prodotto.nome = nome
    prodotto.categoria_id = categoria.id
    prodotto.prezzo_centesimi = prezzo
    prodotto.stato = "attivo"
    prodotto.approvato_da = g.utente.id
    _chiudi_notifiche(prodotto.id, "da_approvare")
    registra("prodotto_approvato", g.utente.id, f"prodotto {prodotto.id}, prezzo {prezzo}")
    db.session.commit()
    flash(f"Approvato: {prodotto.nome}", "ok")
    return redirect(url_for(".attesa"))


@bp.post("/<int:prodotto_id>/rifiuta")
@richiede_ruolo("admin")
def rifiuta(prodotto_id):
    prodotto = _in_attesa(prodotto_id)
    if prodotto is None:
        flash("Prodotto gia' gestito", "errore")
        return redirect(url_for(".attesa"))
    for lotto in prodotto.lotti:
        quantita = lotto.qta_esposta + lotto.qta_magazzino
        if quantita > 0:
            db.session.add(Scarto(lotto_id=lotto.id, quantita=quantita,
                                  motivo="non_conforme", utente_id=g.utente.id))
            lotto.qta_esposta = 0
            lotto.qta_magazzino = 0
    prodotto.stato = "rimosso"
    _chiudi_notifiche(prodotto.id, "da_approvare")
    registra("prodotto_rifiutato", g.utente.id, f"prodotto {prodotto.id}")
    db.session.commit()
    flash(f"Rifiutato: {prodotto.nome}", "ok")
    return redirect(url_for(".attesa"))
