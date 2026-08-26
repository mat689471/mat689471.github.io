# -*- coding: utf-8 -*-
"""
competenze.py - Le Skill di Claude Code messe a disposizione degli agenti.

Una skill di Claude Code e' una cartella con dentro un file SKILL.md: poche
righe di intestazione (nome e descrizione) e poi le istruzioni vere e proprie.
Claude Code le carica da solo; l'ecosistema, fino a ora, non sapeva che
esistessero.

Questo modulo colma il divario. Funziona come Claude Code stesso:
  - all'avvio raccoglie NOME e DESCRIZIONE di ogni skill trovata e le mette
    nel prompt degli agenti (poco testo, sempre presente);
  - il contenuto completo viene letto solo quando un agente decide che quella
    skill gli serve, tramite lo strumento 'leggi_competenza'.

Cosi' le competenze che hai gia' scritto per Claude Code diventano patrimonio
anche dei tuoi agenti, senza doverle riscrivere.

Nota di fiducia: il contenuto di una skill finisce nel prompt di un agente.
Sono file tuoi, sul tuo computer - lo stesso rapporto di fiducia che hai gia'
con Claude Code - ma vale la pena saperlo.
"""

import io
import os
import glob

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
HOME = os.path.expanduser("~")

# Dove Claude Code tiene le skill: personali, di progetto e dei plugin
# (ruflo installa le sue qui sotto).
SCHEMI = [
    (os.path.join(HOME, ".claude", "skills", "*", "SKILL.md"), u"personale"),
    (os.path.join(BASE_DIR, ".claude", "skills", "*", "SKILL.md"), u"progetto"),
    (os.path.join(HOME, ".claude", "plugins", "*", "skills", "*", "SKILL.md"), u"plugin"),
    (os.path.join(HOME, ".claude", "plugins", "*", "*", "skills", "*", "SKILL.md"), u"plugin"),
    (os.path.join(HOME, ".claude", "plugins", "*", "*", "*", "skills", "*", "SKILL.md"), u"plugin"),
]

MAX_CONTENUTO = 20000   # una skill enorme non deve saturare il contesto


def _intestazione(testo):
    """
    Legge l'intestazione YAML fra le due righe '---' in cima al file.
    Ci serve solo 'name' e 'description', quindi un parser minimo basta:
    niente dipendenze da installare.
    """
    campi = {}
    righe = testo.splitlines()
    if not righe or righe[0].strip() != "---":
        return campi
    chiave = None
    for riga in righe[1:]:
        if riga.strip() == "---":
            break
        if riga.startswith((" ", "\t")) and chiave:
            campi[chiave] += u" " + riga.strip()      # valore che continua a capo
            continue
        if ":" in riga:
            k, _, v = riga.partition(":")
            chiave = k.strip()
            campi[chiave] = v.strip().strip('"').strip("'")
    return campi


def _nome_da_percorso(percorso):
    return os.path.basename(os.path.dirname(percorso))


def elenca():
    """Tutte le skill trovate: nome, descrizione, provenienza, percorso."""
    viste, out = set(), []
    for schema, fonte in SCHEMI:
        for percorso in sorted(glob.glob(schema)):
            reale = os.path.normcase(os.path.abspath(percorso))
            if reale in viste:
                continue
            viste.add(reale)
            try:
                with io.open(percorso, "r", encoding="utf-8", errors="replace") as f:
                    testa = f.read(4000)
            except OSError:
                continue
            meta = _intestazione(testa)
            nome = meta.get("name") or _nome_da_percorso(percorso)
            out.append({
                "nome": nome,
                "descrizione": (meta.get("description") or u"(nessuna descrizione)")[:400],
                "fonte": fonte,
                "percorso": percorso,
            })
    out.sort(key=lambda s: s["nome"].lower())
    return out


def leggi(nome):
    """Contenuto completo di una skill, cercata per nome (anche parziale)."""
    n = (nome or "").strip().lower()
    if not n:
        return None
    skills = elenca()
    scelta = (next((s for s in skills if s["nome"].lower() == n), None)
              or next((s for s in skills if n in s["nome"].lower()), None))
    if not scelta:
        return None
    try:
        with io.open(scelta["percorso"], "r", encoding="utf-8", errors="replace") as f:
            contenuto = f.read(MAX_CONTENUTO + 1)
    except OSError as e:
        return {"nome": scelta["nome"], "errore": str(e)}
    troncato = len(contenuto) > MAX_CONTENUTO
    return {
        "nome": scelta["nome"],
        "fonte": scelta["fonte"],
        "percorso": scelta["percorso"],
        "contenuto": contenuto[:MAX_CONTENUTO] + (u"\n\n[…contenuto troncato]" if troncato else u""),
    }


def righe_per_prompt(skills=None):
    """Le righe da mettere nel prompt: solo nomi e descrizioni."""
    skills = elenca() if skills is None else skills
    if not skills:
        return []
    righe = [
        u"",
        u"--- Competenze disponibili (Skill di Claude Code) ---",
        u"Sono istruzioni gia' scritte dall'utente per svolgere compiti specifici.",
        u"Se una di queste riguarda il tuo compito, LEGGILA con 'leggi_competenza'",
        u"prima di procedere, e poi seguine le istruzioni.",
    ]
    for s in skills[:40]:
        righe.append(u"- {}: {}".format(s["nome"], s["descrizione"][:180]))
    if len(skills) > 40:
        righe.append(u"- (+{} altre)".format(len(skills) - 40))
    return righe
