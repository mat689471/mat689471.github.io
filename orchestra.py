# -*- coding: utf-8 -*-
"""
orchestra.py - Orchestrazione multi-agente per il mondo "L'Ecosistema".

Modello di lavoro:
  Tu  ->  ORCHESTRATORE  ->  agenti specialisti  ->  ORCHESTRATORE  ->  Tu

Nessun agente parla direttamente con l'utente: ogni messaggio arriva
all'Orchestratore, che decide chi far lavorare, in che ordine, e che cosa
rispondere.

Caratteristiche:
  - AGENTI IN PARALLELO. Se l'Orchestratore assegna piu' compiti nello stesso
    turno, gli agenti lavorano contemporaneamente: l'ecosistema si muove
    davvero mentre il PC lavora.
  - AGENTI SU MISURA. Oltre ai ruoli standard, l'Orchestratore puo' creare
    uno specialista per un compito specifico, con nome e competenza sue.
  - PASSAGGI DIRETTI. Un agente puo' consegnare il lavoro a un collega:
    nel mondo li vedi incontrarsi.
  - BATTITO COSTANTE. Lo stato viene ripubblicato di continuo, cosi' il mondo
    resta vivo anche mentre nessuno sta lavorando.
  - MEMORIA CHE RESTA. Ogni conversazione e' una sessione salvata su disco:
    chiudi tutto, riapri, e la ritrovi. Le sessioni interrotte si riprendono.

Scambio file con la pagina web:
  mondo/live.json   <- scritto da qui  (stato vivo)
  mondo/inbox.json  -> scritto dalla pagina (messaggi, approvazioni, comandi)
  dati/sessioni.json <-> memoria persistente delle sessioni
"""

import io
import os
import json
import time
import uuid
import threading
import urllib.request
import urllib.error
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor

import agente       # riusa esecuzione comandi, log e classificazione
import competenze   # le Skill di Claude Code
import mcp          # gli strumenti dei server MCP (ruflo)
import avatar       # gli avatar 3D indossati dagli abitanti


def spiega_errore(e):
    """
    Traduce gli errori del modello in una frase comprensibile.
    Un messaggio criptico fa perdere tempo a cercare il problema dove non e'.
    """
    t = str(e)
    if "credit balance is too low" in t:
        return (u"Il credito dell'API Anthropic e' esaurito. Attenzione: "
                u"l'abbonamento Claude Pro e il credito API sono due cose "
                u"separate — l'ecosistema usa il secondo. Si ricarica su "
                u"console.anthropic.com → Plans & Billing. Non dipende dal "
                u"lavoro in corso.")
    if "rate_limit" in t or "429" in t:
        return u"Troppe richieste in poco tempo: attendi qualche istante e riprova."
    if "authentication" in t.lower() or "invalid x-api-key" in t.lower():
        return (u"La chiave ANTHROPIC_API_KEY non e' valida. Controlla la "
                u"variabile d'ambiente e riavvia l'ecosistema.")
    if "overloaded" in t.lower() or "529" in t:
        return u"Il modello e' momentaneamente sovraccarico: riprovo fra poco."
    return t

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MONDO_DIR = os.path.join(BASE_DIR, "mondo")
DATI_DIR = os.path.join(BASE_DIR, "dati")
FILE_LIVE = os.path.join(MONDO_DIR, "live.json")
FILE_INBOX = os.path.join(MONDO_DIR, "inbox.json")
FILE_SESSIONI = os.path.join(DATI_DIR, "sessioni.json")

# ---------------------------------------------------------------------------
# I ruoli disponibili. Ogni ruolo vive in una stanza del mondo; piu' agenti
# possono condividere la stessa stanza (si dispongono a postazioni diverse).
# ---------------------------------------------------------------------------
RUOLI = {
    "code":      (u"Sviluppatore",   "#35d0d6", "sviluppo",   u"scrive ed esegue codice, script, automazioni"),
    "devops":    (u"Sistemista",     "#22b8cf", "sviluppo",   u"installazioni, servizi, configurazione del sistema"),
    "design":    (u"Architetto",     "#9d7bff", "architettura", u"progetta la struttura, decide come impostare il lavoro"),
    "ux":        (u"Designer",       "#b79bff", "architettura", u"interfacce, esperienza d'uso, aspetto visivo"),
    "qa":        (u"Tester",         "#4ce0a5", "test",       u"verifica che funzioni, cerca errori e casi limite"),
    "security":  (u"Guardiano",      "#3fc78d", "test",       u"controlla sicurezza, permessi, dati sensibili"),
    "research":  (u"Ricercatore",    "#ff9f6b", "laboratorio", u"cerca informazioni, esplora, raccoglie dati"),
    "data":      (u"Analista",       "#ffb787", "laboratorio", u"analizza numeri, produce statistiche e tabelle"),
    "review":    (u"Revisore",       "#6aa8ff", "revisione",  u"rilegge il lavoro altrui e propone miglioramenti"),
    "finance":   (u"Contabile",      "#8dbcff", "revisione",  u"costi, incassi, contabilita' dei progetti"),
    "docs":      (u"Documentatore",  "#ff7ac4", "archivio",   u"scrive documentazione, guide, riepiloghi"),
    "content":   (u"Redattore",      "#ff9dd2", "archivio",   u"testi, comunicazione, materiale per i clienti"),
}
STANZE = ["sviluppo", "architettura", "laboratorio", "test", "revisione", "archivio"]
COLORI_SU_MISURA = ["#f5b942", "#7ee787", "#d2a8ff", "#ffa657", "#79c0ff", "#ff7b72"]

MAX_PASSI_AGENTE = 16
MAX_PASSI_ORCHESTRATORE = 18
MAX_AGENTI_PARALLELI = 4
TIMEOUT_APPROVAZIONE = 600
BATTITO_S = 2.0


def scrivi_atomico(percorso, testo, tentativi=6):
    """
    Scrive un file in modo sicuro anche su Windows.

    Su Windows il rinomino fallisce con 'Accesso negato' se un altro programma
    (il ponte, l'antivirus, l'indicizzatore) sta leggendo il file proprio in
    quell'istante. Riproviamo qualche volta a distanza di pochi millisecondi;
    se non ci riusciamo, meglio saltare questo aggiornamento che interrompere
    il lavoro: il battito ripubblichera' fra pochissimo.
    """
    tmp = percorso + ".tmp"
    for i in range(tentativi):
        try:
            with io.open(tmp, "w", encoding="utf-8") as f:
                f.write(testo)
            os.replace(tmp, percorso)
            return True
        except OSError:
            time.sleep(0.05 * (i + 1))
    try:
        os.remove(tmp)
    except OSError:
        pass
    return False


def _ora():
    return datetime.now().strftime("%H:%M:%S")


def _oggi():
    return datetime.now().isoformat()


# ===========================================================================
# Memoria persistente: le sessioni sopravvivono alla chiusura
# ===========================================================================

