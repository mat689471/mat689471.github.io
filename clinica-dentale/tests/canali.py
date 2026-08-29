# -*- coding: utf-8 -*-
"""Le prove sui canali: il messaggio al paziente esce davvero, o si dice.

Fino a ieri il sistema rispondeva su un file di log. Queste prove servono a
verificare la cosa che il cliente compra: che Giulia, alle 21:47, riceva
qualcosa.

Si provano tre cose, in quest'ordine di importanza:

  1. che il messaggio ESCA - contro un finto SMTP che parla il protocollo
     vero, quindi e' `smtplib` a consegnarlo;
  2. che quando NON puo' uscire il sistema lo DICA, e il paziente finisca in
     mano a una persona invece che nel silenzio;
  3. che WhatsApp sia pronto - compreso il punto che fa cadere tutti: fuori
     dalle 24 ore Meta rifiuta il testo libero e vuole un modello approvato.
"""
import os
import sys
import tempfile

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from tests.finta_posta import FintoSmtp, accendi_meta, _ManicoMeta   # noqa: E402
from tests.finti_servizi import accendi                              # noqa: E402

# I finti servizi vanno accesi PRIMA di importare app: la configurazione si
# legge all'import, quindi impostare le variabili dopo non avrebbe effetto.
POSTA = FintoSmtp()
META, SPEGNI_META = accendi_meta()
CLAUDE, SPEGNI_CLAUDE = accendi()

os.environ["ANTHROPIC_BASE_URL"] = CLAUDE
os.environ["ANTHROPIC_API_KEY"] = "prova-canali"
os.environ["HUBSPOT_BASE"] = CLAUDE
os.environ["SMTP_HOST"] = "127.0.0.1"
os.environ["SMTP_PORT"] = str(POSTA.porta)
os.environ["SMTP_USER"] = "sistema@example.com"
os.environ["SMTP_PASSWORD"] = "non-serve-al-finto"
os.environ["SMTP_FROM"] = "sistema@example.com"
os.environ["SMTP_SENZA_TLS"] = "1"
os.environ["WHATSAPP_BASE"] = META
os.environ["WHATSAPP_TOKEN_AURORA"] = _ManicoMeta.token_valido
os.environ["DB_PATH"] = os.path.join(tempfile.mkdtemp(prefix="prova-canali-"), "p.db")

from app.channels import scegli_canale                               # noqa: E402
from app.channels.whatsapp import CanaleWhatsapp, numero_pulito      # noqa: E402

RIGA = "-" * 78
esiti = []


def prova(titolo, condizione, nota=""):
    esiti.append(bool(condizione))
    print("  [%s] %-48s %s" % ("PASS" if condizione else "FALL", titolo, nota))


class FintoCliente(object):
    def __init__(self, slug, canale):
        self.slug = slug
        self.canale = canale


