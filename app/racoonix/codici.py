"""Riconoscimento e validazione dei codici a barre di un market.

Tipi gestiti: EAN-13/EAN-8/UPC-A/GTIN-14, editoriali (977/978/979),
peso variabile da bilancia (prefissi 2x), GS1 DataMatrix/GS1-128, QR GS1 Digital Link.
Ogni tipo ha la sua grammatica: tutto cio' che non la rispetta viene rifiutato.
I link Digital Link vengono solo analizzati, MAI aperti (niente SSRF, niente phishing).
"""
import calendar
import re
from datetime import date
from urllib.parse import parse_qsl, unquote, urlsplit

GS = "\x1d"
MAX_LUNGHEZZA = 100
MAX_LUNGHEZZA_URL = 250
PESO_MIN_G, PESO_MAX_G = 1, 50000
PREFISSI_SIMBOLOGIA = ("]d2", "]C1", "]Q3", "]e0", "]E0")
FISSI = {"01": 14, "13": 6, "15": 6, "17": 6, "3103": 6}
VARIABILI = {"10": 20}
AI_QUERY_LINK = ("13", "15", "17", "3103")
EDITORIALI = ("977", "978", "979")
CIFRE = re.compile(r"^[0-9]+$")
LOTTO_OK = re.compile(r"^[A-Za-z0-9._/-]{1,20}$")


class CodiceNonValido(ValueError):
    pass


def cifra_controllo(base: str) -> str:
    totale = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(base)))
    return str((10 - totale % 10) % 10)


def gtin_valido(gtin: str) -> bool:
    if not CIFRE.match(gtin) or len(gtin) not in (8, 12, 13, 14):
        return False
    return cifra_controllo(gtin[:-1]) == gtin[-1]


def gtin_base(gtin14: str):
    """Un GTIN con indicatore 9 e' la versione 'a peso variabile': riporta al GTIN del prodotto."""
    if gtin14.startswith("9"):
        base = gtin14[1:13]
        return "0" + base + cifra_controllo(base), True
    return gtin14, False


def _risultato(tipo, **campi):
    r = {"tipo": tipo, "gtin": None, "codice_bilancia": None, "peso_g": None,
         "scadenza": None, "tipo_data": None, "confezionamento": None, "lotto": None}
    r.update(campi)
    return r


def _data(valore: str) -> date:
    if not re.fullmatch(r"[0-9]{6}", valore):
        raise CodiceNonValido("Data non valida")
    anno, mese, giorno = 2000 + int(valore[:2]), int(valore[2:4]), int(valore[4:])
    if not 1 <= mese <= 12:
        raise CodiceNonValido("Data non valida")
    if giorno == 0:
        giorno = calendar.monthrange(anno, mese)[1]
    try:
        return date(anno, mese, giorno)
    except ValueError:
        raise CodiceNonValido("Data non valida") from None


def _peso(valore: str) -> int:
    if not re.fullmatch(r"[0-9]{5,6}", valore):
        raise CodiceNonValido("Peso non valido")
    grammi = int(valore)
    if not PESO_MIN_G <= grammi <= PESO_MAX_G:
        raise CodiceNonValido("Peso fuori intervallo")
    return grammi


def _lineare(testo: str, prefissi_bilancia):
    if not gtin_valido(testo):
        raise CodiceNonValido("Cifra di controllo errata")
    if len(testo) == 13 and testo[:2] in prefissi_bilancia:
        return _risultato("bilancia", codice_bilancia=testo[2:7], peso_g=_peso(testo[7:12]))
    tipo = "editoriale" if len(testo) == 13 and testo.startswith(EDITORIALI) else "ean"
    return _risultato(tipo, gtin=testo.zfill(14))


def _campi_parentesi(testo: str) -> dict:
    parti = re.findall(r"\(([0-9]{2,4})\)([^()]+)", testo)
    if not parti or "".join(f"({a}){v}" for a, v in parti) != testo:
        raise CodiceNonValido("Formato non valido")
    campi = {}
    for ai, valore in parti:
        if ai in campi or (ai not in FISSI and ai not in VARIABILI):
            raise CodiceNonValido("AI non supportato o ripetuto")
        if ai in FISSI and len(valore) != FISSI[ai]:
            raise CodiceNonValido("Lunghezza non valida")
        campi[ai] = valore
    return campi


