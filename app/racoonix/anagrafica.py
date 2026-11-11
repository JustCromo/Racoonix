"""Pagine admin dell'anagrafica: catalogo, scheda prodotto, codici aggiuntivi, fornitori, categorie."""
import re
from datetime import date

from flask import Blueprint, flash, g, redirect, render_template, request, url_for
from sqlalchemy import or_
from sqlalchemy.orm import selectinload

from . import codici, db
from .auth import registra, richiede_ruolo
from .carico import _quantita as leggi_quantita
from .catalogo import trova_per_gtin
from .models import Categoria, CodiceAggiuntivo, Fornitore, Prodotto, Sottocategoria
from .prodotti import centesimi
from .formato import _sep
from .lingua import _

bp = Blueprint("anagrafica", __name__, url_prefix="/admin")
NOME_OK = re.compile(r"^[\w .,'()%/&+-]{2,120}$")
BREVE_OK = re.compile(r"^[\w .,'()%/&+-]{1,60}$")
PLU_OK = re.compile(r"^[0-9]{5}$")
TELEFONO_OK = re.compile(r"^[0-9 +()./-]{5,30}$")
EMAIL_OK = re.compile(r"^[^@\s<>\"']{1,64}@[^@\s<>\"']{1,100}\.[A-Za-z]{2,24}$")
NUMERO_OK = re.compile(r"^[0-9]{1,6}$")
STATI = ("attivo", "in_attesa", "rimosso")


def _campo(nome):
    from .formato import testo_pulito
    return testo_pulito(request.form.get(nome))


def _intero(testo, minimo, massimo):
    if not NUMERO_OK.match(testo or ""):
        return None
    valore = int(testo)
    return valore if minimo <= valore <= massimo else None


def _get(modello, testo):
    valore = _intero(testo, 1, 999_999)
    return db.session.get(modello, valore) if valore else None


def _testo_euro(cent):
    return "" if cent is None else f"{cent // 100}{_sep()}{cent % 100:02d}"


def _testo_kg(grammi):
    kg, resto = divmod(grammi, 1000)
    return f"{kg}{_sep()}{resto:03d}"


def _filtro_testo(q):
    sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return or_(Prodotto.nome.ilike(f"%{sicuro}%", escape="\\"),
               Prodotto.marca.ilike(f"%{sicuro}%", escape="\\"))


# ---------- Catalogo ----------

def _cerca_catalogo():
    q = (request.args.get("q") or "").strip()[:100]
    stato = request.args.get("stato") if request.args.get("stato") in STATI else ""
    stmt = (db.select(Prodotto).join(Categoria)
            .options(selectinload(Prodotto.categoria), selectinload(Prodotto.sottocategoria),
                     selectinload(Prodotto.fornitore))
            .order_by(Categoria.nome, Prodotto.nome).limit(300))
    if stato:
        stmt = stmt.where(Prodotto.stato == stato)
    if q:
        try:
            info = codici.riconosci(q)
        except codici.CodiceNonValido:
            info = None
        if info and info.get("gtin"):
            stmt = stmt.where(or_(Prodotto.gtin == info["gtin"],
                                  Prodotto.codici_aggiuntivi.any(CodiceAggiuntivo.gtin == info["gtin"])))
        else:
            stmt = stmt.where(_filtro_testo(q))
    return db.session.scalars(stmt).all(), "".join(c for c in q if c.isprintable()), stato


@bp.get("/catalogo")
@richiede_ruolo("admin")
def catalogo():
    prodotti, q, stato = _cerca_catalogo()
    return render_template("catalogo.html", prodotti=prodotti, q=q, stato=stato)


@bp.get("/catalogo/risultati")
@richiede_ruolo("admin")
def catalogo_risultati():
    prodotti, _x, _x = _cerca_catalogo()
    return render_template("_catalogo_risultati.html", prodotti=prodotti)


# ---------- Scheda prodotto ----------

