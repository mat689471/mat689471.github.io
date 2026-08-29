# -*- coding: utf-8 -*-
"""Il contratto del calendario. Domani Google Calendar entra da qui."""
from abc import ABC, abstractmethod


class Calendario(ABC):

    @abstractmethod
    def slot_libero(self, preferenza=None, urgenza=None):
        """Il primo slot compatibile, o None.

        {"slot_id": int, "inizio": str, "fine": str, "studio": str|None}
        'preferenza' e' testo libero ('mattina', 'pomeriggio'); con
        urgenza='emergenza' si prende il primo disponibile senza filtrare.
        """
        raise NotImplementedError

    @abstractmethod
    def prenota(self, slot_id, lead_id):
        """Occupa lo slot. Se lo stesso lead riprenota lo stesso slot, ok.

        {"ok": bool, "slot_id": int, "inizio": str|None, "fine": str|None,
         "errore": str|None}
        """
        raise NotImplementedError
