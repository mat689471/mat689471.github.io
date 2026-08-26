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

## I tuoi dati restano tuoi

Le cartelle `dati/` (chiavi API, conti, contabilità) e `avatar/` (i modelli 3D
generati) **non stanno nel repository**: restano sul tuo computer. Se rifai il
download in una cartella nuova, copiale dalla vecchia, altrimenti troverai la
cassaforte vuota.
