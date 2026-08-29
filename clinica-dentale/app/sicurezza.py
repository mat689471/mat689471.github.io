# -*- coding: utf-8 -*-
"""Chi puo' entrare. Senza questo, chiunque trovi l'indirizzo legge i pazienti.

Il cruscotto mostra nome, telefono, email e quello che il paziente ha scritto
del suo problema ai denti: sono dati di salute. Su un indirizzo pubblico senza
password sono in mano al primo che passa.

DUE CHIAVI, SEPARATE APPOSTA:

  CONSOLE_TOKEN  chi puo' VEDERE (cruscotto e sue API). E' tua e dello studio.
  WEBHOOK_TOKEN  chi puo' SCRIVERE (i moduli e le campagne del cliente).

Sono separate perche' il token del webhook lo dai a chi monta il modulo sul
sito: quel token deve poter creare pazienti, non leggerli tutti.

Se una chiave non e' impostata, quella porta resta APERTA e il sistema lo dice
forte all'avvio e in cima al cruscotto. Aperta di default perche' la vetrina
deve funzionare con un doppio clic, senza configurare niente: ma online, senza
token, non ci si va.
"""
import hmac
import os

from fastapi.responses import HTMLResponse, JSONResponse

# Le porte che chiunque deve poter chiamare senza chiave.
LIBERE = ("/health", "/vetrina", "/api/vetrina")

BIGLIETTO = "clinica_token"      # il cookie che tiene il login nel browser


def _leggi(nome):
    return (os.environ.get(nome) or "").strip()


def token_console():
    return _leggi("CONSOLE_TOKEN")


def token_webhook():
    return _leggi("WEBHOOK_TOKEN")


def _uguali(dato, atteso):
    """Confronto a tempo costante: evita di far indovinare il token a tentativi."""
    return bool(dato) and hmac.compare_digest(str(dato), str(atteso))


def _presentato(request):
    """Il token che l'utente porta, da dove che sia: intestazione, indirizzo o cookie."""
    return (request.headers.get("x-token")
            or request.query_params.get("token")
            or request.cookies.get(BIGLIETTO)
            or "")


def _serve_html(percorso):
    return percorso == "/" or percorso.startswith("/vetrina")


def controlla(request):
    """None se puo' passare, altrimenti la risposta di rifiuto."""
    percorso = request.url.path
    if percorso in LIBERE or percorso.startswith("/api/vetrina"):
        return None

    scrive = percorso.startswith("/webhook/")
    atteso = token_webhook() if scrive else token_console()
    if not atteso:
        return None                      # porta aperta: lo diciamo altrove

    if _uguali(_presentato(request), atteso):
        return None

    if _serve_html(percorso):
        return HTMLResponse(status_code=401, content=PAGINA_CHIAVE)
    return JSONResponse(status_code=401, content={
        "errore": "serve un token",
        "come": ("aggiungi l'intestazione X-Token, oppure ?token=... "
                 "in fondo all'indirizzo")})


def cliente_bloccato():
    """Se impostata, questo cruscotto vede UN SOLO studio e nient'altro.

    Serve quando il cruscotto lo dai al cliente invece di tenerlo tu: metti
    CONSOLE_CLIENTE=studiorossi e quell'installazione non puo' piu' vedere gli
    altri studi, nemmeno cambiando l'indirizzo a mano. Senza questa variabile
    il cruscotto e' quello del gestore e li vede tutti.
    """
    return _leggi("CONSOLE_CLIENTE").lower()


def filtra(chiesto):
    """Lo studio da usare davvero: quello bloccato vince sempre su quello chiesto."""
    fisso = cliente_bloccato()
    return fisso or chiesto


def stato():
    """Per /health e per la fascia di avviso: mai il valore, solo se c'e'."""
    return {"console_protetta": bool(token_console()),
            "webhook_protetto": bool(token_webhook()),
            "console_bloccata_su": cliente_bloccato() or None}


def avviso():
    """La frase da mettere nel diario all'avvio. Vuota se e' tutto chiuso a chiave."""
    aperte = []
    if not token_console():
        aperte.append("CONSOLE_TOKEN")
    if not token_webhook():
        aperte.append("WEBHOOK_TOKEN")
    if not aperte:
        return ""
    return (u"ATTENZIONE: %s non impostat%s. Chiunque conosca l'indirizzo puo' "
            u"%s. Va bene in locale per la vetrina, NON online con pazienti veri."
            % (" e ".join(aperte), "e" if len(aperte) > 1 else "a",
               "entrare" if len(aperte) > 1 else
               ("leggere i pazienti" if "CONSOLE_TOKEN" in aperte
                else "creare pazienti finti e consumare le tue chiamate")))


PAGINA_CHIAVE = """<!doctype html><html lang="it"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Serve la chiave</title><style>
body{margin:0;min-height:100vh;display:grid;place-items:center;background:#0d1b2a;
     color:#e8eef5;font:16px/1.6 -apple-system,"Segoe UI",Roboto,system-ui,sans-serif}
.c{max-width:420px;padding:34px;background:#14263a;border:1px solid #24405e;
   border-radius:16px;text-align:center}
h1{font-size:20px;margin:0 0 10px} p{color:#9fb3c8;font-size:14px;margin:0 0 18px}
input{width:100%;padding:11px 13px;border-radius:9px;border:1px solid #24405e;
      background:#0d1b2a;color:#e8eef5;font:inherit;font-size:15px;margin-bottom:12px}
button{width:100%;padding:11px;border:0;border-radius:9px;background:#2f9e8f;
       color:#fff;font:inherit;font-weight:650;font-size:15px;cursor:pointer}
</style></head><body><div class="c">
<h1>Serve la chiave</h1>
<p>Questo cruscotto contiene dati di pazienti. Inserisci il token per entrare.</p>
<input id="t" type="password" placeholder="token" autofocus>
<button onclick="v()">Entra</button>
</div><script>
function v(){var t=document.getElementById('t').value.trim();if(!t)return;
document.cookie='clinica_token='+encodeURIComponent(t)+';path=/;max-age=2592000;SameSite=Lax';
location.href=location.pathname;}
document.getElementById('t').addEventListener('keydown',function(e){if(e.key==='Enter')v();});
</script></body></html>"""
