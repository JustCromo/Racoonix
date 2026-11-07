import getpass
import re
import sys
from pathlib import Path

from argon2 import PasswordHasher

USERNAME_OK = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
MIN_LUNGHEZZA = 12


def main():
    username = input("Username admin: ").strip()
    if not USERNAME_OK.match(username):
        print("Username non valido (3-40 caratteri: lettere, numeri, _ . -)")
        return 1
    password = getpass.getpass(f"Password (minimo {MIN_LUNGHEZZA} caratteri): ")
    if len(password) < MIN_LUNGHEZZA:
        print("Password troppo corta")
        return 1
    if password != getpass.getpass("Ripeti password: "):
        print("Le password non coincidono")
        return 1
    out = Path("/out/admin_credentials")
    out.write_text(f"{username}\n{PasswordHasher().hash(password)}\n")
    out.chmod(0o644)
    print("Fatto: salvato solo l'hash, la password non e' scritta da nessuna parte.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
