# -*- coding: utf-8 -*-
"""Le prove sulle cose che, se sbagliate, costano un cliente o una multa.

  python tests/sicurezza.py

Cinque punti:
  1. senza token il cruscotto e' chiuso (401), con token si entra
  2. il webhook ha una chiave sua: chi scrive non puo' leggere
  3. la SCHEDA di un paziente non si legge da un altro studio
     (era il buco: gli elenchi filtravano, la singola scheda no)
  4. CONSOLE_CLIENTE blocca l'installazione su UN solo studio
  5. la cancellazione dati cancella davvero e libera il posto in agenda

Tutto contro servizi finti: non costa niente.
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
os.environ["HUBSPOT_TOKEN_STUDIOROSSI"] = "TOKEN-ROSSI"
os.environ["HUBSPOT_TOKEN_STUDIOBIANCHI"] = "TOKEN-BIANCHI"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="sicurezza-"), "prova.db")

# Le chiavi ci sono PRIMA che l'app parta: il controllo le legge all'arrivo
# di ogni richiesta, ma cosi' la prova somiglia a come gira davvero.
os.environ["CONSOLE_TOKEN"] = "chiave-del-cruscotto"
os.environ["WEBHOOK_TOKEN"] = "chiave-del-modulo"
os.environ.pop("CONSOLE_CLIENTE", None)

from fastapi.testclient import TestClient                    # noqa: E402
from app import db, sicurezza                                # noqa: E402
from app.main import app                                     # noqa: E402

C = TestClient(app)
ROSSI, BIANCHI = "studiorossi", "studiobianchi"
CONSOLE = {"X-Token": "chiave-del-cruscotto"}
MODULO = {"X-Token": "chiave-del-modulo"}
esiti = []


def riga(c="="):
    print(c * 78)


def titolo(t):
    print()
    riga()
    print(t)
    riga()


def verdetto(nome, ok, nota=""):
    esiti.append((nome, ok, nota))
    print(u"\n   -> %s  %s\n" % ("PASS" if ok else "FAIL", nota))


def entra(slug, nome, messaggio, telefono):
    r = C.post("/webhook/lead/" + slug, headers=MODULO, json={
        "nome": nome, "telefono": telefono, "email": "%s@example.com" % nome.split()[0].lower(),
        "messaggio": messaggio, "consenso": True})
    return r.json()


# --- 1 -----------------------------------------------------------------------
titolo("1 - il cruscotto senza chiave non si apre")
senza = C.get("/api/stato")
con = C.get("/api/stato", headers=CONSOLE)
salute = C.get("/health")
print("   senza token : HTTP %s" % senza.status_code)
print("   con token   : HTTP %s" % con.status_code)
print("   /health     : HTTP %s  (deve restare libero, serve al provider)" % salute.status_code)
verdetto("1 - cruscotto chiuso a chiave",
         senza.status_code == 401 and con.status_code == 200 and salute.status_code == 200,
         "401 senza token, 200 con token, /health sempre aperto")

# --- 2 -----------------------------------------------------------------------
titolo("2 - chi scrive non puo' leggere")
scrive_con_sua = C.post("/webhook/lead/" + ROSSI, headers=MODULO,
                        json={"nome": "Prova Chiave", "telefono": "+39 340 0000001",
                              "messaggio": "vorrei una pulizia", "consenso": True})
legge_con_quella_del_modulo = C.get("/api/stato", headers=MODULO)
scrive_senza = C.post("/webhook/lead/" + ROSSI, json={"nome": "X", "messaggio": "ciao"})
print("   webhook con la sua chiave      : HTTP %s" % scrive_con_sua.status_code)
print("   cruscotto con chiave del modulo: HTTP %s  (deve essere 401)"
      % legge_con_quella_del_modulo.status_code)
print("   webhook senza chiave           : HTTP %s  (deve essere 401)" % scrive_senza.status_code)
verdetto("2 - due chiavi separate",
         scrive_con_sua.status_code == 200
         and legge_con_quella_del_modulo.status_code == 401
         and scrive_senza.status_code == 401,
         "il token del modulo scrive ma non legge i pazienti")

# --- 3 -----------------------------------------------------------------------
titolo("3 - la scheda di un paziente non si legge da un altro studio")
di_rossi = entra(ROSSI, "Giulia Bianchi", "vorrei uno sbiancamento", "+39 340 1111111")
id_rossi = di_rossi["lead_id"]
giusto = C.get("/api/paziente/%d?cliente=%s" % (id_rossi, ROSSI), headers=CONSOLE)
rubato = C.get("/api/paziente/%d?cliente=%s" % (id_rossi, BIANCHI), headers=CONSOLE)
print("   paziente %d di %s" % (id_rossi, ROSSI))
print("   letto come %-14s: HTTP %s" % (ROSSI, giusto.status_code))
print("   letto come %-14s: HTTP %s  (deve essere 404)" % (BIANCHI, rubato.status_code))
verdetto("3 - scheda isolata",
         giusto.status_code == 200 and rubato.status_code == 404,
         "il paziente di Rossi non si apre spacciandosi per Bianchi")

# --- 4 -----------------------------------------------------------------------
titolo("4 - un cruscotto bloccato su un solo studio")
di_bianchi = entra(BIANCHI, "Sara Conti", "vorrei una pulizia", "+39 347 2222222")
id_bianchi = di_bianchi["lead_id"]
os.environ["CONSOLE_CLIENTE"] = ROSSI          # da qui in poi: solo Rossi
stato_bloccato = C.get("/api/stato", headers=CONSOLE).json()
altrui = C.get("/api/paziente/%d" % id_bianchi, headers=CONSOLE)
forzato = C.get("/api/stato?cliente=%s" % BIANCHI, headers=CONSOLE).json()
studi_visti = [c["slug"] for c in stato_bloccato.get("clienti", [])]
pazienti_visti = {p["cliente"] for p in stato_bloccato.get("pazienti", [])}
print("   CONSOLE_CLIENTE = %s" % ROSSI)
print("   studi visibili        : %s" % studi_visti)
print("   studi dei pazienti    : %s" % sorted(pazienti_visti))
print("   forzando ?cliente=%s : filtro applicato = %s"
      % (BIANCHI, forzato.get("filtro")))
print("   scheda di un paziente di Bianchi: HTTP %s  (deve essere 404)" % altrui.status_code)
verdetto("4 - blocco su un solo studio",
         studi_visti == [ROSSI] and pazienti_visti <= {ROSSI}
         and forzato.get("filtro") == ROSSI and altrui.status_code == 404,
         "vede solo il suo studio, e cambiare l'indirizzo a mano non serve")
os.environ.pop("CONSOLE_CLIENTE", None)

# --- 5 -----------------------------------------------------------------------
titolo("5 - cancellazione dati: sparisce davvero")
prima = db.leggi_lead(id_rossi)
storico_prima = len(db.storico(id_rossi))
posti_prima = db.numeri(ROSSI)["slot_liberi"]
risposta = C.request("DELETE", "/api/paziente/%d?cliente=%s" % (id_rossi, ROSSI),
                     headers=CONSOLE)
dopo = db.leggi_lead(id_rossi)
storico_dopo = len(db.storico(id_rossi))
posti_dopo = db.numeri(ROSSI)["slot_liberi"]
print("   prima : paziente=%s  messaggi=%d  posti liberi=%d"
      % (bool(prima), storico_prima, posti_prima))
print("   dopo  : paziente=%s  messaggi=%d  posti liberi=%d"
      % (bool(dopo), storico_dopo, posti_dopo))
print("   risposta: %s" % risposta.json())
verdetto("5 - cancellazione vera",
         risposta.status_code == 200 and dopo is None and storico_dopo == 0
         and posti_dopo >= posti_prima,
         "paziente e messaggi spariti, il posto in agenda e' tornato libero")

# --- verdetto ----------------------------------------------------------------
titolo("VERDETTO")
for nome, ok, nota in esiti:
    print(u"  [%s] %-34s %s" % ("PASS" if ok else "FAIL", nome, nota[:40]))
riga("-")
tutti = all(ok for _, ok, _ in esiti)
print("  I DATI DEI PAZIENTI SONO CHIUSI A CHIAVE." if tutti
      else "  QUALCOSA NON VA: NON METTERLO ONLINE COSI'.")
riga()
try:
    SPEGNI()
except Exception:
    pass
sys.exit(0 if tutti else 1)
