<p align="center">
  <img src="app/racoonix/static/img/logo.png" alt="Logo di Racoonix" width="160">
</p>

<h1 align="center">Racoonix</h1>

<p align="center">
  <strong>Il gestionale per il piccolo negozio di alimentari che non vuole più buttare merce, né restare senza.</strong><br>
  Scadenze, magazzino e ordini ai fornitori, dal telefono. Senza abbonamenti, senza cloud, senza cassa da collegare.
</p>

<p align="center">🇮🇹 Italiano · <a href="README.en.md">🇬🇧 English</a></p>

---

## In breve

Racoonix è un'applicazione web che gira su un piccolo computer dentro il negozio (anche un Raspberry Pi) e si usa dal browser di qualunque telefono o PC. Tiene traccia di **ogni lotto di merce e della sua scadenza**, dice a ciascuno **cosa c'è da fare oggi** e prepara **gli ordini da mandare ai fornitori**.

Non serve installare app, non serve una cassa compatibile e i dati **non escono mai dal negozio**.

## Ti serve Racoonix?

Probabilmente sì, se ti riconosci in almeno una di queste situazioni:

- 🗑️ **Butti prodotti scaduti** perché nessuno si è accorto in tempo che stavano per scadere.
- 📒 **Le mancanze le segni su un quaderno** vicino alla cassa (quando ti ricordi di farlo).
- 📞 **Ti accorgi di dover ordinare quando lo scaffale è già vuoto**, o ti dimentichi il giorno in cui passa l'agente.
- 🔍 **Per sapere quanta merce hai in magazzino devi andare a contarla.**
- 🧾 **Non sai quanto ti costano gli sprechi**, né quali prodotti butti più spesso.
- 👥 **Più persone lavorano in negozio** e le informazioni si perdono tra un turno e l'altro.

Probabilmente **no**, se hai già un gestionale collegato alla cassa che gestisce lotti e scadenze, o se vendi solo prodotti che non scadono.

## Che buchi tappa

| Il problema di oggi | Come lo risolve Racoonix |
|---|---|
| Le scadenze si scoprono troppo tardi | Ogni lotto viene registrato all'arrivo con la sua scadenza. Racoonix avvisa **in anticipo**, e il giorno della scadenza chiede di toglierlo. |
| Si butta merce che si poteva vendere | Propone **sconti automatici** quando un lotto si avvicina alla scadenza, e ricorda di mettere il bollino. |
| Le mancanze si dimenticano | Il dipendente tocca **"Sta finendo"** sul telefono: se c'è merce in magazzino parte il compito di riempire lo scaffale, altrimenti il prodotto finisce **nella lista d'ordine**. |
| Gli ordini si fanno a memoria | Una lista **divisa per fornitore**, con i giorni d'ordine di ciascuno e il testo dell'ordine pronto da inviare. Quando la merce arriva, l'ordine si chiude da solo. |
| Non si sa cosa c'è in magazzino | Il magazzino lo toccano solo i dipendenti, e ogni movimento viene registrato: il numero che vedi **è quello vero**. |
| Si mette davanti la merce sbagliata | Quando si riempie lo scaffale, Racoonix indica **quale lotto mettere davanti** (quello che scade prima). |
| Gli sprechi sono invisibili | La dashboard mostra **quanto vale la merce buttata** e **quali prodotti** butti più spesso. |
| "Chi ha toccato questo?" | Ogni operazione resta nel **registro attività**: chi, cosa, quando. |

## Come funziona, in una giornata

**👤 Il dipendente** apre Racoonix sul telefono e trova le sue **cose da fare**: un lotto di yogurt da controllare perché scade dopodomani, un bollino sconto da applicare. Se nota uno scaffale quasi vuoto, inquadra il prodotto e tocca **"Sta finendo"**. Tre secondi.

**📦 Il magazziniere** riceve la merce: inquadra il codice a barre con la fotocamera (o con il lettore USB) e Racoonix riconosce il prodotto, il lotto e la scadenza, quando sono stampati nel codice. Poi trova il compito **"Riempi lo scaffale"**, con l'indicazione del lotto da mettere davanti.

**🏪 Il titolare** apre la **dashboard**: lotti in scadenza nei prossimi giorni, valore degli scarti, prodotti più buttati, cose in sospeso. Il giorno in cui passa l'agente apre gli **Ordini**: la lista è già pronta, divisa per fornitore. Approva i prodotti nuovi arrivati, decide gli sconti, gestisce chi può accedere.

> **Perché senza cassa?** Racoonix è pensato per i negozi che non hanno (o non vogliono collegare) una cassa. Senza cassa nessun programma può sapere quanti pezzi hanno comprato i clienti: per questo Racoonix **non inventa numeri**. Mostra il magazzino come un numero certo e lo scaffale come l'elenco dei lotti presenti, e si affida a chi lavora in negozio per le segnalazioni.

