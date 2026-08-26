# -*- coding: utf-8 -*-
"""
avatar.py - Gli avatar 3D indossati dagli abitanti del mondo.

Quando un agente genera un modello con Meshy (o da qualunque altra fonte),
qui viene registrato e assegnato a un abitante: da quel momento l'Orchestratore
o lo specialista lo "indossa": la sua faccia compare nel mondo e il modello 3D
si apre cliccandolo.

Dove stanno i file:
  avatar/            i .glb e le immagini (serviti dal mondo su /avatar/...)
  dati/avatars.json  chi indossa cosa

Un file .glb puo' essere scaricato a meta' senza che nessuno se ne accorga:
l'intestazione dichiara la lunghezza totale, quindi la controlliamo. Meglio
dirlo subito all'agente che lasciargli credere di aver finito.
"""

import io
import os
import json
import struct
import threading

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CARTELLA = os.path.join(BASE_DIR, "avatar")
DATI_DIR = os.path.join(BASE_DIR, "dati")
FILE_REGISTRO = os.path.join(DATI_DIR, "avatars.json")

_lock = threading.RLock()

# Nomi accettati per l'Orchestratore, oltre agli id dei ruoli.
ALIAS_BOSS = {"boss", "orchestratore", "orchestrator", "capo"}


def _registro():
    try:
        with io.open(FILE_REGISTRO, "r", encoding="utf-8") as f:
            d = json.load(f)
        return d if isinstance(d, dict) else {}
    except (OSError, ValueError):
        return {}


def _salva(reg):
    os.makedirs(DATI_DIR, exist_ok=True)
    tmp = FILE_REGISTRO + ".tmp"
    with io.open(tmp, "w", encoding="utf-8") as f:
        f.write(json.dumps(reg, ensure_ascii=False, indent=2))
    os.replace(tmp, FILE_REGISTRO)


def verifica_glb(percorso):
    """
    Controlla che il .glb sia completo. Ritorna (ok, messaggio).
    Un download troncato passa inosservato: il file esiste, ha un nome giusto,
    ma il visore 3D non riuscira' ad aprirlo.
    """
    try:
        dimensione = os.path.getsize(percorso)
        with io.open(percorso, "rb") as f:
            testa = f.read(12)
    except OSError as e:
        return False, u"non riesco a leggere il file: {}".format(e)

    if len(testa) < 12 or testa[:4] != b"glTF":
        return False, u"non sembra un file .glb (manca la firma glTF)"
    dichiarata = struct.unpack("<I", testa[8:12])[0]
    if dichiarata != dimensione:
        mancanti = dichiarata - dimensione
        return False, (u"file incompleto: dichiara {} byte ma ne ha {} "
                       u"(ne mancano {:.1f} MB). Riscaricalo.").format(
                           dichiarata, dimensione, mancanti / 1048576.0)
    return True, u"file completo ({:.1f} MB)".format(dimensione / 1048576.0)


def _relativo(percorso):
    """Da percorso su disco all'indirizzo con cui il mondo lo carica."""
    p = os.path.abspath(percorso)
    if not p.lower().startswith(os.path.abspath(CARTELLA).lower()):
        return None
    return "/avatar/" + os.path.relpath(p, CARTELLA).replace("\\", "/")


def _risolvi(nome):
    """Accetta un nome di file, un percorso relativo o assoluto."""
    if not nome:
        return None
    for cand in (nome,
                 os.path.join(CARTELLA, os.path.basename(nome)),
                 os.path.join(BASE_DIR, nome)):
        if os.path.isfile(cand):
            return os.path.abspath(cand)
    return None


def applica(chi, glb=None, immagine=None):
    """
    Fa indossare un avatar a un abitante.
      chi: 'boss'/'orchestratore' oppure l'id di un ruolo (code, qa, design...)
    Ritorna un dizionario con l'esito, da restituire all'agente.
    """
    chi = (chi or "").strip().lower()
    if chi in ALIAS_BOSS:
        chi = "boss"
    if not chi:
        return {"ok": False, "errore": u"manca l'abitante a cui applicarlo"}

    voce, avvisi = {}, []

    if glb:
        p = _risolvi(glb)
        if not p:
            return {"ok": False, "errore": u"modello non trovato: {}".format(glb),
                    "suggerimento": u"mettilo nella cartella avatar/ del progetto"}
        ok, msg = verifica_glb(p)
        if not ok:
            return {"ok": False, "errore": msg,
                    "suggerimento": u"riscarica il modello e riprova ad applicarlo"}
        url = _relativo(p)
        if not url:
            return {"ok": False, "errore": u"il modello deve stare nella cartella avatar/"}
        voce["glb"] = url
        avvisi.append(msg)

    if immagine:
        p = _risolvi(immagine)
        if not p:
            return {"ok": False, "errore": u"immagine non trovata: {}".format(immagine)}
        url = _relativo(p)
        if not url:
            return {"ok": False, "errore": u"l'immagine deve stare nella cartella avatar/"}
        voce["img"] = url

    if not voce:
        return {"ok": False, "errore": u"serve almeno un modello .glb o un'immagine"}

    with _lock:
        reg = _registro()
        reg.setdefault(chi, {}).update(voce)
        _salva(reg)

    return {"ok": True, "abitante": chi, "avatar": voce, "note": avvisi,
            "effetto": u"L'avatar e' stato applicato: comparira' nel mondo entro pochi secondi."}


def rimuovi(chi):
    chi = (chi or "").strip().lower()
    if chi in ALIAS_BOSS:
        chi = "boss"
    with _lock:
        reg = _registro()
        if chi not in reg:
            return {"ok": False, "errore": u"nessun avatar applicato a " + chi}
        del reg[chi]
        _salva(reg)
    return {"ok": True}


def scopri():
    """
    Cerca in avatar/ modelli non ancora assegnati, abbinandoli per nome.
    'orchestratore.glb' o 'avatar.glb' vanno al capo; 'code.glb' allo
    Sviluppatore, e cosi' via. L'immagine con lo stesso nome fa da faccia.
    """
    if not os.path.isdir(CARTELLA):
        return {}
    trovati = {}
    for f in sorted(os.listdir(CARTELLA)):
        base, est = os.path.splitext(f)
        if est.lower() != ".glb":
            continue
        chi = "boss" if base.lower() in ALIAS_BOSS | {"avatar"} else base.lower()
        voce = {"glb": "/avatar/" + f}
        for e in (".png", ".jpg", ".jpeg", ".webp"):
            for cand in (base + e, base + "_thumbnail" + e, "avatar_thumbnail" + e):
                if os.path.isfile(os.path.join(CARTELLA, cand)):
                    voce["img"] = "/avatar/" + cand
                    break
            if "img" in voce:
                break
        trovati[chi] = voce
    return trovati


def per_mondo():
    """Quello che il mondo deve sapere: chi indossa cosa."""
    with _lock:
        reg = _registro()
    fusi = dict(scopri())
    fusi.update(reg)          # una scelta esplicita batte la scoperta automatica
    return fusi


def elenco_testuale():
    m = per_mondo()
    if not m:
        return u"(nessun avatar applicato)"
    return u", ".join(u"{}: {}".format(k, v.get("glb") or v.get("img")) for k, v in m.items())
