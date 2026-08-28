/**
 * prova-chiavi.mjs — «Questa chiave funziona?», chiesto al servizio.
 *
 * Una chiave che non va produce sempre lo stesso sintomo - una chiamata che
 * fallisce - ma le cause sono diverse e portano a rimedi opposti: il valore e'
 * sbagliato, i permessi mancano, il nome della risorsa non esiste, o e' solo
 * troppo traffico. Senza un modo di chiederlo si tira a indovinare, e si
 * costruiscono rimedi per problemi che non ci sono.
 *
 * Qui ogni servizio noto ha la sua chiamata piu' innocua - un elenco, un
 * conteggio - e la risposta viene tradotta in una frase che dice cosa fare.
 * Non scrive niente da nessuna parte: e' una domanda, non un'operazione.
 */

const PROVE = {
  ANTHROPIC_API_KEY: {
    servizio: "Anthropic",
    prova: (k) => fetch("https://api.anthropic.com/v1/models?limit=1", {
      headers: { "x-api-key": k, "anthropic-version": "2023-06-01" },
    }),
    // l'elenco dei modelli e' anche il modo giusto per sapere quali nomi valgono
    buono: async (r) => {
      const d = await r.json().catch(() => ({}));
      const nomi = (d.data || []).map((m) => m.id);
      return "chiave valida" + (nomi.length ? " · modelli disponibili, per esempio " + nomi[0] : "");
    },
  },
  HUBSPOT_TOKEN: {
    servizio: "HubSpot",
    prova: (k) => fetch("https://api.hubapi.com/crm/v3/objects/contacts?limit=1", {
      headers: { Authorization: "Bearer " + k },
    }),
    buono: async () => "token valido, i contatti si leggono",
  },
  PRINTIFY_API_TOKEN: {
    servizio: "Printify",
    prova: (k) => fetch("https://api.printify.com/v1/shops.json", {
      headers: { Authorization: "Bearer " + k },
    }),
    buono: async (r) => {
      const d = await r.json().catch(() => []);
      return "token valido · " + (Array.isArray(d) ? d.length : 0) + " negozi collegati";
    },
  },
  STRIPE_SECRET_KEY: {
    servizio: "Stripe",
    prova: (k) => fetch("https://api.stripe.com/v1/products?limit=1", {
      headers: { Authorization: "Bearer " + k },
    }),
    buono: async () => "chiave valida, il catalogo si legge",
  },
  STRIPE_RESTRICTED_KEY: {
    servizio: "Stripe (sola lettura)",
    prova: (k) => fetch("https://api.stripe.com/v1/products?limit=1", {
      headers: { Authorization: "Bearer " + k },
    }),
    buono: async () => "chiave valida",
  },
};

/**
 * Cosa vuol dire davvero quel numero, e cosa farci.
 *
 * Un 401 o un 403 non arrivano per forza dal servizio: un proxy aziendale, un
 * antivirus che ispeziona il traffico o un firewall rispondono con gli stessi
 * codici. Dire «la chiave non ha i permessi» quando a rifiutare e' stato un
 * apparato di mezzo manda a cercare nel posto sbagliato - ed e' proprio
 * l'errore che questo strumento esiste per evitare. Quindi prima di
 * interpretare si guarda se la risposta ha la forma di un errore del servizio.
 */
function traduci(stato, servizio, corpo) {
  const dettaglio = (corpo || "").replace(/\s+/g, " ").trim().slice(0, 180);
  const dalServizio = (() => {
    try { JSON.parse(corpo); return true; } catch { return false; }
  })();

  if ((stato === 401 || stato === 403) && !dalServizio) return {
    esito: "forse",
    che: "qualcosa fra il tuo computer e " + servizio + " ha rifiutato la richiesta",
    fare: "La risposta non ha la forma di un errore di " + servizio + ": non e' "
        + "detto che il problema sia la chiave. Di solito e' un proxy aziendale, "
        + "un antivirus che ispeziona il traffico o un firewall. Prova la stessa "
        + "chiamata da un'altra rete."
        + (dettaglio ? " Risposta ricevuta: " + dettaglio : ""),
  };

  if (stato === 401) return {
    esito: "no",
    che: "il valore della chiave non viene accettato",
    fare: "Ricopiala dal sito di " + servizio + " col pulsante «copia», senza "
        + "selezionarla a mano: quasi sempre e' arrivata incompleta, o con uno "
        + "spazio davanti. Se e' recente, controlla anche di averla presa "
        + "dall'account giusto.",
  };
  if (stato === 403) return {
    esito: "no",
    che: "la chiave e' valida ma non ha i permessi per questa operazione",
    fare: "Il valore va bene: aggiungi gli ambiti mancanti dove l'hai creata. "
        + "Non serve rigenerarla.",
  };
  if (stato === 404) return {
    esito: "no",
    che: "l'indirizzo o il nome della risorsa non esiste",
    fare: "Non e' un problema di chiave. Di solito e' un nome scaduto o scritto "
        + "male nella richiesta.",
  };
  if (stato === 429) return {
    esito: "forse",
    che: "troppe richieste in poco tempo",
    fare: "La chiave probabilmente va bene. Riprova fra qualche minuto.",
  };
  if (stato >= 500) return {
    esito: "forse",
    che: "il servizio ha un problema suo",
    fare: "Non dipende dalla chiave. Riprova piu' tardi.",
  };
  return { esito: "no", che: "risposta inattesa (" + stato + ")",
           fare: dettaglio || "Nessun dettaglio dal servizio." };
}

/** Prova una chiave. Ritorna sempre una risposta leggibile, mai un'eccezione. */
export async function provaChiave(nome, valore) {
  const p = PROVE[nome];
  if (!p) return { nome, esito: "sconosciuto",
                   che: "non so come provare questa chiave",
                   fare: "Le chiavi che so provare: " + Object.keys(PROVE).join(", ") };
  if (!valore) return { nome, servizio: p.servizio, esito: "no",
                        che: "non c'e' nessun valore in Cassaforte", fare: "Aggiungila." };

  // uno spazio o un a capo in coda basta a far fallire l'autenticazione, e non
  // si vede: lo diciamo invece di lasciarlo scoprire per tentativi
  const sporca = valore !== valore.trim();
  const k = valore.trim();

  let r;
  try { r = await p.prova(k); }
  catch (e) {
    return { nome, servizio: p.servizio, esito: "no",
             che: "non riesco a raggiungere " + p.servizio,
             fare: "Controlla la connessione. (" + e.message + ")" };
  }

  if (r.ok) {
    return { nome, servizio: p.servizio, esito: "si",
             che: await p.buono(r).catch(() => "chiave valida"),
             fare: sporca ? "Attenzione: nella Cassaforte ha spazi in fondo. "
                          + "Funziona lo stesso perche' li tolgo io, ma meglio risalvarla pulita." : "" };
  }
  const corpo = await r.text().catch(() => "");
  return { nome, servizio: p.servizio, stato: r.status, ...traduci(r.status, p.servizio, corpo) };
}

export const CHIAVI_PROVABILI = Object.keys(PROVE);
