import re
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, url_for)
from sqlalchemy import and_, or_
from sqlalchemy.orm import selectinload

from . import codici, db
from .auth import registra, richiede_ruolo
from .carico import _quantita as leggi_quantita
from .formato import data_it, quantita as mostra_quantita
from .models import Categoria, CodiceAggiuntivo, Lotto, Prodotto, adesso
from .prodotti import _chiudi_notifiche
from .notifiche import _apri, controlla_scaffali
from .riordini import apri_riordino, riordino_aperto
from .sconti import applica_programmati, crea_sconto, sconto_attivo, togli_sconto
from .lingua import _, force_locale, lingua_negozio

bp = Blueprint("inventario", __name__, url_prefix="/inventario")
ID_OK = re.compile(r"^[0-9]{1,9}$")


def _stato_lotto(lotto, prodotto, oggi):
    if lotto.data_scadenza:
        if lotto.data_scadenza < oggi:
            return "scaduto"
        if lotto.data_scadenza == oggi:
            return "oggi"
        if lotto.data_scadenza <= oggi + timedelta(days=prodotto.giorni_preavviso):
            return "in_scadenza"
        return "ok"
    giorni = prodotto.categoria.giorni_freschezza
    if giorni and (oggi - lotto.data_carico.date()).days >= giorni:
        return "controllare"
    return "ok"


def _vendibile(lotto, oggi):
    return lotto.data_scadenza is None or lotto.data_scadenza > oggi


def _filtri(sorgente):
    q = (sorgente.get("q") or "").strip()[:100]
    categoria = (sorgente.get("categoria") or "").strip()
    return q, int(categoria) if ID_OK.match(categoria) else None


def _scheda(p, oggi):
    """Il magazzino e' un numero certo e si mostra; dello scaffale si mostrano i lotti presenti, non un numero
    (senza cassa nessuno sa quanti pezzi hanno comprato i clienti)."""
    lotti = sorted((l for l in p.lotti if l.qta_esposta + l.qta_magazzino > 0),
                   key=lambda l: (l.data_scadenza is None, l.data_scadenza or oggi, l.data_carico))
    return {
        "p": p,
        "lotti": [{"l": l, "stato": _stato_lotto(l, p, oggi), "sconto": sconto_attivo(l)} for l in lotti],
        "sullo_scaffale": [l for l in lotti if l.qta_esposta > 0],
        "magazzino": sum(l.qta_magazzino for l in lotti),
        "rifornibile": sum(l.qta_magazzino for l in lotti if _vendibile(l, oggi)),
        "riordino": riordino_aperto(p.id),
    }


def _cerca(q, categoria_id, tutti=False, entro=None, giorno=None):
    stmt = (db.select(Prodotto).join(Categoria)
            .where(Prodotto.stato.in_(("attivo", "in_attesa")))
            .options(selectinload(Prodotto.lotti), selectinload(Prodotto.categoria))
            .order_by(Categoria.nome, Prodotto.nome).limit(200))
    if categoria_id:
        stmt = stmt.where(Prodotto.categoria_id == categoria_id)
    if not tutti and not q:
        stmt = stmt.where(Prodotto.lotti.any((Lotto.qta_esposta + Lotto.qta_magazzino) > 0))
    presenti = (Lotto.qta_esposta + Lotto.qta_magazzino) > 0
    if entro is not None:
        stmt = stmt.where(Prodotto.lotti.any(and_(presenti, Lotto.data_scadenza >= date.today(),
                                                  Lotto.data_scadenza <= date.today() + timedelta(days=entro))))
    if giorno is not None:
        stmt = stmt.where(Prodotto.lotti.any(and_(presenti, Lotto.data_scadenza == giorno)))
    if q:
        try:
            info = codici.riconosci(q, current_app.config["BILANCIA_PREFISSI"])
        except codici.CodiceNonValido:
            info = None
        if info and info.get("gtin"):
            stmt = stmt.where(or_(Prodotto.gtin == info["gtin"], Prodotto.codici_aggiuntivi.any(CodiceAggiuntivo.gtin == info["gtin"])))
        elif info and info.get("codice_bilancia"):
            stmt = stmt.where(Prodotto.codice_bilancia == info["codice_bilancia"])
        else:
            sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
            stmt = stmt.where(or_(Prodotto.nome.ilike(f"%{sicuro}%", escape="\\"), Prodotto.marca.ilike(f"%{sicuro}%", escape="\\")))
    oggi = date.today()
    return [_scheda(p, oggi) for p in db.session.scalars(stmt)]


