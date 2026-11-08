import re
import secrets
from datetime import datetime, timezone

from flask import (Blueprint, g, make_response, redirect, render_template,
                   request, url_for)

from . import db
from .auth import ph, registra, richiede_ruolo
from .models import Ruolo, Utente

bp = Blueprint("utenti", __name__, url_prefix="/admin/utenti")
USERNAME_OK = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")


def _password_temporanea():
    return secrets.token_urlsafe(12)


def _tutti_i_ruoli():
    return db.session.scalars(db.select(Ruolo).order_by(Ruolo.id)).all()


def _ruoli_dal_form():
    nomi = set(request.form.getlist("ruoli"))
    if not nomi:
        return []
    return db.session.scalars(db.select(Ruolo).where(Ruolo.nome.in_(nomi))).all()


def _altri_admin_attivi(utente_id):
    ruolo_admin = db.session.scalar(db.select(Ruolo).filter_by(nome="admin"))
    return db.session.scalar(
        db.select(db.func.count(Utente.id)).where(
            Utente.ruoli.contains(ruolo_admin),
            Utente.attivo.is_(True),
            Utente.id != utente_id,
        )
    )


RUOLI_FILTRO = ("admin", "magazziniere", "dipendente")
STATI_FILTRO = ("attivo", "disattivato", "bloccato", "temporanea")


def _cerca_utenti():
    q = (request.args.get("q") or "").strip()[:40]
    ruolo = request.args.get("ruolo") if request.args.get("ruolo") in RUOLI_FILTRO else ""
    stato = request.args.get("stato") if request.args.get("stato") in STATI_FILTRO else ""
    stmt = db.select(Utente).order_by(Utente.username)
    if q:
        sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Utente.username.ilike(f"%{sicuro}%", escape="\\"))
    if ruolo:
        stmt = stmt.where(Utente.ruoli.any(Ruolo.nome == ruolo))
    adesso = datetime.now(timezone.utc)
    if stato == "attivo":
        stmt = stmt.where(Utente.attivo.is_(True))
    elif stato == "disattivato":
        stmt = stmt.where(Utente.attivo.is_(False))
    elif stato == "bloccato":
        stmt = stmt.where(Utente.bloccato_fino > adesso)
    elif stato == "temporanea":
        stmt = stmt.where(Utente.deve_cambiare_password.is_(True))
    return db.session.scalars(stmt).all(), q, ruolo, stato


def _elenco(errore=None, codice=200):
    utenti, q, ruolo, stato = _cerca_utenti()
    return render_template("utenti.html", utenti=utenti, ruoli=_tutti_i_ruoli(), errore=errore,
                           adesso=datetime.now(timezone.utc), q=q, ruolo=ruolo, stato=stato), codice


@bp.get("/risultati")
@richiede_ruolo("admin")
def risultati():
    utenti, _, _, _ = _cerca_utenti()
    return render_template("_utenti_risultati.html", utenti=utenti, ruoli=_tutti_i_ruoli(),
                           adesso=datetime.now(timezone.utc))


def _mostra_password(utente, password):
    risposta = make_response(render_template("utenti_password.html",
                                             utente=utente, password=password))
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


@bp.get("/")
@richiede_ruolo("admin")
def elenco():
    return _elenco()


@bp.route("/nuovo", methods=["GET", "POST"])
@richiede_ruolo("admin")
def nuovo():
    if request.method == "GET":
        return render_template("utenti_nuovo.html", ruoli=_tutti_i_ruoli())

    username = (request.form.get("username") or "").strip()
    scelti = _ruoli_dal_form()
    errore = None
    if not USERNAME_OK.match(username):
        errore = "Username non valido (3-40 caratteri: lettere, numeri, _ . -)"
    elif not scelti:
        errore = "Scegli almeno un ruolo"
    elif db.session.scalar(db.select(Utente).filter_by(username=username)):
        errore = "Username gia' in uso"
    if errore:
        return render_template("utenti_nuovo.html", ruoli=_tutti_i_ruoli(),
                               errore=errore, username=username), 400

    password = _password_temporanea()
    utente = Utente(username=username, password_hash=ph.hash(password),
                    deve_cambiare_password=True)
    utente.ruoli = list(scelti)
    db.session.add(utente)
    registra("utente_creato", g.utente.id,
             f"{username}: {', '.join(r.nome for r in scelti)}")
    db.session.commit()
    return _mostra_password(utente, password)


@bp.post("/<int:utente_id>/ruoli")
@richiede_ruolo("admin")
def ruoli(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    scelti = _ruoli_dal_form()
    if not scelti:
        return _elenco("Ogni utente deve avere almeno un ruolo", 400)
    toglie_admin = utente.ha_ruolo("admin") and not any(r.nome == "admin" for r in scelti)
    if toglie_admin and utente.id == g.utente.id:
        return _elenco("Non puoi togliere il ruolo admin a te stesso", 400)
    if toglie_admin and _altri_admin_attivi(utente.id) == 0:
        return _elenco("Deve restare almeno un admin attivo", 400)
    utente.ruoli = list(scelti)
    registra("ruoli_modificati", g.utente.id,
             f"{utente.username}: {', '.join(r.nome for r in scelti)}")
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/attivo")
@richiede_ruolo("admin")
def attivo(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.id == g.utente.id:
        return _elenco("Non puoi disattivare te stesso", 400)
    if utente.attivo and utente.ha_ruolo("admin") and _altri_admin_attivi(utente.id) == 0:
        return _elenco("Deve restare almeno un admin attivo", 400)
    utente.attivo = not utente.attivo
    if not utente.attivo:
        utente.token_sessione = None
    registra("utente_riattivato" if utente.attivo else "utente_disattivato",
             g.utente.id, utente.username)
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/sblocca")
@richiede_ruolo("admin")
def sblocca(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra("utente_sbloccato", g.utente.id, utente.username)
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/reset-password")
@richiede_ruolo("admin")
def reset_password(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.id == g.utente.id:
        return _elenco("Per te stesso usa 'Cambia password'", 400)
    password = _password_temporanea()
    utente.password_hash = ph.hash(password)
    utente.deve_cambiare_password = True
    utente.token_sessione = None
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra("password_resettata", g.utente.id, utente.username)
    _chiudi_richieste_reset(utente.id)
    db.session.commit()
    return _mostra_password(utente, password)


def _chiudi_richieste_reset(utente_id):
    """Quando l'admin genera la password, la richiesta risulta gestita da lui."""
    from .models import Notifica
    for notifica in db.session.scalars(db.select(Notifica).filter_by(
            tipo="reset_password", utente_id=utente_id, stato="aperta")):
        notifica.stato = "chiusa"
        notifica.chiusa_da = g.utente.id
        notifica.chiusa_il = datetime.now(timezone.utc)
