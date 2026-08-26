# -*- coding: utf-8 -*-
"""
mcp.py - Client MCP: gli strumenti di ruflo (e di qualsiasi altro server MCP)
messi in mano agli agenti.

Un server MCP e' un programma che espone strumenti tramite un protocollo
preciso (JSON-RPC su stdin/stdout, un messaggio per riga). Claude Code sa
parlarlo; l'ecosistema, finora, no. Questo modulo e' il traduttore.

Cosa fa:
  - avvia i server elencati in mcp.json (ruflo/claude-flow e' gia' previsto);
  - fa la stretta di mano (initialize + notifications/initialized);
  - chiede l'elenco degli strumenti e lo mette a disposizione degli agenti;
  - inoltra le chiamate e restituisce il risultato.

Tutto e' facoltativo e a prova di guasto: se un server non parte o non
risponde, l'ecosistema continua a funzionare senza quegli strumenti.

Configurazione: mcp.json accanto a questo file. Vedi mcp.example.json.
"""

import io
import os
import json
import time
import threading
import subprocess

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
FILE_CONFIG = os.path.join(BASE_DIR, "mcp.json")

TIMEOUT_AVVIO = 60      # i server scaricati con npx la prima volta sono lenti
TIMEOUT_CHIAMATA = 120
MAX_RISULTATO = 8000


class Server(object):
    """Un singolo server MCP: processo, stretta di mano, chiamate."""

    def __init__(self, nome, comando, argomenti=None, ambiente=None, cwd=None):
        self.nome = nome
        self.comando = [comando] + list(argomenti or [])
        self.ambiente = ambiente or {}
        self.cwd = cwd or BASE_DIR
        self.proc = None
        self.strumenti = []
        self.errore = None
        self._id = 0
        self._lock = threading.Lock()

    # -- ciclo di vita -----------------------------------------------------
    def avvia(self):
        env = dict(os.environ)
        env.update({str(k): str(v) for k, v in self.ambiente.items()})
        try:
            self.proc = subprocess.Popen(
                self.comando, cwd=self.cwd, env=env,
                stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                text=True, encoding="utf-8", errors="replace", bufsize=1,
                shell=(os.name == "nt"),   # su Windows npx e' uno script, non un eseguibile
            )
        except (OSError, ValueError) as e:
            self.errore = u"non avviato: {}".format(e)
            return False

        try:
            self._richiesta("initialize", {
                "protocolVersion": "2024-11-05",
                "capabilities": {},
                "clientInfo": {"name": "ecosistema", "version": "1.0"},
            }, timeout=TIMEOUT_AVVIO)
            self._notifica("notifications/initialized")
            risp = self._richiesta("tools/list", {}, timeout=TIMEOUT_AVVIO)
            self.strumenti = (risp or {}).get("tools", []) or []
            return True
        except Exception as e:
            self.errore = u"stretta di mano fallita: {}".format(e)
            self.ferma()
            return False

    def ferma(self):
        if self.proc and self.proc.poll() is None:
            try:
                self.proc.terminate()
                self.proc.wait(timeout=5)
            except Exception:
                try:
                    self.proc.kill()
                except Exception:
                    pass
        self.proc = None

    def vivo(self):
        return self.proc is not None and self.proc.poll() is None

    # -- protocollo --------------------------------------------------------
    def _scrivi(self, oggetto):
        riga = json.dumps(oggetto, ensure_ascii=False) + "\n"
        self.proc.stdin.write(riga)
        self.proc.stdin.flush()

    def _notifica(self, metodo, parametri=None):
        with self._lock:
            self._scrivi({"jsonrpc": "2.0", "method": metodo, "params": parametri or {}})

    def _richiesta(self, metodo, parametri, timeout=TIMEOUT_CHIAMATA):
        """Manda una richiesta e attende la risposta con lo stesso id."""
        with self._lock:
            self._id += 1
            rid = self._id
            self._scrivi({"jsonrpc": "2.0", "id": rid, "method": metodo, "params": parametri})

            scadenza = time.time() + timeout
            while time.time() < scadenza:
                if not self.vivo():
                    raise RuntimeError(u"il server si e' chiuso")
                riga = self.proc.stdout.readline()
                if not riga:
                    raise RuntimeError(u"nessuna risposta")
                riga = riga.strip()
                if not riga or not riga.startswith("{"):
                    continue                      # righe di log: si ignorano
                try:
                    msg = json.loads(riga)
                except ValueError:
                    continue
                if msg.get("id") != rid:
                    continue                      # notifica o risposta di un altro
                if "error" in msg:
                    raise RuntimeError(str(msg["error"].get("message", msg["error"])))
                return msg.get("result")
            raise RuntimeError(u"tempo scaduto")

    def chiama(self, strumento, argomenti):
        risp = self._richiesta("tools/call", {"name": strumento, "arguments": argomenti or {}})
        return _testo_risultato(risp)


