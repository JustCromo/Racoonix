"""Configurazione iniziale dal browser, protetta da un codice monouso.

Una pagina di configurazione aperta a chiunque sarebbe una finestra d'attacco: chi arriva per primo
potrebbe prendersi l'account admin. Quindi: il codice lo vede solo chi ha accesso al server (terminale),
vale 24 ore, nel db se ne salva solo l'impronta, e a configurazione finita la pagina sparisce per sempre."""
import hashlib
import hmac
import ipaddress
import os
import re
import secrets
import sys
from datetime import datetime, timedelta, timezone

from flask import Blueprint, flash, redirect, render_template, request, session, url_for

from . import db, limiter, negozio
from .lingua import LINGUE, _

bp = Blueprint("configurazione", __name__, url_prefix="/configurazione")
DURATA = timedelta(hours=24)
NOME_OK = re.compile(r"^[\w .,'&-]{2,60}$")
USERNAME_OK = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
MIN_PASSWORD = 12
RETE_DOCKER = ipaddress.ip_network("172.16.0.0/12")


def _impronta(codice):
    return hashlib.sha256(codice.encode()).hexdigest()


def _salvato():
    from .models import Impostazione
    voce = db.session.get(Impostazione, "configurazione.codice")
    if voce is None or "|" not in voce.valore:
        return None, None
    impronta, scadenza = voce.valore.split("|", 1)
    try:
        return impronta, datetime.fromisoformat(scadenza)
    except ValueError:
        return None, None


def nuovo_codice():
    """Genera un codice nuovo (quello vecchio smette di valere) e lo restituisce in chiaro, una volta sola."""
    from .models import Impostazione
    codice = secrets.token_urlsafe(24)
    voce = db.session.get(Impostazione, "configurazione.codice") or Impostazione(chiave="configurazione.codice", valore="")
    voce.valore = f"{_impronta(codice)}|{(datetime.now(timezone.utc) + DURATA).isoformat()}"
    db.session.add(voce)
    db.session.commit()
    return codice


def _codice_valido(impronta_data):
    impronta, scadenza = _salvato()
    if not impronta or not isinstance(impronta_data, str):
        return False
    return hmac.compare_digest(impronta, impronta_data) and datetime.now(timezone.utc) < scadenza


def _cancella_codice():
    from .models import Impostazione
    voce = db.session.get(Impostazione, "configurazione.codice")
    if voce:
        db.session.delete(voce)


def _valori_iniziali():
    valori = dict(negozio.impostazioni())
    lingua = session.get("lingua_configurazione") or valori["lingua"]
    if "paese" not in request.form and not os.environ.get("RACOONIX_PAESE"):
        valori["paese"] = "IT" if lingua == "it" else "GB"
    ip = request.remote_addr or ""
    return {"lingua": lingua, "paese": valori["paese"], "fuso": valori["fuso"],
            "nome": "" if valori["nome"] == "Racoonix" else valori["nome"], "ip_admin": ip, "username": ""}


def _leggi_modulo():
    f = request.form
    dati = {k: (f.get(k) or "").strip() for k in ("lingua", "paese", "fuso", "nome", "ip_admin", "username")}
    from .formato import testo_pulito
    dati["nome"] = testo_pulito(dati["nome"])
    password, conferma = f.get("password") or "", f.get("conferma") or ""
    errori = []
    if dati["lingua"] not in LINGUE:
        errori.append(_("Scegli la lingua del negozio"))
    if dati["paese"] not in negozio.PAESI:
        errori.append(_("Scegli il paese del negozio"))
    if not negozio.fuso_valido(dati["fuso"]):
        errori.append(_("Fuso orario non valido: sceglilo dall'elenco"))
    if not NOME_OK.match(dati["nome"]):
        errori.append(_("Nome del negozio non valido (2-60 caratteri)"))
    try:
        ip = ipaddress.ip_address(dati["ip_admin"])
    except ValueError:
        ip = None
        errori.append(_("Indirizzo del computer dell'amministratore non valido"))
    if not USERNAME_OK.match(dati["username"]):
        errori.append(_("Username non valido (3-40 caratteri: lettere, numeri, _ . -)"))
    if len(password) < MIN_PASSWORD:
        errori.append(_("La password deve avere almeno %(numero)s caratteri", numero=MIN_PASSWORD))
    elif password != conferma:
        errori.append(_("Le due password non coincidono"))
    reti = []
    if ip is not None:
        reti.append(f"{ip}/{ip.max_prefixlen}")
        # Se l'admin usa il browser sul server stesso, le richieste arrivano dalla rete interna di Docker
        if ip in RETE_DOCKER:
            reti.append(str(RETE_DOCKER))
    return dati, password, ",".join(reti), errori


