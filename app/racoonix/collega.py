"""Collega un telefono: QR per scaricare il certificato della CA e aprire Racoonix."""
import base64
import hashlib
import os
import urllib.request

import segno
from flask import Blueprint, render_template
from markupsafe import Markup

from .auth import richiede_ruolo

bp = Blueprint("collega", __name__, url_prefix="/admin/collega")


def _impronta_certificato():
    """Chiede il certificato a Caddy come un visitatore qualsiasi: l'app non tocca i file di Caddy."""
    try:
        with urllib.request.urlopen("http://caddy/racoonix-ca.crt", timeout=3) as risposta:  # nosec B310 - URL fisso interno, nessun input dell'utente
            pem = risposta.read(10_000).decode("ascii")
    except (OSError, ValueError):
        return None
    corpo = "".join(riga for riga in pem.splitlines() if riga and not riga.startswith("-----"))
    try:
        der = base64.b64decode(corpo, validate=True)
    except ValueError:
        return None
    esadecimale = hashlib.sha256(der).hexdigest().upper()
    return ":".join(esadecimale[i:i + 2] for i in range(0, len(esadecimale), 2))


def _qr(testo):
    # Il contenuto e' generato dal server a partire dalla configurazione, mai da input dell'utente.
    return Markup(segno.make(testo, error="m").svg_inline(scale=5, dark="#2E3A59", light="#FFFFFF", border=2))  # nosec B704 - SVG generato dal server da un URL di configurazione


@bp.get("/")
@richiede_ruolo("admin")
def pagina():
    indirizzo = os.environ.get("RACOONIX_INDIRIZZO", "localhost")
    url_certificato = f"http://{indirizzo}/racoonix-ca.crt"
    url_app_ip = f"https://{indirizzo}/"
    url_app = f"https://{os.environ.get('RACOONIX_NOME') or indirizzo}/"
    return render_template("collega.html", url_certificato=url_certificato, url_app=url_app, url_app_ip=url_app_ip,
                           qr_certificato=_qr(url_certificato), qr_app=_qr(url_app),
                           impronta=_impronta_certificato())
