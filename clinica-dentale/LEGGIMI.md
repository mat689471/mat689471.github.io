# Risposta automatica ai lead — per studi dentistici

Un paziente scrive a uno studio. Il sistema lo qualifica parlando con Claude,
gli propone un posto in agenda, gli risponde, scrive contatto e trattativa sul
CRM di **quello** studio. Se il caso è delicato — dolore, gonfiore, un lavoro
importante — **si ferma e chiama una persona**.

Serve **più studi contemporaneamente**, e ognuno è chiuso in casa propria: un
paziente dello Studio Rossi non può finire nel CRM, nell'agenda o nella coda
del Centro Bianchi. Non è una promessa: è una clausola `WHERE` su ogni query,
e c'è un test che prova a violarla.

---

## Cosa è REALE e cosa è STUB

Onestà prima di tutto, così nessuno resta deluso in demo.

| Pezzo | Stato | Nota |
|---|---|---|
| Qualificazione con Claude | **REALE** | API Anthropic, formato garantito da uno strumento con schema |
| Piu' mestieri (settori) | **REALE** | dentale ed estetica, `tests/settori.py` |
| CRM HubSpot | **REALE** | contatti e trattative v3, uno per cliente, associazione inclusa |
| CRM di scorta locale | **REALE** | se HubSpot cade il paziente non si perde, resta `sincronizzato=0` |
| Isolamento fra clienti | **REALE** | dimostrato da `tests/multicliente.py` |
| Agenda e prenotazioni | **REALE** su SQLite | una agenda per studio; Google Calendar si innesta dietro l'interfaccia |
| Diario per cliente | **REALE** | `dati/diario-<studio>.log` |
| Cruscotto browser | **REALE** | filtrabile per studio |
| **WhatsApp / SMS** | **STUB** | il canale scrive a schermo e su file, marcato `[SIMULATO]`. L'interfaccia c'è già, per cliente |
| **Chiamate telefoniche AI** | **non c'è** | fuori scopo |
| **Pagamenti** | **non c'è** | fuori scopo |
| Accesso a chiave | **REALE** | `CONSOLE_TOKEN` per leggere, `WEBHOOK_TOKEN` per scrivere |
| Cruscotto per un solo studio | **REALE** | `CONSOLE_CLIENTE=studiorossi` e vede solo lui |
| Cancellazione dati paziente | **REALE** | sparisce con messaggi e appuntamento |
| Vetrina online senza costi | **REALE** | `DEMO_PUBBLICA=1`: Claude e HubSpot simulati |

---

## Come arriva la risposta al paziente

Ogni cliente ha il **suo** canale, nel campo `canale` di `clienti.json`.

| `tipo` | Cosa fa | Quando usarlo |
|---|---|---|
| `console` | scrive a schermo, marcato `[SIMULATO]`. **Non manda niente** | prove e vetrina |
| `email` | manda davvero, via SMTP | il primo cliente vero |
| `whatsapp` | Cloud API di Meta | quando la clinica ha numero e token |

**La regola che vale sempre: se la risposta non parte, il paziente passa a una
persona.** Non resta in silenzio, e nella coda c'e' scritto il motivo. Un
paziente che crede di aver ricevuto risposta e non l'ha ricevuta e' peggio di
un paziente richiamato a mano.

### Email

Il server SMTP e' **uno solo, globale**: e' la tua infrastruttura, come la
chiave Anthropic. Mandare dal dominio della clinica richiederebbe i loro DNS,
e non si chiede prima di aver firmato.

```
SMTP_HOST  SMTP_PORT  SMTP_USER  SMTP_PASSWORD  SMTP_FROM
```

Per cliente cambia solo **come si presenta**:

```json
"canale": {
  "tipo": "email",
  "nome_mittente": "Clinica Estetica Aurora",
  "rispondi_a": "info@clinica-aurora.it",
  "oggetto": "La sua richiesta"
}
```

Nella posta del paziente si legge *Clinica Estetica Aurora*, e se risponde la
mail arriva **alla clinica**, non a te.

### WhatsApp, e la regola delle 24 ore

Scritto per intero e provato contro un finto Meta. Non e' acceso perche' non
e' roba tua: numero verificato, azienda verificata e modelli approvati sono
intestati **alla clinica**.

