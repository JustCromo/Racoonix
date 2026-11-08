"""Logica per le apparecchiature collegate: la cassa vende, la bilancia registra vaschette.
Prezzi, sconti, lotti e FEFO li decide sempre Racoonix."""
import secrets
from collections import defaultdict
from datetime import date, timedelta

from flask import current_app
from sqlalchemy import or_

from . import codici, db
from .catalogo import trova_per_gtin
from .formato import data_it
from .models import Lotto, Prodotto, RigaVendita, Sconto, Vendita

VALIDITA_MAX = 60


class NonDisponibile(Exception):
    """La merce non basta (magari venduta nel frattempo da un'altra cassa)."""


class Rifiutato(Exception):
    """Richiesta non accettabile: il messaggio e' sicuro da mostrare."""


def vendibile(lotto, oggi):
    return lotto.qta_esposta > 0 and (lotto.data_scadenza is None or lotto.data_scadenza > oggi)


def importo(prodotto, quantita, perc):
    if prodotto.unita == "kg":
        lordo = (prodotto.prezzo_centesimi * quantita + 500) // 1000
    else:
        lordo = prodotto.prezzo_centesimi * quantita
    return (lordo * (100 - perc) + 50) // 100


def sconti_attivi(lotto_ids, per_aggiornare=False):
    if not lotto_ids:
        return {}
    stmt = db.select(Sconto).where(Sconto.lotto_id.in_(list(lotto_ids)), Sconto.attivo.is_(True))
    if per_aggiornare:
        stmt = stmt.with_for_update()
    return {s.lotto_id: s for s in db.session.scalars(stmt)}


# ---------- Cassa ----------

def interpreta(grezzo):
    """Codice letto in cassa -> (prodotto, lotto fisso o None, quantita' base)."""
    info = codici.riconosci(grezzo, current_app.config["BILANCIA_PREFISSI"])
    if info["tipo"] == "bilancia":
        prodotto = db.session.scalar(db.select(Prodotto).filter_by(codice_bilancia=info["codice_bilancia"]))
    else:
        prodotto = trova_per_gtin(info["gtin"])
    if prodotto is None or prodotto.stato != "attivo" or prodotto.prezzo_centesimi is None:
        raise Rifiutato("Prodotto non vendibile")
    oggi = date.today()
    lotto_id = None
    if info.get("lotto"):
        lotto = db.session.scalar(db.select(Lotto).filter_by(prodotto_id=prodotto.id, codice_lotto=info["lotto"]))
        if lotto is None or not vendibile(lotto, oggi):
            raise Rifiutato("Lotto non disponibile o scaduto")
        lotto_id = lotto.id
    if info.get("peso_g"):
        if prodotto.unita != "kg":
            raise Rifiutato("Prodotto non vendibile")
        if info["tipo"] == "bilancia":
            etichetta = db.session.scalar(
                db.select(Lotto).filter_by(prodotto_id=prodotto.id, codice_etichetta=grezzo.strip())
                .where(Lotto.qta_esposta >= info["peso_g"])
                .order_by(Lotto.data_confezionamento.desc()).limit(1))
            if etichetta:
                lotto_id = etichetta.id
        return prodotto, lotto_id, info["peso_g"]
    if prodotto.unita == "kg":
        raise Rifiutato("Prodotto a peso: serve l'etichetta della bilancia")
    return prodotto, lotto_id, 1


def descrivi(grezzo):
    """Risposta alla cassa: cos'e', quanto costa, che sconti valgono."""
    prodotto, lotto_id, quantita = interpreta(grezzo)
    oggi = date.today()
    perc_automatico = 0
    if lotto_id:
        sconto = sconti_attivi([lotto_id]).get(lotto_id)
        perc_automatico = sconto.perc if sconto and sconto.residuo > 0 else 0
    perc_scadenza = 0
    if lotto_id is None:
        vendibili = [l for l in prodotto.lotti if vendibile(l, oggi)]
        sconti = sconti_attivi([l.id for l in vendibili])
        perc_scadenza = max((s.perc for s in sconti.values() if s.residuo > 0), default=0)
    misura = prodotto.prezzo_misura
    return {
        "descrizione": prodotto.descrizione, "unita": prodotto.unita,
        "prezzo_centesimi": prodotto.prezzo_centesimi,
        "prezzo_misura": {"centesimi": misura[0], "unita": misura[1]} if misura else None,
        "quantita": quantita, "lotto_fisso": lotto_id is not None,
        "sconto_automatico_perc": perc_automatico, "sconto_scadenza_perc": perc_scadenza,
        "importo_centesimi": importo(prodotto, quantita, perc_automatico),
    }


