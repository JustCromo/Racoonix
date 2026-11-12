# Security / Sicurezza

<p align="center">🇬🇧 <a href="#english">English</a> · 🇮🇹 <a href="#italiano">Italiano</a></p>

---

## English

### Supported versions

| Version | Supported |
|---|---|
| 1.0.x (latest) | ✅ |
| Earlier development versions | ❌ |

Security fixes are released as a new patch version (for example 1.0.2). To get them, run `./racoonix.sh update` on the server.

### Reporting a vulnerability

**Please don't open a public issue.** Use GitHub's private reporting instead: go to the **Security** tab of this repository and choose **Report a vulnerability**. Only the maintainer can see the report.

It helps to include:
- what you found and where (page, component, version);
- the steps to reproduce it;
- what an attacker could do with it.

Racoonix is maintained by a single person, so responses are best-effort: I'll aim to acknowledge reports within a week and to keep you updated until a fix is released. If you wish, you'll be credited in the release notes.

Please test only on your own installation, and don't access or modify data that isn't yours.

### How Racoonix is designed

Racoonix was designed starting from one question: **what happens if something goes wrong?** Every defence is meant to keep working even when the one before it has given way.

**Your data stays in the shop.** The only external connection is optional: when a new product is booked in, Racoonix can ask Open Food Facts for its name and brand, sending only the barcode (it can be turned off in Settings). No cloud, nothing downloaded from the internet while you use it: fonts, icons and libraries all live on the shop's server. Racoonix is meant to be reachable only from the local network.

**Always-encrypted connection.** Every page travels over HTTPS, even inside the shop. Racoonix creates its own certificate; each device installs it once and can check its fingerprint. After the first visit, browsers refuse to connect without encryption.

**Protected initial setup.** The setup page only opens with a one-time code shown on the server. The code expires, is stored only as a hash, and the page switches off for good once setup is complete: nobody on the network can set up Racoonix in your place.

