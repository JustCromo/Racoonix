"""Impostazioni del negozio (solo admin): nome, lingua, paese, fuso orario e computer dell'amministratore."""
import ipaddress

from flask import Blueprint, flash, g, redirect, render_template, request, url_for

from . import db, negozio
from .auth import registra, richiede_ruolo
from .configurazione import NOME_OK
from .formato import testo_pulito
from .lingua import LINGUE, _

bp = Blueprint("impostazioni", __name__, url_prefix="/admin/impostazioni")


def _contesto(valori, errori):
    return {"valori": valori, "errori": errori, "fusi": negozio.gruppi_fusi(), "paesi": negozio.PAESI,
            "mio_ip": request.remote_addr}


@bp.route("/", methods=["GET", "POST"])
@richiede_ruolo("admin")
def pagina():
    if request.method == "GET":
        return render_template("impostazioni.html", **_contesto(dict(negozio.impostazioni()), []))
    f = request.form
    valori = {k: testo_pulito(f.get(k)) for k in ("nome", "lingua", "paese", "fuso", "reti_admin")}
    valori["open_food_facts"] = "1" if f.get("open_food_facts") == "1" else "0"
    errori = []
    if not NOME_OK.match(valori["nome"]):
        errori.append(_("Nome del negozio non valido (2-60 caratteri)"))
    if valori["lingua"] not in LINGUE:
        errori.append(_("Scegli la lingua del negozio"))
    if valori["paese"] not in negozio.PAESI:
        errori.append(_("Scegli il paese del negozio"))
    if not negozio.fuso_valido(valori["fuso"]):
        errori.append(_("Fuso orario non valido: sceglilo dall'elenco"))
    reti = negozio.leggi_reti(valori["reti_admin"])
    if reti is None:
        errori.append(_("Indirizzi dell'amministratore non validi"))
    else:
        # Mai chiudersi fuori: il computer da cui si salva deve restare tra quelli autorizzati
        mio = ipaddress.ip_address(request.remote_addr)
        if not any(mio in rete for rete in reti):
            errori.append(_("Il computer che stai usando (%(ip)s) deve restare tra quelli autorizzati", ip=str(mio)))
    if errori:
        return render_template("impostazioni.html", **_contesto(valori, errori)), 400
    valori["reti_admin"] = ",".join(str(r) for r in reti)
    negozio.salva(**valori)
    registra("impostazioni_modificate", g.utente.id,
             f"{valori['paese']}, {valori['lingua']}, {valori['fuso']}, admin: {valori['reti_admin']}")
    db.session.commit()
    flash(_("Impostazioni salvate"), "ok")
    return redirect(url_for(".pagina"))
