# -*- coding: utf-8 -*-
"""Due finti servizi, per provare tutto senza chiavi e senza spendere.

NON sono simulazioni di comodo: parlano lo stesso protocollo di Anthropic e di
HubSpot, quindi se il codice funziona contro questi funziona anche contro
quelli veri. Servono a rispondere alla domanda «il giro completo regge?» senza
pagare una chiamata.

Con le chiavi vere, il test di accettazione li ignora e va sui servizi veri.
"""
import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

# Cosa risponde il finto Claude, in base a quello che scrive il paziente.
#
# E' una scorciatoia grossolana fatta di parole chiave: il modello vero capisce
# molto di piu'. Basta pero' a raccontare la verita' nella vetrina - l'emergenza
# si ferma, il lavoro importante passa a una persona, la preferenza di orario
# viene rispettata - senza spendere niente.

SINTOMI = ("dolore", "sanguina", "gonfio", "gonfiore", "ascesso", "trauma",
           "febbre", "male ai denti", "fa male")
NEGATO = ("non ho dolore", "senza dolore", "non fa male", "nessun dolore",
          "non ho male")
IMPORTANTI = {"impianto": ("impianto", "impianti", "all-on-4", "all on 4"),
              "ortodonzia": ("ortodon", "apparecchio", "invisalign", "allineator"),
              "protesi": ("protesi", "dentiera", "faccette")}
SEMPLICI = {"igiene": ("pulizia", "igiene", "detartrasi", "tartaro"),
            "sbiancamento": ("sbiancament", "sbiancare", "denti piu' bianchi"),
            "otturazione": ("otturazion", "carie", "buco"),
            "controllo": ("controllo", "visita", "check")}

# --- lo stesso, per la medicina estetica -----------------------------------
#
# Qui il finto Claude legge il prompt di sistema per capire che mestiere sta
# facendo, esattamente come lo legge quello vero. E' l'unico modo onesto di
# simulare due settori con un solo finto servizio: se il prompt non dicesse
# il mestiere, non lo saprebbe nemmeno il modello vero.

SINTOMI_EST = ("gonfi", "dolore", "fa male", "reazione", "febbre", "infezion",
               "livido", "brucia", "bruciore", "non si riassorbe",
               "non si sgonfia", "asimmetr", "indurit", "prurito")
CHIRURGIA = ("chirurg", "rinoplastica", "mastoplastica", "liposuzione",
             "lipofilling", "blefaroplastica", "addominoplastica", "lifting",
             "otoplastica", "protesi", "trapianto", "operarmi", "intervento")
INIETTIVI = ("filler", "botulino", "botox", "tossina", "acido ialuronico",
             "biorivitalizzazione", "mesoterapia", "fili di trazione", "labbra")
SEMPLICI_EST = {"epilazione laser": ("epilazione", "laser", "depilazione"),
                "peeling": ("peeling", "macchie", "pulizia del viso"),
                "pressoterapia": ("pressoterapia", "cellulite", "drenaggio"),
                "consulenza estetica": ("consulenza", "informazioni", "preventivo")}


def _fascia(t):
    if "pomerigg" in t or "sera" in t:
        return "pomeriggio"
    if "mattin" in t:
        return "mattina"
    return None


