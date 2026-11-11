#!/usr/bin/env bash
# Racoonix - installazione e gestione con un solo comando.
set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VERDE=$'\e[32m'; GIALLO=$'\e[33m'; ROSSO=$'\e[31m'; GRASSETTO=$'\e[1m'; RESET=$'\e[0m'
BACKUP_DIR="backup"
BACKUP_DA_TENERE="${BACKUP_DA_TENERE:-14}"

# Lingua dei messaggi: quella scelta all'installazione, altrimenti quella del sistema.
LINGUA=$(grep -s '^RACOONIX_LINGUA=' .env | cut -d= -f2 || true)
[[ -z "$LINGUA" ]] && { [[ "${LANG:-}" == en* ]] && LINGUA=en || LINGUA=it; }
t() { if [[ "$LINGUA" == en ]]; then echo "$2"; else echo "$1"; fi; }

ok()      { echo "${VERDE}✔${RESET} $*"; }
info()    { echo "${GRASSETTO}›${RESET} $*"; }
avviso()  { echo "${GIALLO}!${RESET} $*"; }
errore()  { echo "${ROSSO}✘ $*${RESET}" >&2; exit 1; }
chiedi()  { local r; read -rp "$1${2:+ [$2]}: " r; echo "${r:-${2:-}}"; }
conferma(){ local r; read -rp "$1 [$(t s/N y/N)]: " r; [[ "$r" =~ ^[sSyY]$ ]]; }
dc()      { docker compose ${RACOONIX_PROGETTO:+-p "$RACOONIX_PROGETTO"} "$@"; }
valida_ip() { [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }

ip_locale() {
  ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' \
    || hostname -I | awk '{print $1}'
}

controlla_requisiti() {
  command -v docker >/dev/null || errore "$(t "Docker non trovato. Su Ubuntu: sudo apt install docker.io docker-compose-v2" "Docker not found. On Ubuntu: sudo apt install docker.io docker-compose-v2")"
  docker compose version >/dev/null 2>&1 || errore "$(t "Manca Docker Compose v2. Su Ubuntu: sudo apt install docker-compose-v2" "Docker Compose v2 is missing. On Ubuntu: sudo apt install docker-compose-v2")"
  docker info >/dev/null 2>&1 || errore "$(t "Docker non risponde: il servizio e' avviato? Il tuo utente e' nel gruppo docker?" "Docker isn't responding: is the service running? Is your user in the docker group?")"
  command -v openssl >/dev/null || errore "$(t "Manca openssl. Su Ubuntu: sudo apt install openssl" "openssl is missing. On Ubuntu: sudo apt install openssl")"
  ok "$(t "Requisiti presenti" "Requirements found")"
}

controlla_installato() {
  [[ -f .env ]] || errore "$(t "Racoonix non e' installato qui. Usa: ./racoonix.sh installa" "Racoonix isn't installed here. Use: ./racoonix.sh install")"
  # Installazioni precedenti: l'indirizzo si chiamava RACOONIX_SNI
  if ! grep -q '^RACOONIX_IP=' .env && grep -q '^RACOONIX_SNI=' .env; then
    echo "RACOONIX_IP=$(grep '^RACOONIX_SNI=' .env | cut -d= -f2)" >> .env
  fi
}

# Installazioni precedenti: i segreti stavano nella cartella secrets/. Li copio nei volumi una volta sola
# (lo script non sovrascrive mai un segreto gia' presente), cosi' il database esistente continua a funzionare.
importa_segreti_vecchi() {
  [[ -s secrets/db_password ]] || return 0
  dc run --rm --no-deps --cap-add DAC_READ_SEARCH -v "$PWD/secrets:/vecchi:ro" segreti
  avviso "$(t "Segreti importati nei volumi Docker: dopo aver controllato che tutto funzioni, puoi cancellare la cartella secrets/" "Secrets imported into Docker volumes: once you've checked everything works, you can delete the secrets/ folder")"
}

attendi_avvio() {
  info "$(t "Attendo l'avvio di Racoonix..." "Waiting for Racoonix to start...")"
  for _ in $(seq 1 60); do
    if dc exec -T app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" >/dev/null 2>&1; then
      ok "$(t "Racoonix e' attivo" "Racoonix is running")"
      return 0
    fi
    sleep 2
  done
  errore "$(t "Racoonix non risponde. Controlla i log con: ./racoonix.sh log" "Racoonix isn't responding. Check the logs with: ./racoonix.sh logs")"
}

esporta_certificato() {
  for _ in $(seq 1 30); do
    dc cp caddy:/data/caddy/pki/authorities/local/root.crt ./racoonix-root.crt >/dev/null 2>&1 && break
    sleep 1
  done
  if [[ ! -s racoonix-root.crt ]]; then
    avviso "$(t "Certificato non ancora pronto: riprova tra poco con ./racoonix.sh certificato" "Certificate not ready yet: try again shortly with ./racoonix.sh certificate")"
    return 0
  fi
  ok "$(t "Certificato esportato in racoonix-root.crt" "Certificate exported to racoonix-root.crt")"
  echo "  $(t "Impronta SHA-256 (confrontala sul dispositivo dopo l'installazione):" "SHA-256 fingerprint (compare it on the device after installing):")"
  echo "  $(openssl x509 -in racoonix-root.crt -noout -fingerprint -sha256 | cut -d= -f2)"
}

indirizzo() { grep '^RACOONIX_IP=' .env | cut -d= -f2; }
nome_rete() { grep '^RACOONIX_NOME=' .env | cut -d= -f2; }

# La versione (dal tag Git) arriva all'app e compare nella dashboard
segna_versione() {
  local versione
  versione=$(git describe --tags --always 2>/dev/null || echo "?")
  sed -i '/^RACOONIX_VERSIONE=/d' .env
  echo "RACOONIX_VERSIONE=$versione" >> .env
}

mostra_link() {
  dc run --rm --no-deps app python -m racoonix.configurazione
}

# L'installazione fa solo la parte tecnica, senza domande: lingua, paese, fuso orario, nome del negozio
# e account admin si scelgono poi dal browser, con il link monouso che compare alla fine.
installa() {
  [[ -f .env ]] && errore "$(t "Racoonix risulta gia' installato qui. Per aggiornarlo: ./racoonix.sh aggiorna" "Racoonix is already installed here. To update it: ./racoonix.sh update")"
  controlla_requisiti
  local ip="${1:-$(ip_locale)}" nome="${2:-racoonix.local}"
  valida_ip "$ip" || errore "$(t "Non riesco a trovare l'IP di questo server. Indicalo tu: ./racoonix.sh installa 192.168.1.50" "Can't detect this server's IP. Give it yourself: ./racoonix.sh install 192.168.1.50")"
  [[ "$nome" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || errore "$(t "Nome non valido, per esempio racoonix.local" "Invalid name, for example racoonix.local")"
  echo; echo "${GRASSETTO}$(t "Installazione di Racoonix" "Installing Racoonix")${RESET}"; echo
  info "$(t "Indirizzo del server:" "Server address:") $ip  ·  $(t "nome:" "name:") $nome"

  printf 'RACOONIX_IP=%s\nRACOONIX_NOME=%s\n' "$ip" "$nome" > .env
  chmod 600 .env
  segna_versione
  info "$(t "Preparo l'applicazione (la prima volta puo' richiedere qualche minuto)..." "Preparing the application (the first time can take a few minutes)...")"
  dc build
  importa_segreti_vecchi
  dc up -d
  attendi_avvio
  esporta_certificato
  mostra_link
}

backup() {
  controlla_installato
  mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
  local file="$BACKUP_DIR/racoonix-$(date +%Y%m%d-%H%M%S).dump"
  if ! dc exec -T db pg_dump -U racoonix -d racoonix --format=custom > "$file" || [[ ! -s "$file" ]]; then
    rm -f "$file"
    errore "$(t "Backup non riuscito" "Backup failed")"
  fi
  chmod 600 "$file"
  # La dashboard mostra la data dell'ultimo backup riuscito
  dc exec -T db psql -q -U racoonix -d racoonix -c "INSERT INTO impostazioni (chiave, valore, aggiornata_il) VALUES ('sistema.ultimo_backup', 'ok', now()) ON CONFLICT (chiave) DO UPDATE SET valore = 'ok', aggiornata_il = now();" >/dev/null 2>&1 || true
  ok "$(t "Backup salvato:" "Backup saved:") $file ($(du -h "$file" | cut -f1))"
  ls -1t "$BACKUP_DIR"/racoonix-*.dump | tail -n +$((BACKUP_DA_TENERE + 1)) | xargs -r rm -f
}

backup_automatico() {
  controlla_installato
  command -v crontab >/dev/null || errore "$(t "crontab non disponibile su questo sistema" "crontab isn't available on this system")"
  local riga="30 2 * * * cd '$(pwd)' && ./racoonix.sh backup >> $BACKUP_DIR/backup.log 2>&1"
  { { crontab -l 2>/dev/null || true; } | grep -v "racoonix.sh backup" || true; echo "$riga"; } | crontab -
  ok "$(t "Backup automatico ogni notte alle 02:30 (vengono tenuti gli ultimi $BACKUP_DA_TENERE)" "Automatic backup every night at 02:30 (the last $BACKUP_DA_TENERE are kept)")"
}

ripristina() {
  controlla_installato
  local file="${1:-}" copia r
  [[ -f "$file" ]] || errore "$(t "Indica il file da ripristinare, es.: ./racoonix.sh ripristina backup/racoonix-20261109-023000.dump" "Give the file to restore, e.g.: ./racoonix.sh restore backup/racoonix-20261109-023000.dump")"
  avviso "$(t "Il database attuale verra' SOSTITUITO con:" "The current database will be REPLACED with:") $file"
  local parola; parola=$(t RIPRISTINA RESTORE)
  read -rp "$(t "Scrivi RIPRISTINA per confermare:" "Type RESTORE to confirm:") " r
  [[ "$r" == "$parola" ]] || errore "$(t "Annullato: nessuna modifica" "Cancelled: nothing changed")"
  copia=$(mktemp)
  cp "$file" "$copia"
  info "$(t "Prima salvo lo stato attuale, per sicurezza" "First, saving the current state, to be safe")"
  backup
  dc stop app scheduler
  dc exec -T db dropdb -U racoonix --if-exists racoonix
  dc exec -T db createdb -U racoonix -O racoonix racoonix
  dc exec -T db pg_restore -U racoonix -d racoonix --no-owner < "$copia"
  rm -f "$copia"
  dc up -d
  attendi_avvio
  ok "$(t "Ripristino completato" "Restore complete")"
}

aggiorna() {
  controlla_installato
  info "$(t "Backup di sicurezza prima dell'aggiornamento" "Safety backup before updating")"
  backup
  if [[ -d .git ]]; then
    git diff --quiet && git diff --cached --quiet || errore "$(t "Ci sono modifiche locali al codice: salvale o annullale prima di aggiornare" "There are local code changes: commit or discard them before updating")"
    git pull --ff-only
  fi
  segna_versione
  info "$(t "Scarico le immagini aggiornate (correzioni di sicurezza di Caddy e PostgreSQL)" "Downloading updated images (Caddy and PostgreSQL security fixes)")"
  dc pull caddy
  dc build --pull
  importa_segreti_vecchi
  dc up -d
  attendi_avvio
  ok "$(t "Aggiornato: le modifiche al database sono state applicate in automatico" "Updated: database changes were applied automatically")"
  if systemctl is-enabled racoonix-nome >/dev/null 2>&1; then
    avviso "$(t "Il nome in rete ora lo annuncia un container: rimuovi il vecchio servizio con" "The network name is now announced by a container: remove the old service with"): sudo systemctl disable --now racoonix-nome && sudo rm /etc/systemd/system/racoonix-nome.service"
  fi
}

stato() {
  controlla_installato
  dc ps
  echo
  info "$(t "Indirizzo:" "Address:") https://$(indirizzo)"
  local versione
  versione=$(dc exec -T app flask --app racoonix:create_app db current 2>/dev/null | tail -1 || true)
  info "$(t "Versione del database:" "Database version:") ${versione:-$(t "non disponibile" "not available")}"
}

cambia_nome() {
  local nome="$1"
  [[ "$nome" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || errore "$(t "Indica il nuovo nome, per esempio: ./racoonix.sh nome negozio.local" "Give the new name, for example: ./racoonix.sh name shop.local")"
  sed -i '/^RACOONIX_NOME=/d' .env && echo "RACOONIX_NOME=$nome" >> .env
  dc up -d --force-recreate caddy app mdns
  ok "$(t "Ora Racoonix e' raggiungibile anche come" "Racoonix can now also be reached at") https://$nome"
}

aiuto() {
  if [[ "$LINGUA" == en ]]; then
    cat << EOF
${GRASSETTO}Racoonix${RESET} - management

  ./racoonix.sh install [IP]         install (then set it up from the browser)
  ./racoonix.sh link                 show the setup link again
  ./racoonix.sh start | stop         start or stop Racoonix
  ./racoonix.sh status               running services, address and database version
  ./racoonix.sh logs [service]       live logs (default: app)
  ./racoonix.sh update               backup, download the new version and apply it
  ./racoonix.sh backup               database backup in $BACKUP_DIR/
  ./racoonix.sh auto-backup          backup every night at 02:30
  ./racoonix.sh restore FILE         restore a backup (asks for confirmation)
  ./racoonix.sh certificate          export the certificate for devices
  ./racoonix.sh name NAME            change the network name (default: racoonix.local)
EOF
  else
    cat << EOF
${GRASSETTO}Racoonix${RESET} - gestione

  ./racoonix.sh installa [IP]        installa (poi si configura dal browser)
  ./racoonix.sh link                 mostra di nuovo il link della configurazione
  ./racoonix.sh avvia | ferma        avvia o ferma Racoonix
  ./racoonix.sh stato                servizi attivi, indirizzo e versione del database
  ./racoonix.sh log [servizio]       log in tempo reale (predefinito: app)
  ./racoonix.sh aggiorna             backup, scarica la nuova versione e la applica
  ./racoonix.sh backup               backup del database in $BACKUP_DIR/
  ./racoonix.sh backup-automatico    backup ogni notte alle 02:30
  ./racoonix.sh ripristina FILE      ripristina un backup (chiede conferma)
  ./racoonix.sh certificato          esporta il certificato per i dispositivi
  ./racoonix.sh nome NOME            cambia il nome in rete (predefinito: racoonix.local)
EOF
  fi
}

case "${1:-aiuto}" in
  installa|install)                 installa "${2:-}" "${3:-}" ;;
  avvia|start)                      controlla_installato; importa_segreti_vecchi; dc up -d; attendi_avvio; info "$(t "Indirizzo:" "Address:") https://$(indirizzo)" ;;
  ferma|stop)                       controlla_installato; dc stop; ok "$(t "Racoonix fermato" "Racoonix stopped")" ;;
  stato|status)                     stato ;;
  log|logs)                         dc logs -f --tail 100 "${2:-app}" ;;
  aggiorna|update)                  aggiorna ;;
  backup)                           backup ;;
  backup-automatico|auto-backup)    backup_automatico ;;
  ripristina|restore)               ripristina "${2:-}" ;;
  certificato|certificate)          controlla_installato; esporta_certificato ;;
  nome|name)                        controlla_installato; cambia_nome "${2:-}" ;;
  link)                             controlla_installato; mostra_link ;;
  aiuto|help|-h|--help)             aiuto ;;
  *)                                aiuto; exit 1 ;;
esac
