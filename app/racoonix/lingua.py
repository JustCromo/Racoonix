"""Lingue e paesi. La lingua decide i testi (per utente), il paese del negozio decide formati e valuta."""

from flask import g
from flask_babel import force_locale, gettext, lazy_gettext

LINGUE = {"it": "Italiano", "en": "English"}
PAESI = ("IT", "GB", "US")


def lingua_negozio():
    from .negozio import impostazioni
    return impostazioni()["lingua"]


def paese_negozio():
    from .negozio import impostazioni
    return impostazioni()["paese"]


def scegli_lingua():
    """Prima la scelta dell'utente, poi (durante la configurazione iniziale) quella del momento,
    poi la lingua del negozio."""
    from flask import has_request_context, session
    utente = g.get("utente")
    if utente is not None and utente.lingua in LINGUE:
        return utente.lingua
    if has_request_context() and session.get("lingua_configurazione") in LINGUE:
        return session["lingua_configurazione"]
    return lingua_negozio()


def testo_negozio(messaggio, **valori):
    """Testi salvati nel db (note delle notifiche, testo degli ordini): sempre nella lingua del negozio,
    cosi' restano uguali per tutti, chiunque li abbia generati."""
    with force_locale(lingua_negozio()):
        return gettext(messaggio, **valori)


# Nomi mostrati per valori che nel db restano fissi (ruoli e stati dei prodotti)
NOMI_RUOLI = {"admin": lazy_gettext("admin"), "magazziniere": lazy_gettext("magazziniere"),
              "dipendente": lazy_gettext("dipendente")}
NOMI_STATI = {"attivo": lazy_gettext("attivo"), "in_attesa": lazy_gettext("in attesa"),
              "rimosso": lazy_gettext("rimosso")}


def nome_ruolo(ruolo):
    return str(NOMI_RUOLI.get(ruolo, ruolo))


def nome_stato(stato):
    return str(NOMI_STATI.get(stato, stato))


# Testi usati dagli script del browser: arrivano tradotti dentro la pagina, come dati (mai come codice)
TESTI_JS = [lazy_gettext("Mostra password"), lazy_gettext("Nascondi password"), lazy_gettext("Chiudi avviso"),
            lazy_gettext("Copia"), lazy_gettext("Copiato"), lazy_gettext("Non riuscito"),
            lazy_gettext("Usa fotocamera"), lazy_gettext("Ferma fotocamera"),
            lazy_gettext("Fotocamera non disponibile")]


def testi_js():
    return {t._args[0]: str(t) for t in TESTI_JS}


def nella_lingua_del_negozio(funzione):
    """Per le funzioni che scrivono testi nel db: tutto quello che generano esce nella lingua del negozio."""
    from functools import wraps

    @wraps(funzione)
    def avvolta(*args, **kwargs):
        with force_locale(lingua_negozio()):
            return funzione(*args, **kwargs)
    return avvolta


_ = gettext
_l = lazy_gettext
