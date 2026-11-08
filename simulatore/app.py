"""Simulatore delle apparecchiature del negozio (cassa e bilancia del banco).
E' un sistema separato: non vede il database e comunica con Racoonix solo tramite API."""
import hashlib
import os
import time
import uuid
from pathlib import Path

import requests
from flask import Flask, flash, redirect, render_template, request, session, url_for
from flask_wtf.csrf import CSRFProtect

SECRETS = Path("/run/secrets")
API = os.environ.get("RACOONIX_API", "http://app:8000/api/v1")
MAX_RIGHE = 20
DOPPIA_LETTURA_S = 2


def secret(nome):
    percorso = SECRETS / nome
    return percorso.read_text().strip() if percorso.exists() else ""


chiave_sessione = secret("sim_secret")
if not chiave_sessione:
    raise RuntimeError("Manca il secret sim_secret")

app = Flask(__name__)
app.config.update(
    SECRET_KEY=chiave_sessione, SESSION_COOKIE_NAME="simulatore",
    SESSION_COOKIE_SECURE=True, SESSION_COOKIE_HTTPONLY=True, SESSION_COOKIE_SAMESITE="Strict",
    MAX_CONTENT_LENGTH=16 * 1024,
)
CSRFProtect(app)


@app.template_filter("euro")
def euro(centesimi):
    intero, cent = divmod(int(centesimi or 0), 100)
    return f"{intero},{cent:02d} €"


@app.template_filter("peso")
def peso(grammi):
    kg, resto = divmod(int(grammi or 0), 1000)
    return f"{kg},{resto:03d} kg"


@app.template_filter("data")
def data(iso):
    return "/".join(reversed(iso.split("-"))) if iso else "—"


def chiama(metodo, percorso, token_secret, **kwargs):
    """Chiamata all'API di Racoonix con la chiave del dispositivo. Restituisce (dati, errore)."""
    token = secret(token_secret)
    if not token:
        return None, "Dispositivo non configurato: manca la chiave"
    try:
        risposta = requests.request(metodo, f"{API}{percorso}", timeout=5,
                                    headers={"Authorization": f"Bearer {token}"}, **kwargs)
    except requests.RequestException:
        return None, "Racoonix non raggiungibile: riprova"
    try:
        dati = risposta.json()
    except ValueError:
        return None, "Risposta non valida da Racoonix"
    if risposta.status_code >= 400:
        return None, dati.get("errore", "Operazione rifiutata")
    return dati, None


# ---------- Cassa ----------

def _carrello():
    return [dict(r) for r in session.get("carrello", [])]


def _perc(riga):
    if riga["lotto_fisso"]:
        return riga["auto_perc"]
    return riga["scadenza_perc"] if riga["sconto"] else 0


def _importo(riga):
    if riga["unita"] == "kg":
        lordo = (riga["prezzo"] * riga["quantita"] + 500) // 1000
    else:
        lordo = riga["prezzo"] * riga["quantita"]
    return (lordo * (100 - _perc(riga)) + 50) // 100


@app.get("/")
def home():
    return render_template("home.html")


@app.get("/cassa")
def cassa():
    righe = [dict(r, indice=i, perc=_perc(r), importo=_importo(r)) for i, r in enumerate(_carrello())]
    return render_template("cassa.html", righe=righe, totale=sum(r["importo"] for r in righe),
                           scontrino=session.pop("scontrino", None))


