#!/usr/bin/env bash
# Racoonix - installazione e gestione con un solo comando.
set -Eeuo pipefail
cd "$(dirname "$(readlink -f "$0")")"

VERDE=$'\e[32m'; GIALLO=$'\e[33m'; ROSSO=$'\e[31m'; GRASSETTO=$'\e[1m'; RESET=$'\e[0m'
BACKUP_DIR="backup"
BACKUP_DA_TENERE="${BACKUP_DA_TENERE:-14}"

ok()      { echo "${VERDE}✔${RESET} $*"; }
info()    { echo "${GRASSETTO}›${RESET} $*"; }
avviso()  { echo "${GIALLO}!${RESET} $*"; }
errore()  { echo "${ROSSO}✘ $*${RESET}" >&2; exit 1; }
chiedi()  { local r; read -rp "$1${2:+ [$2]}: " r; echo "${r:-${2:-}}"; }
conferma(){ local r; read -rp "$1 [s/N]: " r; [[ "$r" =~ ^[sS]$ ]]; }
dc()      { docker compose ${RACOONIX_PROGETTO:+-p "$RACOONIX_PROGETTO"} "$@"; }
valida_ip() { [[ "$1" =~ ^([0-9]{1,3}\.){3}[0-9]{1,3}$ ]]; }

ip_locale() {
  ip route get 1.1.1.1 2>/dev/null | awk '{for(i=1;i<=NF;i++) if($i=="src"){print $(i+1); exit}}' \
    || hostname -I | awk '{print $1}'
}

controlla_requisiti() {
  command -v docker >/dev/null || errore "Docker non trovato. Su Ubuntu: sudo apt install docker.io docker-compose-v2"
  docker compose version >/dev/null 2>&1 || errore "Manca Docker Compose v2. Su Ubuntu: sudo apt install docker-compose-v2"
  docker info >/dev/null 2>&1 || errore "Docker non risponde: il servizio e' avviato? Il tuo utente e' nel gruppo docker?"
  command -v openssl >/dev/null || errore "Manca openssl. Su Ubuntu: sudo apt install openssl"
  ok "Requisiti presenti"
}

controlla_installato() {
  [[ -s secrets/db_password && -f .env ]] || errore "Racoonix non e' installato qui. Usa: ./racoonix.sh installa"
}

attendi_avvio() {
  info "Attendo l'avvio di Racoonix..."
  for _ in $(seq 1 60); do
    if dc exec -T app python -c "import urllib.request; urllib.request.urlopen('http://localhost:8000/health', timeout=2)" >/dev/null 2>&1; then
      ok "Racoonix e' attivo"
      return 0
    fi
    sleep 2
  done
  errore "Racoonix non risponde. Controlla i log con: ./racoonix.sh log"
}

esporta_certificato() {
  for _ in $(seq 1 30); do
    dc cp caddy:/data/caddy/pki/authorities/local/root.crt ./racoonix-root.crt >/dev/null 2>&1 && break
    sleep 1
  done
  if [[ ! -s racoonix-root.crt ]]; then
    avviso "Certificato non ancora pronto: riprova tra poco con ./racoonix.sh certificato"
    return 0
  fi
  ok "Certificato esportato in racoonix-root.crt"
  echo "  Impronta SHA-256 (confrontala sul dispositivo dopo l'installazione):"
  echo "  $(openssl x509 -in racoonix-root.crt -noout -fingerprint -sha256 | cut -d= -f2)"
}

indirizzo() { grep '^RACOONIX_SNI=' .env | cut -d= -f2; }

