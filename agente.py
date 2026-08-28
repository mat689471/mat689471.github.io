# -*- coding: utf-8 -*-
"""
agente.py - Agente autonomo da terminale per Windows 10/11 (shell PowerShell).

Lancio:      python agente.py
Dipendenza:  anthropic (pip install anthropic)
Chiave API:  variabile d'ambiente ANTHROPIC_API_KEY

L'agente riceve un obiettivo, propone ed esegue comandi PowerShell uno alla volta
in autonomia. I comandi NON distruttivi partono subito; quelli distruttivi vengono
mostrati e richiedono conferma [s/n] prima di essere eseguiti.

Modalita' ECOSISTEMA:
    python agente.py --mondo

Passa il controllo a orchestra.py: l'ORCHESTRATORE riceve i tuoi messaggi
dalla Sala Comando della pagina web, crea gli agenti specialisti che servono,
li coordina e ti risponde. Le conferme dei comandi distruttivi vengono chieste
nel mondo invece che nel terminale.
"""

import io
import os
import re
import sys
import json
import time
import subprocess
from datetime import datetime

try:
    import anthropic
except ImportError:
    # Su Windows convivono spesso due Python ('py' e 'python'): la libreria
    # puo' essere installata sull'altro. Nominare l'interprete che sta girando
    # toglie ogni dubbio su dove vada installata.
    print("")
    print("Manca la libreria 'anthropic' per questo Python:")
    print("  " + sys.executable)
    print("")
    print("Installala con questo comando, copiato cosi' com'e':")
    print('  "%s" -m pip install anthropic' % sys.executable)
    print("")
    sys.exit(1)


# ---------------------------------------------------------------------------
# Costanti e percorsi
# ---------------------------------------------------------------------------

MODELLO = "claude-opus-4-8"
# Alcuni comandi legittimi sono lenti: scaricare un modello 3D da decine di MB
# supera facilmente il minuto e mezzo. Meglio dare respiro che troncare lavoro
# buono a meta'.
TIMEOUT_COMANDO = 240  # secondi

# Percorsi ancorati alla cartella del file sorgente, così l'agente funziona
# indipendentemente dalla directory da cui viene lanciato.
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARTELLA_MEMORIA = os.path.join(BASE_DIR, "memoria")
FILE_MEMORIA = os.path.join(CARTELLA_MEMORIA, "memoria.json")
CARTELLA_SKILLS = os.path.join(BASE_DIR, "skills")
FILE_LOG = os.path.join(BASE_DIR, "agent_log.txt")

# Vincolo di stabilità: l'agente non deve mai riscrivere il proprio sorgente
# mentre gira. Custodiamo il nome del file per bloccare eventuali tentativi.
FILE_SORGENTE = os.path.basename(os.path.abspath(__file__))

# Cartella del mondo "L'Ecosistema". Con 'python agente.py --mondo' il
# controllo passa a orchestra.py, che dialoga con la pagina web tramite i
# file dentro questa cartella (live.json e inbox.json).
MONDO_DIR = os.path.join(BASE_DIR, "mondo")

# Chiavi prelevate dalla Cassaforte e passate ai comandi come variabili
# d'ambiente. Popolato da orchestra.py all'avvio: gli agenti conoscono solo
# i NOMI, mai i valori.
AMBIENTE_CASSAFORTE = {}


# ===========================================================================
# CLASSIFICAZIONE COMANDI DISTRUTTIVI
# ---------------------------------------------------------------------------
# Funzione isolata: riceve la stringa del comando e ritorna True se il comando
# è considerato DISTRUTTIVO, False se NORMALE. Il confronto è case-insensitive.
# Filosofia: nel dubbio -> distruttivo. Meglio una conferma di troppo che una
# cancellazione non voluta.
# ===========================================================================

