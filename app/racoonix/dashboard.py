"""Dashboard admin: tutti i numeri sono calcolati dal server, il browser riceve solo la pagina."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request, url_for
from sqlalchemy import func

from . import db
from .auth import richiede_ruolo
from .models import AuditLog, Fornitore, Impostazione, Lotto, Notifica, Prodotto, Riordino, Ruolo, Scarto, Sconto, Utente

bp = Blueprint("dashboard", __name__, url_prefix="/admin/dashboard")
PERIODI = {1: "Oggi", 7: "Ultimi 7 giorni", 30: "Ultimi 30 giorni"}
MOTIVI = {"scaduto": "Scaduti", "deteriorato": "Deteriorati", "non_conforme": "Non conformi"}
LARGHEZZA, ALTEZZA = 600, 130
ETICHETTE_ATTIVITA = {"carico": "Carico merce", "rettifica": "Correzione quantita'",
                      "notifica_verifica": "Verifica scadenza", "notifica_rimosso": "Rimozione scaduti",
                      "notifica_deteriorato": "Scarto per freschezza", "rifornimento": "Scaffale rifornito",
                      "prodotto_approvato": "Prodotto approvato", "sconto_manuale": "Sconto applicato", "segnalazione_mancanza": "Segnalato: sta finendo"}


def _valore(prodotto, quantita):
    """Valore a prezzo di vendita: pezzi x prezzo, oppure grammi x prezzo al kg."""
    prezzo = prodotto.prezzo_centesimi
    if prezzo is None:
        return 0
    return (prezzo * quantita + 500) // 1000 if prodotto.unita == "kg" else prezzo * quantita


@bp.get("/")
@richiede_ruolo("admin")
def pagina():
    giorni = request.args.get("giorni", "7")
    giorni = int(giorni) if giorni in ("1", "7", "30") else 7
    oggi = date.today()
    primo = oggi - timedelta(days=giorni - 1)
    inizio = datetime.combine(primo, time.min).astimezone()
    vivi = (Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0)

    # Scarti del periodo: per motivo e per prodotto (quelli che fanno perdere di piu')
    scarti = {m: {"etichetta": e, "numero": 0, "valore": 0} for m, e in MOTIVI.items()}
    per_prodotto = {}
    for scarto, prodotto in db.session.execute(
            db.select(Scarto, Prodotto).join(Lotto, Scarto.lotto_id == Lotto.id)
            .join(Prodotto, Lotto.prodotto_id == Prodotto.id).where(Scarto.data >= inizio)).all():
        valore = _valore(prodotto, scarto.quantita)
        scarti[scarto.motivo]["numero"] += 1
        scarti[scarto.motivo]["valore"] += valore
        voce = per_prodotto.setdefault(prodotto.id, {"p": prodotto, "quantita": 0, "valore": 0})
        voce["quantita"] += scarto.quantita
        voce["valore"] += valore
    piu_buttati = sorted(per_prodotto.values(), key=lambda v: v["valore"], reverse=True)[:5]

    # Valore del magazzino: l'unico numero certo (lo scaffale cambia con gli acquisti dei clienti)
    valore_magazzino = sum(_valore(p, l.qta_magazzino) for l, p in db.session.execute(
        db.select(Lotto, Prodotto).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
        .where(Prodotto.stato == "attivo", Lotto.qta_magazzino > 0)).all())

    aperte = dict(db.session.execute(
        db.select(Notifica.tipo, func.count(Notifica.id))
        .where(Notifica.stato == "aperta").group_by(Notifica.tipo)).all())
    voci = [("da_rimuovere", "Da rimuovere", True), ("reset_password", "Richieste di nuova password", True),
            ("dispositivo", "Dispositivi da approvare", True), ("da_approvare", "Prodotti da approvare", True),
            ("riempi", "Scaffali da riempire", False), ("sconto", "Bollini da applicare", False),
            ("in_scadenza", "Lotti in scadenza", False), ("freschezza", "Freschezza da controllare", False)]
    attenzione = [{"etichetta": e, "numero": aperte[tipo], "urgente": u} for tipo, e, u in voci if aperte.get(tipo)]
    da_ordinare = db.session.scalar(db.select(func.count(Riordino.id)).where(Riordino.stato == "da_ordinare"))
    if da_ordinare:
        attenzione.insert(0, {"etichetta": "Da ordinare ai fornitori", "numero": da_ordinare, "urgente": True,
                              "link": url_for("ordini.pagina")})
    per_fornitore = db.session.execute(
        db.select(Fornitore, func.count(Riordino.id))
        .join(Prodotto, Prodotto.fornitore_id == Fornitore.id)
        .join(Riordino, Riordino.prodotto_id == Prodotto.id)
        .where(Riordino.stato == "da_ordinare").group_by(Fornitore.id)).all()
    for fornitore, numero in per_fornitore:
        if fornitore.ordina_oggi:
            attenzione.insert(0, {"etichetta": f"Oggi ordina a {fornitore.ragione_sociale}", "numero": numero,
                                  "urgente": True, "link": url_for("ordini.pagina", _anchor=f"fornitore-{fornitore.id}")})

    in_scadenza = db.session.execute(
        db.select(Lotto, Prodotto).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
        .where(*vivi, Lotto.data_scadenza >= oggi, Lotto.data_scadenza <= oggi + timedelta(days=3))
        .order_by(Lotto.data_scadenza).limit(6)).all()
    sconti_attivi = db.session.scalar(db.select(func.count(Sconto.id)).where(Sconto.attivo.is_(True)))

    per_giorno_scadenza = defaultdict(int)
    for (scadenza,) in db.session.execute(
            db.select(Lotto.data_scadenza).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
            .where(*vivi, Lotto.data_scadenza >= oggi, Lotto.data_scadenza <= oggi + timedelta(days=13))).all():
        per_giorno_scadenza[scadenza] += 1
    quattordici = [oggi + timedelta(days=i) for i in range(14)]
    massimo14 = max([per_giorno_scadenza[d] for d in quattordici] + [1])
    passo14 = LARGHEZZA / 14
    barre_scadenze = [{"etichetta": d.strftime("%d/%m"), "titolo": d.strftime("%d/%m/%Y"),
                       "valore": per_giorno_scadenza[d], "testo": str(per_giorno_scadenza[d]),
                       "x": round(i * passo14 + passo14 * 0.15, 1), "w": round(passo14 * 0.7, 1),
                       "centro": round(i * passo14 + passo14 / 2, 1),
                       "h": round(per_giorno_scadenza[d] / massimo14 * ALTEZZA, 1), "mostra": i % 2 == 0,
                       "link": url_for("inventario.pagina", giorno=d.isoformat()) if per_giorno_scadenza[d] else None}
                      for i, d in enumerate(quattordici)]
    numeri = {
        "lotti": db.session.scalar(db.select(func.count(Lotto.id)).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
                                   .where(*vivi)),
        "prodotti": db.session.scalar(db.select(func.count(func.distinct(Lotto.prodotto_id)))
                                      .join(Prodotto, Lotto.prodotto_id == Prodotto.id).where(*vivi)),
        "scadenza_7": db.session.scalar(db.select(func.count(Lotto.id)).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
                                        .where(*vivi, Lotto.data_scadenza >= oggi,
                                               Lotto.data_scadenza <= oggi + timedelta(days=7))),
        "verifiche": db.session.scalar(db.select(func.count(Notifica.id)).where(
            Notifica.tipo == "in_scadenza", Notifica.stato == "chiusa",
            Notifica.chiusa_da.is_not(None), Notifica.chiusa_il >= inizio)),
        "segnalazioni": db.session.scalar(db.select(func.count(AuditLog.id)).where(
            AuditLog.azione == "segnalazione_mancanza", AuditLog.data_ora >= inizio)),
    }
    attivita = db.session.execute(
        db.select(AuditLog, Utente.username).outerjoin(Utente, AuditLog.utente_id == Utente.id)
        .where(AuditLog.azione.in_(list(ETICHETTE_ATTIVITA)))
        .order_by(AuditLog.data_ora.desc()).limit(8)).all()

    return render_template(
        "dashboard.html", giorni=giorni, saluto=_saluto(), periodi=PERIODI, primo=primo, oggi=oggi,
        scarti=scarti.values(), valore_scarti=sum(s["valore"] for s in scarti.values()), piu_buttati=piu_buttati,
        valore_magazzino=valore_magazzino, attenzione=attenzione, in_scadenza=in_scadenza,
        sconti_attivi=sconti_attivi, barre_scadenze=barre_scadenze, numeri=numeri, attivita=attivita,
        etichette_attivita=ETICHETTE_ATTIVITA, guida=_guida(),
        guida_nascosta=_impostazione("guida_nascosta") == "1" and _guida(True) is not None)


def _saluto():
    ora = datetime.now().hour
    return "Buongiorno" if ora < 13 else ("Buon pomeriggio" if ora < 18 else "Buonasera")


def _impostazione(chiave):
    voce = db.session.get(Impostazione, chiave)
    return voce.valore if voce else None


def _imposta(chiave, valore):
    voce = db.session.get(Impostazione, chiave) or Impostazione(chiave=chiave, valore=valore)
    voce.valore = valore
    db.session.add(voce)


def _guida(ignora_nascosta=False):
    """Primi passi: ogni passo si completa da solo guardando i dati, tranne il backup (che vive sul server)."""
    if not ignora_nascosta and _impostazione("guida_nascosta") == "1":
        return None
    conta = lambda stmt: db.session.scalar(stmt) or 0
    telefoni = db.session.scalar(
        db.select(AuditLog.id).join(Utente, AuditLog.utente_id == Utente.id)
        .where(AuditLog.azione == "login_ok", ~Utente.ruoli.any(Ruolo.nome == "admin")).limit(1))
    passi = [
        {"titolo": "Crea gli account dei dipendenti", "testo": "Ognuno con i suoi ruoli: dipendente, magazziniere o entrambi.",
         "link": url_for("utenti.nuovo"),
         "fatto": conta(db.select(func.count(Utente.id)).where(Utente.eliminato.is_(False))) > 1},
        {"titolo": "Aggiungi i fornitori", "testo": "Serviranno per sapere a chi riordinare.",
         "link": url_for("anagrafica.fornitori"), "fatto": conta(db.select(func.count(Fornitore.id))) > 0},
        {"titolo": "Carica la prima merce", "testo": "Con il lettore o la fotocamera: lotti e scadenze partono da qui.",
         "link": url_for("carico.pagina"), "fatto": conta(db.select(func.count(Lotto.id))) > 0},
        {"titolo": "Collega i telefoni", "testo": "Certificato e primo accesso dei dipendenti.",
         "link": url_for("collega.pagina"), "fatto": telefoni is not None},
        {"titolo": "Attiva i backup notturni", "testo": "Sul server: ./racoonix.sh backup-automatico",
         "azione": "backup", "fatto": _impostazione("backup_confermato") == "1"},
    ]
    fatti = sum(1 for p in passi if p["fatto"])
    if fatti == len(passi):
        return None
    return {"passi": passi, "fatti": fatti, "totale": len(passi)}


@bp.post("/guida/<azione>")
@richiede_ruolo("admin")
def guida(azione):
    from flask import abort, g, redirect
    from .auth import registra
    if azione == "mostra":
        voce = db.session.get(Impostazione, "guida_nascosta")
        if voce:
            db.session.delete(voce)
        registra("guida_mostra", g.utente.id)
        db.session.commit()
        return redirect(url_for(".pagina"))
    chiavi = {"nascondi": "guida_nascosta", "backup": "backup_confermato"}
    if azione not in chiavi:
        abort(404)
    _imposta(chiavi[azione], "1")
    registra(f"guida_{azione}", g.utente.id)
    db.session.commit()
    return redirect(url_for(".pagina"))
