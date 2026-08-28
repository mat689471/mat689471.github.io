# L'Ecosistema

Un mondo dove un gruppo di agenti lavora per te: parli con l'Orchestratore,
lui decide chi mettere al lavoro e ti riporta i risultati.

## Avviare, senza impazzire

**Doppio clic su `AVVIA.bat`.** Basta quello. Apre da solo le due finestre che
servono (il mondo e gli agenti) e il browser.

Non importa in che cartella ti trovi né come si chiama: il file si orienta da
solo, purché resti accanto a `agente.py` e alla cartella `mondo`.

### La prima volta: sblocca lo ZIP

Windows blocca i file scaricati da internet e al doppio clic mostra
*"Windows ha protetto il PC"*. Si toglie in dieci secondi, **prima** di
estrarre:

1. tasto destro sullo **ZIP** scaricato → **Proprietà**
2. in fondo alla scheda *Generale*, spunta **Annulla blocco**
3. **OK**, poi estrai

Così vale per tutti i file dentro. Se hai già estratto, fai la stessa cosa
direttamente su `AVVIA.bat`.

Se il messaggio compare comunque: **Ulteriori informazioni** → **Esegui
comunque**.

### Un pulsante sul desktop

Tasto destro su `AVVIA.bat` → **Mostra altre opzioni** → **Invia a** →
**Desktop (crea collegamento)**.

Da lì in poi è un'icona sul desktop e non devi più cercare la cartella.

## Cosa si apre

| Finestra | A cosa serve |
|---|---|
| `Ecosistema - mondo` | il server; apre il browser da solo |
| `Ecosistema - agenti` | l'Orchestratore e il suo sciame |

Servono **tutte e due** accese. Se avvii solo il mondo, lo vedi ma resta
scritto *"in attesa dell'orchestratore"*. Per fermare tutto, chiudi le due
finestre.

Indirizzi, una volta avviato:

- il mondo — <http://localhost:5178/>
- il Quartier Generale (chiavi, conti, progetti) — <http://localhost:5178/gestione.html>

## Se la finestra degli agenti dice «Manca la libreria 'anthropic'»

Windows tiene spesso **due Python** affiancati, `py` e `python`, che sono due
installazioni separate con librerie separate. Se hai installato `anthropic` su
una, l'altra non ce l'ha.

`AVVIA.bat` se ne accorge: prova l'altro interprete e, se manca a entrambi, la
installa da solo. Se preferisci farlo a mano, dalla cartella del progetto:

```
py -m pip install anthropic
```

Se PowerShell risponde che `py` non esiste, usa `python` al posto di `py`.

## Se la finestra lampeggia e sparisce

Vuol dire che `AVVIA.bat` parte ma si interrompe prima di poterti mostrare
l'errore. Per leggerlo: apri PowerShell nella cartella e lancia il file da li'
(`.\AVVIA.bat`) — la finestra resta aperta e il messaggio si vede.

## Se qualcosa manca

`AVVIA.bat` controlla da solo e te lo dice:

- **Node.js** — <https://nodejs.org>, pulsante LTS
- **Python** — <https://python.org>; durante l'installazione spunta
  *"Add Python to PATH"*, altrimenti Windows non lo trova

## Avviare a mano

Se preferisci i comandi, dalla cartella principale, in due finestre separate:

```
node mondo/avvia.mjs
```
```
python agente.py --mondo
```

L'errore più comune è `Cannot find module ...\mondo\mondo\avvia.mjs`: vuol
dire che sei già dentro `mondo`. Torna indietro con `cd ..` e riprova.

## Cosa hanno in mano gli agenti

Quartier Generale, scheda **🔌 Strumenti agenti**.

**Le competenze (Skill) sono già tutte attive.** Non c'è niente da accendere:
l'ecosistema le cerca dove le tiene Claude Code (`~/.claude/skills`, i plugin, e
`.claude/skills` del progetto), quindi le skill che hai scritto per lui sono
automaticamente anche degli agenti. Un agente si legge per intero solo quella
che gli serve, quando gli serve.

**I server MCP invece si accendono**, con gli interruttori della stessa scheda.
Accesi di partenza: `ruflo`, memoria persistente e ragionamento a passi. Dopo
ogni accensione **riavvia l'ecosistema**.

Un server MCP può portare centinaia di strumenti: nel prompt degli agenti ce ne
stanno poche decine, prese a turno fra i server. Gli altri restano
raggiungibili — l'agente li cerca con `cerca_strumento_mcp` quando pensa che
esista quello adatto.

Da sapere prima di accenderne altri: **gli strumenti MCP non passano dalla
richiesta di autorizzazione del mondo**. Un comando PowerShell distruttivo ti
chiede il permesso; uno strumento MCP no. Accendi quello che ti fidi di dare in
mano agli agenti senza conferma.

### Connettori su internet

Non tutto gira in locale. I servizi che generano video, audio e immagini stanno
sul web, e si attaccano dalla stessa scheda: **Aggiungine uno tuo → 🌐 Su
internet**. Servono due cose: l'indirizzo del connettore (lo trovi nella pagina
per sviluppatori del servizio) e una chiave, che metti **prima** in Cassaforte —
nel modulo scegli solo il suo nome. In `mcp.json` finisce il nome, mai il valore.

L'indirizzo deve essere `https://`: su `http://` la chiave viaggerebbe in chiaro,
e viene rifiutato.

I connettori che hai attivato dentro **claude.ai** (Gmail, Drive, Calendario…)
sono un'altra cosa: vivono nel tuo account Claude e si autenticano con un accesso
che non ti lascia una chiave da incollare, quindi non si attaccano qui. Per dare
quelle capacità agli agenti serve il connettore del servizio con una sua chiave.

## Dare un incarico lungo

