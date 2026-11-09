"""Genera le etichette e il catalogo demo di Racoonix. Marchi, codici e fornitori sono inventati.

Uso, dalla cartella del progetto:
  docker build -t racoonix-etichette tools/barcode
  docker run --rm -v ./demo:/out racoonix-etichette
  docker compose run --rm --no-deps -v ./demo:/demo:ro app python -m racoonix.carica_demo /demo/catalogo_demo.json
Poi apri demo/foglio_demo.html, stampalo e prova il carico inquadrando i codici.
"""
import datetime as dt
import html
import json
from pathlib import Path

import treepoem
from PIL import Image

OUT = Path("/out")
OGGI = dt.date.today()

FORNITORI = [
    "Carni del Chianti Srl", "Latteria Val d'Arno Soc. Coop.", "Ortofrutta Arno Srl",
    "Forno Ponte Vecchio Snc", "Pastificio Mugello Spa", "Dolci di Fiesole Srl",
    "Fonte Casentino Spa", "Salumificio Valdarno Srl", "Conserve del Sole Srl",
]

# formato = (pezzi, quantita per pezzo, unita) oppure None per i prodotti a peso
CATALOGO = {
    1: dict(nome="Petto di pollo", marca="Corte dei Campi", categoria="Carne", sotto="Pollame",
            unita="pezzo", prezzo=690, formato=(1, 400, "g"), fornitore=0),
    2: dict(nome="Insalata mista", marca="Orto Fresco", categoria="Ortofrutta", sotto="Verdura",
            unita="pezzo", prezzo=149, formato=(1, 150, "g"), fornitore=2),
    3: dict(nome="Latte fresco intero", marca="Latteria Val d'Arno", categoria="Latticini", sotto="Latte",
            unita="pezzo", prezzo=159, formato=(1, 1000, "ml"), fornitore=1),
    4: dict(nome="Yogurt bianco", marca="Latteria Val d'Arno", categoria="Latticini", sotto="Yogurt",
            unita="pezzo", prezzo=89, formato=(2, 125, "g"), fornitore=1),
    5: dict(nome="Pane in cassetta", marca="Forno Ponte Vecchio", categoria="Forno", sotto="Pane",
            unita="pezzo", prezzo=199, formato=(1, 400, "g"), fornitore=3),
    6: dict(nome="Mozzarella", marca="Latteria Val d'Arno", categoria="Latticini", sotto="Formaggi freschi",
            unita="pezzo", prezzo=129, formato=(1, 125, "g"), fornitore=1),
    7: dict(nome="Frollini al burro", marca="Dolci di Fiesole", categoria="Dolci", sotto="Biscotti",
            unita="pezzo", prezzo=249, formato=(1, 350, "g"), fornitore=5),
    8: dict(nome="Penne rigate", marca="Pastificio Mugello", categoria="Pasta", sotto="Pasta secca",
            unita="pezzo", prezzo=99, formato=(1, 500, "g"), fornitore=4),
    9: dict(nome="Acqua naturale", marca="Fonte Casentino", categoria="Bevande", sotto="Acqua",
            unita="pezzo", prezzo=219, formato=(6, 1500, "ml"), fornitore=6),
    10: dict(nome="Passata di pomodoro", marca="Conserve del Sole", categoria="Conserve", sotto="Pomodoro",
             unita="pezzo", prezzo=119, formato=(1, 700, "g"), fornitore=8),
    11: dict(nome="Mele Golden", marca=None, categoria="Ortofrutta", sotto="Frutta",
             unita="kg", prezzo=220, formato=None, fornitore=2, plu="00012"),
    12: dict(nome="Prosciutto cotto", marca="Salumificio Valdarno", categoria="Salumi e formaggi", sotto="Salumi",
             unita="kg", prezzo=2490, formato=None, fornitore=7, plu="00034"),
}
NON_IN_CATALOGO = {10}
SENZA_GTIN = {11}
ALIAS = {13: (8, "nuova confezione")}  # EAN aggiuntivo: stesso prodotto, codice diverso

# numero (prodotto o alias), formato codice, giorni alla scadenza, peso in grammi.
# Mele e prosciutto (prodotti a peso) non hanno etichetta: si caricano dall'elenco "sfusi" del Carico.
ETICHETTE = [
    (1, "gs1dm", 2, None), (1, "gs1dm", 6, None), (2, "gs1dm", 1, None),
    (3, "link", 3, None), (4, "gs1dm", 5, None), (5, "link", 5, None),
    (6, "gs1dm", 0, None), (7, "ean13", 240, None), (8, "ean13", 365, None),
    (13, "ean13", 365, None), (9, "ean13", 365, None), (10, "gs1dm", 540, None),
]

DESCRIZIONI = {
    "gs1dm": "GS1 DataMatrix: scadenza e lotto nel codice",
    "link": "QR GS1 Digital Link: scadenza e lotto nel link",
    "ean13": "EAN-13 classico: scadenza da inserire a mano",
}


def cifra_controllo(base: str) -> str:
    totale = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(base)))
    return str((10 - totale % 10) % 10)


def gtin13(numero: int) -> str:
    base = f"20{numero:010d}"
    return base + cifra_controllo(base)


