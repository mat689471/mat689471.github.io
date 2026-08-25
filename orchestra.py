# -*- coding: utf-8 -*-
"""
orchestra.py - Orchestrazione multi-agente per il mondo "L'Ecosistema".

Modello di lavoro (voluto dall'utente):
  Tu  ->  ORCHESTRATORE  ->  agenti specialisti  ->  ORCHESTRATORE  ->  Tu

Nessun agente parla direttamente con l'utente: ogni messaggio arriva
all'Orchestratore, che decide chi far lavorare, in che ordine, e che cosa
rispondere. Gli specialisti nascono su richiesta dell'Orchestratore e
compaiono nel mondo nella stanza del proprio ruolo.

Scambio file con la pagina web:
  mondo/live.json   <- scritto da qui  (stato vivo: agenti, chat, progressi)
  mondo/inbox.json  -> scritto dalla pagina (messaggi, approvazioni, toggle)

Sicurezza: i comandi distruttivi chiedono approvazione NEL MONDO. L'utente
puo' accendere "autorizzazione completa" (interruttore volontario, valido
solo per la sessione corrente) per farli passare senza chiedere.
"""

import io
import os
import json
import time
import threading
from datetime import datetime

import agente  # riusa esecuzione comandi, log e classificazione

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONDO_DIR = os.path.join(BASE_DIR, "mondo")
FILE_LIVE = os.path.join(MONDO_DIR, "live.json")
FILE_INBOX = os.path.join(MONDO_DIR, "inbox.json")

# Ruolo -> (nome visualizzato, colore, stanza)
RUOLI = {
    "code":     (u"Sviluppatore",   "#35d0d6"),
    "design":   (u"Architetto",     "#9d7bff"),
    "qa":       (u"Tester",         "#4ce0a5"),
    "research": (u"Ricercatore",    "#ff9f6b"),
    "review":   (u"Revisore",       "#6aa8ff"),
    "docs":     (u"Documentatore",  "#ff7ac4"),
}

MAX_PASSI_AGENTE = 14      # quanti giri puo' fare uno specialista
MAX_PASSI_ORCHESTRATORE = 16
TIMEOUT_APPROVAZIONE = 300  # secondi di attesa per un'approvazione dal mondo


# ---------------------------------------------------------------------------
# Stato condiviso con la pagina web
# ---------------------------------------------------------------------------

