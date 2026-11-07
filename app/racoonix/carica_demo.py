"""Carica il catalogo demo generato da tools/barcode (prodotti gia' approvati)."""
import json
import sys
from pathlib import Path

from . import create_app, db
from .codici import gtin_valido
from .models import Categoria, Prodotto


def main(percorso):
    app = create_app()
    with app.app_context():
        caricati = 0
        for voce in json.loads(Path(percorso).read_text()):
            gtin, plu = voce.get("gtin"), voce.get("codice_bilancia")
            unita, prezzo = voce.get("unita"), voce.get("prezzo_centesimi")
            categoria = db.session.scalar(db.select(Categoria).filter_by(nome=voce.get("categoria")))
            if (gtin and not gtin_valido(gtin)) or unita not in ("pezzo", "kg") \
                    or not isinstance(prezzo, int) or prezzo < 0 or categoria is None:
                print(f"Saltato (dati non validi): {voce.get('nome')}")
                continue
            esiste = db.session.scalar(db.select(Prodotto).where(
                (Prodotto.gtin == gtin) if gtin else (Prodotto.codice_bilancia == plu)))
            if esiste:
                continue
            db.session.add(Prodotto(
                gtin=gtin, codice_bilancia=plu, nome=str(voce["nome"])[:120],
                categoria_id=categoria.id, unita=unita, prezzo_centesimi=prezzo, stato="attivo",
                soglia_esposti=5 if unita == "pezzo" else 2000,
                giorni_validita=3 if categoria.nome == "Salumi e formaggi" else None,
            ))
            caricati += 1
        db.session.commit()
        print(f"Catalogo demo: {caricati} prodotti caricati")


if __name__ == "__main__":
    main(sys.argv[1])
