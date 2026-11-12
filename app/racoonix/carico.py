import re
import secrets
import time
from datetime import date, timedelta

from flask import (Blueprint, current_app, flash, g, redirect, render_template,
                   request, session, url_for)

from . import codici, db
from .auth import registra, richiede_ruolo
from .models import Categoria, Lotto, Notifica, Prodotto
from .notifiche import controlla_scaffali
from .riordini import merce_arrivata
from .catalogo import trova_per_gtin
from .formato import testo_pulito
from .lingua import _, _l

bp = Blueprint("carico", __name__, url_prefix="/carico")
NOME_OK = re.compile(r"^[\w .,'()%/&+-]{2,120}$")
ID_OK = re.compile(r"^[0-9]{1,9}$")
PEZZI_OK = re.compile(r"^[0-9]{1,5}$")
KG_OK = re.compile(r"^[0-9]{1,4}([.,][0-9]{1,3})?$")
ERRORE_CODICE = _l("Codice non riconosciuto")
CHIAVE = "carichi"


def _metti_in_sospeso(info):
    """Ogni lettura ha il suo codice: due schede aperte non si scambiano il prodotto. Tengo solo gli ultimi 5."""
    sospesi = dict(session.get(CHIAVE) or {})
    # La sessione salva le chiavi in ordine alfabetico, non di arrivo: tolgo la lettura piu' vecchia per orario
    while len(sospesi) >= 5:
        sospesi.pop(min(sospesi, key=lambda k: sospesi[k].get("letto", 0)))
    chiave = secrets.token_urlsafe(8)
    info["letto"] = time.time()
    sospesi[chiave] = info
    session[CHIAVE] = sospesi
    return chiave


def _categorie():
    return db.session.scalars(
        db.select(Categoria).filter_by(attiva=True).order_by(Categoria.nome)).all()


def _id(testo):
    testo = (testo or "").strip()
    return int(testo) if ID_OK.match(testo) else None


def _quantita(testo, unita):
    """Pezzi interi, oppure kg con al massimo 3 decimali convertiti in grammi interi."""
    testo = (testo or "").strip()
    if not testo:
        return 0
    if unita == "pezzo":
        return int(testo) if PEZZI_OK.match(testo) else None
    if not KG_OK.match(testo):
        return None
    intero, _x, decimali = testo.replace(",", ".").partition(".")
    return int(intero) * 1000 + int(decimali.ljust(3, "0"))


def _prodotto_da_info(info):
    if info.get("prodotto_id"):
        return db.session.get(Prodotto, info["prodotto_id"])
    if info.get("gtin"):
        return trova_per_gtin(info["gtin"])
    return None


def _mostra_form(info, prodotto, errori=None, valori=None, codice=200):
    from .riordini import riordino_aperto
    valori = dict(valori or {})
    # Carico a raffica: ricordo le ultime quantita' e (se scritta a mano) l'ultima scadenza
    if not errori and session.get("raffica"):
        for chiave, valore in (session.get("ultimo_carico") or {}).items():
            valori.setdefault(chiave, valore)
    # Prodotto ordinato: propongo la quantita' dell'ordine, cosi' si vede subito se ne manca qualcuno
    ordine = riordino_aperto(prodotto.id) if prodotto else None
    if ordine and ordine.stato == "ordinato" and ordine.quantita and not errori:
        from .formato import quantita_input
        valori["magazzino"] = quantita_input(ordine.quantita, prodotto.unita)
    if not errori and prodotto is None and info.get("suggerito"):
        sugg = info["suggerito"]
        valori.setdefault("nome", sugg["nome"])
        valori.setdefault("marca", sugg.get("marca") or "")
        if sugg.get("formato"):
            pezzi, quantita, unita = sugg["formato"]
            valori.setdefault("formato_pezzi", str(pezzi))
            valori.setdefault("formato_quantita", str(quantita))
            valori.setdefault("formato_unita", unita)
    return render_template("carico_form.html", info=info, prodotto=prodotto, ordine=ordine,
                           categorie=_categorie(), errori=errori or [],
                           valori=valori, oggi=date.today()), codice


@bp.get("/")
@richiede_ruolo("magazziniere")
def pagina():
    from .annulla import disponibile
    sfusi = db.session.scalars(
        db.select(Prodotto)
        .where(Prodotto.codice_bilancia.is_not(None), Prodotto.stato == "attivo")
        .order_by(Prodotto.nome)).all()
    return render_template("carico.html", sfusi=sfusi, raffica=bool(session.get("raffica")),
                           annullabile=disponibile("carico"))


