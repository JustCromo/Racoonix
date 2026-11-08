"""Gestione dei dispositivi collegati: ogni cassa o bilancia ha la sua chiave, revocabile."""
import hashlib
import re
import secrets

from flask import Blueprint, flash, g, make_response, redirect, render_template, request, url_for

from . import db
from .auth import registra, richiede_ruolo
from .models import Dispositivo

bp = Blueprint("dispositivi", __name__, url_prefix="/admin/dispositivi")
NOME_OK = re.compile(r"^[\w .'()/-]{2,60}$")


@bp.get("/")
@richiede_ruolo("admin")
def elenco():
    dispositivi = db.session.scalars(db.select(Dispositivo).where(Dispositivo.archiviato.is_(False))
                                     .order_by(Dispositivo.creato_il.desc())).all()
    return render_template("dispositivi.html", dispositivi=dispositivi)


@bp.post("/nuovo")
@richiede_ruolo("admin")
def nuovo():
    nome = (request.form.get("nome") or "").strip()
    tipo = request.form.get("tipo")
    if not NOME_OK.match(nome) or tipo not in ("cassa", "bilancia"):
        flash("Nome o tipo non validi", "errore")
        return redirect(url_for(".elenco"))
    if db.session.scalar(db.select(Dispositivo.id).filter_by(nome=nome)):
        flash("Esiste gia' un dispositivo con questo nome", "errore")
        return redirect(url_for(".elenco"))
    token = "rcx_" + secrets.token_urlsafe(32)
    dispositivo = Dispositivo(nome=nome, tipo=tipo, token_hash=hashlib.sha256(token.encode()).hexdigest(),
                              prefisso=token[:10], creato_da=g.utente.id)
    db.session.add(dispositivo)
    registra("dispositivo_creato", g.utente.id, f"{nome} ({tipo})")
    db.session.commit()
    risposta = make_response(render_template("dispositivo_token.html", d=dispositivo, token=token))
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


@bp.post("/<int:did>/revoca")
@richiede_ruolo("admin")
def revoca(did):
    dispositivo = db.get_or_404(Dispositivo, did)
    dispositivo.attivo = False
    registra("dispositivo_revocato", g.utente.id, dispositivo.nome)
    db.session.commit()
    flash(f"Chiave di {dispositivo.nome} revocata definitivamente", "ok")
    return redirect(url_for(".elenco"))


@bp.post("/<int:did>/rimuovi")
@richiede_ruolo("admin")
def rimuovi(did):
    """Mai usato: si elimina. Usato: si archivia, perche' le sue vendite devono restare nello storico."""
    from .models import RichiestaApi, Vendita
    dispositivo = db.get_or_404(Dispositivo, did)
    if dispositivo.attivo:
        flash("Prima revoca la chiave", "errore")
        return redirect(url_for(".elenco"))
    usato = (db.session.scalar(db.select(Vendita.id).filter_by(dispositivo_id=dispositivo.id).limit(1))
             or db.session.scalar(db.select(RichiestaApi.id).filter_by(dispositivo_id=dispositivo.id).limit(1)))
    if usato:
        dispositivo.archiviato = True
        registra("dispositivo_archiviato", g.utente.id, dispositivo.nome)
        messaggio = f"{dispositivo.nome} archiviato: lo storico delle sue operazioni resta"
    else:
        registra("dispositivo_eliminato", g.utente.id, dispositivo.nome)
        db.session.delete(dispositivo)
        messaggio = f"{dispositivo.nome} eliminato"
    db.session.commit()
    flash(messaggio, "ok")
    return redirect(url_for(".elenco"))


@bp.get("/<int:did>")
@richiede_ruolo("admin")
def dettaglio(did):
    """Riepilogo degli ultimi 30 giorni di una singola cassa o bilancia."""
    import json
    from datetime import date, datetime, time, timedelta

    from sqlalchemy import func

    from .models import Lotto, Prodotto, RichiestaApi, RigaVendita, Vendita
    dispositivo = db.get_or_404(Dispositivo, did)
    inizio = datetime.combine(date.today() - timedelta(days=29), time.min).astimezone()
    if dispositivo.tipo == "cassa":
        vendite = db.session.scalars(db.select(Vendita).filter_by(dispositivo_id=dispositivo.id)
                                     .order_by(Vendita.data_ora.desc())).all()
        nel_periodo = [v for v in vendite if v.data_ora >= inizio]
        incasso = sum(v.totale_centesimi for v in nel_periodo)
        top = db.session.execute(
            db.select(Prodotto, func.sum(RigaVendita.totale_centesimi), func.sum(RigaVendita.quantita))
            .join(Lotto, Lotto.prodotto_id == Prodotto.id)
            .join(RigaVendita, RigaVendita.lotto_id == Lotto.id)
            .join(Vendita, RigaVendita.vendita_id == Vendita.id)
            .where(Vendita.dispositivo_id == dispositivo.id, Vendita.data_ora >= inizio)
            .group_by(Prodotto.id).order_by(func.sum(RigaVendita.totale_centesimi).desc()).limit(5)).all()
        dati = {"scontrini": len(nel_periodo), "incasso": incasso,
                "medio": incasso // len(nel_periodo) if nel_periodo else 0,
                "ultime": vendite[:10], "top": top}
    else:
        vaschette = []
        for richiesta in db.session.scalars(db.select(RichiestaApi).filter_by(dispositivo_id=dispositivo.id)
                                            .order_by(RichiestaApi.creata_il.desc()).limit(200)):
            try:
                esito = json.loads(richiesta.risposta)
            except ValueError:
                continue
            if isinstance(esito, dict) and "peso_g" in esito:
                vaschette.append(dict(esito, quando=richiesta.creata_il))
        nel_periodo = [v for v in vaschette if v["quando"] >= inizio]
        dati = {"numero": len(nel_periodo), "grammi": sum(v["peso_g"] for v in nel_periodo),
                "ultime": vaschette[:10]}
    return render_template("dispositivo.html", d=dispositivo, dati=dati)