# Elenco di pattern regex, ciascuno con una breve etichetta descrittiva.
# \b = confine di parola, così "del" non scatta dentro "Get-ChildItem" e simili.
_PATTERN_DISTRUTTIVI = [
    (r"\bRemove-Item\b",        "Remove-Item (cancella file/cartelle)"),
    (r"\bRemove-ItemProperty\b","Remove-ItemProperty (rimuove proprieta' del registro)"),
    (r"\bClear-Content\b",      "Clear-Content (svuota il contenuto di un file)"),
    (r"\bdel\b",                "del (cancella file)"),
    (r"\berase\b",              "erase (cancella file)"),
    (r"\brmdir\b",              "rmdir (rimuove cartelle)"),
    (r"\brd\b",                 "rd (rimuove cartelle)"),
    (r"\brm\b",                 "rm (alias di Remove-Item)"),
    # 'format C:' formatta davvero un volume; 'Format-Table' non c'entra nulla,
    # quindi pretendiamo la lettera di unita' subito dopo.
    (r"\bformat(?:\.com)?\s+[A-Za-z]:", "format (formatta un volume)"),
    (r"\bFormat-Volume\b",      "Format-Volume (formatta un volume)"),
    (r"\breg\s+delete\b",       "reg delete (cancella chiavi di registro)"),
    (r"\bStop-Process\b",       "Stop-Process (termina processi)"),
    (r"\btaskkill\b",           "taskkill (termina processi)"),
    (r"\bSet-ExecutionPolicy\b","Set-ExecutionPolicy (cambia policy di esecuzione)"),
    # Redirezione '>' che sovrascrive un file. Escludiamo le freccine '->',
    # l'append '>>', i confronti '-ge'/'>=' e le redirezioni di flusso '2>':
    # comparivano in stringhe di messaggio e facevano scattare falsi allarmi.
    (r"(?<![-<>=!0-9])>(?!>)",  "redirect > su file (sovrascrive)"),
    # '-Force' e '-Recurse' da soli non dicono nulla: 'New-Item -Force' crea una
    # cartella, non distrugge niente. Sono rischiosi quando accompagnano un
    # comando che puo' sovrascrivere dati gia' esistenti.
    (r"\b(?:Copy|Move|Rename)-Item\b[^\n]*-Force\b", "sovrascrive la destinazione (-Force)"),
    (r"\bSet-Content\b[^\n]*-Force\b",               "sovrascrive un file (-Force)"),
]

# Precompiliamo i pattern in modo case-insensitive per efficienza e chiarezza.
_REGEX_DISTRUTTIVI = [(re.compile(p, re.IGNORECASE), etichetta)
                      for p, etichetta in _PATTERN_DISTRUTTIVI]

# ---------------------------------------------------------------------------
# Comandi FIDATI: prefissi considerati SEMPRE sicuri. Se un comando inizia con
# uno di questi (spazi iniziali ignorati), viene eseguito senza mai chiedere
# conferma, anche se contenesse flag che altrimenti sembrerebbero rischiosi
# (es. Get-ChildItem -Recurse, di sola lettura). Aggiungi qui i comandi che
# usi spesso e di cui ti fidi. NON mettere qui comandi che cancellano/formattano.
# ---------------------------------------------------------------------------
COMANDI_FIDATI = [
    r"Get-\w+",                                   # tutti i Get-* (sola lettura)
    r"dir\b", r"ls\b", r"pwd\b", r"cd\b",
    r"echo\b", r"cat\b", r"type\b", r"more\b",
    r"python\b", r"pip\b", r"node\b", r"npm\b", r"git\b",
    r"Test-\w+", r"Measure-\w+", r"Select-\w+", r"Where-\w+", r"Sort-\w+",
    r"Write-Output\b", r"Write-Host\b", r"Out-\w+",
]
_REGEX_FIDATI = [re.compile(r"^\s*" + p, re.IGNORECASE) for p in COMANDI_FIDATI]


def classifica_comando(comando):
    """
    Classifica un comando come distruttivo o normale.

    Parametri:
        comando (str): la riga di comando PowerShell da valutare.

    Ritorna:
        (bool, str|None): (True, motivo) se distruttivo, (False, None) se normale.
    """
    if not comando or not comando.strip():
        return (False, None)

    # I pattern distruttivi vengono PRIMA della lista fidata: un comando puo'
    # cominciare in modo innocuo e finire male ('Get-Date > file' sovrascrive,
    # 'Get-ChildItem | Remove-Item' cancella). Chi apre il comando non decide
    # da solo che l'intera riga e' sicura.
    for regex, etichetta in _REGEX_DISTRUTTIVI:
        if regex.search(comando):
            return (True, etichetta)

    # Nessun pericolo trovato: i comandi fidati sono la conferma esplicita che
    # quella riga e' di uso quotidiano e non va messa in discussione.
    for regex in _REGEX_FIDATI:
        if regex.search(comando):
            return (False, None)

    return (False, None)