class Archivio(object):
    """Custodisce su disco le sessioni di lavoro, cosi' nulla va perduto."""

    def __init__(self):
        self._lock = threading.RLock()
        os.makedirs(DATI_DIR, exist_ok=True)
        self.dati = {"versione": 1, "sessioni": []}
        self._carica()

    def _carica(self):
        try:
            with io.open(FILE_SESSIONI, "r", encoding="utf-8") as f:
                d = json.load(f)
            if isinstance(d, dict) and isinstance(d.get("sessioni"), list):
                self.dati = d
        except (OSError, ValueError):
            pass
        # una sessione lasciata "in corso" da un avvio precedente e' interrotta
        for s in self.dati["sessioni"]:
            if s.get("stato") == "in corso":
                s["stato"] = "interrotta"
        self.salva()

    def salva(self):
        with self._lock:
            scrivi_atomico(FILE_SESSIONI, json.dumps(self.dati, ensure_ascii=False, indent=2))

    def nuova(self, obiettivo):
        with self._lock:
            s = {
                "id": uuid.uuid4().hex[:8],
                "titolo": (obiettivo or u"Nuova sessione")[:70],
                "obiettivo": obiettivo or "",
                "creato": _oggi(), "aggiornato": _oggi(),
                "stato": "in corso",
                "chat": [], "lavori": [], "agenti": [],
            }
            self.dati["sessioni"].insert(0, s)
            self.dati["sessioni"] = self.dati["sessioni"][:100]
        self.salva()
        return s

    def trova(self, sid):
        for s in self.dati["sessioni"]:
            if s["id"] == sid:
                return s
        return None

    def elimina(self, sid):
        with self._lock:
            self.dati["sessioni"] = [s for s in self.dati["sessioni"] if s["id"] != sid]
        self.salva()

    def elenco(self):
        """Vista sintetica per la tabella dei lavori nel mondo."""
        return [{
            "id": s["id"], "titolo": s["titolo"], "stato": s["stato"],
            "creato": s["creato"], "aggiornato": s["aggiornato"],
            "messaggi": len(s.get("chat", [])),
            "lavori": len(s.get("lavori", [])),
            "agenti": s.get("agenti", []),
            "riassunto": self.riassunto(s, breve=True),
        } for s in self.dati["sessioni"]]

    @staticmethod
    def riassunto(s, breve=False):
        """Racconta in poche righe cosa e' stato fatto: serve per riprendere."""
        righe = []
        if s.get("obiettivo"):
            righe.append(u"Richiesta iniziale: " + s["obiettivo"][:200])
        fatti = [l for l in s.get("lavori", []) if l.get("fatto")]
        if fatti:
            righe.append(u"Lavori completati:")
            for l in fatti[-8:]:
                righe.append(u"- {} ({}): {}".format(
                    l.get("agente", "?"), l.get("task", "")[:70],
                    (l.get("esito") or "")[:160]))
        if breve:
            return u" · ".join(righe)[:220]
        ultimi = s.get("chat", [])[-6:]
        if ultimi:
            righe.append(u"Ultimi scambi:")
            for m in ultimi:
                righe.append(u"  {}: {}".format(m.get("from", ""), (m.get("text") or "")[:180]))
        return u"\n".join(righe)


# ===========================================================================
# Stato vivo condiviso con la pagina web
# ===========================================================================