@app.post("/cassa/leggi")
def cassa_leggi():
    codice = (request.form.get("codice") or "").strip()[:250]
    if not codice:
        return redirect(url_for("cassa"))
    impronta = hashlib.sha256(codice.encode()).hexdigest()[:16]
    ultima = session.get("ultima_lettura") or {}
    if ultima.get("c") == impronta and time.time() - ultima.get("t", 0) < DOPPIA_LETTURA_S:
        return redirect(url_for("cassa"))
    session["ultima_lettura"] = {"c": impronta, "t": time.time()}

    dati, errore = chiama("GET", "/prodotti", "cassa_token", params={"codice": codice})
    if errore:
        flash(errore, "errore")
        return redirect(url_for("cassa"))
    carrello = _carrello()
    if len(carrello) >= MAX_RIGHE:
        flash("Scontrino pieno: chiudi questa spesa e aprine un'altra", "errore")
        return redirect(url_for("cassa"))
    uguale = next((r for r in carrello if r["codice"] == codice and r["unita"] == "pezzo" and not r["sconto"]), None)
    if uguale:
        uguale["quantita"] += 1
    else:
        carrello.append({"codice": codice, "descrizione": dati["descrizione"], "unita": dati["unita"],
                         "prezzo": dati["prezzo_centesimi"], "quantita": dati["quantita"],
                         "auto_perc": dati["sconto_automatico_perc"], "scadenza_perc": dati["sconto_scadenza_perc"],
                         "lotto_fisso": dati["lotto_fisso"], "sconto": False})
    session["carrello"] = carrello
    session.setdefault("transazione", uuid.uuid4().hex)
    return redirect(url_for("cassa"))


@app.post("/cassa/riga/<int:indice>/<azione>")
def cassa_riga(indice, azione):
    carrello = _carrello()
    if not 0 <= indice < len(carrello) or azione not in ("piu", "meno", "rimuovi", "sconto"):
        return redirect(url_for("cassa"))
    riga = carrello[indice]
    if azione == "rimuovi":
        carrello.pop(indice)
    elif azione in ("piu", "meno") and riga["unita"] == "pezzo":
        riga["quantita"] += 1 if azione == "piu" else -1
        if riga["quantita"] <= 0:
            carrello.pop(indice)
    elif azione == "sconto" and not riga["lotto_fisso"] and riga["scadenza_perc"]:
        riga["sconto"] = not riga["sconto"]
    session["carrello"] = carrello
    return redirect(url_for("cassa"))


@app.post("/cassa/annulla")
def cassa_annulla():
    session.pop("carrello", None)
    session.pop("transazione", None)
    flash("Spesa annullata: a Racoonix non e' stato inviato nulla", "ok")
    return redirect(url_for("cassa"))


@app.post("/cassa/paga")
def cassa_paga():
    carrello = _carrello()
    if not carrello:
        return redirect(url_for("cassa"))
    corpo = {"id_transazione": session.setdefault("transazione", uuid.uuid4().hex),
             "righe": [{"codice": r["codice"], "quantita": r["quantita"], "sconto": r["sconto"]} for r in carrello]}
    dati, errore = chiama("POST", "/vendite", "cassa_token", json=corpo)
    if errore:
        flash(f"{errore}. Il pagamento si puo' ritentare senza rischio di doppioni.", "errore")
        return redirect(url_for("cassa"))
    session.pop("carrello", None)
    session.pop("transazione", None)
    session["scontrino"] = dati
    return redirect(url_for("cassa"))


# ---------- Bilancia del banco ----------

@app.get("/bilancia")
def bilancia():
    return render_template("bilancia.html", etichetta=session.get("etichetta"),
                           esito=session.pop("esito_banco", None))


@app.post("/bilancia/leggi")
def bilancia_leggi():
    codice = (request.form.get("codice") or "").strip()[:250]
    dati, errore = chiama("GET", "/prodotti", "bilancia_token", params={"codice": codice})
    if errore:
        flash(errore, "errore")
        return redirect(url_for("bilancia"))
    session["etichetta"] = dict(dati, codice=codice, transazione=uuid.uuid4().hex)
    return redirect(url_for("bilancia"))


@app.post("/bilancia/registra")
def bilancia_registra():
    etichetta = session.get("etichetta")
    if not etichetta:
        return redirect(url_for("bilancia"))
    scadenza = None if etichetta["scadenza_fissa"] else (request.form.get("scadenza") or None)
    dati, errore = chiama("POST", "/banco/vaschette", "bilancia_token",
                          json={"id_transazione": etichetta["transazione"], "codice": etichetta["codice"],
                                "scadenza": scadenza})
    if errore:
        flash(errore, "errore")
        return redirect(url_for("bilancia"))
    session.pop("etichetta", None)
    session["esito_banco"] = dati
    return redirect(url_for("bilancia"))


@app.post("/bilancia/annulla")
def bilancia_annulla():
    session.pop("etichetta", None)
    return redirect(url_for("bilancia"))