```json
"canale": {
  "tipo": "whatsapp",
  "id_numero": "111222333",
  "token_env": "WHATSAPP_TOKEN_AURORA",
  "modello": "risposta_lead",
  "lingua_modello": "it"
}
```

**Il punto che fa cadere tutti:** Meta lascia mandare testo libero **solo
entro 24 ore** dall'ultimo messaggio del paziente. Fuori da li' passano solo i
**modelli approvati**.

- Il paziente ci ha scritto **su WhatsApp** -> dentro la finestra, testo
  libero. Perfetto.
- Il lead arriva **da un modulo o da una campagna** -> il paziente non ci ha
  mai scritto, la finestra non e' mai stata aperta, serve il modello.

Se il modello non c'e', il sistema **non ci prova**: lo dice e passa il
paziente a una persona. Meglio di un rifiuto di Meta che nessuno legge.

---

## Il mestiere e' un dato, non e' scritto nel codice

Il sistema e' nato per studi dentistici, ma l'odontoiatria non e' piu' cucita
dentro: ogni cliente ha un **settore**, e il settore decide tre cose.

1. **Come parla** — chi sei, chi hai davanti, cosa devi capire.
2. **Dove si ferma** — quali richieste devono passare per forza da una
   persona. Questa lista **non passa dal modello**: la applica il codice dopo,
   e c'e' una prova che gli passa apposta una risposta sbagliata per vedere se
   la raddrizza.
3. **Come si racconta** — i testi della vetrina, perche' a un chirurgo estetico
   non si fa vedere una demo che parla di otturazioni.

Oggi ce ne sono due, in `app/settori.py`:

| Settore | Si ferma davanti a | Prenota da solo |
|---|---|---|
| `dentale` | dolore, gonfiore, trauma; impianti, ortodonzia, protesi | igiene, sbiancamento, controllo |
| `estetica` | un problema **dopo** un trattamento; chirurgia; iniettivi (filler, tossina, fili) | laser, peeling, pressoterapia, consulenza |

La differenza non e' un dettaglio: in estetica **quasi tutto e' un atto
medico**, quindi la soglia e' molto piu' bassa. Un filler non e' una pulizia
dei denti, e il sistema non lo prenota da solo nemmeno se il modello dice di
si'.

In `clienti.json` basta la riga `"settore": "estetica"`. Se manca vale
`dentale`, cosi' un file gia' scritto continua a funzionare; se c'e' ma e'
scritto male **il sistema non parte**, invece di servire una clinica estetica
con le regole del dentista.

Aggiungere un mestiere e' aggiungere una voce a `SETTORI`. Non si tocca il
motore: ne' l'agenda, ne' il CRM, ne' l'isolamento fra clienti.

---

## Provalo subito, senza spendere niente

**`VETRINA-DEMO.bat`** — il cruscotto acceso con cinque pazienti d'esempio
divisi fra due studi. Clicca i nomi degli studi in alto e guarda le liste
cambiare: è il modo più veloce per far capire a un cliente cosa compra.

**`PROVA-SENZA-SPENDERE.bat`** — i 5 punti di accettazione + 12 casi storti.

**`PROVA-MULTICLIENTE.bat`** — la prova che due studi non si toccano.

**`python tests/canali.py`** — le 24 prove che il messaggio esce davvero:
un finto SMTP che parla il protocollo vero, un finto Meta con la regola delle
24 ore, e il giro completo che passa il paziente a una persona se la risposta
non parte.

**`python tests/settori.py`** — dentale ed estetica non si contaminano.

**`python tests/sicurezza.py`** — le cinque prove che, se saltano, ti costano
un cliente: cruscotto chiuso a chiave, le due chiavi separate, la scheda di un
paziente che non si legge da un altro studio, il blocco su un solo studio, la
cancellazione che cancella davvero.

Tutti e tre girano contro finti Claude e finto HubSpot che parlano **lo stesso
protocollo** dei veri: se il giro regge con quelli regge anche con gli altri.
Zero centesimi.

**`PROVA-VERA.bat`** — gli stessi 5 punti contro i servizi veri (serve
`CHIAVI.bat`, costa due chiamate al modello).

---

## Le chiavi: la regola che non si piega