@bp.post("/raffica")
@richiede_ruolo("magazziniere")
def raffica():
    """Carico a raffica: dopo ogni carico la fotocamera si riaccende da sola e le quantita' restano."""
    session["raffica"] = request.form.get("attiva") == "1"
    if not session["raffica"]:
        session.pop("ultimo_carico", None)
    return redirect(url_for(".pagina"))


@bp.post("/leggi")
@richiede_ruolo("magazziniere")
def leggi():
    try:
        info = codici.riconosci(request.form.get("codice"), current_app.config["BILANCIA_PREFISSI"])
    except codici.CodiceNonValido as errore:
        current_app.logger.info("carico: codice rifiutato (%s)", errore)
        flash(ERRORE_CODICE, "errore")
        return redirect(url_for(".pagina"))
    if info["tipo"] == "bilancia":
        flash(_("Etichetta di una bilancia del negozio: per i prodotti a peso scegli il prodotto dall'elenco qui sotto"), "errore")
        return redirect(url_for(".pagina"))
    info = {k: (v.isoformat() if isinstance(v, date) else v) for k, v in info.items()}
    prodotto = _prodotto_da_info(info)
    if prodotto and prodotto.stato == "rimosso":
        flash(_("Prodotto non ammesso: contatta l'admin"), "errore")
        return redirect(url_for(".pagina"))
    if prodotto is None and info.get("gtin"):
        from . import negozio
        from .lingua import scegli_lingua
        from .openfoodfacts import cerca
        if negozio.impostazioni().get("open_food_facts") != "0":
            info["suggerito"] = cerca(info["gtin"], scegli_lingua())
    info["chiave"] = _metti_in_sospeso(info)
    return _mostra_form(info, prodotto)


@bp.post("/sfuso")
@richiede_ruolo("magazziniere")
def sfuso():
    pid = _id(request.form.get("prodotto_id"))
    prodotto = db.session.get(Prodotto, pid) if pid else None
    if prodotto is None or prodotto.stato != "attivo":
        flash(ERRORE_CODICE, "errore")
        return redirect(url_for(".pagina"))
    info = {"tipo": "manuale", "prodotto_id": prodotto.id, "gtin": None, "scadenza": None,
            "tipo_data": None, "lotto": None, "confezionamento": None, "peso_g": None}
    info["chiave"] = _metti_in_sospeso(info)
    return _mostra_form(info, prodotto)


