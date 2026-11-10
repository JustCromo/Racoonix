import re
import sys

from flask_migrate import upgrade
from sqlalchemy import text

from . import MIGRAZIONI, create_app, db
from . import negozio
from .config import leggi_secret
from .lingua import testo_negozio
from .models import Categoria, Ruolo, Sottocategoria, Utente

def N_(testo):
    """Segna un testo da tradurre senza tradurlo subito: lo traduce il bootstrap nella lingua del negozio."""
    return testo


RUOLI = ["admin", "magazziniere", "dipendente"]

# nome, richiede scadenza, giorni freschezza, (giorni, %) fascia 1, (giorni, %) fascia 2
CATEGORIE = [
    (N_("Carne"), True, None, (3, 20), (1, 40)),
    (N_("Salumi e formaggi"), True, None, (3, 20), (1, 40)),
    (N_("Latticini"), True, None, (3, 20), (1, 40)),
    (N_("Forno"), True, None, (2, 20), (1, 40)),
    (N_("Ortofrutta"), False, 5, (0, 0), (0, 0)),
    (N_("Pasta"), True, None, (0, 0), (0, 0)),
    (N_("Dolci"), True, None, (0, 0), (0, 0)),
    (N_("Conserve"), True, None, (0, 0), (0, 0)),
    (N_("Bevande"), True, None, (0, 0), (0, 0)),
    (N_("Surgelati"), True, None, (0, 0), (0, 0)),
    (N_("Edicola"), False, None, (0, 0), (0, 0)),
    (N_("Casa e igiene"), False, None, (0, 0), (0, 0)),
]

SOTTOCATEGORIE = {
    N_("Carne"): [N_("Bovino"), N_("Pollame"), N_("Suino")],
    N_("Salumi e formaggi"): [N_("Salumi"), N_("Formaggi")],
    N_("Latticini"): [N_("Latte"), N_("Yogurt"), N_("Formaggi freschi")],
    N_("Forno"): [N_("Pane"), N_("Prodotti da forno")],
    N_("Ortofrutta"): [N_("Frutta"), N_("Verdura")],
    N_("Pasta"): [N_("Pasta secca"), N_("Pasta fresca")],
    N_("Dolci"): [N_("Biscotti"), N_("Merendine")],
    N_("Conserve"): [N_("Pomodoro"), N_("Legumi")],
    N_("Bevande"): [N_("Acqua"), N_("Bibite")],
    N_("Surgelati"): [N_("Verdure surgelate"), N_("Pesce surgelato")],
    N_("Edicola"): [N_("Riviste"), N_("Figurine e carte")],
    N_("Casa e igiene"): [N_("Detersivi"), N_("Igiene personale")],
}


def concedi_permessi():
    """Minimo privilegio: racoonix_app legge e scrive dati, ma non cambia la struttura del db,
    non crea utenti e sul registro attivita' puo' solo aggiungere righe."""
    password = leggi_secret("db_app_password")
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
        # Le categorie iniziali nascono nella lingua del negozio
        if not db.session.scalar(db.select(Categoria).limit(1)):
            for nome, scadenza, freschezza, (g1, p1), (g2, p2) in CATEGORIE:
                db.session.add(Categoria(
                    nome=testo_negozio(nome), richiede_scadenza=scadenza, giorni_freschezza=freschezza,
                    sconto1_giorni=g1, sconto1_perc=p1, sconto2_giorni=g2, sconto2_perc=p2,
                ))
        if not db.session.scalar(db.select(Sottocategoria).limit(1)):
            for nome_categoria, nomi in SOTTOCATEGORIE.items():
                categoria = db.session.scalar(db.select(Categoria).filter_by(nome=testo_negozio(nome_categoria)))
                if categoria:
                    for nome in nomi:
                        db.session.add(Sottocategoria(categoria_id=categoria.id, nome=testo_negozio(nome)))
        db.session.commit()

        ruolo_admin = db.session.scalar(db.select(Ruolo).filter_by(nome="admin"))
        admin_presente = db.session.scalar(db.select(Utente.id).where(Utente.ruoli.contains(ruolo_admin)).limit(1))
        if admin_presente and not negozio.configurato():
            # Installazione precedente (configurata dal terminale): porto le sue impostazioni nel db
            valori = negozio.impostazioni()
            negozio.salva(nome=valori["nome"], lingua=valori["lingua"], paese=valori["paese"],
                          fuso=valori["fuso"], reti_admin=valori["reti_admin"], configurato="1")
            db.session.commit()
            print("[bootstrap] impostazioni importate dalla configurazione precedente")
        if negozio.configurato():
            print("[bootstrap] Racoonix e' configurato")
        else:
            print("[bootstrap] Racoonix aspetta la configurazione iniziale: ./racoonix.sh link")
    return 0


if __name__ == "__main__":
    sys.exit(main())