@bp.route("/", methods=["GET", "POST"])
@limiter.limit("20 per minute")
def pagina():
    from .auth import ph, registra
    from .models import Ruolo, Utente
    if negozio.configurato():
        # Link gia' usato: niente errore, una pagina che porta al login. La configurazione resta chiusa.
        return render_template("configurazione_attesa.html", gia_configurato=True)
    lingua = request.args.get("lingua")
    if lingua in LINGUE:
        session["lingua_configurazione"] = lingua
    codice = request.args.get("codice")
    if codice is not None:
        impronta = _impronta(codice[:100])
        if not _codice_valido(impronta):
            registra("configurazione_codice_errato", None)
            db.session.commit()
            return render_template("configurazione_attesa.html", errore=True), 403
        # Il modulo si mostra subito, senza reindirizzare: arrivando da un QR o da un link esterno,
        # il browser non rimanderebbe il cookie di sessione (SameSite=Strict) dopo un reindirizzamento.
        session["configurazione"] = impronta
    if not _codice_valido(session.get("configurazione")):
        if lingua in LINGUE:
            return redirect(url_for(".pagina"))
        return render_template("configurazione_attesa.html"), 403
    if lingua in LINGUE:
        return redirect(url_for(".pagina"))

    contesto = {"fusi": negozio.gruppi_fusi(), "paesi": negozio.PAESI}
    if request.method == "GET":
        return render_template("configurazione.html", valori=_valori_iniziali(), errori=[], **contesto)

    dati, password, reti, errori = _leggi_modulo()
    if not errori and db.session.scalar(db.select(Utente.id).filter_by(username=dati["username"])):
        errori.append(_("Username gia' in uso"))
    if errori:
        return render_template("configurazione.html", valori=dati, errori=errori, **contesto), 400

    admin = Utente(username=dati["username"], password_hash=ph.hash(password), deve_cambiare_password=False,
                   lingua=dati["lingua"])
    admin.ruoli.append(db.session.scalar(db.select(Ruolo).filter_by(nome="admin")))
    db.session.add(admin)
    negozio.salva(nome=dati["nome"], lingua=dati["lingua"], paese=dati["paese"], fuso=dati["fuso"],
                  reti_admin=reti, configurato="1")
    _cancella_codice()
    db.session.flush()
    registra("configurazione_completata", admin.id, f"{dati['paese']}, {dati['lingua']}, {dati['fuso']}")
    db.session.commit()
    session.clear()
    flash(_("Configurazione completata: entra con il tuo account."), "ok")
    return redirect(url_for("auth.login"))


def main():
    """Dal server: ./racoonix.sh link. Mostra il link della configurazione, anche come QR nel terminale."""
    import segno
    from . import create_app
    app = create_app()
    with app.app_context():
        if negozio.configurato():
            print("Racoonix e' gia' configurato. / Racoonix is already set up.")
            return 0
        codice = nuovo_codice()
    ip = os.environ.get("RACOONIX_IP") or "localhost"
    nome = os.environ.get("RACOONIX_NOME") or "racoonix.local"
    link = f"https://{ip}/configurazione/?codice={codice}"
    print("\nApri questo link dal computer dell'amministratore (vale 24 ore, una volta sola):")
    print("Open this link from the administrator's computer (valid for 24 hours, once only):\n")
    print(f"  {link}")
    print(f"  https://{nome}/configurazione/?codice={codice}\n")
    segno.make(link, error="l").terminal(compact=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