def _mostra_scheda(p, errori=None, valori=None, codice=200):
    categorie = db.session.scalars(db.select(Categoria).options(selectinload(Categoria.sottocategorie))
                                   .order_by(Categoria.nome)).all()
    fornitori = db.session.scalars(db.select(Fornitore).where(
        or_(Fornitore.attivo.is_(True), Fornitore.id == p.fornitore_id)).order_by(Fornitore.ragione_sociale)).all()
    return render_template("anagrafica_prodotto.html", p=p, categorie=categorie, fornitori=fornitori,
                           errori=errori or [], valori=valori or {}, prezzo_testo=_testo_euro(p.prezzo_centesimi),
                           riordino_testo="" if p.soglia_riordino is None else (_testo_kg(p.soglia_riordino) if p.unita == "kg" else str(p.soglia_riordino))), codice


@bp.get("/catalogo/<int:pid>")
@richiede_ruolo("admin")
def scheda(pid):
    return _mostra_scheda(db.get_or_404(Prodotto, pid))


def _ha_storia(p):
    """Un prodotto con lotti o ordini alle spalle non si cancella: si archivia, cosi' lo storico resta intero."""
    from .models import Lotto, Riordino
    return bool(db.session.scalar(db.select(Lotto.id).filter_by(prodotto_id=p.id).limit(1))
                or db.session.scalar(db.select(Riordino.id).filter_by(prodotto_id=p.id).limit(1)))


def _merce_presente(p):
    return any(l.qta_esposta + l.qta_magazzino > 0 for l in p.lotti)


@bp.route("/catalogo/<int:pid>/elimina", methods=["GET", "POST"])
@richiede_ruolo("admin")
def elimina_prodotto(pid):
    from .models import Notifica
    from .riordini import chiudi_riordini, APERTI
    p = db.get_or_404(Prodotto, pid)
    torna = redirect(url_for(".scheda", pid=p.id))
    if p.stato != "attivo":
        flash(_("Si possono eliminare solo i prodotti attivi"), "errore")
        return torna
    if _merce_presente(p):
        flash(_("C'e' ancora merce di questo prodotto: segnala che e' finito o conta il magazzino, poi eliminalo"), "errore")
        return torna
    archiviare = _ha_storia(p)
    if request.method == "GET":
        return render_template("prodotto_elimina.html", p=p, archiviare=archiviare)
    nome = p.descrizione
    if archiviare:
        p.stato = "rimosso"
        chiudi_riordini(p.id, APERTI, "annullato")
        for notifica in db.session.scalars(db.select(Notifica).filter_by(prodotto_id=p.id, stato="aperta")):
            notifica.stato = "chiusa"
        registra("prodotto_archiviato", g.utente.id, f"prodotto {p.id}: {nome}")
        db.session.commit()
        flash(_("%(prodotto)s eliminato dal catalogo: lo storico resta, e puoi ripristinarlo quando vuoi", prodotto=nome), "ok")
        return redirect(url_for(".catalogo"))
    for notifica in db.session.scalars(db.select(Notifica).filter_by(prodotto_id=p.id)):
        db.session.delete(notifica)
    db.session.delete(p)
    registra("prodotto_eliminato", g.utente.id, f"prodotto {pid}: {nome}")
    db.session.commit()
    flash(_("%(prodotto)s eliminato definitivamente", prodotto=nome), "ok")
    return redirect(url_for(".catalogo"))


@bp.post("/catalogo/<int:pid>/ripristina")
@richiede_ruolo("admin")
def ripristina_prodotto(pid):
    p = db.get_or_404(Prodotto, pid)
    if p.stato == "rimosso":
        p.stato = "attivo"
        registra("prodotto_ripristinato", g.utente.id, f"prodotto {p.id}: {p.descrizione}")
        db.session.commit()
        flash(_("Prodotto ripristinato"), "ok")
    return redirect(url_for(".scheda", pid=p.id))


