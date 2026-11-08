"""Gestione dei dispositivi collegati: ogni cassa o bilancia ha la sua chiave, revocabile."""
import hashlib
import re
import secrets

from flask import Blueprint, flash, g, make_response, redirect, render_template, request, url_for

from . import db
from .auth import registra, richiede_ruolo
from .models import Dispositivo

bp = Blueprint("dispositivi", __name__, url_prefix="/admin/dispositivi")
NOME_OK = re.compile(r"^[\w .'()/-]{2,60}$")


@bp.get("/")
@richiede_ruolo("admin")
def elenco():
    dispositivi = db.session.scalars(db.select(Dispositivo).order_by(Dispositivo.creato_il.desc())).all()
    return render_template("dispositivi.html", dispositivi=dispositivi)


@bp.post("/nuovo")
@richiede_ruolo("admin")
def nuovo():
    nome = (request.form.get("nome") or "").strip()
    tipo = request.form.get("tipo")
    if not NOME_OK.match(nome) or tipo not in ("cassa", "bilancia"):
        flash("Nome o tipo non validi", "errore")
        return redirect(url_for(".elenco"))
    if db.session.scalar(db.select(Dispositivo.id).filter_by(nome=nome)):
        flash("Esiste gia' un dispositivo con questo nome", "errore")
        return redirect(url_for(".elenco"))
    token = "rcx_" + secrets.token_urlsafe(32)
    dispositivo = Dispositivo(nome=nome, tipo=tipo, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                              prefisso=token[:10], creato_da=g.utente.id)
    db.session.add(dispositivo)
    registra("dispositivo_creato", g.utente.id, f"{nome} ({tipo})")
    db.session.commit()
    risposta = make_response(render_template("dispositivo_token.html", d=dispositivo, token=token))
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


@bp.post("/<int:did>/revoca")
@richiede_ruolo("admin")
def revoca(did):
    dispositivo = db.get_or_404(Dispositivo, did)
    dispositivo.attivo = False
    registra("dispositivo_revocato", g.utente.id, dispositivo.nome)
    db.session.commit()
    flash(f"Chiave di {dispositivo.nome} revocata definitivamente", "ok")
    return redirect(url_for(".elenco"))
