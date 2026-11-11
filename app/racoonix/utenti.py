import re
import secrets
from datetime import datetime, timezone

from flask import (Blueprint, flash, g, make_response, redirect, render_template,
                   request, url_for)

from . import db
from .auth import ph, registra, richiede_ruolo
from .models import Ruolo, Utente
from .lingua import _

bp = Blueprint("utenti", __name__, url_prefix="/admin/utenti")
USERNAME_OK = re.compile(r"^[a-zA-Z0-9_.-]{3,40}$")


ALFABETO_TEMPORANEA = "abcdefghjkmnpqrstuvwxyz23456789"


def _password_temporanea():
    """Facile da dettare e da scrivere sul telefono: niente l/1/i, o/0, maiuscole o simboli."""
    gruppi = ("".join(secrets.choice(ALFABETO_TEMPORANEA) for _x in range(5)) for _y in range(3))
    return "-".join(gruppi)


def _tutti_i_ruoli():
    return db.session.scalars(db.select(Ruolo).order_by(Ruolo.id)).all()


def _ruoli_dal_form():
    nomi = set(request.form.getlist("ruoli"))
    if not nomi:
        return []
    return db.session.scalars(db.select(Ruolo).where(Ruolo.nome.in_(nomi))).all()


def _altri_admin_attivi(utente_id):
    ruolo_admin = db.session.scalar(db.select(Ruolo).filter_by(nome="admin"))
    return db.session.scalar(
        db.select(db.func.count(Utente.id)).where(
            Utente.ruoli.contains(ruolo_admin),
            Utente.attivo.is_(True),
            Utente.id != utente_id,
        )
    )


RUOLI_FILTRO = ("admin", "magazziniere", "dipendente")
STATI_FILTRO = ("attivo", "disattivato", "bloccato", "temporanea")


def _cerca_utenti():
    q = (request.args.get("q") or "").strip()[:40]
    ruolo = request.args.get("ruolo") if request.args.get("ruolo") in RUOLI_FILTRO else ""
    stato = request.args.get("stato") if request.args.get("stato") in STATI_FILTRO else ""
    stmt = db.select(Utente).where(Utente.eliminato.is_(False)).order_by(Utente.username)
    if q:
        sicuro = q.replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        stmt = stmt.where(Utente.username.ilike(f"%{sicuro}%", escape="\\"))
    if ruolo:
        stmt = stmt.where(Utente.ruoli.any(Ruolo.nome == ruolo))
    adesso = datetime.now(timezone.utc)
    if stato == "attivo":
        stmt = stmt.where(Utente.attivo.is_(True))
    elif stato == "disattivato":
        stmt = stmt.where(Utente.attivo.is_(False))
    elif stato == "bloccato":
        stmt = stmt.where(Utente.bloccato_fino > adesso)
    elif stato == "temporanea":
        stmt = stmt.where(Utente.deve_cambiare_password.is_(True))
    utenti = db.session.scalars(stmt).all()
    # Chi ha una richiesta di dispositivo in attesa sale in cima all'elenco.
    utenti.sort(key=lambda u: not any(d.stato == "in_attesa" for d in u.dispositivi_accesso))
    return utenti, q, ruolo, stato


def _elenco(errore=None, codice=200):
    utenti, q, ruolo, stato = _cerca_utenti()
    return render_template("utenti.html", utenti=utenti, ruoli=_tutti_i_ruoli(), errore=errore,
                           adesso=datetime.now(timezone.utc), q=q, ruolo=ruolo, stato=stato), codice


@bp.get("/risultati")
@richiede_ruolo("admin")
def risultati():
    utenti, _x, _x, _x = _cerca_utenti()
    return render_template("_utenti_risultati.html", utenti=utenti, ruoli=_tutti_i_ruoli(),
                           adesso=datetime.now(timezone.utc))


def _mostra_password(utente, password):
    from .benvenuto import prepara
    link, qr = prepara(utente)
    db.session.commit()
    risposta = make_response(render_template("utenti_password.html",
                                             utente=utente, password=password, link=link, qr=qr))
    risposta.headers["Cache-Control"] = "no-store"
    return risposta


@bp.get("/")
@richiede_ruolo("admin")
def elenco():
    return _elenco()


