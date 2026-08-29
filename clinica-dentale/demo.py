# -*- coding: utf-8 -*-
"""La vetrina: il cruscotto acceso, senza chiavi e senza spendere niente.

  python demo.py

Accende i finti Claude e HubSpot (stesso protocollo dei veri), mette dentro
qualche paziente d'esempio e apre il cruscotto nel browser. Serve a far vedere
il sistema a un cliente senza consumare un centesimo.
"""
import os
import sys
import tempfile
import threading
import webbrowser

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from tests.finti_servizi import accendi                     # noqa: E402

INDIRIZZO, _ = accendi()
os.environ["ANTHROPIC_BASE_URL"] = INDIRIZZO
os.environ["ANTHROPIC_API_KEY"] = "chiave-di-prova"
os.environ["HUBSPOT_BASE"] = INDIRIZZO
# Un token finto per ogni studio: nella vetrina si vede che sono separati.
os.environ["HUBSPOT_TOKEN"] = "TOKEN-DEMO"
os.environ["HUBSPOT_TOKEN_STUDIOROSSI"] = "TOKEN-ROSSI"
os.environ["HUBSPOT_TOKEN_STUDIOBIANCHI"] = "TOKEN-BIANCHI"
os.environ.setdefault("DB_PATH", os.path.join(tempfile.mkdtemp(prefix="demo-"), "demo.db"))

from app import clienti, db                                 # noqa: E402
from app.main import app, _giro                             # noqa: E402

# Pazienti d'esempio, divisi fra gli studi: cosi' la vetrina mostra anche il
# filtro per cliente, che e' meta' del valore di un sistema multi-cliente.
ESEMPI = [
    ("studiorossi", "Giulia Bianchi", "+39 340 1122334", "giulia@example.com",
     "Sbiancamento Estate",
     "Buongiorno, vorrei informazioni per uno sbiancamento, preferirei di mattina"),
    ("studiorossi", "Marco Verdi", "+39 349 9988776", "marco@example.com", "Impianti",
     "Ho un dolore fortissimo a un dente e sanguina, e' un'emergenza"),
    ("studiorossi", "Paolo Ricci", "+39 331 2233445", "paolo@example.com",
     "Igiene Settembre",
     "Vorrei prenotare una pulizia dei denti, di pomeriggio se possibile"),
    ("studiobianchi", "Sara Conti", "+39 347 5566778", "sara@example.com", "Ortodonzia",
     "Vorrei un preventivo per un apparecchio ortodontico"),
    ("studiobianchi", "Elena Costa", "+39 333 4455667", "elena@example.com",
     "Estetica",
     "Vorrei informazioni per l'estetica dentale, di pomeriggio"),
]


def semina():
    for slug, nome, tel, mail, campagna, messaggio in ESEMPI:
        cliente = clienti.cerca(slug)
        if not cliente:
            continue
        lead_id = db.crea_lead({"cliente": slug, "nome": nome, "telefono": tel,
                                "email": mail, "canale": "console", "canale_id": tel,
                                "campagna": campagna, "stato": "nuovo", "consenso": 1})
        db.aggiungi_messaggio(lead_id, "user", messaggio)
        _giro(cliente, lead_id)


if __name__ == "__main__":
    db.prepara()
    semina()
    print("")
    print("=" * 58)
    print("  VETRINA - cruscotto acceso, nessuna spesa")
    print("  Apri:  http://127.0.0.1:8000")
    print("  Per fermare: chiudi questa finestra")
    print("=" * 58)
    print("")
    threading.Timer(1.5, lambda: webbrowser.open("http://127.0.0.1:8000")).start()
    import uvicorn
    import os as _o
    uvicorn.run(app, host="127.0.0.1", port=int(_o.environ.get("PORTA", "8000")), log_level="warning")
