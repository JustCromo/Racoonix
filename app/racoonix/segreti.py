"""Primo avvio: genera i segreti (password del database, chiave delle sessioni) dentro volumi Docker
dedicati. Non sovrascrive mai quelli esistenti, e puo' importare quelli di una vecchia installazione."""
import os
import secrets
import shutil
import sys
from pathlib import Path

DESTINAZIONI = {"db_password": Path("/segreti/db"), "db_app_password": Path("/segreti/app"),
                "flask_secret": Path("/segreti/app")}
VECCHI = Path("/vecchi")


def main():
    for nome, cartella in DESTINAZIONI.items():
        cartella.mkdir(parents=True, exist_ok=True)
        file = cartella / nome
        if file.exists() and file.stat().st_size > 0:
            continue
        vecchio = VECCHI / nome
        if vecchio.exists() and vecchio.stat().st_size > 0:
            shutil.copyfile(vecchio, file)
            print(f"[segreti] {nome}: importato dalla vecchia installazione")
        else:
            file.write_text(secrets.token_hex(32))
            print(f"[segreti] {nome}: generato")
        # Leggibile dai container che montano questo volume (e solo da loro), mai scrivibile
        os.chmod(file, 0o444)
    return 0


if __name__ == "__main__":
    sys.exit(main())
