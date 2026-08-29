# -*- coding: utf-8 -*-
"""I casi storti: quelli che in produzione capitano e fanno danno.

  python tests/scenari.py

Gira sempre contro i servizi finti: qui non si prova che Claude e' bravo, si
prova che il giro regge quando le cose vanno male.
"""
import io
import os
import sys
import tempfile

for _n in ("stdout", "stderr"):
    _f = getattr(sys, _n, None)
    if _f is not None and hasattr(_f, "buffer"):
        setattr(sys, _n, io.TextIOWrapper(_f.buffer, encoding="utf-8",
                                          errors="replace", line_buffering=True))

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from tests.finti_servizi import accendi                      # noqa: E402

INDIRIZZO, SPEGNI = accendi()
os.environ["ANTHROPIC_BASE_URL"] = INDIRIZZO
os.environ["ANTHROPIC_API_KEY"] = "chiave-di-prova"
os.environ["HUBSPOT_BASE"] = INDIRIZZO
os.environ["HUBSPOT_TOKEN"] = "TOKEN-DI-PROVA"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="scenari-"), "p.db")

from fastapi.testclient import TestClient   # noqa: E402
from app import clienti, db                 # noqa: E402
from app.main import app                    # noqa: E402

STUDIO = clienti.predefinito().slug          # i casi storti si provano su uno studio

C = TestClient(app)
esiti = []


def prova(nome, condizione, dettaglio=""):
    esiti.append((nome, bool(condizione)))
    print(u"  [%s] %-46s %s" % ("PASS" if condizione else "FAIL", nome, dettaglio))


print("\nCASI STORTI\n" + "=" * 78)

# 1. Conversazione a piu' turni: il secondo messaggio trova il lead dal telefono
r = C.post("/webhook/lead", json={"nome": "Anna Neri", "telefono": "+39 333 111",
                                  "email": "anna@example.com",
                                  "messaggio": "vorrei uno sbiancamento"}).json()
lead = r["lead_id"]
r2 = C.post("/webhook/message", json={"telefono": "+39 333 111",
                                      "testo": "di mattina va benissimo"}).json()
storico = db.storico(lead)
prova("secondo messaggio trovato dal telefono", r2.get("lead_id") == lead,
      u"lead %s" % r2.get("lead_id"))
prova("la conversazione si accumula", len(storico) >= 3,
      u"%d messaggi salvati" % len(storico))

# 2. Cliente che torna: stessa email -> HubSpot risponde 409, si riusa l'id
r3 = C.post("/webhook/lead", json={"nome": "Anna Neri", "telefono": "+39 333 111",
                                   "email": "anna@example.com",
                                   "messaggio": "un'altra informazione"}).json()
prova("cliente che torna: stesso contatto CRM",
      r3["crm"]["contact_id"] == r["crm"]["contact_id"],
      u"contatto %s riusato" % r3["crm"]["contact_id"])

# 3. HubSpot cade: il lead non si perde, finisce in casa da sincronizzare
import app.config as config                                   # noqa: E402
vero = config.HUBSPOT_BASE
config.HUBSPOT_BASE = "http://127.0.0.1:1"        # nessuno risponde qui
try:
    r4 = C.post("/webhook/lead", json={"nome": "Luca Blu", "telefono": "+39 333 222",
                                       "email": "luca@example.com",
                                       "messaggio": "vorrei una pulizia"}).json()
finally:
    config.HUBSPOT_BASE = vero
conn = db.connessione()
try:
    riga = conn.execute("SELECT sincronizzato, ultimo_errore, email FROM crm_records "
                        "WHERE email = ?", ("luca@example.com",)).fetchone()
finally:
    conn.close()
prova("HubSpot giu': il lead finisce in casa",
      r4["crm"]["fonte"] == "sqlite" and riga is not None,
      u"id locale %s" % r4["crm"]["contact_id"])
prova("segnato da sincronizzare", riga is not None and riga["sincronizzato"] == 0,
      u"motivo: %s" % (riga["ultimo_errore"][:44] if riga else "-"))

# 4. Un lead in mano all'operatore non torna in automatico
r5 = C.post("/webhook/lead", json={"nome": "Sara Gialli", "telefono": "+39 333 333",
                                   "messaggio": "ho un dolore fortissimo"}).json()
prova("emergenza -> operatore", r5["stato"] == "da_operatore")
r6 = C.post("/webhook/message", json={"lead_id": r5["lead_id"],
                                      "testo": "allora facciamo domani?"}).json()
prova("l'automazione non se lo riprende",
      r6["stato"] == "da_operatore" and r6["qualificazione"] is None,
      u"nessuna nuova chiamata al modello")

# 5. Alto valore senza sintomi: comunque a una persona
r7 = C.post("/webhook/lead", json={"nome": "Ugo Rosa", "telefono": "+39 333 444",
                                   "messaggio": "vorrei un preventivo per impianti"}).json()
prova("lavoro importante -> operatore", r7["stato"] == "da_operatore",
      u"trattamento=%s" % (r7["qualificazione"] or {}).get("tipo_trattamento"))

# 6. Un messaggio per un lead che non esiste non fa crollare niente
r8 = C.post("/webhook/message", json={"telefono": "+39 000 000", "testo": "ciao"}).json()
prova("telefono sconosciuto: errore chiaro", "errore" in r8, r8.get("errore", ""))

# 7. Senza chiave Anthropic si passa la mano, non si inventa una risposta
chiave = config.ANTHROPIC_API_KEY
config.ANTHROPIC_API_KEY = ""
try:
    r9 = C.post("/webhook/lead", json={"nome": "Tino Viola", "telefono": "+39 333 555",
                                       "messaggio": "vorrei un controllo"}).json()
finally:
    config.ANTHROPIC_API_KEY = chiave
prova("senza chiave: operatore, non invenzioni",
      r9["stato"] == "da_operatore" and r9["qualificazione"]["serve_umano"],
      u"motivo: %s" % (r9["qualificazione"].get("_motivo_ripiego") or "-"))

# 8. Due prenotazioni sullo stesso slot: la seconda non passa
from app.calendar.sqlite_cal import CalendarioSqlite         # noqa: E402
cal = CalendarioSqlite(STUDIO)
uno = db.crea_lead({"cliente": STUDIO, "canale": "console", "nome": "Slot Uno"})
due = db.crea_lead({"cliente": STUDIO, "canale": "console", "nome": "Slot Due"})
slot = cal.slot_libero()
if slot:
    a = cal.prenota(slot["slot_id"], uno)
    b = cal.prenota(slot["slot_id"], due)
    c = cal.prenota(slot["slot_id"], uno)     # lo stesso lead: e' gia' sua
    prova("uno slot, un paziente solo", a["ok"] and not b["ok"] and c["ok"],
          u"secondo tentativo: %s" % b.get("errore"))
    libero = cal.slot_libero()                     # uno slot davvero libero
    d = cal.prenota(libero["slot_id"], 999999)     # ma con un lead che non esiste
    prova("lead inesistente: errore, non crollo",
          not d["ok"] and "non posso prenotare" in (d["errore"] or ""),
          (d["errore"] or "")[:52])

print("-" * 78)
buoni = sum(1 for _, ok in esiti if ok)
print(u"  %d/%d passano" % (buoni, len(esiti)))
print("=" * 78)
SPEGNI()
sys.exit(0 if buoni == len(esiti) else 1)
