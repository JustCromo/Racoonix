from datetime import date

from flask import Blueprint, current_app, render_template, request

from . import codici
from .auth import login_richiesto

bp = Blueprint("scanner_test", __name__)


@bp.get("/test-scanner")
@login_richiesto
def pagina():
    return render_template("test_scanner.html")


@bp.post("/test-scanner/analizza")
@login_richiesto
def analizza():
    dati = request.get_json(silent=True) or {}
    try:
        risultato = codici.riconosci(dati.get("codice"), current_app.config["BILANCIA_PREFISSI"])
    except codici.CodiceNonValido as errore:
        return {"errore": str(errore)}, 400
    return {k: (v.isoformat() if isinstance(v, date) else v) for k, v in risultato.items()}
