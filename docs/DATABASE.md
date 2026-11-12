# Database

<p align="center">🇮🇹 <a href="#italiano">Italiano</a> · 🇬🇧 <a href="#english">English</a></p>

PostgreSQL 16. Lo schema nasce dai modelli in [`app/racoonix/models.py`](../app/racoonix/models.py) e viene applicato dalle migrazioni Alembic in [`app/migrations/versions`](../app/migrations/versions) a ogni avvio.
The schema comes from the models in `app/racoonix/models.py` and is applied by the Alembic migrations on every start.

```mermaid
erDiagram
    audit_log {
        integer id PK
        integer utente_id FK
        string azione
        text dettaglio
        string ip
        timestamp data_ora
    }
    categorie {
        integer id PK
        string nome
        boolean attiva
        boolean richiede_scadenza
        integer giorni_freschezza
        integer sconto1_giorni
        integer sconto1_perc
        integer sconto2_giorni
        integer sconto2_perc
    }
    codici_aggiuntivi {
        integer id PK
        integer prodotto_id FK
        string gtin
        string descrizione
    }
    dispositivi_accesso {
        integer id PK
        integer utente_id FK
        string token_hash
        string descrizione
        string nome
        string stato
        timestamp creato_il
        integer approvato_da FK
        timestamp approvato_il
        timestamp ultimo_uso
        string ultimo_ip
    }
    fornitori {
        integer id PK
        string ragione_sociale
        string partita_iva
        string telefono
        string email
        string giorni_ordine
        boolean attivo
    }
    impostazioni {
        string chiave PK
        string valore
        timestamp aggiornata_il
    }
    lotti {
        integer id PK
        integer prodotto_id FK
        string codice_lotto
        date data_scadenza
        integer qta_esposta
        integer qta_magazzino
        timestamp data_carico
        integer caricato_da FK
    }
    notifiche {
        integer id PK
        string tipo
        integer prodotto_id FK
        integer lotto_id FK
        integer utente_id FK
        string ruolo_destinatario
        string stato
        string nota
        timestamp creata_il
        integer chiusa_da FK
        timestamp chiusa_il
    }
    prodotti {
        integer id PK
        string gtin
        string codice_bilancia
        string nome
        string marca
        integer categoria_id FK
        integer sottocategoria_id FK
        integer fornitore_id FK
        string unita
        integer formato_pezzi
        integer formato_quantita
        string formato_unita
        integer prezzo_centesimi
        boolean in_esaurimento
        integer soglia_riordino
        timestamp ultima_conta_il
        integer giorni_preavviso
        integer sconto1_giorni
        integer sconto1_perc
        integer sconto2_giorni
        integer sconto2_perc
        string stato
        integer creato_da FK
        integer approvato_da FK
        timestamp creato_il
    }
    riordini {
        integer id PK
        integer prodotto_id FK
        integer quantita
        string stato
        string origine
        integer segnalato_da FK
        timestamp creato_il
        integer ordinato_da FK
        timestamp ordinato_il
        timestamp chiuso_il
    }
    ruoli {
        integer id PK
        string nome
    }
    scarti {
        integer id PK
        integer lotto_id FK
        integer quantita
        string motivo
        timestamp data
        integer utente_id FK
    }
    sconti {
        integer id PK
        integer lotto_id FK
        integer perc
        integer quantita
        string origine
        boolean attivo
        integer creato_da FK
        timestamp creato_il
        timestamp chiuso_il
    }
    sottocategorie {
        integer id PK
        integer categoria_id FK
        string nome
        boolean attiva
    }
    utenti {
        integer id PK
        string username
        string password_hash
        boolean attivo
        boolean eliminato
        boolean deve_cambiare_password
        integer tentativi_falliti
        timestamp bloccato_fino
        string tema
        string lingua
        string benvenuto_hash
        timestamp benvenuto_scade
        string token_sessione
        timestamp creato_il
    }
    utenti_ruoli {
        integer utente_id PK
        integer ruolo_id PK
    }
    categorie ||--o{ prodotti : "categoria_id"
    categorie ||--o{ sottocategorie : "categoria_id"
    fornitori ||--o{ prodotti : "fornitore_id"
    lotti ||--o{ notifiche : "lotto_id"
    lotti ||--o{ scarti : "lotto_id"
    lotti ||--o{ sconti : "lotto_id"
    prodotti ||--o{ codici_aggiuntivi : "prodotto_id"
    prodotti ||--o{ lotti : "prodotto_id"
    prodotti ||--o{ notifiche : "prodotto_id"
    prodotti ||--o{ riordini : "prodotto_id"
    ruoli ||--o{ utenti_ruoli : "ruolo_id"
    sottocategorie ||--o{ prodotti : "sottocategoria_id"
    utenti ||--o{ audit_log : "utente_id"
    utenti ||--o{ dispositivi_accesso : "approvato_da"
    utenti ||--o{ dispositivi_accesso : "utente_id"
    utenti ||--o{ lotti : "caricato_da"
    utenti ||--o{ notifiche : "chiusa_da"
    utenti ||--o{ notifiche : "utente_id"
    utenti ||--o{ prodotti : "approvato_da"
    utenti ||--o{ prodotti : "creato_da"
    utenti ||--o{ riordini : "ordinato_da"
    utenti ||--o{ riordini : "segnalato_da"
    utenti ||--o{ scarti : "utente_id"
    utenti ||--o{ sconti : "creato_da"
    utenti ||--o{ utenti_ruoli : "utente_id"
```

