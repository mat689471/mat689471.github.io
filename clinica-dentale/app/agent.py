# -*- coding: utf-8 -*-
"""L'agente che qualifica il paziente, con una chiamata vera a Claude.

Il JSON non si spera: si obbliga. Invece di chiedere al modello «rispondi solo
con JSON» e poi sperare, gli si da' un solo strumento con lo schema esatto e
gli si dice di usarlo. Cosi' la forma della risposta e' garantita dall'API.

(Il tentativo precedente usava il «prefill», cioe' cominciare la risposta al
posto suo con una graffa: sui modelli attuali e' rifiutato con un 400.)

Ogni guasto porta all'operatore. Meglio far rispondere una persona che
rispondere a caso a chi ha mal di denti.
"""
import json
import os

from app import config, settori
from app.logging_setup import passo

CHIAVI = ("qualificato", "tipo_trattamento", "urgenza", "slot_proposto",
          "serve_umano", "risposta_bozza")
URGENZE = ("bassa", "media", "alta", "emergenza")

# I trattamenti che devono passare da una persona non stanno piu' qui: sono
# una proprieta' del MESTIERE, e vivono in app/settori.py. Il dentale ferma
# gli impianti, l'estetica ferma la chirurgia e gli iniettivi. La regola che
# li applica, pero', resta dov'era: nel codice, sotto al modello.

STRUMENTO = {
    "name": "registra_qualificazione",
    "description": "Registra la qualificazione del paziente e la risposta da inviargli.",
    "input_schema": {
        "type": "object",
        "properties": {
            "qualificato": {"type": "boolean",
                            "description": "Hai capito il trattamento e l'intenzione di prenotare."},
            "tipo_trattamento": {"type": ["string", "null"],
                                 "description": "igiene, sbiancamento, otturazione, impianto, ortodonzia, urgenza_dolore..."},
            "urgenza": {"type": "string", "enum": list(URGENZE)},
            "slot_proposto": {"type": ["string", "null"],
                              "description": "Preferenza del paziente in parole: 'mattina', 'pomeriggio', o null."},
            "serve_umano": {"type": "boolean",
                            "description": "true se il caso deve passare a un operatore."},
            "risposta_bozza": {"type": "string",
                               "description": "Il messaggio in italiano da mandare al paziente."},
        },
        "required": list(CHIAVI),
        "additionalProperties": False,
    },
    "strict": True,
}

MODELLO_ISTRUZIONI = u"""\
Sei alla reception di {nome}, {luogo}. Parli italiano, con il tono di
{mestiere}: accogliente, chiara, mai da robot.

QUESTO CLIENTE
- Si chiama {nome}.
- Orari: {orari}.
- Dove: {indirizzo}.
- Trattamenti che offre: {trattamenti}.
- Prima visita conoscitiva: {prima_visita}.
Rispondi con QUESTI dati. Se ti chiedono qualcosa che non e' in questo elenco,
dillo con garbo e passa la mano a un operatore invece di inventare.

COSA DEVI CAPIRE
{cosa_capire}

QUANTO E' URGENTE
{scala_urgenza}

QUANDO DEVE RISPONDERE UNA PERSONA (serve_umano = true)
- Qualunque sintomo clinico, quindi sempre in caso di emergenza.
- Lavori importanti: {alto_valore}.
- Il {persona} chiede di parlare con qualcuno.
- Sei in dubbio, o quello che ti scrive non torna.

NON PUOI
{divieti}

Compila SEMPRE lo strumento registra_qualificazione. La risposta al {persona}
va in risposta_bozza, scritta come la manderesti davvero.
"""


def settore_di(cliente):
    """Il mestiere di questo cliente. Senza cliente, il predefinito."""
    return settori.per_chiave(getattr(cliente, "settore", "") or settori.PREDEFINITO)


def istruzioni_per(cliente):
    """Il prompt di QUESTO cliente: mestiere, nome, orari, trattamenti.

    Due cose cambiano insieme. Il MESTIERE decide come si parla e dove ci si
    ferma; il CLIENTE decide nome, orari e trattamenti. La segretaria del
    Centro Bianchi non puo' dare gli orari dello Studio Rossi, perche' non li
    ha mai letti - e non puo' prenotare una rinoplastica, perche' non e' il
    suo mestiere.
    """
    s = settore_di(cliente)
    return MODELLO_ISTRUZIONI.format(
        luogo=s.luogo,
        mestiere=s.mestiere_di_chi_risponde,
        persona=s.persona,
        cosa_capire=s.cosa_capire,
        scala_urgenza=s.scala_urgenza,
        alto_valore=s.alto_valore_detto,
        divieti=s.divieti,
        nome=cliente.nome,
        orari=cliente.orari,
        indirizzo=cliente.indirizzo or "chiedi in studio",
        trattamenti=", ".join(cliente.trattamenti) or "da concordare",
        prima_visita=(u"gratuita" if cliente.prima_visita_gratuita
                      else u"a pagamento, il costo si concorda in studio"),
    )


def _client_anthropic():
    import anthropic
    if not config.ANTHROPIC_API_KEY:
        raise RuntimeError(
            "ANTHROPIC_API_KEY non e' impostata: non posso chiamare Claude. "
            "Impostala nell'ambiente e riprova (non invento una risposta).")
    extra = {}
    # Serve ai test: puntando altrove si prova tutto senza spendere.
    base = os.environ.get("ANTHROPIC_BASE_URL", "").strip()
    if base:
        extra["base_url"] = base
    return anthropic.Anthropic(api_key=config.ANTHROPIC_API_KEY,
                               timeout=60.0, max_retries=2, **extra)


