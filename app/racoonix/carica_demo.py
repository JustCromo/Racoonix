"""Carica fornitori e catalogo demo generati da tools/barcode (prodotti gia' approvati)."""
import json
import sys
from pathlib import Path

from . import create_app, db
from .codici import gtin_valido, piva_valida
from .lingua import testo_negozio
from .models import Categoria, CodiceAggiuntivo, Fornitore, Prodotto, Sottocategoria


def _testo(valore, massimo):
    return str(valore).strip()[:massimo] if valore else None


def _intero_positivo(valore):
    return isinstance(valore, int) and not isinstance(valore, bool) and valore > 0


def main(percorso):
    app = create_app()
    with app.app_context():
        dati = json.loads(Path(percorso).read_text())

        fornitori = {}
        for voce in dati.get("fornitori", []):
            nome, piva = _testo(voce.get("ragione_sociale"), 120), voce.get("partita_iva")
            if not nome or (piva and not piva_valida(piva)):
                print(f"Fornitore saltato (dati non validi): {nome}")
                continue
            fornitore = db.session.scalar(db.select(Fornitore).filter_by(ragione_sociale=nome))
            if fornitore is None:
                fornitore = Fornitore(ragione_sociale=nome, partita_iva=piva,
                                      telefono=_testo(voce.get("telefono"), 30),
                                      email=_testo(voce.get("email"), 120))
                db.session.add(fornitore)
            fornitori[nome] = fornitore
        db.session.flush()

        caricati = 0
        for voce in dati.get("prodotti", []):
            gtin, plu = voce.get("gtin"), voce.get("codice_bilancia")
            unita, prezzo = voce.get("unita"), voce.get("prezzo_centesimi")
            pezzi = voce.get("formato_pezzi") or 1
            quantita, unita_formato = voce.get("formato_quantita"), voce.get("formato_unita")
            categoria = db.session.scalar(db.select(Categoria).filter_by(nome=testo_negozio(voce.get("categoria") or "")))
            sotto = db.session.scalar(db.select(Sottocategoria).filter_by(
                categoria_id=categoria.id, nome=testo_negozio(voce.get("sottocategoria") or ""))) if categoria else None
            valido = (
                (not gtin or gtin_valido(gtin)) and unita in ("pezzo", "kg")
                and isinstance(prezzo, int) and prezzo >= 0
                and categoria is not None and _intero_positivo(pezzi)
                and (quantita is None) == (unita_formato is None)
                and (quantita is None or (_intero_positivo(quantita) and unita_formato in ("g", "ml", "pz")))
            )
            if not valido:
                print(f"Prodotto saltato (dati non validi): {voce.get('nome')}")
                continue
            esiste = db.session.scalar(db.select(Prodotto).where(
                (Prodotto.gtin == gtin) if gtin else (Prodotto.codice_bilancia == plu)))
            if esiste:
                continue
            prodotto = Prodotto(
                gtin=gtin, codice_bilancia=plu, nome=_testo(voce.get("nome"), 120),
                marca=_testo(voce.get("marca"), 60), categoria_id=categoria.id,
                sottocategoria_id=sotto.id if sotto else None,
                fornitore_id=fornitori[voce["fornitore"]].id if voce.get("fornitore") in fornitori else None,
                unita=unita, formato_pezzi=pezzi, formato_quantita=quantita, formato_unita=unita_formato,
                prezzo_centesimi=prezzo, stato="attivo",
            )
            for extra in voce.get("codici_aggiuntivi", []):
                if gtin_valido(extra.get("gtin", "")):
                    prodotto.codici_aggiuntivi.append(CodiceAggiuntivo(
                        gtin=extra["gtin"], descrizione=_testo(extra.get("descrizione"), 60)))
            db.session.add(prodotto)
            caricati += 1
        db.session.commit()
        print(f"Catalogo demo: {len(fornitori)} fornitori e {caricati} prodotti caricati")


if __name__ == "__main__":
    main(sys.argv[1])
