"""Servizio separato: lancia il controllo di scadenze, sconti e freschezza ogni ora."""
import time

from . import create_app, db
from .notifiche import controllo_giornaliero
from .sconti import applica_programmati

INTERVALLO_S = 3600
RIPROVA_S = 60


def main():
    app = create_app()
    while True:
        attesa = INTERVALLO_S
        with app.app_context():
            try:
                nuove = controllo_giornaliero() + applica_programmati()
                print(f"[scheduler] controllo eseguito: {nuove} nuove notifiche", flush=True)
            except Exception as errore:
                db.session.rollback()
                print(f"[scheduler] controllo non riuscito ({type(errore).__name__}), riprovo tra poco", flush=True)
                attesa = RIPROVA_S
        time.sleep(attesa)


if __name__ == "__main__":
    main()
