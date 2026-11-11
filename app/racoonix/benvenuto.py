"""Primo accesso con il QR: il dipendente inquadra il codice che l'admin gli mostra, sceglie la sua password
e il suo telefono diventa subito un dispositivo approvato. Niente password temporanea da ricopiare.

Sicurezza: il QR lo genera l'admin e lo mostra di persona; il codice vale 30 minuti e una volta sola,
nel db se ne salva solo l'impronta, e il modulo si mostra senza reindirizzamenti (un QR arriva "da fuori",
e i cookie SameSite=Strict non tornerebbero dopo un reindirizzamento)."""
import hmac
import os
import secrets
import time
from datetime import datetime, timedelta, timezone

import segno
from flask import Blueprint, redirect, render_template, request, session, url_for
from markupsafe import Markup

from . import db, limiter
from .accessi import COOKIE, DURATA_COOKIE, descrivi, impronta
from .lingua import _

bp = Blueprint("benvenuto", __name__, url_prefix="/benvenuto")
DURATA = timedelta(minutes=30)
MIN_PASSWORD = 12


def _adesso():
    return datetime.now(timezone.utc)


def prepara(utente):
    """Chiamata quando l'admin crea un utente o genera una password temporanea. Restituisce link e QR."""
    codice = secrets.token_urlsafe(24)
    utente.benvenuto_hash = impronta(codice)
    utente.benvenuto_scade = _adesso() + DURATA
    indirizzo = os.environ.get("RACOONIX_INDIRIZZO") or request.host
    link = f"https://{indirizzo}/benvenuto/?codice={codice}"
    qr = segno.make(link, error="m").svg_inline(scale=5, dark="#2E3A59", light="#FFFFFF", border=2)
    return link, Markup(qr)  # nosec B704 - SVG generato dal server da un link creato dal server


def annulla(utente):
    utente.benvenuto_hash = None
    utente.benvenuto_scade = None


def _utente(impronta_codice):
    from .models import Utente
    if not impronta_codice:
        return None
    utente = db.session.scalar(db.select(Utente).filter_by(benvenuto_hash=impronta_codice))
    if (utente is None or not utente.attivo or utente.eliminato or not utente.benvenuto_scade
            or utente.benvenuto_scade < _adesso() or not hmac.compare_digest(utente.benvenuto_hash, impronta_codice)):
        return None
    return utente


@bp.route("/", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def pagina():
    from .auth import ph, registra
    from .models import DispositivoAccesso
    codice = request.args.get("codice")
    if codice is not None:
        utente = _utente(impronta(codice[:100]))
        if utente is None:
            registra("benvenuto_codice_errato", None)
            db.session.commit()
            return render_template("benvenuto.html", errore_link=True), 403
        session["benvenuto"] = utente.benvenuto_hash
    else:
        utente = _utente(session.get("benvenuto"))
        if utente is None:
            return render_template("benvenuto.html", errore_link=True), 403
    if request.method == "GET":
        return render_template("benvenuto.html", utente=utente, errori=[])

    password, conferma = request.form.get("password") or "", request.form.get("conferma") or ""
    errori = []
    if len(password) < MIN_PASSWORD:
        errori.append(_("La password deve avere almeno %(numero)s caratteri", numero=MIN_PASSWORD))
    elif password != conferma:
        errori.append(_("Le due password non coincidono"))
    if errori:
        return render_template("benvenuto.html", utente=utente, errori=errori), 400

    adesso = _adesso()
    utente.password_hash = ph.hash(password)
    utente.deve_cambiare_password = False
    utente.tentativi_falliti = 0
    utente.bloccato_fino = None
    utente.token_sessione = secrets.token_hex(32)
    annulla(utente)
    # Il telefono che ha inquadrato il QR mostrato dall'admin diventa un dispositivo approvato
    token = secrets.token_urlsafe(32)
    dispositivo = DispositivoAccesso(utente_id=utente.id, token_hash=impronta(token),
                                     descrizione=descrivi(request.headers.get("User-Agent", "")),
                                     stato="approvato", approvato_il=adesso, creato_il=adesso,
                                     ultimo_uso=adesso, ultimo_ip=request.remote_addr)
    db.session.add(dispositivo)
    db.session.flush()
    registra("benvenuto_usato", utente.id, f"{utente.username}: {dispositivo.descrizione}")
    db.session.commit()
    session.clear()
    session.permanent = True
    session["uid"] = utente.id
    session["token"] = utente.token_sessione
    session["dispositivo"] = dispositivo.id
    session["attivita"] = time.time()
    risposta = redirect(url_for("home"))
    risposta.set_cookie(COOKIE, token, max_age=DURATA_COOKIE, secure=True, httponly=True, samesite="Strict")
    return risposta
