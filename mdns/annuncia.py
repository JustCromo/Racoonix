"""Annuncia Racoonix nella rete del negozio con un nome facile (racoonix.local), come fanno le stampanti.
Gira in un container separato: niente servizi da installare sul server, niente permessi di amministratore."""
import ipaddress
import os
import re
import socket
import sys
import time

from zeroconf import IPVersion, ServiceInfo, Zeroconf


def main():
    nome = os.environ.get("RACOONIX_NOME", "racoonix.local").strip().lower()
    ip = os.environ.get("RACOONIX_IP", "").strip()
    try:
        indirizzo = ipaddress.IPv4Address(ip)
    except ValueError:
        indirizzo = None
    if indirizzo is None or not re.fullmatch(r"[a-z0-9-]+\.local", nome):
        # Senza IP, o con un nome non .local (va registrato nel DNS del router), non c'e' niente da annunciare.
        # Il container resta fermo in attesa invece di riavviarsi di continuo.
        print(f"[mdns] nessun annuncio (IP {ip!r}, nome {nome!r})", flush=True)
        while True:
            time.sleep(3600)
    info = ServiceInfo("_https._tcp.local.", "Racoonix._https._tcp.local.", addresses=[socket.inet_aton(str(indirizzo))],
                       port=443, server=f"{nome}.", properties={"path": "/"})
    zc = Zeroconf(ip_version=IPVersion.V4Only, interfaces=[str(indirizzo)])
    zc.register_service(info, allow_name_change=False)
    print(f"[mdns] annunciato {nome} -> {indirizzo}", flush=True)
    try:
        while True:
            time.sleep(3600)
    finally:
        zc.unregister_all_services()
        zc.close()


if __name__ == "__main__":
    sys.exit(main())