class Mondo(object):
    """Tiene lo stato vivo dell'ecosistema e lo pubblica su live.json."""

    def __init__(self):
        self._lock = threading.RLock()
        self.agenti = {}          # id -> dict
        self.chat = []            # messaggi mostrati nella Sala Comando
        self.eventi = []          # log breve per il flusso in diretta
        self.handoff = []         # passaggi di lavoro tra agenti
        self.pending = None       # approvazione in attesa
        self.fullaccess = False   # interruttore autorizzazione completa
        self.resoconto = None     # ultimo resoconto richiesto
        self.lavori = []          # storico dei task per il resoconto
        self.boss = {"id": "boss", "name": u"Orchestratore",
                     "status": "idle", "task": None, "thinking": None}
        self._ultimo_id_inbox = self._id_inbox_corrente()
        os.makedirs(MONDO_DIR, exist_ok=True)
        self.pubblica()

    # -- utilita' ----------------------------------------------------------
    @staticmethod
    def _ora():
        return datetime.now().strftime("%H:%M:%S")

    def _id_inbox_corrente(self):
        try:
            with io.open(FILE_INBOX, "r", encoding="utf-8") as f:
                voci = json.load(f).get("items", [])
            return max([v.get("id", 0) for v in voci]) if voci else 0
        except (OSError, ValueError):
            return 0

    # -- pubblicazione -----------------------------------------------------
    def pubblica(self):
        with self._lock:
            dati = {
                "boss": self.boss,
                "agents": list(self.agenti.values()),
                "chat": self.chat[-40:],
                "events": list(reversed(self.eventi[-40:])),
                "handoffs": self.handoff[-6:],
                "pending": self.pending,
                "fullaccess": self.fullaccess,
                "report": self.resoconto,
                "stats": {
                    "done": len([l for l in self.lavori if l.get("fatto")]),
                    "messages": len(self.chat),
                },
                "_generatoIl": datetime.now().isoformat(),
                # marca temporale assoluta: il ponte la usa per capire se
                # l'orchestratore e' ancora vivo, senza dipendere dal fuso.
                "_epoch": int(time.time() * 1000),
            }
            tmp = FILE_LIVE + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(dati, ensure_ascii=False, indent=2))
            os.replace(tmp, FILE_LIVE)

    # -- chat / eventi -----------------------------------------------------
    def dico(self, chi, testo, ruolo="boss", colore="#f5b942"):
        with self._lock:
            self.chat.append({"id": int(time.time() * 1000) % 10**9,
                              "from": chi, "role": ruolo, "color": colore,
                              "text": testo, "ts": self._ora()})
        self.pubblica()

    def evento(self, chi, testo, colore="#8a96b3"):
        with self._lock:
            self.eventi.append({"ts": self._ora(), "who": chi,
                                "msg": testo, "color": colore})
        self.pubblica()

    def pensa(self, testo):
        with self._lock:
            self.boss["thinking"] = testo
            self.boss["status"] = "thinking"
        self.pubblica()

    def boss_stato(self, stato, task=None):
        with self._lock:
            self.boss["status"] = stato
            if task is not None:
                self.boss["task"] = task
        self.pubblica()

    # -- agenti ------------------------------------------------------------
    def crea_agente(self, ruolo, nome=None):
        ruolo = (ruolo or "code").lower()
        if ruolo not in RUOLI:
            ruolo = "code"
        nome_def, colore = RUOLI[ruolo]
        aid = ruolo
        with self._lock:
            if aid in self.agenti:
                return self.agenti[aid]
            self.agenti[aid] = {
                "id": aid, "role": ruolo, "name": nome or nome_def,
                "color": colore, "status": "idle", "task": None,
                "progress": 0, "preview": None, "message": None,
                "nato": self._ora(),
            }
        self.evento(nome or nome_def, u"e' entrato nell'ecosistema", colore)
        self.pubblica()
        return self.agenti[aid]

    def agg(self, aid, **campi):
        with self._lock:
            if aid in self.agenti:
                self.agenti[aid].update(campi)
        self.pubblica()

    def passaggio(self, da, a, cosa):
        with self._lock:
            self.handoff.append({"from": da, "to": a, "what": cosa,
                                 "ts": time.time()})
        self.evento(da, u"passa a {}: {}".format(a, cosa), "#ff7ac4")

    # -- inbox dalla pagina ------------------------------------------------
    def _leggi_inbox(self):
        try:
            with io.open(FILE_INBOX, "r", encoding="utf-8") as f:
                return json.load(f).get("items", [])
        except (OSError, ValueError):
            return []

    def nuovi_comandi(self):
        """Ritorna le voci nuove arrivate dalla pagina, in ordine."""
        voci = [v for v in self._leggi_inbox()
                if v.get("id", 0) > self._ultimo_id_inbox]
        voci.sort(key=lambda v: v.get("id", 0))
        if voci:
            self._ultimo_id_inbox = voci[-1]["id"]
        for v in voci:
            if v.get("type") == "fullaccess":
                self.fullaccess = bool(v.get("value"))
                self.evento(u"Tu",
                            u"autorizzazione completa " + (u"ATTIVATA" if self.fullaccess else u"disattivata"),
                            "#ff9f6b" if self.fullaccess else "#8a96b3")
                self.pubblica()
        return voci

    # -- approvazioni ------------------------------------------------------
    def chiedi_approvazione(self, comando, motivo):
        """Mostra la richiesta nel mondo e attende Approva/Nega. True se ok."""
        if self.fullaccess:
            self.evento(u"Sistema",
                        u"autorizzazione completa: eseguo senza chiedere",
                        "#ff9f6b")
            return True
        rid = int(time.time() * 1000)
        with self._lock:
            self.pending = {"id": rid, "command": comando, "reason": motivo}
        self.dico(u"Orchestratore",
                  u"Serve la tua autorizzazione per: " + motivo,
                  "boss", "#f5b942")
        self.pubblica()
        scadenza = time.time() + TIMEOUT_APPROVAZIONE
        esito = False
        while time.time() < scadenza:
            for v in self.nuovi_comandi():
                if v.get("type") in ("approve", "deny"):
                    esito = (v.get("type") == "approve")
                    scadenza = 0
                    break
            if scadenza == 0:
                break
            time.sleep(0.4)
        with self._lock:
            self.pending = None
        self.evento(u"Tu", u"approvato" if esito else u"negato",
                    "#4ce0a5" if esito else "#ff9f6b")
        self.pubblica()
        return esito