def _decide_estetica(t):
    """Il mestiere in cui quasi tutto e' un atto medico.

    La soglia e' molto piu' bassa che nel dentale: si prenota da solo soltanto
    cio' che non e' invasivo. Chirurgia e iniettivi passano da una persona, e
    chi segnala un problema DOPO un trattamento e' la cosa piu' urgente che
    possa arrivare - non si rassicura, si passa la mano.
    """
    if any(k in t for k in SINTOMI_EST):
        return {"qualificato": True, "tipo_trattamento": "complicanza",
                "urgenza": "emergenza", "slot_proposto": None, "serve_umano": True,
                "risposta_bozza": u"Di questo la faccio parlare subito con il medico "
                                  u"che l'ha seguita: la sto segnalando come prima "
                                  u"della lista."}

    if any(k in t for k in CHIRURGIA):
        return {"qualificato": True, "tipo_trattamento": "chirurgia",
                "urgenza": "media", "slot_proposto": _fascia(t), "serve_umano": True,
                "risposta_bozza": u"Per un intervento la valutazione la fa il "
                                  u"chirurgo in consulenza: le fisso un incontro."}

    if any(k in t for k in INIETTIVI):
        return {"qualificato": True, "tipo_trattamento": "iniettivo",
                "urgenza": "media", "slot_proposto": _fascia(t), "serve_umano": True,
                "risposta_bozza": u"E' un trattamento medico: prima serve una visita "
                                  u"con il nostro medico estetico. Le fisso la "
                                  u"consulenza."}

    trattamento = "consulenza estetica"
    for nome, parole in SEMPLICI_EST.items():
        if any(k in t for k in parole):
            trattamento = nome
            break
    return {"qualificato": True, "tipo_trattamento": trattamento,
            "urgenza": "bassa", "slot_proposto": _fascia(t), "serve_umano": False,
            "risposta_bozza": u"Buongiorno! Volentieri: le propongo un "
                              u"appuntamento per una prima valutazione."}


def _settore_dal_prompt(sistema):
    """Che mestiere sta facendo, letto dal prompt di sistema.

    Si confronta con la frase esatta del registro dei settori, non con una
    parola a caso: cercare "estetica" scambiava uno studio dentistico per una
    clinica, perche' anche il dentista parla di «estetica dentale». Una prova
    che c'era gia' l'ha beccato subito.
    """
    from app import settori
    testo = sistema or ""
    for s in settori.SETTORI.values():
        if s.luogo in testo:
            return s.chiave
    return settori.PREDEFINITO


def _decide(testo, sistema=""):
    t = (testo or "").lower()
    if _settore_dal_prompt(sistema) == "estetica":
        return _decide_estetica(t)
    negato = any(n in t for n in NEGATO)

    # 1. Un sintomo clinico batte tutto il resto: si ferma e chiama una persona.
    if any(k in t for k in SINTOMI) and not negato:
        return {"qualificato": True, "tipo_trattamento": "urgenza_dolore",
                "urgenza": "emergenza", "slot_proposto": None, "serve_umano": True,
                "risposta_bozza": u"Mi dispiace, capisco che sta soffrendo. La faccio "
                                  u"richiamare subito da un nostro operatore."}

    # 2. Lavoro importante: lo segue una persona, non un programma.
    for nome, parole in IMPORTANTI.items():
        if any(k in t for k in parole):
            return {"qualificato": True, "tipo_trattamento": nome,
                    "urgenza": "media", "slot_proposto": _fascia(t),
                    "serve_umano": True,
                    "risposta_bozza": u"Per questo tipo di lavoro le fa avere tutte "
                                      u"le informazioni un nostro specialista."}

    # 3. Un dente rotto senza dolore forte: urgente ma non emergenza.
    if any(k in t for k in ("rotto", "scheggiat", "spezzat", "caduta")):
        return {"qualificato": True, "tipo_trattamento": "dente_rotto",
                "urgenza": "alta", "slot_proposto": _fascia(t), "serve_umano": False,
                "risposta_bozza": u"Capisco, la vediamo presto: le riservo il primo "
                                  u"posto utile."}

    # 4. Routine: si prenota da solo.
    trattamento = "controllo"
    for nome, parole in SEMPLICI.items():
        if any(k in t for k in parole):
            trattamento = nome
            break
    return {"qualificato": True, "tipo_trattamento": trattamento,
            "urgenza": "bassa", "slot_proposto": _fascia(t), "serve_umano": False,
            "risposta_bozza": u"Buongiorno! Volentieri: la prima visita conoscitiva "
                              u"e' gratuita. Le propongo un appuntamento."}