def _filtri_scadenza():
    """Filtri arrivati dalla dashboard: in scadenza entro N giorni, oppure in un giorno preciso."""
    testo_entro = (request.args.get("entro") or "").strip()
    entro = int(testo_entro) if re.fullmatch(r"[0-9]{1,2}", testo_entro) and int(testo_entro) <= 60 else None
    try:
        giorno = date.fromisoformat((request.args.get("giorno") or "").strip()[:10])
    except ValueError:
        giorno = None
    return entro, giorno


def _q_mostrabile(q):
    return "".join(c for c in q if c.isprintable())


@bp.get("/")
@richiede_ruolo("dipendente", "magazziniere")
def pagina():
    q, categoria_id = _filtri(request.args)
    categorie = db.session.scalars(db.select(Categoria).filter_by(attiva=True)
                                   .order_by(Categoria.nome)).all()
    return render_template("inventario.html", schede=_cerca(q, categoria_id, request.args.get("tutti") == "1", *_filtri_scadenza()), categorie=categorie,
                           q=_q_mostrabile(q), categoria_id=categoria_id, filtro_scadenza=_filtri_scadenza())


@bp.get("/risultati")
@richiede_ruolo("dipendente", "magazziniere")
def risultati():
    q, categoria_id = _filtri(request.args)
    return render_template("_risultati.html", schede=_cerca(q, categoria_id, request.args.get("tutti") == "1", *_filtri_scadenza()),
                           q=_q_mostrabile(q), categoria_id=categoria_id, filtro_scadenza=_filtri_scadenza())


def _risposta(prodotto, messaggio, esito, q, categoria_id, annullabile=False):
    """Con htmx restituisce solo la scheda aggiornata, senza htmx fa il classico redirect."""
    if request.headers.get("HX-Request") == "true":
        return render_template("_scheda_prodotto.html", s=_scheda(prodotto, date.today()),
                               messaggio=messaggio, esito=esito, annullabile=annullabile,
                               q=_q_mostrabile(q), categoria_id=categoria_id, filtro_scadenza=_filtri_scadenza())
    flash(messaggio, esito)
    return redirect(url_for(".pagina", q=q or None, categoria=categoria_id))


def sposta_sullo_scaffale(prodotto, quantita):
    """Dal magazzino allo scaffale, prima i lotti che scadono prima (FEFO). Chiude "Riempi lo scaffale".
    Restituisce (messaggio d'errore, movimenti): i movimenti servono per poter annullare."""
    oggi = date.today()
    lotti = db.session.scalars(
        db.select(Lotto)
        .where(Lotto.prodotto_id == prodotto.id, Lotto.qta_magazzino > 0,
               or_(Lotto.data_scadenza.is_(None), Lotto.data_scadenza > oggi))
        .order_by(Lotto.data_scadenza.asc().nulls_last(), Lotto.data_carico)
        .with_for_update()).all()
    disponibile = sum(l.qta_magazzino for l in lotti)
    if quantita > disponibile:
        db.session.rollback()
        return _("In magazzino ci sono solo %(quantita)s", quantita=mostra_quantita(disponibile, prodotto.unita)), []
    restante, movimenti = quantita, []
    for lotto in lotti:
        sposta = min(restante, lotto.qta_magazzino)
        lotto.qta_magazzino -= sposta
        lotto.qta_esposta += sposta
        movimenti.append((lotto.id, sposta))
        restante -= sposta
        if restante == 0:
            break
    _chiudi_notifiche(prodotto.id, "riempi")
    registra("rifornimento", g.utente.id, f"prodotto {prodotto.id}, quantita {quantita}")
    db.session.commit()
    controlla_scaffali([prodotto.id])
    return None, movimenti


@bp.post("/<int:prodotto_id>/rifornisci")
@richiede_ruolo("dipendente", "magazziniere")
def rifornisci(prodotto_id):
    q, categoria_id = _filtri(request.form)
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    if prodotto.stato != "attivo":
        return _risposta(prodotto, _("Prodotto non ancora approvato"), "errore", q, categoria_id)
    quantita = leggi_quantita(request.form.get("quantita"), prodotto.unita)
    if not quantita:
        return _risposta(prodotto, _("Quantita' non valida"), "errore", q, categoria_id)

    errore, movimenti = sposta_sullo_scaffale(prodotto, quantita)
    if errore:
        return _risposta(prodotto, errore, "errore", q, categoria_id)
    from .annulla import ricorda
    ricorda("rifornimento", prodotto_id=prodotto.id, movimenti=movimenti, cerca=prodotto.nome)
    return _risposta(prodotto, _("Spostati sullo scaffale: %(quantita)s", quantita=mostra_quantita(quantita, prodotto.unita)),
                     "ok", q, categoria_id, annullabile=True)


