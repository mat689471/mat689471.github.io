# Mettere online la vetrina — 15 minuti

Questo file serve a una cosa sola: avere un **link da mandare a uno studio
dentistico** che, cliccato, mostra il sistema che lavora. Niente installazioni
per lui, niente chiamate a vuoto.

---

## La regola da cui dipende tutto

Metti online **due cose diverse**, mai una sola.

| | **La vetrina** | **La produzione** |
|---|---|---|
| A chi la dai | a chiunque, nelle email | a nessuno, tranne gli studi paganti |
| Chiavi vere | **nessuna** | Anthropic + HubSpot |
| Cosa costa | zero per visitatore | le chiamate dei pazienti veri |
| Cruscotto | aperto (dati finti) | chiuso a chiave |
| Pazienti | cinque inventati | veri, con dati di salute |

Il motivo è concreto: se metti la tua chiave Anthropic dietro un link
pubblico, **ogni curioso che scrive un messaggio lo paghi tu**. Bastano venti
persone su LinkedIn per farti una bolletta. E il cruscotto della produzione
contiene nome, telefono e problema dentale di persone vere: non è una pagina
da lasciare aperta.

La vetrina evita entrambe le cose: Claude e HubSpot sono **simulati dentro il
processo** e parlano lo stesso protocollo dei veri, quindi il giro che il
cliente vede è quello autentico — qualificazione, agenda, CRM, urgenza che si
ferma — solo che non esce niente e non si paga niente.

---

## La strada più corta: GitHub Pages, sul tuo indirizzo

**Questa batte Render per la vetrina, e va usata per prima.** La pagina non ha
bisogno di un server: orologio, conversazione e calcolo del mancato guadagno
girano tutti nel browser di chi guarda. L'unica cosa che faceva Python era
riempire i testi del settore, e quello si fa una volta sola prima di
pubblicare.

```
cd clinica-dentale
python costruisci_vetrina.py
```

Escono due file nella cartella `vetrina/`:

| File | A chi lo mandi |
|---|---|
| `vetrina/index.html` | studi dentistici |
| `vetrina/estetica.html` | cliniche di medicina estetica, e le agenzie che le seguono |

Sono già nel repository. Per accenderli:

1. su GitHub, **Settings → Pages**
2. *Source*: **Deploy from a branch**
3. *Branch*: il ramo su cui stai lavorando, cartella **`/ (root)`** → **Save**

Dopo un paio di minuti gli indirizzi sono:

```
https://mat689471.github.io/vetrina/
https://mat689471.github.io/vetrina/estetica.html
```

**Perché è meglio di Render per la vetrina:** è gratis davvero, **non si
addormenta** (niente attesa di un minuto per chi apre il link a mezzanotte), e
l'indirizzo è il tuo, non quello di un servizio terzo. In un'email a
un'azienda quella differenza si nota.

Il file `.nojekyll` nella radice serve a dire a GitHub di pubblicare le pagine
come stanno, senza passarle da Jekyll.

**Cosa NON entra in questa strada:** il cruscotto. Quello mostra pazienti e ha
bisogno del database, quindi resta una cosa da far vedere in diretta durante
una call, col sistema acceso sul tuo computer — oppure online con Render,
quando arriva il primo cliente che paga.

---

## L'altra strada: Render (serve solo se vuoi anche il cruscotto online)

## Passo per passo

### 1. Metti la cartella su GitHub

Va benissimo un repository **privato**.

Prima controlla che le chiavi non partano con lui:

```
git init
git add .
git status        # NON deve comparire CHIAVI.bat
git commit -m "sistema risposta-lead"
```

`.gitignore` esclude già `CHIAVI.bat`, `.env`, i database e i diari. Se
`CHIAVI.bat` compare lo stesso, fermati e toglilo prima di andare avanti.

### 2. Su Render

1. **render.com** → **New** → **Blueprint** → scegli il repository.
2. Render legge `render.yaml` e ti propone **due servizi**: `clinica-vetrina`
   e `clinica-risposta-lead`.
3. **Per cominciare crea solo `clinica-vetrina`.** La produzione la accendi
   quando hai il primo cliente che paga — prima è solo un costo fisso.

La vetrina non chiede nessuna chiave: parte e basta.

### 3. Controlla che sia viva

Apri `https://clinica-vetrina.onrender.com/health`. Devi vedere:

```json
{"ok": true, "vetrina_pubblica": true, "clienti": 4}
```

I clienti sono quattro perche' la vetrina accende **due mestieri insieme**: tre
studi dentistici e una clinica estetica. Non e' un vezzo — e' la cosa da far
vedere a un'agenzia: settori diversi, regole diverse, un solo cruscotto, e
nessuno che vede i pazienti dell'altro.

