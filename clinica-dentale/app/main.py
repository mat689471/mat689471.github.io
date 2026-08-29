# -*- coding: utf-8 -*-
"""Il server: un webhook per cliente, e il giro completo di un paziente.

Qui non c'e' logica di dominio, solo l'ordine dei passi. Ogni passo scrive una
riga nel diario, sempre col nome del cliente, cosi' per ogni paziente si puo'
ricostruire cosa e' successo dall'ingresso alla riga sul CRM - e si puo'
mostrare a UNO studio soltanto le sue righe.

Due principi:
  - davanti a qualunque guasto si passa la mano a una persona;
  - un cliente non tocca mai i dati di un altro. Il cliente arriva dall'indirizzo
    (/webhook/lead/studiorossi) e accompagna ogni singola operazione.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Va fatto per primo: sistema le variabili d'ambiente prima che config le legga.
from app import vetrina_online                                   # noqa: E402
vetrina_online.prepara_ambiente()

from fastapi import FastAPI
from fastapi.responses import HTMLResponse, JSONResponse
from pydantic import BaseModel

from app import agent, clienti, config, db, settori, sicurezza
from app.calendar.sqlite_cal import CalendarioSqlite
from app.channels import scegli_canale
from app.crm import scegli_crm
from app.logging_setup import passo, prepara

prepara()
clienti.ricarica()      # se clienti.json e' rotto, si scopre all'avvio
db.prepara()
passo(0, "avvio", json.dumps({**config.diagnosi(),
                              "clienti": [c.slug for c in clienti.tutti().values()]},
                             ensure_ascii=False))

_avviso = sicurezza.avviso()
if _avviso and not vetrina_online.ACCESA:
    passo(0, "sicurezza", _avviso, "WARNING")
if vetrina_online.ACCESA:
    passo(0, "vetrina", u"modalita' vetrina pubblica: Claude e HubSpot finti, "
                        u"nessuna chiave vera, nessun costo", "WARNING")

app = FastAPI(title="Risposta-lead per studi dentistici")

PRIORITA = {"emergenza": 1, "alta": 2, "media": 5, "bassa": 8}


@app.middleware("http")
async def porta(request, prosegui):
    """Nessuno entra senza chiave, quando la chiave e' stata impostata."""
    rifiuto = sicurezza.controlla(request)
    if rifiuto is not None:
        return rifiuto
    return await prosegui(request)


class LeadIn(BaseModel):
    nome: str | None = None
    telefono: str | None = None
    email: str | None = None
    campagna: str | None = None
    messaggio: str | None = None
    consenso: bool = False
    model_config = {"extra": "allow"}


class MessaggioIn(BaseModel):
    lead_id: int | None = None
    telefono: str | None = None
    testo: str = ""
    model_config = {"extra": "allow"}


def _cliente_o_errore(slug):
    """(cliente, risposta di errore). Uno dei due e' sempre None."""
    c = clienti.cerca(slug)
    if c:
        return c, None
    noti = ", ".join(sorted(clienti.tutti()))
    return None, JSONResponse(status_code=404, content={
        "errore": u"cliente sconosciuto: «%s»" % slug,
        "clienti_configurati": noti,
        "come_si_aggiunge": "vedi LEGGIMI.md, sezione «Aggiungere un cliente»"})


# ---------------------------------------------------------------------------
# Il giro di un paziente
# ---------------------------------------------------------------------------
def _recapito(cliente, lead, lead_id):
    """Dove scrivere a questo paziente, secondo il canale del suo cliente.

    Non e' un dettaglio: mandare un'email a un numero di telefono, o un
    WhatsApp a un indirizzo, fallisce sempre. Il canale email vuole la mail,
    quello WhatsApp il numero; la console si accontenta di quello che c'e'.
    """
    tipo = (dict(getattr(cliente, "canale", None) or {}).get("tipo") or "console").lower()
    if tipo == "email":
        return lead.get("email") or lead.get("telefono") or str(lead_id)
    if tipo == "whatsapp":
        return lead.get("telefono") or lead.get("email") or str(lead_id)
    return lead.get("telefono") or lead.get("email") or str(lead_id)


