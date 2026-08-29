# -*- coding: utf-8 -*-
"""Un finto server SMTP e un finto Meta, per provare che il messaggio esce.

Come per il finto Claude e il finto HubSpot: non sono simulazioni di comodo.
Il finto SMTP parla davvero il protocollo, quindi e' `smtplib` vero a mandare
il messaggio; il finto Meta risponde con la stessa forma della Cloud API. Se
il codice regge contro questi, regge contro quelli veri.
"""
import json
import socket
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer


# ---------------------------------------------------------------------------
# Finto SMTP: quel tanto di protocollo che serve a farsi consegnare una mail
# ---------------------------------------------------------------------------
class FintoSmtp(object):
    """Accetta la posta e la tiene da parte. Niente TLS, niente login."""

    def __init__(self):
        self.ricevute = []
        self._presa = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
        self._presa.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        self._presa.bind(("127.0.0.1", 0))
        self._presa.listen(5)
        self.porta = self._presa.getsockname()[1]
        self._acceso = True
        threading.Thread(target=self._servi, daemon=True).start()

    def _servi(self):
        while self._acceso:
            try:
                conn, _ = self._presa.accept()
            except OSError:
                return
            threading.Thread(target=self._parla, args=(conn,), daemon=True).start()

    def _parla(self, conn):
        f = conn.makefile("rwb")

        def dico(riga):
            f.write((riga + "\r\n").encode())
            f.flush()

        dico("220 finto.locale SMTP di prova")
        mittente = destinatari = None
        try:
            while True:
                riga = f.readline()
                if not riga:
                    return
                comando = riga.decode("utf-8", "replace").strip()
                alto = comando.upper()

                if alto.startswith(("HELO", "EHLO")):
                    dico("250-finto.locale")
                    dico("250 SIZE 10240000")
                elif alto.startswith("MAIL FROM"):
                    mittente = comando[10:].strip()
                    dico("250 OK")
                elif alto.startswith("RCPT TO"):
                    destinatari = (destinatari or []) + [comando[8:].strip()]
                    dico("250 OK")
                elif alto == "DATA":
                    dico("354 manda pure, chiudi con un punto")
                    righe = []
                    while True:
                        r = f.readline()
                        if not r or r.strip() == b".":
                            break
                        righe.append(r.decode("utf-8", "replace"))
                    self.ricevute.append({
                        "mittente": mittente, "destinatari": destinatari,
                        "corpo": "".join(righe)})
                    dico("250 OK: presa in carico")
                elif alto == "QUIT":
                    dico("221 arrivederci")
                    return
                elif alto == "RSET":
                    mittente = destinatari = None
                    dico("250 OK")
                else:
                    dico("250 OK")
        except Exception:
            return
        finally:
            try:
                f.close()
                conn.close()
            except Exception:
                pass

    def spegni(self):
        self._acceso = False
        try:
            self._presa.close()
        except OSError:
            pass


# ---------------------------------------------------------------------------
# Finto Meta: la Cloud API di WhatsApp, con i suoi errori
# ---------------------------------------------------------------------------
class _ManicoMeta(BaseHTTPRequestHandler):
    inviati = []
    token_valido = "TOKEN-WHATSAPP"

    def log_message(self, *a):
        pass

    def _rispondi(self, stato, corpo):
        dati = json.dumps(corpo).encode("utf-8")
        self.send_response(stato)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(dati)))
        self.end_headers()
        self.wfile.write(dati)

    def do_POST(self):
        lunghezza = int(self.headers.get("Content-Length") or 0)
        corpo = json.loads(self.rfile.read(lunghezza) or b"{}")

        intestazione = self.headers.get("Authorization") or ""
        token = intestazione[7:].strip() if intestazione.startswith("Bearer ") else ""
        if token != self.token_valido:
            return self._rispondi(401, {"error": {
                "message": "Invalid OAuth access token", "type": "OAuthException"}})

        if not self.path.endswith("/messages"):
            return self._rispondi(404, {"error": {"message": "non previsto: " + self.path}})

        # La regola vera di Meta: fuori dalle 24 ore passa solo un modello.
        # Il finto la applica, altrimenti la prova non proverebbe niente.
        if corpo.get("type") == "text" and self.headers.get("X-Prova-Fuori-Finestra"):
            return self._rispondi(400, {"error": {
                "message": "Message failed to send because more than 24 hours have "
                           "passed since the customer last replied to this number",
                "code": 131047}})

        self.inviati.append({"a": corpo.get("to"), "tipo": corpo.get("type"),
                             "corpo": corpo, "id_numero": self.path.split("/")[-2]})
        return self._rispondi(200, {
            "messaging_product": "whatsapp",
            "contacts": [{"input": corpo.get("to"), "wa_id": corpo.get("to")}],
            "messages": [{"id": "wamid.FINTO%d" % len(self.inviati)}]})


def accendi_meta():
    """Avvia il finto Meta su una porta libera. Ritorna (indirizzo, spegni)."""
    _ManicoMeta.inviati = []
    server = HTTPServer(("127.0.0.1", 0), _ManicoMeta)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return "http://127.0.0.1:%d" % server.server_port, server.shutdown
