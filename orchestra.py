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

import agente  # riusa esecuzione comandi, log e classificazione

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
            tmp = FILE_SESSIONI + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(self.dati, ensure_ascii=False, indent=2))
            os.replace(tmp, FILE_SESSIONI)

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
            while True:
                try:
                    self.pubblica()
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
                "sessione": {"id": self.sessione["id"], "titolo": self.sessione["titolo"]} if self.sessione else None,
                "sessioni": self.archivio.elenco(),
                "stats": {
                    "done": len([l for l in self.lavori if l.get("fatto")]),
                    "messages": len(self.chat),
                },
                "_generatoIl": _oggi(),
                "_epoch": int(time.time() * 1000),
            }
            tmp = FILE_LIVE + ".tmp"
            with io.open(tmp, "w", encoding="utf-8") as f:
                f.write(json.dumps(dati, ensure_ascii=False, indent=2))
            os.replace(tmp, FILE_LIVE)

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
            return max([v.get("id", 0) for v in voci]) if voci else 0
        except (OSError, ValueError):
            return 0

    def nuovi_comandi(self):
        try:
            with io.open(FILE_INBOX, "r", encoding="utf-8") as f:
                voci = json.load(f).get("items", [])
        except (OSError, ValueError):
            return []
        voci = [v for v in voci if v.get("id", 0) > self._ultimo_id_inbox]
        voci.sort(key=lambda v: v.get("id", 0))
        if voci:
            self._ultimo_id_inbox = voci[-1]["id"]
        for v in voci:
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
    sapranno."""
    for porta in PORTE_MONDO:
        try:
            url = "http://127.0.0.1:{}/api/secret".format(porta)
            with urllib.request.urlopen(url, timeout=1.5) as r:
                dati = json.loads(r.read().decode("utf-8"))
            ambiente = dati.get("ambiente") or {}
            agente.AMBIENTE_CASSAFORTE = {str(k): str(v) for k, v in ambiente.items()}
            return sorted(agente.AMBIENTE_CASSAFORTE.keys())
        except (urllib.error.URLError, OSError, ValueError):
            continue
    return []


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
        "name": "consegna",
        "description": u"Consegna il risultato all'Orchestratore e chiudi il tuo compito.",
        "input_schema": {"type": "object",
                         "properties": {"riepilogo": {"type": "string"}},
                         "required": ["riepilogo"]},
    },
]


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
    ] + _righe_chiavi())


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
            riepilogo = u"(errore: {})".format(e)
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

            elif b.name == "consegna":
                riepilogo = args.get("riepilogo", "")
                finito = True
                contenuto = json.dumps({"ok": True})

            else:
                contenuto = json.dumps({"errore": "tool sconosciuto"})

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
    return u"\n".join(testo)


def gestisci_messaggio(client, memoria, testo_utente, storico, ripresa=None):
    """Un giro completo: messaggio -> Orchestratore -> agenti (anche in parallelo) -> risposta."""
    m = MONDO
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
            m.dico(u"Orchestratore", u"Ho avuto un problema con il modello: {}".format(e),
                   "boss", "#ff9f6b")
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
                a = b.input or {}
                if b.name == "assegna":
                    return b, esegui_specialista(client, a.get("ruolo", "code"),
                                                 a.get("istruzioni", ""))
                return b, esegui_specialista(client, a.get("ruolo_base", "code"),
                                             a.get("istruzioni", ""),
                                             nome=a.get("nome"),
                                             specialita=a.get("competenza"))

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
            if b.name == "rispondi":
                m.dico(u"Orchestratore", args.get("testo", ""), "boss", "#f5b942")
                contenuto = json.dumps({"ok": True})
            elif b.name == "resoconto":
                with m._lock:
                    m.resoconto = {"text": args.get("testo", ""), "ts": _ora()}
                m.dico(u"Orchestratore", u"Ecco il resoconto del lavoro.", "boss", "#f5b942")
                m.pubblica()
                contenuto = json.dumps({"ok": True})
            else:
                contenuto = json.dumps({"errore": "tool sconosciuto"})
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
    global MONDO, ARCHIVIO
    ARCHIVIO = Archivio()
    MONDO = Mondo(ARCHIVIO)
    MONDO.avvia_battito()
    agente.CHIEDI_CONFERMA_HOOK = MONDO.chiedi_approvazione

    nomi = carica_chiavi()
    interrotte = [s for s in ARCHIVIO.dati["sessioni"] if s["stato"] == "interrotta"]

    print(u"\n Ecosistema avviato. L'Orchestratore e' in ascolto.")
    print(u" Ruoli disponibili: {}".format(len(RUOLI)))
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
                        gestisci_messaggio(client, memoria, testo, storico, ripresa)
                        ripresa = None
                    except Exception as e:
                        MONDO.dico(u"Orchestratore", u"Ho avuto un problema: {}".format(e),
                                   "boss", "#ff9f6b")
                        MONDO.chiudi_sessione("interrotta")
                        print(u"[errore] {}".format(e))

                elif tipo == "riprendi" and v.get("id"):
                    s = MONDO.riprendi_sessione(v["id"])
                    if s:
                        storico = []
                        ripresa = ARCHIVIO.riassunto(s)
                        MONDO.dico(u"Orchestratore",
                                   u"Ho ripreso «{}». Ecco dove eravamo rimasti — dimmi come proseguire.".format(s["titolo"]),
                                   "boss", "#f5b942")
                        print(u"\n[dal mondo] ripresa sessione: {}".format(s["titolo"]))

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

                elif tipo == "elimina_sessione" and v.get("id"):
                    ARCHIVIO.elimina(v["id"])
                    MONDO.pubblica()

            time.sleep(0.5)
        except (EOFError, KeyboardInterrupt):
            print(u"\nChiusura dell'ecosistema. Le sessioni restano salvate.")
            MONDO.chiudi_sessione("interrotta")
            break