def partita_iva(numero: int) -> str:
    base = f"{numero:07d}048"
    cifre = [int(c) for c in base]
    dispari = sum(cifre[0::2])
    pari = sum(d * 2 - 9 if d * 2 > 9 else d * 2 for d in cifre[1::2])
    return base + str((10 - (dispari + pari) % 10) % 10)


def salva(immagine, percorso: Path):
    immagine = immagine.convert("1")
    immagine.resize((immagine.width * 6, immagine.height * 6), Image.NEAREST).save(percorso)


def main():
    (OUT / "codici").mkdir(parents=True, exist_ok=True)
    righe = []
    for i, (n, formato, giorni, peso) in enumerate(ETICHETTE, 1):
        n_prodotto = ALIAS[n][0] if n in ALIAS else n
        prodotto = CATALOGO[n_prodotto]
        g14 = None if n in SENZA_GTIN else "0" + gtin13(n)
        lotto = f"L{OGGI:%y%m}{i:02d}"
        scadenza = OGGI + dt.timedelta(days=giorni) if giorni is not None else None
        nota = DESCRIZIONI[formato]

        if formato == "gs1dm":
            tipo_bc, dati = "gs1datamatrix", f"(01){g14}(17){scadenza:%y%m%d}(10){lotto}"
        elif formato == "link":
            tipo_bc, dati = "qrcode", f"https://id.gs1.org/01/{g14}/10/{lotto}?17={scadenza:%y%m%d}"
        else:
            tipo_bc, dati = "ean13", g14[1:]
            nota += f" (usa {scadenza:%d/%m/%Y})"

        file = f"codici/{i:02d}.png"
        salva(treepoem.generate_barcode(barcode_type=tipo_bc, data=dati), OUT / file)
        if n in ALIAS:
            nota += f" | EAN aggiuntivo ({ALIAS[n][1]})"
        if n_prodotto in NON_IN_CATALOGO:
            nota += " | NON in catalogo: serve l'ok dell'admin"
        nome = " · ".join(x for x in (prodotto["marca"], prodotto["nome"]) if x)
        info_peso = f"{peso} g" if peso else ""
        info_scad = f"{scadenza:%d/%m/%Y} (+{giorni} gg)" if scadenza else "nessuna"
        righe.append(
            f"<tr><td><img src='{file}' alt=''></td><td>{html.escape(nome)}</td>"
            f"<td>{html.escape(prodotto['categoria'])}</td><td>{lotto}</td><td>{info_scad}</td>"
            f"<td>{info_peso}</td><td>{html.escape(nota)}</td></tr>"
        )

    fornitori = [{"ragione_sociale": nome, "partita_iva": partita_iva(i + 1),
                  "telefono": f"055 000 {i + 1:04d}", "email": f"ordini{i + 1}@fornitore.example"}
                 for i, nome in enumerate(FORNITORI)]
    prodotti = []
    for n, p in CATALOGO.items():
        if n in NON_IN_CATALOGO:
            continue
        pezzi, quantita, unita_formato = p["formato"] or (1, None, None)
        prodotti.append({
            "gtin": None if n in SENZA_GTIN else "0" + gtin13(n), "codice_bilancia": p.get("plu"),
            "nome": p["nome"], "marca": p["marca"], "categoria": p["categoria"],
            "sottocategoria": p["sotto"], "unita": p["unita"], "prezzo_centesimi": p["prezzo"],
            "formato_pezzi": pezzi, "formato_quantita": quantita,
            "formato_unita": unita_formato, "fornitore": FORNITORI[p["fornitore"]],
            "codici_aggiuntivi": [{"gtin": "0" + gtin13(a), "descrizione": d}
                                  for a, (orig, d) in ALIAS.items() if orig == n],
        })
    (OUT / "catalogo_demo.json").write_text(
        json.dumps({"fornitori": fornitori, "prodotti": prodotti}, ensure_ascii=False, indent=2))
    (OUT / "foglio_demo.html").write_text(f"""<!doctype html><html lang="it"><head>
<meta charset="utf-8"><title>Codici demo Racoonix</title><style>
body{{font-family:sans-serif;background:#F6F0E4;color:#2E3A59;padding:1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #6B7A8F;padding:.5rem}}
img{{width:150px;image-rendering:pixelated;background:#fff;padding:8px}}
</style></head><body><h1>Codici demo Racoonix - generati il {OGGI:%d/%m/%Y}</h1>
<p>Prima carica il catalogo demo (vedi l'intestazione di <code>tools/barcode/genera_demo.py</code>), poi inquadra
i codici dalla pagina Carico. Le scadenze sono calcolate dalla data di generazione: rigenera il foglio prima di ogni demo.
Mele e prosciutto, venduti a peso, si caricano dall'elenco dei prodotti sfusi.</p>
<table><tr><th>Codice</th><th>Prodotto</th><th>Categoria</th><th>Lotto</th>
<th>Scadenza</th><th>Peso</th><th>Note</th></tr>{''.join(righe)}</table></body></html>""")
    print(f"Generate {len(ETICHETTE)} etichette e il catalogo demo in demo/ (date da {OGGI:%d/%m/%Y})")


if __name__ == "__main__":
    main()