# ===========================================================================
# FINE blocco classificazione
# ===========================================================================


# ---------------------------------------------------------------------------
# Memoria persistente
# ---------------------------------------------------------------------------

def carica_memoria():
    """Legge memoria/memoria.json (utf-8) e ritorna un dizionario. Se manca, {}."""
    if not os.path.exists(FILE_MEMORIA):
        return {}
    try:
        with io.open(FILE_MEMORIA, "r", encoding="utf-8") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError):
        return {}


def salva_memoria(memoria):
    """Scrive il dizionario memoria su disco in utf-8, formattato e leggibile."""
    os.makedirs(CARTELLA_MEMORIA, exist_ok=True)
    with io.open(FILE_MEMORIA, "w", encoding="utf-8") as f:
        json.dump(memoria, f, ensure_ascii=False, indent=2)


def aggiungi_fatto(memoria, chiave, valore):
    """L'agente usa questo per memorizzare un fatto/preferenza sotto una chiave."""
    fatti = memoria.setdefault("fatti", {})
    fatti[str(chiave)] = valore
    salva_memoria(memoria)


# ---------------------------------------------------------------------------
# Skills persistenti
# ---------------------------------------------------------------------------

def estrai_descrizione_skill(percorso):
    """
    Legge le prime righe di uno script skill e ricava la descrizione dal commento
    di intestazione (righe che iniziano con # contenenti 'descrizione' o 'desc').
    Ritorna una stringa breve.
    """
    try:
        with io.open(percorso, "r", encoding="utf-8") as f:
            righe = [next(f, "") for _ in range(6)]
    except OSError:
        return "(descrizione non disponibile)"

    for r in righe:
        r_strip = r.strip()
        if r_strip.startswith("#") and re.search(r"descriz", r_strip, re.IGNORECASE):
            # Prende la parte dopo i due punti, se presente.
            parti = r_strip.lstrip("#").split(":", 1)
            if len(parti) == 2:
                return parti[1].strip()
    return "(nessuna descrizione)"


def elenca_skills():
    """Ritorna una lista di tuple (nome_file, descrizione) per le skill presenti."""
    if not os.path.isdir(CARTELLA_SKILLS):
        return []
    skills = []
    for nome in sorted(os.listdir(CARTELLA_SKILLS)):
        percorso = os.path.join(CARTELLA_SKILLS, nome)
        if os.path.isfile(percorso):
            skills.append((nome, estrai_descrizione_skill(percorso)))
    return skills


def salva_skill(nome_file, descrizione, codice):
    """
    Salva uno script skill in skills/ aggiungendo in cima un commento con
    nome, descrizione e data. Ritorna il percorso del file salvato.
    """
    os.makedirs(CARTELLA_SKILLS, exist_ok=True)
    if not nome_file.endswith(".py"):
        nome_file += ".py"
    percorso = os.path.join(CARTELLA_SKILLS, nome_file)

    intestazione = (
        u"# -*- coding: utf-8 -*-\n"
        u"# Nome: {}\n"
        u"# Descrizione: {}\n"
        u"# Data: {}\n\n"
    ).format(nome_file, descrizione, datetime.now().strftime("%Y-%m-%d"))

    with io.open(percorso, "w", encoding="utf-8") as f:
        f.write(intestazione)
        f.write(codice)
    return percorso


def leggi_skill(nome_file):
    """Ritorna il contenuto testuale di una skill, o None se non esiste."""
    if not nome_file.endswith(".py"):
        nome_file += ".py"
    percorso = os.path.join(CARTELLA_SKILLS, nome_file)
    if not os.path.isfile(percorso):
        return None
    with io.open(percorso, "r", encoding="utf-8") as f:
        return f.read()


# ---------------------------------------------------------------------------
# Log
# ---------------------------------------------------------------------------

