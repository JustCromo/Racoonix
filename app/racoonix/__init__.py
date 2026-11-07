import os

from flask import Flask, render_template, request
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
csrf = CSRFProtect()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    app = Flask(__name__)
    from .config import Config
    app.config.from_object(Config)
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_app(app)
    csrf.init_app(app)
    limiter.init_app(app)
    from .formato import data_it, euro, quantita
    app.add_template_filter(quantita, "quantita")
    app.add_template_filter(euro, "euro")
    app.add_template_filter(data_it, "data")

    from . import models  # noqa: F401
    from . import auth
    from .carico import bp as carico_bp
    from .cassa import bp as cassa_bp
    from .inventario import bp as inventario_bp
    from .prodotti import bp as prodotti_bp
    from .utenti import bp as utenti_bp
    for blueprint in (auth.bp, utenti_bp, carico_bp, prodotti_bp, inventario_bp, cassa_bp):
        app.register_blueprint(blueprint)
    app.before_request(auth.carica_utente)
    app.before_request(auth.obbligo_cambio_password)

    if os.environ.get("RACOONIX_TEST_SCANNER") == "1":
        from .scanner_test import bp as scanner_bp
        app.register_blueprint(scanner_bp)

    @app.context_processor
    def contesto():
        return {"market": app.config["MARKET_NAME"]}


    @app.get("/")
    @auth.login_richiesto
    def home():
        ruoli = auth.ruoli_attivi()
        da_approvare = 0
        if "admin" in ruoli:
            da_approvare = db.session.scalar(
                db.select(db.func.count(models.Prodotto.id)).filter_by(stato="in_attesa"))
        return render_template("home.html", ruoli=sorted(ruoli), ip=request.remote_addr,
                               test_scanner="scanner_test" in app.blueprints,
                               da_approvare=da_approvare)

    @app.get("/health")
    def health():
        return {"stato": "ok"}

    def errore(messaggio, codice):
        return render_template("errore.html", messaggio=messaggio), codice

    app.register_error_handler(403, lambda e: errore("Accesso non consentito", 403))
    app.register_error_handler(404, lambda e: errore("Pagina non trovata", 404))
    app.register_error_handler(429, lambda e: errore("Troppi tentativi, riprova tra poco", 429))
    app.register_error_handler(500, lambda e: errore("Errore interno", 500))
    app.register_error_handler(CSRFError, lambda e: errore("Sessione scaduta, ricarica la pagina", 400))

    return app