## Cosa sa fare

- **Lettura dei codici**: EAN-13 ed EAN-8, UPC, codici dei libri e delle riviste, GS1 DataMatrix e QR GS1 Digital Link (con lotto e scadenza), etichette dei prodotti a peso.
- **Lotti e scadenze**, con rotazione automatica: si vende prima quello che scade prima.
- **Cose da fare** per ruolo, aggiornate in tempo reale.
- **Sconti** manuali su un lotto, o programmati a due fasce in base ai giorni che mancano alla scadenza.
- **Ordini ai fornitori** con giorni d'ordine, soglie di riordino e testo pronto da inviare.
- **Conteggio del magazzino**, con registrazione automatica delle differenze.
- **Dashboard** con scadenze, sprechi e valore del magazzino.
- **Utenti e ruoli**: titolare (admin), magazziniere e dipendente, anche combinati.
- **Tema chiaro e scuro**, interfaccia pensata prima di tutto per il telefono.

## Installazione rapida

Ti serve un computer Linux sempre acceso nel negozio, con un indirizzo fisso nella rete locale (va benissimo un Raspberry Pi 4 o 5), con **Docker**, **git** e **openssl**.

```bash
git clone https://github.com/JustCromo/Racoonix.git
cd Racoonix
./racoonix.sh installa
```

L'installatore fa **quattro domande** (nome del negozio, indirizzo del server, computer da cui amministrerai, nome di Racoonix nella rete), prepara tutto il resto da solo e avvia Racoonix. Poi:

