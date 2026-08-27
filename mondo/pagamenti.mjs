/**
 * pagamenti.mjs — Gli agenti costruiscono l'offerta, non solo il sito.
 *
 * Un link di pagamento fatto a mano vale per un prezzo solo. Se lo sciame
 * inventa un servizio con tre livelli di abbonamento, quei tre livelli devono
 * nascere da soli: prodotto, prezzi, e il link per pagarli.
 *
 * Qui dentro c'e' l'unico punto che parla con Stripe e PayPal. Gli agenti
 * chiedono «crea questa offerta» e ricevono i link: non vedono mai una chiave,
 * non scrivono mai una chiamata HTTP, non possono inventarsi un'operazione che
 * non sia creare un'offerta.
 *
 * Cosa NON si puo' fare da qui, di proposito: incassare, rimborsare, spostare
 * denaro, cancellare. Creare un'offerta e' reversibile - si archivia - e non
 * muove un centesimo finche' non e' un cliente vero a premere «Paga».
 */

const STRIPE = "https://api.stripe.com/v1";
const PAYPAL = { vivo: "https://api-m.paypal.com", prova: "https://api-m.sandbox.paypal.com" };

const CADENZE = {
  unatantum: null,
  mensile:   { interval: "month", conteggio: 1 },
  annuale:   { interval: "year",  conteggio: 1 },
};

/** Stripe vuole i parametri come un modulo, anche quelli annidati. */
function modulo(oggetto, prefisso = "", out = new URLSearchParams()) {
  for (const [k, v] of Object.entries(oggetto)) {
    if (v === undefined || v === null) continue;
    const chiave = prefisso ? `${prefisso}[${k}]` : k;
    if (typeof v === "object" && !Array.isArray(v)) modulo(v, chiave, out);
    else if (Array.isArray(v)) v.forEach((x, i) => modulo(x, `${chiave}[${i}]`, out));
    else out.append(chiave, String(v));
  }
  return out;
}

/**
 * Da un prezzo scritto in qualunque modo ai centesimi, che e' l'unico modo di
 * non perdere spiccioli per strada.
 *
 * Il prezzo lo scrive un agente, e puo' arrivare all'italiana ("1.234,50") o
 * all'inglese ("1,234.50"). La regola che distingue le due: quando ci sono
 * entrambi i separatori, l'ultimo e' quello dei decimali; quando ce n'e' uno
 * solo, e' decimale se lo seguono al massimo due cifre, altrimenti separa le
 * migliaia. Cosi' "29,90" fa 29,90 e "1.234" fa milleduecentotrentaquattro.
 */
export function centesimi(valore) {
  let n;
  if (typeof valore === "number") {
    n = valore;
  } else {
    let t = String(valore).replace(/[\s\u00a0]/g, "").replace(/[€$£]/g, "");
    const ultimoP = t.lastIndexOf("."), ultimaV = t.lastIndexOf(",");
    if (ultimoP >= 0 && ultimaV >= 0) {
      const dec = Math.max(ultimoP, ultimaV);
      t = t.slice(0, dec).replace(/[.,]/g, "") + "." + t.slice(dec + 1);
    } else if (ultimoP >= 0 || ultimaV >= 0) {
      const dec = Math.max(ultimoP, ultimaV);
      const dopo = t.length - dec - 1;
      t = (dopo <= 2 && dopo > 0)
        ? t.slice(0, dec).replace(/[.,]/g, "") + "." + t.slice(dec + 1)
        : t.replace(/[.,]/g, "");
    }
    n = Number(t);
  }
  if (!Number.isFinite(n) || n < 0) throw new Error("prezzo non valido: " + valore);
  // Un prezzo vuoto diventerebbe zero in silenzio, e un link da 0 euro non
  // serve a nessuno: meglio fermarsi e farselo dire.
  if (n === 0) throw new Error("il prezzo manca o e' zero: " + JSON.stringify(valore));
  // Un prezzo assurdo e' quasi sempre uno zero di troppo, non un'intenzione.
  if (n > 999999) throw new Error("prezzo troppo alto, controlla gli zeri: " + valore);
  return Math.round(n * 100);
}

export class Pagamenti {
  constructor(leggiChiave) {
    // Una funzione, non i valori: le chiavi restano nella Cassaforte e vengono
    // lette solo nell'istante della chiamata.
    this.chiave = leggiChiave;
    this._ppToken = null;
    this._ppScade = 0;
  }

