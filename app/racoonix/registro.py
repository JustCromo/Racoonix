"""Registro attivita': il log di audit reso leggibile per l'admin, con riepilogo di sicurezza.
Il registro e' in sola lettura: nessuna pagina permette di modificarlo o cancellarlo."""
import csv
import io
import re
from datetime import datetime, timedelta, timezone

from flask import Blueprint, Response, g, render_template, request
from sqlalchemy import func, or_

from . import db
from .auth import registra, richiede_ruolo
from .lingua import _, _l
from .models import AuditLog, Utente

bp = Blueprint("registro", __name__, url_prefix="/admin/registro")
PER_PAGINA = 50
SOGLIA_SOSPETTO = 5
CATEGORIE = {"sicurezza": _l("Sicurezza"), "utenti": _l("Utenti e dispositivi"), "magazzino": _l("Magazzino"),
             "prodotti": _l("Prodotti e prezzi"), "sistema": _l("Sistema")}
PERIODI = {"1": _l("Ultime 24 ore"), "7": _l("Ultimi 7 giorni"), "30": _l("Ultimi 30 giorni"), "tutto": _l("Tutto")}
TENTATIVI_FALLITI = ("login_fallito", "login_bloccato", "login_dispositivo_bloccato", "admin_ip_non_consentito")

# azione: (categoria, descrizione leggibile, evento da evidenziare)
AZIONI = {
    "login_ok": ("sicurezza", _l("Accesso riuscito"), False),
    "login_fallito": ("sicurezza", _l("Accesso non riuscito"), True),
    "login_bloccato": ("sicurezza", _l("Accesso tentato durante il blocco dell'account"), True),
    "account_bloccato": ("sicurezza", _l("Account bloccato per troppi tentativi"), True),
    "login_dispositivo_bloccato": ("sicurezza", _l("Tentativo da un dispositivo bloccato"), True),
    "admin_ip_non_consentito": ("sicurezza", _l("Admin da un dispositivo non autorizzato"), True),
    "logout": ("sicurezza", _l("Uscita"), False),
    "cambio_password": ("sicurezza", _l("Password cambiata"), False),
    "richiesta_reset_password": ("sicurezza", _l("Richiesta di nuova password"), False),
    "bootstrap_admin": ("sicurezza", _l("Primo amministratore creato"), False),
    "registro_esportato": ("sicurezza", _l("Registro esportato"), False),
    "configurazione_codice_errato": ("sicurezza", _l("Codice di configurazione errato o scaduto"), True),
    "configurazione_completata": ("sicurezza", _l("Configurazione iniziale completata"), False),
    "impostazioni_modificate": ("sistema", _l("Impostazioni del negozio modificate"), False),
    "utente_creato": ("utenti", _l("Utente creato"), False),
    "ruoli_modificati": ("utenti", _l("Ruoli modificati"), False),
    "utente_disattivato": ("utenti", _l("Utente disattivato"), False),
    "utente_riattivato": ("utenti", _l("Utente riattivato"), False),
    "utente_sbloccato": ("utenti", _l("Utente sbloccato"), False),
    "password_resettata": ("utenti", _l("Password temporanea generata"), False),
    "utente_archiviato": ("utenti", _l("Utente eliminato (storico conservato)"), False),
    "utente_eliminato": ("utenti", _l("Utente eliminato definitivamente"), False),
    "dispositivo_nuovo": ("utenti", _l("Richiesta di nuovo dispositivo"), False),
    "dispositivo_approvato": ("utenti", _l("Dispositivo approvato"), False),
    "dispositivo_revocato": ("utenti", _l("Dispositivo revocato"), False),
    "carico": ("magazzino", _l("Carico merce"), False),
    "rifornimento": ("magazzino", _l("Scaffale rifornito"), False),
    "rettifica": ("magazzino", _l("Correzione quantita'"), False),
    "notifica_verifica": ("magazzino", _l("Verifica scadenza"), False),
    "notifica_rimosso": ("magazzino", _l("Rimozione scaduti"), False),
    "notifica_deteriorato": ("magazzino", _l("Scarto per freschezza"), False),
    "notifica_ok": ("magazzino", _l("Freschezza controllata"), False),
    "notifica_visto": ("magazzino", _l("Presa visione"), False),
    "notifica_bollino": ("magazzino", _l("Bollino sconto applicato"), False),
    "notifica_esaurimento": ("magazzino", _l("Prodotto messo in esaurimento"), False),
    "notifica_ignora": ("magazzino", _l("Richiesta ignorata"), False),
    "prodotto_approvato": ("prodotti", _l("Prodotto approvato"), False),
    "segnalazione_mancanza": ("magazzino", _l("Segnalato: sta finendo"), False),
    "scaffale_vuoto": ("magazzino", _l("Segnalato: scaffale vuoto"), False),
    "riordino_ordinato": ("prodotti", _l("Ordine segnato come inviato"), False),
    "riordino_annullato": ("prodotti", _l("Tolto dalla lista d'ordine"), False),
    "prodotto_esaurimento": ("prodotti", _l("Prodotto messo in esaurimento"), False),
    "prodotto_rifiutato": ("prodotti", _l("Prodotto rifiutato"), False),
    "prodotto_unito": ("prodotti", _l("Codice unito a un prodotto esistente"), False),
    "prodotto_modificato": ("prodotti", _l("Scheda prodotto modificata"), False),
    "codice_aggiunto": ("prodotti", _l("EAN aggiuntivo aggiunto"), False),
    "codice_rimosso": ("prodotti", _l("EAN aggiuntivo rimosso"), False),
    "sconto_manuale": ("prodotti", _l("Sconto applicato"), False),
    "sconto_tolto": ("prodotti", _l("Sconto tolto"), False),
    "programmazione_sconto": ("prodotti", _l("Sconto programmato"), False),
    "programmazione_rimossa": ("prodotti", _l("Programmazione sconto rimossa"), False),
    "fornitore_creato": ("prodotti", _l("Fornitore aggiunto"), False),
    "fornitore_modificato": ("prodotti", _l("Fornitore modificato"), False),
    "categoria_creata": ("prodotti", _l("Categoria aggiunta"), False),
    "categoria_modificata": ("prodotti", _l("Categoria modificata"), False),
    "sottocategoria_creata": ("prodotti", _l("Sottocategoria aggiunta"), False),
    "sottocategoria_modificata": ("prodotti", _l("Sottocategoria modificata"), False),
    "guida_nascondi": ("sistema", _l("Guida ai primi passi nascosta"), False),
    "guida_mostra": ("sistema", _l("Guida ai primi passi mostrata"), False),
    "guida_backup": ("sistema", _l("Backup notturni confermati"), False),
}


