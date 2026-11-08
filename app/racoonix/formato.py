"""Formattazione per l'interfaccia: i valori nel db restano interi (centesimi, grammi)."""


def quantita(valore, unita):
    valore = valore or 0
    if unita == "kg":
        kg, grammi = divmod(valore, 1000)
        return f"{kg},{grammi:03d} kg"
    return f"{valore} pz"


def euro(centesimi):
    if centesimi is None:
        return "-"
    intero, cent = divmod(centesimi, 100)
    return f"{intero},{cent:02d} €"


def data_it(valore):
    return valore.strftime("%d/%m/%Y") if valore else "—"


def misura(valore, unita):
    """500 g, 1,5 kg, 750 ml, 1 l, 6 pz"""
    if unita == "pz":
        return f"{valore} pz"
    grande = {"g": "kg", "ml": "l"}[unita]
    if valore >= 1000:
        intero, resto = divmod(valore, 1000)
        decimali = f"{resto:03d}".rstrip("0")
        return f"{intero},{decimali} {grande}" if decimali else f"{intero} {grande}"
    return f"{valore} {unita}"


def data_ora_it(valore):
    """Data e ora nel fuso del server (Europe/Rome nei container)."""
    return valore.astimezone().strftime("%d/%m/%Y %H:%M") if valore else "—"