MONDO = None  # istanza globale, impostata da avvia()


# ---------------------------------------------------------------------------
# Strumenti degli agenti specialisti
# ---------------------------------------------------------------------------

TOOLS_SPECIALISTA = [
    {
        "name": "esegui_comando",
        "description": (u"Esegue UN comando PowerShell sul PC dell'utente. "
                        u"I comandi non distruttivi partono subito; quelli "
                        u"distruttivi chiedono approvazione all'utente."),
        "input_schema": {"type": "object",
                         "properties": {"comando": {"type": "string"}},
                         "required": ["comando"]},
    },
    {
        "name": "avanzamento",
        "description": u"Aggiorna la barra di avanzamento del tuo lavoro (0-100) e cosa stai facendo.",
        "input_schema": {"type": "object",
                         "properties": {"percentuale": {"type": "number"},
                                        "cosa": {"type": "string"}},
                         "required": ["percentuale"]},
    },
    {
        "name": "anteprima",
        "description": (u"Mostra all'utente un'anteprima del lavoro (testo, codice, "
                        u"elenco). Usala quando produci qualcosa di consultabile."),
        "input_schema": {"type": "object",
                         "properties": {"titolo": {"type": "string"},
                                        "contenuto": {"type": "string"}},
                         "required": ["titolo", "contenuto"]},
    },
    {
        "name": "consegna",
        "description": u"Consegna il risultato all'Orchestratore e termina il tuo compito.",
        "input_schema": {"type": "object",
                         "properties": {"riepilogo": {"type": "string"}},
                         "required": ["riepilogo"]},
    },
]


def _prompt_specialista(ruolo, nome):
    return u"\n".join([
        u"Sei '{}', un agente specialista ({}) dentro l'ecosistema di lavoro dell'utente.".format(nome, ruolo),
        u"Lavori su Windows con PowerShell. Ricevi istruzioni dall'ORCHESTRATORE, non dall'utente.",
        u"Esegui un comando alla volta con 'esegui_comando' e osserva l'output.",
        u"Aggiorna spesso 'avanzamento' cosi' l'utente vede a che punto sei.",
        u"Se produci qualcosa di consultabile (elenco, riepilogo, codice) mostralo con 'anteprima'.",
        u"Quando hai finito chiama 'consegna' con un riepilogo chiaro: sara' l'Orchestratore a parlare con l'utente.",
        u"Sii concreto e sintetico. Non chiedere permessi: ci pensa il sistema.",
    ])


def esegui_specialista(client, ruolo, istruzioni, memoria):
    """Fa lavorare un agente specialista. Ritorna il riepilogo consegnato."""
    m = MONDO
    ag = m.crea_agente(ruolo)
    nome, colore = ag["name"], ag["color"]
    m.agg(ag["id"], status="working", task=istruzioni[:90], progress=0.05,
          preview=None)
    m.evento(nome, u"riceve: " + istruzioni[:70], colore)

    messaggi = [{"role": "user", "content": istruzioni}]
    riepilogo = None
    passi = 0

    while passi < MAX_PASSI_AGENTE:
        passi += 1
        risposta = client.messages.create(
            model=agente.MODELLO, max_tokens=2048,
            system=_prompt_specialista(ruolo, nome),
            tools=TOOLS_SPECIALISTA, messages=messaggi,
        )
        messaggi.append({"role": "assistant", "content": risposta.content})

        if risposta.stop_reason != "tool_use":
            testo = u" ".join([b.text for b in risposta.content
                               if b.type == "text"]).strip()
            riepilogo = testo or u"(nessun risultato)"
            break

        risultati = []
        finito = False
        for b in risposta.content:
            if b.type != "tool_use":
                continue
            args = b.input or {}

            if b.name == "esegui_comando":
                cmd = args.get("comando", "")
                m.agg(ag["id"], message=cmd[:60],
                      progress=min(0.9, 0.1 + passi / float(MAX_PASSI_AGENTE)))
                m.evento(nome, u"$ " + cmd[:70], colore)
                esito = agente.gestisci_esecuzione(cmd)
                contenuto = json.dumps(esito, ensure_ascii=False)[:6000]

            elif b.name == "avanzamento":
                p = max(0.0, min(100.0, float(args.get("percentuale", 0)))) / 100.0
                m.agg(ag["id"], progress=p, message=args.get("cosa") or None)
                contenuto = json.dumps({"ok": True})

            elif b.name == "anteprima":
                m.agg(ag["id"], preview={"title": args.get("titolo", ""),
                                         "body": (args.get("contenuto") or "")[:4000],
                                         "agent": nome, "color": colore})
                m.evento(nome, u"anteprima: " + args.get("titolo", ""), colore)
                contenuto = json.dumps({"ok": True})

            elif b.name == "consegna":
                riepilogo = args.get("riepilogo", "")
                finito = True
                contenuto = json.dumps({"ok": True})

            else:
                contenuto = json.dumps({"errore": "tool sconosciuto"})

            risultati.append({"type": "tool_result", "tool_use_id": b.id,
                              "content": contenuto})

        messaggi.append({"role": "user", "content": risultati})
        if finito:
            break

    if riepilogo is None:
        riepilogo = u"(limite di passi raggiunto)"

    m.agg(ag["id"], status="delivering", progress=1.0, message=None)
    m.passaggio(nome, u"Orchestratore", u"consegna il risultato")
    m.lavori.append({"agente": nome, "ruolo": ruolo, "task": istruzioni,
                     "esito": riepilogo, "fatto": True, "ts": m._ora()})
    time.sleep(1.2)  # tempo per vedere l'animazione della consegna
    m.agg(ag["id"], status="idle", task=None, progress=0)
    return riepilogo


