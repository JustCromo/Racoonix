"""Ricerca prodotti per codice: GTIN principale oppure EAN aggiuntivi (es. confezione promo)."""
from . import db
from .models import CodiceAggiuntivo, Prodotto


def trova_per_gtin(gtin):
    prodotto = db.session.scalar(db.select(Prodotto).filter_by(gtin=gtin))
    if prodotto:
        return prodotto
    return db.session.scalar(db.select(Prodotto).join(CodiceAggiuntivo)
                             .where(CodiceAggiuntivo.gtin == gtin))