@bp.post("/conferma")
@richiede_ruolo("magazziniere")
def conferma():
    info = (session.get(CHIAVE) or {}).get(request.form.get("carico") or "")
    if not info:
        flash(_("Carico scaduto, rileggi il codice"), "errore")
        return redirect(url_for(".pagina"))
    prodotto = _prodotto_da_info(info)
    if prodotto and prodotto.stato == "rimosso":
        flash(_("Prodotto non ammesso: contatta l'admin"), "errore")
        return redirect(url_for(".pagina"))

    f = request.form
    errori = []
    if prodotto is None:
        nome = testo_pulito(f.get("nome"))
        unita = f.get("unita")
        cid = _id(f.get("categoria_id"))
        categoria = db.session.get(Categoria, cid) if cid else None
        if not NOME_OK.match(nome):
            errori.append(_("Nome non valido"))
        if categoria is None or not categoria.attiva:
            errori.append(_("Categoria non valida"))
        if unita not in ("pezzo", "kg"):
            errori.append(_("Unita' non valida"))
        marca = testo_pulito(f.get("marca"))[:60] or None
        if marca and not NOME_OK.match(marca):
            errori.append(_("Marca non valida"))
        formato_pezzi, formato_quantita, formato_unita = 1, None, None
        testo_q = (f.get("formato_quantita") or "").strip()
        if unita == "pezzo" and testo_q:
            pezzi_t = (f.get("formato_pezzi") or "1").strip()
            formato_unita = f.get("formato_unita")
            if not (PEZZI_OK.match(pezzi_t) and 1 <= int(pezzi_t) <= 99 and PEZZI_OK.match(testo_q)
                    and 1 <= int(testo_q) <= 100_000 and formato_unita in ("g", "ml", "pz")):
                errori.append(_("Formato non valido: servono quantita' e unita'"))
            else:
                formato_pezzi, formato_quantita = int(pezzi_t), int(testo_q)
        if not formato_quantita:
            formato_unita = None
    else:
        categoria, unita = prodotto.categoria, prodotto.unita

    attivo = prodotto is not None and prodotto.stato == "attivo"
    esposta = _quantita(f.get("esposta"), unita) if attivo else 0
    magazzino = _quantita(f.get("magazzino"), unita)
    if esposta is None or magazzino is None:
        errori.append(_("Quantita' non valida"))
    elif esposta + magazzino <= 0:
        errori.append(_("Inserisci almeno una quantita'"))

    oggi = date.today()
    scadenza = None
    if info.get("scadenza"):
        scadenza = date.fromisoformat(info["scadenza"])
    else:
        testo = (f.get("scadenza") or "").strip()
        if testo:
            try:
                scadenza = date.fromisoformat(testo)
            except ValueError:
                errori.append(_("Data di scadenza non valida"))
        elif categoria is not None and categoria.richiede_scadenza:
            errori.append(_("Questa categoria richiede la data di scadenza"))
    if scadenza and scadenza < oggi:
        errori.append(_("Prodotto gia' scaduto: non si puo' caricare"))
    if scadenza and scadenza > oggi + timedelta(days=3650):
        errori.append(_("Data di scadenza non plausibile"))

    codice_lotto = info.get("lotto") or (f.get("lotto") or "").strip()
    if codice_lotto and not codici.LOTTO_OK.match(codice_lotto):
        errori.append(_("Lotto non valido"))

    if errori:
        return _mostra_form(info, prodotto, errori, f, 400)

    if not codice_lotto:
        codice_lotto = f"INT{oggi:%y%m%d}{secrets.token_hex(2).upper()}"

    if prodotto is None:
        prodotto = Prodotto(gtin=info.get("gtin"), nome=nome, marca=marca, categoria_id=categoria.id,
                            formato_pezzi=formato_pezzi, formato_quantita=formato_quantita, formato_unita=formato_unita,
                            unita=unita, stato="in_attesa", creato_da=g.utente.id)
        db.session.add(prodotto)
        db.session.flush()
        db.session.add(Notifica(tipo="da_approvare", prodotto_id=prodotto.id,
                                ruolo_destinatario="admin"))
        prodotto_nuovo = True
    else:
        prodotto_nuovo = False

    lotto = db.session.scalar(db.select(Lotto).filter_by(
        prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza))
    lotto_nuovo = lotto is None
    if lotto is None:
        lotto = Lotto(prodotto_id=prodotto.id, codice_lotto=codice_lotto, data_scadenza=scadenza,
                      qta_esposta=0, qta_magazzino=0, caricato_da=g.utente.id)
        db.session.add(lotto)
    lotto.qta_esposta += esposta
    lotto.qta_magazzino += magazzino

    # Merce ordinata: se ne arriva una quantita' diversa, lo dico subito e resta nel registro
    from .formato import quantita as mostra_quantita
    from .models import Riordino
    from .riordini import APERTI
    aperti = db.session.scalars(db.select(Riordino).where(
        Riordino.prodotto_id == prodotto.id, Riordino.stato.in_(APERTI))).all()
    differenza = None
    for r in aperti:
        if r.stato == "ordinato" and r.quantita and r.quantita != esposta + magazzino:
            differenza = _("Ordinati %(ordinati)s, arrivati %(arrivati)s: controlla la consegna",
                           ordinati=mostra_quantita(r.quantita, prodotto.unita),
                           arrivati=mostra_quantita(esposta + magazzino, prodotto.unita))
            registra("consegna_diversa", g.utente.id,
                     f"prodotto {prodotto.id}: ordinati {r.quantita}, arrivati {esposta + magazzino}")
    stati_prima = [(r.id, r.stato) for r in aperti]
    merce_arrivata(prodotto.id)
    registra("carico", g.utente.id,
             f"prodotto {prodotto.id}, lotto {codice_lotto}, esposta {esposta}, magazzino {magazzino}")
    db.session.commit()
    sospesi = dict(session.get(CHIAVE) or {})
    sospesi.pop(request.form.get("carico") or "", None)
    session[CHIAVE] = sospesi
    controlla_scaffali([prodotto.id])
    from .annulla import ricorda
    ricorda("carico", lotto_id=lotto.id, esposta=esposta, magazzino=magazzino, lotto_nuovo=lotto_nuovo,
            prodotto_nuovo=prodotto_nuovo, riordini=stati_prima, nome=prodotto.descrizione)
    if session.get("raffica"):
        session["ultimo_carico"] = {k: (f.get(k) or "").strip() for k in ("esposta", "magazzino", "scadenza")
                                    if (f.get(k) or "").strip()}
    if differenza:
        flash(differenza, "errore")
    flash(_("Caricato: %(prodotto)s", prodotto=prodotto.descrizione), "ok")
    return redirect(url_for(".pagina"))
