"""Annuncia Racoonix nella rete del negozio con un nome facile (racoonix.local), come fanno le stampanti.
Gira in un container separato: niente servizi da installare sul server, niente permessi di amministratore.

Se nella rete c'e' gia' un altro dispositivo con lo stesso nome (per esempio un secondo Racoonix di prova),
non lo contende: lo scrive chiaramente nel log e riprova ogni qualche minuto.
Uso per l'installatore: python annuncia.py --verifica  ->  esce con 3 se il nome e' gia' usato da un altro."""
import ipaddress
import os
import re
import socket
import struct
import sys
import time

from zeroconf import IPVersion, NonUniqueNameException, ServiceInfo, Zeroconf

ATTESA_RIPROVA = 300


def _nome_dns(dati, pos):
    """Legge un nome DNS (con i puntatori di compressione) e restituisce (nome, posizione dopo il nome)."""
    parti, salti, fine = [], 0, None
    while True:
        lung = dati[pos]
        if lung == 0:
            pos += 1
            break
        if lung & 0xC0 == 0xC0:
            if fine is None:
                fine = pos + 2
            pos = ((lung & 0x3F) << 8) | dati[pos + 1]
            salti += 1
            if salti > 20:
                raise ValueError("troppi salti")
            continue
        parti.append(dati[pos + 1:pos + 1 + lung].decode(errors="replace"))
        pos += 1 + lung
    return ".".join(parti).lower(), (fine if fine is not None else pos)


def chi_usa(nome, ip_locale, attesa=2.0):
    """Indirizzi di altri dispositivi che rispondono al nome (domanda mDNS di tipo A)."""
    domanda = struct.pack(">HHHHHH", 0, 0, 1, 0, 0, 0)
    domanda += b"".join(bytes([len(p)]) + p.encode() for p in nome.split(".")) + b"\x00" + struct.pack(">HH", 1, 1)
    s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    try:
        s.setsockopt(socket.IPPROTO_IP, socket.IP_MULTICAST_IF, socket.inet_aton(ip_locale))
        s.settimeout(0.3)
        s.bind((ip_locale, 0))
    except OSError:
        s.close()
        return set()  # rete non pronta: nessun conflitto da segnalare, ci pensera' il prossimo controllo
    trovati = set()
    fine = time.monotonic() + attesa
    s.sendto(domanda, ("224.0.0.251", 5353))
    while time.monotonic() < fine:
        try:
            dati, _da = s.recvfrom(4096)
        except socket.timeout:
            continue
        try:
            _id, _flag, nd, na, ns, nr = struct.unpack(">HHHHHH", dati[:12])
            pos = 12
            for _x in range(nd):
                _n, pos = _nome_dns(dati, pos)
                pos += 4
            for _x in range(na + ns + nr):
                n, pos = _nome_dns(dati, pos)
                tipo, _classe, _ttl, lung = struct.unpack(">HHIH", dati[pos:pos + 10])
                pos += 10
                if tipo == 1 and lung == 4 and n == nome.lower():
                    trovati.add(socket.inet_ntoa(dati[pos:pos + 4]))
                pos += lung
        except (ValueError, IndexError, struct.error):
            continue  # risposta malformata: la ignoro
    s.close()
    return trovati - {ip_locale}


def _configurazione():
    nome = os.environ.get("RACOONIX_NOME", "racoonix.local").strip().lower()
    ip = os.environ.get("RACOONIX_IP", "").strip()
    try:
        indirizzo = str(ipaddress.IPv4Address(ip))
    except ValueError:
        indirizzo = None
    return nome, indirizzo


def verifica():
    nome, ip = _configurazione()
    if ip is None or not re.fullmatch(r"[a-z0-9-]+\.local", nome):
        return 0
    altri = chi_usa(nome, ip)
    if altri:
        print(f"[mdns] {nome} e' gia' usato da {', '.join(sorted(altri))}", flush=True)
        return 3
    return 0


def main():
    nome, ip = _configurazione()
    if ip is None or not re.fullmatch(r"[a-z0-9-]+\.local", nome):
        # Senza IP, o con un nome non .local (va registrato nel DNS del router), non c'e' niente da annunciare.
        # Il container resta fermo in attesa invece di riavviarsi di continuo.
        print(f"[mdns] nessun annuncio (IP {ip!r}, nome {nome!r})", flush=True)
        while True:
            time.sleep(3600)
    servizio = "Racoonix " + nome.removesuffix(".local") + "._https._tcp.local."
    info = ServiceInfo("_https._tcp.local.", servizio, addresses=[socket.inet_aton(ip)],
                       port=443, server=f"{nome}.", properties={"path": "/"})
    while True:
        altri = chi_usa(nome, ip)
        if altri:
            print(f"[mdns] ATTENZIONE: {nome} e' gia' usato da {', '.join(sorted(altri))}. Non lo annuncio: "
                  f"Racoonix resta raggiungibile da https://{ip}. Per un altro nome: ./racoonix.sh nome NOME.local", flush=True)
            time.sleep(ATTESA_RIPROVA)
            continue
        zc = Zeroconf(ip_version=IPVersion.V4Only, interfaces=[ip])
        try:
            zc.register_service(info, allow_name_change=False)
        except NonUniqueNameException:
            zc.close()
            print(f"[mdns] ATTENZIONE: {nome} e' gia' annunciato da un altro Racoonix nella rete. Riprovo tra poco.", flush=True)
            time.sleep(ATTESA_RIPROVA)
            continue
        print(f"[mdns] annunciato {nome} -> {ip}", flush=True)
        try:
            while True:
                time.sleep(3600)
        finally:
            zc.unregister_all_services()
            zc.close()


if __name__ == "__main__":
    sys.exit(verifica() if "--verifica" in sys.argv else main())
