"""Regole di business condivise da cassa e notifiche."""


def vendibile(lotto, oggi):
    return lotto.data_scadenza is None or lotto.data_scadenza > oggi


def perc_sconto(prodotto, lotto, oggi):
    if lotto is None or lotto.data_scadenza is None:
        return 0
    giorni = (lotto.data_scadenza - oggi).days
    perc = 0
    for limite, p in prodotto.fasce_sconto():
        if p and limite and giorni <= limite:
            perc = max(perc, p)
    return perc