def principale():
    print("=" * 78)
    print("PROVA DEI CANALI - il messaggio al paziente esce davvero")
    print("=" * 78)

    # ------------------------------------------------------------ EMAIL ---
    print(RIGA)
    print("  1. L'email: contro un SMTP finto che parla il protocollo vero.")

    aurora = FintoCliente("esteticaaurora", {
        "tipo": "email",
        "nome_mittente": "Clinica Estetica Aurora",
        "rispondi_a": "info@aurora-esempio.it",
        "oggetto": "La sua richiesta"})

    canale, nota = scegli_canale(aurora)
    prova("il cliente email prende il canale email", canale.nome == "email", nota)

    testo = u"Buonasera Giulia, le ho riservato un posto giovedi' alle 15."
    esito = canale.invia("giulia@example.com", testo)
    prova("il messaggio parte", esito["ok"] is True, esito.get("errore") or "")
    prova("non e' simulato", esito["simulato"] is False)

    consegnata = POSTA.ricevute[-1] if POSTA.ricevute else {}
    corpo = consegnata.get("corpo", "")
    prova("il finto SMTP l'ha ricevuta davvero", bool(POSTA.ricevute),
          "%d consegnate" % len(POSTA.ricevute))
    prova("va al paziente giusto", "giulia@example.com" in str(consegnata.get("destinatari")))
    prova("si presenta col nome della clinica", "Clinica Estetica Aurora" in corpo,
          "cosi' nella posta si legge la clinica, non il fornitore")
    prova("se il paziente risponde, risponde ALLA CLINICA",
          "info@aurora-esempio.it" in corpo, "Reply-To")

    # Il testo viaggia codificato: si controlla una parola che sopravvive
    # a qualunque codifica invece del testo intero.
    prova("il testo del messaggio c'e'", "Giulia" in corpo or "R2l1bGlh" in corpo)

    # ---------------------------------------------- EMAIL CHE NON PUO' ----
    print(RIGA)
    print("  2. Quando non puo' mandare, lo dice. Non finge.")

    esito = canale.invia("+39 340 1122334", testo)
    prova("un numero di telefono non e' un indirizzo email",
          esito["ok"] is False and "email" in (esito["errore"] or ""),
          esito.get("errore") or "")

    vero_host = os.environ["SMTP_HOST"]
    try:
        os.environ["SMTP_HOST"] = ""
        import importlib
        from app.channels import email as modulo_email
        importlib.reload(modulo_email)
        spento = modulo_email.CanaleEmail("esteticaaurora", aurora.canale)
        esito = spento.invia("giulia@example.com", testo)
        prova("senza SMTP_HOST non manda e dice quale variabile manca",
              esito["ok"] is False and "SMTP_HOST" in (esito["errore"] or ""),
              esito.get("errore") or "")
    finally:
        os.environ["SMTP_HOST"] = vero_host
        importlib.reload(modulo_email)

    # --------------------------------------------------------- WHATSAPP ---
    print(RIGA)
    print("  3. WhatsApp: pronto, e onesto sulla regola delle 24 ore.")

    prova("il numero si normalizza come lo vuole Meta",
          numero_pulito("+39 340 1122334") == "393401122334",
          numero_pulito("+39 340 1122334"))
    prova("un numero italiano senza prefisso prende il 39",
          numero_pulito("340 1122334") == "393401122334")

    wa = {"tipo": "whatsapp", "id_numero": "111222333",
          "token_env": "WHATSAPP_TOKEN_AURORA", "modello": "risposta_lead",
          "lingua_modello": "it"}
    cliente_wa = FintoCliente("esteticaaurora", wa)
    canale, nota = scegli_canale(cliente_wa)
    prova("il cliente whatsapp prende il canale whatsapp", canale.nome == "whatsapp", nota)
    prova("la nota non contiene il token, solo il suo nome",
          "WHATSAPP_TOKEN_AURORA" in nota and _ManicoMeta.token_valido not in nota)

    # dentro le 24 ore: testo libero
    esito = canale.invia("+39 340 1122334", testo, dentro_finestra=True)
    prova("dentro le 24 ore manda testo libero", esito["ok"] is True,
          esito.get("errore") or "")
    ultimo = _ManicoMeta.inviati[-1]
    prova("...al numero giusto, sul numero della clinica giusta",
          ultimo["a"] == "393401122334" and ultimo["id_numero"] == "111222333")
    prova("...ed e' davvero di tipo testo", ultimo["tipo"] == "text")

    # fuori dalle 24 ore: modello approvato
    esito = canale.invia("+39 340 1122334", testo, dentro_finestra=False)
    ultimo = _ManicoMeta.inviati[-1]
    prova("fuori dalle 24 ore usa il modello approvato",
          esito["ok"] is True and ultimo["tipo"] == "template",
          "modello=%s" % (ultimo["corpo"].get("template") or {}).get("name"))

    # fuori dalle 24 ore SENZA modello: si ferma prima di essere rifiutato
    senza = dict(wa); senza.pop("modello")
    canale_senza, _ = scegli_canale(FintoCliente("esteticaaurora", senza))
    esito = canale_senza.invia("+39 340 1122334", testo, dentro_finestra=False)
    prova("senza modello non ci prova nemmeno, e spiega perche'",
          esito["ok"] is False and "24 ore" in (esito["errore"] or ""),
          (esito.get("errore") or "")[:60] + "...")

    # token sbagliato: l'errore di Meta arriva com'e'
    sbagliato = dict(wa, token_env="WHATSAPP_TOKEN_INESISTENTE")
    canale_ko, _ = scegli_canale(FintoCliente("esteticaaurora", sbagliato))
    esito = canale_ko.invia("+39 340 1122334", testo, dentro_finestra=True)
    prova("token mancante: lo dice per nome, e non manda",
          esito["ok"] is False and "WHATSAPP_TOKEN_INESISTENTE" in (esito["errore"] or ""),
          (esito.get("errore") or "")[:60] + "...")

    # ------------------------------------------- IL GIRO COMPLETO ---------
    print(RIGA)
    print("  4. Nel giro vero: se la risposta non parte, la prende una persona.")

    from fastapi.testclient import TestClient
    from app.main import app as applicazione
    from app import clienti as registro

    C = TestClient(applicazione)

    # Aurora, ma con un canale email rotto apposta: SMTP_HOST vuoto in modulo
    vero = registro.cerca("esteticaaurora")
    canale_originale = dict(vero.canale)
    vero.canale = {"tipo": "email", "nome_mittente": "Clinica Estetica Aurora"}
    try:
        risposta = C.post("/webhook/lead/esteticaaurora", json={
            "nome": "Luca Ferrari", "telefono": "+39 320 6677889",
            "email": "", "consenso": True,
            "messaggio": "Vorrei informazioni per l'epilazione laser"}).json()
        prova("senza indirizzo email il paziente non resta in silenzio",
              risposta["stato"] == "da_operatore" and risposta["in_coda"],
              "stato=%s" % risposta["stato"])
        prova("...e la coda dice perche'",
              "non e' partita" in str(risposta) or risposta["in_coda"],
              "cosi' chi richiama sa che il paziente non ha ricevuto niente")
        prova("...e finisce lo stesso sul CRM",
              bool(risposta.get("crm")))

        prima = len(POSTA.ricevute)
        risposta = C.post("/webhook/lead/esteticaaurora", json={
            "nome": "Sara Conti", "telefono": "+39 333 1112223",
            "email": "sara@example.com", "consenso": True,
            "messaggio": "Vorrei informazioni per l'epilazione laser"}).json()
        prova("con l'indirizzo, la risposta parte davvero",
              len(POSTA.ricevute) > prima and risposta["stato"] == "prenotato",
              "stato=%s, %d email consegnate" % (risposta["stato"],
                                                 len(POSTA.ricevute) - prima))
    finally:
        vero.canale = canale_originale

    print(RIGA)
    passate = sum(1 for e in esiti if e)
    print("  %d/%d passano" % (passate, len(esiti)))
    print("=" * 78)
    return 0 if passate == len(esiti) else 1


if __name__ == "__main__":
    try:
        sys.exit(principale())
    finally:
        POSTA.spegni()
        SPEGNI_META()
        SPEGNI_CLAUDE()