# Annuncia il nome (es. racoonix.local) nella rete con mDNS, come fanno le stampanti di rete.
# Non rinomina il computer: un piccolo servizio di sistema pubblica il nome con l'IP del server.
configura_nome() {
  local nome="$1" ip="$2"
  [[ "$nome" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] && valida_ip "$ip" || { avviso "Nome o IP non validi"; return 1; }
  if [[ "$nome" != *.local ]]; then
    info "$nome non e' un nome .local: va registrato nel DNS del router, che deve puntare a $ip"
    return 0
  fi
  command -v systemctl >/dev/null || { avviso "Serve systemd per annunciare $nome"; return 1; }
  info "Annuncio $nome nella rete del negozio: servono i permessi di amministratore (sudo)"
  if ! command -v avahi-publish >/dev/null; then
    if command -v apt-get >/dev/null; then sudo apt-get install -y -qq avahi-daemon avahi-utils >/dev/null
    elif command -v pacman >/dev/null; then sudo pacman -S --needed --noconfirm avahi >/dev/null
    elif command -v dnf >/dev/null; then sudo dnf install -y -q avahi avahi-tools
    else avviso "Installa avahi con il gestore pacchetti del sistema, poi: ./racoonix.sh nome"; return 1
    fi
  fi
  sudo systemctl enable --now avahi-daemon >/dev/null 2>&1 || { avviso "avahi-daemon non si avvia"; return 1; }

  if [[ "$(hostname)" == "${nome%.local}" ]]; then
    # Il computer si chiama gia' cosi': avahi annuncia il nome da solo
    sudo systemctl disable --now racoonix-nome >/dev/null 2>&1 || true
  else
    sudo tee /etc/systemd/system/racoonix-nome.service >/dev/null << UNIT
[Unit]
Description=Racoonix: annuncia ${nome} nella rete locale (mDNS)
After=avahi-daemon.service network-online.target
Requires=avahi-daemon.service
Wants=network-online.target

[Service]
ExecStart=$(command -v avahi-publish) -a -R ${nome} ${ip}
Restart=always
RestartSec=10
DynamicUser=yes
NoNewPrivileges=yes
ProtectSystem=strict
ProtectHome=yes
PrivateTmp=yes

[Install]
WantedBy=multi-user.target
UNIT
    sudo systemctl daemon-reload
    sudo systemctl enable racoonix-nome >/dev/null 2>&1
    sudo systemctl restart racoonix-nome
  fi

  # Se c'e' un firewall attivo, lascio passare mDNS (porta UDP 5353)
  if command -v ufw >/dev/null && sudo ufw status 2>/dev/null | grep -q "Status: active"; then
    sudo ufw allow 5353/udp comment "mDNS Racoonix" >/dev/null
  elif command -v firewall-cmd >/dev/null && sudo firewall-cmd --state >/dev/null 2>&1; then
    sudo firewall-cmd --permanent --add-service=mdns >/dev/null && sudo firewall-cmd --reload >/dev/null
  fi

  sleep 2
  if [[ "$(hostname)" == "${nome%.local}" ]] || systemctl is-active --quiet racoonix-nome; then
    ok "Racoonix e' raggiungibile anche come https://$nome"
  else
    avviso "Il nome non si e' attivato (forse e' gia' usato da un altro dispositivo). Controlla: systemctl status racoonix-nome"
    return 1
  fi
}

installa() {
  [[ -s secrets/db_password ]] && errore "Racoonix risulta gia' installato qui. Per aggiornarlo: ./racoonix.sh aggiorna"
  controlla_requisiti
  echo; echo "${GRASSETTO}Installazione di Racoonix${RESET}"; echo

  local negozio ip admin_ip reti suggerito nome
  negozio=$(chiedi "Nome del negozio" "Il mio negozio")
  [[ "$negozio" =~ ^[[:alnum:][:space:]\'.,\&-]{2,60}$ ]] || errore "Nome non valido: 2-60 caratteri tra lettere, numeri, spazi e . , ' & -"
  ip=$(chiedi "IP di questo server nella rete del negozio" "$(ip_locale)")
  valida_ip "$ip" || errore "IP non valido"
  suggerito="${SSH_CLIENT:-}"; suggerito="${suggerito%% *}"
  [[ -z "$suggerito" ]] && suggerito="$ip"
  info "L'area admin sara' raggiungibile solo dal computer dell'amministratore."
  admin_ip=$(chiedi "IP del computer dell'amministratore" "$suggerito")
  nome=$(chiedi "Nome di Racoonix nella rete del negozio" "racoonix.local")
  [[ "$nome" =~ ^[a-z0-9-]+(\.[a-z0-9-]+)+$ ]] || errore "Nome non valido: lettere minuscole, numeri e trattini, per esempio racoonix.local"
  valida_ip "$admin_ip" || errore "IP non valido"
  reti="$admin_ip/32"
  # Se l'admin usa il browser sul server stesso, le richieste arrivano dalla rete interna di Docker.
  [[ "$admin_ip" == "$ip" ]] && reti="$reti,172.16.0.0/12"

  mkdir -p secrets && chmod 700 secrets
  openssl rand -base64 32 | tr -d '\n' > secrets/db_password
  openssl rand -hex 32 | tr -d '\n' > secrets/flask_secret
  openssl rand -hex 32 | tr -d '\n' > secrets/db_app_password
  : > secrets/admin_credentials
  chmod 644 secrets/*
  ok "Segreti generati (password del database e chiavi interne)"

  cat > .env << EOF
MARKET_NAME=$negozio
RACOONIX_HOST=localhost, $ip, $nome
RACOONIX_SNI=$ip
RACOONIX_NOME=$nome
ADMIN_IP_CONSENTITI=$reti
EOF
  chmod 600 .env
  ok "Configurazione salvata in .env"
  configura_nome "$nome" "$ip" || avviso "Racoonix resta raggiungibile dall'IP. Per riprovare con il nome: ./racoonix.sh nome"

  info "Preparo l'applicazione (la prima volta puo' richiedere qualche minuto)..."
  dc build app
  echo; info "Scegli le credenziali dell'amministratore:"
  until dc run --rm --no-deps -v ./secrets:/out app python -m racoonix.crea_admin; do
    avviso "Riprova."
  done

  dc up -d
  attendi_avvio
  : > secrets/admin_credentials
  ok "Impronta della password admin rimossa dal disco: non serve piu'"
  esporta_certificato

  echo
  echo "${GRASSETTO}Racoonix e' pronto.${RESET}"
  echo "  Apri:          https://$ip"
  echo "  Da questo PC:  https://localhost"
  echo
  echo "  Prima di aprirlo dagli altri dispositivi, installa su ognuno il certificato racoonix-root.crt"
  echo "  come 'certificato CA', e controlla che l'impronta coincida con quella mostrata sopra."
  echo "  Backup automatici ogni notte: ./racoonix.sh backup-automatico"
}

backup() {
  controlla_installato
  mkdir -p "$BACKUP_DIR" && chmod 700 "$BACKUP_DIR"
  local file="$BACKUP_DIR/racoonix-$(date +%Y%m%d-%H%M%S).dump"
  if ! dc exec -T db pg_dump -U racoonix -d racoonix --format=custom > "$file" || [[ ! -s "$file" ]]; then
    rm -f "$file"
    errore "Backup non riuscito"
  fi
  chmod 600 "$file"
  ok "Backup salvato: $file ($(du -h "$file" | cut -f1))"
  ls -1t "$BACKUP_DIR"/racoonix-*.dump | tail -n +$((BACKUP_DA_TENERE + 1)) | xargs -r rm -f
}

backup_automatico() {
  controlla_installato
  command -v crontab >/dev/null || errore "crontab non disponibile su questo sistema"
  local riga="30 2 * * * cd '$(pwd)' && ./racoonix.sh backup >> $BACKUP_DIR/backup.log 2>&1"
  { { crontab -l 2>/dev/null || true; } | grep -v "racoonix.sh backup" || true; echo "$riga"; } | crontab -
  ok "Backup automatico ogni notte alle 02:30 (vengono tenuti gli ultimi $BACKUP_DA_TENERE)"
}

ripristina() {
  controlla_installato
  local file="${1:-}" copia r
  [[ -f "$file" ]] || errore "Indica il file da ripristinare, es.: ./racoonix.sh ripristina backup/racoonix-20261109-023000.dump"
  avviso "Il database attuale verra' SOSTITUITO con: $file"
  read -rp "Scrivi RIPRISTINA per confermare: " r
  [[ "$r" == "RIPRISTINA" ]] || errore "Annullato: nessuna modifica"
  copia=$(mktemp)
  cp "$file" "$copia"
  info "Prima salvo lo stato attuale, per sicurezza"
  backup
  dc stop app scheduler
  dc exec -T db dropdb -U racoonix --if-exists racoonix
  dc exec -T db createdb -U racoonix -O racoonix racoonix
  dc exec -T db pg_restore -U racoonix -d racoonix --no-owner < "$copia"
  rm -f "$copia"
  dc up -d
  attendi_avvio
  ok "Ripristino completato"
}

aggiorna() {
  controlla_installato
  info "Backup di sicurezza prima dell'aggiornamento"
  backup
  if [[ -d .git ]]; then
    git diff --quiet && git diff --cached --quiet || errore "Ci sono modifiche locali al codice: salvale o annullale prima di aggiornare"
    git pull --ff-only
  fi
  info "Scarico le immagini aggiornate (correzioni di sicurezza di Caddy e PostgreSQL)"
  dc pull db caddy
  dc build --pull
  dc up -d
  attendi_avvio
  ok "Aggiornato: le modifiche al database sono state applicate in automatico"
}

stato() {
  controlla_installato
  dc ps
  echo
  info "Indirizzo: https://$(indirizzo)"
  local versione
  versione=$(dc exec -T app flask --app racoonix:create_app db current 2>/dev/null | tail -1 || true)
  info "Versione del database: ${versione:-non disponibile}"
}

aiuto() {
  cat << EOF
${GRASSETTO}Racoonix${RESET} - gestione

  ./racoonix.sh installa             prima installazione guidata
  ./racoonix.sh avvia | ferma        avvia o ferma Racoonix
  ./racoonix.sh stato                servizi attivi, indirizzo e versione del database
  ./racoonix.sh log [servizio]       log in tempo reale (predefinito: app)
  ./racoonix.sh aggiorna             backup, scarica la nuova versione e la applica
  ./racoonix.sh backup               backup del database in $BACKUP_DIR/
  ./racoonix.sh backup-automatico    backup ogni notte alle 02:30
  ./racoonix.sh ripristina FILE      ripristina un backup (chiede conferma)
  ./racoonix.sh certificato          esporta il certificato per i dispositivi
  ./racoonix.sh nome                 annuncia di nuovo il nome (es. racoonix.local) nella rete
EOF
}

case "${1:-aiuto}" in
  installa)          installa ;;
  avvia)             controlla_installato; dc up -d; attendi_avvio; info "Indirizzo: https://$(indirizzo)" ;;
  ferma)             controlla_installato; dc stop; ok "Racoonix fermato" ;;
  stato)             stato ;;
  log)               dc logs -f --tail 100 "${2:-app}" ;;
  aggiorna)          aggiorna ;;
  backup)            backup ;;
  backup-automatico) backup_automatico ;;
  ripristina)        ripristina "${2:-}" ;;
  certificato)       controlla_installato; esporta_certificato ;;
  nome)              controlla_installato; configura_nome "$(grep '^RACOONIX_NOME=' .env | cut -d= -f2)" "$(indirizzo)" ;;
  aiuto|-h|--help)   aiuto ;;
  *)                 aiuto; exit 1 ;;
esac