def scrivi_log(comando, return_code, distruttivo, confermato):
    """
    Registra un comando eseguito in agent_log.txt con timestamp ISO, il comando,
    il return code, se era distruttivo e se e' stato confermato dall'utente.
    """
    riga = u"{ts}\tRC={rc}\tdistruttivo={d}\tconfermato={c}\tcomando={cmd}\n".format(
        ts=datetime.now().isoformat(),
        rc=return_code,
        d="si" if distruttivo else "no",
        c=("si" if confermato else "no") if distruttivo else "n/a",
        cmd=comando.replace("\n", " ").replace("\t", " "),
    )
    with io.open(FILE_LOG, "a", encoding="utf-8") as f:
        f.write(riga)


# ---------------------------------------------------------------------------
# Esecuzione comandi in PowerShell
# ---------------------------------------------------------------------------

def nascondi_segreti(testo):
    """Toglie dal testo qualunque valore della Cassaforte.

    L'idea era che una chiave usata come $env:NOME non comparisse mai. Non
    basta: PowerShell, quando un comando e' scritto male, rimanda indietro la
    riga GIA' ESPANSA - e la chiave finisce nel terminale, nel log e sotto gli
    occhi di chiunque guardi lo schermo. E' successo davvero con la chiave
    Anthropic. Quindi ogni riga che esce da un comando passa da qui prima di
    essere stampata, mandata al modello o scritta da qualche parte.
    """
    if not testo:
        return testo
    for nome, valore in AMBIENTE_CASSAFORTE.items():
        v = (valore or "").strip()
        if len(v) >= 8 and v in testo:
            testo = testo.replace(v, u"\u00ab{} nascosta\u00bb".format(nome))
    return testo


def _ripulisci(esito):
    """Un solo punto di passaggio: nessun esito esce senza essere ripulito."""
    esito["stdout"] = nascondi_segreti(esito.get("stdout", ""))
    esito["stderr"] = nascondi_segreti(esito.get("stderr", ""))
    return esito


def esegui_powershell(comando):
    """
    Esegue un comando tramite PowerShell catturando stdout, stderr e return code.
    Timeout di 90 secondi: allo scadere il processo viene terminato (kill).

    Le chiavi custodite nella Cassaforte vengono passate come variabili
    d'ambiente: il comando puo' usarle con $env:NOME senza che il valore
    compaia mai nel comando stesso, nel log o nella conversazione.

    Ritorna un dizionario: {stdout, stderr, returncode}.
    """
    ambiente = dict(os.environ)
    ambiente.update(AMBIENTE_CASSAFORTE)
    try:
        proc = subprocess.Popen(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", comando],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding="utf-8",
            errors="replace",
            env=ambiente,
        )
    except FileNotFoundError:
        return {"stdout": "", "stderr": "PowerShell non trovato sul sistema.", "returncode": -1}

    try:
        stdout, stderr = proc.communicate(timeout=TIMEOUT_COMANDO)
        return _ripulisci({"stdout": stdout or "", "stderr": stderr or "", "returncode": proc.returncode})
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        return _ripulisci({
            "stdout": stdout or "",
            "stderr": (stderr or "") + "\n[TIMEOUT] Comando terminato dopo {}s.".format(TIMEOUT_COMANDO),
            "returncode": -1,
        })


# Se impostato (dalla modalita' MONDO), le conferme dei comandi distruttivi
# vengono chieste nella pagina web invece che nel terminale.
CHIEDI_CONFERMA_HOOK = None


def chiedi_conferma(motivo, comando=""):
    """Mostra il motivo e chiede conferma [s/n]. Ritorna True su 's'.
    In modalita' MONDO la richiesta viene inoltrata alla pagina web."""
    if CHIEDI_CONFERMA_HOOK is not None:
        print(u"  [ATTENZIONE] Comando distruttivo -> {}".format(motivo))
        print(u"  In attesa della tua approvazione nel mondo...")
        return bool(CHIEDI_CONFERMA_HOOK(comando, motivo))
    try:
        risposta = input(u"  [ATTENZIONE] Comando distruttivo -> {}\n  Eseguo? [s/n]: ".format(motivo))
    except (EOFError, KeyboardInterrupt):
        return False
    return risposta.strip().lower() == "s"


