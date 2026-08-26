# Avatar degli abitanti

Qui vanno i modelli 3D e le immagini che gli abitanti del mondo indossano.

## Come si applica un avatar

**Modo automatico (consigliato):** chiedilo nella Sala Comando —
*"genera un avatar per l'Orchestratore e applicalo"*. L'agente lo crea (con la
chiave Meshy dalla Cassaforte), lo salva qui e lo applica da solo con lo
strumento `applica_avatar`.

**Modo manuale:** metti i file qui dentro con il nome dell'abitante. Vengono
riconosciuti al riavvio dell'ecosistema, senza dover fare altro:

| File | Chi lo indossa |
|---|---|
| `orchestratore.glb` + `orchestratore.png` | l'Orchestratore |
| `avatar.glb` + `avatar_thumbnail.png` | l'Orchestratore (nomi che usa Meshy) |
| `code.glb` + `code.png` | lo Sviluppatore |
| `qa.glb`, `design.glb`, `ux.glb`, `research.glb`… | il ruolo corrispondente |

- il **`.glb`** è il modello 3D: si apre cliccando l'agente nel mondo;
- l'**immagine** diventa la sua faccia nella scena e nella lista.

## Perché un avatar può non comparire

Un `.glb` scaricato a metà sembra a posto — c'è, ha il nome giusto — ma il
visore non riesce ad aprirlo. L'ecosistema controlla l'intestazione del file
(che dichiara la lunghezza totale) e **rifiuta di applicarlo** dicendo quanto
manca, invece di lasciarti credere che sia fatto.

Se succede: riscarica il modello e riprova.

## Nota

I modelli generati non finiscono nel repository (sono grossi e sono tuoi):
questa cartella è esclusa da git tranne questo file.