def _testo_risultato(risp):
    """Riduce la risposta MCP a testo leggibile da un agente."""
    if risp is None:
        return u"(nessun risultato)"
    parti = []
    for blocco in (risp.get("content") or []):
        if blocco.get("type") == "text":
            parti.append(blocco.get("text", ""))
        else:
            parti.append(u"[{}]".format(blocco.get("type", "?")))
    testo = u"\n".join(parti).strip() or json.dumps(risp, ensure_ascii=False)[:MAX_RISULTATO]
    if risp.get("isError"):
        testo = u"[errore dallo strumento] " + testo
    return testo[:MAX_RISULTATO]


# ===========================================================================
# Registro dei server
# ===========================================================================

SERVER = {}


def _config():
    try:
        with io.open(FILE_CONFIG, "r", encoding="utf-8") as f:
            return json.load(f)
    except (OSError, ValueError):
        return {}


def avvia_tutti(al_via=None):
    """
    Avvia i server MCP attivi in mcp.json. Ritorna l'elenco dei nomi avviati.
    'al_via' e' una funzione facoltativa per raccontare cosa sta succedendo.
    """
    dillo = al_via or (lambda t: None)
    cfg = _config().get("server") or {}
    attivi = []
    for nome, c in cfg.items():
        if not c.get("attivo"):
            continue
        s = Server(nome, c.get("comando", ""), c.get("argomenti"), c.get("ambiente"), c.get("cartella"))
        dillo(u"avvio il server MCP «{}»…".format(nome))
        if s.avvia():
            SERVER[nome] = s
            attivi.append(nome)
            dillo(u"«{}» pronto: {} strumenti".format(nome, len(s.strumenti)))
        else:
            dillo(u"«{}» non disponibile ({})".format(nome, s.errore))
    return attivi


def ferma_tutti():
    for s in list(SERVER.values()):
        s.ferma()
    SERVER.clear()


def catalogo():
    """Tutti gli strumenti disponibili, per server."""
    out = []
    for nome, s in SERVER.items():
        for t in s.strumenti:
            out.append({
                "server": nome,
                "nome": t.get("name", ""),
                "descrizione": (t.get("description") or "")[:300],
                "schema": t.get("inputSchema") or {},
            })
    return out


def chiama(server, strumento, argomenti):
    s = SERVER.get(server)
    if not s:
        return u"[errore] server MCP «{}» non disponibile".format(server)
    if not s.vivo():
        return u"[errore] il server MCP «{}» si e' chiuso".format(server)
    try:
        return s.chiama(strumento, argomenti)
    except Exception as e:
        return u"[errore] {}".format(e)


MAX_IN_PROMPT = 60      # oltre, il prompt diventa piu' lungo del lavoro da fare

# Parole troppo comuni per dire qualcosa: se restano, la ricerca risponde
# sempre di si'. Sono le italiane dei nostri prompt e le inglesi dei server.
_VUOTE = set(u"""
una uno per con del della dei delle che cosa come dopo prima poi non piu meno
sul sulla nel nella dal dalla mio mia tuo tua suo sua questo questa quello
and the for with from that this into your you use used using when where what
all any are can get set new old its our their they them there here
""".split())


