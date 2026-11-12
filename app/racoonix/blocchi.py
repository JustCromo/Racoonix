"""Indirizzi bloccati: chi prova a indovinare le password puo' essere fermato del tutto, non solo rallentato.

Il controllo avviene per primo, a ogni richiesta, e non dice niente a chi viene respinto. L'elenco si tiene in
memoria per pochi secondi, cosi' non pesa sul database. Nessun blocco puo' includere i computer dell'admin."""
import ipaddress
import time
from datetime import datetime, timezone

from flask import request

from . import db

DURATA_CACHE = 10
_cache = {"letto": 0.0, "reti": []}


def _attivi(stato):
    from .models import IndirizzoBloccato
    adesso = datetime.now(timezone.utc)
    return db.session.scalars(db.select(IndirizzoBloccato).where(
        IndirizzoBloccato.stato == stato,
        db.or_(IndirizzoBloccato.scade_il.is_(None), IndirizzoBloccato.scade_il > adesso))).all()


def reti_bloccate():
    if time.monotonic() - _cache["letto"] > DURATA_CACHE:
        try:
            _cache["reti"] = [ipaddress.ip_network(b.rete) for b in _attivi("bloccato")]
        except Exception:  # db non ancora pronto: nessun blocco, si riprova al giro dopo
            db.session.rollback()
            _cache["reti"] = []
        _cache["letto"] = time.monotonic()
    return _cache["reti"]


def svuota_cache():
    _cache["letto"] = 0.0


def respingi():
    """Primo controllo di ogni richiesta (anche dei file statici): un indirizzo bloccato non arriva a niente."""
    try:
        ip = ipaddress.ip_address(request.remote_addr or "")
    except ValueError:
        return None
    if any(ip in rete for rete in reti_bloccate()):
        return "", 403
    return None
