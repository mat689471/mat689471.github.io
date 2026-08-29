# -*- coding: utf-8 -*-
"""Un diario leggibile, una riga per passo, sempre col numero del lead.

Serve a far vedere a un cliente cosa e' successo dall'ingresso del lead fino
alla riga scritta sul CRM. Nessun segreto ci passa mai attraverso.
"""
import io
import logging
import os
import sys
from datetime import datetime, timezone

from app import config

_CARTELLA = os.path.join(config.RADICE, "dati")
_FILE = os.path.join(_CARTELLA, "diario.log")
_pronto = False


def _utf8():
    """La console Windows e' cp1252 e va in errore su accenti ed emoji.

    Claude scrive in italiano e a volte mette un'emoji nella risposta al
    paziente: senza questo, il programma muore mentre stampa. Non e' un
    dettaglio estetico, e' quello che faceva fallire il test.
    """
    for nome in ("stdout", "stderr"):
        flusso = getattr(sys, nome, None)
        if flusso is None or not hasattr(flusso, "buffer"):
            continue
        if (getattr(flusso, "encoding", "") or "").lower().replace("-", "") != "utf8":
            setattr(sys, nome, io.TextIOWrapper(flusso.buffer, encoding="utf-8",
                                                errors="replace", line_buffering=True))


def prepara(livello="INFO"):
    global _pronto
    if _pronto:
        return logging.getLogger("clinica")
    _utf8()
    os.makedirs(_CARTELLA, exist_ok=True)
    log = logging.getLogger("clinica")
    log.setLevel(getattr(logging, livello.upper(), logging.INFO))
    log.propagate = False
    if not log.handlers:
        forma = logging.Formatter("%(message)s")
        a_video = logging.StreamHandler(sys.stdout)
        a_video.setFormatter(forma)
        log.addHandler(a_video)
        su_file = logging.FileHandler(_FILE, encoding="utf-8")
        su_file.setFormatter(forma)
        log.addHandler(su_file)
    _pronto = True
    return log


def passo(lead_id, evento, dettaglio="", livello="INFO", cliente="-"):
    """Una riga del diario, sempre col cliente:

        [ora] [studiorossi] LEAD 42 | evento | dettaglio

    Serve a due cose: capire cosa e' successo a un paziente, e poter mostrare
    a UNO studio soltanto le sue righe. Basta un filtro sul nome fra parentesi.
    """
    log = prepara()
    ora = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    riga = u"[{}] [{}] LEAD {} | {} | {}".format(ora, cliente or "-", lead_id,
                                                 evento, dettaglio)
    log.log(getattr(logging, livello.upper(), logging.INFO), riga)
    # Ogni studio ha anche il suo file: si manda quello, senza filtrare a mano.
    if cliente and cliente != "-":
        try:
            os.makedirs(_CARTELLA, exist_ok=True)
            with open(os.path.join(_CARTELLA, "diario-%s.log" % cliente),
                      "a", encoding="utf-8") as f:
                f.write(riga + "\n")
        except OSError:
            pass    # il diario per-cliente e' un di piu': non blocca il lavoro