- **`ANTHROPIC_API_KEY`: una sola, globale.** È il costo di chi fa girare il
  servizio, non del singolo studio.
- **Token HubSpot: uno per cliente**, letto dall'ambiente col nome scritto in
  `clienti.json`. Mai nel codice, mai nei file di configurazione, mai nei log.
- Se manca il token di uno studio, **quello studio** scrive in locale e lo dice.
  Gli altri continuano a lavorare.

In `clienti.json` c'è scritto `"hubspot_token_env": "HUBSPOT_TOKEN_STUDIOROSSI"`
— cioè **il nome della variabile**, non il valore. Il file si può mandare per
email o mettere su GitHub: dentro non c'è niente di segreto. C'è anche un
controllo all'avvio: se qualcuno ci incolla un token vero, il sistema si
rifiuta di partire e dice dove.

---

## Chi può entrare

Il cruscotto mostra nome, telefono e quello che il paziente ha scritto del suo
problema ai denti: sono **dati di salute**. Su un indirizzo pubblico senza
chiave sono in mano al primo che passa.

Due chiavi, separate apposta:

| Variabile | Chi la usa | Cosa apre |
|---|---|---|
| `CONSOLE_TOKEN` | tu e lo studio | il cruscotto e le sue API — **leggere** |
| `WEBHOOK_TOKEN` | chi monta il modulo sul sito | i webhook — **scrivere** |

Sono separate perché il token del webhook lo dai a un fornitore esterno:
quello deve poter creare pazienti, non leggerli tutti. C'è una prova che lo
verifica (`python tests/sicurezza.py`).

Se una chiave non è impostata **quella porta resta aperta**, il sistema lo
scrive nel diario all'avvio e mette una fascia rossa in cima al cruscotto.
Aperta di default perché la vetrina deve funzionare con un doppio clic: ma
**online, con pazienti veri, senza token non ci si va**.

`/health` resta sempre libero: serve al provider per sapere se sei vivo.

### Un cruscotto per un solo studio

Se il cruscotto lo dai al cliente invece di tenerlo tu, aggiungi
`CONSOLE_CLIENTE=studiorossi`. Quell'installazione vede **solo** quello
studio: non solo l'elenco, anche la singola scheda paziente. Cambiare
l'indirizzo a mano non serve a niente.

### Cancellare un paziente

Nella scheda del paziente c'è **Cancella i dati di questo paziente**: sparisce
con i suoi messaggi, la coda e la riga sul CRM locale, e il posto in agenda
torna libero. Sul CRM esterno va cancellato dal CRM, e il sistema te lo dice
invece di far finta.

---

## Aggiungere un cliente — i passi esatti

1. **Apri `clienti.json`** e copia un blocco dentro `"clienti"`:

   ```json
   {
     "slug": "studioverdi",
     "nome": "Studio Dentistico Verdi",
     "hubspot_token_env": "HUBSPOT_TOKEN_STUDIOVERDI",
     "orari": "lunedi-venerdi 9:00-19:00",
     "indirizzo": "via Roma 5, Bologna",
     "trattamenti": ["igiene", "sbiancamento", "impianto", "controllo"],
     "prima_visita_gratuita": true,
     "canale": {"tipo": "console"},
     "agenda": {"ore": [9, 15], "giorni": 5, "durata_min": 45, "studio": "Verdi"}
   }
   ```

   `slug` è il nome corto che finisce nell'indirizzo: solo minuscole, niente
   spazi. Deve essere diverso da tutti gli altri.

2. **Metti il suo token** dove gira il sistema:
   - in locale, dentro `CHIAVI.bat`: `set HUBSPOT_TOKEN_STUDIOVERDI=pat-...`
   - online, fra le variabili d'ambiente del provider (sotto c'è come)

   Il nome deve combaciare **esattamente** con `hubspot_token_env`.

3. **Riavvia** il sistema. All'avvio rilegge `clienti.json`, crea l'agenda del
   nuovo studio e lo fa comparire nel cruscotto.

4. **Dai l'indirizzo al cliente** per il suo modulo o la sua campagna:

   ```
   POST https://iltuoindirizzo/webhook/lead/studioverdi
   ```

