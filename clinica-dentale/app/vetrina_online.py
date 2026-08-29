# -*- coding: utf-8 -*-
"""La modalita' vetrina: online, pubblica, e non costa un centesimo.

Serve per il link che mandi a un potenziale cliente. Il problema di mettere
online il sistema vero e' doppio:

  1. ogni visitatore che scrive un messaggio consuma la TUA chiave Anthropic.
     Dieci curiosi che giocano sono dieci chiamate pagate da te;
  2. il cruscotto mostra pazienti. Anche se sono finti, un cruscotto aperto a
     tutti e' un'abitudine sbagliata da prendere.

Con DEMO_PUBBLICA=1 il sistema parte agganciato ai finti Claude e HubSpot -
gli stessi delle prove, che parlano lo stesso protocollo dei veri. Il giro e'
identico: qualificazione, agenda, CRM, coda operatore. Solo che non esce
niente verso l'esterno e non si paga niente.

Nel dubbio, la regola: LA CHIAVE VERA NON SI METTE SU UN LINK PUBBLICO.
"""
import os
import tempfile

ACCESA = (os.environ.get("DEMO_PUBBLICA") or "").strip().lower() in ("1", "si", "true", "yes")

# Quanti pazienti puo' creare il pubblico prima che la vetrina si rifiuti.
# Senza un tetto, il database cresce finche' il disco finisce.
TETTO = int((os.environ.get("DEMO_TETTO") or "300").strip() or 300)

_spegni = None


def prepara_ambiente():
    """Da chiamare PRIMA di importare il resto: sistema le variabili."""
    global _spegni
    if not ACCESA:
        return False

    from tests.finti_servizi import accendi          # viaggiano gia' nel pacchetto
    indirizzo, _spegni = accendi()

    os.environ["ANTHROPIC_BASE_URL"] = indirizzo
    os.environ["ANTHROPIC_API_KEY"] = "vetrina-senza-costi"
    os.environ["HUBSPOT_BASE"] = indirizzo
    os.environ["HUBSPOT_TOKEN_STUDIOROSSI"] = "TOKEN-VETRINA-ROSSI"
    os.environ["HUBSPOT_TOKEN_STUDIOBIANCHI"] = "TOKEN-VETRINA-BIANCHI"
    os.environ.pop("HUBSPOT_TOKEN", None)     # 'demo' resta senza CRM: si vede il ripiego

    # In vetrina il cruscotto e' aperto apposta: e' quello che vuoi far vedere.
    # Le chiavi vere qui non ci sono, quindi non c'e' niente da proteggere.
    os.environ.pop("CONSOLE_TOKEN", None)
    os.environ.pop("WEBHOOK_TOKEN", None)

    if not (os.environ.get("DB_PATH") or "").strip():
        os.environ["DB_PATH"] = os.path.join(
            tempfile.mkdtemp(prefix="vetrina-"), "vetrina.db")
    return True


# Pazienti d'esempio: raccontano da soli le tre cose che vendono il sistema -
# la prenotazione che va da sola, l'emergenza che si ferma, il lavoro
# importante che passa a una persona.
ESEMPI = [
    ("studiorossi", "Giulia Bianchi", "+39 340 1122334", "Sbiancamento Estate",
     u"Buongiorno, vorrei informazioni per uno sbiancamento, preferirei di mattina"),
    ("studiorossi", "Marco Verdi", "+39 349 9988776", "Impianti",
     u"Ho un dolore fortissimo a un dente e sanguina, è un'emergenza"),
    ("studiorossi", "Paolo Ricci", "+39 331 2233445", "Igiene Settembre",
     u"Vorrei prenotare una pulizia dei denti, di pomeriggio se possibile"),
    ("studiobianchi", "Sara Conti", "+39 347 5566778", "Ortodonzia",
     u"Vorrei un preventivo per un apparecchio ortodontico"),
    ("studiobianchi", "Elena Costa", "+39 333 4455667", "Estetica",
     u"Vorrei informazioni per l'estetica dentale, di pomeriggio"),
]


def semina(giro, cerca_cliente, db):
    """Mette dentro gli esempi, ma solo se la vetrina e' vuota.

    Render riavvia il servizio quando gli pare: senza questo controllo, ogni
    riavvio raddoppierebbe i pazienti finti.
    """
    if not ACCESA:
        return 0
    if db.numeri()["pazienti"]:
        return 0
    fatti = 0
    for slug, nome, tel, campagna, messaggio in ESEMPI:
        cliente = cerca_cliente(slug)
        if not cliente:
            continue
        lead_id = db.crea_lead({"cliente": slug, "nome": nome, "telefono": tel,
                                "email": nome.split()[0].lower() + "@example.com",
                                "canale": "console", "canale_id": tel,
                                "campagna": campagna, "stato": "nuovo", "consenso": 1})
        db.aggiungi_messaggio(lead_id, "user", messaggio)
        try:
            giro(cliente, lead_id)
            fatti += 1
        except Exception:
            pass          # un esempio che non parte non deve impedire l'avvio
    return fatti


def pieno(db):
    """True se il pubblico ha giocato abbastanza e la vetrina va fermata."""
    return ACCESA and db.numeri()["pazienti"] >= TETTO