def _scrivi_crm(cliente, lead_id, lead, qual):
    """Scrive contatto e trattativa sul CRM DI QUESTO cliente.

    Vale per tutti i pazienti, anche per quelli che passano a un operatore.
    Prima non era cosi': chi veniva passato a una persona non arrivava mai al
    CRM. Nel dentale erano due casi; in medicina estetica sono quasi TUTTI i
    casi che valgono qualcosa - chirurgia e iniettivi passano sempre da una
    persona - quindi i contatti piu' importanti sparivano proprio da dove il
    cliente li conta.

    Un contatto pagato va registrato comunque: che poi lo chiami una persona
    invece di un programma non lo rende meno reale. Nella trattativa restano
    urgenza e serve_umano, cosi' si vede subito che e' da richiamare.

    Se il CRM di questo cliente rifiuta, il paziente non si perde: finisce
    nell'archivio locale marcato da sincronizzare, e gli altri clienti non se
    ne accorgono nemmeno.
    """
    crm, nota = scegli_crm(cliente)
    passo(lead_id, "crm", nota, cliente=cliente.slug)
    try:
        c = crm.contatto(lead)
        d = crm.deal(c["contact_id"], lead, qual)
        esito = {"contact_id": c["contact_id"], "deal_id": d["deal_id"],
                 "fonte": c["fonte"]}
        passo(lead_id, "crm scritto", u"fonte={} contatto={} trattativa={}".format(
            c["fonte"], c["contact_id"], d["deal_id"]), cliente=cliente.slug)
    except Exception as e:
        passo(lead_id, "crm fallito", u"{}: {} -> scrivo in locale".format(
            type(e).__name__, e), "WARNING", cliente=cliente.slug)
        from app.crm.sqlite_crm import CrmLocale
        riserva = CrmLocale(cliente.slug, u"{}: {}".format(type(e).__name__, e))
        c = riserva.contatto(lead)
        d = riserva.deal(c["contact_id"], lead, qual)
        esito = {"contact_id": c["contact_id"], "deal_id": d["deal_id"],
                 "fonte": c["fonte"], "da_sincronizzare": True}
    db.aggiorna_lead(lead_id, crm_contact_id=c["contact_id"],
                     crm_deal_id=d["deal_id"])
    return esito


def _handoff(cliente, lead_id, qual, motivo=None):
    """Ferma l'automazione e mette il paziente in mano a un operatore DI QUESTO
    studio. La coda e' sua: nessun altro cliente la vede."""
    motivo = motivo or u"serve_umano (urgenza={}, trattamento={})".format(
        qual.get("urgenza"), qual.get("tipo_trattamento"))
    priorita = PRIORITA.get(qual.get("urgenza"), 5)
    db.aggiorna_lead(lead_id, stato="da_operatore", serve_umano=1,
                     urgenza=qual.get("urgenza"),
                     tipo_trattamento=qual.get("tipo_trattamento"))
    db.accoda_operatore(cliente.slug, lead_id, motivo, priorita,
                        json.dumps(qual, ensure_ascii=False))
    passo(lead_id, "OPERATORE", u"{} (priorita {})".format(motivo, priorita),
          "WARNING", cliente=cliente.slug)

    lead = db.leggi_lead(lead_id, cliente.slug) or {}
    cortesia = (u"Grazie, la mettiamo subito in contatto con un nostro operatore, "
                u"che la richiamera' al piu' presto.")
    invio = _canale(cliente, lead_id).invia(_recapito(cliente, lead, lead_id), cortesia)
    passo(lead_id, "risposta inviata" if invio["ok"] else "risposta NON inviata",
          u"canale={} ok={} {}".format(invio["canale"], invio["ok"],
                                       invio.get("errore") or ""),
          "INFO" if invio["ok"] else "WARNING", cliente=cliente.slug)
    db.aggiungi_messaggio(lead_id, "assistant", cortesia)
    esito_crm = _scrivi_crm(cliente, lead_id, lead, qual)
    return {"stato": "da_operatore", "in_coda": True, "crm": esito_crm,
            "risposta": cortesia}


def _canale(cliente, lead_id=0):
    """Il canale di QUESTO cliente, con la nota nel diario.

    Ogni cliente puo' avere il suo: console (non manda niente), email, o
    WhatsApp col proprio numero. La nota dice quale si sta usando, cosi' nel
    diario si vede subito se un cliente sta ancora girando a vuoto.
    """
    canale, nota = scegli_canale(cliente)
    passo(lead_id, "canale", nota, cliente=cliente.slug)
    return canale