def _intero(testo, minimo, massimo):
    testo = (testo or "").strip()
    if not re.fullmatch(r"[0-9]{1,3}", testo):
        return None
    valore = int(testo)
    return valore if minimo <= valore <= massimo else None


@bp.post("/lotto/<int:lotto_id>/sconto")
@richiede_ruolo("admin")
def sconta(lotto_id):
    q, categoria_id = _filtri(request.form)
    lotto = db.get_or_404(Lotto, lotto_id)
    prodotto = lotto.prodotto
    if request.form.get("azione") == "togli":
        togli_sconto(lotto)
        registra("sconto_tolto", g.utente.id, f"lotto {lotto.id}")
        db.session.commit()
        return _risposta(prodotto, _("Sconto tolto"), "ok", q, categoria_id)

    perc = _intero(request.form.get("perc"), 1, 90)
    totale = lotto.qta_esposta + lotto.qta_magazzino
    testo_q = (request.form.get("quantita") or "").strip()
    quantita = leggi_quantita(testo_q, prodotto.unita) if testo_q else totale
    if lotto.data_scadenza is None or lotto.data_scadenza <= date.today():
        return _risposta(prodotto, _("Si possono scontare solo lotti con scadenza futura"), "errore", q, categoria_id)
    if perc is None or not quantita or quantita > totale:
        return _risposta(prodotto, _("Percentuale (1-90) o quantita' non valida"), "errore", q, categoria_id)
    crea_sconto(lotto, perc, quantita, "manuale", g.utente.id)
    registra("sconto_manuale", g.utente.id, f"lotto {lotto.id}, {perc}%, quantita {quantita}")
    db.session.commit()
    return _risposta(prodotto, _("Sconto -%(perc)s%% registrato: il dipendente ricevera' l'avviso del bollino", perc=perc),
                     "ok", q, categoria_id)


@bp.post("/<int:prodotto_id>/programma")
@richiede_ruolo("admin")
def programma(prodotto_id):
    q, categoria_id = _filtri(request.form)
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    f = request.form
    if f.get("azione") == "rimuovi":
        prodotto.sconto1_giorni = prodotto.sconto1_perc = None
        prodotto.sconto2_giorni = prodotto.sconto2_perc = None
        registra("programmazione_rimossa", g.utente.id, f"prodotto {prodotto.id}")
        db.session.commit()
        return _risposta(prodotto, _("Programmazione rimossa"), "ok", q, categoria_id)

    g1, p1 = _intero(f.get("g1"), 1, 60), _intero(f.get("p1"), 1, 90)
    testo_g2, testo_p2 = (f.get("g2") or "").strip(), (f.get("p2") or "").strip()
    g2 = _intero(testo_g2, 0, 60) if testo_g2 else None
    p2 = _intero(testo_p2, 1, 90) if testo_p2 else None
    if g1 is None or p1 is None:
        return _risposta(prodotto, _("Prima fascia non valida (giorni 1-60, sconto 1-90%)"), "errore", q, categoria_id)
    if (testo_g2 or testo_p2) and (g2 is None or p2 is None or g2 >= g1 or p2 <= p1):
        return _risposta(prodotto, _("Seconda fascia: meno giorni e sconto piu' alto della prima"), "errore",
                         q, categoria_id)
    prodotto.sconto1_giorni, prodotto.sconto1_perc = g1, p1
    prodotto.sconto2_giorni, prodotto.sconto2_perc = g2, p2
    registra("programmazione_sconto", g.utente.id, f"prodotto {prodotto.id}: {g1}gg {p1}%, {g2}gg {p2}%")
    db.session.commit()
    applica_programmati()
    return _risposta(prodotto, _("Sconto programmato"), "ok", q, categoria_id)