## Italiano

| Tabella | A cosa serve |
|---|---|
| `audit_log` | Registro attività: chi, cosa, quando, da dove. L'app può solo aggiungere righe. |
| `categorie` | Categorie di prodotti, con le regole di scadenza, freschezza e sconto suggerito. |
| `codici_aggiuntivi` | Altri codici a barre dello stesso prodotto (per esempio una nuova confezione). |
| `dispositivi_accesso` | Dispositivi da cui ogni persona può entrare, approvati dall'admin (solo l'impronta del token). |
| `fornitori` | Fornitori, con partita IVA e giorni d'ordine. |
| `impostazioni` | Impostazioni del negozio (nome, lingua, paese, fuso, computer admin, Open Food Facts), codice di configurazione e data dell'ultimo backup. |
| `lotti` | Ogni arrivo di merce: scadenza, quantità sullo scaffale e in magazzino. |
| `notifiche` | Le cose da fare, per ruolo: scadenze, scaffali, approvazioni, ordini. |
| `prodotti` | Il catalogo: codici, formato, prezzo, fornitore, soglie e stato. |
| `riordini` | Lista d'ordine: da ordinare, ordinato, arrivato o annullato. |
| `ruoli` | admin, magazziniere, dipendente. |
| `scarti` | Merce buttata, con il motivo. |
| `sconti` | Sconti applicati ai lotti (manuali o programmati). |
| `sottocategorie` | Sottocategorie di ogni categoria. |
| `utenti` | Account: solo l'hash Argon2 della password, ruoli, blocchi, lingua, tema e impronta del codice QR di benvenuto. |
| `utenti_ruoli` | Quali ruoli ha ogni utente (anche più di uno). |

**Regole nel database**, non solo nell'app: vincoli `CHECK` su stati, quantità, partita IVA e codici; indici unici per evitare doppioni (per esempio un solo riordino aperto per prodotto); l'utente con cui gira l'app non può modificare né cancellare `audit_log`, né cambiare la struttura delle tabelle.

**Quantità in interi**: i prezzi sono in centesimi, i prodotti a peso in grammi, così non ci sono errori di arrotondamento.

## English

| Table | Purpose |
|---|---|
| `audit_log` | Activity log: who, what, when, from where. The app can only add rows. |
| `categorie` | Product categories, with expiry, freshness and suggested-discount rules. |
| `codici_aggiuntivi` | Other barcodes for the same product (for example new packaging). |
| `dispositivi_accesso` | Devices each person can sign in from, approved by the admin (token hash only). |
| `fornitori` | Suppliers, with VAT number and ordering days. |
| `impostazioni` | Shop settings (name, language, country, time zone, admin computers, Open Food Facts), setup code and last backup date. |
| `lotti` | Each delivery batch: expiry, quantity on the shelf and in the stockroom. |
| `notifiche` | To-do items by role: expiries, shelves, approvals, orders. |
| `prodotti` | The catalogue: codes, size, price, supplier, thresholds and status. |
| `riordini` | Order list: to order, ordered, arrived or cancelled. |
| `ruoli` | admin, stockroom worker, shop assistant. |
| `scarti` | Discarded stock, with the reason. |
| `sconti` | Discounts applied to batches (manual or scheduled). |
| `sottocategorie` | Subcategories of each category. |
| `utenti` | Accounts: Argon2 password hash only, roles, lockouts, language, theme and the welcome QR code hash. |
| `utenti_ruoli` | Which roles each user has (possibly more than one). |

**Rules enforced by the database**, not just by the app: `CHECK` constraints on statuses, quantities, VAT numbers and codes; unique indexes to prevent duplicates (for example one open reorder per product); the database user the app runs as can't modify or delete `audit_log`, nor change the table structure.

**Integer quantities**: prices are in cents and weighed products in grams, so there are no rounding errors.
