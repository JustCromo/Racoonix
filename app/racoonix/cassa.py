import hashlib
import re
import secrets
import time
from collections import defaultdict
from datetime import date

from flask import (Blueprint, abort, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from . import codici, db
from .auth import registra, richiede_ruolo
from .catalogo import trova_per_gtin
from .models import Lotto, Prodotto, RigaVendita, Sconto, Vendita
from .notifiche import controlla_scaffali

bp = Blueprint("cassa", __name__, url_prefix="/cassa")
CHIAVE = "carrello"
MAX_RIGHE = 30
DOPPIA_LETTURA_S = 2
RIGA_OK = re.compile(r"^[0-9a-f]{8}$")


class NonDisponibile(Exception):
    pass


def _carrello():
    return [dict(r) for r in session.get(CHIAVE, [])]


def _vendibile(lotto, oggi):
    return lotto.qta_esposta > 0 and (lotto.data_scadenza is None or lotto.data_scadenza > oggi)


def _importo(prodotto, quantita, perc):
    if prodotto.unita == "kg":
        lordo = (prodotto.prezzo_centesimi * quantita + 500) // 1000
    else:
        lordo = prodotto.prezzo_centesimi * quantita
    return (lordo * (100 - perc) + 50) // 100


def _sconti_attivi(lotto_ids, per_aggiornare=False):
    if not lotto_ids:
        return {}
    stmt = db.select(Sconto).where(Sconto.lotto_id.in_(list(lotto_ids)), Sconto.attivo.is_(True))
    if per_aggiornare:
        stmt = stmt.with_for_update()
    return {s.lotto_id: s for s in db.session.scalars(stmt)}


def _in_sconto(prodotto, oggi):
    """Lotti vendibili con pezzi scontati ancora disponibili, dal piu' vicino alla scadenza."""
    vendibili = [l for l in prodotto.lotti if _vendibile(l, oggi)]
    sconti = _sconti_attivi([l.id for l in vendibili])
    coppie = [(l, sconti[l.id]) for l in vendibili if l.id in sconti and sconti[l.id].residuo > 0]
    return sorted(coppie, key=lambda c: (c[0].data_scadenza is None, c[0].data_scadenza or oggi))


def _anteprima_perc(riga, prodotto, oggi):
    if riga["l"]:
        sconto = _sconti_attivi([riga["l"]]).get(riga["l"])
        return sconto.perc if sconto and sconto.residuo > 0 else 0
    if riga["s"]:
        coppie = _in_sconto(prodotto, oggi)
        return coppie[0][1].perc if coppie else 0
    return 0


def _disponibile(prodotto, righe, oggi):
    mie = [r for r in righe if r["p"] == prodotto.id]
    if sum(r["q"] for r in mie) > sum(l.qta_esposta for l in prodotto.lotti if _vendibile(l, oggi)):
        return False
    for lotto_id in {r["l"] for r in mie if r["l"]}:
        lotto = db.session.get(Lotto, lotto_id)
        if sum(r["q"] for r in mie if r["l"] == lotto_id) > lotto.qta_esposta:
            return False
    return True


def _dati(messaggio=None, esito="ok", scontrino=None):
    oggi = date.today()
    righe, totale = [], 0
    for r in _carrello():
        prodotto = db.session.get(Prodotto, r["p"])
        if prodotto is None or prodotto.prezzo_centesimi is None:
            continue
        perc = _anteprima_perc(r, prodotto, oggi)
        importo = _importo(prodotto, r["q"], perc)
        totale += importo
        righe.append({"id": r["i"], "p": prodotto, "q": r["q"], "perc": perc, "importo": importo,
                      "sconto_richiesto": bool(r["s"]), "lotto_fisso": bool(r["l"]),
                      "sconto_possibile": bool(r["s"]) or bool(_in_sconto(prodotto, oggi))})
    return {"righe": righe, "totale": totale, "messaggio": messaggio,
            "esito": esito, "scontrino": scontrino}


def _vista(messaggio=None, esito="ok", scontrino=None):
    if request.headers.get("HX-Request") == "true":
        return render_template("_carrello.html", **_dati(messaggio, esito, scontrino))
    if messaggio:
        flash(messaggio, esito)
    return redirect(url_for(".pagina"))


@bp.get("/")
@richiede_ruolo("dipendente")
def pagina():
    return render_template("cassa.html", **_dati())


@bp.post("/leggi")
@richiede_ruolo("dipendente")
def leggi():
    grezzo = (request.form.get("codice") or "").strip()[:250]
    impronta = hashlib.sha256(grezzo.encode()).hexdigest()[:16]
    ultima = session.get("ultima_lettura") or {}
    adesso = time.time()
    if ultima.get("c") == impronta and adesso - ultima.get("t", 0) < DOPPIA_LETTURA_S:
        return _vista()
    session["ultima_lettura"] = {"c": impronta, "t": adesso}

    try:
        info = codici.riconosci(grezzo, current_app.config["BILANCIA_PREFISSI"])
    except codici.CodiceNonValido as errore:
        current_app.logger.info("cassa: codice rifiutato (%s)", errore)
        return _vista("Codice non riconosciuto", "errore")

    righe = _carrello()
    if len(righe) >= MAX_RIGHE:
        return _vista("Carrello pieno", "errore")
    if info["tipo"] == "bilancia":
        prodotto = db.session.scalar(db.select(Prodotto).filter_by(codice_bilancia=info["codice_bilancia"]))
    else:
        prodotto = trova_per_gtin(info["gtin"])
    if prodotto is None or prodotto.stato != "attivo" or prodotto.prezzo_centesimi is None:
        return _vista("Prodotto non vendibile", "errore")

    oggi = date.today()
    lotto_id = None
    if info.get("lotto"):
        lotto = db.session.scalar(db.select(Lotto).filter_by(prodotto_id=prodotto.id, codice_lotto=info["lotto"]))
        if lotto is None or not _vendibile(lotto, oggi):
            return _vista("Lotto non disponibile o scaduto", "errore")
        lotto_id = lotto.id

    if info.get("peso_g"):
        if prodotto.unita != "kg":
            return _vista("Prodotto non vendibile", "errore")
        if info["tipo"] == "bilancia":
            etichetta = db.session.scalar(db.select(Lotto).filter_by(prodotto_id=prodotto.id, codice_etichetta=grezzo).where(Lotto.qta_esposta >= info["peso_g"]).order_by(Lotto.data_confezionamento.desc()).limit(1))
            if etichetta:
                lotto_id = etichetta.id
        righe.append({"i": secrets.token_hex(4), "p": prodotto.id, "l": lotto_id, "q": info["peso_g"], "s": 0})
    else:
        if prodotto.unita == "kg":
            return _vista("Prodotto a peso: usa l'etichetta della bilancia", "errore")
        uguale = next((r for r in righe if r["p"] == prodotto.id and r["l"] == lotto_id and not r["s"]), None)
        if uguale:
            uguale["q"] += 1
        else:
            righe.append({"i": secrets.token_hex(4), "p": prodotto.id, "l": lotto_id, "q": 1, "s": 0})

    if not _disponibile(prodotto, righe, oggi):
        return _vista(f"Sullo scaffale non c'e' abbastanza {prodotto.descrizione}", "errore")
    session[CHIAVE] = righe
    return _vista()


@bp.post("/riga/<rid>/<azione>")
@richiede_ruolo("dipendente")
def riga(rid, azione):
    if not RIGA_OK.match(rid) or azione not in ("piu", "meno", "rimuovi", "sconto"):
        abort(404)
    righe = _carrello()
    r = next((x for x in righe if x["i"] == rid), None)
    if r is None:
        return _vista("Riga non trovata", "errore")
    prodotto = db.session.get(Prodotto, r["p"])
    oggi = date.today()

    if azione == "rimuovi":
        righe.remove(r)
    elif azione in ("piu", "meno"):
        if prodotto.unita != "pezzo":
            return _vista("Per i prodotti a peso leggi un'altra etichetta", "errore")
        r["q"] += 1 if azione == "piu" else -1
        if r["q"] <= 0:
            righe.remove(r)
    else:
        if r["l"]:
            return _vista("Per questo lotto lo sconto e' gia' gestito dal codice", "errore")
        if not r["s"] and not _in_sconto(prodotto, oggi):
            return _vista(f"Nessuno sconto attivo su {prodotto.descrizione}", "errore")
        r["s"] = 0 if r["s"] else 1

    if prodotto and not _disponibile(prodotto, righe, oggi):
        return _vista(f"Sullo scaffale non c'e' abbastanza {prodotto.descrizione}", "errore")
    session[CHIAVE] = righe
    return _vista()


@bp.post("/annulla")
@richiede_ruolo("dipendente")
def annulla():
    session.pop(CHIAVE, None)
    return _vista("Carrello svuotato: nessun prodotto e' stato toccato", "ok")


@bp.post("/finalizza")
@richiede_ruolo("dipendente")
def finalizza():
    righe = _carrello()
    if not righe:
        return _vista("Carrello vuoto", "errore")
    oggi = date.today()
    prodotto_ids = {r["p"] for r in righe}
    prodotti = {p.id: p for p in db.session.scalars(db.select(Prodotto).where(Prodotto.id.in_(prodotto_ids)))}
    lotti = defaultdict(list)
    for lotto in db.session.scalars(db.select(Lotto).where(Lotto.prodotto_id.in_(prodotto_ids))
                                    .order_by(Lotto.id).with_for_update()):
        lotti[lotto.prodotto_id].append(lotto)
    sconti = _sconti_attivi([l.id for gruppo in lotti.values() for l in gruppo], per_aggiornare=True)

    def scontabile(lotto):
        return lotto.id in sconti and sconti[lotto.id].residuo > 0

    vendita = Vendita(utente_id=g.utente.id, totale_centesimi=0)
    db.session.add(vendita)
    totale, scontrino = 0, []
    ordine = sorted(righe, key=lambda r: 0 if r["l"] else (1 if r["s"] else 2))
    try:
        for r in ordine:
            p = prodotti.get(r["p"])
            if p is None or p.stato != "attivo" or p.prezzo_centesimi is None:
                raise NonDisponibile("un prodotto")
            vendibili = [l for l in lotti[p.id] if _vendibile(l, oggi)]
            restante, parti = r["q"], []

            if r["l"]:
                lotto = next((l for l in vendibili if l.id == r["l"]), None)
                if lotto is None or lotto.qta_esposta < restante:
                    raise NonDisponibile(p.descrizione)
                scontati = min(restante, sconti[lotto.id].residuo) if scontabile(lotto) else 0
                if scontati:
                    parti.append((lotto, scontati, sconti[lotto.id].perc))
                    sconti[lotto.id].venduti += scontati
                parti.append((lotto, restante - scontati, 0))
                restante = 0
            elif r["s"]:
                for lotto in sorted(filter(scontabile, vendibili),
                                    key=lambda l: (l.data_scadenza is None, l.data_scadenza or oggi)):
                    parte = min(restante, lotto.qta_esposta, sconti[lotto.id].residuo)
                    if parte > 0:
                        parti.append((lotto, parte, sconti[lotto.id].perc))
                        sconti[lotto.id].venduti += parte
                        restante -= parte
                    if restante == 0:
                        break
            else:
                for lotto in sorted(vendibili, key=lambda l: (scontabile(l), l.data_scadenza is None,
                                                              l.data_scadenza or oggi, l.data_carico)):
                    parte = min(restante, lotto.qta_esposta)
                    if parte > 0:
                        parti.append((lotto, parte, 0))
                        restante -= parte
                    if restante == 0:
                        break
            if restante > 0:
                raise NonDisponibile(p.descrizione)

            for lotto, parte, perc in parti:
                if parte <= 0:
                    continue
                importo = _importo(p, parte, perc)
                lotto.qta_esposta -= parte
                db.session.add(RigaVendita(vendita=vendita, lotto_id=lotto.id, quantita=parte,
                                           prezzo_unitario_centesimi=p.prezzo_centesimi,
                                           sconto_perc=perc, totale_centesimi=importo, aliquota_iva=p.aliquota_iva))
                totale += importo
                scontrino.append({"nome": p.descrizione, "unita": p.unita, "q": parte,
                                  "perc": perc, "importo": importo})
    except NonDisponibile as errore:
        db.session.rollback()
        return _vista(f"Disponibilita' cambiata: {errore} non basta. Nessuna modifica eseguita", "errore")

    vendita.totale_centesimi = totale
    registra("vendita", g.utente.id, f"{len(righe)} righe, totale {totale}")
    db.session.commit()
    controlla_scaffali(prodotto_ids)
    session.pop(CHIAVE, None)
    return _vista(f"Vendita n. {vendita.id} completata", "ok",
                  scontrino={"id": vendita.id, "totale": totale, "righe": scontrino})
