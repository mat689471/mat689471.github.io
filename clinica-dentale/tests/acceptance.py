# -*- coding: utf-8 -*-
"""La prova che il sistema e' vero: cinque punti, uno per uno, in chiaro.

  python tests/acceptance.py            con le chiavi vere -> servizi veri
  python tests/acceptance.py --finto    senza chiavi       -> servizi finti

I finti parlano lo stesso protocollo dei veri: se il giro regge con quelli,
regge anche con gli altri. Servono per provare senza spendere.

Ogni punto stampa PASS o FAIL, e alla fine c'e' il verdetto.
"""
import io
import json
import os
import sys

# La console Windows e' cp1252 e muore sugli accenti: qui si stampa in UTF-8.
for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is not None and hasattr(_f, "buffer"):
        setattr(sys, _n, io.TextIOWrapper(_f.buffer, encoding="utf-8",
                                          errors="replace", line_buffering=True))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

FINTO = "--finto" in sys.argv or not os.environ.get("ANTHROPIC_API_KEY")
_spegni = None
if FINTO:
    from tests.finti_servizi import accendi
    _indirizzo, _spegni = accendi()
    os.environ["ANTHROPIC_BASE_URL"] = _indirizzo
    os.environ["ANTHROPIC_API_KEY"] = "chiave-di-prova"
    os.environ["HUBSPOT_BASE"] = _indirizzo
    os.environ["HUBSPOT_TOKEN"] = "TOKEN-DI-PROVA"

# Ogni giro parte da un database pulito, altrimenti il secondo lead trova
# l'agenda mezza occupata dal primo e i risultati non si confrontano.
import tempfile
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="clinica-"), "prova.db")

from fastapi.testclient import TestClient    # noqa: E402
from app import clienti, config, db          # noqa: E402
from app.main import app                     # noqa: E402

esiti = []


def riga(c="="):
    print(c * 78)


def titolo(t):
    print()
    riga()
    print(t)
    riga()


def mostra(etichetta, dato):
    print(u"%s:" % etichetta)
    print(json.dumps(dato, ensure_ascii=False, indent=2))


def verifica(nome, condizione, dettaglio):
    esiti.append((nome, bool(condizione), dettaglio))
    print(u"\n   -> %s  %s" % ("PASS" if condizione else "FAIL", dettaglio))


