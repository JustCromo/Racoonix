"""Menu e tema: li decide il server in base all'utente, il browser riceve solo l'HTML."""
from flask import current_app, g, request, url_for

from .auth import ruoli_attivi
from .lingua import _l

TUTTI = None
GIORNO, ANAGRAFICA, IMPOSTAZIONI = _l("Ogni giorno"), _l("Anagrafica"), _l("Impostazioni")
# endpoint, etichetta, icona, ruoli ammessi (l'admin vede tutto), prefissi per la voce attiva, gruppo
VOCI = [
    ("dashboard.pagina", _l("Dashboard"), "chart-bar", {"admin"}, ("dashboard.",), GIORNO),
    ("notifiche.pagina", _l("Cose da fare"), "bell", TUTTI, ("notifiche.",), GIORNO),
    ("inventario.pagina", _l("Inventario"), "box", {"dipendente", "magazziniere"}, ("inventario.",), GIORNO),
    ("carico.pagina", _l("Carico"), "truck", {"magazziniere"}, ("carico.",), GIORNO),
    ("ordini.pagina", _l("Ordini"), "clipboard-list", {"admin"}, ("ordini.",), GIORNO),
    ("anagrafica.catalogo", _l("Catalogo"), "tags", {"admin"},
     ("anagrafica.catalogo", "anagrafica.scheda", "anagrafica.salva", "anagrafica.aggiungi_codice",
      "anagrafica.elimina_prodotto", "anagrafica.ripristina_prodotto",
      "anagrafica.rimuovi_codice", "prodotti."), ANAGRAFICA),
    ("anagrafica.fornitori", _l("Fornitori"), "building-warehouse", {"admin"},
     ("anagrafica.fornitori", "anagrafica.nuovo_fornitore", "anagrafica.salva_fornitore"), ANAGRAFICA),
    ("anagrafica.categorie", _l("Categorie"), "category", {"admin"},
     ("anagrafica.categorie", "anagrafica.nuova_categoria", "anagrafica.salva_categoria",
      "anagrafica.nuova_sottocategoria", "anagrafica.cambia_sottocategoria"), ANAGRAFICA),
    ("impostazioni.pagina", _l("Negozio"), "building-store", {"admin"}, ("impostazioni.",), IMPOSTAZIONI),
    ("utenti.elenco", _l("Utenti"), "users", {"admin"}, ("utenti.",), IMPOSTAZIONI),
    ("collega.pagina", _l("Collega dispositivi"), "device-mobile", {"admin"}, ("collega.",), IMPOSTAZIONI),
    ("registro.pagina", _l("Registro attivita'"), "history", {"admin"}, ("registro.",), IMPOSTAZIONI),
]


def contesto():
    if g.get("utente") is None:
        return {"menu": [], "tema": "chiaro"}
    ruoli = ruoli_attivi()
    admin = "admin" in ruoli
    attuale = request.endpoint or ""
    menu = []
    for endpoint, etichetta, icona, ammessi, prefissi, gruppo in VOCI:
        if endpoint not in current_app.view_functions:
            continue
        if ammessi is TUTTI or admin or ruoli & ammessi:
            menu.append({"url": url_for(endpoint), "etichetta": str(etichetta), "icona": icona,
                         "attiva": attuale.startswith(prefissi), "gruppo": str(gruppo) if admin else None})
    return {"menu": menu, "tema": g.utente.tema,
            "admin_limitato": g.utente.ha_ruolo("admin") and not admin}
