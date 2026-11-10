"""Dispositivi di accesso: ogni utente entra solo dai suoi dispositivi personali approvati dall'admin."""
import hashlib
import re
import secrets
from dataclasses import dataclass
from datetime import datetime, timezone

from flask import request, session

from . import db
from .lingua import testo_negozio
from .models import DispositivoAccesso, Utente

COOKIE = "rx_dispositivo"
DURATA_COOKIE = 400 * 24 * 3600
TOKEN_OK = re.compile(r"^[A-Za-z0-9_-]{40,60}$")
MAX_IN_ATTESA = 5
NON_AUTORIZZATO = "Questo dispositivo non e' autorizzato ad accedere."
IN_ATTESA = "Dispositivo registrato: l'amministratore deve approvarlo prima del primo accesso."


@dataclass
class Esito:
    ammesso: bool
    messaggio: str = ""
    token_nuovo: str | None = None
    dispositivo_id: int | None = None


def _adesso():
    return datetime.now(timezone.utc)


def impronta(token):
    return hashlib.sha256(token.encode()).hexdigest()


def descrivi(user_agent):
    """Solo browser e sistema: il resto dell'User-Agent non serve, quindi non lo conserviamo."""
    ua = user_agent or ""
    sistemi = (("Android", "Android"), ("iPhone", "iPhone"), ("iPad", "iPad"),
               ("Windows", "Windows"), ("Mac OS", "Mac"), ("Linux", "Linux"))
    browser = (("Edg/", "Edge"), ("SamsungBrowser", "Samsung Internet"), ("Firefox/", "Firefox"),
               ("Chrome/", "Chrome"), ("Safari/", "Safari"))
    s = next((nome for chiave, nome in sistemi if chiave in ua), "?")
    b = next((nome for chiave, nome in browser if chiave in ua), "?")
    return f"{b} \u00b7 {s}"


def _token_browser():
    token = request.cookies.get(COOKIE, "")
    if TOKEN_OK.match(token):
        return token, None
    nuovo = secrets.token_urlsafe(32)
    return nuovo, nuovo


def controlla_al_login(utente):
    """Password gia' verificata: ora si decide se questo dispositivo puo' entrare con questo account."""
    from .auth import ip_admin_consentito, registra
    from .notifiche import _apri
    token, nuovo = _token_browser()
    firma = impronta(token)

    if db.session.scalar(db.select(DispositivoAccesso.id).filter_by(token_hash=firma, stato="revocato").limit(1)):
        registra("login_dispositivo_bloccato", utente.id)
        return Esito(False, NON_AUTORIZZATO, nuovo)

    dispositivo = db.session.scalar(db.select(DispositivoAccesso).filter_by(utente_id=utente.id, token_hash=firma))
    if dispositivo is None:
        automatico = utente.ha_ruolo("admin") and ip_admin_consentito()
        in_attesa = db.session.scalar(db.select(db.func.count(DispositivoAccesso.id))
                                      .filter_by(utente_id=utente.id, stato="in_attesa"))
        if not automatico and in_attesa >= MAX_IN_ATTESA:
            return Esito(False, IN_ATTESA, nuovo)
        descrizione = descrivi(request.headers.get("User-Agent"))
        dispositivo = DispositivoAccesso(utente_id=utente.id, token_hash=firma, descrizione=descrizione,
                                         stato="approvato" if automatico else "in_attesa",
                                         approvato_il=_adesso() if automatico else None)
        db.session.add(dispositivo)
        db.session.flush()
        if automatico:
            registra("dispositivo_approvato", utente.id, f"{descrizione} (admin da IP autorizzato)")
        else:
            altri = db.session.scalars(
                db.select(Utente.username).join(DispositivoAccesso, DispositivoAccesso.utente_id == Utente.id)
                .where(DispositivoAccesso.token_hash == firma, DispositivoAccesso.utente_id != utente.id)).all()
            nota = testo_negozio("%(utente)s chiede di accedere da %(dispositivo)s", utente=utente.username, dispositivo=descrizione)
            if altri:
                nota += testo_negozio(". Attenzione: browser gia' registrato da %(utenti)s", utenti=", ".join(altri))
            registra("dispositivo_nuovo", utente.id, descrizione)
            _apri("dispositivo", None, "admin", nota, utente_id=utente.id)

    if dispositivo.stato != "approvato":
        return Esito(False, IN_ATTESA if dispositivo.stato == "in_attesa" else NON_AUTORIZZATO, nuovo)
    dispositivo.ultimo_uso = _adesso()
    dispositivo.ultimo_ip = request.remote_addr
    return Esito(True, token_nuovo=nuovo, dispositivo_id=dispositivo.id)


def imposta_cookie(risposta, token):
    if token:
        risposta.set_cookie(COOKIE, token, max_age=DURATA_COOKIE, secure=True, httponly=True, samesite="Strict")
    return risposta


def sessione_valida(utente):
    """A ogni richiesta: la sessione deve appartenere a un dispositivo ancora approvato di questo utente."""
    dispositivo_id = session.get("dispositivo")
    if not dispositivo_id:
        return False
    dispositivo = db.session.get(DispositivoAccesso, dispositivo_id)
    token = request.cookies.get(COOKIE, "")
    return (dispositivo is not None and dispositivo.utente_id == utente.id and dispositivo.stato == "approvato"
            and TOKEN_OK.match(token) is not None and secrets.compare_digest(dispositivo.token_hash, impronta(token)))


def revoca_tutti(utente_id):
    for dispositivo in db.session.scalars(db.select(DispositivoAccesso).where(
            DispositivoAccesso.utente_id == utente_id, DispositivoAccesso.stato != "revocato")):
        dispositivo.stato = "revocato"


def assicura_cookie(risposta):
    """Ogni visitatore della pagina di login riceve il cookie del dispositivo, prima ancora della password:
    cosi' la sua comparsa non rivela se una password era giusta."""
    if not TOKEN_OK.match(request.cookies.get(COOKIE, "")):
        imposta_cookie(risposta, secrets.token_urlsafe(32))
    return risposta
