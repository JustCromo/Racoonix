"""Scarica le icone Tabler (licenza MIT) e le unisce in un unico file SVG servito dal server."""
import re
import urllib.request
from pathlib import Path

VERSIONE = "3.19.0"
NOMI = ["chart-bar", "bell", "box", "truck", "shopping-cart", "scale", "tags",
        "building-warehouse", "category", "users", "camera", "moon", "sun", "key", "logout", "user", "circle-check", "history", "user-plus", "shield", "plug-connected", "eye", "eye-off", "copy", "check", "alert-triangle", "building-store", "device-mobile"]
DESTINAZIONE = Path("app/racoonix/static/img/icone.svg")

simboli = []
for nome in NOMI:
    url = f"https://cdn.jsdelivr.net/npm/@tabler/icons@{VERSIONE}/icons/outline/{nome}.svg"
    svg = urllib.request.urlopen(url, timeout=20).read().decode()
    interno = re.search(r"<svg[^>]*>(.*)</svg>", svg, re.S).group(1).strip()
    simboli.append(f'<symbol id="{nome}" viewBox="0 0 24 24" fill="none" stroke="currentColor" '
                   f'stroke-width="2" stroke-linecap="round" stroke-linejoin="round">{interno}</symbol>')
    print(f"ok: {nome}")
DESTINAZIONE.parent.mkdir(parents=True, exist_ok=True)
DESTINAZIONE.write_text('<svg xmlns="http://www.w3.org/2000/svg">' + "".join(simboli) + "</svg>\n")
print(f"Creato {DESTINAZIONE} con {len(simboli)} icone")
