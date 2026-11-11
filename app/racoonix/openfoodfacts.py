"""Riempimento automatico dei prodotti nuovi con Open Food Facts (https://world.openfoodfacts.org),
il database aperto dei prodotti alimentari.

Privacy: al servizio arriva solo il codice a barre, mai dati del negozio. Si puo' spegnere da Impostazioni.
Sicurezza: indirizzo fisso (nessuna richiesta verso indirizzi scelti da altri), tempo massimo breve,
risposta di dimensione limitata, e ogni campo ricevuto viene trattato come non affidabile e ricontrollato."""
import json
import re
import time
import urllib.request

from .formato import testo_pulito

INDIRIZZO = "https://world.openfoodfacts.org/api/v2/product/{codice}.json?fields=product_name,product_name_{lingua},brands,quantity"
AGENTE = "Racoonix/1.0 (https://github.com/JustCromo/Racoonix)"
TEMPO_MASSIMO = 3
DIMENSIONE_MASSIMA = 200_000
NOME_OK = re.compile(r"^[\w .,'()%/&+-]{2,120}$")
_cache = {}
DURATA_CACHE = 24 * 3600


def _scarica(url):
    richiesta = urllib.request.Request(url, headers={"User-Agent": AGENTE, "Accept": "application/json"})
    with urllib.request.urlopen(richiesta, timeout=TEMPO_MASSIMO) as risposta:  # nosec B310 - indirizzo https fisso
        return json.loads(risposta.read(DIMENSIONE_MASSIMA + 1)[:DIMENSIONE_MASSIMA])


def formato(testo):
    """'500 g' -> (1, 500, 'g'); '6 x 1,5 l' -> (6, 1500, 'ml'); altrimenti None."""
    testo = (testo or "").lower().replace(",", ".")
    m = re.match(r"^\s*(?:(\d{1,2})\s*[x×]\s*)?(\d{1,5}(?:\.\d{1,3})?)\s*(kg|g|ml|cl|l)\b(?:\s*[x×]\s*(\d{1,2}))?", testo)
    if not m:
        return None
    pezzi = int(m.group(1) or m.group(4) or 1)
    valore = float(m.group(2))
    unita = {"kg": ("g", 1000), "g": ("g", 1), "l": ("ml", 1000), "cl": ("ml", 10), "ml": ("ml", 1)}[m.group(3)]
    quantita = round(valore * unita[1])
    if not (1 <= pezzi <= 99 and 1 <= quantita <= 100_000):
        return None
    return pezzi, quantita, unita[0]


def _testo(valore, massimo):
    valore = testo_pulito(re.sub(r"\s+", " ", str(valore or "")))[:massimo]
    return valore if NOME_OK.match(valore) else None


def cerca(gtin, lingua="it"):
    """Dati del prodotto, oppure None se non si trova, se il servizio non risponde o se i dati non sono validi."""
    if not gtin or not re.fullmatch(r"[0-9]{8,14}", gtin):
        return None
    codice = gtin[1:] if len(gtin) == 14 and gtin.startswith("0") else gtin
    adesso = time.monotonic()
    if codice in _cache and adesso - _cache[codice][0] < DURATA_CACHE:
        return _cache[codice][1]
    try:
        dati = _scarica(INDIRIZZO.format(codice=codice, lingua="it" if lingua == "it" else "en"))
    except Exception:  # rete assente, servizio lento o risposta strana: si scrive a mano come sempre
        return None
    risultato = None
    prodotto = dati.get("product") if isinstance(dati, dict) and dati.get("status") == 1 else None
    if isinstance(prodotto, dict):
        nome = _testo(prodotto.get(f"product_name_{'it' if lingua == 'it' else 'en'}") or prodotto.get("product_name"), 120)
        marca = _testo(str(prodotto.get("brands") or "").split(",")[0], 60)
        if nome:
            risultato = {"nome": nome, "marca": marca, "formato": formato(prodotto.get("quantity"))}
    if len(_cache) > 500:
        _cache.clear()
    _cache[codice] = (adesso, risultato)
    return risultato
