# L'Ecosistema — il mondo vivente degli agenti di ruflo

Una sede isometrica in cui gli agenti-avatar camminano tra le stanze, lavorano
alle loro postazioni, si scambiano messaggi e riportano i risultati
all'**Orchestratore** (l'agente capo). Pensato per visualizzare il lavoro di
**ruflo** in modo vivo, non come un diagramma.

## Cosa contiene questa cartella

| File | A cosa serve |
|------|--------------|
| `index.html` | Il mondo. Apribile nel browser. Funziona da solo in **modalità demo**. |
| `state.example.json` | Il **formato dei dati** che il mondo si aspetta da ruflo. |
| `bridge/ruflo-bridge.mjs` | Il **ponte**: legge lo stato reale di ruflo e scrive `state.json`. |

## 1. Guardarlo subito (modalità demo)

- Online (una volta pubblicato il sito): **https://mat689471.github.io/mondo/**
- In locale: apri un piccolo server nella cartella del sito e vai su `/mondo/`.
  Esempi (uno qualsiasi):
  ```bash
  npx serve .
  # oppure
  python -m http.server 8000
  ```
  Poi apri `http://localhost:8000/mondo/`.

In demo il mondo simula agenti e task da solo. Il badge in alto dice
**"modalità demo"**.

### Comandi nel mondo
- **Trascina** = sposta la telecamera · **rotella** = zoom
- **Clicca un agente** = apre la scheda con l'**avatar 3D**
- **Pausa**, **velocità** (0.5×/1×/2×), **✦ Nuovo task**

## 2. Collegarlo ai dati reali di ruflo (B)

Il browser non può leggere ruflo direttamente, quindi serve il **bridge**:

1. Assicurati di avere **Node.js 18+**.
2. Avvia il bridge (dalla cartella del sito):
   ```bash
   node mondo/bridge/ruflo-bridge.mjs
   ```
   Questo crea/aggiorna `mondo/state.json`.
3. Apri il mondo con un server locale (vedi sopra). In **modalità "auto"**
   (predefinita) il mondo rileva `state.json` e passa da solo ai dati reali:
   il badge diventa verde **"collegato a ruflo"**.

> Per adesso il bridge produce dati **dimostrativi**. Per usare quelli veri,
> apri `bridge/ruflo-bridge.mjs` e sostituisci la funzione
> `leggiStatoRuflo()` con la lettura reale del tuo ruflo (un comando
> `ruflo ... --json`, la cartella `memoria/` del tuo `agente.py`, o il
> server MCP `claude-flow`). Deve restituire un oggetto nel formato di
> `state.example.json`.

### Configurazione
In cima a `index.html` c'è il blocco `window.ECO_CONFIG`:
```js
source: "auto",          // "auto" | "mock" | "remote"
endpoint: "./state.json",// dove il bridge scrive lo stato reale
pollMs: 2000,            // ogni quanto ricontrollare
proceduralFallback: true // avatar 3D segnaposto quando manca Meshy
```

## 3. Avatar 3D con Meshy (C)

Ogni agente può avere un avatar 3D. Nel formato dati ci sono due campi:
- `avatarImage` → un'immagine usata come **faccia** dell'avatar nel mondo;
- `avatarGlb` → un **modello 3D `.glb`** (es. generato da **Meshy**), mostrato
  nel visore 3D quando clicchi l'agente.

Cliccando un agente si apre una scheda con un **visore 3D** (Three.js): se
c'è un `avatarGlb` carica il modello vero; altrimenti mostra un segnaposto 3D
nel colore dell'agente.

### ⚠️ La chiave API Meshy NON va nella pagina
Questo sito è pubblico: una chiave nel codice sarebbe visibile a tutti.
La generazione con Meshy va fatta nel **bridge** (sul tuo PC), dove la chiave
sta in una variabile d'ambiente:
```bash
# Windows PowerShell
$env:MESHY_API_KEY="la-tua-chiave"
# Mac/Linux
export MESHY_API_KEY="la-tua-chiave"
```
Il bridge genera il `.glb`, lo carica da qualche parte e scrive **solo l'URL**
dentro `state.json`. La pagina legge l'URL, mai la chiave. Nel file
`ruflo-bridge.mjs` trovi lo scheletro `generaAvatarMeshy()` da completare.

### Il flusso completo che immagini
1. In ruflo crei un nuovo agente (con la tua chiave Meshy configurata).
2. Il bridge chiede a Meshy l'avatar 3D → ottiene un `.glb`.
3. Il bridge scrive l'agente e l'URL del `.glb` in `state.json`.
4. Il mondo mostra il nuovo agente che si muove, e il suo avatar 3D al click.

## Note
- Il visore 3D richiede la connessione a internet (carica la libreria Three.js).
  Se sei offline, il mondo 2D funziona comunque; il visore mostra un avviso.
- Nessun dato lascia il tuo PC: il bridge scrive un file locale, il mondo lo legge.
