"""API di integrazione per casse e bilance. Niente sessioni ne' cookie: ogni richiesta porta la chiave."""
import hashlib
import json
import re
from datetime import datetime, timezone
from functools import wraps

from flask import Blueprint, g, request
from sqlalchemy.exc import IntegrityError

from . import codici, db, limiter
from .auth import registra
from .integrazione import (NonDisponibile, Rifiutato, descrivi, descrivi_etichetta, interpreta,
                           registra_vaschetta, registra_vendita)
from .models import Dispositivo, RichiestaApi
from .notifiche import controlla_scaffali

bp = Blueprint("api", __name__, url_prefix="/api/v1")
TOKEN_OK = re.compile(r"^rcx_[A-Za-z0-9_-]{30,80}$")
CHIAVE_OK = re.compile(r"^[A-Za-z0-9-]{8,64}$")
MAX_RIGHE = 50


def _chiave_limite():
    return hashlib.sha256(request.headers.get("Authorization", "").encode()).hexdigest()[:16]


def richiede_dispositivo(*tipi):
    def decoratore(vista):
        @wraps(vista)
        def wrapper(*args, **kwargs):
            intestazione = request.headers.get("Authorization", "")
            token = intestazione[7:].strip() if intestazione.startswith("Bearer ") else ""
            dispositivo = None
            if TOKEN_OK.match(token):
                impronta = hashlib.sha256(token.encode()).hexdigest()
                dispositivo = db.session.scalar(db.select(Dispositivo).filter_by(token_hash=impronta))
            if dispositivo is None or not dispositivo.attivo:
                return {"errore": "Non autorizzato"}, 401
            if dispositivo.tipo not in tipi:
                return {"errore": "Operazione non consentita a questo dispositivo"}, 403
            dispositivo.ultimo_uso = datetime.now(timezone.utc)
            g.dispositivo = dispositivo
            return vista(*args, **kwargs)
        return wrapper
    return decoratore


def _idempotente(esegui):
    corpo = request.get_json(silent=True)
    if not isinstance(corpo, dict):
        return {"errore": "JSON non valido"}, 400
    chiave = corpo.get("id_transazione")
    if not isinstance(chiave, str) or not CHIAVE_OK.match(chiave):
        return {"errore": "id_transazione mancante o non valido"}, 400
    dispositivo_id = g.dispositivo.id

    def gia_eseguita():
        return db.session.scalar(db.select(RichiestaApi).filter_by(dispositivo_id=dispositivo_id, chiave=chiave))

    precedente = gia_eseguita()
    if precedente:
        db.session.commit()
        return json.loads(precedente.risposta), precedente.codice_http
    try:
        risposta, codice, prodotti = esegui(corpo)
    except codici.CodiceNonValido:
        db.session.rollback()
        return {"errore": "Codice non riconosciuto"}, 422
    except NonDisponibile as errore:
        db.session.rollback()
        return {"errore": f"Disponibilita' cambiata: {errore} non basta"}, 409
    except Rifiutato as errore:
        db.session.rollback()
        return {"errore": str(errore)}, 422
    db.session.add(RichiestaApi(dispositivo_id=dispositivo_id, chiave=chiave,
                                codice_http=codice, risposta=json.dumps(risposta)))
    try:
        db.session.commit()
    except IntegrityError:
        db.session.rollback()
        precedente = gia_eseguita()
        return json.loads(precedente.risposta), precedente.codice_http
    controlla_scaffali(prodotti)
    return risposta, codice


@bp.get("/prodotti")
@limiter.limit("240 per minute", key_func=_chiave_limite)
@richiede_dispositivo("cassa", "bilancia")
def prodotto():
    codice = (request.args.get("codice") or "")[:250]
    try:
        dati = descrivi_etichetta(codice) if g.dispositivo.tipo == "bilancia" else descrivi(codice)
    except codici.CodiceNonValido:
        dati, stato = {"errore": "Codice non riconosciuto"}, 422
    except Rifiutato as errore:
        dati, stato = {"errore": str(errore)}, 422
    else:
        stato = 200
    db.session.commit()
    return dati, stato


@bp.post("/vendite")
@limiter.limit("120 per minute", key_func=_chiave_limite)
@richiede_dispositivo("cassa")
def vendite():
    def esegui(corpo):
        righe_in = corpo.get("righe")
        if not isinstance(righe_in, list) or not 1 <= len(righe_in) <= MAX_RIGHE:
            raise Rifiutato("Righe non valide")
        righe = []
        for r in righe_in:
            if not isinstance(r, dict) or not isinstance(r.get("codice"), str):
                raise Rifiutato("Riga non valida")
            prodotto, lotto_id, quantita = interpreta(r["codice"][:250])
            if prodotto.unita == "pezzo":
                q = r.get("quantita", 1)
                if not isinstance(q, int) or isinstance(q, bool) or not 1 <= q <= 999:
                    raise Rifiutato("Quantita' non valida")
                quantita = q
            righe.append({"p": prodotto.id, "l": lotto_id, "q": quantita,
                          "s": r.get("sconto") is True and lotto_id is None})
        vendita, scontrino = registra_vendita(righe, dispositivo_id=g.dispositivo.id)
        registra("vendita_api", None,
                 f"dispositivo {g.dispositivo.nome}: vendita {vendita.id}, totale {vendita.totale_centesimi}")
        return ({"vendita_id": vendita.id, "totale_centesimi": vendita.totale_centesimi, "righe": scontrino},
                201, {r["p"] for r in righe})
    return _idempotente(esegui)


@bp.post("/banco/vaschette")
@limiter.limit("120 per minute", key_func=_chiave_limite)
@richiede_dispositivo("bilancia")
def vaschette():
    def esegui(corpo):
        codice, scadenza = corpo.get("codice"), corpo.get("scadenza")
        if not isinstance(codice, str) or (scadenza is not None and not isinstance(scadenza, str)):
            raise Rifiutato("Dati non validi")
        esito = registra_vaschetta(codice[:250], scadenza)
        registra("vaschetta_api", None,
                 f"dispositivo {g.dispositivo.nome}: prodotto {esito['prodotto_id']}, {esito['peso_g']} g")
        return esito, 201, {esito["prodotto_id"]}
    return _idempotente(esegui)