def gestisci_esecuzione(comando):
    """
    Flusso completo per un comando proposto dal modello: stampa, classifica,
    eventuale conferma, esecuzione, log. Ritorna un dizionario con l'esito da
    restituire al modello (include 'saltato' se l'utente ha rifiutato).
    """
    # Vincolo di stabilita': non lasciare che l'agente riscriva il proprio sorgente.
    if FILE_SORGENTE.lower() in comando.lower():
        return {
            "stdout": "",
            "stderr": "Operazione bloccata: l'agente non puo' modificare il proprio file sorgente ({}).".format(FILE_SORGENTE),
            "returncode": -1,
            "saltato": True,
        }

    # anche il comando passa dal filtro: se il modello ci scrive dentro una
    # chiave per sbaglio, non deve finire sullo schermo
    print(u"\n>> COMANDO PROPOSTO:\n   {}".format(nascondi_segreti(comando)))
    distruttivo, motivo = classifica_comando(comando)

    confermato = False
    if distruttivo:
        confermato = chiedi_conferma(motivo, comando)
        if not confermato:
            print(u"   -> Saltato (nessuna conferma).")
            scrivi_log(comando, "n/a", distruttivo, confermato)
            return {"stdout": "", "stderr": "", "returncode": None, "saltato": True}
        print(u"   -> Confermato, eseguo...")
    else:
        print(u"   (non distruttivo) -> eseguo...")

    esito = esegui_powershell(comando)
    scrivi_log(comando, esito["returncode"], distruttivo, confermato)

    print(u"   RC={}".format(esito["returncode"]))
    if esito["stdout"].strip():
        print(u"   --- stdout ---\n{}".format(esito["stdout"].rstrip()))
    if esito["stderr"].strip():
        print(u"   --- stderr ---\n{}".format(esito["stderr"].rstrip()))

    esito["saltato"] = False
    return esito


# ---------------------------------------------------------------------------
# Definizione dei tool esposti al modello
# ---------------------------------------------------------------------------

TOOLS = [
    {
        "name": "esegui_comando",
        "description": (
            "Propone ed esegue UN comando PowerShell sul sistema Windows dell'utente. "
            "I comandi non distruttivi partono subito; quelli distruttivi richiedono "
            "conferma dell'utente. Ritorna stdout, stderr e return code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "comando": {"type": "string", "description": "Il comando PowerShell da eseguire."}
            },
            "required": ["comando"],
        },
    },
    {
        "name": "ricorda",
        "description": (
            "Memorizza in modo permanente un fatto o una preferenza dell'utente, "
            "cosi' da poterlo riusare nelle sessioni future."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "chiave": {"type": "string", "description": "Etichetta breve del fatto."},
                "valore": {"type": "string", "description": "Contenuto del fatto/preferenza."},
            },
            "required": ["chiave", "valore"],
        },
    },
    {
        "name": "salva_skill",
        "description": (
            "Salva uno script Python riutilizzabile nella cartella skills/, cosi' da "
            "poterlo richiamare nelle sessioni future. Usa questo quando serve una "
            "capacita' nuova che vale la pena conservare."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file, es. 'pulisci_temp.py'."},
                "descrizione": {"type": "string", "description": "Cosa fa la skill, in una frase."},
                "codice": {"type": "string", "description": "Il corpo dello script Python."},
            },
            "required": ["nome_file", "descrizione", "codice"],
        },
    },
    {
        "name": "esegui_skill",
        "description": (
            "Esegue una skill salvata in skills/ tramite 'python'. Se la skill "
            "contiene comandi distruttivi verra' chiesta conferma prima di partire. "
            "Ritorna stdout, stderr e return code."
        ),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome_file": {"type": "string", "description": "Nome del file skill da eseguire."}
            },
            "required": ["nome_file"],
        },
    },
    {
        "name": "obiettivo_completato",
        "description": "Segnala che l'obiettivo corrente e' stato raggiunto. Termina il ciclo di lavoro.",
        "input_schema": {
            "type": "object",
            "properties": {
                "riepilogo": {"type": "string", "description": "Breve riepilogo di cosa e' stato fatto."}
            },
            "required": ["riepilogo"],
        },
    },
]


