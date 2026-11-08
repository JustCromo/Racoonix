"""Dashboard admin: tutti i numeri sono calcolati dal server, il browser riceve solo la pagina."""
from collections import defaultdict
from datetime import date, datetime, time, timedelta

from flask import Blueprint, render_template, request
from sqlalchemy import func

from . import db
from .auth import richiede_ruolo
from .models import Lotto, Notifica, Prodotto, RigaVendita, Scarto, Vendita

bp = Blueprint("dashboard", __name__, url_prefix="/admin/dashboard")
PERIODI = {1: "Oggi", 7: "Ultimi 7 giorni", 30: "Ultimi 30 giorni"}
MOTIVI = {"scaduto": "Scaduti", "deteriorato": "Deteriorati", "non_conforme": "Non conformi"}
LARGHEZZA, ALTEZZA = 600, 130


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
    barre = [{"etichetta": e, "titolo": tt, "valore": v,
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

    return render_template(
        "dashboard.html", giorni=giorni, titolo_grafico=titolo_grafico, saluto=_saluto(), periodi=PERIODI, primo=primo, oggi=oggi,
        incasso=incasso, scontrini=scontrini, medio=incasso // scontrini if scontrini else 0,
        sconti=sconti, iva=iva, top=top, barre=barre, scarti=scarti.values(),
        valore_scarti=sum(s["valore"] for s in scarti.values()),
        aperte=aperte, valore_merce=valore_merce)


def _saluto():
    ora = datetime.now().hour
    return "Buongiorno" if ora < 13 else ("Buon pomeriggio" if ora < 18 else "Buonasera")