Se `vetrina_pubblica` è `false`, manca `DEMO_PUBBLICA=1` fra le variabili:
**non mandare il link finché non è `true`**, o stai pagando tu.

### 4. I due indirizzi da usare

| Indirizzo | A cosa serve |
|---|---|
| `.../vetrina` | **quello che mandi a uno studio dentistico.** La pagina che spiega il problema, con l'animazione e il calcolo del mancato guadagno |
| `.../vetrina?settore=estetica` | **quello che mandi a una clinica estetica o all'agenzia che la segue.** Stessa pagina, altro mestiere: la conversazione parla di un filler gonfio invece che di un dente, e il conto parte da 2.500 € a paziente invece che da 600 |
| `.../` | il cruscotto, da mostrare **durante una call**: si vedono i pazienti arrivare, l'urgenza che va in cima, il riquadro per far scrivere un paziente finto in diretta |

---

## Il piano gratuito e il suo unico difetto

La vetrina gira sul piano **free**, che costa zero ma **si addormenta dopo un
quarto d'ora di silenzio**. Il primo che apre il link dopo la pausa aspetta
quasi un minuto davanti a una pagina bianca.

Per una vetrina è accettabile, a un patto: **aprila tu un minuto prima**.

- Prima di mandare una tornata di email → apri il link, così si sveglia.
- Prima di una call → aprila mentre saluti.

Se ti dà fastidio, in `render.yaml` cambia `plan: free` in `plan: starter`
sul servizio `clinica-vetrina`.

---

## Il link nelle email

Un link nudo si clicca poco. Nelle bozze che stiamo preparando, la riga che
funziona è quella che dice **cosa vedrà**, non "guarda la mia demo":

> Le ho preparato una pagina che mostra cosa succede quando un paziente vi
> scrive alle 21:47:
> `https://clinica-vetrina.onrender.com/vetrina?settore=estetica`
> Ci sono due minuti di lettura, e in fondo può mettere i numeri del suo
> studio e vedere il conto.

Il calcolatore in fondo alla vetrina usa **i numeri che inserisce lui**: non
c'è nessuna statistica di settore inventata. Se il risultato è piccolo, lo
vede da solo — ed è meglio saperlo prima di venderglielo.

---

## Quando arriva il primo cliente vero

Solo allora accendi `clinica-risposta-lead`, e in quel momento cambia tutto:

1. **Le chiavi.** In *Environment* metti `ANTHROPIC_API_KEY` e il token
   HubSpot dello studio. `CONSOLE_TOKEN` e `WEBHOOK_TOKEN` li genera Render
   da solo: aprili e copiali, ti servono.
2. **Il disco.** `render.yaml` chiede già 1 GB su `/var/dati`. Senza, il
   database sparisce a ogni pubblicazione.
3. **Il piano `starter`**, non il gratuito: un servizio che dorme perde i lead
   che arrivano di notte, cioè esattamente quelli che stai vendendo.
4. **Gli indirizzi da dare allo studio:**
   - il modulo del sito manda a
     `POST https://.../webhook/lead/studiorossi`
     con l'intestazione `X-Token: <WEBHOOK_TOKEN>`
   - il cruscotto è `https://.../?token=<CONSOLE_TOKEN>` — al primo accesso il
     token si salva nel browser e non lo richiede più
5. **Se il cruscotto lo usa lo studio e non tu**, aggiungi
   `CONSOLE_CLIENTE=studiorossi`: quella installazione vedrà solo i suoi
   pazienti, anche se qualcuno prova a cambiare l'indirizzo a mano.

---

## Cosa dire quando te lo chiedono

**«I dati dei miei pazienti dove stanno?»**
Sul tuo servizio, in Europa (Render, regione Francoforte), dietro una chiave.
Il cruscotto senza token non si apre. Ogni paziente si può cancellare
davvero: sparisce con messaggi e appuntamento.

**«E se sbaglia?»**
Davanti a un sintomo non decide: si ferma e mette il paziente in cima alla
lista di chi va richiamato. Vale anche per impianti, ortodonzia e protesi.
Quelle regole sono nel codice, non nel modello, e c'è una prova automatica
che le verifica.

**«È a norma GDPR?»**
Le richieste dei pazienti sono dati sanitari, quindi la risposta seria è: il
sistema fa la sua parte — accesso a chiave, isolamento fra studi,
cancellazione su richiesta, log senza segreti — ma **il titolare del
trattamento resta lo studio**, e servono informativa e nomina a responsabile
esterno. Non improvvisare su questo punto: fatti dare una mano da un
consulente prima di firmare il primo contratto. Meglio dirlo così che
promettere una conformità che non puoi garantire da solo.
