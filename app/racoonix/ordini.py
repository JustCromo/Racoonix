"""Ordini ai fornitori: la lista nasce dalle segnalazioni 'Sta finendo' e dalle soglie di magazzino."""
from datetime import datetime, timezone

from flask import Blueprint, abort, current_app, flash, g, redirect, render_template, request, url_for
from sqlalchemy.orm import selectinload

from . import db
from .auth import registra, richiede_ruolo
from .carico import _quantita as leggi_quantita
from .formato import quantita as mostra_quantita
from .models import Prodotto, Riordino
from .riordini import APERTI

bp = Blueprint("ordini", __name__, url_prefix="/admin/ordini")


def _ean(gtin):
    return gtin[1:] if gtin and gtin.startswith("0") else gtin


def _testo_ordine(gruppo):
    f = gruppo["fornitore"]
    righe = [f"Buongiorno{', ' + f.ragione_sociale if f else ''}, ecco il nostro ordine:"]
    for r in gruppo["da_ordinare"]:
        p = r.prodotto
        q = mostra_quantita(r.quantita, p.unita) if r.quantita else "quantita' da definire"
        codice = f" (EAN {_ean(p.gtin)})" if p.gtin else ""
        righe.append(f"- {p.descrizione}{codice}: {q}")
    righe.append(f"Grazie, {current_app.config['MARKET_NAME']}")
    return "\n".join(righe)


def _gruppi():
    voci = db.session.scalars(
        db.select(Riordino).where(Riordino.stato.in_(APERTI)).order_by(Riordino.creato_il)
        .options(selectinload(Riordino.prodotto).selectinload(Prodotto.fornitore),
                 selectinload(Riordino.prodotto).selectinload(Prodotto.lotti),
                 selectinload(Riordino.segnalato_da_utente))).all()
    gruppi = {}
    for r in voci:
        f = r.prodotto.fornitore
        gruppo = gruppi.setdefault(f.id if f else 0, {"id": f.id if f else 0, "fornitore": f,
                                                      "da_ordinare": [], "ordinati": []})
        gruppo["da_ordinare" if r.stato == "da_ordinare" else "ordinati"].append(r)
    elenco = sorted(gruppi.values(), key=lambda x: (x["fornitore"] is None,
                                                    x["fornitore"].ragione_sociale if x["fornitore"] else ""))
    for gruppo in elenco:
        gruppo["testo"] = _testo_ordine(gruppo)
    return elenco


@bp.get("/")
@richiede_ruolo("admin")
def pagina():
    return render_template("ordini.html", gruppi=_gruppi())


@bp.post("/fornitore/<int:fid>")
@richiede_ruolo("admin")
def fornitore(fid):
    azione = request.form.get("azione")
    if azione not in ("salva", "ordina"):
        abort(404)
    stmt = (db.select(Riordino).join(Prodotto, Riordino.prodotto_id == Prodotto.id)
            .where(Riordino.stato == "da_ordinare").with_for_update(of=Riordino))
    stmt = stmt.where(Prodotto.fornitore_id.is_(None)) if fid == 0 else stmt.where(Prodotto.fornitore_id == fid)
    righe = db.session.scalars(stmt).all()
    errori = []
    for r in righe:
        testo = (request.form.get(f"q_{r.id}") or "").strip()
        quantita = leggi_quantita(testo, r.prodotto.unita) if testo else None
        if (testo and not quantita) or (azione == "ordina" and not quantita):
            errori.append(r.prodotto.descrizione)
        r.quantita = quantita
    torna = redirect(url_for(".pagina", _anchor=f"fornitore-{fid}"))
    if errori:
        db.session.rollback()
        flash("Quantita' mancante o non valida: " + ", ".join(errori[:3]), "errore")
        return torna
    if azione == "ordina" and righe:
        adesso = datetime.now(timezone.utc)
        for r in righe:
            r.stato, r.ordinato_da, r.ordinato_il = "ordinato", g.utente.id, adesso
        registra("riordino_ordinato", g.utente.id, f"fornitore {fid}, {len(righe)} prodotti")
        messaggio = f"Segnati come ordinati: {len(righe)}. Usciranno dalla lista all'arrivo della merce"
    else:
        messaggio = "Quantita' salvate: il testo dell'ordine e' aggiornato"
    db.session.commit()
    flash(messaggio, "ok")
    return torna


@bp.post("/<int:rid>/<azione>")
@richiede_ruolo("admin")
def riga(rid, azione):
    if azione not in ("togli", "esaurimento"):
        abort(404)
    r = db.get_or_404(Riordino, rid)
    fid = r.prodotto.fornitore_id or 0
    if r.stato in APERTI:
        r.stato, r.chiuso_il = "annullato", datetime.now(timezone.utc)
        if azione == "esaurimento":
            r.prodotto.in_esaurimento = True
        registra("riordino_annullato" if azione == "togli" else "prodotto_esaurimento",
                 g.utente.id, f"prodotto {r.prodotto_id}")
        db.session.commit()
        flash("Tolto dalla lista" if azione == "togli" else "Prodotto in esaurimento: non verra' piu' riordinato", "ok")
    return redirect(url_for(".pagina", _anchor=f"fornitore-{fid}"))
