import re
import sys
from pathlib import Path

from flask_migrate import upgrade
from sqlalchemy import text

from . import MIGRAZIONI, create_app, db
from .models import AuditLog, Categoria, Ruolo, Sottocategoria, Utente

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

SOTTOCATEGORIE = {
    "Carne": ["Bovino", "Pollame", "Suino"],
    "Salumi e formaggi": ["Salumi", "Formaggi"],
    "Latticini": ["Latte", "Yogurt", "Formaggi freschi"],
    "Forno": ["Pane", "Prodotti da forno"],
    "Ortofrutta": ["Frutta", "Verdura"],
    "Pasta": ["Pasta secca", "Pasta fresca"],
    "Dolci": ["Biscotti", "Merendine"],
    "Conserve": ["Pomodoro", "Legumi"],
    "Bevande": ["Acqua", "Bibite"],
    "Surgelati": ["Verdure surgelate", "Pesce surgelato"],
    "Edicola": ["Riviste", "Figurine e carte"],
    "Casa e igiene": ["Detersivi", "Igiene personale"],
}
CREDENZIALI = Path("/run/secrets/admin_credentials")


def concedi_permessi():
    """Minimo privilegio: racoonix_app legge e scrive dati, ma non cambia la struttura del db,
    non crea utenti e sul registro attivita' puo' solo aggiungere righe."""
    password = Path("/run/secrets/db_app_password").read_text().strip()
    if not re.fullmatch(r"[A-Za-z0-9]{32,128}", password):
        raise RuntimeError("db_app_password non valida: servono 32-128 caratteri alfanumerici")
    for istruzione in (
        "DO $$ BEGIN IF NOT EXISTS (SELECT 1 FROM pg_roles WHERE rolname = 'racoonix_app') "
        "THEN CREATE ROLE racoonix_app; END IF; END $$",
        f"ALTER ROLE racoonix_app WITH LOGIN NOSUPERUSER NOCREATEDB NOCREATEROLE NOREPLICATION PASSWORD '{password}'",
        "REVOKE CREATE ON SCHEMA public FROM PUBLIC",
        "GRANT USAGE ON SCHEMA public TO racoonix_app",
        "GRANT SELECT, INSERT, UPDATE, DELETE ON ALL TABLES IN SCHEMA public TO racoonix_app",
        "REVOKE UPDATE, DELETE, TRUNCATE ON audit_log FROM racoonix_app",
        "REVOKE INSERT, UPDATE, DELETE ON alembic_version FROM racoonix_app",
        "GRANT USAGE, SELECT ON ALL SEQUENCES IN SCHEMA public TO racoonix_app",
    ):
        db.session.execute(text(istruzione))
    db.session.commit()
    print("[bootstrap] permessi di racoonix_app aggiornati")


def main():
    app = create_app()
    with app.app_context():
        upgrade(directory=MIGRAZIONI)
        concedi_permessi()

        for nome in RUOLI:
            if not db.session.scalar(db.select(Ruolo).filter_by(nome=nome)):
                db.session.add(Ruolo(nome=nome))
        if not db.session.scalar(db.select(Categoria).limit(1)):
            for nome, scadenza, freschezza, (g1, p1), (g2, p2) in CATEGORIE:
                db.session.add(Categoria(
                    nome=nome, richiede_scadenza=scadenza, giorni_freschezza=freschezza,
                    sconto1_giorni=g1, sconto1_perc=p1, sconto2_giorni=g2, sconto2_perc=p2,
                ))
        if not db.session.scalar(db.select(Sottocategoria).limit(1)):
            for nome_categoria, nomi in SOTTOCATEGORIE.items():
                categoria = db.session.scalar(db.select(Categoria).filter_by(nome=nome_categoria))
                if categoria:
                    for nome in nomi:
                        db.session.add(Sottocategoria(categoria_id=categoria.id, nome=nome))
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
