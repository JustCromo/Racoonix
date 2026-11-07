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
