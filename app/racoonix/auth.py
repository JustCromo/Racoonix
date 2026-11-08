import ipaddress
import secrets
from datetime import datetime, timedelta, timezone
from functools import wraps

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError
from flask import (Blueprint, abort, current_app, g, make_response, redirect, render_template,
                   request, session, url_for)

from . import db, limiter
from .models import AuditLog, Utente

bp = Blueprint("auth", __name__)
ph = PasswordHasher()
HASH_FINTO = ph.hash("hash-finto-per-tempi-di-risposta-costanti")
MAX_TENTATIVI = 5
DURATA_BLOCCO = timedelta(minutes=15)
MIN_PASSWORD = 12
ERRORE_LOGIN = ("Accesso non riuscito. Se e' il primo accesso da questo dispositivo, "
                "potrebbe servire l'approvazione dell'amministratore.")


def _adesso():
    return datetime.now(timezone.utc)


def _verifica(hash_salvato, password):
    try:
        return ph.verify(hash_salvato, password)
    except (VerificationError, InvalidHashError):
        return False


def _percorso_interno(percorso):
    return (isinstance(percorso, str) and percorso.startswith("/")
            and not percorso.startswith(("//", "/\\")))


def _vai_al_login():
    if request.method == "GET" and _percorso_interno(request.path):
        session["dopo_login"] = request.path
    return redirect(url_for("auth.login"))


def registra(azione, utente_id=None, dettaglio=None):
    db.session.add(AuditLog(azione=azione, utente_id=utente_id,
                            dettaglio=dettaglio, ip=request.remote_addr))


def ip_admin_consentito():
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return False
    return any(ip in rete for rete in current_app.config["ADMIN_RETI"])


def ruoli_attivi():
    if g.get("utente") is None:
        return set()
    nomi = {r.nome for r in g.utente.ruoli}
    if "admin" in nomi and not ip_admin_consentito():
        nomi.discard("admin")
    return nomi


def carica_utente():
    g.utente = None
    if request.endpoint == "static":
        return
    uid, token = session.get("uid"), session.get("token")
    if not uid or not token:
        return
    utente = db.session.get(Utente, uid)
    if (utente and utente.attivo and utente.token_sessione
            and secrets.compare_digest(utente.token_sessione, token) and _dispositivo_ok(utente)):
        g.utente = utente
    else:
        destinazione = session.get("dopo_login")
        session.clear()
        if destinazione:
            session["dopo_login"] = destinazione


def _dispositivo_ok(utente):
    from .accessi import sessione_valida
    return sessione_valida(utente)


def obbligo_cambio_password():
    consentiti = ("auth.cambia_password", "auth.logout", "static")
    if g.utente and g.utente.deve_cambiare_password and request.endpoint not in consentiti:
        return redirect(url_for("auth.cambia_password"))


def login_richiesto(vista):
    @wraps(vista)
    def wrapper(*args, **kwargs):
        if g.utente is None:
            return _vai_al_login()
        return vista(*args, **kwargs)
    return wrapper


def richiede_ruolo(*ruoli):
    def decoratore(vista):
        @wraps(vista)
        def wrapper(*args, **kwargs):
            if g.utente is None:
                return _vai_al_login()
            attivi = ruoli_attivi()
            if "admin" in attivi or attivi.intersection(ruoli):
                return vista(*args, **kwargs)
            abort(403)
        return wrapper
    return decoratore