class Mondo(object):
    def __init__(self, archivio):
        self._lock = threading.RLock()
        self.archivio = archivio
        self.agenti = {}
        self.chat = []
        self.eventi = []
        self.handoff = []
        self.pending = None
        self.fullaccess = False
        self.resoconto = None
        self.lavori = []
        self.sessione = None
        self.chiavi = []          # nomi (mai i valori) delle chiavi in Cassaforte
        self.competenze = []      # Skill di Claude Code a disposizione
        self.strumenti_mcp = []   # strumenti offerti dai server MCP
        self.avatars = {}         # chi indossa quale avatar 3D
        self.personale = False    # True = comanda il tuo agente personale
        self.boss = {"id": "boss", "name": u"Orchestratore",
                     "status": "idle", "task": None, "thinking": None}
        self._ultimo_id_inbox = self._id_inbox_corrente()
        self._battito = None
        os.makedirs(MONDO_DIR, exist_ok=True)
        self.pubblica()

    # -- battito -----------------------------------------------------------
    def avvia_battito(self):
        """Ripubblica lo stato a intervalli regolari.
        Senza questo, quando nessuno lavora il file diventa 'vecchio', il ponte
        lo scarta e il mondo perde tutti gli agenti."""
        def ciclo():
            giro = 0
            while True:
                try:
                    self.pubblica()
                    giro += 1
                    if giro % 5 == 0:      # ogni ~10s ricontrolla la Cassaforte
                        carica_chiavi()
                except Exception:
                    pass
                time.sleep(BATTITO_S)
        self._battito = threading.Thread(target=ciclo, daemon=True)
        self._battito.start()

    # -- pubblicazione -----------------------------------------------------
    def pubblica(self):
        with self._lock:
            dati = {
                "boss": self.boss,
                "agents": list(self.agenti.values()),
                "chat": self.chat[-60:],
                "events": list(reversed(self.eventi[-40:])),
                "handoffs": self.handoff[-8:],
                "pending": self.pending,
                "fullaccess": self.fullaccess,
                "report": self.resoconto,
                "chiavi": self.chiavi,
                "competenze": self.competenze,
                "strumentiMcp": self.strumenti_mcp,
                "avatars": self.avatars,
                "personale": self.personale,
                "sessione": {"id": self.sessione["id"], "titolo": self.sessione["titolo"]} if self.sessione else None,
                "sessioni": self.archivio.elenco(),
                "stats": {
                    "done": len([l for l in self.lavori if l.get("fatto")]),
                    "messages": len(self.chat),
                },
                "_generatoIl": _oggi(),
                "_epoch": int(time.time() * 1000),
            }
            scrivi_atomico(FILE_LIVE, json.dumps(dati, ensure_ascii=False, indent=2))

    # -- sessioni ----------------------------------------------------------
    def apri_sessione(self, obiettivo):
        self.sessione = self.archivio.nuova(obiettivo)
        return self.sessione

    def riprendi_sessione(self, sid):
        s = self.archivio.trova(sid)
        if not s:
            return None
        self.sessione = s
        s["stato"] = "in corso"
        s["aggiornato"] = _oggi()
        with self._lock:
            self.chat = list(s.get("chat", []))
            self.lavori = list(s.get("lavori", []))
        self.archivio.salva()
        self.pubblica()
        return s

    def chiudi_sessione(self, stato="completata"):
        if self.sessione:
            self.sessione["stato"] = stato
            self.sessione["aggiornato"] = _oggi()
            self._sincronizza()

    def _sincronizza(self):
        """Riversa chat e lavori correnti nella sessione salvata."""
        if not self.sessione:
            return
        with self._lock:
            self.sessione["chat"] = self.chat[-200:]
            self.sessione["lavori"] = self.lavori[-100:]
            self.sessione["agenti"] = sorted({a["name"] for a in self.agenti.values()})
            self.sessione["aggiornato"] = _oggi()
        self.archivio.salva()

    # -- chat / eventi -----------------------------------------------------
    def dico(self, chi, testo, ruolo="boss", colore="#f5b942"):
        with self._lock:
            self.chat.append({"id": uuid.uuid4().hex[:10], "from": chi, "role": ruolo,
                              "color": colore, "text": testo, "ts": _ora()})
        self._sincronizza()
        self.pubblica()

    def evento(self, chi, testo, colore="#8a96b3"):
        with self._lock:
            self.eventi.append({"ts": _ora(), "id": uuid.uuid4().hex[:8],
                                "who": chi, "msg": testo, "color": colore})
        self.pubblica()

    def pensa(self, testo):
        with self._lock:
            self.boss["thinking"] = testo
            if testo:
                self.boss["status"] = "thinking"
        self.pubblica()

    def boss_stato(self, stato, task=None):
        with self._lock:
            self.boss["status"] = stato
            if task is not None:
                self.boss["task"] = task
        self.pubblica()

    # -- agenti ------------------------------------------------------------
    def crea_agente(self, ruolo, nome=None, specialita=None, stanza=None):
        """Crea (o recupera) un agente. Se 'nome' e' nuovo, nasce un agente
        su misura anche per un ruolo gia' occupato."""
        ruolo = (ruolo or "code").lower()
        base = RUOLI.get(ruolo)
        if base:
            nome_def, colore, st, competenza = base
        else:
            nome_def, colore, st, competenza = (ruolo.title(),
                                                COLORI_SU_MISURA[len(self.agenti) % len(COLORI_SU_MISURA)],
                                                stanza or "laboratorio", specialita or ruolo)
        nome = nome or nome_def
        aid = ruolo if (base and nome == nome_def) else (ruolo + "-" + uuid.uuid4().hex[:4])

        with self._lock:
            for a in self.agenti.values():
                if a["name"] == nome:
                    return a
            self.agenti[aid] = {
                "id": aid, "role": ruolo, "name": nome, "color": colore,
                "room": stanza or st, "skill": specialita or competenza,
                "status": "entering", "task": None, "progress": 0,
                "preview": None, "message": None, "nato": _ora(),
                "suMisura": base is None or nome != nome_def,
            }
        self.evento(nome, u"entra nell'ecosistema · " + (specialita or competenza), colore)
        self.pubblica()
        return self.agenti[aid]

    def agg(self, aid, **campi):
        with self._lock:
            if aid in self.agenti:
                self.agenti[aid].update(campi)
        self.pubblica()

    def passaggio(self, da, a, cosa):
        with self._lock:
            self.handoff.append({"id": uuid.uuid4().hex[:8], "from": da, "to": a,
                                 "what": cosa, "ts": time.time()})
        self.evento(da, u"→ {}: {}".format(a, cosa), "#ff7ac4")

    # -- inbox dalla pagina ------------------------------------------------
    def _id_inbox_corrente(self):
        try:
            with io.open(FILE_INBOX, "r", encoding="utf-8") as f:
                voci = json.load(f).get("items", [])
            numeri = [v["id"] for v in voci if isinstance(v.get("id"), (int, float))]
            return max(numeri) if numeri else 0
        except (OSError, ValueError):
            return 0

    def nuovi_comandi(self):
        try:
            with io.open(FILE_INBOX, "r", encoding="utf-8") as f:
                voci = json.load(f).get("items", [])
        except (OSError, ValueError):
            return []
        voci = [v for v in voci if isinstance(v.get("id"), (int, float))
                and v["id"] > self._ultimo_id_inbox]
        voci.sort(key=lambda v: v["id"])
        if voci:
            self._ultimo_id_inbox = voci[-1]["id"]
        for v in voci:
            if v.get("type") == "agente_personale":
                self.personale = bool(v.get("value"))
                if self.personale:
                    self.evento(u"Tu", u"hai messo al comando il tuo agente personale", "#f5b942")
                    self.dico(u"Il tuo Agente",
                              u"Eccomi, comando io. Dimmi pure: se serve una squadra "
                              u"la chiedo all'Orchestratore.", "agent", "#f5b942")
                else:
                    self.evento(u"Tu", u"il comando torna all'Orchestratore", "#8a96b3")
                    with self._lock:
                        self.agenti.pop("personale", None)
                    self.dico(u"Orchestratore",
                              u"Bentornato al comando. Dimmi cosa ti serve.", "boss", "#f5b942")
                self.pubblica()
            if v.get("type") == "fullaccess":
                self.fullaccess = bool(v.get("value"))
                self.evento(u"Tu", u"autorizzazione completa " +
                            (u"ATTIVATA" if self.fullaccess else u"disattivata"),
                            "#ff9f6b" if self.fullaccess else "#8a96b3")
                self.pubblica()
        return voci

    # -- approvazioni ------------------------------------------------------
    def chiedi_approvazione(self, comando, motivo):
        if self.fullaccess:
            self.evento(u"Sistema", u"autorizzazione completa: eseguo senza chiedere", "#ff9f6b")
            return True
        rid = int(time.time() * 1000)
        with self._lock:
            self.pending = {"id": rid, "command": comando, "reason": motivo}
        self.dico(u"Orchestratore", u"Serve la tua autorizzazione per: " + motivo, "boss", "#f5b942")
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


MONDO = None
ARCHIVIO = None
_lock_esecuzione = threading.Lock()   # un comando di sistema alla volta


# ===========================================================================
# Cassaforte
# ===========================================================================

PORTE_MONDO = range(5178, 5189)


def carica_chiavi():
    """Preleva le chiavi custodite e le rende disponibili ai comandi come
    variabili d'ambiente. Ritorna solo i NOMI: e' l'unica cosa che gli agenti
    sapranno. Va richiamata spesso, cosi' le chiavi aggiunte a ecosistema
    acceso vengono viste senza riavviare."""
    prima = set(agente.AMBIENTE_CASSAFORTE.keys())
    for porta in PORTE_MONDO:
        try:
            url = "http://127.0.0.1:{}/api/secret".format(porta)
            with urllib.request.urlopen(url, timeout=1.5) as r:
                dati = json.loads(r.read().decode("utf-8"))
            ambiente = dati.get("ambiente") or {}
            agente.AMBIENTE_CASSAFORTE = {str(k): str(v) for k, v in ambiente.items()}
            nomi = sorted(agente.AMBIENTE_CASSAFORTE.keys())
            if MONDO is not None:
                MONDO.chiavi = nomi
                nuove = set(nomi) - prima
                if nuove:
                    MONDO.evento(u"Cassaforte",
                                 u"nuove chiavi disponibili: " + u", ".join(sorted(nuove)),
                                 "#9d7bff")
                MONDO.pubblica()
            return nomi
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return sorted(agente.AMBIENTE_CASSAFORTE.keys())


def _righe_chiavi():
    nomi = sorted(agente.AMBIENTE_CASSAFORTE.keys())
    if not nomi:
        return []
    return [
        u"",
        u"--- Chiavi disponibili (Cassaforte) ---",
        u"Sono gia' caricate come variabili d'ambiente dei comandi.",
        u"NON conosci i loro valori e non devi chiederli: usale per nome, es. $env:" + nomi[0] + u".",
        u"Non stampare mai il contenuto di queste variabili a schermo.",
        u"Disponibili: " + u", ".join(nomi),
    ]


