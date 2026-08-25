# L'Ecosistema — il mondo vivente degli agenti

Una sede isometrica dove **tu parli con l'Orchestratore** nella Sala Comando,
e lui decide chi mettere al lavoro. Gli agenti specialisti **nascono quando
servono**, vanno nella loro stanza, lavorano, si passano il lavoro fra loro e
tornano a riferire al capo.

## Il principio: si passa sempre dall'Orchestratore

```
Tu  →  ORCHESTRATORE  →  agenti specialisti  →  ORCHESTRATORE  →  Tu
```

Nessun agente parla direttamente con te. Ogni tuo messaggio arriva
all'Orchestratore, che sceglie i ruoli, spezza il lavoro, li coordina e poi
ti risponde lui. Quando serve un ruolo che non esiste ancora, l'agente
**viene creato sul momento** e lo vedi entrare nella sua stanza.

## Le stanze

| Ruolo | Stanza | Chi ci lavora |
|---|---|---|
| `code` | Studio Sviluppo | Sviluppatore |
| `design` | Sala Architettura | Architetto |
| `qa` | Sala Test | Tester |
| `research` | Laboratorio | Ricercatore |
| `review` | Sala Review | Revisore |
| `docs` | Archivio Docs | Documentatore |

Al centro la **Sala Comando**: la pedana dell'Orchestratore e il punto dove
stai tu. Lì compaiono i vostri messaggi.

## Avviare tutto (due finestre, stessa cartella)

Serve **Node.js 18+** e **Python 3** con `anthropic` installato
(`pip install anthropic`) e la variabile `ANTHROPIC_API_KEY` impostata.

**Finestra 1 — il mondo**
```bash
cd mondo
node avvia.mjs
```
Apre il browser sull'indirizzo indicato (es. `http://localhost:5178/`).

**Finestra 2 — l'ecosistema**
```bash
python agente.py --mondo
```
Deve dire *"Ecosistema avviato. L'Orchestratore è in ascolto."*

⚠️ Le due finestre devono partire **dalla stessa cartella estratta**,
altrimenti scrivono e leggono file diversi e non si vedono.

Quando l'Orchestratore è vivo, il badge in alto diventa verde
**"orchestratore attivo"**.

## Cosa puoi fare nel mondo

- **Sala Comando (destra)** — scrivi all'Orchestratore. Ti risponde lì.
- **Abitanti (sinistra)** — chi c'è, cosa sta facendo, **barra di avanzamento**.
- **Anteprima lavoro (sinistra)** — quello che un agente produce (elenchi,
  riepiloghi, codice) compare qui mentre lavora.
- **📋 Resoconto** — chiede all'Orchestratore un riepilogo del lavoro svolto.
- **Clicca un agente** — scheda con stato, compito e **avatar 3D**.
- **Scena** — trascina per spostarti, rotella per lo zoom. I fili luminosi
  mostrano chi sta riferendo al capo; gli impulsi rosa sono i passaggi di
  lavoro fra agenti.

## Autorizzazioni

I comandi **distruttivi** (cancellazioni, modifiche di sistema) non partono
da soli: compare una **finestra nel mondo** con il comando esatto e il motivo,
e decidi tu — *Approva* o *Nega*. I comandi **fidati** (`Get-*`, `git`,
`python`, `dir`…) partono sempre senza chiedere.

### 🔓 Autorizzazione completa

Il pulsante in alto accende un interruttore che fa passare **anche i comandi
distruttivi senza chiedere**. È volontario, vale **solo per la sessione**, e
finché è attivo la pagina mostra una fascia rossa di avviso. Ogni comando
eseguito così resta tracciato nel flusso in diretta.

Consiglio: tienilo spento per il lavoro normale, accendilo solo per
un'operazione che stai seguendo di persona.

## Avatar 3D con Meshy

Ogni agente può avere:
- `avatarImage` → un'immagine usata come **faccia** nel mondo;
- `avatarGlb` → un **modello 3D `.glb`** (es. generato da **Meshy**), mostrato
  nel visore quando clicchi l'agente.

**La chiave Meshy non va mai nella pagina.** Il sito è pubblico: una chiave nel
codice sarebbe visibile a tutti. La generazione va fatta nel **bridge**, dove
la chiave sta in una variabile d'ambiente:
```bash
# Windows PowerShell
$env:MESHY_API_KEY="la-tua-chiave"
```
Il bridge genera il `.glb` e scrive **solo l'URL** nello stato; la pagina legge
l'URL, mai la chiave. In `bridge/ruflo-bridge.mjs` c'è lo scheletro
`generaAvatarMeshy()` da completare.

