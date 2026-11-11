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
- **Prodotti nuovi già compilati**: al carico, nome, marca e formato arrivano da [Open Food Facts](https://world.openfoodfacts.org), il database aperto dei prodotti alimentari (solo il codice a barre lascia il negozio, e si può spegnere).
- **Lotti e scadenze**, con rotazione automatica: si vende prima quello che scade prima.
- **Cose da fare** per ruolo, aggiornate in tempo reale.
- **Sconti** manuali su un lotto, o programmati a due fasce in base ai giorni che mancano alla scadenza.
- **Ordini ai fornitori** con giorni d'ordine, soglie di riordino e testo pronto da inviare.
- **Conteggio del magazzino**, con registrazione automatica delle differenze.
- **Dashboard** con scadenze, sprechi e valore del magazzino.
- **Utenti e ruoli**: titolare (admin), magazziniere e dipendente, anche combinati.
- **Italiano e inglese**: ogni persona sceglie la sua lingua dal menu; date e valuta seguono il paese del negozio (Italia, Regno Unito, Stati Uniti).
- **Tema chiaro e scuro**, interfaccia pensata prima di tutto per il telefono.

## Installazione rapida

Ti serve un computer Linux sempre acceso nel negozio, con un indirizzo fisso nella rete locale (va benissimo un Raspberry Pi 4 o 5), con **Docker** e **git**. Non serve altro: niente da installare sul sistema, niente permessi di amministratore.

```bash
git clone https://github.com/JustCromo/Racoonix.git
cd Racoonix
./racoonix.sh installa
```

L'installatore non fa domande: prepara tutto da solo, avvia Racoonix e alla fine mostra un **link personale** (anche come codice QR). Poi:

1. dal tuo computer apri quel link: si apre la **configurazione guidata**, dove scegli con un clic paese, lingua e fuso orario, dai un nome al negozio e crei il tuo account. Il link vale una volta sola: se ti serve di nuovo, `./racoonix.sh link`;
2. vai su **Collega dispositivi** e segui le istruzioni per far riconoscere Racoonix a telefoni e PC (una volta sola per dispositivo);
3. crea gli account di chi lavora con te da **Utenti**. Al primo accesso ognuno sceglie la sua password, e tu approvi il suo telefono.

Nome, lingua, paese e fuso orario si cambiano quando vuoi da **Negozio**, nel menu.

Per il resto basta un comando:

| Comando | A cosa serve |
|---|---|
| `./racoonix.sh avvia` / `ferma` | Accendere o spegnere Racoonix |
| `./racoonix.sh stato` | Controllare che tutto funzioni |
| `./racoonix.sh backup-automatico` | Attivare il backup ogni notte |
| `./racoonix.sh backup` / `ripristina` | Fare un backup subito, o tornare a uno precedente |
| `./racoonix.sh aggiorna` | Passare all'ultima versione (prima fa un backup da solo) |
| `./racoonix.sh link` | Mostrare di nuovo il link della configurazione guidata |
| `./racoonix.sh nome NOME` | Cambiare il nome di Racoonix nella rete (di serie `racoonix.local`) |

### Come si raggiunge Racoonix

Racoonix ha **due indirizzi**, e funzionano entrambi:

- **un nome facile da ricordare**, `https://racoonix.local`. Racoonix lo annuncia da solo nella rete del negozio, come fanno le stampanti di rete, senza toccare niente sul router né sul server;
- **l'indirizzo IP del server**, per esempio `https://192.168.1.50`, che funziona sempre e ovunque.

| Dispositivo | Indirizzo da usare |
|---|---|
| PC Windows, Mac, iPhone e iPad | `https://racoonix.local` |
| Computer Linux | `https://racoonix.local`, se il sistema sa trovare i nomi `.local` (molte distribuzioni lo fanno già, altre richiedono il pacchetto `nss-mdns`) |
| Telefoni e tablet Android | l'indirizzo IP: molti Android non cercano i nomi `.local` |

La pagina **Collega dispositivi** mostra sempre entrambi gli indirizzi, con un QR da inquadrare.

> **Un consiglio:** fai usare a ogni dispositivo sempre lo stesso indirizzo. Per il browser, il nome e l'IP sono due siti diversi: cambiando indirizzo, bisogna rifare l'accesso e far approvare di nuovo il dispositivo.

**Vuoi il nome anche sugli Android?** Se il router del negozio permette di dare un nome ai dispositivi della rete (molti router lo chiamano "DNS locale" o "nome host"), puoi associare un nome all'IP del server: quel nome funzionerà su qualunque dispositivo. In questo caso, dai quel nome a Racoonix con `./racoonix.sh nome`.

## Sicurezza

Racoonix è progettato partendo da una domanda: **cosa succede se qualcosa va storto?** In breve:

- **i dati restano in negozio**, e la connessione è sempre cifrata;
- **si entra solo dai dispositivi approvati**, e la configurazione iniziale è protetta da un codice monouso;
- **difesa in profondità**: permessi minimi, registro attività inalterabile, componenti isolati;
- **verificato**, con test automatici, scansioni e test manuali.

I dettagli, e come segnalare una vulnerabilità in privato, sono in **[SECURITY.md](SECURITY.md)**.

## Com'è fatto

Per chi vuole guardare sotto il cofano:

```mermaid
flowchart LR
    T["Telefoni e PC<br/>del negozio"] -- HTTPS --> C["Server web<br/>(Caddy)"]
    C --> A["Racoonix<br/>(Python, Flask)"]
    A --> D[("Database<br/>(PostgreSQL)")]
    S["Controlli<br/>programmati"] --> D
    N["Nome in rete<br/>(racoonix.local)"] -. mDNS .-> T
```

Python e Flask per l'applicazione, PostgreSQL per i dati, Caddy per la connessione cifrata, htmx per un'interfaccia reattiva senza logica nel browser, Docker per far girare tutto allo stesso modo su qualunque computer.

## Autore

Racoonix è un progetto di **Ivan** ([JustCromo](https://github.com/JustCromo)), nato per il corso *System Cyber Security* dell'ITS Academy Prodigi.