def _conversazione(lead, storico):
    """Lo storico diventa il dialogo. Deve cominciare da chi scrive."""
    grezzi = []
    for m in storico or []:
        testo = (m.get("testo") or "").strip()
        if not testo:
            continue
        ruolo = "assistant" if (m.get("ruolo") or "").lower() == "assistant" else "user"
        grezzi.append({"role": ruolo, "content": testo})
    while grezzi and grezzi[0]["role"] != "user":
        grezzi.pop(0)
    # Due turni di fila dello stesso tipo vanno uniti.
    fusi = []
    for m in grezzi:
        if fusi and fusi[-1]["role"] == m["role"]:
            fusi[-1]["content"] += "\n" + m["content"]
        else:
            fusi.append(dict(m))
    if not fusi:
        nome = (lead or {}).get("nome") or ""
        fusi = [{"role": "user", "content":
                 (u"Salve, sono %s e vorrei delle informazioni." % nome) if nome
                 else u"Salve, vorrei delle informazioni."}]
    if fusi[-1]["role"] != "user":
        fusi.append({"role": "user", "content": u"(il paziente attende una risposta)"})
    return fusi


def all_operatore(motivo=None):
    """La risposta di ripiego: non qualifica niente e chiama una persona."""
    return {
        "qualificato": False, "tipo_trattamento": None, "urgenza": "media",
        "slot_proposto": None, "serve_umano": True,
        "risposta_bozza": u"Grazie per averci scritto. La faccio richiamare da "
                          u"un nostro operatore, che potra' aiutarla meglio.",
        "_motivo_ripiego": motivo,
    }


def _sistema(dati, cliente=None):
    """Mette in riga i campi: tipi giusti, e le regole di sicurezza sopra al modello."""
    fuori = {}
    fuori["qualificato"] = bool(dati.get("qualificato"))
    t = dati.get("tipo_trattamento")
    fuori["tipo_trattamento"] = t.strip() if isinstance(t, str) and t.strip() else None
    u = (dati.get("urgenza") or "").strip().lower() if isinstance(dati.get("urgenza"), str) else ""
    fuori["urgenza"] = u if u in URGENZE else "media"
    s = dati.get("slot_proposto")
    fuori["slot_proposto"] = s.strip() if isinstance(s, str) and s.strip() else None
    fuori["serve_umano"] = bool(dati.get("serve_umano"))
    r = dati.get("risposta_bozza")
    fuori["risposta_bozza"] = r.strip() if isinstance(r, str) and r.strip() else \
        u"Grazie per il suo messaggio, la ricontattiamo a breve."

    # Rete di sicurezza nel codice: non ci si affida al modello per le cose
    # che non devono sbagliare mai.
    if fuori["urgenza"] == "emergenza":
        fuori["serve_umano"] = True
    alto_valore = settore_di(cliente).alto_valore
    if any(k in (fuori["tipo_trattamento"] or "").lower() for k in alto_valore):
        fuori["serve_umano"] = True
    return fuori


def qualifica(lead, storico, cliente):
    """Chiama Claude e torna SEMPRE il dizionario col contratto completo.

    La chiave Anthropic e' UNA SOLA, globale: e' il costo di chi fa girare il
    servizio, non del singolo studio. Quello che cambia per cliente sono le
    istruzioni: nome, orari, trattamenti.
    """
    lead = lead or {}
    lead_id = lead.get("id", 0)
    slug = getattr(cliente, "slug", "-")
    messaggi = _conversazione(lead, storico)
    passo(lead_id, "qualificazione", u"chiamo %s (%d turni)" % (config.MODELLO, len(messaggi)),
          cliente=slug)
    try:
        api = _client_anthropic()
        risposta = api.messages.create(
            model=config.MODELLO,
            max_tokens=2000,
            system=istruzioni_per(cliente),
            tools=[STRUMENTO],
            tool_choice={"type": "tool", "name": STRUMENTO["name"]},
            messages=messaggi,
        )
    except Exception as e:
        passo(lead_id, "qualificazione fallita", u"%s: %s" % (type(e).__name__, e),
              "ERROR", cliente=slug)
        return all_operatore(u"chiamata a Claude fallita: %s" % type(e).__name__)

    dati = None
    for blocco in risposta.content:
        if getattr(blocco, "type", "") == "tool_use" and blocco.name == STRUMENTO["name"]:
            # L'input arriva sempre come JSON gia' interpretato dall'SDK.
            dati = blocco.input if isinstance(blocco.input, dict) else json.loads(blocco.input)
            break
    if dati is None:
        passo(lead_id, "qualificazione fallita",
              u"il modello non ha compilato lo strumento", "ERROR", cliente=slug)
        return all_operatore(u"il modello non ha compilato lo strumento")

    fuori = _sistema(dati, cliente)
    passo(lead_id, "qualificato",
          u"trattamento={} urgenza={} serve_umano={}".format(
              fuori["tipo_trattamento"], fuori["urgenza"], fuori["serve_umano"]),
          cliente=slug)
    return fuori
