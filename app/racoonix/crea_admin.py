import getpass
import os
import re
import sys
from pathlib import Path

from argon2 import PasswordHasher

USERNAME_OK = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")
MIN_LUNGHEZZA = 12
INGLESE = os.environ.get("RACOONIX_LINGUA") == "en"


def t(italiano, inglese):
    return inglese if INGLESE else italiano


def main():
    username = input(t("Username admin: ", "Admin username: ")).strip()
    if not USERNAME_OK.match(username):
        print(t("Username non valido (3-40 caratteri: lettere, numeri, _ . -)", "Invalid username (3-40 characters: letters, numbers, _ . -)"))
        return 1
    password = getpass.getpass(t(f"Password (minimo {MIN_LUNGHEZZA} caratteri): ", f"Password (at least {MIN_LUNGHEZZA} characters): "))
    if len(password) < MIN_LUNGHEZZA:
        print(t("Password troppo corta", "Password too short"))
        return 1
    if password != getpass.getpass(t("Ripeti password: ", "Repeat password: ")):
        print(t("Le password non coincidono", "The passwords don't match"))
        return 1
    out = Path("/out/admin_credentials")
    out.write_text(f"{username}\n{PasswordHasher().hash(password)}\n")
    out.chmod(0o644)
    print(t("Fatto: salvato solo l'hash, la password non e' scritta da nessuna parte.",
            "Done: only the hash was saved, the password isn't written anywhere."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