# ---------------------------------------------------------------------------
# Orchestratore
# ---------------------------------------------------------------------------

TOOLS_ORCHESTRATORE = [
    {
        "name": "assegna",
        "description": (u"Assegna un compito a un agente specialista. Se l'agente "
                        u"per quel ruolo non esiste ancora viene creato. Ritorna il "
                        u"riepilogo del lavoro svolto."),
        "input_schema": {
            "type": "object",
            "properties": {
                "ruolo": {"type": "string",
                          "enum": list(RUOLI.keys()),
                          "description": u"code=sviluppo, design=architettura, qa=test, research=ricerca, review=revisione, docs=documentazione"},
                "istruzioni": {"type": "string",
                               "description": u"Cosa deve fare, in modo autosufficiente e concreto."},
            },
            "required": ["ruolo", "istruzioni"],
        },
    },
    {
        "name": "rispondi",
        "description": u"Parla all'utente nella Sala Comando. Usalo per rispondere o chiedere chiarimenti.",
        "input_schema": {"type": "object",
                         "properties": {"testo": {"type": "string"}},
                         "required": ["testo"]},
    },
    {
        "name": "resoconto",
        "description": u"Produce un resoconto del lavoro svolto finora dagli agenti e lo mostra all'utente.",
        "input_schema": {"type": "object",
                         "properties": {"testo": {"type": "string",
                                                  "description": u"Il resoconto, in markdown breve."}},
                         "required": ["testo"]},
    },
]


def _prompt_orchestratore(memoria):
    testo = [
        u"Sei l'ORCHESTRATORE dell'ecosistema di agenti dell'utente, su Windows/PowerShell.",
        u"Sei l'unico che parla con l'utente: gli specialisti riferiscono solo a te.",
        u"Regole di lavoro:",
        u"- Ogni messaggio dell'utente arriva a te. Decidi tu come procedere.",
        u"- Per compiti operativi usa 'assegna' scegliendo il ruolo giusto; puoi assegnare",
        u"  piu' compiti in sequenza e far collaborare piu' agenti sullo stesso obiettivo.",
        u"- Spezza gli obiettivi complessi in compiti chiari, uno per agente.",
        u"- Per domande semplici o conversazione rispondi direttamente con 'rispondi',",
        u"  senza scomodare nessun agente.",
        u"- Quando l'utente chiede un resoconto/riepilogo del lavoro, usa 'resoconto'.",
        u"- Chiudi SEMPRE il turno con 'rispondi' (o 'resoconto'), riassumendo all'utente",
        u"  cosa e' stato fatto. Parla in italiano, chiaro e breve.",
        u"Ruoli disponibili: " + u", ".join([u"{} ({})".format(k, v[0]) for k, v in RUOLI.items()]),
    ]
    if memoria.get("fatti"):
        testo.append(u"\n--- Memoria ---")
        for k, v in memoria["fatti"].items():
            testo.append(u"- {}: {}".format(k, v))
    return u"\n".join(testo)