def _automatico(cliente, lead_id, lead, qual):
    """Il percorso normale: posto in agenda, risposta, CRM. Tutto di questo studio."""
    db.aggiorna_lead(lead_id, urgenza=qual.get("urgenza"),
                     tipo_trattamento=qual.get("tipo_trattamento"))
    testo = qual["risposta_bozza"]
    stato = "qualificato"

    calendario = CalendarioSqlite(cliente.slug)
    slot = calendario.slot_libero(qual.get("slot_proposto"), qual.get("urgenza"))
    if slot:
        esito = calendario.prenota(slot["slot_id"], lead_id)
        if esito["ok"]:
            stato = "prenotato"
            quando = slot["inizio"].replace("T", " ").replace("Z", "")
            testo += u"\n\nLe ho riservato un posto per {} presso {}. " \
                     u"Va bene o preferisce un altro momento?".format(
                         quando, slot.get("studio") or cliente.nome)
            passo(lead_id, "prenotato", u"posto {} - {}".format(
                slot["slot_id"], slot["inizio"]), cliente=cliente.slug)
        else:
            passo(lead_id, "prenotazione fallita", esito.get("errore") or "",
                  "WARNING", cliente=cliente.slug)
    else:
        passo(lead_id, "agenda piena", "", "WARNING", cliente=cliente.slug)
        if qual.get("urgenza") in ("alta", "emergenza"):
            return _handoff(cliente, lead_id, qual,
                            u"agenda piena con urgenza %s" % qual["urgenza"])

    invio = _canale(cliente, lead_id).invia(_recapito(cliente, lead, lead_id), testo)
    passo(lead_id, "risposta inviata",
          u"canale={} ok={} simulato={}".format(invio["canale"], invio["ok"],
                                                invio["simulato"]),
          cliente=cliente.slug)
    if not invio["ok"]:
        # Non siamo riusciti a parlargli. Un paziente che non riceve niente e'
        # un paziente perso: lo prende una persona, e sa perche'.
        passo(lead_id, "risposta NON inviata", invio.get("errore") or "",
              "ERROR", cliente=cliente.slug)
        return _handoff(cliente, lead_id, qual,
                        u"la risposta non e' partita (%s): richiamare a mano"
                        % (invio.get("errore") or invio["canale"]))
    db.aggiungi_messaggio(lead_id, "assistant", testo,
                          json.dumps(qual, ensure_ascii=False))

    esito_crm = _scrivi_crm(cliente, lead_id, lead, qual)

    db.aggiorna_lead(lead_id, stato=stato)
    return {"stato": stato, "in_coda": False, "crm": esito_crm, "risposta": testo}


def _giro(cliente, lead_id):
    lead = db.leggi_lead(lead_id, cliente.slug) or {}
    if not lead:
        return {"errore": "questo paziente non e' di %s" % cliente.slug}

    if db.in_carico_a_operatore(lead_id):
        passo(lead_id, "gia' con l'operatore", "l'automazione non interviene",
              cliente=cliente.slug)
        return {"lead_id": lead_id, "cliente": cliente.slug, "qualificazione": None,
                "stato": "da_operatore", "in_coda": True, "crm": None, "risposta": None}

    qual = agent.qualifica(lead, db.storico(lead_id), cliente)
    esito = (_handoff(cliente, lead_id, qual) if qual["serve_umano"]
             else _automatico(cliente, lead_id, lead, qual))
    passo(lead_id, "fine turno", u"stato={}".format(esito["stato"]), cliente=cliente.slug)
    return {"lead_id": lead_id, "cliente": cliente.slug, "qualificazione": qual, **esito}


# ---------------------------------------------------------------------------
# I webhook, uno per cliente
# ---------------------------------------------------------------------------
def _entra(cliente, dati):
    if vetrina_online.pieno(db):
        return JSONResponse(status_code=429, content={
            "errore": "la vetrina ha raggiunto il numero massimo di prove",
            "cosa_fare": "riavvia il servizio per ripartire da zero"})
    lead_id = db.crea_lead({
        "cliente": cliente.slug,
        "nome": dati.nome, "email": dati.email, "telefono": dati.telefono,
        "canale": cliente.canale.get("tipo", "console"),
        "canale_id": dati.telefono or dati.email,
        "campagna": dati.campagna, "stato": "nuovo",
        "consenso": 1 if dati.consenso else 0,
    })
    passo(lead_id, "ingresso", u"campagna={}".format(dati.campagna or "-"),
          cliente=cliente.slug)
    if dati.messaggio:
        db.aggiungi_messaggio(lead_id, "user", dati.messaggio)
    return _giro(cliente, lead_id)


@app.post("/webhook/lead/{cliente_slug}")
def webhook_lead(cliente_slug: str, dati: LeadIn):
    cliente, errore = _cliente_o_errore(cliente_slug)
    return errore or _entra(cliente, dati)


