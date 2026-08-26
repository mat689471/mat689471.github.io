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

I connettori di claude.ai (Gmail, Drive, Calendario…) **non si attaccano qui**:
vivono nel tuo account Claude, non su questo computer, e questo ecosistema parla
solo con i server MCP che girano in locale.

## I tuoi dati restano tuoi

Le cartelle `dati/` (chiavi API, conti, contabilità) e `avatar/` (i modelli 3D
generati) **non stanno nel repository**: restano sul tuo computer. Se rifai il
download in una cartella nuova, copiale dalla vecchia, altrimenti troverai la
cassaforte vuota.
