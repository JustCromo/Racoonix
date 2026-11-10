from pathlib import Path

from flask import Flask, redirect, render_template, request, url_for
from flask_babel import Babel
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address
from flask_migrate import Migrate
from flask_sqlalchemy import SQLAlchemy
from flask_wtf.csrf import CSRFError, CSRFProtect
from werkzeug.middleware.proxy_fix import ProxyFix

db = SQLAlchemy()
migrate = Migrate()
MIGRAZIONI = str(Path(__file__).resolve().parent.parent / "migrations")
csrf = CSRFProtect()
babel = Babel()
limiter = Limiter(key_func=get_remote_address, storage_uri="memory://")


def create_app():
    app = Flask(__name__)
    from .config import Config
    app.config.from_object(Config)
    app.config["MAX_CONTENT_LENGTH"] = 64 * 1024
    app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1)
    db.init_app(app)
    migrate.init_app(app, db, directory=MIGRAZIONI)
    csrf.init_app(app)
    limiter.init_app(app)
    from .lingua import LINGUE, _, lingua_negozio, nome_ruolo, nome_stato, paese_negozio, scegli_lingua, testi_js
    from .formato import VALUTE
    app.config["BABEL_DEFAULT_LOCALE"] = lingua_negozio()
    babel.init_app(app, locale_selector=scegli_lingua)
    from .formato import data_it, data_ora_it, euro, quantita, quantita_input
    app.add_template_filter(quantita, "quantita")
    app.add_template_filter(euro, "euro")
    app.add_template_filter(data_it, "data")
    app.add_template_filter(data_ora_it, "data_ora")
    app.add_template_filter(quantita_input, "quantita_input")

    from . import models  # noqa: F401
    from . import auth
    from .carico import bp as carico_bp
    from .notifiche_web import bp as notifiche_bp, conta_notifiche
    from .anagrafica import bp as anagrafica_bp
    from .dashboard import bp as dashboard_bp
    from .inventario import bp as inventario_bp
    from .prodotti import bp as prodotti_bp
    from .utenti import bp as utenti_bp
    for blueprint in (auth.bp, utenti_bp, carico_bp, prodotti_bp, inventario_bp, notifiche_bp, anagrafica_bp, dashboard_bp):
        app.register_blueprint(blueprint)
    from .collega import bp as collega_bp
    app.register_blueprint(collega_bp)
    from .registro import bp as registro_bp
    app.register_blueprint(registro_bp)
    from .ordini import bp as ordini_bp
    app.register_blueprint(ordini_bp)
    from .configurazione import bp as configurazione_bp
    app.register_blueprint(configurazione_bp)
    from .impostazioni import bp as impostazioni_bp
    app.register_blueprint(impostazioni_bp)
    from . import negozio
    app.before_request(negozio.applica_fuso)
    app.before_request(auth.carica_utente)
    app.before_request(auth.obbligo_cambio_password)

    @app.before_request
    def serve_configurazione():
        """Finche' il negozio non e' configurato, esiste solo la pagina di configurazione (con il suo codice)."""
        if request.endpoint in (None, "static", "health", "configurazione.pagina"):
            return None
        if not negozio.configurato():
            return render_template("configurazione_attesa.html"), 503
        return None
    app.context_processor(conta_notifiche)
    from .interfaccia import contesto as contesto_interfaccia
    app.context_processor(contesto_interfaccia)


    @app.context_processor
    def contesto():
        return {"market": negozio.impostazioni()["nome"], "lingua": scegli_lingua(), "lingue": LINGUE,
                "paese": paese_negozio(), "testi_js": testi_js(), "nome_ruolo": nome_ruolo, "nome_stato": nome_stato,
                "simbolo_valuta": "".join(VALUTE[paese_negozio()]).strip()}


    @app.after_request
    def niente_cache(risposta):
        """Le pagine non restano nella cache: su un dispositivo condiviso, "indietro" dopo il logout non mostra niente."""
        if request.endpoint != "static" and risposta.mimetype == "text/html":
            risposta.headers["Cache-Control"] = "no-store"
        return risposta

    @app.get("/")
    @auth.login_richiesto
    def home():
        """Ognuno entra dove lavora: l'admin sulla dashboard, gli altri sulle cose da fare."""
        if "admin" in auth.ruoli_attivi():
            return redirect(url_for("dashboard.pagina"))
        return redirect(url_for("notifiche.pagina"))

    @app.get("/health")
    def health():
        return {"stato": "ok"}
    def errore(messaggio, codice):
        return render_template("errore.html", messaggio=messaggio), codice

    app.register_error_handler(403, lambda e: errore(_("Accesso non consentito"), 403))
    app.register_error_handler(404, lambda e: errore(_("Pagina non trovata"), 404))
    app.register_error_handler(429, lambda e: errore(_("Troppi tentativi, riprova tra poco"), 429))
    app.register_error_handler(500, lambda e: errore(_("Errore interno"), 500))
    app.register_error_handler(CSRFError, lambda e: errore(_("Sessione scaduta, ricarica la pagina"), 400))

    return app