  quali() {
    return {
      stripe: !!this.chiave("STRIPE_SECRET_KEY") || !!this.chiave("STRIPE_RESTRICTED_KEY"),
      paypal: !!(this.chiave("PAYPAL_CLIENT_ID") && this.chiave("PAYPAL_CLIENT_SECRET")),
    };
  }

  // ---- Stripe -----------------------------------------------------------
  #chiaveStripe() {
    const k = this.chiave("STRIPE_SECRET_KEY") || this.chiave("STRIPE_RESTRICTED_KEY");
    if (!k) throw new Error("manca la chiave Stripe in Cassaforte (STRIPE_SECRET_KEY)");
    return k;
  }

  async #stripe(percorso, corpo) {
    const r = await fetch(STRIPE + percorso, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + this.#chiaveStripe(),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: modulo(corpo || {}).toString(),
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) {
      const e = t.error || {};
      // Il caso piu' probabile e' una chiave ristretta senza i permessi giusti:
      // dirlo com'e' evita mezz'ora di ricerche.
      if (e.code === "api_key_expired" || /permission|scope/i.test(e.message || ""))
        throw new Error("la chiave Stripe non ha il permesso di scrivere su "
          + percorso.slice(1) + ". Serve una chiave ristretta con «write» su "
          + "Prodotti, Prezzi e Link di pagamento.");
      throw new Error(e.message || ("Stripe ha risposto " + r.status));
    }
    return t;
  }

  /**
   * Un'offerta: un servizio con uno o piu' livelli, ognuno col suo link.
   * livelli: [{ nome, prezzo, cadenza: unatantum|mensile|annuale, descrizione }]
   */
  async creaStripe({ nome, descrizione, valuta = "eur", livelli }) {
    const prod = await this.#stripe("/products", { name: nome, description: descrizione || undefined });
    const fatti = [];
    for (const l of livelli) {
      const cad = CADENZE[l.cadenza || "unatantum"];
      if (cad === undefined) throw new Error("cadenza sconosciuta: " + l.cadenza);
      const prezzo = await this.#stripe("/prices", {
        product: prod.id,
        currency: valuta.toLowerCase(),
        unit_amount: centesimi(l.prezzo),
        nickname: l.nome || undefined,
        ...(cad ? { recurring: { interval: cad.interval, interval_count: cad.conteggio } } : {}),
      });
      const link = await this.#stripe("/payment_links", {
        line_items: [{ price: prezzo.id, quantity: 1 }],
      });
      fatti.push({
        livello: l.nome || nome,
        prezzo: l.prezzo, valuta: valuta.toUpperCase(),
        cadenza: l.cadenza || "unatantum",
        url: link.url, idPrezzo: prezzo.id, idLink: link.id,
      });
    }
    return { fornitore: "stripe", prodotto: prod.id, nome, livelli: fatti };
  }

  // ---- PayPal -----------------------------------------------------------
  #basePayPal() {
    const id = this.chiave("PAYPAL_CLIENT_ID") || "";
    // Le credenziali di prova cominciano per 'A' come quelle vere, ma l'app
    // sandbox e' registrata su un altro dominio: lo diciamo esplicitamente.
    return this.chiave("PAYPAL_SANDBOX") ? PAYPAL.prova : PAYPAL.vivo;
  }

  async #tokenPayPal() {
    if (this._ppToken && Date.now() < this._ppScade) return this._ppToken;
    const id = this.chiave("PAYPAL_CLIENT_ID"), seg = this.chiave("PAYPAL_CLIENT_SECRET");
    if (!id || !seg) throw new Error("mancano PAYPAL_CLIENT_ID e PAYPAL_CLIENT_SECRET in Cassaforte");
    const r = await fetch(this.#basePayPal() + "/v1/oauth2/token", {
      method: "POST",
      headers: {
        Authorization: "Basic " + Buffer.from(id + ":" + seg).toString("base64"),
        "Content-Type": "application/x-www-form-urlencoded",
      },
      body: "grant_type=client_credentials",
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(t.error_description || "PayPal non accetta le credenziali");
    this._ppToken = t.access_token;
    this._ppScade = Date.now() + (Number(t.expires_in) || 3000) * 1000 - 60000;
    return this._ppToken;
  }

  async #paypal(percorso, corpo) {
    const r = await fetch(this.#basePayPal() + percorso, {
      method: "POST",
      headers: {
        Authorization: "Bearer " + await this.#tokenPayPal(),
        "Content-Type": "application/json",
      },
      body: JSON.stringify(corpo),
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) {
      const d = (t.details && t.details[0]) || {};
      throw new Error([t.message, d.description].filter(Boolean).join(" — ")
                      || ("PayPal ha risposto " + r.status));
    }
    return t;
  }

  async creaPayPal({ nome, descrizione, valuta = "EUR", livelli }) {
    const prod = await this.#paypal("/v1/catalogs/products", {
      name: nome, description: descrizione || nome, type: "SERVICE",
    });
    const fatti = [];
    for (const l of livelli) {
      const cad = CADENZE[l.cadenza || "unatantum"];
      if (cad === undefined) throw new Error("cadenza sconosciuta: " + l.cadenza);
      if (!cad) {
        // PayPal fa i piani solo per gli abbonamenti. Per il pagamento singolo
        // resta il PayPal.me, che non ha bisogno di API.
        fatti.push({ livello: l.nome || nome, prezzo: l.prezzo, valuta,
                     cadenza: "unatantum", url: null,
                     nota: "PayPal non fa link per il pagamento singolo: usa il tuo PayPal.me." });
        continue;
      }
      const piano = await this.#paypal("/v1/billing/plans", {
        product_id: prod.id,
        name: (l.nome || nome).slice(0, 127),
        billing_cycles: [{
          frequency: { interval_unit: cad.interval.toUpperCase(), interval_count: cad.conteggio },
          tenure_type: "REGULAR",
          sequence: 1,
          total_cycles: 0,                       // 0 = finche' non disdice
          pricing_scheme: { fixed_price: { value: Number(centesimi(l.prezzo) / 100).toFixed(2), currency_code: valuta } },
        }],
        payment_preferences: { auto_bill_outstanding: true, setup_fee_failure_action: "CONTINUE", payment_failure_threshold: 3 },
      });
      fatti.push({
        livello: l.nome || nome, prezzo: l.prezzo, valuta, cadenza: l.cadenza,
        url: "https://www.paypal.com/webapps/billing/plans/subscribe?plan_id=" + piano.id,
        idPiano: piano.id,
      });
    }
    return { fornitore: "paypal", prodotto: prod.id, nome, livelli: fatti };
  }

  /** Crea l'offerta dove si puo': quello che manca lo dice, non lo nasconde. */
  async crea({ nome, descrizione, valuta = "eur", livelli, dove = "tutti" }) {
    if (!String(nome || "").trim()) throw new Error("serve il nome del servizio");
    if (!Array.isArray(livelli) || !livelli.length) throw new Error("serve almeno un livello di prezzo");
    if (livelli.length > 10) throw new Error("troppi livelli: al massimo 10");

    // Ogni livello si controlla QUI, prima di dividersi fra i fornitori. Se il
    // controllo sta dentro ciascuno, una richiesta scritta male riesce su uno e
    // fallisce sull'altro: resta un prodotto a meta' su un conto vero.
    for (const l of livelli) {
      if (!String(l.nome || "").trim()) throw new Error("un livello e' senza nome");
      if (CADENZE[l.cadenza || "unatantum"] === undefined)
        throw new Error(`cadenza sconosciuta per «${l.nome}»: ${l.cadenza} `
                        + `(valgono: ${Object.keys(CADENZE).join(", ")})`);
      centesimi(l.prezzo);      // solleva da solo se il prezzo non va
    }

    const q = this.quali();
    const esiti = [], problemi = [];
    for (const [f, attivo, fn] of [
      ["stripe", q.stripe, () => this.creaStripe({ nome, descrizione, valuta, livelli })],
      ["paypal", q.paypal, () => this.creaPayPal({ nome, descrizione, valuta: valuta.toUpperCase(), livelli })],
    ]) {
      if (dove !== "tutti" && dove !== f) continue;
      if (!attivo) { problemi.push(`${f}: credenziali non in Cassaforte`); continue; }
      try { esiti.push(await fn()); }
      catch (e) { problemi.push(`${f}: ${e.message}`); }
    }
    if (!esiti.length) throw new Error(problemi.join(" | ") || "nessun fornitore configurato");
    return { ok: true, offerte: esiti, problemi };
  }
}
