"""Impostazioni del negozio: si scelgono nella configurazione iniziale (dal browser) e si cambiano dalla
pagina Impostazioni. Stanno nel database; le variabili d'ambiente servono solo come valori di partenza."""
import ipaddress
import os
import time
from zoneinfo import available_timezones

from flask import g, has_app_context

from . import db

LINGUE = ("it", "en")
PAESI = ("IT", "GB", "US")
FUSO_PER_PAESE = {"IT": "Europe/Rome", "GB": "Europe/London", "US": "America/New_York"}
CHIAVI = ("nome", "lingua", "paese", "fuso", "reti_admin", "configurato")


def _da_ambiente():
    return {
        "nome": os.environ.get("MARKET_NAME") or "Racoonix",
        "lingua": os.environ.get("RACOONIX_LINGUA") or "it",
        "paese": os.environ.get("RACOONIX_PAESE") or "IT",
        "fuso": os.environ.get("RACOONIX_FUSO") or "Europe/Rome",
        "reti_admin": os.environ.get("ADMIN_IP_CONSENTITI") or "127.0.0.1/32",
        "configurato": "0",
    }


def _leggi_db():
    from .models import Impostazione
    righe = db.session.scalars(db.select(Impostazione).where(
        Impostazione.chiave.in_([f"negozio.{c}" for c in CHIAVI]))).all()
    return {r.chiave.removeprefix("negozio."): r.valore for r in righe}


def impostazioni():
    """Valori validati: anche se il db contenesse qualcosa di strano, l'app usa solo valori ammessi."""
    if has_app_context() and "negozio" in g:
        return g.negozio
    valori = _da_ambiente()
    if has_app_context():
        try:
            valori.update(_leggi_db())
        except Exception:  # db non ancora pronto (prima migrazione): restano i valori di partenza
            db.session.rollback()
    if valori["lingua"] not in LINGUE:
        valori["lingua"] = "it"
    if valori["paese"] not in PAESI:
        valori["paese"] = "IT"
    if not fuso_valido(valori["fuso"]):
        valori["fuso"] = "Europe/Rome"
    if has_app_context():
        g.negozio = valori
    return valori


def salva(**valori):
    from .models import Impostazione
    for chiave, valore in valori.items():
        assert chiave in CHIAVI, chiave
        voce = db.session.get(Impostazione, f"negozio.{chiave}") or Impostazione(chiave=f"negozio.{chiave}", valore="")
        voce.valore = str(valore)
        db.session.add(voce)
    g.pop("negozio", None)


def configurato():
    return impostazioni()["configurato"] == "1"


def fuso_valido(fuso):
    return isinstance(fuso, str) and fuso in _fusi()


_FUSI = None


def _fusi():
    global _FUSI
    if _FUSI is None:
        _FUSI = frozenset(f for f in available_timezones() if "/" in f and not f.startswith(("Etc/", "SystemV/", "posix/", "right/")))
    return _FUSI


def elenco_fusi():
    return sorted(_fusi())


CONSIGLIATI = {"IT": ["Europe/Rome"], "GB": ["Europe/London"],
               "US": ["America/New_York", "America/Chicago", "America/Denver", "America/Phoenix",
                      "America/Los_Angeles", "America/Anchorage", "Pacific/Honolulu"]}


def _etichetta(fuso):
    from datetime import datetime
    from zoneinfo import ZoneInfo
    scarto = datetime.now(ZoneInfo(fuso)).utcoffset()
    minuti = int(scarto.total_seconds() // 60)
    segno = "+" if minuti >= 0 else "-"
    ore, resto = divmod(abs(minuti), 60)
    citta = " \u00b7 ".join(parte.replace("_", " ") for parte in fuso.split("/")[1:])
    return f"{citta} (UTC{segno}{ore:02d}:{resto:02d})"


def gruppi_fusi():
    """Per il menu a tendina: prima i fusi dei paesi previsti, poi tutti gli altri per continente."""
    from .lingua import _l
    paesi = {"IT": _l("Italia"), "GB": _l("Regno Unito"), "US": _l("Stati Uniti")}
    continenti = {"Europe": _l("Europa"), "America": _l("America"), "Asia": _l("Asia"), "Africa": _l("Africa"),
                  "Australia": _l("Australia"), "Pacific": _l("Pacifico"), "Atlantic": _l("Atlantico"),
                  "Indian": _l("Oceano Indiano"), "Antarctica": _l("Antartide"), "Arctic": _l("Artico")}
    gruppi = [(str(paesi[p]), [(f, _etichetta(f)) for f in CONSIGLIATI[p]]) for p in PAESI]
    gia = {f for elenco in CONSIGLIATI.values() for f in elenco}
    for prefisso, nome in continenti.items():
        voci = [(f, _etichetta(f)) for f in elenco_fusi() if f.split("/")[0] == prefisso and f not in gia]
        if voci:
            gruppi.append((str(nome), sorted(voci, key=lambda v: v[1])))
    return gruppi


def applica_fuso():
    """date.today() e gli orari seguono il fuso del negozio, che si puo' cambiare senza riavviare niente."""
    fuso = impostazioni()["fuso"]
    if os.environ.get("TZ") != fuso:
        os.environ["TZ"] = fuso
        time.tzset()


def leggi_reti(testo):
    """Accetta indirizzi o reti separati da virgole o a capo; None se qualcosa non e' valido."""
    reti = []
    for parte in testo.replace("\n", ",").split(","):
        parte = parte.strip()
        if not parte:
            continue
        try:
            reti.append(ipaddress.ip_network(parte, strict=False))
        except ValueError:
            return None
    return reti or None


def reti_admin():
    return leggi_reti(impostazioni()["reti_admin"]) or [ipaddress.ip_network("127.0.0.1/32")]