@bp.route("/login", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
def login():
    from .accessi import assicura_cookie, controlla_al_login, imposta_cookie
    if g.utente:
        return redirect(url_for("home"))
    if request.method == "GET":
        return assicura_cookie(make_response(render_template("login.html")))

    username = (request.form.get("username") or "").strip()[:40]
    password = request.form.get("password") or ""
    utente = db.session.scalar(db.select(Utente).filter_by(username=username)) if username else None
    adesso = _adesso()

    if utente is None or not utente.attivo:
        _verifica(HASH_FINTO, password)
        esito = "fallito"
    elif utente.bloccato_fino and utente.bloccato_fino > adesso:
        _verifica(HASH_FINTO, password)
        esito = "bloccato"
    elif _verifica(utente.password_hash, password):
        esito = "ok"
    else:
        esito = "fallito"

    if esito == "ok":
        from .accessi import controlla_al_login, imposta_cookie
        controllo = controlla_al_login(utente)
        if not controllo.ammesso:
            # Stessa risposta di una password sbagliata: il motivo vero resta solo nel log di audit.
            db.session.commit()
            risposta = make_response(render_template("login.html", errore=ERRORE_LOGIN), 401)
            return imposta_cookie(risposta, controllo.token_nuovo)
        if ph.check_needs_rehash(utente.password_hash):
            utente.password_hash = ph.hash(password)
        utente.tentativi_falliti = 0
        utente.bloccato_fino = None
        utente.token_sessione = secrets.token_hex(32)
        registra("login_ok", utente.id)
        if utente.ha_ruolo("admin") and not ip_admin_consentito():
            registra("admin_ip_non_consentito", utente.id)
        db.session.commit()
        destinazione = session.get("dopo_login")
        session.clear()
        session.permanent = True
        session["uid"] = utente.id
        session["token"] = utente.token_sessione
        session["dispositivo"] = controllo.dispositivo_id
        if _percorso_interno(destinazione):
            return imposta_cookie(redirect(destinazione), controllo.token_nuovo)
        return imposta_cookie(redirect(url_for("home")), controllo.token_nuovo)

    if esito == "fallito" and utente is not None and utente.attivo:
        utente.tentativi_falliti += 1
        if utente.tentativi_falliti >= MAX_TENTATIVI:
            utente.bloccato_fino = adesso + DURATA_BLOCCO
            utente.tentativi_falliti = 0
            registra("account_bloccato", utente.id)
    registra(f"login_{esito}", utente.id if utente else None)
    db.session.commit()
    return assicura_cookie(make_response(render_template("login.html", errore=ERRORE_LOGIN), 401))


@bp.post("/logout")
def logout():
    if g.utente:
        g.utente.token_sessione = None
        registra("logout", g.utente.id)
        db.session.commit()
    session.clear()
    return redirect(url_for("auth.login"))


@bp.route("/cambia-password", methods=["GET", "POST"])
@limiter.limit("10 per minute", methods=["POST"])
@login_richiesto
def cambia_password():
    if not g.utente.deve_cambiare_password and "admin" not in ruoli_attivi():
        abort(403)
    if request.method == "GET":
        return render_template("cambia_password.html")

    attuale = request.form.get("attuale") or ""
    nuova = request.form.get("nuova") or ""
    conferma = request.form.get("conferma") or ""
    errore = None
    if not _verifica(g.utente.password_hash, attuale):
        errore = "Password attuale errata"
    elif len(nuova) < MIN_PASSWORD:
        errore = f"La nuova password deve avere almeno {MIN_PASSWORD} caratteri"
    elif nuova == attuale:
        errore = "La nuova password deve essere diversa dalla attuale"
    elif nuova != conferma:
        errore = "Le due password non coincidono"
    if errore:
        return render_template("cambia_password.html", errore=errore), 400

    g.utente.password_hash = ph.hash(nuova)
    g.utente.deve_cambiare_password = False
    g.utente.token_sessione = secrets.token_hex(32)
    session["token"] = g.utente.token_sessione
    registra("cambio_password", g.utente.id)
    db.session.commit()
    return redirect(url_for("home"))


@bp.route("/password-dimenticata", methods=["GET", "POST"])
@limiter.limit("5 per 15 minutes", methods=["POST"])
def password_dimenticata():
    """La risposta e' sempre la stessa: non rivela se l'username esiste."""
    if g.utente:
        return redirect(url_for("home"))
    if request.method == "GET":
        return render_template("password_dimenticata.html")
    from .notifiche import _apri
    username = (request.form.get("username") or "").strip()[:40]
    utente = db.session.scalar(db.select(Utente).filter_by(username=username)) if username else None
    if utente and utente.attivo:
        _apri("reset_password", None, "admin",
              f"{utente.username} ha chiesto di reimpostare la password", utente_id=utente.id)
        registra("richiesta_reset_password", utente.id)
    db.session.commit()
    return render_template("password_dimenticata.html", inviata=True)


@bp.post("/tema")
@login_richiesto
def cambia_tema():
    """Il tema si salva nel profilo: segue l'utente su ogni dispositivo."""
    from urllib.parse import urlsplit
    g.utente.tema = "scuro" if g.utente.tema == "chiaro" else "chiaro"
    db.session.commit()
    ritorno = urlsplit(request.referrer or "").path
    return redirect(ritorno if _percorso_interno(ritorno) else url_for("home"))