def esegui_skill(nome_file):
    """
    Esegue una skill salvata. Se il suo contenuto contiene comandi distruttivi,
    chiede conferma prima. Ritorna un dizionario con l'esito.
    """
    contenuto = leggi_skill(nome_file)
    if contenuto is None:
        return {"stdout": "", "stderr": "Skill '{}' non trovata.".format(nome_file), "returncode": -1, "saltato": True}

    if not nome_file.endswith(".py"):
        nome_file += ".py"
    percorso = os.path.join(CARTELLA_SKILLS, nome_file)

    distruttivo, motivo = classifica_comando(contenuto)
    confermato = False
    if distruttivo:
        print(u"\n>> La skill '{}' contiene comandi potenzialmente distruttivi.".format(nome_file))
        confermato = chiedi_conferma(motivo, contenuto)
        if not confermato:
            print(u"   -> Skill saltata (nessuna conferma).")
            scrivi_log("SKILL:" + nome_file, "n/a", distruttivo, confermato)
            return {"stdout": "", "stderr": "", "returncode": None, "saltato": True}

    print(u"\n>> Eseguo skill '{}'...".format(nome_file))
    try:
        proc = subprocess.Popen(
            [sys.executable, percorso],
            stdout=subprocess.PIPE, stderr=subprocess.PIPE,
            encoding="utf-8", errors="replace",
        )
        stdout, stderr = proc.communicate(timeout=TIMEOUT_COMANDO)
        esito = _ripulisci({"stdout": stdout or "", "stderr": stderr or "", "returncode": proc.returncode, "saltato": False})
    except subprocess.TimeoutExpired:
        proc.kill()
        stdout, stderr = proc.communicate()
        esito = _ripulisci({"stdout": stdout or "", "stderr": (stderr or "") + "\n[TIMEOUT]", "returncode": -1, "saltato": False})

    scrivi_log("SKILL:" + nome_file, esito["returncode"], distruttivo, confermato)
    print(u"   RC={}".format(esito["returncode"]))
    if esito["stdout"].strip():
        print(u"   --- stdout ---\n{}".format(esito["stdout"].rstrip()))
    if esito["stderr"].strip():
        print(u"   --- stderr ---\n{}".format(esito["stderr"].rstrip()))
    return esito


# ---------------------------------------------------------------------------
# Costruzione del prompt di sistema
# ---------------------------------------------------------------------------

def costruisci_system_prompt(memoria, skills):
    """Compone il messaggio di sistema con memoria e skill disponibili."""
    testo = [
        u"Sei un agente autonomo che opera su un terminale Windows 10/11 con shell PowerShell.",
        u"L'utente ti da' un obiettivo. Tu proponi ed esegui UN comando alla volta tramite il tool 'esegui_comando',",
        u"osservi l'output (stdout, stderr, return code) e decidi il passo successivo.",
        u"Lavori in autonomia senza chiedere permesso: i comandi non distruttivi partono subito,",
        u"mentre quelli distruttivi vengono automaticamente sottoposti a conferma dell'utente dal sistema (non da te).",
        u"Quando impari un fatto o una preferenza utile, salvalo con 'ricorda'.",
        u"Quando ti serve una capacita' riutilizzabile, creala con 'salva_skill' e richiamala con 'esegui_skill'.",
        u"Quando l'obiettivo e' raggiunto, chiama 'obiettivo_completato'.",
        u"Non tentare mai di modificare il file sorgente dell'agente ({}).".format(FILE_SORGENTE),
    ]

    if memoria.get("fatti"):
        testo.append(u"\n--- Memoria (fatti noti) ---")
        for k, v in memoria["fatti"].items():
            testo.append(u"- {}: {}".format(k, v))

    if skills:
        testo.append(u"\n--- Skill disponibili ---")
        for nome, descr in skills:
            testo.append(u"- {}: {}".format(nome, descr))

    return u"\n".join(testo)


# ---------------------------------------------------------------------------
# Ciclo agentico su un singolo obiettivo
# ---------------------------------------------------------------------------

