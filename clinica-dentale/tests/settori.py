# -*- coding: utf-8 -*-
"""Le prove sui settori: lo stesso motore, due mestieri, regole diverse.

Queste prove servono a rispondere a una domanda che un cliente fara' davvero:
«e se il vostro sistema decide da solo di prenotarmi una rinoplastica?».

La risposta e' che non puo', e non perche' il modello e' bravo: perche' dopo
il modello c'e' del codice che rilegge la risposta e la corregge. Qui si
verifica proprio quello - si passa apposta all'agente una qualificazione
SBAGLIATA, come se il modello avesse toppato, e si controlla che il codice la
raddrizzi comunque.

Le ultime due prove guardano il contrario: che aver aggiunto un mestiere non
abbia cambiato il comportamento del dentale, che e' quello gia' in mano ai
clienti.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.finti_servizi import accendi          # noqa: E402

INDIRIZZO, SPEGNI = accendi()
os.environ["ANTHROPIC_BASE_URL"] = INDIRIZZO
os.environ["ANTHROPIC_API_KEY"] = "prova-settori"
os.environ["HUBSPOT_BASE"] = INDIRIZZO
os.environ["HUBSPOT_TOKEN_ESTETICAAURORA"] = "TOKEN-AURORA"
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="prova-settori-"), "p.db")

from app import agent, clienti, settori          # noqa: E402

RIGA = "-" * 78
esiti = []


def prova(titolo, condizione, nota=""):
    esiti.append(bool(condizione))
    print("  [%s] %-46s %s" % ("PASS" if condizione else "FALL", titolo, nota))


def _modello_dice(trattamento, urgenza="bassa", serve_umano=False):
    """Una risposta come la darebbe il modello. Volutamente permissiva."""
    return {"qualificato": True, "tipo_trattamento": trattamento,
            "urgenza": urgenza, "slot_proposto": "mattina",
            "serve_umano": serve_umano, "risposta_bozza": u"Le fisso io un posto."}


def principale():
    print("=" * 78)
    print("PROVA DEI SETTORI - il mestiere cambia dove il sistema si ferma")
    print("=" * 78)

    aurora = clienti.cerca("esteticaaurora")
    rossi = clienti.cerca("studiorossi")

    prova("il cliente estetico esiste ed e' del suo settore",
          aurora is not None and aurora.settore == "estetica",
          "settore=%s" % (aurora.settore if aurora else "assente"))

    # --- 1. le regole dell'estetica, applicate CONTRO il modello -----------
    print(RIGA)
    print("  Il modello sbaglia apposta: dice «prenotalo pure». Il codice corregge.")

    for trattamento in ("rinoplastica", "mastoplastica additiva", "liposuzione",
                        "blefaroplastica", "lifting del viso"):
        fuori = agent._sistema(_modello_dice(trattamento), aurora)
        prova(u"chirurgia: %s passa a una persona" % trattamento,
              fuori["serve_umano"] is True)

    for trattamento in ("filler labbra", "tossina botulinica", "biorivitalizzazione",
                        "fili di trazione"):
        fuori = agent._sistema(_modello_dice(trattamento), aurora)
        prova(u"iniettivo: %s passa a una persona" % trattamento,
              fuori["serve_umano"] is True)

    fuori = agent._sistema(_modello_dice("complicanza", urgenza="emergenza"), aurora)
    prova("un problema dopo il trattamento e' emergenza e passa a una persona",
          fuori["serve_umano"] is True and fuori["urgenza"] == "emergenza")

    # --- 2. cio' che NON e' invasivo si prenota da solo --------------------
    print(RIGA)
    for trattamento in ("epilazione laser", "pressoterapia", "peeling",
                        "consulenza estetica"):
        fuori = agent._sistema(_modello_dice(trattamento), aurora)
        prova(u"non invasivo: %s si prenota da solo" % trattamento,
              fuori["serve_umano"] is False)

    # --- 3. i due mestieri non si contaminano ------------------------------
    print(RIGA)
    fuori = agent._sistema(_modello_dice("filler labbra"), rossi)
    prova("un filler chiesto a uno STUDIO DENTISTICO non e' bloccato dal dentale",
          fuori["serve_umano"] is False,
          "giusto cosi': non e' il suo mestiere, e il dentista non lo offre")

    fuori = agent._sistema(_modello_dice("impianto singolo"), rossi)
    prova("il dentale ferma ancora gli impianti, come prima",
          fuori["serve_umano"] is True)

    fuori = agent._sistema(_modello_dice("igiene"), rossi)
    prova("il dentale prenota ancora l'igiene da solo, come prima",
          fuori["serve_umano"] is False)

    # --- 4. il prompt e' davvero quello del mestiere -----------------------
    print(RIGA)
    testo_aurora = agent.istruzioni_per(aurora)
    testo_rossi = agent.istruzioni_per(rossi)
    prova("il prompt della clinica estetica parla di estetica",
          "estetica" in testo_aurora and "dentistico" not in testo_aurora)
    prova("il prompt dello studio dentistico e' rimasto dentale",
          "dentistico" in testo_rossi and "rinoplastica" not in testo_rossi)
    prova("alla clinica estetica e' vietato promettere un risultato",
          "Promettere un risultato" in testo_aurora)
    prova("i trattamenti nel prompt sono i SUOI",
          "rinoplastica" in testo_aurora and "otturazione" not in testo_aurora)

    # --- 5. un mestiere inventato non parte, non ripiega -------------------
    print(RIGA)
    try:
        settori.per_chiave("veterinario")
        ok, nota = False, "ha accettato un settore che non esiste"
    except settori.SettoreSconosciuto as e:
        ok, nota = True, "dice quali esistono"
    prova("un settore sconosciuto si ferma subito", ok, nota)

    try:
        clienti.ConfigCliente({"slug": "x", "settore": "veterinario"})
        ok = False
    except settori.SettoreSconosciuto:
        ok = True
    prova("un cliente con un settore sbagliato non si carica", ok,
          "meglio non partire che partire col mestiere sbagliato")

    # --- 6. anche chi passa a una persona finisce nel CRM ------------------
    print(RIGA)
    print("  Il contatto che vale di piu' e' quello che passa a una persona.")
    import json as _json
    from fastapi.testclient import TestClient

    if True:
        from app.main import app as applicazione
        C = TestClient(applicazione)
        richiesta = {"nome": "Martina Greco", "telefono": "+39 346 1122556",
                     "email": "martina@example.com", "consenso": True,
                     "messaggio": "Vorrei un preventivo per una rinoplastica"}
        risposta = C.post("/webhook/lead/esteticaaurora", json=richiesta).json()
        prova("una rinoplastica passa a una persona",
              risposta["stato"] == "da_operatore" and risposta["in_coda"],
              "stato=%s" % risposta["stato"])
        prova("...e finisce lo stesso sul CRM del suo cliente",
              bool(risposta.get("crm")) and risposta["crm"].get("contact_id"),
              "crm=%s" % _json.dumps(risposta.get("crm"), ensure_ascii=False))
        prova("il CRM usato e' quello di QUEL cliente",
              (risposta.get("crm") or {}).get("fonte") == "hubspot",
              "fonte=%s" % (risposta.get("crm") or {}).get("fonte"))

    # --- 7. la vetrina ha i testi di tutti e due ---------------------------
    print(RIGA)
    import re
    with open(os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))),
                           "app", "web", "vetrina.html"), encoding="utf-8") as f:
        pagina = f.read()
    usati = set(re.findall(r"\{\{([a-z0-9_]+)\}\}", pagina))
    for s in settori.SETTORI.values():
        mancanti = usati - set(s.vetrina)
        prova(u"la vetrina «%s» non lascia buchi" % s.chiave, not mancanti,
              ("mancano: %s" % sorted(mancanti)) if mancanti else "")

    print(RIGA)
    passate = sum(1 for e in esiti if e)
    print("  %d/%d passano" % (passate, len(esiti)))
    print("=" * 78)
    return 0 if passate == len(esiti) else 1


if __name__ == "__main__":
    sys.exit(principale())