**Who gets in, and from where.**
- No open sign-up: only the owner creates accounts, and everyone chooses their own password on first sign-in.
- Passwords are protected with an algorithm designed to make guessing extremely slow, even if the database were stolen.
- Each person can only sign in from devices the owner has approved. A stolen password alone isn't enough, and a revoked device is blocked for every account.
- New staff can sign in for the first time with a QR code the owner shows them in person: it works once, for 30 minutes, it's stored only as a hash, and the phone that scans it becomes their approved device. Every device, including blocked ones, is listed on the Devices page.
- A failed sign-in always gets the same response, whatever the reason: an attacker can't tell whether a password was right or a user exists.
- Repeated failures lock the account for a while and slow down requests.
- The owner's functions only work from authorised computers.
- Sessions expire after 30 minutes without real use (automatic page updates don't count), and signing out really ends them on the server too.

**Everyone sees only their own.** Roles are checked by the server on every request; the interface contains no logic, so there's nothing to bypass in the browser.

**Defence in depth.** If someone took control of the application anyway:
- the application talks to the database with the fewest permissions possible: it can't delete tables, create users or change the structure;
- the activity log can't be changed or deleted, not even by the application: the database itself prevents it;
- each component runs isolated, with only the permissions it needs and a read-only disk; the database isn't reachable from the network;
- passwords and keys are generated at random on first start, each component sees only what it needs, and none of them appear in the code;
- on every update, the images are rebuilt with the latest operating system security fixes.

**Protection on every page.** Protection against forged requests, cookies that scripts can't read and that are tied to Racoonix alone, a strict content policy, protection against embedding in other sites, no pages kept in the browser cache, strict checks on every input and every scanned code, and spreadsheet exports protected against malicious formulas.

**Everything is recorded.** Sign-ins, failed attempts, approvals and every important action go into the activity log, with a 24-hour security summary that flags password-guessing attempts.

**Tested, not just claimed.** The code, its libraries, the Docker images, the repository history and the web interface are checked with automated tools, alongside automated tests and manual testing. Vulnerabilities found during development were fixed and verified.

---

## Italiano

### Versioni supportate

| Versione | Supportata |
|---|---|
| 1.0.x (ultima) | ✅ |
| Versioni di sviluppo precedenti | ❌ |

Le correzioni di sicurezza escono come nuova versione (per esempio 1.0.2). Per riceverle, sul server: `./racoonix.sh aggiorna`.

### Segnalare una vulnerabilità

**Per favore non aprire una issue pubblica.** Usa la segnalazione privata di GitHub: apri la scheda **Security** di questo repository e scegli **Report a vulnerability**. La segnalazione la vede solo chi mantiene il progetto.

È utile indicare:
- cosa hai trovato e dove (pagina, componente, versione);
- i passaggi per riprodurlo;
- cosa potrebbe farci un attaccante.

Racoonix è mantenuto da una sola persona, quindi le risposte arrivano appena possibile: l'obiettivo è confermare la ricezione entro una settimana e tenerti aggiornato fino alla correzione. Se vuoi, verrai ringraziato nelle note della versione.

Fai le prove solo sulla tua installazione, e non accedere né modificare dati che non sono tuoi.

### Come è progettato Racoonix

Racoonix è stato progettato partendo da una domanda: **cosa succede se qualcosa va storto?** Ogni difesa è pensata per funzionare anche quando quella prima ha ceduto.

**I dati restano in negozio.** L'unico collegamento esterno è facoltativo: al carico di un prodotto nuovo, Racoonix può chiedere nome e marca a Open Food Facts inviando solo il codice a barre (si spegne da Impostazioni). Niente cloud, niente risorse scaricate da internet mentre lo usi: caratteri, icone e librerie stanno sul server del negozio. Racoonix è pensato per essere raggiungibile solo dalla rete locale.

**Connessione sempre cifrata.** Ogni pagina viaggia su HTTPS, anche dentro il negozio. Racoonix crea il proprio certificato; ogni dispositivo lo installa una volta e può verificarne l'impronta. Dopo il primo accesso, il browser rifiuta di collegarsi senza cifratura.

**Configurazione iniziale protetta.** La pagina di configurazione si apre solo con un codice monouso che compare sul server. Il codice scade, viene salvato solo come impronta, e a configurazione finita la pagina si spegne per sempre: nessuno, nella rete, può configurare Racoonix al posto tuo.

**Chi entra, e da dove.**
- Niente registrazione libera: gli account li crea solo il titolare, e al primo accesso ognuno sceglie la sua password.
- Le password sono protette con un algoritmo pensato per rendere lentissimi i tentativi di indovinarle, anche se qualcuno rubasse il database.
- Ognuno entra solo dai dispositivi approvati dal titolare. Una password rubata, da sola, non basta, e un dispositivo revocato viene bloccato per qualunque account.
- Chi è nuovo può fare il primo accesso con un QR che il titolare gli mostra di persona: vale una volta sola, per 30 minuti, viene salvato solo come impronta, e il telefono che lo inquadra diventa il suo dispositivo approvato. Tutti i dispositivi, compresi quelli bloccati, sono nella pagina Dispositivi.
- Un accesso fallito riceve sempre la stessa risposta, qualunque sia il motivo: chi attacca non capisce se una password era giusta o se un utente esiste.
- Dopo una serie di errori l'account si blocca per un po', e le richieste ripetute vengono rallentate.
- Le funzioni del titolare funzionano solo dai computer autorizzati.
- Le sessioni scadono dopo 30 minuti senza un uso vero (gli aggiornamenti automatici delle pagine non contano), e l'uscita le chiude davvero, anche sul server.

**Ognuno vede solo il suo.** I ruoli li controlla il server a ogni richiesta; l'interfaccia non contiene logica, quindi nel browser non c'è niente da aggirare.

**Difesa in profondità.** Se qualcuno prendesse comunque il controllo dell'applicazione:
- l'applicazione parla al database con i permessi minimi indispensabili: non può cancellare tabelle, creare utenti o cambiare la struttura;
- il registro attività non si può modificare né cancellare, nemmeno dall'applicazione: lo impedisce il database stesso;
- ogni componente gira isolato, con i soli permessi necessari e il disco in sola lettura; il database non è raggiungibile dalla rete;
- password e chiavi vengono generate a caso al primo avvio, ogni componente vede solo quelle che gli servono, e nessuna compare nel codice;
- a ogni aggiornamento, le immagini vengono ricostruite con le ultime correzioni di sicurezza del sistema operativo.

**Le protezioni di ogni pagina.** Protezione dalle richieste contraffatte, cookie inaccessibili agli script e legati solo a Racoonix, una politica dei contenuti restrittiva, protezione dall'inserimento in altri siti, nessuna pagina nella cache del browser, controlli rigorosi su ogni dato inserito o letto da un codice a barre, ed esportazioni protette contro le formule malevole nei fogli di calcolo.

**Tutto resta registrato.** Accessi, tentativi falliti, approvazioni e ogni operazione importante finiscono nel registro attività, con un riepilogo di sicurezza delle ultime 24 ore che segnala i tentativi di indovinare una password.

**Verificato, non solo dichiarato.** Il codice, le librerie, le immagini Docker, la storia del repository e l'interfaccia web vengono controllati con strumenti automatici, insieme a test automatici e test manuali. Le vulnerabilità trovate durante lo sviluppo sono state corrette e verificate.