@bp.post("/catalogo/<int:pid>")
@richiede_ruolo("admin")
def salva(pid):
    p = db.get_or_404(Prodotto, pid)
    errori = []
    nome, marca = _campo("nome"), _campo("marca")
    if not NOME_OK.match(nome):
        errori.append(_("Nome non valido"))
    if marca and not BREVE_OK.match(marca):
        errori.append(_("Marca non valida"))
    categoria = _get(Categoria, _campo("categoria_id"))
    if categoria is None:
        errori.append(_("Categoria non valida"))
    sotto = None
    if _campo("sottocategoria_id"):
        sotto = _get(Sottocategoria, _campo("sottocategoria_id"))
        if sotto is None or categoria is None or sotto.categoria_id != categoria.id:
            errori.append(_("La sottocategoria deve appartenere alla categoria scelta"))
    fornitore = None
    if _campo("fornitore_id"):
        fornitore = _get(Fornitore, _campo("fornitore_id"))
        if fornitore is None:
            errori.append(_("Fornitore non valido"))
    prezzo = centesimi(_campo("prezzo"))
    if prezzo is None:
        errori.append(_("Prezzo non valido (esempio: 2,49)"))

    pezzi, quantita, unita_formato = 1, None, None
    if p.unita == "pezzo":
        pezzi = _intero(_campo("formato_pezzi") or "1", 1, 99)
        testo_q, unita_formato = _campo("formato_quantita"), _campo("formato_unita") or None
        if pezzi is None:
            errori.append(_("Numero di pezzi non valido (1-99)"))
        if testo_q or unita_formato:
            quantita = _intero(testo_q, 1, 100_000)
            if quantita is None or unita_formato not in ("g", "ml", "pz"):
                errori.append(_("Formato non valido: servono quantita' e unita'"))

    testo_riordino = _campo("soglia_riordino")
    soglia_riordino = leggi_quantita(testo_riordino, p.unita) if testo_riordino else None
    if testo_riordino and soglia_riordino is None:
        errori.append(_("Soglia di riordino non valida"))
    preavviso = _intero(_campo("giorni_preavviso"), 0, 60)
    if preavviso is None:
        errori.append(_("Giorni di preavviso non validi (0-60)"))
    plu = _campo("codice_bilancia") or None
    if plu and not PLU_OK.match(plu):
        errori.append(_("Codice bilancia: servono 5 cifre"))
    elif plu and db.session.scalar(db.select(Prodotto.id).where(
            Prodotto.codice_bilancia == plu, Prodotto.id != p.id)):
        errori.append(_("Codice bilancia gia' usato da un altro prodotto"))
    if not p.gtin and not plu:
        errori.append(_("Serve almeno il GTIN o il codice bilancia"))
    if errori:
        return _mostra_scheda(p, errori, request.form, 400)

    vecchio_prezzo = p.prezzo_centesimi
    p.nome, p.marca = nome, marca or None
    p.categoria_id = categoria.id
    p.sottocategoria_id = sotto.id if sotto else None
    p.fornitore_id = fornitore.id if fornitore else None
    p.prezzo_centesimi = prezzo
    p.formato_pezzi, p.formato_quantita = pezzi, quantita
    p.formato_unita = unita_formato if quantita else None
    p.giorni_preavviso = preavviso
    p.soglia_riordino = soglia_riordino
    p.codice_bilancia = plu
    p.in_esaurimento = request.form.get("in_esaurimento") == "1"
    registra("prodotto_modificato", g.utente.id, f"prodotto {p.id}, prezzo {vecchio_prezzo} -> {prezzo}")
    db.session.commit()
    from .notifiche import controlla_scaffali
    controlla_scaffali([p.id])
    flash(_("Scheda salvata"), "ok")
    return redirect(url_for(".scheda", pid=p.id))


@bp.post("/catalogo/<int:pid>/codici")
@richiede_ruolo("admin")
def aggiungi_codice(pid):
    p = db.get_or_404(Prodotto, pid)
    try:
        info = codici.riconosci(_campo("gtin"))
    except codici.CodiceNonValido:
        info = None
    descrizione = _campo("descrizione")
    if info is None or info["tipo"] not in ("ean", "editoriale"):
        flash(_("Serve un EAN o UPC valido"), "errore")
    elif trova_per_gtin(info["gtin"]):
        flash(_("Questo codice e' gia' associato a un prodotto"), "errore")
    elif descrizione and not BREVE_OK.match(descrizione):
        flash(_("Descrizione non valida"), "errore")
    else:
        p.codici_aggiuntivi.append(CodiceAggiuntivo(gtin=info["gtin"], descrizione=descrizione or None))
        registra("codice_aggiunto", g.utente.id, f"prodotto {p.id}, gtin {info['gtin']}")
        db.session.commit()
        flash(_("Codice aggiunto"), "ok")
    return redirect(url_for(".scheda", pid=p.id))