1. dal tuo computer apri `https://racoonix.local` (oppure l'indirizzo IP del server) ed entra come amministratore;
2. vai su **Collega dispositivi** e segui le istruzioni per far riconoscere Racoonix a telefoni e PC (una volta sola per dispositivo);
3. crea gli account di chi lavora con te da **Utenti**. Al primo accesso ognuno sceglie la sua password, e tu approvi il suo telefono.

Per il resto basta un comando:

| Comando | A cosa serve |
|---|---|
| `./racoonix.sh avvia` / `ferma` | Accendere o spegnere Racoonix |
| `./racoonix.sh stato` | Controllare che tutto funzioni |
| `./racoonix.sh backup-automatico` | Attivare il backup ogni notte |
| `./racoonix.sh backup` / `ripristina` | Fare un backup subito, o tornare a uno precedente |
| `./racoonix.sh aggiorna` | Passare all'ultima versione (prima fa un backup da solo) |
| `./racoonix.sh nome` | Annunciare di nuovo il nome `racoonix.local` nella rete (ad esempio se è cambiato l'IP del server) |

### Come si raggiunge Racoonix

Racoonix ha **due indirizzi**, e funzionano entrambi:

- **un nome facile da ricordare**, `https://racoonix.local`. Racoonix lo annuncia da solo nella rete del negozio, come fanno le stampanti di rete: l'installatore lo configura in automatico, senza toccare niente sul router;
- **l'indirizzo IP del server**, per esempio `https://192.168.1.50`, che funziona sempre e ovunque.

| Dispositivo | Indirizzo da usare |
|---|---|
| PC Windows, Mac, iPhone e iPad | `https://racoonix.local` |
| Computer Linux | `https://racoonix.local`, se il sistema sa trovare i nomi `.local` (molte distribuzioni lo fanno già, altre richiedono il pacchetto `nss-mdns`) |
| Telefoni e tablet Android | l'indirizzo IP: molti Android non cercano i nomi `.local` |

La pagina **Collega dispositivi** mostra sempre entrambi gli indirizzi, con un QR da inquadrare.

> **Un consiglio:** fai usare a ogni dispositivo sempre lo stesso indirizzo. Per il browser, il nome e l'IP sono due siti diversi: cambiando indirizzo, bisogna rifare l'accesso e far approvare di nuovo il dispositivo.

**Vuoi il nome anche sugli Android?** Se il router del negozio permette di dare un nome ai dispositivi della rete (molti router lo chiamano "DNS locale" o "nome host"), puoi associare un nome all'IP del server: quel nome funzionerà su qualunque dispositivo. In questo caso, durante l'installazione indica quel nome al posto di `racoonix.local`.

## Sicurezza

Un gestionale contiene dati che contano: le persone che lavorano in negozio, il valore della merce, le abitudini di acquisto. Racoonix è stato progettato partendo da una domanda: **cosa succede se qualcosa va storto?** Ogni difesa è pensata per funzionare anche quando quella prima ha ceduto.

### I dati restano in negozio

Racoonix non usa servizi esterni: niente cloud, niente account da creare altrove, niente risorse scaricate da internet mentre lo usi. Caratteri, icone e librerie sono tutti sul server del negozio. Racoonix è pensato per essere raggiungibile solo dalla rete locale.

### Connessione sempre cifrata

Ogni pagina viaggia su **HTTPS**, anche dentro il negozio. Racoonix crea il proprio certificato, e ogni dispositivo lo installa una volta sola, potendo verificare con un'impronta digitale che sia proprio quello del negozio. Dopo il primo accesso, il browser rifiuta di collegarsi senza cifratura.

### Chi entra, e da dove

- **Niente registrazione libera**: gli account li crea solo il titolare, e al primo accesso ognuno sceglie una password sua.
- **Password protette** con un algoritmo progettato apposta per rendere lentissimi i tentativi di indovinarle, anche nel caso in cui qualcuno rubasse il database.
- **Dispositivi approvati**: ogni persona può entrare solo dai dispositivi che il titolare ha approvato. Una password rubata, da sola, non basta. Un dispositivo revocato viene bloccato subito, per qualunque account.
- **Nessun indizio a chi tenta**: quando un accesso fallisce, la risposta è sempre la stessa, qualunque sia il motivo. Chi prova a indovinare non può capire se ha trovato la password giusta, né se un utente esiste. Il motivo vero lo vede solo il titolare.
- **Tentativi limitati**: dopo una serie di errori l'account si blocca per un po', e le richieste ripetute vengono rallentate.
- **Le funzioni del titolare** sono disponibili solo dai computer autorizzati, anche se qualcuno ne conoscesse la password.
- **Le sessioni scadono** dopo un periodo di inattività, e l'uscita le chiude davvero, anche sul server.

### Ognuno vede solo il suo

I ruoli sono controllati dal server a ogni richiesta, non dall'interfaccia: un dipendente non può raggiungere le pagine del titolare nemmeno scrivendone l'indirizzo. L'interfaccia stessa non contiene logica: tutte le decisioni le prende il server.

### Difesa in profondità

Se un giorno qualcuno riuscisse comunque a prendere il controllo dell'applicazione, Racoonix limita i danni:

- l'applicazione parla al database con **permessi ridotti al minimo**: può leggere e scrivere i dati del negozio, ma non può cancellare tabelle, creare utenti o cambiare la struttura del database;
- **il registro attività non si può modificare né cancellare**, nemmeno dall'applicazione: è il database stesso a impedirlo. Chi entra di nascosto non può cancellare le proprie tracce;
- ogni componente gira **isolato** nel suo container, con i soli permessi indispensabili e il disco in sola lettura; il database non è raggiungibile dalla rete del negozio;
- **password e chiavi** vengono generate a caso durante l'installazione e non compaiono mai nel codice.

### Le protezioni di ogni pagina

Protezione dalle richieste contraffatte su ogni modulo, cookie inaccessibili agli script e legati al solo sito di Racoonix, una politica dei contenuti che impedisce di eseguire codice estraneo, protezione dall'inserimento della pagina in altri siti, nessuna pagina salvata nella cache del browser (importante sui dispositivi condivisi), controllo rigoroso di ogni dato inserito o letto da un codice a barre, esportazioni protette contro le formule malevole nei fogli di calcolo.

### Tutto resta registrato

Accessi, tentativi falliti, approvazioni, carichi, correzioni, ordini: ogni operazione importante finisce nel **registro attività**, consultabile dal titolare. Un riepilogo di sicurezza delle ultime 24 ore segnala subito se qualcuno sta provando a indovinare una password.

### Verificato, non solo dichiarato

Il codice e le immagini vengono controllati con strumenti di analisi automatica (codice, librerie, immagini Docker, segreti nel repository, scansione web) e con test manuali. Le vulnerabilità trovate durante lo sviluppo sono state corrette e verificate.

> **Hai trovato un problema di sicurezza?** Per favore non aprire una issue pubblica: contattami in privato tramite il mio profilo GitHub, così possiamo correggerlo prima che venga sfruttato.

## Com'è fatto

Per chi vuole guardare sotto il cofano:

```mermaid
flowchart LR
    T["Telefoni e PC<br/>del negozio"] -- HTTPS --> C["Server web<br/>(Caddy)"]
    C --> A["Racoonix<br/>(Python, Flask)"]
    A --> D[("Database<br/>(PostgreSQL)")]
    S["Controlli<br/>programmati"] --> D
```

Python e Flask per l'applicazione, PostgreSQL per i dati, Caddy per la connessione cifrata, htmx per un'interfaccia reattiva senza logica nel browser, Docker per far girare tutto allo stesso modo su qualunque computer.

## Autore

Racoonix è un progetto di **Ivan** ([JustCromo](https://github.com/JustCromo)), nato per il corso *System Cyber Security* dell'ITS Academy Prodigi.