@bp.post("/<int:prodotto_id>/conteggio")
@richiede_ruolo("dipendente", "magazziniere")
def conteggio(prodotto_id):
    """Il conteggio fisico del magazzino e' la verita': corregge le quantita' e lascia traccia della differenza."""
    q, categoria_id = _filtri(request.form)
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    lotti = db.session.scalars(
        db.select(Lotto).where(Lotto.prodotto_id == prodotto.id, Lotto.qta_magazzino > 0)
        .order_by(Lotto.id).with_for_update()).all()
    nuovi = {}
    for lotto in lotti:
        testo = (request.form.get(f"mag_{lotto.id}") or "").strip()
        valore = leggi_quantita(testo, prodotto.unita) if testo else lotto.qta_magazzino
        if valore is None:
            return _risposta(prodotto, _("Quantita' non valida"), "errore", q, categoria_id)
        nuovi[lotto.id] = valore

    differenza, dettagli = 0, []
    for lotto in lotti:
        if nuovi[lotto.id] != lotto.qta_magazzino:
            dettagli.append(f"lotto {lotto.id}: {lotto.qta_magazzino} -> {nuovi[lotto.id]}")
            differenza += nuovi[lotto.id] - lotto.qta_magazzino
            lotto.qta_magazzino = nuovi[lotto.id]
    prodotto.ultima_conta_il = adesso()
    if not dettagli:
        db.session.commit()
        return _risposta(prodotto, _("Nessuna differenza: tutto torna"), "ok", q, categoria_id)
    registra("rettifica", g.utente.id, f"conteggio magazzino prodotto {prodotto.id}; " + "; ".join(dettagli))
    db.session.commit()
    controlla_scaffali([prodotto.id])
    segno = "+" if differenza > 0 else "−"
    return _risposta(prodotto, _("Conteggio salvato: differenza %(differenza)s", differenza=segno + mostra_quantita(abs(differenza), prodotto.unita)),
                     "ok", q, categoria_id)


@bp.post("/<int:prodotto_id>/finendo")
@richiede_ruolo("dipendente", "magazziniere")
def finendo(prodotto_id):
    """'Sta finendo': il quaderno delle mancanze, digitale. Racoonix decide il passo successivo."""
    return _segnala(prodotto_id, vuoto=False)


@bp.post("/<int:prodotto_id>/finito")
@richiede_ruolo("dipendente", "magazziniere")
def finito(prodotto_id):
    """'E' finito': sullo scaffale non ne resta nessuno. I lotti non risultano piu' esposti
    (sono stati venduti), poi come per 'Sta finendo': riempire dal magazzino oppure ordinare."""
    return _segnala(prodotto_id, vuoto=True)


def _segnala(prodotto_id, vuoto):
    q, categoria_id = _filtri(request.form)
    prodotto = db.get_or_404(Prodotto, prodotto_id)
    if prodotto.stato != "attivo":
        return _risposta(prodotto, _("Prodotto non ancora approvato"), "errore", q, categoria_id)
    if vuoto:
        for lotto in db.session.scalars(db.select(Lotto).where(
                Lotto.prodotto_id == prodotto.id, Lotto.qta_esposta > 0).with_for_update()):
            lotto.qta_esposta = 0
        registra("scaffale_vuoto", g.utente.id, f"prodotto {prodotto.id}")
    oggi = date.today()
    lotti = sorted((l for l in prodotto.lotti if l.qta_magazzino > 0 and _vendibile(l, oggi)),
                   key=lambda l: (l.data_scadenza is None, l.data_scadenza or oggi, l.data_carico))
    magazzino = sum(l.qta_magazzino for l in lotti)
    if magazzino > 0:
        primo = lotti[0]
        with force_locale(lingua_negozio()):
            scade = _(" (scade il %(data)s)", data=data_it(primo.data_scadenza)) if primo.data_scadenza else ""
            valori = {"utente": g.utente.username, "quantita": mostra_quantita(magazzino, prodotto.unita),
                      "lotto": primo.codice_lotto, "scade": scade}
            if vuoto:
                nota = _("Segnalato da %(utente)s: lo scaffale e' vuoto. In magazzino: %(quantita)s, "
                         "metti davanti il lotto %(lotto)s%(scade)s", **valori)
            else:
                nota = _("Segnalato da %(utente)s: sullo scaffale sta finendo. In magazzino: %(quantita)s, "
                         "metti davanti il lotto %(lotto)s%(scade)s", **valori)
        _apri("riempi", prodotto.id, "magazziniere", nota)
        messaggio = _("Segnalato: chi sta in magazzino ricevera' il compito di riempire lo scaffale")
    elif prodotto.in_esaurimento:
        messaggio = _("Magazzino vuoto, ma il prodotto e' in esaurimento: non verra' riordinato")
    elif apri_riordino(prodotto, "segnalazione", g.utente.id):
        messaggio = _("Magazzino vuoto: aggiunto alla lista d'ordine")
    else:
        messaggio = _("Magazzino vuoto: e' gia' nella lista d'ordine")
    registra("segnalazione_mancanza", g.utente.id, f"prodotto {prodotto.id}, magazzino {magazzino}")
    db.session.commit()
    return _risposta(prodotto, messaggio, "ok", q, categoria_id)