@bp.post("/catalogo/codici/<int:cid>/rimuovi")
@richiede_ruolo("admin")
def rimuovi_codice(cid):
    codice = db.get_or_404(CodiceAggiuntivo, cid)
    pid = codice.prodotto_id
    registra("codice_rimosso", g.utente.id, f"prodotto {pid}, gtin {codice.gtin}")
    db.session.delete(codice)
    db.session.commit()
    flash(_("Codice rimosso"), "ok")
    return redirect(url_for(".scheda", pid=pid))


# ---------- Fornitori ----------

def _leggi_fornitore(escludi_id=None):
    errori = []
    ragione, piva = _campo("ragione_sociale"), _campo("partita_iva") or None
    telefono, email = _campo("telefono") or None, _campo("email") or None
    if not NOME_OK.match(ragione):
        errori.append(_("Ragione sociale non valida"))
    elif db.session.scalar(db.select(Fornitore.id).where(
            Fornitore.ragione_sociale == ragione, Fornitore.id != (escludi_id or 0))):
        errori.append(_("Esiste gia' un fornitore con questa ragione sociale"))
    if piva and not codici.piva_valida(piva):
        errori.append(_("Partita IVA non valida (11 cifre con cifra di controllo corretta)"))
    elif piva and db.session.scalar(db.select(Fornitore.id).where(
            Fornitore.partita_iva == piva, Fornitore.id != (escludi_id or 0))):
        errori.append(_("Partita IVA gia' presente"))
    if telefono and not TELEFONO_OK.match(telefono):
        errori.append(_("Telefono non valido"))
    if email and not EMAIL_OK.match(email):
        errori.append(_("Email non valida"))
    giorni = sorted({v for v in request.form.getlist("giorni") if v in "0123456" and len(v) == 1})
    return {"ragione_sociale": ragione, "partita_iva": piva, "telefono": telefono, "email": email,
            "giorni_ordine": "".join(giorni) or None}, errori


def _cerca_fornitori(q):
    stmt = db.select(Fornitore).order_by(Fornitore.attivo.desc(), Fornitore.ragione_sociale).limit(300)
    if q:
        modello = "%" + q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
        stmt = stmt.where(or_(*(campo.ilike(modello, escape="\\") for campo in (
            Fornitore.ragione_sociale, Fornitore.partita_iva, Fornitore.telefono, Fornitore.email))))
    return db.session.scalars(stmt).all()


def _q_fornitori():
    q = (request.args.get("q") or "").strip()[:100]
    return q, "".join(c for c in q if c.isprintable())


@bp.get("/fornitori")
@richiede_ruolo("admin")
def fornitori():
    q, mostra = _q_fornitori()
    return render_template("fornitori.html", fornitori=_cerca_fornitori(q), q=mostra, oggi=date.today().weekday())


@bp.get("/fornitori/risultati")
@richiede_ruolo("admin")
def fornitori_risultati():
    q, _x = _q_fornitori()
    return render_template("_fornitori_risultati.html", fornitori=_cerca_fornitori(q), oggi=date.today().weekday())


@bp.route("/fornitori/nuovo", methods=["GET", "POST"])
@richiede_ruolo("admin")
def nuovo_fornitore():
    if request.method == "GET":
        return render_template("fornitore_nuovo.html", errori=[], valori={}, giorni="")
    dati, errori = _leggi_fornitore()
    if errori:
        return render_template("fornitore_nuovo.html", errori=errori, valori=request.form,
                               giorni=dati["giorni_ordine"] or ""), 400
    fornitore = Fornitore(**dati)
    db.session.add(fornitore)
    registra("fornitore_creato", g.utente.id, dati["ragione_sociale"])
    db.session.commit()
    flash(_("Fornitore aggiunto: %(nome)s", nome=fornitore.ragione_sociale), "ok")
    return redirect(url_for(".fornitori", _anchor=f"fornitore-{fornitore.id}"))


@bp.post("/fornitori/<int:fid>")
@richiede_ruolo("admin")
def salva_fornitore(fid):
    fornitore = db.get_or_404(Fornitore, fid)
    dati, errori = _leggi_fornitore(fornitore.id)
    if errori:
        for e in errori:
            flash(e, "errore")
        return redirect(url_for(".fornitori"))
    for chiave, valore in dati.items():
        setattr(fornitore, chiave, valore)
    fornitore.attivo = request.form.get("attivo") == "1"
    registra("fornitore_modificato", g.utente.id, f"fornitore {fornitore.id}")
    db.session.commit()
    flash(_("Fornitore salvato"), "ok")
    return redirect(url_for(".fornitori"))