# ===========================================================================
# Agenti specialisti
# ===========================================================================

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
        "description": u"Aggiorna la tua barra di avanzamento (0-100) e cosa stai facendo.",
        "input_schema": {"type": "object",
                         "properties": {"percentuale": {"type": "number"},
                                        "cosa": {"type": "string"}},
                         "required": ["percentuale"]},
    },
    {
        "name": "anteprima",
        "description": u"Mostra all'utente un'anteprima del lavoro (testo, codice, elenco).",
        "input_schema": {"type": "object",
                         "properties": {"titolo": {"type": "string"},
                                        "contenuto": {"type": "string"}},
                         "required": ["titolo", "contenuto"]},
    },
    {
        "name": "chiedi_a_collega",
        "description": (u"Chiede aiuto a un altro agente su un punto specifico e ne "
                        u"attende la risposta. Usalo quando serve una competenza diversa "
                        u"dalla tua. Nel mondo vi si vede confrontarvi."),
        "input_schema": {
            "type": "object",
            "properties": {
                "ruolo": {"type": "string", "enum": sorted(RUOLI.keys())},
                "domanda": {"type": "string"},
            },
            "required": ["ruolo", "domanda"],
        },
    },
    {
        "name": "leggi_competenza",
        "description": (u"Apre una Skill dell'utente e ne restituisce le istruzioni complete. "
                        u"Usala PRIMA di lavorare quando una competenza elencata riguarda il "
                        u"tuo compito: contiene il metodo che l'utente vuole si segua."),
        "input_schema": {"type": "object",
                         "properties": {"nome": {"type": "string"}},
                         "required": ["nome"]},
    },
    {
        "name": "usa_strumento_mcp",
        "description": (u"Richiama uno degli strumenti MCP elencati (per esempio quelli di "
                        u"ruflo). Piu' mirato di un comando PowerShell quando esiste lo "
                        u"strumento adatto."),
        "input_schema": {
            "type": "object",
            "properties": {
                "server": {"type": "string", "description": u"il server fra parentesi quadre nell'elenco"},
                "strumento": {"type": "string"},
                "argomenti": {"type": "object", "description": u"secondo lo schema dello strumento"},
            },
            "required": ["server", "strumento"],
        },
    },
    {
        "name": "applica_avatar",
        "description": (u"Fa indossare un avatar 3D a un abitante del mondo. Il modello .glb "
                        u"(e l'eventuale immagine) devono stare nella cartella avatar/ del "
                        u"progetto. Verifica che il file sia completo e lo mostra nel mondo. "
                        u"Usalo dopo aver generato un avatar, per applicarlo davvero."),
        "input_schema": {
            "type": "object",
            "properties": {
                "abitante": {"type": "string",
                             "description": u"'orchestratore' oppure l'id di un ruolo (code, qa, design, ...)"},
                "modello": {"type": "string", "description": u"nome del file .glb dentro avatar/"},
                "immagine": {"type": "string", "description": u"immagine per la faccia (facoltativa)"},
            },
            "required": ["abitante"],
        },
    },
    {
        "name": "consegna",
        "description": u"Consegna il risultato all'Orchestratore e chiudi il tuo compito.",
        "input_schema": {"type": "object",
                         "properties": {"riepilogo": {"type": "string"}},
                         "required": ["riepilogo"]},
    },
]

# Raccolte una volta all'avvio: nomi e descrizioni finiscono nei prompt.
COMPETENZE = []


def _prompt_specialista(ag):
    return u"\n".join([
        u"Sei '{}', agente specialista dentro l'ecosistema di lavoro dell'utente.".format(ag["name"]),
        u"La tua competenza: {}.".format(ag.get("skill", ag["role"])),
        u"Lavori su Windows con PowerShell. Ricevi istruzioni dall'ORCHESTRATORE, non dall'utente.",
        u"Esegui un comando alla volta con 'esegui_comando' e osserva l'output.",
        u"Aggiorna spesso 'avanzamento' cosi' l'utente vede a che punto sei.",
        u"Se produci qualcosa di consultabile mostralo con 'anteprima'.",
        u"Se ti serve una competenza che non hai, usa 'chiedi_a_collega'.",
        u"Quando hai finito chiama 'consegna': sara' l'Orchestratore a parlare con l'utente.",
        u"Sii concreto e sintetico. Non chiedere permessi: ci pensa il sistema.",
        u"",
        u"INSISTI FINO AL RISULTATO. Un comando che fallisce non e' la fine del lavoro:",
        u"- leggi l'errore, capiscine la causa e riprova in modo diverso;",
        u"- se un comando va in timeout, spezzalo in passi piu' piccoli;",
        u"- se una strada e' bloccata, cercane un'altra per lo stesso obiettivo;",
        u"- verifica sempre l'esito (il file esiste? e' della dimensione giusta?)",
        u"  invece di darlo per buono.",
        u"Consegna solo quando hai un risultato vero. Se davvero non e' possibile,",
        u"consegna spiegando cosa hai provato e cosa manca: mai lasciare a meta'.",
    ] + _righe_chiavi()
      + competenze.righe_per_prompt(COMPETENZE)
      + mcp.righe_per_prompt())


