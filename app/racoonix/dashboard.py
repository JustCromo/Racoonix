"""Dashboard admin: tutti i numeri sono calcolati dal server, il browser riceve solo la pagina."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request, url_for
from sqlalchemy import func

from . import db
from .auth import richiede_ruolo
from .formato import euro
from .models import AuditLog, Dispositivo, Fornitore, Impostazione, Ruolo, Lotto, Notifica, Prodotto, RigaVendita, Riordino, Scarto, Sconto, Utente, Vendita

bp = Blueprint("dashboard", __name__, url_prefix="/admin/dashboard")
PERIODI = {1: "Oggi", 7: "Ultimi 7 giorni", 30: "Ultimi 30 giorni"}
MOTIVI = {"scaduto": "Scaduti", "deteriorato": "Deteriorati", "non_conforme": "Non conformi"}
LARGHEZZA, ALTEZZA = 600, 130
ETICHETTE_ATTIVITA = {"carico": "Carico merce", "rettifica": "Correzione quantita'",
                      "notifica_verifica": "Verifica scadenza", "notifica_rimosso": "Rimozione scaduti",
                      "notifica_deteriorato": "Scarto per freschezza", "rifornimento": "Scaffale rifornito",
                      "prodotto_approvato": "Prodotto approvato", "sconto_manuale": "Sconto applicato", "segnalazione_mancanza": "Segnalato: sta finendo"}


def _valore(prodotto, quantita, prezzo=None):
    """Valore a prezzo di vendita: pezzi x prezzo, oppure grammi x prezzo al kg."""
    prezzo = prodotto.prezzo_centesimi if prezzo is None else prezzo
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

    righe = db.session.execute(
        db.select(RigaVendita, Prodotto, Vendita.data_ora)
        .join(Vendita, RigaVendita.vendita_id == Vendita.id)
        .join(Lotto, RigaVendita.lotto_id == Lotto.id)
        .join(Prodotto, Lotto.prodotto_id == Prodotto.id)
        .where(Vendita.data_ora >= inizio)).all()
    scontrini = db.session.scalar(db.select(func.count(Vendita.id)).where(Vendita.data_ora >= inizio))

    incasso = sconti = 0
    per_iva, per_giorno, per_prodotto = defaultdict(int), defaultdict(int), {}
    for riga, prodotto, quando in righe:
        incasso += riga.totale_centesimi
        per_iva[riga.aliquota_iva] += riga.totale_centesimi
        per_giorno[quando.astimezone().date()] += riga.totale_centesimi
        if riga.sconto_perc:
            sconti += _valore(prodotto, riga.quantita, riga.prezzo_unitario_centesimi) - riga.totale_centesimi
        voce = per_prodotto.setdefault(prodotto.id, {"p": prodotto, "incasso": 0, "quantita": 0})
        voce["incasso"] += riga.totale_centesimi
        voce["quantita"] += riga.quantita

    iva = []
    for aliquota in sorted(per_iva):
        totale = per_iva[aliquota]
        imposta = (totale * aliquota + (100 + aliquota) // 2) // (100 + aliquota)
        iva.append({"aliquota": aliquota, "totale": totale, "imponibile": totale - imposta, "imposta": imposta})
    top = sorted(per_prodotto.values(), key=lambda v: v["incasso"], reverse=True)[:5]

    if giorni == 1:
        per_ora = defaultdict(int)
        for riga, _, quando in righe:
            per_ora[quando.astimezone().hour] += riga.totale_centesimi
        ore = range(min([8] + list(per_ora)), max([20] + list(per_ora)) + 1)
        punti = [(f"{o:02d}", f"ore {o:02d}", per_ora[o]) for o in ore]
        titolo_grafico = "Incasso per ora"
    else:
        lista_giorni = [primo + timedelta(days=i) for i in range(giorni)]
        punti = [(d.strftime("%d/%m"), d.strftime("%d/%m/%Y"), per_giorno[d]) for d in lista_giorni]
        titolo_grafico = "Incasso per giorno"
    massimo = max([v for _, _, v in punti] + [1])
    passo = LARGHEZZA / len(punti)
    barre = [{"etichetta": e, "titolo": tt, "valore": v, "testo": euro(v),
              "x": round(i * passo + passo * 0.15, 1), "w": round(passo * 0.7, 1),
              "centro": round(i * passo + passo / 2, 1),
              "h": round(v / massimo * ALTEZZA, 1),
              "mostra": len(punti) <= 14 or i % 5 == 0 or i == len(punti) - 1}
             for i, (e, tt, v) in enumerate(punti)]

    scarti = {m: {"etichetta": e, "numero": 0, "valore": 0} for m, e in MOTIVI.items()}
    for scarto, prodotto in db.session.execute(
            db.select(Scarto, Prodotto).join(Lotto, Scarto.lotto_id == Lotto.id)
            .join(Prodotto, Lotto.prodotto_id == Prodotto.id).where(Scarto.data >= inizio)).all():
        scarti[scarto.motivo]["numero"] += 1
        scarti[scarto.motivo]["valore"] += _valore(prodotto, scarto.quantita)

    aperte = dict(db.session.execute(
        db.select(Notifica.tipo, func.count(Notifica.id))
        .where(Notifica.stato == "aperta").group_by(Notifica.tipo)).all())
    giacenze = db.session.execute(
        db.select(Lotto, Prodotto).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
        .where(Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0)).all()
    valore_merce = sum(_valore(p, l.qta_esposta + l.qta_magazzino) for l, p in giacenze)

    voci = [("da_rimuovere", "Da rimuovere", True), ("reset_password", "Richieste di nuova password", True),
            ("da_approvare", "Prodotti da approvare", True),
            ("riempi", "Scaffali da riempire", False), ("sconto", "Bollini da applicare", False),
            ("in_scadenza", "Lotti in scadenza", False), ("freschezza", "Freschezza da controllare", False)]
    attenzione = [{"etichetta": e, "numero": aperte[tipo], "urgente": u} for tipo, e, u in voci if aperte.get(tipo)]
    da_ordinare = db.session.scalar(db.select(func.count(Riordino.id)).where(Riordino.stato == "da_ordinare"))
    if da_ordinare:
        attenzione.insert(0, {"etichetta": "Da ordinare ai fornitori", "numero": da_ordinare, "urgente": True,
                              "link": url_for("ordini.pagina")})
    in_scadenza = db.session.execute(
        db.select(Lotto, Prodotto).join(Prodotto, Lotto.prodotto_id == Prodotto.id)
        .where(Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0,
               Lotto.data_scadenza >= oggi, Lotto.data_scadenza <= oggi + timedelta(days=3))
        .order_by(Lotto.data_scadenza).limit(6)).all()
    ultime = db.session.execute(
        db.select(Vendita, Dispositivo.nome, Utente.username)
        .outerjoin(Dispositivo, Vendita.dispositivo_id == Dispositivo.id)
        .outerjoin(Utente, Vendita.utente_id == Utente.id)
        .order_by(Vendita.data_ora.desc()).limit(6)).all()
    cassa_collegata = db.session.scalar(db.select(func.count(Dispositivo.id)).where(
        Dispositivo.tipo == "cassa", Dispositivo.attivo.is_(True))) > 0
    sconti_attivi = db.session.scalar(db.select(func.count(Sconto.id)).where(
        Sconto.attivo.is_(True), Sconto.venduti < Sconto.quantita))

    autonoma = {}
    if not cassa_collegata:
        vivi = (Prodotto.stato == "attivo", (Lotto.qta_esposta + Lotto.qta_magazzino) > 0)
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
        autonoma = {
            "barre_scadenze": barre_scadenze,
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
            "rettifiche": db.session.scalar(db.select(func.count(AuditLog.id)).where(
                AuditLog.azione == "rettifica", AuditLog.data_ora >= inizio)),
            "attivita": db.session.execute(
                db.select(AuditLog, Utente.username).outerjoin(Utente, AuditLog.utente_id == Utente.id)
                .where(AuditLog.azione.in_(list(ETICHETTE_ATTIVITA)))
                .order_by(AuditLog.data_ora.desc()).limit(8)).all(),
        }

    return render_template(
        "dashboard.html", giorni=giorni, titolo_grafico=titolo_grafico, saluto=_saluto(), periodi=PERIODI, primo=primo, oggi=oggi,
        incasso=incasso, scontrini=scontrini, medio=incasso // scontrini if scontrini else 0,
        sconti=sconti, iva=iva, top=top, barre=barre, scarti=scarti.values(),
        valore_scarti=sum(s["valore"] for s in scarti.values()),
        aperte=aperte, valore_merce=valore_merce, attenzione=attenzione,
        in_scadenza=in_scadenza, ultime=ultime, sconti_attivi=sconti_attivi,
        vendite_attive=cassa_collegata, autonoma=autonoma, etichette_attivita=ETICHETTE_ATTIVITA, guida=_guida(),
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
