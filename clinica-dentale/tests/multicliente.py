# -*- coding: utf-8 -*-
"""La prova che due studi non si toccano.

  python tests/multicliente.py            servizi finti, gratis
  python tests/multicliente.py --veri     Claude vero (serve ANTHROPIC_API_KEY)

Cinque punti, come il capitolato:
  1. due clienti configurati, ognuno col SUO token da variabile d'ambiente
  2. un lead a studiorossi   -> contatto e trattativa sul HubSpot di Rossi
  3. un lead a studiobianchi -> sull'altro HubSpot
  4. ISOLAMENTO: niente di Rossi compare da Bianchi, e viceversa
  5. un'emergenza finisce SOLO nella coda del suo studio
"""
import io
import json
import os
import sys
import tempfile
import urllib.request

for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is not None and hasattr(_f, "buffer"):
        setattr(sys, _n, io.TextIOWrapper(_f.buffer, encoding="utf-8",
                                          errors="replace", line_buffering=True))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

VERI = "--veri" in sys.argv and os.environ.get("ANTHROPIC_API_KEY")
from tests.finti_servizi import accendi                      # noqa: E402

INDIRIZZO, SPEGNI = accendi()
if not VERI:
    os.environ["ANTHROPIC_BASE_URL"] = INDIRIZZO
    os.environ["ANTHROPIC_API_KEY"] = "chiave-di-prova"
# HubSpot resta finto anche con Claude vero: cosi' l'isolamento si puo'
# ispezionare senza sporcare due CRM veri.
os.environ["HUBSPOT_BASE"] = INDIRIZZO
os.environ["HUBSPOT_TOKEN_STUDIOROSSI"] = "TOKEN-ROSSI"
os.environ["HUBSPOT_TOKEN_STUDIOBIANCHI"] = "TOKEN-BIANCHI"
os.environ.pop("HUBSPOT_TOKEN", None)      # il cliente 'demo' resta senza CRM
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="multi-"), "prova.db")

from fastapi.testclient import TestClient                    # noqa: E402
from app import clienti, config, db                          # noqa: E402
from app.main import app                                     # noqa: E402

C = TestClient(app)
esiti = []
ROSSI, BIANCHI = "studiorossi", "studiobianchi"


def riga(c="="):
    print(c * 78)


def titolo(t):
    print(); riga(); print(t); riga()


def mostra(eti, dato):
    print(u"%s:" % eti)
    print(json.dumps(dato, ensure_ascii=False, indent=2)[:1400])


def verifica(nome, ok, dettaglio):
    esiti.append((nome, bool(ok), dettaglio))
    print(u"\n   -> %s  %s" % ("PASS" if ok else "FAIL", dettaglio))


def archivi():
    """Cosa c'e' dentro il finto HubSpot, token per token."""
    with urllib.request.urlopen(INDIRIZZO + "/_ispeziona", timeout=5) as r:
        return json.loads(r.read().decode())