def esegui_specialista(client, ruolo, istruzioni, nome=None, specialita=None, profondita=0):
    """Fa lavorare un agente. Ritorna il riepilogo consegnato."""
    m = MONDO
    ag = m.crea_agente(ruolo, nome=nome, specialita=specialita)
    aid, nome_ag, colore = ag["id"], ag["name"], ag["color"]

    # entra in scena, poi si mette al lavoro
    m.agg(aid, status="entering", task=istruzioni[:90], progress=0.02, preview=None)
    time.sleep(1.4)
    m.agg(aid, status="working", progress=0.05)
    m.evento(nome_ag, u"riceve: " + istruzioni[:70], colore)

    messaggi = [{"role": "user", "content": istruzioni}]
    riepilogo = None
    passi = 0

    while passi < MAX_PASSI_AGENTE:
        passi += 1
        try:
            risposta = client.messages.create(
                model=agente.MODELLO, max_tokens=2048,
                system=_prompt_specialista(ag),
                tools=TOOLS_SPECIALISTA, messages=messaggi,
            )
        except Exception as e:
            riepilogo = u"(non ho potuto proseguire: {})".format(spiega_errore(e))
            break
        messaggi.append({"role": "assistant", "content": risposta.content})

        if risposta.stop_reason != "tool_use":
            testo = u" ".join([b.text for b in risposta.content if b.type == "text"]).strip()
            riepilogo = testo or u"(nessun risultato)"
            break

        risultati = []
        finito = False
        for b in risposta.content:
            if b.type != "tool_use":
                continue
            args = b.input or {}

            try:
                if b.name == "esegui_comando":
                    cmd = args.get("comando", "")
                    m.agg(aid, message=cmd[:60],
                          progress=min(0.9, 0.1 + passi / float(MAX_PASSI_AGENTE)))
                    m.evento(nome_ag, u"$ " + cmd[:70], colore)
                    with _lock_esecuzione:      # un comando di sistema per volta
                        esito = agente.gestisci_esecuzione(cmd)
                    contenuto = json.dumps(esito, ensure_ascii=False)[:6000]

                elif b.name == "avanzamento":
                    p = max(0.0, min(100.0, float(args.get("percentuale", 0)))) / 100.0
                    m.agg(aid, progress=p, message=args.get("cosa") or None)
                    contenuto = json.dumps({"ok": True})

                elif b.name == "anteprima":
                    m.agg(aid, preview={"title": args.get("titolo", ""),
                                        "body": (args.get("contenuto") or "")[:4000],
                                        "agent": nome_ag, "color": colore})
                    m.evento(nome_ag, u"anteprima: " + args.get("titolo", ""), colore)
                    contenuto = json.dumps({"ok": True})

                elif b.name == "chiedi_a_collega":
                    altro = args.get("ruolo", "research")
                    domanda = args.get("domanda", "")
                    if profondita >= 1:
                        contenuto = json.dumps({"errore": u"catena troppo lunga: rispondi con quello che sai"},
                                               ensure_ascii=False)
                    else:
                        nome_altro = RUOLI.get(altro, (altro,))[0]
                        m.passaggio(nome_ag, nome_altro, domanda[:60])
                        m.agg(aid, status="waiting", message=u"attende " + nome_altro)
                        risp = esegui_specialista(client, altro,
                                                  u"Un collega ti chiede: " + domanda,
                                                  profondita=profondita + 1)
                        m.passaggio(nome_altro, nome_ag, u"risponde")
                        m.agg(aid, status="working", message=None)
                        contenuto = json.dumps({"collega": nome_altro, "risposta": risp},
                                               ensure_ascii=False)[:4000]

                elif b.name == "leggi_competenza":
                    nome_c = args.get("nome", "")
                    m.agg(aid, message=u"consulta «{}»".format(nome_c)[:60])
                    m.evento(nome_ag, u"📖 apre la competenza «{}»".format(nome_c), colore)
                    sk = competenze.leggi(nome_c)
                    contenuto = (json.dumps(sk, ensure_ascii=False)[:22000] if sk
                                 else json.dumps({"errore": u"competenza non trovata: " + nome_c},
                                                 ensure_ascii=False))

                elif b.name == "usa_strumento_mcp":
                    srv = args.get("server", "")
                    strum = args.get("strumento", "")
                    m.agg(aid, message=u"{}·{}".format(srv, strum)[:60])
                    m.evento(nome_ag, u"🔌 {} → {}".format(srv, strum), colore)
                    with _lock_esecuzione:
                        esito = mcp.chiama(srv, strum, args.get("argomenti") or {})
                    contenuto = json.dumps({"risultato": esito}, ensure_ascii=False)[:9000]

                elif b.name == "applica_avatar":
                    chi = args.get("abitante", "")
                    esito = avatar.applica(chi, args.get("modello"), args.get("immagine"))
                    if esito.get("ok"):
                        m.avatars = avatar.per_mondo()
                        m.evento(nome_ag, u"🎭 avatar applicato a {}".format(esito["abitante"]), colore)
                        m.pubblica()
                    else:
                        m.evento(nome_ag, u"🎭 avatar non applicato: " + esito.get("errore", "")[:60], "#ff9f6b")
                    contenuto = json.dumps(esito, ensure_ascii=False)

                elif b.name == "consegna":
                    riepilogo = args.get("riepilogo", "")
                    finito = True
                    contenuto = json.dumps({"ok": True})

                else:
                    contenuto = json.dumps({"errore": "tool sconosciuto"})

            except Exception as _e:
                # Un guasto interno non deve fermare l'agente: diventa un esito
                # che puo' leggere, cosi' cambia strada e prosegue.
                contenuto = json.dumps({"errore": str(_e),
                                        "suggerimento": u"Non fermarti: prova un altro modo per arrivare al risultato."},
                                       ensure_ascii=False)
                m.evento(nome_ag, u"\u26a0 intoppo: " + str(_e)[:70] + u" \u2014 cerco un'altra strada", "#ff9f6b")
            risultati.append({"type": "tool_result", "tool_use_id": b.id, "content": contenuto})

        messaggi.append({"role": "user", "content": risultati})
        if finito:
            break

    if riepilogo is None:
        riepilogo = u"(limite di passi raggiunto)"

    m.agg(aid, status="delivering", progress=1.0, message=None)
    m.passaggio(nome_ag, u"Orchestratore", u"consegna il risultato")
    m.lavori.append({"agente": nome_ag, "ruolo": ruolo, "task": istruzioni,
                     "esito": riepilogo, "fatto": True, "ts": _ora()})
    m._sincronizza()
    time.sleep(1.6)   # tempo per vedere il tragitto verso il capo
    m.agg(aid, status="idle", task=None, progress=0)
    return riepilogo


# ===========================================================================
# Orchestratore
# ===========================================================================

