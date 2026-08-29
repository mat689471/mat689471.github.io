# -*- coding: utf-8 -*-
"""I settori: lo stesso motore, mestieri diversi.

Il sistema era scritto per studi dentistici, con l'odontoiatria cucita dentro
al prompt e dentro alle regole di sicurezza. Funzionava, ma voleva dire un
sistema per mestiere - e quindi rifare tutto da capo per il primo cliente che
non fosse un dentista.

Qui il mestiere diventa un dato. Un settore descrive tre cose, e nient'altro:

  1. COME PARLARE      - chi sei, chi hai davanti, cosa devi capire;
  2. QUANDO FERMARTI   - quali parole obbligano a chiamare una persona.
                         Questa lista NON passa dal modello: la applica il
                         codice dopo, in app/agent.py, e c'e' una prova che
                         lo verifica;
  3. COME RACCONTARLO  - i testi della vetrina, perche' a un chirurgo estetico
                         non si fa vedere una demo che parla di otturazioni.

Aggiungere un mestiere e' aggiungere una voce a SETTORI. Non si tocca il
motore: ne' l'agenda, ne' il CRM, ne' l'isolamento fra clienti.

La regola che vale in ogni settore, e che non si configura: davanti a un
sintomo non si decide. Si passa la mano.
"""

PREDEFINITO = "dentale"


class Settore(object):
    """Un mestiere: come parla, dove si ferma, come si racconta."""

    def __init__(self, chiave, etichetta, luogo, persona, mestiere_di_chi_risponde,
                 cosa_capire, scala_urgenza, alto_valore, alto_valore_detto,
                 divieti, vetrina):
        self.chiave = chiave
        self.etichetta = etichetta                  # "Studi dentistici"
        self.luogo = luogo                          # "uno studio dentistico italiano"
        self.persona = persona                      # "paziente"
        self.mestiere_di_chi_risponde = mestiere_di_chi_risponde
        self.cosa_capire = cosa_capire
        self.scala_urgenza = scala_urgenza
        self.alto_valore = tuple(alto_valore)       # applicate dal CODICE
        self.alto_valore_detto = alto_valore_detto  # le stesse, dette al modello
        self.divieti = divieti
        self.vetrina = dict(vetrina)

    def __repr__(self):
        return "<Settore %s>" % self.chiave


# ---------------------------------------------------------------------------
# DENTALE - il settore da cui e' nato tutto. Il testo e' quello di prima,
# parola per parola: chi lo usava non deve accorgersi di niente.
# ---------------------------------------------------------------------------
DENTALE = Settore(
    chiave="dentale",
    etichetta=u"Studi dentistici",
    luogo=u"uno studio dentistico italiano",
    persona=u"paziente",
    mestiere_di_chi_risponde=u"una segretaria esperta",
    cosa_capire=u"""\
- Di che trattamento ha bisogno, fra quelli qui sopra, oppure se e'
  un'urgenza per dolore.
- Quanto e' urgente davvero.
- Quando preferirebbe venire (mattina, pomeriggio, giorni).""",
    scala_urgenza=u"""\
- emergenza: dolore acuto, gonfiore, trauma, sanguinamento, ascesso, febbre.
- alta: fastidio importante ma non emergenza, dente rotto senza dolore forte.
- media: un trattamento che vuole fare a breve.
- bassa: estetica o routine senza fretta.""",
    alto_valore=("impianto", "impianti", "ortodonzia", "all-on-4", "all on 4",
                 "riabilitazione", "protesi", "faccette"),
    alto_valore_detto=u"impianti, ortodonzia completa, All-on-4, protesi",
    divieti=u"""\
- Fare diagnosi o dare consigli clinici: davanti a un sintomo rassicura,
  segna l'urgenza e passa la mano.
- Inventare prezzi: si definiscono in visita.""",
    vetrina={
        "titolo_pagina": u"Il paziente scrive alle 21:47 — risposta automatica ai lead",
        "occhiello": u"Studi dentistici",
        "eroe_titolo": u"Il paziente scrive alle 21:47.<br>Tu <em>apri domani</em>.",
        "eroe_testo": u"Chi ha mal di denti la sera non aspetta il mattino: scrive "
                      u"a te, e mentre non rispondi scrive anche a un altro. Questo "
                      u"sistema risponde subito, capisce cosa serve e propone un "
                      u"posto in agenda — e quando il caso è serio chiama te, invece "
                      u"di improvvisare.",
        "stato_chiuso": u"studio chiuso",
        "stato_aperto": u"studio aperto",
        "settimana_titolo": u"Una settimana ha 168 ore. La reception ne copre 40.",
        "settimana_nota": u"del tempo lo studio non risponde",
        "passo2": u"Che trattamento serve, quanto è urgente, quando preferisce "
                  u"venire. Conosce i tuoi orari e i tuoi trattamenti, non quelli "
                  u"di un altro.",
        "fermata_titolo": u"Davanti a un sintomo, il sistema si ferma e chiama una persona.",
        "fermata_testo": u"Nessuna diagnosi, nessun consiglio clinico, nessun prezzo "
                         u"inventato. Un paziente con dolore o gonfiore non viene "
                         u"gestito da un programma: finisce in cima alla lista di chi "
                         u"deve essere richiamato subito.",
        "regola1": u"Dolore, gonfiore, trauma, ascesso",
        "regola2": u"Impianti, ortodonzia, protesi",
        "conto_titolo": u"Quanto vale una richiesta a cui nessuno risponde?",
        "conto_valore_label": u"Quanto vale in media un paziente nuovo",
        "conto_valore": "600",
        "conto_valore_max": "3000",
        "conto_valore_passo": "50",
        "isolamento": u"Tiene separati gli studi",
        "chat_nome": u"Elena",
        "chat_1": u"Buonasera, si è staccato un pezzo di dente mentre mangiavo. "
                  u"Fa un po’ male. Riuscite a vedermi presto?",
        "chat_2": u"Mi dispiace, Elena. Un dente scheggiato che fa male lo facciamo "
                  u"guardare da un nostro dentista: la sto passando a una persona "
                  u"dello studio, che la richiama appena apriamo.",
        "chat_3": u"Elena è la prima della lista, con la nota: dente scheggiato, "
                  u"dolore. Nessuno ha dovuto stare sveglio.",
        "chat_luogo": u"In studio, ore 8:31",
    },
)


