"""Genera i codici demo di Racoonix (un esempio per ogni tipo), date calcolate da oggi."""
import datetime as dt
import html
import json
from pathlib import Path

import treepoem
from PIL import Image

OUT = Path("/out")
OGGI = dt.date.today()

# numero: nome, categoria, unita, prezzo in centesimi (al pezzo o al kg), codice bilancia
CATALOGO = {
    1: ("Petto di pollo", "Carne", "pezzo", 690, None),
    2: ("Insalata in busta", "Ortofrutta", "pezzo", 149, None),
    3: ("Latte fresco", "Latticini", "pezzo", 159, None),
    4: ("Yogurt bianco", "Latticini", "pezzo", 89, None),
    5: ("Pane in cassetta", "Forno", "pezzo", 199, None),
    6: ("Mozzarella", "Latticini", "pezzo", 129, None),
    7: ("Biscotti", "Dolci", "pezzo", 249, None),
    8: ("Pasta penne", "Pasta", "pezzo", 99, None),
    9: ("Acqua naturale", "Bevande", "pezzo", 39, None),
    10: ("Passata di pomodoro", "Conserve", "pezzo", 119, None),
    11: ("Mele Golden", "Ortofrutta", "kg", 220, "00012"),
    12: ("Prosciutto cotto", "Salumi e formaggi", "kg", 2490, "00034"),
}
NON_IN_CATALOGO = {10}
SENZA_GTIN = {11}

# numero prodotto, formato, giorni alla scadenza, peso in grammi
ETICHETTE = [
    (1, "gs1dm", 2, None), (1, "gs1dm", 6, None), (2, "gs1dm", 1, None),
    (3, "link", 3, None), (4, "gs1dm", 5, None), (5, "link", 5, None),
    (6, "gs1dm", 0, None), (7, "ean13", 240, None), (8, "ean13", 365, None),
    (9, "ean13", 365, None), (10, "gs1dm", 540, None),
    (11, "bilancia", None, 1250), (12, "preincartato", 3, 180),
]

DESCRIZIONI = {
    "gs1dm": "GS1 DataMatrix: scadenza e lotto nel codice",
    "link": "QR GS1 Digital Link: scadenza e lotto nel link",
    "ean13": "EAN-13 classico: scadenza da inserire a mano",
    "bilancia": "Etichetta bilancia self-service: codice articolo + peso",
    "preincartato": "Preincartato al banco: peso, confezionamento e scadenza",
}


def cifra_controllo(base: str) -> str:
    totale = sum(int(c) * (3 if i % 2 == 0 else 1) for i, c in enumerate(reversed(base)))
    return str((10 - totale % 10) % 10)


def gtin13(numero: int) -> str:
    base = f"20{numero:010d}"
    return base + cifra_controllo(base)


def gtin14_peso_variabile(numero: int) -> str:
    base = "9" + gtin13(numero)[:12]
    return base + cifra_controllo(base)


def salva(immagine, percorso: Path):
    immagine = immagine.convert("1")
    immagine.resize((immagine.width * 6, immagine.height * 6), Image.NEAREST).save(percorso)


def main():
    (OUT / "codici").mkdir(parents=True, exist_ok=True)
    righe = []
    for i, (n, formato, giorni, peso) in enumerate(ETICHETTE, 1):
        nome, categoria, unita, prezzo, plu = CATALOGO[n]
        g14 = None if n in SENZA_GTIN else "0" + gtin13(n)
        lotto = f"L{OGGI:%y%m}{i:02d}"
        scadenza = OGGI + dt.timedelta(days=giorni) if giorni is not None else None
        nota = DESCRIZIONI[formato]

        if formato == "gs1dm":
            tipo_bc, dati = "gs1datamatrix", f"(01){g14}(17){scadenza:%y%m%d}(10){lotto}"
        elif formato == "link":
            tipo_bc, dati = "qrcode", f"https://id.gs1.org/01/{g14}/10/{lotto}?17={scadenza:%y%m%d}"
        elif formato == "ean13":
            tipo_bc, dati = "ean13", g14[1:]
            nota += f" (usa {scadenza:%d/%m/%Y})"
        elif formato == "bilancia":
            base = f"21{plu}{peso:05d}"
            tipo_bc, dati = "ean13", base + cifra_controllo(base)
            lotto = "-"
        else:
            tipo_bc = "gs1datamatrix"
            dati = (f"(01){gtin14_peso_variabile(n)}(13){OGGI:%y%m%d}"
                    f"(17){scadenza:%y%m%d}(3103){peso:06d}(10){lotto}")

        file = f"codici/{i:02d}.png"
        salva(treepoem.generate_barcode(barcode_type=tipo_bc, data=dati), OUT / file)
        if n in NON_IN_CATALOGO:
            nota += " | NON in catalogo: serve l'ok dell'admin"
        info_peso = f"{peso} g" if peso else ""
        info_scad = f"{scadenza:%d/%m/%Y} (+{giorni} gg)" if scadenza else "nessuna"
        righe.append(
            f"<tr><td><img src='{file}' alt=''></td><td>{html.escape(nome)}</td>"
            f"<td>{html.escape(categoria)}</td><td>{lotto}</td><td>{info_scad}</td>"
            f"<td>{info_peso}</td><td>{html.escape(nota)}</td></tr>"
        )

    catalogo = [
        {"gtin": None if n in SENZA_GTIN else "0" + gtin13(n), "codice_bilancia": plu,
         "nome": nome, "categoria": categoria, "unita": unita, "prezzo_centesimi": prezzo}
        for n, (nome, categoria, unita, prezzo, plu) in CATALOGO.items() if n not in NON_IN_CATALOGO
    ]
    (OUT / "catalogo_demo.json").write_text(json.dumps(catalogo, ensure_ascii=False, indent=2))
    (OUT / "foglio_demo.html").write_text(f"""<!doctype html><html lang="it"><head>
<meta charset="utf-8"><title>Codici demo Racoonix</title><style>
body{{font-family:sans-serif;background:#F6F0E4;color:#2E3A59;padding:1rem}}
table{{border-collapse:collapse;width:100%}}td,th{{border:1px solid #6B7A8F;padding:.5rem}}
img{{width:150px;image-rendering:pixelated;background:#fff;padding:8px}}
</style></head><body><h1>Codici demo Racoonix - generati il {OGGI:%d/%m/%Y}</h1>
<table><tr><th>Codice</th><th>Prodotto</th><th>Categoria</th><th>Lotto</th>
<th>Scadenza</th><th>Peso</th><th>Note</th></tr>{''.join(righe)}</table></body></html>""")
    print(f"Generate {len(ETICHETTE)} etichette in demo/ (date calcolate da {OGGI:%d/%m/%Y})")


if __name__ == "__main__":
    main()