def registra_vendita(righe, utente_id=None, dispositivo_id=None):
    """righe: [{"p": prodotto_id, "l": lotto_id|None, "q": quantita, "s": sconto scadenza}].
    Non fa commit: chi chiama decide, cosi' vendita e memoria della richiesta stanno nella stessa transazione."""
    oggi = date.today()
    prodotto_ids = {r["p"] for r in righe}
    prodotti = {p.id: p for p in db.session.scalars(db.select(Prodotto).where(Prodotto.id.in_(prodotto_ids)))}
    lotti = defaultdict(list)
    for lotto in db.session.scalars(db.select(Lotto).where(Lotto.prodotto_id.in_(prodotto_ids))
                                    .order_by(Lotto.id).with_for_update()):
        lotti[lotto.prodotto_id].append(lotto)
    sconti = sconti_attivi([l.id for gruppo in lotti.values() for l in gruppo], per_aggiornare=True)

    def scontabile(lotto):
        return lotto.id in sconti and sconti[lotto.id].residuo > 0

    vendita = Vendita(utente_id=utente_id, dispositivo_id=dispositivo_id, totale_centesimi=0)
    db.session.add(vendita)
    totale, scontrino = 0, []
    for r in sorted(righe, key=lambda r: 0 if r["l"] else (1 if r["s"] else 2)):
        p = prodotti.get(r["p"])
        if p is None or p.stato != "attivo" or p.prezzo_centesimi is None:
            raise NonDisponibile("un prodotto")
        vendibili = [l for l in lotti[p.id] if vendibile(l, oggi)]
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
            valore = importo(p, parte, perc)
            lotto.qta_esposta -= parte
            db.session.add(RigaVendita(vendita=vendita, lotto_id=lotto.id, quantita=parte,
                                       prezzo_unitario_centesimi=p.prezzo_centesimi, sconto_perc=perc,
                                       totale_centesimi=valore, aliquota_iva=p.aliquota_iva))
            totale += valore
            scontrino.append({"descrizione": p.descrizione, "unita": p.unita, "quantita": parte,
                              "sconto_perc": perc, "importo_centesimi": valore})
    vendita.totale_centesimi = totale
    db.session.flush()
    return vendita, scontrino


# ---------- Bilancia del banco ----------

def _prodotto_banco(grezzo):
    info = codici.riconosci(grezzo, current_app.config["BILANCIA_PREFISSI"])
    if info["tipo"] == "bilancia":
        prodotto = db.session.scalar(db.select(Prodotto).filter_by(codice_bilancia=info["codice_bilancia"]))
    elif info.get("peso_g") and info.get("gtin"):
        prodotto = trova_per_gtin(info["gtin"])
    else:
        raise Rifiutato("Serve l'etichetta stampata dalla bilancia")
    if prodotto is None or prodotto.stato != "attivo" or prodotto.unita != "kg":
        raise Rifiutato("Etichetta non collegata a un prodotto a peso del catalogo")
    if not prodotto.giorni_validita:
        raise Rifiutato("Prodotto non gestito al banco")
    return prodotto, info


def _origini(prodotto, oggi, per_aggiornare=False):
    stmt = (db.select(Lotto)
            .where(Lotto.prodotto_id == prodotto.id, Lotto.lotto_origine_id.is_(None),
                   (Lotto.qta_esposta + Lotto.qta_magazzino) > 0,
                   or_(Lotto.data_scadenza.is_(None), Lotto.data_scadenza > oggi))
            .order_by(Lotto.data_scadenza.asc().nulls_last(), Lotto.data_carico))
    if per_aggiornare:
        stmt = stmt.with_for_update()
    return db.session.scalars(stmt).all()