def _campi_stringa(testo: str) -> dict:
    campi, i = {}, 0
    while i < len(testo):
        ai = next((a for a in (testo[i:i + 4], testo[i:i + 2]) if a in FISSI or a in VARIABILI), None)
        if ai is None or ai in campi:
            raise CodiceNonValido("AI non supportato o ripetuto")
        i += len(ai)
        if ai in FISSI:
            n = FISSI[ai]
            valore = testo[i:i + n]
            i += n
            if len(valore) != n:
                raise CodiceNonValido("Lunghezza non valida")
            if i < len(testo) and testo[i] == GS:
                i += 1
        else:
            fine = testo.find(GS, i)
            fine = len(testo) if fine == -1 else fine
            valore = testo[i:fine]
            i = fine + 1
        campi[ai] = valore
    return campi


def _campi_digital_link(testo: str) -> dict:
    parti = urlsplit(testo)
    if parti.scheme not in ("https", "http") or not parti.netloc:
        raise CodiceNonValido("Link non valido")
    segmenti = [unquote(s) for s in parti.path.split("/") if s]
    if "01" not in segmenti:
        raise CodiceNonValido("Link non GS1")
    coppie = segmenti[segmenti.index("01"):]
    if len(coppie) % 2:
        raise CodiceNonValido("Link non valido")
    campi = {}
    for ai, valore in zip(coppie[::2], coppie[1::2]):
        if ai in campi or ai not in ("01", "10", "21", "22"):
            raise CodiceNonValido("AI non supportato o ripetuto")
        if ai in ("21", "22"):
            if not LOTTO_OK.match(valore):
                raise CodiceNonValido("Valore non valido")
            continue
        campi[ai] = valore
    gtin = campi.get("01", "")
    if not CIFRE.match(gtin) or len(gtin) not in (8, 12, 13, 14):
        raise CodiceNonValido("GTIN non valido")
    campi["01"] = gtin.zfill(14)
    for chiave, valore in parse_qsl(parti.query):
        if chiave in AI_QUERY_LINK:
            if chiave in campi:
                raise CodiceNonValido("AI ripetuto")
            campi[chiave] = valore
    return campi


def _da_campi(campi: dict, tipo: str):
    gtin = campi.get("01")
    if not gtin or not gtin_valido(gtin):
        raise CodiceNonValido("GTIN mancante o non valido")
    gtin, peso_variabile = gtin_base(gtin)
    r = _risultato(tipo, gtin=gtin)
    if "17" in campi:
        r["scadenza"], r["tipo_data"] = _data(campi["17"]), "da_consumarsi_entro"
    elif "15" in campi:
        r["scadenza"], r["tipo_data"] = _data(campi["15"]), "preferibilmente_entro"
    if "13" in campi:
        r["confezionamento"] = _data(campi["13"])
    if "3103" in campi:
        r["peso_g"] = _peso(campi["3103"])
    elif peso_variabile:
        raise CodiceNonValido("Peso mancante")
    if "10" in campi:
        if not LOTTO_OK.match(campi["10"]):
            raise CodiceNonValido("Lotto non valido")
        r["lotto"] = campi["10"]
    return r


def riconosci(grezzo, prefissi_bilancia=()):
    if not isinstance(grezzo, str) or not grezzo.strip():
        raise CodiceNonValido("Codice vuoto")
    testo = grezzo.strip()
    if len(testo) > MAX_LUNGHEZZA_URL:
        raise CodiceNonValido("Codice troppo lungo")
    if testo.lower().startswith(("https://", "http://")):
        return _da_campi(_campi_digital_link(testo), "gs1_digital_link")
    if len(testo) > MAX_LUNGHEZZA:
        raise CodiceNonValido("Codice troppo lungo")
    for prefisso in PREFISSI_SIMBOLOGIA:
        if testo.startswith(prefisso):
            testo = testo[len(prefisso):]
            break
    testo = testo.lstrip(GS)
    if re.fullmatch(r"[0-9]{8}|[0-9]{12,14}", testo):
        return _lineare(testo, prefissi_bilancia)
    campi = _campi_parentesi(testo) if testo.startswith("(") else _campi_stringa(testo)
    return _da_campi(campi, "gs1")


def piva_valida(piva) -> bool:
    """Partita IVA italiana: 11 cifre, l'ultima e' di controllo (simile all'algoritmo di Luhn)."""
    if not isinstance(piva, str) or not re.fullmatch(r"[0-9]{11}", piva):
        return False
    cifre = [int(c) for c in piva]
    dispari = sum(cifre[0:10:2])
    pari = sum(d * 2 - 9 if d * 2 > 9 else d * 2 for d in cifre[1:10:2])
    return (10 - (dispari + pari) % 10) % 10 == cifre[10]