class _Manico(BaseHTTPRequestHandler):
    # Il finto HubSpot tiene una casa SEPARATA per ogni token. E' cosi' che il
    # test dimostra l'isolamento: se il contatto di uno studio comparisse
    # nell'archivio dell'altro, si vedrebbe qui.
    archivi = {}          # token -> {"contatti": {email: id}, "oggetti": [...]}
    prossimo = [1000]

    @classmethod
    def casa(cls, token):
        return cls.archivi.setdefault(token, {"contatti": {}, "oggetti": []})

    def _token(self):
        intestazione = self.headers.get("Authorization") or ""
        return intestazione[7:].strip() if intestazione.startswith("Bearer ") else ""

    def log_message(self, *a):
        pass    # silenzio: il diario del test e' gia' abbastanza fitto

    def _rispondi(self, stato, corpo):
        dati = json.dumps(corpo).encode("utf-8")
        self.send_response(stato)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def do_POST(self):
        lunghezza = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(lunghezza) or b"{}")

        # ---- finto Anthropic ----
        if self.path.endswith("/v1/messages"):
            if not (self.headers.get("x-api-key") or self.headers.get("authorization")):
                return self._rispondi(401, {"type": "error", "error": {
                    "type": "authentication_error", "message": "manca la chiave"}})
            ultimo = ""
            for m in corpo.get("messages", []):
                if m.get("role") == "user":
                    ultimo = m.get("content") if isinstance(m.get("content"), str) else ultimo
            return self._rispondi(200, {
                "id": "msg_finto", "type": "message", "role": "assistant",
                "model": corpo.get("model", "finto"),
                "content": [{"type": "tool_use", "id": "toolu_finto",
                             "name": "registra_qualificazione",
                             "input": _decide(ultimo, corpo.get("system") or "")}],
                "stop_reason": "tool_use", "stop_sequence": None,
                "usage": {"input_tokens": 10, "output_tokens": 20},
            })

        # ---- finto HubSpot, un archivio per token ----
        token = self._token()
        if self.path.startswith("/crm/") and not token.startswith("TOKEN-"):
            return self._rispondi(401, {"status": "error", "category": "INVALID_AUTHENTICATION",
                                        "message": "Authentication credentials not found"})
        casa = self.casa(token) if token else None

        if self.path.endswith("/crm/v3/objects/contacts"):
            email = (corpo.get("properties") or {}).get("email")
            if email and email in casa["contatti"]:
                return self._rispondi(409, {"status": "error", "category": "CONFLICT",
                                            "message": "Contact already exists"})
            self.prossimo[0] += 1
            ident = str(self.prossimo[0])
            if email:
                casa["contatti"][email] = ident
            casa["oggetti"].append({"tipo": "contatto", "id": ident, "email": email,
                                    "nome": (corpo.get("properties") or {}).get("firstname")})
            return self._rispondi(201, {"id": ident, "properties": corpo.get("properties")})

        if self.path.endswith("/crm/v3/objects/contacts/search"):
            valore = corpo["filterGroups"][0]["filters"][0]["value"]
            ident = casa["contatti"].get(valore)
            return self._rispondi(200, {"results": [{"id": ident}] if ident else []})

        if self.path.endswith("/crm/v3/objects/deals"):
            if not corpo.get("associations"):
                return self._rispondi(400, {"status": "error",
                                            "message": "la trattativa non e' legata a un contatto"})
            self.prossimo[0] += 1
            ident = str(self.prossimo[0])
            casa["oggetti"].append({
                "tipo": "trattativa", "id": ident,
                "nome": (corpo.get("properties") or {}).get("dealname"),
                "contatto": corpo["associations"][0]["to"]["id"]})
            return self._rispondi(201, {"id": ident})

        self._rispondi(404, {"errore": "non previsto: " + self.path})

    def do_GET(self):
        # Serve al test: cosa contiene l'archivio di ciascun token.
        if self.path == "/_ispeziona":
            return self._rispondi(200, {t: c["oggetti"] for t, c in self.archivi.items()})
        self._rispondi(404, {"errore": "non previsto: " + self.path})


def accendi():
    """Avvia i finti servizi su una porta libera. Ritorna (indirizzo, spegni)."""
    _Manico.archivi = {}
    server = HTTPServer(("127.0.0.1", 0), _Manico)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    indirizzo = "http://127.0.0.1:%d" % server.server_port
    return indirizzo, server.shutdown