La casella della Sala Comando cresce con quello che scrivi, fino a riempire quasi
metà del riquadro. Un incarico serio si scrive per esteso, e va **visto tutto**
prima di partire: una volta mandato, il lavoro comincia subito e non puoi
completarlo con un secondo messaggio.

- **Invio** manda
- **Maiusc + Invio** va a capo
- Oltre gli 800 caratteri compare il conteggio, così sai quanto spazio resta

Il limite è di 20.000 caratteri — circa dieci pagine. Prima erano 2.000, e il
taglio avveniva **in silenzio**: la richiesta partiva monca senza che niente lo
dicesse.

## Collegare la posta

Quartier Generale → **🔌 Strumenti agenti** → in cima, **Posta**.

Ci sono i pulsanti **Accedi con Google** e **Accedi con Microsoft** (Outlook,
Hotmail, Live). La password la scrivi sulla pagina del fornitore, non qui: da noi
arriva solo un permesso, revocabile quando vuoi, limitato a leggere e mandare
posta.

**Un account alla volta.** Per usare il secondo indirizzo: *Esci*, poi rientri
con quello.

### La preparazione, una volta sola

Google e Microsoft non lasciano che un programma acceda alla tua posta senza
sapere chi è, quindi va registrato questo ecosistema. È gratis e non serve carta
di credito. La scheda ti dà i passi e, soprattutto, **l'indirizzo di ritorno da
incollare** — quello dipende dalla porta e non puoi indovinarlo.

Se il tuo progetto Google è «in test», aggiungi il tuo indirizzo fra gli utenti
di prova, altrimenti l'accesso viene rifiutato.

### Come mandano gli agenti

Con lo strumento `manda_email`. Di partenza ogni invio ti chiede conferma nel
mondo; se preferisci che partano da sole c'è il pulsante **✉️ Mail libere** nella
barra in alto, con la stessa logica dell'autorizzazione sui comandi: si accende
apposta, vale solo per la sessione in corso, e ogni mail partita resta tracciata
nel flusso in diretta con destinatario e oggetto.

I due interruttori sono **separati**: l'autorizzazione completa sui comandi non
accende le mail, e viceversa. Dare mano libera sul proprio computer non è la
stessa cosa che darla su quello che esce e arriva ad altre persone.

I permessi restano cifrati in `dati/account.enc`, con la stessa chiave della
Cassaforte, e non escono dal tuo computer.

## Farsi pagare: l'offerta la costruiscono gli agenti

Un link di pagamento fatto a mano vale per un prezzo solo. Se lo sciame inventa
un servizio con tre livelli di abbonamento, quei livelli nascono da soli: con
`crea_offerta` un agente crea su **Stripe e PayPal** il prodotto, i prezzi
(singoli, mensili o annuali) e i link per pagarli, e li mette nella pagina che
ha appena costruito.

Cosa serve in Cassaforte:

| Chiave | A cosa serve |
|---|---|
| `STRIPE_SECRET_KEY` | creare prodotti, prezzi e link — chiave ristretta con permesso **write** su Prodotti, Prezzi e Link di pagamento |
| `PAYPAL_CLIENT_ID` + `PAYPAL_CLIENT_SECRET` | i piani di abbonamento PayPal |

Basta uno dei due: quello che manca viene detto, non nascosto.

PayPal fa i link solo per gli **abbonamenti**; per il pagamento singolo resta il
tuo PayPal.me.

Cosa **non** si può fare da lì, di proposito: incassare, rimborsare, spostare
denaro, cancellare. Creare un'offerta è reversibile — si archivia — e non muove
un centesimo finché non è un cliente vero a premere «Paga». Gli agenti non
vedono mai il valore di una chiave: chiedono al mondo, e il mondo risponde con i
link.

## La Vetrina: vedere il lavoro finito

Quando un agente finisce qualcosa di guardabile — una pagina web, un'immagine,
un video, un audio, un PDF — lo salva nella cartella `lavori/` e la **Vetrina**
si apre da sola nel mondo. Una pagina si sfoglia davvero, un video parte, un
audio si ascolta. Il pulsante **🖼 Vetrina** riapre l'ultimo lavoro, e in basso
restano i precedenti.

`lavori/` è l'unica cartella che il mondo mostra: una consegna che punta altrove
viene rifiutata, così un agente non può pubblicare per sbaglio un file privato.

## Niente si perde per strada

**Il codice.** Ogni modifica finisce nel repository, e a ogni pubblicazione un
controllo automatico verifica che l'archivio contenga ancora tutti i file di
`MANIFESTO.txt` e che il codice si legga. Se qualcosa sparisce o si rompe, su
GitHub compare una croce rossa invece di passare inosservato. Lo puoi lanciare
anche tu:

```
node controlla.mjs
```

Serve perche' un file cancellato per sbaglio non da' nessun fastidio a chi l'ha
cancellato — sul suo computer c'e' ancora — e il buco si scopre solo quando
qualcun altro scarica lo zip. È già successo una volta.

**I tuoi dati.** Doppio clic su **`SALVA-I-MIEI-DATI.bat`**: copia `dati/`,
`lavori/` e `avatar/` in *Documenti → Ecosistema-salvataggi*, in una cartella
con la data. Fallo prima di scaricare un archivio nuovo, e non perdi né le
credenziali né il lavoro fatto.

Copia anche i file nascosti, `.masterkey` compreso: senza quello la cassaforte
cifrata non si riapre.

## I tuoi dati restano tuoi

Le cartelle `dati/` (chiavi API, conti, contabilità) e `avatar/` (i modelli 3D
generati) **non stanno nel repository**: restano sul tuo computer. Se rifai il
download in una cartella nuova, copiale dalla vecchia, altrimenti troverai la
cassaforte vuota.
