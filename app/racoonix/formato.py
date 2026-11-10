"""Formattazione per l'interfaccia: i valori nel db restano interi (centesimi, grammi).
Separatore decimale, valuta e formato delle date seguono il paese del negozio."""
from .lingua import _, paese_negozio

VALUTE = {"IT": ("", " \u20ac"), "GB": ("\u00a3", ""), "US": ("$", "")}
FORMATI_DATA = {"IT": "%d/%m/%Y", "GB": "%d/%m/%Y", "US": "%m/%d/%Y"}
FORMATI_ORA = {"IT": "%H:%M", "GB": "%H:%M", "US": "%I:%M %p"}


def _sep():
    return "," if paese_negozio() == "IT" else "."


def _pz():
    return _("pz")


def quantita(valore, unita):
    valore = valore or 0
    if unita == "kg":
        kg, grammi = divmod(valore, 1000)
        return f"{kg}{_sep()}{grammi:03d} kg"
    return f"{valore} {_pz()}"


def euro(centesimi):
    """Prezzo nella valuta del negozio (il nome resta per compatibilita' con i template)."""
    if centesimi is None:
        return "-"
    intero, cent = divmod(centesimi, 100)
    prima, dopo = VALUTE[paese_negozio()]
    return f"{prima}{intero}{_sep()}{cent:02d}{dopo}"


def data_it(valore):
    return valore.strftime(FORMATI_DATA[paese_negozio()]) if valore else "\u2014"


def misura(valore, unita):
    """500 g, 1,5 kg (1.5 kg), 750 ml, 1 l, 6 pz"""
    if unita == "pz":
        return f"{valore} {_pz()}"
    grande = {"g": "kg", "ml": "l"}[unita]
    if valore >= 1000:
        intero, resto = divmod(valore, 1000)
        decimali = f"{resto:03d}".rstrip("0")
        return f"{intero}{_sep()}{decimali} {grande}" if decimali else f"{intero} {grande}"
    return f"{valore} {unita}"


def data_ora_it(valore):
    """Data e ora nel fuso del server."""
    if not valore:
        return "\u2014"
    paese = paese_negozio()
    return valore.astimezone().strftime(f"{FORMATI_DATA[paese]} {FORMATI_ORA[paese]}")


def quantita_input(valore, unita):
    """Valore pronto per un campo modificabile: 12 oppure 2,500 (kg)."""
    valore = valore or 0
    if unita == "kg":
        kg, grammi = divmod(valore, 1000)
        return f"{kg}{_sep()}{grammi:03d}"
    return str(valore)


TIPOGRAFICI = str.maketrans({"\u2019": "'", "\u2018": "'", "\u201c": '"', "\u201d": '"'})


def testo_pulito(valore):
    """Le tastiere dei telefoni mettono apostrofi e virgolette curvi: li riportiamo a quelli dritti."""
    return (valore or "").translate(TIPOGRAFICI).strip()
