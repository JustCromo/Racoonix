"""Menu e tema: li decide il server in base all'utente, il browser riceve solo l'HTML."""
from flask import current_app, g, request, url_for

from .auth import ruoli_attivi

TUTTI = None
# endpoint, etichetta, icona, ruoli ammessi (l'admin vede tutto), prefissi per evidenziare la voce attiva
VOCI = [
    ("dashboard.pagina", "Dashboard", "chart-bar", {"admin"}, ("dashboard.",)),
    ("notifiche.pagina", "Cose da fare", "bell", TUTTI, ("notifiche.",)),
    ("inventario.pagina", "Inventario", "box", {"dipendente", "magazziniere"}, ("inventario.",)),
    ("carico.pagina", "Carico", "truck", {"magazziniere"}, ("carico.",)),
    ("anagrafica.catalogo", "Catalogo", "tags", {"admin"},
     ("anagrafica.catalogo", "anagrafica.scheda", "anagrafica.salva", "anagrafica.aggiungi_codice",
      "anagrafica.rimuovi_codice", "prodotti.")),
    ("anagrafica.fornitori", "Fornitori", "building-warehouse", {"admin"},
     ("anagrafica.fornitori", "anagrafica.nuovo_fornitore", "anagrafica.salva_fornitore")),
    ("anagrafica.categorie", "Categorie", "category", {"admin"},
     ("anagrafica.categorie", "anagrafica.nuova_categoria", "anagrafica.salva_categoria",
      "anagrafica.nuova_sottocategoria", "anagrafica.cambia_sottocategoria")),
    ("dispositivi.elenco", "Dispositivi", "plug-connected", {"admin"}, ("dispositivi.",)),
    ("utenti.elenco", "Utenti", "users", {"admin"}, ("utenti.",)),
    ("scanner_test.pagina", "Test scanner", "camera", {"admin"}, ("scanner_test.",)),
]


def contesto():
    if g.get("utente") is None:
        return {"menu": [], "tema": "chiaro"}
    ruoli = ruoli_attivi()
    admin = "admin" in ruoli
    attuale = request.endpoint or ""
    menu = []
    for endpoint, etichetta, icona, ammessi, prefissi in VOCI:
        if endpoint not in current_app.view_functions:
            continue
        if ammessi is TUTTI or admin or ruoli & ammessi:
            menu.append({"url": url_for(endpoint), "etichetta": etichetta, "icona": icona,
                         "attiva": attuale.startswith(prefissi)})
    return {"menu": menu, "tema": g.utente.tema,
            "admin_limitato": g.utente.ha_ruolo("admin") and not admin}