def descrivi(azione):
    return AZIONI.get(azione, ("sistema", azione.replace("_", " ").capitalize(), False))


def _filtri():
    a = request.args
    categoria = a.get("categoria") if a.get("categoria") in CATEGORIE else ""
    periodo = a.get("periodo") if a.get("periodo") in PERIODI else "7"
    testo_utente = a.get("utente") or ""
    utente_id = int(testo_utente) if re.fullmatch(r"[0-9]{1,9}", testo_utente) else None
    q = (a.get("q") or "").strip()[:100]
    testo_pagina = a.get("pagina") or ""
    pagina = int(testo_pagina) if re.fullmatch(r"[0-9]{1,4}", testo_pagina) else 0
    return categoria, periodo, utente_id, q, pagina


def _query(categoria, periodo, utente_id, q):
    stmt = db.select(AuditLog, Utente.username).outerjoin(Utente, AuditLog.utente_id == Utente.id)
    if periodo != "tutto":
        stmt = stmt.where(AuditLog.data_ora >= datetime.now(timezone.utc) - timedelta(days=int(periodo)))
    if categoria == "sistema":
        stmt = stmt.where(AuditLog.azione.not_in([a for a, (c, _x, _x) in AZIONI.items() if c != "sistema"]))
    elif categoria:
        stmt = stmt.where(AuditLog.azione.in_([a for a, (c, _x, _x) in AZIONI.items() if c == categoria]))
    if utente_id:
        stmt = stmt.where(AuditLog.utente_id == utente_id)
    if q:
        sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        modello = f"%{sicuro}%"
        stmt = stmt.where(or_(AuditLog.dettaglio.ilike(modello, escape="\\"), AuditLog.ip.ilike(modello, escape="\\"),
                              AuditLog.azione.ilike(modello, escape="\\")))
    return stmt.order_by(AuditLog.id.desc())