def main():
    riga()
    print("PROVA MULTI-CLIENTE - due studi, nessuna contaminazione")
    riga()
    print(u"Claude    : %s" % (u"VERO (%s)" % config.MODELLO if VERI else u"finto"))
    print(u"HubSpot   : finto, un archivio separato per token")
    print(u"Database  : %s" % config.DB_PATH)

    # ----------------------------------------------------------------- 1 ---
    titolo("PUNTO 1 - due clienti, ognuno col suo token da variabile d'ambiente")
    elenco = C.get("/api/clienti").json()["clienti"]
    mostra("clienti configurati", elenco)
    r = next(c for c in elenco if c["slug"] == ROSSI)
    b = next(c for c in elenco if c["slug"] == BIANCHI)
    testo = json.dumps(elenco)
    verifica("1 - due clienti isolati",
             r["hubspot"] and b["hubspot"]
             and r["hubspot_env"] != b["hubspot_env"]
             and "TOKEN-ROSSI" not in testo and "TOKEN-BIANCHI" not in testo,
             u"%s da %s, %s da %s — e nessun token compare nelle risposte"
             % (r["slug"], r["hubspot_env"], b["slug"], b["hubspot_env"]))

    # ----------------------------------------------------------------- 2 ---
    titolo("PUNTO 2 - un paziente scrive allo Studio Rossi")
    lead_r = {"nome": "Anna Rossi Paziente", "telefono": "+39 340 0000001",
              "email": "anna.rossi@example.com", "campagna": "Igiene",
              "messaggio": "Vorrei prenotare una pulizia dei denti, di mattina"}
    mostra("POST /webhook/lead/" + ROSSI, lead_r)
    risp_r = C.post("/webhook/lead/%s" % ROSSI, json=lead_r).json()
    mostra("risposta", {k: risp_r.get(k) for k in
                        ("lead_id", "cliente", "stato", "crm")})
    verifica("2 - lead su Rossi",
             risp_r.get("cliente") == ROSSI and (risp_r.get("crm") or {}).get("fonte") == "hubspot",
             u"contatto %s e trattativa %s sul CRM di Rossi"
             % ((risp_r.get("crm") or {}).get("contact_id"),
                (risp_r.get("crm") or {}).get("deal_id")))

    # ----------------------------------------------------------------- 3 ---
    titolo("PUNTO 3 - un paziente scrive al Centro Bianchi")
    lead_b = {"nome": "Bruno Bianchi Paziente", "telefono": "+39 340 0000002",
              "email": "bruno.bianchi@example.com", "campagna": "Estetica",
              "messaggio": "Vorrei informazioni per uno sbiancamento, di pomeriggio"}
    mostra("POST /webhook/lead/" + BIANCHI, lead_b)
    risp_b = C.post("/webhook/lead/%s" % BIANCHI, json=lead_b).json()
    mostra("risposta", {k: risp_b.get(k) for k in
                        ("lead_id", "cliente", "stato", "crm")})
    verifica("3 - lead su Bianchi",
             risp_b.get("cliente") == BIANCHI and (risp_b.get("crm") or {}).get("fonte") == "hubspot",
             u"contatto %s e trattativa %s sul CRM di Bianchi"
             % ((risp_b.get("crm") or {}).get("contact_id"),
                (risp_b.get("crm") or {}).get("deal_id")))

    # ----------------------------------------------------------------- 4 ---
    titolo("PUNTO 4 - ISOLAMENTO: niente passa da uno studio all'altro")
    a = archivi()
    print(u"Cosa c'e' nel CRM di ciascuno studio:")
    for token, oggetti in sorted(a.items()):
        print(u"  %-16s %s" % (token, [o["nome"] for o in oggetti]))

    dentro_rossi = json.dumps(a.get("TOKEN-ROSSI", []), ensure_ascii=False)
    dentro_bianchi = json.dumps(a.get("TOKEN-BIANCHI", []), ensure_ascii=False)
    crm_pulito = ("Anna" in dentro_rossi and "Anna" not in dentro_bianchi
                  and "Bruno" in dentro_bianchi and "Bruno" not in dentro_rossi)

    # il cruscotto filtrato per cliente
    st_r = C.get("/api/stato?cliente=%s" % ROSSI).json()
    st_b = C.get("/api/stato?cliente=%s" % BIANCHI).json()
    nomi_r = [p["nome"] for p in st_r["pazienti"]]
    nomi_b = [p["nome"] for p in st_b["pazienti"]]
    print(u"\npazienti visti da Rossi  : %s" % nomi_r)
    print(u"pazienti visti da Bianchi: %s" % nomi_b)
    liste_pulite = (lead_r["nome"] in nomi_r and lead_r["nome"] not in nomi_b
                    and lead_b["nome"] in nomi_b and lead_b["nome"] not in nomi_r)

    # le agende
    ag_r = [s["nome"] for s in st_r["agenda"]]
    ag_b = [s["nome"] for s in st_b["agenda"]]
    print(u"agenda di Rossi  : %s" % ag_r)
    print(u"agenda di Bianchi: %s" % ag_b)
    agende_pulite = (lead_r["nome"] not in ag_b and lead_b["nome"] not in ag_r)

    # un id dell'altro studio non si legge nemmeno sapendolo
    altrui = db.leggi_lead(risp_b["lead_id"], ROSSI)
    print(u"\nRossi prova a leggere il paziente %s di Bianchi: %s"
          % (risp_b["lead_id"], "niente" if altrui is None else "LO VEDE!"))

    # lo stesso numero di telefono su due studi resta due persone diverse
    C.post("/webhook/lead/%s" % ROSSI, json={
        "nome": "Omonimo da Rossi", "telefono": "+39 340 9999999",
        "email": "omo.rossi@example.com", "messaggio": "vorrei un controllo"})
    C.post("/webhook/lead/%s" % BIANCHI, json={
        "nome": "Omonimo da Bianchi", "telefono": "+39 340 9999999",
        "email": "omo.bianchi@example.com", "messaggio": "vorrei un controllo"})
    id_r = db.lead_per_telefono("+39 340 9999999", ROSSI)
    id_b = db.lead_per_telefono("+39 340 9999999", BIANCHI)
    print(u"stesso numero su due studi -> due pazienti distinti: %s e %s" % (id_r, id_b))

    verifica("4 - isolamento",
             crm_pulito and liste_pulite and agende_pulite and altrui is None
             and id_r != id_b,
             u"CRM separati, elenchi separati, agende separate, "
             u"lettura incrociata negata, stesso numero = due pazienti")

    # ----------------------------------------------------------------- 5 ---
    titolo("PUNTO 5 - un'emergenza finisce SOLO nella coda del suo studio")
    urgente = {"nome": "Urgente da Bianchi", "telefono": "+39 340 0000003",
               "email": "urgente@example.com",
               "messaggio": "Ho un dolore fortissimo e mi sanguina la gengiva"}
    mostra("POST /webhook/lead/" + BIANCHI, urgente)
    risp_u = C.post("/webhook/lead/%s" % BIANCHI, json=urgente).json()
    coda_b = C.get("/api/stato?cliente=%s" % BIANCHI).json()["coda"]
    coda_r = C.get("/api/stato?cliente=%s" % ROSSI).json()["coda"]
    print(u"\ncoda di Bianchi: %s" % [(v["nome"], v["priorita"]) for v in coda_b])
    print(u"coda di Rossi  : %s" % [(v["nome"], v["priorita"]) for v in coda_r])
    conn = db.connessione()
    try:
        presi = conn.execute("SELECT COUNT(*) n FROM disponibilita WHERE lead_id = ?",
                             (risp_u["lead_id"],)).fetchone()["n"]
    finally:
        conn.close()
    nella_sua = any(v["lead_id"] == risp_u["lead_id"] and v["priorita"] == 1
                    for v in coda_b)
    nell_altra = any(v["lead_id"] == risp_u["lead_id"] for v in coda_r)
    verifica("5 - emergenza nella coda giusta",
             risp_u["stato"] == "da_operatore" and nella_sua and not nell_altra
             and presi == 0,
             u"priorita 1 nella coda di Bianchi, assente da quella di Rossi, "
             u"nessuna prenotazione automatica")

    # -------------------------------------------------------------- extra --
    titolo("IN PIU' - un cliente mal configurato non ferma gli altri")
    print(u"Il cliente 'demo' non ha HUBSPOT_TOKEN impostato.")
    risp_d = C.post("/webhook/lead/demo", json={
        "nome": "Paziente Demo", "telefono": "+39 340 0000004",
        "email": "demo@example.com", "messaggio": "vorrei un controllo"}).json()
    print(u"il suo lead: stato=%s, CRM=%s" % (risp_d["stato"],
                                              (risp_d.get("crm") or {}).get("fonte")))
    ancora_r = C.post("/webhook/lead/%s" % ROSSI, json={
        "nome": "Dopo il guasto", "telefono": "+39 340 0000005",
        "email": "dopo@example.com", "messaggio": "vorrei una pulizia"}).json()
    verifica("extra - il guasto di uno non ferma gli altri",
             (risp_d.get("crm") or {}).get("fonte") == "sqlite"
             and (ancora_r.get("crm") or {}).get("fonte") == "hubspot",
             u"demo scrive in locale, Rossi continua su HubSpot")

    ignoto = C.post("/webhook/lead/studioinesistente", json={"nome": "X"})
    verifica("extra - cliente sconosciuto: 404 chiaro",
             ignoto.status_code == 404 and "clienti_configurati" in ignoto.json(),
             u"HTTP %s, e dice quali clienti esistono" % ignoto.status_code)

    # ---------------------------------------------------------- verdetto ---
    titolo("VERDETTO")
    for nome, ok, dettaglio in esiti:
        print(u"  [%s] %-40s %s" % ("PASS" if ok else "FAIL", nome, dettaglio[:70]))
    riga("-")
    tutto = all(ok for _, ok, _ in esiti)
    print(u"  %s" % (u"MULTI-CLIENTE REALE E ISOLATO." if tutto
                     else u"QUALCOSA NON PASSA: guarda i FAIL qui sopra."))
    riga()
    return 0 if tutto else 1


if __name__ == "__main__":
    try:
        codice = main()
    finally:
        SPEGNI()
    sys.exit(codice)
