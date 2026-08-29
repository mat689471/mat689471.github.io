# -*- coding: utf-8 -*-
"""Il contratto del CRM. Due sole operazioni: il contatto e la trattativa."""
from abc import ABC, abstractmethod


def dividi_nome(nome):
    """'Mario Rossi' -> ('Mario', 'Rossi'). Regge anche i casi storti."""
    parti = (nome or "").strip().split()
    if not parti:
        return "", ""
    if len(parti) == 1:
        return parti[0], ""
    return parti[0], " ".join(parti[1:])


class CRM(ABC):
    nome = "astratto"

    @abstractmethod
    def contatto(self, lead):
        """Crea il contatto, o riusa quello che c'e' gia' con la stessa email.

        {"ok": bool, "contact_id": str|None, "creato": bool,
         "errore": str|None, "fonte": str}
        """
        raise NotImplementedError

    @abstractmethod
    def deal(self, contact_id, lead, qualificazione):
        """Crea la trattativa e la lega al contatto.

        {"ok": bool, "deal_id": str|None, "errore": str|None, "fonte": str}
        """
        raise NotImplementedError