def _righe(stmt, pagina):
    risultati = db.session.execute(stmt.offset(pagina * PER_PAGINA).limit(PER_PAGINA + 1)).all()
    righe = []
    for voce, username in risultati[:PER_PAGINA]:
        categoria, etichetta, attenzione = descrivi(voce.azione)
        righe.append({"voce": voce, "username": username, "categoria": categoria,
                      "etichetta": etichetta, "attenzione": attenzione})
    return righe, len(risultati) > PER_PAGINA


def _riepilogo():
    da = datetime.now(timezone.utc) - timedelta(hours=24)
    falliti = (AuditLog.azione.in_(TENTATIVI_FALLITI), AuditLog.data_ora >= da)
    return {
        "falliti": db.session.scalar(db.select(func.count(AuditLog.id)).where(*falliti)),
        "indirizzi": db.session.scalar(db.select(func.count(func.distinct(AuditLog.ip))).where(*falliti)),
        "bloccati": db.session.scalar(db.select(func.count(AuditLog.id)).where(
            AuditLog.azione == "account_bloccato", AuditLog.data_ora >= da)),
        "admin_ip": db.session.scalar(db.select(func.count(AuditLog.id)).where(
            AuditLog.azione == "admin_ip_non_consentito", AuditLog.data_ora >= da)),
        "sospetti": db.session.execute(
            db.select(AuditLog.ip, func.count(AuditLog.id), func.max(AuditLog.data_ora)).where(*falliti)
            .group_by(AuditLog.ip).having(func.count(AuditLog.id) >= SOGLIA_SOSPETTO)
            .order_by(func.count(AuditLog.id).desc()).limit(5)).all(),
    }


def _contesto_righe():
    categoria, periodo, utente_id, q, pagina = _filtri()
    righe, altre = _righe(_query(categoria, periodo, utente_id, q), pagina)
    return {"righe": righe, "altre": altre, "pagina": pagina, "categorie": CATEGORIE}


@bp.get("/")
@richiede_ruolo("admin")
def pagina():
    categoria, periodo, utente_id, q, _x = _filtri()
    utenti = db.session.scalars(db.select(Utente).order_by(Utente.username)).all()
    return render_template("registro.html", riepilogo=_riepilogo(), utenti=utenti, periodi=PERIODI,
                           categoria=categoria, periodo=periodo, utente_id=utente_id, q=q,
                           soglia=SOGLIA_SOSPETTO, **_contesto_righe())


@bp.get("/risultati")
@richiede_ruolo("admin")
def risultati():
    return render_template("_registro_righe.html", **_contesto_righe())


def _cella_sicura(valore):
    """Protezione dalla CSV injection: Excel eseguirebbe come formula un testo che inizia con = + - @."""
    testo = str(valore)
    return "'" + testo if testo[:1] in ("=", "+", "-", "@", "\t", "\r") else testo


@bp.get("/esporta.csv")
@richiede_ruolo("admin")
def esporta():
    categoria, periodo, utente_id, q, _x = _filtri()
    righe = db.session.execute(_query(categoria, periodo, utente_id, q).limit(10_000)).all()
    buffer = io.StringIO()
    scrittore = csv.writer(buffer, delimiter=";")
    scrittore.writerow([_("data_ora"), _("categoria"), _("azione"), _("descrizione"), _("utente"), _("dettaglio"), "ip"])
    for voce, username in righe:
        categoria_voce, etichetta, _x = descrivi(voce.azione)
        scrittore.writerow([_cella_sicura(x) for x in (
            voce.data_ora.astimezone().isoformat(timespec="seconds"), CATEGORIE[categoria_voce], voce.azione,
            etichetta, username or "", voce.dettaglio or "", voce.ip or "")])
    registra("registro_esportato", g.utente.id, f"{len(righe)} righe, categoria {categoria or 'tutte'}, periodo {periodo}")
    db.session.commit()
    return Response("\ufeff" + buffer.getvalue(), mimetype="text/csv; charset=utf-8",
                    headers={"Content-Disposition": "attachment; filename=registro-racoonix.csv"})