@bp.route("/nuovo", methods=["GET", "POST"])
@richiede_ruolo("admin")
def nuovo():
    if request.method == "GET":
        return render_template("utenti_nuovo.html", ruoli=_tutti_i_ruoli())

    username = (request.form.get("username") or "").strip()
    scelti = _ruoli_dal_form()
    errore = None
    if not USERNAME_OK.match(username):
        errore = _("Username non valido (3-40 caratteri: lettere, numeri, _ . -)")
    elif not scelti:
        errore = _("Scegli almeno un ruolo")
    elif db.session.scalar(db.select(Utente).filter_by(username=username)):
        errore = _("Username gia' in uso")
    if errore:
        return render_template("utenti_nuovo.html", ruoli=_tutti_i_ruoli(),
                               errore=errore, username=username), 400

    password = _password_temporanea()
    utente = Utente(username=username, password_hash=ph.hash(password),
                    deve_cambiare_password=True)
    utente.ruoli = list(scelti)
    db.session.add(utente)
    registra("utente_creato", g.utente.id,
             f"{username}: {', '.join(r.nome for r in scelti)}")
    db.session.commit()
    return _mostra_password(utente, password)


@bp.post("/<int:utente_id>/ruoli")
@richiede_ruolo("admin")
def ruoli(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    scelti = _ruoli_dal_form()
    if not scelti:
        return _elenco(_("Ogni utente deve avere almeno un ruolo"), 400)
    toglie_admin = utente.ha_ruolo("admin") and not any(r.nome == "admin" for r in scelti)
    if toglie_admin and utente.id == g.utente.id:
        return _elenco(_("Non puoi togliere il ruolo admin a te stesso"), 400)
    if toglie_admin and _altri_admin_attivi(utente.id) == 0:
        return _elenco(_("Deve restare almeno un admin attivo"), 400)
    utente.ruoli = list(scelti)
    registra("ruoli_modificati", g.utente.id,
             f"{utente.username}: {', '.join(r.nome for r in scelti)}")
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/attivo")
@richiede_ruolo("admin")
def attivo(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.id == g.utente.id:
        return _elenco(_("Non puoi disattivare te stesso"), 400)
    if utente.attivo and utente.ha_ruolo("admin") and _altri_admin_attivi(utente.id) == 0:
        return _elenco(_("Deve restare almeno un admin attivo"), 400)
    utente.attivo = not utente.attivo
    if not utente.attivo:
        utente.token_sessione = None
        from .accessi import revoca_tutti
        revoca_tutti(utente.id)
    registra("utente_riattivato" if utente.attivo else "utente_disattivato",
             g.utente.id, utente.username)
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/sblocca")
@richiede_ruolo("admin")
def sblocca(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra("utente_sbloccato", g.utente.id, utente.username)
    db.session.commit()
    return redirect(url_for(".elenco"))


@bp.post("/<int:utente_id>/reset-password")
@richiede_ruolo("admin")
def reset_password(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.id == g.utente.id:
        return _elenco(_("Per te stesso usa 'Cambia password'"), 400)
    password = _password_temporanea()
    utente.password_hash = ph.hash(password)
    utente.deve_cambiare_password = True
    utente.token_sessione = None
    utente.bloccato_fino = None
    utente.tentativi_falliti = 0
    registra("password_resettata", g.utente.id, utente.username)
    _chiudi_richieste_reset(utente.id)
    db.session.commit()
    return _mostra_password(utente, password)


def _chiudi_richieste_reset(utente_id):
    """Quando l'admin genera la password, la richiesta risulta gestita da lui."""
    from .models import Notifica
    for notifica in db.session.scalars(db.select(Notifica).filter_by(
            tipo="reset_password", utente_id=utente_id, stato="aperta")):
        notifica.stato = "chiusa"
        notifica.chiusa_da = g.utente.id
        notifica.chiusa_il = datetime.now(timezone.utc)


def _ha_storico(utente_id):
    """True se l'utente compare in qualche operazione: in quel caso non si cancella, si archivia."""
    from .models import AuditLog, DispositivoAccesso, Lotto, Notifica, Prodotto, Riordino, Scarto, Sconto
    colonne = [AuditLog.utente_id, Lotto.caricato_da, Scarto.utente_id,
               Notifica.chiusa_da, Notifica.utente_id, Prodotto.creato_da, Prodotto.approvato_da,
               Sconto.creato_da, DispositivoAccesso.utente_id, Riordino.segnalato_da, Riordino.ordinato_da]
    return any(db.session.scalar(db.select(c).where(c == utente_id).limit(1)) for c in colonne)


@bp.get("/<int:utente_id>/elimina")
@richiede_ruolo("admin")
def conferma_elimina(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.eliminato or utente.id == g.utente.id:
        return redirect(url_for(".elenco"))
    return render_template("utenti_elimina.html", utente=utente, storico=_ha_storico(utente.id))


@bp.post("/<int:utente_id>/elimina")
@richiede_ruolo("admin")
def elimina(utente_id):
    utente = db.get_or_404(Utente, utente_id)
    if utente.id == g.utente.id:
        return _elenco(_("Non puoi eliminare te stesso"), 400)
    if utente.attivo and utente.ha_ruolo("admin") and _altri_admin_attivi(utente.id) == 0:
        return _elenco(_("Deve restare almeno un admin attivo"), 400)
    nome = utente.username
    if _ha_storico(utente.id):
        utente.eliminato = True
        utente.attivo = False
        utente.token_sessione = None
        utente.ruoli = []
        from .accessi import revoca_tutti
        revoca_tutti(utente.id)
        registra("utente_archiviato", g.utente.id, nome)
        messaggio = _("%(utente)s eliminato dall'elenco: le sue operazioni restano nello storico", utente=nome)
    else:
        registra("utente_eliminato", g.utente.id, nome)
        db.session.delete(utente)
        messaggio = _("%(utente)s eliminato definitivamente", utente=nome)
    db.session.commit()
    flash(messaggio, "ok")
    return redirect(url_for(".elenco"))


@bp.post("/dispositivi/<int:did>/<azione>")
@richiede_ruolo("admin")
def dispositivo(did, azione):
    """Approva (con un nome facoltativo) o revoca un dispositivo personale di un utente."""
    from flask import abort
    from .models import DispositivoAccesso, Notifica
    if azione not in ("approva", "revoca", "riabilita"):
        abort(404)
    voce = db.get_or_404(DispositivoAccesso, did)
    utente = voce.utente
    # Dalla pagina Dispositivi si torna li', dalla scheda dell'utente si torna alla scheda
    torna = redirect(url_for(".dispositivi") if request.form.get("da") == "dispositivi"
                     else url_for(".elenco", _anchor=f"utente-{utente.id}"))
    if azione == "approva":
        if voce.stato != "in_attesa":
            flash(_("Dispositivo gia' gestito"), "errore")
            return torna
        nome = (request.form.get("nome") or "").strip()
        if nome and not re.fullmatch(r"[\w .'()/-]{1,60}", nome):
            flash(_("Nome del dispositivo non valido"), "errore")
            return torna
        voce.stato = "approvato"
        voce.nome = nome or None
        voce.approvato_da = g.utente.id
        voce.approvato_il = datetime.now(timezone.utc)
        registra("dispositivo_approvato", g.utente.id, f"{utente.username}: {voce.nome or voce.descrizione}")
        messaggio = _("Dispositivo di %(utente)s approvato", utente=utente.username)
    elif azione == "riabilita":
        if voce.stato != "revocato" or not utente.attivo or utente.eliminato:
            flash(_("Si possono riabilitare solo i dispositivi bloccati di utenti attivi"), "errore")
            return torna
        voce.stato = "approvato"
        voce.approvato_da = g.utente.id
        voce.approvato_il = datetime.now(timezone.utc)
        registra("dispositivo_riabilitato", g.utente.id, f"{utente.username}: {voce.nome or voce.descrizione}")
        messaggio = _("Dispositivo di %(utente)s riabilitato", utente=utente.username)
    else:
        voce.stato = "revocato"
        registra("dispositivo_revocato", g.utente.id, f"{utente.username}: {voce.nome or voce.descrizione}")
        messaggio = _("Dispositivo di %(utente)s revocato: e' bloccato per qualunque account", utente=utente.username)
    ancora_in_attesa = db.session.scalar(db.select(DispositivoAccesso.id).filter_by(
        utente_id=utente.id, stato="in_attesa").limit(1))
    if not ancora_in_attesa:
        for notifica in db.session.scalars(db.select(Notifica).filter_by(
                tipo="dispositivo", utente_id=utente.id, stato="aperta")):
            notifica.stato = "chiusa"
            notifica.chiusa_da = g.utente.id
            notifica.chiusa_il = datetime.now(timezone.utc)
    db.session.commit()
    flash(messaggio, "ok")
    return torna


@bp.get("/dispositivi")
@richiede_ruolo("admin")
def dispositivi():
    """Tutti i dispositivi, divisi per stato: in attesa, bloccati (con la possibilita' di riabilitarli), approvati."""
    from sqlalchemy.orm import selectinload
    from .models import DispositivoAccesso, Utente
    voci = db.session.scalars(
        db.select(DispositivoAccesso).join(Utente, DispositivoAccesso.utente_id == Utente.id)
        .where(Utente.eliminato.is_(False)).options(selectinload(DispositivoAccesso.utente))
        .order_by(DispositivoAccesso.ultimo_uso.desc().nulls_last(), DispositivoAccesso.creato_il.desc())).all()
    gruppi = {"in_attesa": [], "revocato": [], "approvato": []}
    for voce in voci:
        gruppi[voce.stato].append(voce)
    return render_template("dispositivi.html", gruppi=gruppi)
