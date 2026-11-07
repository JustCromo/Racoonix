import sys
from pathlib import Path

from . import create_app, db
from .models import AuditLog, Categoria, Ruolo, Utente

RUOLI = ["admin", "magazziniere", "dipendente"]

# nome, richiede scadenza, giorni freschezza, (giorni, %) fascia 1, (giorni, %) fascia 2
CATEGORIE = [
    ("Carne", True, None, (3, 20), (1, 40)),
    ("Salumi e formaggi", True, None, (3, 20), (1, 40)),
    ("Latticini", True, None, (3, 20), (1, 40)),
    ("Forno", True, None, (2, 20), (1, 40)),
    ("Ortofrutta", False, 5, (0, 0), (0, 0)),
    ("Pasta", True, None, (0, 0), (0, 0)),
    ("Dolci", True, None, (0, 0), (0, 0)),
    ("Conserve", True, None, (0, 0), (0, 0)),
    ("Bevande", True, None, (0, 0), (0, 0)),
    ("Surgelati", True, None, (0, 0), (0, 0)),
    ("Edicola", False, None, (0, 0), (0, 0)),
    ("Casa e igiene", False, None, (0, 0), (0, 0)),
]
CREDENZIALI = Path("/run/secrets/admin_credentials")


def main():
    app = create_app()
    with app.app_context():
        db.create_all()

        for nome in RUOLI:
            if not db.session.scalar(db.select(Ruolo).filter_by(nome=nome)):
                db.session.add(Ruolo(nome=nome))
        if not db.session.scalar(db.select(Categoria).limit(1)):
            for nome, scadenza, freschezza, (g1, p1), (g2, p2) in CATEGORIE:
                db.session.add(Categoria(
                    nome=nome, richiede_scadenza=scadenza, giorni_freschezza=freschezza,
                    sconto1_giorni=g1, sconto1_perc=p1, sconto2_giorni=g2, sconto2_perc=p2,
                ))
        db.session.commit()

        ruolo_admin = db.session.scalar(db.select(Ruolo).filter_by(nome="admin"))
        if db.session.scalar(db.select(Utente).where(Utente.ruoli.contains(ruolo_admin)).limit(1)):
            print("[bootstrap] admin gia' presente")
            return 0

        if not CREDENZIALI.exists():
            print("[bootstrap] ERRORE: manca il secret admin_credentials", file=sys.stderr)
            return 1
        righe = CREDENZIALI.read_text().strip().splitlines()
        if len(righe) != 2 or not righe[1].startswith("$argon2"):
            print("[bootstrap] ERRORE: admin_credentials non valido", file=sys.stderr)
            return 1

        admin = Utente(username=righe[0].strip(), password_hash=righe[1].strip(),
                       deve_cambiare_password=False)
        admin.ruoli.append(ruolo_admin)
        db.session.add(admin)
        db.session.add(AuditLog(azione="bootstrap_admin", dettaglio="primo admin creato"))
        db.session.commit()
        print("[bootstrap] admin creato")
    return 0


if __name__ == "__main__":
    sys.exit(main())