def esegui_obiettivo(client, system_prompt, memoria, obiettivo):
    """Fa lavorare il modello sull'obiettivo finche' non lo completa."""
    messaggi = [{"role": "user", "content": obiettivo}]

    while True:
        risposta = client.messages.create(
            model=MODELLO,
            max_tokens=2048,
            system=system_prompt,
            tools=TOOLS,
            messages=messaggi,
        )

        # Stampa il testo di ragionamento eventuale del modello.
        for blocco in risposta.content:
            if blocco.type == "text" and blocco.text.strip():
                print(u"\n[agente] {}".format(blocco.text.strip()))

        messaggi.append({"role": "assistant", "content": risposta.content})

        if risposta.stop_reason != "tool_use":
            # Il modello non ha chiamato tool: chiudiamo l'obiettivo.
            break

        risultati_tool = []
        completato = False

        for blocco in risposta.content:
            if blocco.type != "tool_use":
                continue

            nome = blocco.name
            args = blocco.input

            if nome == "esegui_comando":
                esito = gestisci_esecuzione(args.get("comando", ""))
                contenuto = json.dumps(esito, ensure_ascii=False)

            elif nome == "ricorda":
                aggiungi_fatto(memoria, args.get("chiave", ""), args.get("valore", ""))
                print(u"\n[memoria] Salvato: {} = {}".format(args.get("chiave"), args.get("valore")))
                contenuto = json.dumps({"ok": True}, ensure_ascii=False)

            elif nome == "salva_skill":
                percorso = salva_skill(args.get("nome_file", "skill"),
                                       args.get("descrizione", ""),
                                       args.get("codice", ""))
                print(u"\n[skill] Salvata in {}".format(percorso))
                contenuto = json.dumps({"ok": True, "percorso": percorso}, ensure_ascii=False)

            elif nome == "esegui_skill":
                esito = esegui_skill(args.get("nome_file", ""))
                contenuto = json.dumps(esito, ensure_ascii=False)

            elif nome == "obiettivo_completato":
                print(u"\n[completato] {}".format(args.get("riepilogo", "")))
                completato = True
                contenuto = json.dumps({"ok": True}, ensure_ascii=False)

            else:
                contenuto = json.dumps({"errore": "tool sconosciuto"}, ensure_ascii=False)

            risultati_tool.append({
                "type": "tool_result",
                "tool_use_id": blocco.id,
                "content": contenuto,
            })

        messaggi.append({"role": "user", "content": risultati_tool})

        if completato:
            break



# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def main():
    # Cervello: chiave API obbligatoria da variabile d'ambiente.
    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        print("ERRORE: la variabile d'ambiente ANTHROPIC_API_KEY non e' impostata.")
        sys.exit(1)

    client = anthropic.Anthropic(api_key=api_key)

    memoria = carica_memoria()
    skills = elenca_skills()

    # Banner di avvio.
    print(u"=" * 64)
    print(u" Agente autonomo da terminale (Windows / PowerShell)")
    print(u"=" * 64)
    print(u" Modello: {}".format(MODELLO))

    print(u"\n Fatti in memoria:")
    if memoria.get("fatti"):
        for k, v in memoria["fatti"].items():
            print(u"   - {}: {}".format(k, v))
    else:
        print(u"   (nessuno)")

    print(u"\n Skill disponibili:")
    if skills:
        for nome, descr in skills:
            print(u"   - {}: {}".format(nome, descr))
    else:
        print(u"   (nessuna)")

    print(u"\n AVVISO: eseguo tutti i comandi da solo, tranne quelli DISTRUTTIVI,")
    print(u"         per i quali chiedo la tua conferma [s/n] prima di procedere.")
    print(u"         (i comandi FIDATI partono sempre senza chiedere).")
    print(u" Scrivi il tuo obiettivo. Scrivi 'stop' per uscire.")
    print(u" Suggerimento: 'python agente.py --mondo' per comandarlo dal mondo web.")
    print(u"=" * 64)

    system_prompt = costruisci_system_prompt(memoria, skills)

    # Modalità MONDO: obiettivi presi dalla casella della pagina web.
    if "--mondo" in sys.argv or "--watch" in sys.argv:
        import orchestra
        orchestra.avvia(client, memoria)
        return

    while True:
        try:
            obiettivo = input(u"\nObiettivo> ").strip()
        except (EOFError, KeyboardInterrupt):
            print(u"\nChiusura.")
            break

        if not obiettivo:
            continue
        if obiettivo.lower() == "stop":
            print(u"Chiusura.")
            break

        try:
            esegui_obiettivo(client, system_prompt, memoria, obiettivo)
        except anthropic.APIError as e:
            print(u"[errore API] {}".format(e))
        except Exception as e:  # nessun crash del loop principale
            print(u"[errore] {}".format(e))


if __name__ == "__main__":
    main()
