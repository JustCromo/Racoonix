import ipaddress
import os
from datetime import timedelta
from pathlib import Path
from urllib.parse import quote_plus

SECRETS_DIR = Path("/run/secrets")


def leggi_secret(nome: str) -> str:
    percorso = SECRETS_DIR / nome
    if not percorso.exists():
        raise RuntimeError(f"Secret mancante: {nome}")
    return percorso.read_text().strip()


def reti_admin():
    valore = os.environ.get("ADMIN_IP_CONSENTITI", "127.0.0.1/32")
    return [ipaddress.ip_network(v.strip(), strict=False) for v in valore.split(",") if v.strip()]


class Config:
    MARKET_NAME = os.environ.get("MARKET_NAME", "Racoonix Demo")
    SECRET_KEY = leggi_secret("flask_secret")
    SQLALCHEMY_DATABASE_URI = (
        "postgresql+psycopg://racoonix:"
        f"{quote_plus(leggi_secret('db_password'))}@db:5432/{os.environ.get('RACOONIX_DB_NOME', 'racoonix')}"
    )
    SQLALCHEMY_TRACK_MODIFICATIONS = False
    SESSION_COOKIE_SECURE = True
    SESSION_COOKIE_HTTPONLY = True
    SESSION_COOKIE_SAMESITE = "Strict"
    PERMANENT_SESSION_LIFETIME = timedelta(minutes=30)
    ADMIN_RETI = reti_admin()
    WTF_CSRF_TIME_LIMIT = 3600
    RATELIMIT_HEADERS_ENABLED = False


def prefissi_bilancia():
    valore = os.environ.get("BILANCIA_PREFISSI", "21,22,23,24,25,26,27,28,29")
    prefissi = tuple(v.strip() for v in valore.split(",") if v.strip())
    if not all(len(p) == 2 and p.startswith("2") and p.isdigit() for p in prefissi):
        raise RuntimeError("BILANCIA_PREFISSI non valido")
    return prefissi


Config.BILANCIA_PREFISSI = prefissi_bilancia()