@app.post("/webhook/message/{cliente_slug}")
def webhook_message(cliente_slug: str, dati: MessaggioIn):
    cliente, errore = _cliente_o_errore(cliente_slug)
    if errore:
        return errore
    # Il numero si cerca SOLO fra i pazienti di questo studio.
    lead_id = dati.lead_id or db.lead_per_telefono(dati.telefono, cliente.slug)
    if not lead_id or not db.leggi_lead(lead_id, cliente.slug):
        passo(0, "messaggio senza paziente", u"telefono={}".format(dati.telefono or "-"),
              "WARNING", cliente=cliente.slug)
        return JSONResponse(status_code=404, content={
            "errore": u"non trovo questo paziente fra quelli di %s" % cliente.slug})
    passo(lead_id, "messaggio in arrivo", (dati.testo or "")[:60], cliente=cliente.slug)
    db.aggiungi_messaggio(lead_id, "user", dati.testo or "")
    return _giro(cliente, lead_id)


# Le vecchie porte senza cliente restano valide e vanno al cliente predefinito:
# chi aveva gia' collegato un modulo non deve rifare niente.
@app.post("/webhook/lead")
def webhook_lead_predefinito(dati: LeadIn):
    return _entra(clienti.predefinito(), dati)


@app.post("/webhook/message")
def webhook_message_predefinito(dati: MessaggioIn):
    return webhook_message(clienti.predefinito().slug, dati)


# ---------------------------------------------------------------------------
# Il cruscotto
# ---------------------------------------------------------------------------
WEB = os.path.join(os.path.dirname(os.path.abspath(__file__)), "web")
PAGINA = os.path.join(WEB, "console.html")
VETRINA = os.path.join(WEB, "vetrina.html")


@app.get("/", response_class=HTMLResponse)
def cruscotto():
    with open(PAGINA, encoding="utf-8") as f:
        return f.read()


@app.get("/vetrina", response_class=HTMLResponse)
def vetrina(settore: str | None = None):
    """La pagina da far vedere al titolare, nel SUO mestiere.

    Non chiede la chiave e non mostra nemmeno un paziente: dentro non c'e' un
    dato vero, solo il racconto di cosa fa il sistema. Si puo' mandare per
    email o aprire davanti a un cliente senza pensarci.

    `?settore=estetica` cambia i testi: a una clinica di chirurgia estetica non
    si manda una pagina che parla di otturazioni. La pagina e' una sola - il
    mestiere e' un dato, come per l'agente.
    """
    try:
        scelto = settori.per_chiave(settore)
    except settori.SettoreSconosciuto as e:
        return HTMLResponse(u"<p style='font:16px system-ui;padding:40px'>%s</p>" % e,
                            status_code=404)
    with open(VETRINA, encoding="utf-8") as f:
        pagina = f.read()
    for chiave, valore in scelto.vetrina.items():
        pagina = pagina.replace("{{%s}}" % chiave, valore)
    return pagina


@app.get("/api/clienti")
def api_clienti():
    fisso = sicurezza.cliente_bloccato()
    elenco = [c for c in clienti.elenco_pubblico()
              if not fisso or c["slug"] == fisso]
    return {"clienti": elenco,
            "predefinito": fisso or clienti.predefinito().slug}


@app.get("/api/stato")
def stato(cliente: str | None = None):
    """Tutto quello che serve alla pagina. Senza 'cliente' si vede tutto.

    Se CONSOLE_CLIENTE e' impostata, si vede solo quello studio: la scelta
    nell'indirizzo viene ignorata, e nell'elenco compare lui soltanto.
    """
    cliente = sicurezza.filtra(cliente) or None
    if cliente and not clienti.cerca(cliente):
        return JSONResponse(status_code=404, content={"errore": "cliente sconosciuto"})
    fisso = sicurezza.cliente_bloccato()
    visibili = [c for c in clienti.elenco_pubblico()
                if not fisso or c["slug"] == fisso]
    return {"numeri": db.numeri(cliente), "coda": db.coda_con_nomi(cliente),
            "pazienti": db.elenco_leads(cliente), "agenda": db.agenda(cliente),
            "clienti": visibili, "filtro": cliente, "bloccato": fisso or None,
            "config": config.diagnosi(), "sicurezza": sicurezza.stato(),
            "vetrina": vetrina_online.ACCESA}