def descrivi_etichetta(grezzo):
    prodotto, info = _prodotto_banco(grezzo)
    oggi = date.today()
    origini = _origini(prodotto, oggi)
    limite = min((l.data_scadenza for l in origini if l.data_scadenza), default=None)
    proposta = info["scadenza"] or oggi + timedelta(days=prodotto.giorni_validita)
    if limite and proposta > limite:
        proposta = limite
    return {"descrizione": prodotto.descrizione, "peso_g": info["peso_g"],
            "disponibile_g": sum(l.qta_esposta + l.qta_magazzino for l in origini),
            "scadenza_proposta": proposta.isoformat(), "scadenza_fissa": bool(info["scadenza"]),
            "limite": limite.isoformat() if limite else None}


def registra_vaschetta(grezzo, scadenza_testo=None, utente_id=None):
    """Toglie i grammi dal pezzo intero (FEFO) e crea la vaschetta esposta. Non fa commit."""
    prodotto, info = _prodotto_banco(grezzo)
    peso, oggi = info["peso_g"], date.today()
    if info["scadenza"]:
        scadenza, esplicita = info["scadenza"], True
    elif scadenza_testo:
        try:
            scadenza, esplicita = date.fromisoformat(scadenza_testo), True
        except ValueError:
            raise Rifiutato("Data di scadenza non valida") from None
    else:
        scadenza, esplicita = oggi + timedelta(days=prodotto.giorni_validita), False

    origini = _origini(prodotto, oggi, per_aggiornare=True)
    if sum(l.qta_esposta + l.qta_magazzino for l in origini) < peso:
        raise Rifiutato(f"Al banco non c'e' abbastanza {prodotto.descrizione}")
    restante, usati = peso, []
    for lotto in origini:
        for campo in ("qta_esposta", "qta_magazzino"):
            prendi = min(restante, getattr(lotto, campo))
            if prendi > 0:
                setattr(lotto, campo, getattr(lotto, campo) - prendi)
                restante -= prendi
                if lotto not in usati:
                    usati.append(lotto)
        if restante == 0:
            break
    limite = min((l.data_scadenza for l in usati if l.data_scadenza), default=None)
    if limite and scadenza > limite:
        if esplicita:
            raise Rifiutato(f"La vaschetta non puo' scadere dopo il prodotto da cui e' tagliata ({data_it(limite)})")
        scadenza = limite
    if not oggi < scadenza <= oggi + timedelta(days=VALIDITA_MAX):
        raise Rifiutato("Data di scadenza non valida")

    etichetta = grezzo.strip() if info["tipo"] == "bilancia" else None
    confezionamento = info["confezionamento"] or oggi
    codice_lotto = info.get("lotto") or f"BAN{oggi:%y%m%d}{secrets.token_hex(2).upper()}"
    filtro = {"prodotto_id": prodotto.id, "data_scadenza": scadenza, "data_confezionamento": confezionamento}
    if etichetta:
        filtro["codice_etichetta"] = etichetta
    else:
        filtro["codice_lotto"] = codice_lotto
    vaschetta = db.session.scalar(db.select(Lotto).filter_by(**filtro).where(Lotto.lotto_origine_id.is_not(None)))
    if vaschetta is None:
        vaschetta = Lotto(prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza,
                          data_confezionamento=confezionamento, lotto_origine_id=usati[0].id,
                          codice_etichetta=etichetta, qta_esposta=0, qta_magazzino=0, caricato_da=utente_id)
        db.session.add(vaschetta)
    vaschetta.qta_esposta += peso
    db.session.flush()
    return {"prodotto_id": prodotto.id, "descrizione": prodotto.descrizione,
            "lotto": vaschetta.codice_lotto, "peso_g": peso, "scadenza": scadenza.isoformat()}