5. **Controlla** che sia collegato: apri `/health` e guarda `clienti_con_crm`,
   oppure guarda la spia in alto a destra nel cruscotto — dice quanti studi
   sono senza CRM.

---

## Le porte

| | |
|---|---|
| `POST /webhook/lead/{studio}` | arriva un paziente nuovo |
| `POST /webhook/message/{studio}` | il paziente risponde (`lead_id` oppure `telefono`, più `testo`) |
| `GET /coda/{studio}` | chi aspetta un operatore in quello studio |
| `GET /api/stato?cliente={studio}` | tutto quello che serve al cruscotto |
| `GET /api/clienti` | gli studi configurati (senza segreti) |
| `GET /health` | vivo, con quanti studi e quanti col CRM collegato |
| `GET /` | il cruscotto (chiede `CONSOLE_TOKEN`, se impostato) |
| `GET /vetrina` | la pagina da far vedere al cliente: nessun dato, nessuna chiave |
| `DELETE /api/paziente/{id}` | cancella davvero un paziente |

`POST /webhook/lead` senza studio funziona ancora e va al cliente
`predefinito`: chi aveva già collegato un modulo non deve rifare niente.

Esempio:

```json
POST /webhook/lead/studiorossi
{ "nome": "Giulia Bianchi", "telefono": "+39 340 1122334",
  "email": "giulia@example.com", "campagna": "Sbiancamento",
  "messaggio": "Vorrei uno sbiancamento, preferirei di mattina" }
```

---

## Cosa succede a ogni paziente

1. **Entra** da un indirizzo che dice a quale studio appartiene.
2. **Claude lo qualifica** con le istruzioni di **quello** studio: nome, orari,
   indirizzo, trattamenti offerti. La segretaria del Centro Bianchi non può
   dare gli orari dello Studio Rossi, perché non li ha mai letti.
3. **Bivio.** Se serve una persona, l'automazione si ferma qui.
4. **Agenda di quello studio**: si cerca un posto e si prenota.
5. **Risposta** dal canale di quello studio.
6. **CRM di quello studio**. Se non risponde, copia locale segnata da
   sincronizzare.

Ogni passo scrive una riga con dentro il nome dello studio.

## Quando si ferma e chiama una persona

| Caso | Priorità |
|---|---|
| Emergenza: dolore, gonfiore, trauma, sanguinamento, ascesso | 1 |
| Fastidio importante | 2 |
| Lavoro importante: impianti, ortodonzia, protesi | 3–5 |
| Il paziente chiede di parlare con qualcuno | 4 |
| Claude non è sicuro, o qualcosa si rompe | 5 |
| Agenda piena con urgenza alta | 1 |

Due regole non passano dal modello, sono nel codice: **un'emergenza va sempre
a una persona**, e **un lavoro importante anche**. E un paziente già in mano a
un operatore non torna in automatico da solo.

---

## Il cruscotto

`http://127.0.0.1:8000` — in alto i bottoni degli studi: **Tutti**, oppure uno
solo. La scelta resta anche dopo un ricaricamento.

**Aspettano una persona** (a sinistra, la colonna che conta) — chi il sistema
non ha voluto gestire da solo, i più urgenti in cima. *Lo seguo io* / *Fatto*.

**Pazienti** — tutti, con **quello che hanno chiesto loro** fra virgolette.
Clicca un nome: si apre la scheda con lo studio, i dati, l'appuntamento, gli id
su HubSpot e tutta la conversazione.

**Appuntamenti** — l'agenda dello studio scelto.

In basso a destra un riquadro per far scrivere un paziente finto **allo studio
che stai guardando**, e vedere il sistema rispondere in diretta.

---

## Mettere il sistema online

> Per il **link pubblico da mandare ai clienti** — quello che costa zero e non
> espone nessuna chiave — c'è una guida dedicata: **`VETRINA-ONLINE.md`**.
> Leggi quella per prima: mettere online il sistema vero prima di avere un
> cliente pagante è solo un costo fisso.

Serve un host **sempre acceso**: se dorme, i lead che arrivano di notte si
perdono. Sotto c'è Render perché è il più corto, ma il `Dockerfile` va
ovunque (Railway, Fly, una macchina tua).

### Su Render, passo per passo