def gestisci_messaggio(client, memoria, testo_utente, storico):
    """Un giro completo: messaggio utente -> Orchestratore -> agenti -> risposta."""
    m = MONDO
    m.dico(u"Tu", testo_utente, "user", "#e9edf8")
    m.boss_stato("thinking", testo_utente[:80])
    m.pensa(u"sto decidendo come procedere…")

    storico.append({"role": "user", "content": testo_utente})
    system = _prompt_orchestratore(memoria)
    passi = 0

    while passi < MAX_PASSI_ORCHESTRATORE:
        passi += 1
        risposta = client.messages.create(
            model=agente.MODELLO, max_tokens=2048, system=system,
            tools=TOOLS_ORCHESTRATORE, messages=storico,
        )
        storico.append({"role": "assistant", "content": risposta.content})

        if risposta.stop_reason != "tool_use":
            testo = u" ".join([b.text for b in risposta.content
                               if b.type == "text"]).strip()
            if testo:
                m.dico(u"Orchestratore", testo, "boss", "#f5b942")
            break

        risultati = []
        for b in risposta.content:
            if b.type != "tool_use":
                continue
            args = b.input or {}

            if b.name == "assegna":
                ruolo = args.get("ruolo", "code")
                istr = args.get("istruzioni", "")
                nome = RUOLI.get(ruolo, (ruolo, "#8a96b3"))[0]
                m.boss_stato("dispatching", istr[:80])
                m.pensa(u"assegno a " + nome)
                m.passaggio(u"Orchestratore", nome, istr[:60])
                esito = esegui_specialista(client, ruolo, istr, memoria)
                m.boss_stato("thinking")
                contenuto = json.dumps({"agente": nome, "risultato": esito},
                                       ensure_ascii=False)[:6000]

            elif b.name == "rispondi":
                m.dico(u"Orchestratore", args.get("testo", ""), "boss", "#f5b942")
                contenuto = json.dumps({"ok": True})

            elif b.name == "resoconto":
                with MONDO._lock:
                    MONDO.resoconto = {"text": args.get("testo", ""),
                                       "ts": MONDO._ora()}
                m.dico(u"Orchestratore", u"Ecco il resoconto del lavoro.",
                       "boss", "#f5b942")
                m.pubblica()
                contenuto = json.dumps({"ok": True})

            else:
                contenuto = json.dumps({"errore": "tool sconosciuto"})

            risultati.append({"type": "tool_result", "tool_use_id": b.id,
                              "content": contenuto})

        storico.append({"role": "user", "content": risultati})

    m.boss_stato("idle", None)
    m.pensa(None)
    # tieni lo storico entro limiti ragionevoli
    if len(storico) > 40:
        del storico[:len(storico) - 40]


# ---------------------------------------------------------------------------
# Avvio
# ---------------------------------------------------------------------------

def avvia(client, memoria):
    """Ciclo principale: ascolta la Sala Comando del mondo."""
    global MONDO
    MONDO = Mondo()
    # instrada le conferme dei comandi distruttivi verso il mondo
    agente.CHIEDI_CONFERMA_HOOK = MONDO.chiedi_approvazione

    print(u"\n Ecosistema avviato. L'Orchestratore e' in ascolto.")
    print(u" Apri il mondo e scrivi nella Sala Comando. Ctrl+C per uscire.\n")
    MONDO.dico(u"Orchestratore",
               u"Ecosistema online. Dimmi cosa ti serve: decido io chi mettere al lavoro.",
               "boss", "#f5b942")

    storico = []
    while True:
        try:
            for v in MONDO.nuovi_comandi():
                if v.get("type") == "message" and (v.get("text") or "").strip():
                    testo = v["text"].strip()
                    print(u"\n[dal mondo] {}".format(testo))
                    try:
                        gestisci_messaggio(client, memoria, testo, storico)
                    except Exception as e:
                        MONDO.dico(u"Orchestratore",
                                   u"Ho avuto un problema: {}".format(e),
                                   "boss", "#ff9f6b")
                        print(u"[errore] {}".format(e))
            time.sleep(0.6)
        except (EOFError, KeyboardInterrupt):
            print(u"\nChiusura dell'ecosistema.")
            break