def _parole(testo):
    """Le parole utili di un testo: niente punteggiatura, niente parole vuote."""
    pulito = u"".join(c if c.isalnum() else u" " for c in (testo or u"").lower())
    return [p for p in pulito.split() if len(p) >= 3 and p not in _VUOTE]


def cerca(parola, limite=25):
    """
    Gli strumenti che somigliano a quello che l'agente sta cercando.
    Serve perche' nel prompt ce ne stanno poche decine e i server ne portano
    centinaia: senza una ricerca, tutto quello che non entra nell'elenco e'
    come se non esistesse.
    """
    parti = _parole(parola)
    if not parti:
        return []
    trovati = []
    for t in catalogo():
        nome = set(_parole(t["nome"]))
        testo = set(_parole(t["descrizione"])) | nome
        # parola intera, non pezzo di parola: senza questo 'per' trova
        # 'performance' e la ricerca restituisce qualsiasi cosa.
        punti = sum(3 if p in nome else (1 if p in testo else 0) for p in parti)
        if punti:
            trovati.append((punti, t))
    trovati.sort(key=lambda x: (-x[0], x[1]["nome"]))
    return [t for _, t in trovati[:limite]]


def riassunto():
    """
    Un riassunto per il mondo: una voce per server, non una per strumento.
    Un solo server puo' portarne centinaia; mandarle tutte al browser ogni due
    secondi vorrebbe dire oltre cento KB a battito, e un pannello con
    trecento pastiglie non si legge comunque.
    """
    per_server = {}
    for t in catalogo():
        per_server.setdefault(t["server"], []).append(t["nome"])
    out = []
    for srv, nomi in sorted(per_server.items()):
        out.append({
            "server": srv,
            "nome": u"{} · {} strument{}".format(srv, len(nomi), u"o" if len(nomi) == 1 else u"i"),
            "descrizione": u"Per esempio: " + u", ".join(nomi[:12])
                           + (u" e altri {}.".format(len(nomi) - 12) if len(nomi) > 12 else u"."),
        })
    return out


def righe_per_prompt():
    """Le righe da mettere nel prompt degli agenti."""
    cat = catalogo()
    if not cat:
        return []
    righe = [
        u"",
        u"--- Strumenti MCP disponibili ---",
        u"Oltre a PowerShell puoi usare questi strumenti con 'usa_strumento_mcp'.",
        u"Passa gli argomenti secondo lo schema indicato dallo strumento.",
    ]

    # A turno fra i server, non i primi 60 in ordine: un server che ne porta
    # centinaia riempirebbe da solo l'elenco e gli altri sparirebbero.
    per_server = {}
    for t in cat:
        per_server.setdefault(t["server"], []).append(t)
    # copie: sotto svuotiamo le code, e i conteggi servono ancora interi
    scelti, code = [], [list(v) for v in per_server.values()]
    while code and len(scelti) < MAX_IN_PROMPT:
        for coda in list(code):
            if not coda:
                code.remove(coda)
                continue
            scelti.append(coda.pop(0))
            if len(scelti) >= MAX_IN_PROMPT:
                break

    for t in scelti:
        righe.append(u"- [{}] {}: {}".format(t["server"], t["nome"], t["descrizione"][:150]))

    resto = len(cat) - len(scelti)
    if resto > 0:
        conteggi = u", ".join(u"{} {}".format(len(v), k) for k, v in sorted(per_server.items()))
        righe.append(u"")
        righe.append(u"Questi sono solo un assaggio: in tutto ce ne sono {} ({}).".format(len(cat), conteggi))
        righe.append(u"Gli altri {} NON sono elencati qui ma ci sono: se pensi che esista lo "
                     u"strumento giusto per quello che devi fare, cercalo con "
                     u"'cerca_strumento_mcp' prima di ripiegare su PowerShell.".format(resto))
    return righe