# ---------------------------------------------------------------------------
# ESTETICA - medicina e chirurgia estetica.
#
# Cambia una cosa sostanziale rispetto al dentale, e va capita: qui quasi
# tutto quello che il cliente chiede e' un ATTO MEDICO. Un filler non e' una
# pulizia dei denti - e' una iniezione, con anamnesi e controindicazioni.
# Quindi la soglia del «passa a una persona» e' molto piu' bassa: si prenota
# da solo soltanto cio' che non e' invasivo (laser, consulenza, valutazione).
#
# L'emergenza qui non e' il mal di denti: e' la COMPLICANZA dopo un
# trattamento fatto - gonfiore anomalo, dolore forte, febbre, una reazione.
# Quella persona non deve aspettare lunedi', e non deve leggere una risposta
# scritta da un programma.
# ---------------------------------------------------------------------------
ESTETICA = Settore(
    chiave="estetica",
    etichetta=u"Medicina e chirurgia estetica",
    luogo=u"una clinica italiana di medicina e chirurgia estetica",
    persona=u"paziente",
    mestiere_di_chi_risponde=u"una consulente d'accoglienza esperta",
    cosa_capire=u"""\
- Che trattamento ha in mente, fra quelli qui sopra.
- Se ha gia' fatto un trattamento da voi e sta segnalando un problema DOPO:
  in quel caso e' la cosa piu' urgente che ti puo' arrivare.
- Quando preferirebbe venire (mattina, pomeriggio, giorni).""",
    scala_urgenza=u"""\
- emergenza: sta segnalando un problema dopo un trattamento gia' fatto -
  gonfiore anomalo, dolore forte, febbre, una reazione, qualcosa che non
  si sgonfia o non si riassorbe.
- alta: e' preoccupato per un risultato, o ha un evento vicino e teme di
  non arrivarci.
- media: vuole fare un trattamento a breve e chiede come funziona.
- bassa: sta guardandosi intorno, chiede informazioni generali.""",
    # Il codice ferma tutto questo, qualunque cosa dica il modello.
    alto_valore=("chirurg", "rinoplastica", "mastoplastica", "liposuzione",
                 "lipofilling", "blefaroplastica", "addominoplastica", "lifting",
                 "otoplastica", "protesi", "trapianto",
                 "filler", "botulino", "tossina", "acido ialuronico",
                 "biorivitalizzazione", "mesoterapia", "fili di trazione",
                 "complicanza", "post_trattamento"),
    alto_valore_detto=u"qualunque intervento chirurgico (rinoplastica, "
                      u"mastoplastica, liposuzione, blefaroplastica, lifting, "
                      u"addominoplastica) e qualunque trattamento iniettivo "
                      u"(filler, tossina botulinica, biorivitalizzazione, fili)",
    divieti=u"""\
- Fare diagnosi, dare consigli medici o dire se un trattamento e' adatto a
  questa persona: lo stabilisce il medico in visita, dopo l'anamnesi.
- Dire che un trattamento e' sicuro, indolore o senza rischi.
- Promettere un risultato, mostrarne uno o dire quanto dura.
- Inventare prezzi: si definiscono in consulenza.
- Rassicurare qualcuno che segnala un problema dopo un trattamento. Non lo
  tranquillizzi: lo passi subito a una persona.""",
    vetrina={
        "titolo_pagina": u"La richiesta arriva alle 21:47 — risposta automatica ai lead",
        "occhiello": u"Cliniche di medicina estetica",
        "eroe_titolo": u"La richiesta arriva alle 21:47.<br>Tu <em>apri domani</em>.",
        "eroe_testo": u"Chi decide di informarsi su un trattamento lo fa la sera, dal "
                      u"telefono, dopo un annuncio. Se non trova risposta compila il "
                      u"modulo della clinica accanto, e domani mattina il contatto "
                      u"che hai pagato è già di qualcun altro. Questo sistema "
                      u"risponde subito, capisce cosa cerca e propone una "
                      u"consulenza — e quando il caso è medico chiama te, invece di "
                      u"improvvisare.",
        "stato_chiuso": u"clinica chiusa",
        "stato_aperto": u"clinica aperta",
        "settimana_titolo": u"Una settimana ha 168 ore. La segreteria ne copre 40.",
        "settimana_nota": u"del tempo la clinica non risponde",
        "passo2": u"Che trattamento cerca, se sta segnalando un problema dopo un "
                  u"intervento, quando preferisce venire. Conosce i tuoi orari e i "
                  u"tuoi trattamenti, non quelli di un'altra clinica.",
        "fermata_titolo": u"Un trattamento medico non lo prenota un programma.",
        "fermata_testo": u"Nessuna diagnosi, nessun parere su cosa è adatto a quella "
                         u"persona, nessuna promessa di risultato, nessun prezzo "
                         u"inventato. Chirurgia e iniettivi passano sempre da una "
                         u"persona: il sistema fissa la consulenza, non il "
                         u"trattamento.",
        "regola1": u"Un problema dopo un trattamento già fatto",
        "regola2": u"Chirurgia, filler, botulino, fili",
        "conto_titolo": u"Quanto vale una richiesta a cui nessuno risponde?",
        "conto_valore_label": u"Quanto vale in media un paziente nuovo",
        "conto_valore": "2500",
        "conto_valore_max": "8000",
        "conto_valore_passo": "100",
        "isolamento": u"Tiene separate le cliniche",
        "chat_nome": u"Elena",
        "chat_1": u"Buonasera, ho fatto il filler alle labbra da voi giovedì e "
                  u"stamattina si è gonfiato molto da un lato. Devo preoccuparmi?",
        "chat_2": u"Elena, di questo la faccio parlare subito con il medico che l’ha "
                  u"seguita — non è una cosa su cui posso risponderle io. La sto "
                  u"segnalando come prima della lista: la richiamano appena apriamo, "
                  u"e se peggiora durante la notte vada al pronto soccorso.",
        "chat_3": u"Elena è la prima della lista, con la nota: gonfiore asimmetrico "
                  u"dopo filler, quarta giornata. Nessuno ha dovuto stare sveglio.",
        "chat_luogo": u"In clinica, ore 8:31",
    },
)


SETTORI = {s.chiave: s for s in (DENTALE, ESTETICA)}


class SettoreSconosciuto(RuntimeError):
    pass


def per_chiave(chiave):
    """Il settore, o un errore che dice quali esistono.

    Non si ripiega sul dentale in silenzio: un cliente estetico servito con le
    regole del dentale prenoterebbe da solo una rinoplastica.
    """
    c = (chiave or "").strip().lower() or PREDEFINITO
    if c not in SETTORI:
        raise SettoreSconosciuto(
            u"settore «%s» sconosciuto: esistono %s"
            % (chiave, ", ".join(sorted(SETTORI))))
    return SETTORI[c]