TOOLS_ORCHESTRATORE = [
    {
        "name": "assegna",
        "description": (u"Assegna un compito a un agente specialista, creandolo se non "
                        u"esiste. Puoi chiamarlo PIU' VOLTE nello stesso turno: i compiti "
                        u"indipendenti verranno svolti IN PARALLELO e l'utente vedra' piu' "
                        u"agenti lavorare insieme. Ritorna il riepilogo del lavoro."),
        "input_schema": {
            "type": "object",
            "properties": {
                "ruolo": {"type": "string", "enum": sorted(RUOLI.keys()),
                          "description": u"; ".join(u"{}={}".format(k, v[3]) for k, v in RUOLI.items())},
                "istruzioni": {"type": "string",
                               "description": u"Cosa deve fare, in modo autosufficiente e concreto."},
            },
            "required": ["ruolo", "istruzioni"],
        },
    },
    {
        "name": "crea_specialista",
        "description": (u"Crea un agente SU MISURA per un compito che i ruoli standard non "
                        u"coprono bene, dandogli un nome e una competenza sua, e gli assegna "
                        u"il lavoro. Usalo quando serve una figura dedicata."),
        "input_schema": {
            "type": "object",
            "properties": {
                "nome": {"type": "string", "description": u"Nome proprio, es. 'Traduttore'"},
                "competenza": {"type": "string", "description": u"Di cosa si occupa"},
                "ruolo_base": {"type": "string", "enum": sorted(RUOLI.keys()),
                               "description": u"Il ruolo standard piu' vicino (decide la stanza)"},
                "istruzioni": {"type": "string"},
            },
            "required": ["nome", "competenza", "ruolo_base", "istruzioni"],
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
        "name": "leggi_competenza",
        "description": (u"Apre una Skill dell'utente e ne restituisce le istruzioni complete. "
                        u"Consultala quando riguarda la richiesta, per capire come impostare "
                        u"il lavoro prima di assegnarlo."),
        "input_schema": {"type": "object",
                         "properties": {"nome": {"type": "string"}},
                         "required": ["nome"]},
    },
    {
        "name": "resoconto",
        "description": u"Produce un resoconto del lavoro svolto e lo mostra all'utente.",
        "input_schema": {"type": "object",
                         "properties": {"testo": {"type": "string"}},
                         "required": ["testo"]},
    },
]


def _prompt_orchestratore(memoria, ripresa=None):
    testo = [
        u"Sei l'ORCHESTRATORE dell'ecosistema di agenti dell'utente, su Windows/PowerShell.",
        u"Sei l'unico che parla con l'utente: gli specialisti riferiscono solo a te.",
        u"",
        u"Come lavori:",
        u"- Ogni messaggio dell'utente arriva a te. Decidi tu come procedere.",
        u"- Per i compiti operativi usa 'assegna' scegliendo il ruolo giusto.",
        u"- SFRUTTA LA SQUADRA: quando un obiettivo ha parti indipendenti, chiama",
        u"  'assegna' piu' volte NELLO STESSO TURNO. Lavoreranno in parallelo e",
        u"  l'utente vedra' l'ecosistema muoversi davvero. Non fare tutto da un",
        u"  agente solo se il lavoro si puo' dividere.",
        u"- Se serve una figura che i ruoli standard non coprono, usa 'crea_specialista'.",
        u"- Per domande semplici o conversazione rispondi con 'rispondi', senza",
        u"  scomodare nessun agente.",
        u"- Quando l'utente chiede un riepilogo del lavoro, usa 'resoconto'.",
        u"- Chiudi SEMPRE il turno con 'rispondi' (o 'resoconto'). Parla italiano,",
        u"  chiaro e breve.",
        u"",
        u"NON MOLLARE A META'. Se un agente torna con un errore o un lavoro",
        u"incompleto, non fermarti li': rileggi cosa e' andato storto e riassegna",
        u"il compito con istruzioni corrette, oppure affidalo a un ruolo diverso.",
        u"Insisti finche' l'obiettivo e' raggiunto. Solo se dopo piu' tentativi",
        u"resta impossibile, spiega all'utente cosa e' stato provato e cosa serve",
        u"da lui per proseguire: mai lasciare la richiesta senza una conclusione.",
        u"",
        u"Ruoli disponibili:",
    ]
    for k, v in RUOLI.items():
        testo.append(u"  {} — {}: {}".format(k, v[0], v[3]))
    if memoria.get("fatti"):
        testo.append(u"\n--- Memoria (fatti noti) ---")
        for k, v in memoria["fatti"].items():
            testo.append(u"- {}: {}".format(k, v))
    if ripresa:
        testo.append(u"\n--- Stai RIPRENDENDO un lavoro interrotto ---")
        testo.append(ripresa)
        testo.append(u"Riprendi da dove si era fermato, senza ricominciare da capo.")
    testo.extend(_righe_chiavi())
    testo.extend(competenze.righe_per_prompt(COMPETENZE))
    testo.extend(mcp.righe_per_prompt())
    return u"\n".join(testo)


def gestisci_messaggio(client, memoria, testo_utente, storico, ripresa=None):
    """Un giro completo: messaggio -> Orchestratore -> agenti (anche in parallelo) -> risposta."""
    m = MONDO
    # Rileggi la Cassaforte a ogni turno: cosi' una chiave aggiunta dal
    # Quartier Generale a ecosistema gia' avviato viene vista subito, senza
    # dover riavviare nulla.
    carica_chiavi()
    if not m.sessione:
        m.apri_sessione(testo_utente)
    m.dico(u"Tu", testo_utente, "user", "#e9edf8")
    m.boss_stato("thinking", testo_utente[:80])
    m.pensa(u"sto decidendo come procedere…")

    storico.append({"role": "user", "content": testo_utente})
    system = _prompt_orchestratore(memoria, ripresa)
    passi = 0

    while passi < MAX_PASSI_ORCHESTRATORE:
        passi += 1
        try:
            risposta = client.messages.create(
                model=agente.MODELLO, max_tokens=2048, system=system,
                tools=TOOLS_ORCHESTRATORE, messages=storico,
            )
        except Exception as e:
            m.dico(u"Orchestratore", spiega_errore(e), "boss", "#ff9f6b")
            break
        storico.append({"role": "assistant", "content": risposta.content})

        if risposta.stop_reason != "tool_use":
            testo = u" ".join([b.text for b in risposta.content if b.type == "text"]).strip()
            if testo:
                m.dico(u"Orchestratore", testo, "boss", "#f5b942")
            break

        blocchi = [b for b in risposta.content if b.type == "tool_use"]
        incarichi = [b for b in blocchi if b.name in ("assegna", "crea_specialista")]
        altri = [b for b in blocchi if b.name not in ("assegna", "crea_specialista")]
        risultati = []

        # --- lavori in parallelo -------------------------------------------
        if incarichi:
            m.boss_stato("dispatching")
            m.pensa(u"metto al lavoro {} agenti".format(len(incarichi)) if len(incarichi) > 1
                    else u"assegno il compito")
            for b in incarichi:
                a = b.input or {}
                nome = a.get("nome") or RUOLI.get(a.get("ruolo") or a.get("ruolo_base", ""), (u"agente",))[0]
                m.passaggio(u"Orchestratore", nome,
                            (a.get("istruzioni") or "")[:60])

            def lavora(b):
                # Se un agente incontra un guasto, l'Orchestratore deve poterlo
                # sapere e riprovare: mai far cadere tutto il turno.
                a = b.input or {}
                try:
                    if b.name == "assegna":
                        return b, esegui_specialista(client, a.get("ruolo", "code"),
                                                     a.get("istruzioni", ""))
                    return b, esegui_specialista(client, a.get("ruolo_base", "code"),
                                                 a.get("istruzioni", ""),
                                                 nome=a.get("nome"),
                                                 specialita=a.get("competenza"))
                except Exception as e:
                    return b, (u"L'agente si e' fermato per un problema: {}. "
                               u"Il compito NON e' stato completato: valuta di "
                               u"riassegnarlo con istruzioni diverse.".format(e))

            with ThreadPoolExecutor(max_workers=min(MAX_AGENTI_PARALLELI, len(incarichi))) as pool:
                for b, esito in pool.map(lavora, incarichi):
                    a = b.input or {}
                    nome = a.get("nome") or RUOLI.get(a.get("ruolo") or a.get("ruolo_base", ""), (u"agente",))[0]
                    risultati.append({"type": "tool_result", "tool_use_id": b.id,
                                      "content": json.dumps({"agente": nome, "risultato": esito},
                                                            ensure_ascii=False)[:6000]})
            m.boss_stato("thinking")

        # --- risposte e resoconti ------------------------------------------
        for b in altri:
            args = b.input or {}
            try:
                if b.name == "rispondi":
                    m.dico(u"Orchestratore", args.get("testo", ""), "boss", "#f5b942")
                    contenuto = json.dumps({"ok": True})
                elif b.name == "leggi_competenza":
                    nome_c = args.get("nome", "")
                    m.pensa(u"consulto la competenza «{}»".format(nome_c))
                    m.evento(u"Orchestratore", u"📖 consulta «{}»".format(nome_c), "#f5b942")
                    sk = competenze.leggi(nome_c)
                    contenuto = (json.dumps(sk, ensure_ascii=False)[:22000] if sk
                                 else json.dumps({"errore": u"competenza non trovata: " + nome_c},
                                                 ensure_ascii=False))
                elif b.name == "resoconto":
                    with m._lock:
                        m.resoconto = {"text": args.get("testo", ""), "ts": _ora()}
                    m.dico(u"Orchestratore", u"Ecco il resoconto del lavoro.", "boss", "#f5b942")
                    m.pubblica()
                    contenuto = json.dumps({"ok": True})
                else:
                    contenuto = json.dumps({"errore": "tool sconosciuto"})
            except Exception as _e:
                # Un guasto interno non deve fermare il lavoro: lo raccontiamo
                # all'agente come esito, cosi' puo' correggere e riprovare.
                contenuto = json.dumps({"errore": str(_e),
                                        "suggerimento": u"Riprova in modo diverso: cambia strada, non fermarti."},
                                       ensure_ascii=False)
            risultati.append({"type": "tool_result", "tool_use_id": b.id, "content": contenuto})

        # rimetti i risultati nell'ordine dei blocchi richiesti
        ordine = {b.id: i for i, b in enumerate(blocchi)}
        risultati.sort(key=lambda r: ordine.get(r["tool_use_id"], 99))
        storico.append({"role": "user", "content": risultati})

    m.boss_stato("idle", None)
    m.pensa(None)
    m.chiudi_sessione("completata")
    if len(storico) > 40:
        del storico[:len(storico) - 40]


# ===========================================================================
# Avvio
# ===========================================================================

def avvia(client, memoria):
    global MONDO, ARCHIVIO, COMPETENZE
    ARCHIVIO = Archivio()
    MONDO = Mondo(ARCHIVIO)
    MONDO.avvia_battito()
    agente.CHIEDI_CONFERMA_HOOK = MONDO.chiedi_approvazione

    nomi = carica_chiavi()
    interrotte = [s for s in ARCHIVIO.dati["sessioni"] if s["stato"] == "interrotta"]

    # Le Skill di Claude Code diventano competenze dell'ecosistema.
    COMPETENZE = competenze.elenca()
    MONDO.competenze = [{"nome": s["nome"], "descrizione": s["descrizione"], "fonte": s["fonte"]}
                        for s in COMPETENZE]

    # Avatar gia' presenti nella cartella avatar/ (o assegnati in precedenza).
    MONDO.avatars = avatar.per_mondo()

    # I server MCP (ruflo) portano i loro strumenti agli agenti.
    print(u"")
    avviati = mcp.avvia_tutti(lambda t: print(u" MCP: " + t))
    MONDO.strumenti_mcp = [{"server": t["server"], "nome": t["nome"],
                            "descrizione": t["descrizione"]} for t in mcp.catalogo()]
    MONDO.pubblica()

    print(u"\n Ecosistema avviato. L'Orchestratore e' in ascolto.")
    print(u" Ruoli disponibili: {}".format(len(RUOLI)))
    print(u" Al comando: l'Orchestratore (lo sciame lavora anche senza il tuo agente)")
    print(u" Il tuo agente personale si accende dal mondo, quando vuoi.")
    print(u" Competenze (Skill): {}".format(len(COMPETENZE)))
    print(u" Avatar applicati: {}".format(avatar.elenco_testuale()))
    print(u" Strumenti MCP: {}{}".format(
        len(MONDO.strumenti_mcp),
        u" da " + u", ".join(avviati) if avviati else u" (nessun server attivo in mcp.json)"))
    if nomi:
        print(u" Cassaforte: {} chiavi disponibili agli agenti.".format(len(nomi)))
    else:
        print(u" Cassaforte: nessuna chiave (aggiungile dal Quartier Generale).")
    print(u" Sessioni in archivio: {} ({} interrotte da riprendere).".format(
        len(ARCHIVIO.dati["sessioni"]), len(interrotte)))
    print(u" Apri il mondo e scrivi nella Sala Comando. Ctrl+C per uscire.\n")

    MONDO.dico(u"Orchestratore",
               u"Ecosistema online. Dimmi cosa ti serve: decido io chi mettere al lavoro."
               + (u" Hai {} lavori interrotti: puoi riprenderli dalla tabella dei lavori.".format(len(interrotte))
                  if interrotte else u""),
               "boss", "#f5b942")

    storico = []
    ripresa = None
    while True:
        try:
            for v in MONDO.nuovi_comandi():
                tipo = v.get("type")

                if tipo == "message" and (v.get("text") or "").strip():
                    testo = v["text"].strip()
                    print(u"\n[dal mondo] {}".format(testo))
                    try:
                        if MONDO.personale:
                            gestisci_messaggio_personale(client, memoria, testo, storico)
                        else:
                            gestisci_messaggio(client, memoria, testo, storico, ripresa)
                        ripresa = None
                    except Exception as e:
                        MONDO.dico(u"Orchestratore", spiega_errore(e), "boss", "#ff9f6b")
                        MONDO.chiudi_sessione("interrotta")
                        print(u"[errore] {}".format(e))

                elif tipo == "riprendi" and v.get("sessione"):
                    s = MONDO.riprendi_sessione(v["sessione"])
                    if s:
                        storico = []
                        ripresa = ARCHIVIO.riassunto(s)
                        MONDO.dico(u"Orchestratore",
                                   u"Ho ripreso «{}». Ecco dove eravamo rimasti — dimmi come proseguire.".format(s["titolo"]),
                                   "boss", "#f5b942")
                        print(u"\n[dal mondo] ripresa sessione: {}".format(s["titolo"]))

                elif tipo == "agente_personale":
                    storico = []          # cambia chi comanda: si riparte puliti
                    ripresa = None

                elif tipo == "nuova_sessione":
                    MONDO.chiudi_sessione("completata")
                    MONDO.sessione = None
                    storico = []
                    ripresa = None
                    with MONDO._lock:
                        MONDO.chat = []
                        MONDO.lavori = []
                        MONDO.agenti = {}
                    MONDO.dico(u"Orchestratore", u"Nuova sessione. Di cosa ti occupi adesso?",
                               "boss", "#f5b942")

                elif tipo == "elimina_sessione" and v.get("sessione"):
                    ARCHIVIO.elimina(v["sessione"])
                    MONDO.pubblica()

            time.sleep(0.5)
        except (EOFError, KeyboardInterrupt):
            print(u"\nChiusura dell'ecosistema. Le sessioni restano salvate.")
            MONDO.chiudi_sessione("interrotta")
            mcp.ferma_tutti()
            break


# ===========================================================================
# Il tuo Agente personale
# ---------------------------------------------------------------------------
# Lo sciame funziona benissimo da solo: l'Orchestratore riceve le richieste,
# decide e mette al lavoro gli specialisti. Il tuo agente personale (quello
# di agente.py, con la sua memoria e le sue skill) e' FACOLTATIVO.
#
# Quando lo accendi dal mondo, passa al comando: sei tu a parlare con lui,
# e' lui a lavorare, e quando serve una squadra la chiede all'Orchestratore.
# Quando lo spegni, torna tutto all'Orchestratore.
# ===========================================================================

TOOLS_PERSONALE = agente.TOOLS + [
    {
        "name": "affida_allo_sciame",
        "description": (u"Affida un lavoro all'Orchestratore e alla sua squadra di "
                        u"specialisti, e ne attende il risultato. Usalo quando il compito "
                        u"e' ampio, ha parti indipendenti, o richiede competenze diverse "
                        u"dalle tue: loro possono lavorare in parallelo."),
        "input_schema": {"type": "object",
                         "properties": {"compito": {"type": "string"}},
                         "required": ["compito"]},
    },
    {
        "name": "anteprima",
        "description": u"Mostra all'utente un'anteprima del lavoro (testo, codice, elenco).",
        "input_schema": {"type": "object",
                         "properties": {"titolo": {"type": "string"},
                                        "contenuto": {"type": "string"}},
                         "required": ["titolo", "contenuto"]},
    },
]


def _prompt_personale(memoria, skills):
    base = agente.costruisci_system_prompt(memoria, skills)
    return base + u"\n".join([
        u"",
        u"",
        u"--- Sei nell'ECOSISTEMA ---",
        u"Sei l'agente personale dell'utente e in questo momento sei TU al comando.",
        u"Parli direttamente con lui: rispondi nel testo, non serve nessuno strumento",
        u"per farlo. Quello che scrivi compare nella sua Sala Comando.",
        u"Hai a disposizione una squadra: con 'affida_allo_sciame' passi un lavoro",
        u"all'Orchestratore, che sceglie gli specialisti e li fa lavorare in parallelo.",
        u"Usala per i compiti ampi; le cose rapide falle tu.",
        u"Insisti fino al risultato: se qualcosa fallisce, cambia strada e riprova.",
    ] + _righe_chiavi() + competenze.righe_per_prompt(COMPETENZE) + mcp.righe_per_prompt())


def gestisci_messaggio_personale(client, memoria, testo_utente, storico):
    """Un giro con il tuo agente personale al comando."""
    m = MONDO
    carica_chiavi()
    if not m.sessione:
        m.apri_sessione(testo_utente)
    m.dico(u"Tu", testo_utente, "user", "#e9edf8")

    ag = m.crea_agente("personale", nome=u"Il tuo Agente",
                       specialita=u"il tuo agente personale, con la tua memoria e le tue skill",
                       stanza="comando")
    aid = ag["id"]
    m.agg(aid, status="working", task=testo_utente[:90], progress=0.05)
    m.boss_stato("idle", None)

    skills = agente.elenca_skills()
    system = _prompt_personale(memoria, skills)
    storico.append({"role": "user", "content": testo_utente})
    passi = 0

    while passi < MAX_PASSI_ORCHESTRATORE:
        passi += 1
        try:
            risposta = client.messages.create(
                model=agente.MODELLO, max_tokens=2048, system=system,
                tools=TOOLS_PERSONALE, messages=storico,
            )
        except Exception as e:
            m.dico(u"Il tuo Agente", spiega_errore(e), "agent", ag["color"])
            break
        storico.append({"role": "assistant", "content": risposta.content})

        testo = u" ".join([b.text for b in risposta.content if b.type == "text"]).strip()
        if testo:
            m.dico(u"Il tuo Agente", testo, "agent", ag["color"])

        if risposta.stop_reason != "tool_use":
            break

        risultati = []
        finito = False
        for b in risposta.content:
            if b.type != "tool_use":
                continue
            args = b.input or {}
            try:
                if b.name == "esegui_comando":
                    cmd = args.get("comando", "")
                    m.agg(aid, message=cmd[:60],
                          progress=min(0.9, 0.1 + passi / float(MAX_PASSI_ORCHESTRATORE)))
                    m.evento(u"Il tuo Agente", u"$ " + cmd[:70], ag["color"])
                    with _lock_esecuzione:
                        esito = agente.gestisci_esecuzione(cmd)
                    contenuto = json.dumps(esito, ensure_ascii=False)[:6000]

                elif b.name == "affida_allo_sciame":
                    compito = args.get("compito", "")
                    m.passaggio(u"Il tuo Agente", u"Orchestratore", compito[:60])
                    m.agg(aid, status="waiting", message=u"attende lo sciame")
                    m.boss_stato("dispatching", compito[:80])
                    esito = esegui_specialista(client, "code", compito)
                    m.boss_stato("idle", None)
                    m.agg(aid, status="working", message=None)
                    m.passaggio(u"Orchestratore", u"Il tuo Agente", u"riporta il risultato")
                    contenuto = json.dumps({"risultato": esito}, ensure_ascii=False)[:6000]

                elif b.name == "anteprima":
                    m.agg(aid, preview={"title": args.get("titolo", ""),
                                        "body": (args.get("contenuto") or "")[:4000],
                                        "agent": u"Il tuo Agente", "color": ag["color"]})
                    contenuto = json.dumps({"ok": True})

                elif b.name == "ricorda":
                    agente.aggiungi_fatto(memoria, args.get("chiave", ""), args.get("valore", ""))
                    m.evento(u"Il tuo Agente", u"🧠 ricorda: " + str(args.get("chiave", ""))[:50], ag["color"])
                    contenuto = json.dumps({"ok": True})

                elif b.name == "salva_skill":
                    percorso = agente.salva_skill(args.get("nome_file", "skill"),
                                                  args.get("descrizione", ""),
                                                  args.get("codice", ""))
                    m.evento(u"Il tuo Agente", u"📖 nuova skill: " + os.path.basename(percorso), ag["color"])
                    contenuto = json.dumps({"ok": True, "percorso": percorso}, ensure_ascii=False)

                elif b.name == "esegui_skill":
                    with _lock_esecuzione:
                        esito = agente.esegui_skill(args.get("nome_file", ""))
                    contenuto = json.dumps(esito, ensure_ascii=False)[:6000]

                elif b.name == "obiettivo_completato":
                    riepilogo = args.get("riepilogo", "")
                    if riepilogo:
                        m.dico(u"Il tuo Agente", riepilogo, "agent", ag["color"])
                    finito = True
                    contenuto = json.dumps({"ok": True})

                else:
                    contenuto = json.dumps({"errore": "tool sconosciuto"})

            except Exception as _e:
                contenuto = json.dumps({"errore": str(_e),
                                        "suggerimento": u"Non fermarti: prova un'altra strada."},
                                       ensure_ascii=False)
                m.evento(u"Il tuo Agente", u"⚠ intoppo: " + str(_e)[:60], "#ff9f6b")

            risultati.append({"type": "tool_result", "tool_use_id": b.id, "content": contenuto})

        storico.append({"role": "user", "content": risultati})
        if finito:
            break

    m.agg(aid, status="idle", task=None, progress=0, message=None)
    m.chiudi_sessione("completata")
    if len(storico) > 40:
        del storico[:len(storico) - 40]