1. **Metti la cartella su GitHub** (un repository privato va benissimo).
   Controlla che `CHIAVI.bat` **non** ci sia: è già escluso da `.dockerignore`,
   ma su git aggiungilo a `.gitignore`.

2. Su **render.com** → **New** → **Blueprint** → scegli il repository.
   Render legge `render.yaml` e prepara il servizio da solo.

3. **Piano**: `starter`, non quello gratuito. Il gratuito si addormenta dopo
   un po' di silenzio, e un lead che arriva mentre dorme lo perdi.

4. **Metti le chiavi** in **Environment** (mai nel repository):

   | Variabile | Cosa ci va |
   |---|---|
   | `ANTHROPIC_API_KEY` | la tua unica chiave Anthropic |
   | `ANTHROPIC_MODEL` | `claude-sonnet-5` (già impostata) |
   | `HUBSPOT_TOKEN_STUDIOROSSI` | il token di quello studio |
   | `HUBSPOT_TOKEN_STUDIOBIANCHI` | il token dell'altro |
   | `DB_PATH` | `/var/dati/clinica.db` (già impostata) |

   Una riga per ogni cliente in più. Il nome deve combaciare con
   `hubspot_token_env` in `clienti.json`.

5. **Il disco**: `render.yaml` chiede già 1 GB montato su `/var/dati`. Senza,
   il database sparisce a ogni pubblicazione.

6. **Controlla**: apri `https://iltuonome.onrender.com/health`. Deve
   rispondere `"ok": true` e dirti quanti studi ha collegato.

7. **Dai gli indirizzi ai clienti**:
   `https://iltuonome.onrender.com/webhook/lead/studiorossi`

### I log

- Su Render: pannello del servizio → **Logs**. Ogni riga ha il nome dello
  studio fra parentesi quadre, quindi si cerca `[studiorossi]` e si vede solo
  quello.
- Sul disco: `dati/diario.log` (tutto) e `dati/diario-<studio>.log` (uno per
  studio, da mandare a quel cliente senza filtrare a mano).

Una riga è fatta così:

```
[2026-08-28T18:33:05Z] [studiorossi] LEAD 42 | crm scritto | fonte=hubspot contatto=855441807548
```

### Con Docker, dove vuoi

```
docker build -t clinica .
docker run -p 8000:8000 \
  -e ANTHROPIC_API_KEY=sk-ant-... \
  -e HUBSPOT_TOKEN_STUDIOROSSI=pat-... \
  -v $(pwd)/dati:/app/dati \
  clinica
```

L'immagine non gira da root e ha un controllo di salute integrato.

---

## Girare in locale

Serve Python 3.11 o più recente. La prima volta:

```
pip install -r requirements.txt
```

Poi copia `CHIAVI.bat.esempio` in **`CHIAVI.bat`**, mettici le chiavi
(**senza virgolette, senza spazi attorno all'uguale**) e fai doppio clic su
**`AVVIA.bat`**.

## Dove si innestano le cose vere

- **WhatsApp / SMS**: una classe come `app/channels/console.py` con lo stesso
  metodo `invia()`. La configurazione per-cliente esiste già (campo `canale`
  in `clienti.json`), quindi ogni studio potrà avere il suo numero.
- **Google Calendar**: una classe come `app/calendar/sqlite_cal.py` con
  `slot_libero()` e `prenota()`.
- **Un altro CRM**: una classe come `app/crm/hubspot.py` con `contatto()` e
  `deal()`.

`base.py` di ogni cartella è solo il contratto: non importa nient'altro.

## Se qualcosa non va

| Cosa vedi | Cosa vuol dire |
|---|---|
| `cliente sconosciuto` (404) | lo `slug` nell'indirizzo non è in `clienti.json` — la risposta elenca quelli veri |
| uno studio scrive sempre in locale | manca la sua variabile d'ambiente, o il nome non combacia |
| ogni paziente va in coda operatore | manca `ANTHROPIC_API_KEY` |
| `401` da HubSpot | token sbagliato — o con uno spazio davanti |
| `404` da Anthropic | nome del modello sbagliato, non la chiave |
| il sistema non parte e parla di `clienti.json` | c'è un errore nel file: il messaggio dice quale |
| accenti strani a schermo | usa i `.bat`, che sistemano la console |