def main():
    riga()
    print("PROVA DI ACCETTAZIONE - risposta-lead per clinica dentale")
    riga()
    print(u"Servizi     : %s" % (u"FINTI (nessuna spesa, stesso protocollo)"
                                 if FINTO else u"VERI (Anthropic + HubSpot)"))
    print(u"Modello     : %s" % config.MODELLO)
    studio = clienti.predefinito()
    print(u"Studio      : %s (%s)" % (studio.nome, studio.slug))
    print(u"CRM         : %s" % ("HubSpot" if studio.ha_hubspot else "locale"))
    print(u"Database    : %s" % config.DB_PATH)

    cliente = TestClient(app)

    # ---------------------------------------------------------------- 1 ----
    titolo("PUNTO 1 - un lead entra da /webhook/lead (formato Meta Lead Ads)")
    lead = {"nome": "Giulia Bianchi", "telefono": "+39 340 1122334",
            "email": "giulia.bianchi@example.com", "campagna": "Sbiancamento Estate",
            "messaggio": "Vorrei informazioni per uno sbiancamento dei denti, "
                         "preferirei di mattina", "consenso": True}
    mostra("RICHIESTA", lead)
    r1 = cliente.post("/webhook/lead", json=lead)
    corpo1 = r1.json()
    mostra("RISPOSTA", corpo1)
    verifica("1 - ingresso lead",
             r1.status_code == 200 and corpo1.get("lead_id"),
             u"HTTP %s, lead_id=%s" % (r1.status_code, corpo1.get("lead_id")))

    # ---------------------------------------------------------------- 2 ----
    titolo("PUNTO 2 - la qualificazione tornata da Claude")
    qual = corpo1.get("qualificazione") or {}
    mostra("JSON di qualificazione", qual)
    attese = ["qualificato", "risposta_bozza", "serve_umano", "slot_proposto",
              "tipo_trattamento", "urgenza"]
    mancanti = [k for k in attese if k not in qual]
    tipi_ok = (isinstance(qual.get("qualificato"), bool)
               and isinstance(qual.get("serve_umano"), bool)
               and qual.get("urgenza") in ("bassa", "media", "alta", "emergenza"))
    verifica("2 - qualificazione", not mancanti and tipi_ok,
             u"%d/%d chiavi presenti, tipi %s" % (len(attese) - len(mancanti),
                                                  len(attese),
                                                  "corretti" if tipi_ok else "SBAGLIATI"))

    # ---------------------------------------------------------------- 3 ----
    titolo("PUNTO 3 - la risposta scritta per il paziente, e l'invio")
    print(u"Testo generato da Claude:\n  %s" % (qual.get("risposta_bozza") or "(vuoto)"))
    print(u"\nTesto realmente inviato dal canale:\n  %s" % (corpo1.get("risposta") or "(niente)"))
    log_invii = os.path.join(config.RADICE, "dati", "messaggi-inviati.log")
    inviato = os.path.exists(log_invii) and os.path.getsize(log_invii) > 0
    print(u"\nATTENZIONE: canale di prova, nessun SMS o WhatsApp e' partito davvero.")
    verifica("3 - risposta e invio",
             bool(qual.get("risposta_bozza")) and inviato,
             u"bozza presente e registrata in dati/messaggi-inviati.log")

    # ---------------------------------------------------------------- 4 ----
    titolo("PUNTO 4 - la riga scritta sul CRM")
    crm = corpo1.get("crm") or {}
    mostra("esito CRM", crm)
    conn = db.connessione()
    try:
        riga_lead = dict(conn.execute("SELECT id,stato,crm_contact_id,crm_deal_id "
                                      "FROM leads WHERE id = ?",
                                      (corpo1["lead_id"],)).fetchone())
        locali = conn.execute("SELECT COUNT(*) n FROM crm_records").fetchone()["n"]
    finally:
        conn.close()
    mostra("riga del lead nel database", riga_lead)
    print(u"righe nella tabella crm_records (copia locale): %d" % locali)
    verifica("4 - CRM", crm.get("contact_id") and crm.get("deal_id")
             and riga_lead["crm_contact_id"],
             u"fonte=%s contatto=%s trattativa=%s" % (crm.get("fonte"),
                                                      crm.get("contact_id"),
                                                      crm.get("deal_id")))

    # ---------------------------------------------------------------- 5 ----
    titolo("PUNTO 5 - un'emergenza si ferma e passa a una persona")
    urgente = {"nome": "Marco Verdi", "telefono": "+39 349 9988776",
               "email": "marco.verdi@example.com", "campagna": "Impianti",
               "messaggio": "Ho un dolore fortissimo a un dente e sanguina, "
                            "e' un'emergenza"}
    mostra("RICHIESTA", urgente)
    r2 = cliente.post("/webhook/lead", json=urgente)
    corpo2 = r2.json()
    mostra("RISPOSTA", corpo2)
    lead2 = corpo2["lead_id"]

    conn = db.connessione()
    try:
        stato2 = conn.execute("SELECT stato FROM leads WHERE id = ?",
                              (lead2,)).fetchone()["stato"]
        slot_presi = conn.execute("SELECT COUNT(*) n FROM disponibilita "
                                  "WHERE lead_id = ?", (lead2,)).fetchone()["n"]
    finally:
        conn.close()
    coda = cliente.get("/coda").json()["coda"]
    in_coda = [v for v in coda if v["lead_id"] == lead2]
    mostra("coda operatore", coda)
    print(u"stato del lead      : %s" % stato2)
    print(u"slot prenotati da solo: %d  (deve essere 0)" % slot_presi)
    verifica("5 - passaggio all'operatore",
             stato2 == "da_operatore" and in_coda and slot_presi == 0
             and in_coda[0]["priorita"] == 1,
             u"stato=%s, in coda con priorita %s, nessuna prenotazione automatica"
             % (stato2, in_coda[0]["priorita"] if in_coda else "-"))

    # ------------------------------------------------------------ verdetto --
    titolo("VERDETTO")
    for nome, ok, dettaglio in esiti:
        print(u"  [%s] %-32s %s" % ("PASS" if ok else "FAIL", nome, dettaglio))
    riga("-")
    tutto = all(ok for _, ok, _ in esiti)
    print(u"  %s" % (u"TUTTI E CINQUE I PUNTI PASSANO." if tutto
                     else u"QUALCOSA NON PASSA: guarda i FAIL qui sopra."))
    if FINTO:
        print(u"\n  Nota: prova fatta contro servizi FINTI (stesso protocollo dei veri).")
        print(u"  Per farla contro Claude e HubSpot veri, imposta ANTHROPIC_API_KEY")
        print(u"  e HUBSPOT_TOKEN e rilancia senza --finto.")
    riga()
    return 0 if tutto else 1


if __name__ == "__main__":
    try:
        codice = main()
    finally:
        if _spegni:
            _spegni()
    sys.exit(codice)