@app.get("/api/paziente/{lead_id}")
def paziente(lead_id: int, cliente: str | None = None):
    """La scheda di un paziente — solo se e' dello studio che si sta guardando.

    Senza questo filtro bastava cambiare il numero nell'indirizzo per leggere
    il paziente di un altro studio: l'isolamento valeva per gli elenchi ma non
    per la singola scheda. Ora vale per tutti e due.
    """
    dove = sicurezza.filtra(cliente)
    riga = db.leggi_lead(lead_id, dove or None)
    if not riga:
        return JSONResponse(status_code=404,
                            content={"errore": "questo paziente non esiste, "
                                               "o non e' dello studio che stai guardando"})
    return {"paziente": riga, "conversazione": db.storico(lead_id),
            "coda": [v for v in db.coda_aperta(riga["cliente"])
                     if v["lead_id"] == lead_id]}


@app.delete("/api/paziente/{lead_id}")
def cancella_paziente(lead_id: int, cliente: str | None = None):
    """Diritto alla cancellazione: il paziente sparisce, davvero.

    Un paziente che scrive «ho un ascesso» lascia un dato sanitario. Se chiede
    di essere cancellato, deve sparire da qui: messaggi, posto in agenda, riga
    sul CRM locale, coda. Sul CRM esterno va cancellato dal CRM: qui si scrive
    cosa resta da fare, invece di far finta.
    """
    dove = sicurezza.filtra(cliente)
    riga = db.leggi_lead(lead_id, dove or None)
    if not riga:
        return JSONResponse(status_code=404, content={
            "errore": "questo paziente non esiste, o non e' dello studio che stai guardando"})
    esito = db.cancella_lead(lead_id)
    passo(lead_id, "CANCELLATO", u"richiesta di cancellazione dati eseguita",
          "WARNING", cliente=riga["cliente"])
    return {"ok": True, "cancellato": lead_id, **esito,
            "resta_da_fare": (u"su HubSpot il contatto %s va cancellato dal CRM"
                              % riga["crm_contact_id"]) if riga.get("crm_contact_id") else None}


class AzioneCoda(BaseModel):
    operatore: str | None = None


def _azione_coda(voce_id, stato, operatore):
    esito = db.cambia_voce_coda(voce_id, stato, operatore or "operatore")
    if esito:
        passo(esito["lead_id"],
              "preso in carico" if stato == "preso" else "chiuso dall'operatore",
              operatore or "operatore", cliente=esito["cliente"])
        return {"ok": True, **esito}
    return {"ok": False}


@app.post("/api/coda/{voce_id}/prendi")
def prendi(voce_id: int, dati: AzioneCoda):
    return _azione_coda(voce_id, "preso", dati.operatore)


@app.post("/api/coda/{voce_id}/chiudi")
def chiudi(voce_id: int, dati: AzioneCoda):
    return _azione_coda(voce_id, "chiuso", dati.operatore)


@app.get("/coda")
def coda_pubblica(cliente: str | None = None):
    """Chi aspetta un operatore. Senza 'cliente' si vede tutto; con il nome di
    uno studio, solo la sua coda."""
    cliente = sicurezza.filtra(cliente) or None
    if cliente and not clienti.cerca(cliente):
        return JSONResponse(status_code=404, content={"errore": "cliente sconosciuto"})
    return {"cliente": cliente, "coda": db.coda_aperta(cliente)}


@app.get("/coda/{cliente_slug}")
def coda_di(cliente_slug: str):
    fisso = sicurezza.cliente_bloccato()
    if fisso and fisso != cliente_slug.strip().lower():
        return JSONResponse(status_code=403, content={
            "errore": "questo cruscotto e' bloccato su un solo studio"})
    cliente, errore = _cliente_o_errore(cliente_slug)
    return errore or {"cliente": cliente.slug, "coda": db.coda_aperta(cliente.slug)}


@app.get("/health")
def salute():
    """Vivo? E con quanti studi collegati? (nessun segreto qui dentro)"""
    elenco = clienti.elenco_pubblico()
    return {"ok": True, "vetrina_pubblica": vetrina_online.ACCESA,
            **config.diagnosi(), **sicurezza.stato(),
            "clienti": len(elenco),
            "clienti_con_crm": sum(1 for c in elenco if c["hubspot"]),
            "slug": [c["slug"] for c in elenco]}


# ---------------------------------------------------------------------------
# Vetrina pubblica: gli esempi entrano da soli, cosi' il link che mandi a un
# cliente non si apre su una pagina vuota.
# ---------------------------------------------------------------------------
if vetrina_online.ACCESA:
    _seminati = vetrina_online.semina(_giro, clienti.cerca, db)
    if _seminati:
        passo(0, "vetrina", u"%d pazienti d'esempio caricati" % _seminati)