# ---------- Categorie e sottocategorie ----------

@bp.get("/categorie")
@richiede_ruolo("admin")
def categorie():
    import unicodedata
    semplice = lambda s: unicodedata.normalize("NFD", s).encode("ascii", "ignore").decode().lower()
    q = (request.args.get("q") or "").strip()[:60]
    elenco = db.session.scalars(db.select(Categoria).options(selectinload(Categoria.sottocategorie))
                                .order_by(Categoria.nome)).all()
    if q:
        cerca = semplice(q)
        elenco = [c for c in elenco if cerca in semplice(c.nome) or any(cerca in semplice(s.nome) for s in c.sottocategorie)]
    return render_template("categorie.html", categorie=elenco, q="".join(ch for ch in q if ch.isprintable()))


@bp.post("/categorie/nuova")
@richiede_ruolo("admin")
def nuova_categoria():
    nome = _campo("nome")
    if not BREVE_OK.match(nome) or len(nome) > 50:
        flash(_("Nome categoria non valido"), "errore")
    elif db.session.scalar(db.select(Categoria.id).filter_by(nome=nome)):
        flash(_("Categoria gia' esistente"), "errore")
    else:
        db.session.add(Categoria(nome=nome))
        registra("categoria_creata", g.utente.id, nome)
        db.session.commit()
        flash(_("Categoria aggiunta"), "ok")
    return redirect(url_for(".categorie"))


@bp.post("/categorie/<int:cid>")
@richiede_ruolo("admin")
def salva_categoria(cid):
    categoria = db.get_or_404(Categoria, cid)
    freschezza = _intero(_campo("giorni_freschezza"), 1, 60) if _campo("giorni_freschezza") else None
    g1, p1 = _intero(_campo("g1") or "0", 0, 60), _intero(_campo("p1") or "0", 0, 90)
    g2, p2 = _intero(_campo("g2") or "0", 0, 60), _intero(_campo("p2") or "0", 0, 90)
    if (_campo("giorni_freschezza") and freschezza is None) or None in (g1, p1, g2, p2):
        flash(_("%(categoria)s: valori non validi", categoria=categoria.nome), "errore")
    elif g2 > g1:
        flash(_("%(categoria)s: la seconda fascia deve avere meno giorni della prima", categoria=categoria.nome), "errore")
    else:
        categoria.richiede_scadenza = request.form.get("richiede_scadenza") == "1"
        categoria.attiva = request.form.get("attiva") == "1"
        categoria.giorni_freschezza = freschezza
        categoria.sconto1_giorni, categoria.sconto1_perc = g1, p1
        categoria.sconto2_giorni, categoria.sconto2_perc = g2, p2
        registra("categoria_modificata", g.utente.id, f"categoria {categoria.id}")
        db.session.commit()
        flash(f"{categoria.nome}: salvata", "ok")
    return redirect(url_for(".categorie"))


@bp.post("/categorie/<int:cid>/sottocategorie")
@richiede_ruolo("admin")
def nuova_sottocategoria(cid):
    categoria = db.get_or_404(Categoria, cid)
    nome = _campo("nome")
    if not BREVE_OK.match(nome) or len(nome) > 50:
        flash(_("Nome sottocategoria non valido"), "errore")
    elif db.session.scalar(db.select(Sottocategoria.id).filter_by(categoria_id=categoria.id, nome=nome)):
        flash(_("Sottocategoria gia' esistente"), "errore")
    else:
        db.session.add(Sottocategoria(categoria_id=categoria.id, nome=nome))
        registra("sottocategoria_creata", g.utente.id, f"{categoria.nome} > {nome}")
        db.session.commit()
        flash(_("Sottocategoria aggiunta"), "ok")
    return redirect(url_for(".categorie"))


@bp.post("/sottocategorie/<int:sid>/attiva")
@richiede_ruolo("admin")
def cambia_sottocategoria(sid):
    sotto = db.get_or_404(Sottocategoria, sid)
    sotto.attiva = not sotto.attiva
    registra("sottocategoria_modificata", g.utente.id, f"sottocategoria {sotto.id}, attiva {sotto.attiva}")
    db.session.commit()
    return redirect(url_for(".categorie"))
