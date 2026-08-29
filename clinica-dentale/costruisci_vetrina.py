# -*- coding: utf-8 -*-
"""Costruisce la vetrina in versione STATICA, da mettere online senza server.

Perche' esiste. La vetrina vera la serve Python: legge `app/web/vetrina.html`,
ci mette dentro i testi del settore e la manda al browser. Funziona, ma vuole
un servizio acceso da qualche parte - che costa, che si addormenta se e'
gratuito, e che va sorvegliato.

La pagina, pero', non ha bisogno di niente: l'orologio, la conversazione e il
calcolo del mancato guadagno girano tutti nel browser di chi guarda. L'unica
cosa che fa il server e' riempire i segnaposti, e quello si puo' fare una
volta sola, qui, prima di pubblicare.

Il risultato sono due file HTML che stanno in piedi da soli. Si mettono su
GitHub Pages (gratis, sempre svegli, sul TUO indirizzo) e il link nelle email
funziona sempre, anche alle undici di sera quando qualcuno lo apre.

Cosa NON entra nella versione statica: il cruscotto. Quello mostra pazienti e
ha bisogno del database, quindi resta una cosa da far vedere in diretta
durante una call, con il sistema acceso sul tuo computer.

    python costruisci_vetrina.py [cartella]      (predefinita: ../vetrina)
"""
import io
import os
import sys

RADICE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, RADICE)

from app import settori                                          # noqa: E402

MODELLO = os.path.join(RADICE, "app", "web", "vetrina.html")

# Il file che ogni settore produce. Il dentale fa da pagina d'ingresso.
NOMI = {"dentale": "index.html", "estetica": "estetica.html"}

# --- l'unico pezzo che cambia fra servita e statica -------------------------
#
# Nella versione servita il bottone porta al cruscotto, che e' li' accanto.
# In quella statica il cruscotto non c'e': un bottone che porta a una pagina
# inesistente e' peggio di nessun bottone, davanti a un potenziale cliente.
# Quindi la chiusura dice la verita': il cruscotto si vede insieme.

CHIUSURA_SERVITA = u"""    <p class="sotto" style="margin-inline:auto;text-align:center">
      Il cruscotto è acceso qui accanto: scrivi un messaggio come lo scriverebbe
      un paziente e guarda cosa succede, in diretta.</p>
    <a class="bottone" href="/">Apri il cruscotto</a>
    <a class="secondario" href="#top">Torna su</a>"""

CHIUSURA_STATICA = u"""    <p class="sotto" style="margin-inline:auto;text-align:center">
      Questa pagina racconta. Il cruscotto, invece, si guarda insieme: si scrive
      un messaggio come lo scriverebbe un paziente e si vede cosa succede, in
      diretta &mdash; la prenotazione che va da sola, l'urgenza che si ferma.</p>
    <a class="secondario" href="#top">Torna su</a>"""


def costruisci(dove):
    with io.open(MODELLO, encoding="utf-8") as f:
        modello = f.read()

    if CHIUSURA_SERVITA not in modello:
        raise SystemExit(
            u"la chiusura della pagina non e' quella che mi aspetto: "
            u"app/web/vetrina.html e' cambiato, aggiorna CHIUSURA_SERVITA qui.")
    modello = modello.replace(CHIUSURA_SERVITA, CHIUSURA_STATICA)

    if not os.path.isdir(dove):
        os.makedirs(dove)

    fatti = []
    for chiave, nome in sorted(NOMI.items()):
        settore = settori.per_chiave(chiave)
        pagina = modello
        for segnaposto, valore in settore.vetrina.items():
            pagina = pagina.replace("{{%s}}" % segnaposto, valore)

        rimasti = pagina.count("{{")
        if rimasti:
            raise SystemExit(u"il settore «%s» lascia %d segnaposti vuoti"
                             % (chiave, rimasti))

        strada = os.path.join(dove, nome)
        with io.open(strada, "w", encoding="utf-8") as f:
            f.write(pagina)
        fatti.append((chiave, nome, os.path.getsize(strada)))

    print(u"Vetrina statica in %s" % os.path.abspath(dove))
    for chiave, nome, peso in fatti:
        print(u"  %-9s -> %-14s %5.0f KB" % (chiave, nome, peso / 1024.0))
    print(u"\nNessun server, nessuna chiave, nessun costo per visitatore.")
    return 0


if __name__ == "__main__":
    cartella = sys.argv[1] if len(sys.argv) > 1 else os.path.join(RADICE, "..", "vetrina")
    sys.exit(costruisci(cartella))