## I file

| File | A cosa serve |
|---|---|
| `index.html` | Il mondo (pagina) |
| `avvia.mjs` | Server locale + apertura browser + avvio del ponte |
| `bridge/ruflo-bridge.mjs` | Unisce lo stato vivo e l'attività grezza in `state.json` |
| `state.example.json` | Formato dei dati che la pagina si aspetta |
| `AVVIA-WINDOWS.bat` | Avvio con doppio clic su Windows |

File creati a runtime (non versionati): `live.json` (stato scritto
dall'Orchestratore), `inbox.json` (i tuoi messaggi e le approvazioni),
`state.json` (ciò che la pagina legge).

## Note

- Il visore 3D scarica Three.js da internet: offline il mondo 2D funziona
  comunque, il visore mostra un avviso.
- Senza l'Orchestratore avviato, il mondo resta collegato e mostra l'attività
  grezza di `agente.py` (i comandi eseguiti), invitandoti ad avviarlo.

---

# Quartier Generale

Accanto al mondo c'è `gestione.html`: **cassaforte delle chiavi**, **canali di
incasso** e **contabilità dei progetti**. Si apre dal pulsante 🏛️ nel mondo,
oppure su `http://localhost:5178/gestione.html`.

Tutti i dati stanno in `dati/`, **escluso da git**: non finiscono mai nel sito
pubblico.

## 🔑 Cassaforte

Il posto dove metti le chiavi API man mano che le ottieni (Meshy, e qualunque
altra ti serva). Quando un agente ne avrà bisogno, la troverà già pronta.

**Gli agenti non vedono mai i valori.** Le chiavi vengono passate ai comandi
come variabili d'ambiente: l'agente le usa per nome (`$env:MESHY_API_KEY`) e il
valore non entra mai nella conversazione né nei log.

**Come sono protette:**
- cifrate a riposo con AES-256-GCM in `dati/cassaforte.enc`;
- di base la chiave di cifratura sta in `dati/.masterkey` (protegge il file se
  finisce in uno zip o in un repository, non da chi usa il tuo account Windows);
- **con una passphrase** (consigliata se ci tieni credenziali di pagamento) la
  cassaforte parte chiusa a ogni avvio e va aperta a mano. La passphrase non
  viene salvata da nessuna parte: se la dimentichi, le chiavi vanno reinserite.

Le API della cassaforte rispondono **solo a richieste dal computer stesso**.

## 💳 Incassi — Stripe e PayPal

Qui c'è una cosa importante da sapere, e la pagina te la ripete:

**Per farti pagare non serve dare al sistema le chiavi che muovono denaro.**
La chiave segreta live di Stripe (`sk_live_…`) può emettere rimborsi, leggere
tutti i tuoi clienti e disporre trasferimenti.

Serve molto meno:

| Ti serve… | Metti questo | Perché è sicuro |
|---|---|---|
| **Ricevere i soldi** | il **link di pagamento** (Stripe Payment Link, PayPal.me) | sono link pubblici: puoi condividerli senza rischio |
| **Vedere le statistiche** | una **chiave a sola lettura** (Stripe: chiave ristretta `rk_…`) | se te la rubano possono guardare, non toccare |

Se inserisci una chiave `sk_live_`, la cassaforte te la segnala in rosso e ti
dice cosa usare al posto suo.

## 📊 Progetti e contabilità

Ogni progetto ha la sua scheda: entrate, uscite, margine, link di pagamento e
registro dei movimenti. In cima le tessere riassuntive e il grafico
**entrate/uscite degli ultimi 12 mesi** (con tabella equivalente, per chi
preferisce i numeri).

I movimenti possono arrivare a mano, dagli agenti (per esempio il costo dei
crediti consumati) o, in futuro, da Stripe/PayPal collegando una chiave di sola
lettura. Gli importi sono conservati in centesimi interi, così i conti non
soffrono degli errori di arrotondamento dei decimali.

## I file del Quartier Generale

| File | A cosa serve |
|---|---|
| `gestione.html` | La pagina: cassaforte, incassi, progetti |
| `vault.mjs` | Cassaforte cifrata (AES-256-GCM, passphrase con scrypt) |
| `ledger.mjs` | Progetti, movimenti e statistiche |

Dati privati creati a runtime (mai versionati): `dati/cassaforte.enc`,
`dati/.masterkey`, `dati/progetti.json`.
