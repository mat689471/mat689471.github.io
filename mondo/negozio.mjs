/**
 * negozio.mjs — Il negozio Etsy e la stampa su richiesta, dentro il mondo.
 *
 * Una stanza del mondo e' un'azienda vera: ci lavora una squadra fissa, e per
 * lavorare le serve sapere come va il negozio. Questo modulo e' l'unico punto
 * che parla con Etsy e Printify, e restituisce una fotografia: cosa si e'
 * venduto, quanto si e' incassato, cosa guarda la gente e cosa no.
 *
 * Due modi di collegarsi, diversi perche' diversi sono i due servizi:
 *   - Printify: un token personale, si incolla in Cassaforte e basta.
 *   - Etsy: accesso con OAuth, come Google. Serve registrare un'app sul loro
 *     sito, perche' Etsy vuole sapere chi sta chiedendo i dati.
 *
 * Una cosa che le API di Etsy NON danno: le visite al negozio e il tasso di
 * conversione. Quelli restano nel pannello di Etsy. Qui si mostra cio' che
 * esiste davvero - visualizzazioni e preferiti per inserzione - invece di
 * inventare un numero che sembra giusto.
 */

import crypto from "node:crypto";
import { readFile, writeFile, mkdir, chmod } from "node:fs/promises";
import path from "node:path";

const ALG = "aes-256-gcm";
const ETSY = {
  autorizza: "https://www.etsy.com/oauth/connect",
  token: "https://api.etsy.com/v3/public/oauth/token",
  api: "https://openapi.etsy.com/v3/application",
  ambiti: ["shops_r", "listings_r", "transactions_r", "email_r"],
  console: "https://www.etsy.com/developers/your-apps",
};
const PRINTIFY = "https://api.printify.com/v1";

/** Etsy manda gli importi come {amount, divisor}: 1250/100 = 12,50. */
function soldi(m) {
  if (!m || typeof m.amount !== "number") return 0;
  return m.amount / (m.divisor || 100);
}

export class Negozio {
  constructor(dirDati, leggiChiave) {
    this.dir = dirDati;
    this.file = path.join(dirDati, "negozio.enc");
    this.fileMaster = path.join(dirDati, ".masterkey");
    this.chiave = leggiChiave;          // per il token Printify, dalla Cassaforte
    this.cifra = null;
    this.dati = { app: {}, etsy: null };
    this.inCorso = new Map();
    this.redirect = null;
    this.cache = null;                  // ultima fotografia, con l'ora
  }

  async init(redirect) {
    this.redirect = redirect;
    await mkdir(this.dir, { recursive: true });
    this.cifra = await this.#masterKey();
    try { this.dati = this.#decifra(JSON.parse(await readFile(this.file, "utf8"))); }
    catch { /* primo avvio */ }
    this.dati.app = this.dati.app || {};
    return this;
  }

  // ---- cosa vede la pagina ----------------------------------------------
  vista() {
    const e = this.dati.etsy;
    return {
      ok: true,
      redirect: this.redirect,
      etsy: {
        configurato: !!this.dati.app.keystring,
        collegato: !!e,
        negozio: e ? { nome: e.nomeNegozio, id: e.shopId, utente: e.email } : null,
        console: ETSY.console,
      },
      printify: { collegato: !!this.chiave("PRINTIFY_API_TOKEN") },
      ultimaFoto: this.cache ? this.cache.quando : null,
    };
  }

  async configura(keystring, sharedSecret) {
    if (!String(keystring || "").trim()) throw new Error("serve la Keystring dell'app Etsy");
    this.dati.app = { keystring: String(keystring).trim(),
                      secret: String(sharedSecret || "").trim() };
    await this.#salva();
    return { ok: true };
  }

  // ---- accesso a Etsy ----------------------------------------------------
  urlAccesso() {
    const app = this.dati.app;
    if (!app.keystring) throw new Error("prima inserisci la Keystring dell'app Etsy");
    const verifier = crypto.randomBytes(32).toString("base64url");
    const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    const state = crypto.randomBytes(16).toString("base64url");
    this.#pulisci();
    this.inCorso.set(state, { verifier, nato: Date.now() });
    const p = new URLSearchParams({
      response_type: "code",
      client_id: app.keystring,
      redirect_uri: this.redirect,
      scope: ETSY.ambiti.join(" "),
      state,
      code_challenge: challenge,
      code_challenge_method: "S256",
    });
    return ETSY.autorizza + "?" + p.toString();
  }

  async completa(code, state) {
    this.#pulisci();
    const attesa = this.inCorso.get(state);
    if (!attesa) throw new Error("richiesta scaduta o non riconosciuta: riprova dall'inizio");
    this.inCorso.delete(state);

    const t = await this.#postaForm(ETSY.token, {
      grant_type: "authorization_code",
      client_id: this.dati.app.keystring,
      redirect_uri: this.redirect,
      code,
      code_verifier: attesa.verifier,
    });
    this.dati.etsy = {
      access: t.access_token, refresh: t.refresh_token,
      scade: Date.now() + (Number(t.expires_in) || 3600) * 1000,
      collegato: new Date().toISOString(),
    };
    await this.#identifica();
    await this.#salva();
    return { ok: true, negozio: this.dati.etsy.nomeNegozio };
  }

  async esci() {
    this.dati.etsy = null; this.cache = null;
    await this.#salva();
    return { ok: true };
  }

  /** Chi siamo e quale negozio: si chiede una volta, poi resta scritto. */
  async #identifica() {
    const me = await this.#etsy("/users/me");
    const e = this.dati.etsy;
    e.userId = me.user_id;
    e.shopId = me.shop_id;
    if (!e.shopId) throw new Error("questo account Etsy non ha un negozio");
    const s = await this.#etsy(`/shops/${e.shopId}`);
    e.nomeNegozio = s.shop_name;
    e.valuta = s.currency_code || "EUR";
  }

  async #accessoValido() {
    const e = this.dati.etsy;
    if (!e) throw new Error("negozio Etsy non collegato: entra dal Quartier Generale");
    if (e.access && Date.now() < e.scade - 60000) return e;
    if (!e.refresh) throw new Error("l'accesso e' scaduto: esci e rientra");
    const t = await this.#postaForm(ETSY.token, {
      grant_type: "refresh_token",
      client_id: this.dati.app.keystring,
      refresh_token: e.refresh,
    });
    e.access = t.access_token;
    e.scade = Date.now() + (Number(t.expires_in) || 3600) * 1000;
    if (t.refresh_token) e.refresh = t.refresh_token;
    await this.#salva();
    return e;
  }

  // ---- la fotografia del negozio ----------------------------------------
  /**
   * Ordini, incasso, inserzioni e attenzione ricevuta. 'giorni' limita gli
   * ordini considerati: 30 e' il respiro giusto per capire come sta andando.
   */
  async fotografia({ giorni = 30, forza = false } = {}) {
    // Una fotografia vale qualche minuto: le API hanno limiti, e la squadra del
    // negozio la chiede spesso. Ma vale solo per LO STESSO periodo: senza questo
    // controllo, chiedere 7 giorni restituiva la fotografia di 30 gia' in cache.
    if (!forza && this.cache && this.cache._giorni === giorni
        && Date.now() - this.cache._t < 5 * 60 * 1000)
      return this.cache;

    const foto = { quando: new Date().toISOString(), _t: Date.now(), _giorni: giorni,
                   etsy: null, printify: null, problemi: [] };

    try { foto.etsy = await this.#fotoEtsy(giorni); }
    catch (e) { foto.problemi.push("Etsy: " + e.message); }

    try { foto.printify = await this.#fotoPrintify(); }
    catch (e) { foto.problemi.push("Printify: " + e.message); }

    this.cache = foto;
    return foto;
  }

  async #fotoEtsy(giorni) {
    const e = await this.#accessoValido();
    const da = Math.floor((Date.now() - giorni * 86400000) / 1000);

    const ric = await this.#etsy(`/shops/${e.shopId}/receipts`,
      { limit: 100, min_created: da, was_paid: "true" });
    const ordini = ric.results || [];
    const incasso = ordini.reduce((s, o) => s + soldi(o.grandtotal), 0);
    const pezzi = ordini.reduce((s, o) => s + (o.transactions || []).length, 0);

    const att = await this.#etsy(`/shops/${e.shopId}/listings/active`,
      { limit: 100, sort_on: "score" });
    const inserzioni = (att.results || []).map(l => ({
      id: l.listing_id, titolo: l.title,
      prezzo: soldi(l.price), valuta: l.price?.currency_code || e.valuta,
      viste: l.views || 0, preferiti: l.num_favorers || 0,
      quantita: l.quantity || 0,
    }));
    const viste = inserzioni.reduce((s, l) => s + l.viste, 0);
    const preferiti = inserzioni.reduce((s, l) => s + l.preferiti, 0);

    // giorno per giorno, per il grafico
    const perGiorno = new Map();
    for (let i = giorni - 1; i >= 0; i--) {
      const d = new Date(Date.now() - i * 86400000).toISOString().slice(0, 10);
      perGiorno.set(d, { giorno: d, ordini: 0, incasso: 0 });
    }
    for (const o of ordini) {
      const d = new Date((o.created_timestamp || 0) * 1000).toISOString().slice(0, 10);
      const v = perGiorno.get(d);
      if (v) { v.ordini++; v.incasso += soldi(o.grandtotal); }
    }

    return {
      negozio: e.nomeNegozio, valuta: e.valuta, giorni,
      ordini: ordini.length, pezzi, incasso: Math.round(incasso * 100) / 100,
      scontrinoMedio: ordini.length ? Math.round(incasso / ordini.length * 100) / 100 : 0,
      inserzioniAttive: inserzioni.length, viste, preferiti,
      // Le viste sono TOTALI dalla pubblicazione, non del periodo: Etsy non
      // scompone il dato, e spacciarlo per traffico recente sarebbe falso.
      vistePeriodo: false,
      migliori: [...inserzioni].sort((a, b) => b.viste - a.viste).slice(0, 5),
      ferme: inserzioni.filter(l => l.viste < 10).slice(0, 5),
      serie: [...perGiorno.values()],
    };
  }

  async #fotoPrintify() {
    const tok = this.chiave("PRINTIFY_API_TOKEN");
    if (!tok) throw new Error("manca PRINTIFY_API_TOKEN in Cassaforte");
    const negozi = await this.#printify("/shops.json", tok);
    if (!negozi.length) return { negozi: 0, prodotti: 0, inLavorazione: 0 };
    const n = negozi[0];
    const prod = await this.#printify(`/shops/${n.id}/products.json?limit=50`, tok);
    const ord = await this.#printify(`/shops/${n.id}/orders.json?limit=50`, tok);
    const righe = ord.data || [];
    return {
      negozio: n.title, canale: n.channel, negozi: negozi.length,
      prodotti: (prod.data || []).length,
      ordini: righe.length,
      inLavorazione: righe.filter(o => !["fulfilled", "canceled"].includes(o.status)).length,
    };
  }

  // ---- chiamate ----------------------------------------------------------
  async #etsy(percorso, parametri) {
    const e = this.dati.etsy;
    const url = ETSY.api + percorso + (parametri ? "?" + new URLSearchParams(parametri) : "");
    const r = await fetch(url, {
      headers: { Authorization: "Bearer " + e.access, "x-api-key": this.dati.app.keystring },
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(this.#spiega(t, r.status));
    return t;
  }

  async #printify(percorso, token) {
    const r = await fetch(PRINTIFY + percorso, {
      headers: { Authorization: "Bearer " + token, "Content-Type": "application/json" },
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(t.error || t.message || ("Printify ha risposto " + r.status));
    return t;
  }

  async #postaForm(url, corpo) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: new URLSearchParams(corpo).toString(),
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(this.#spiega(t, r.status));
    return t;
  }

  #spiega(t, stato) {
    const e = t.error || t.error_description || t.message || "";
    if (/invalid_grant/i.test(e)) return "il permesso non vale piu': esci e rientra";
    if (stato === 401) return "Etsy non accetta l'accesso: esci e rientra";
    if (stato === 403) return "permessi insufficienti: rientra accettando tutte le richieste";
    if (stato === 429) return "troppe richieste in poco tempo: riprova fra qualche minuto";
    return String(e || "Etsy ha risposto " + stato);
  }

  // ---- deposito cifrato --------------------------------------------------
  #pulisci() {
    const limite = Date.now() - 10 * 60 * 1000;
    for (const [s, v] of this.inCorso) if (v.nato < limite) this.inCorso.delete(s);
  }
  async #masterKey() {
    try { return Buffer.from((await readFile(this.fileMaster, "utf8")).trim(), "base64"); }
    catch {
      const k = crypto.randomBytes(32);
      await mkdir(this.dir, { recursive: true });
      await writeFile(this.fileMaster, k.toString("base64"), "utf8");
      try { await chmod(this.fileMaster, 0o600); } catch { /* non su Windows */ }
      return k;
    }
  }
  #decifra(blob) {
    const d = crypto.createDecipheriv(ALG, this.cifra, Buffer.from(blob.iv, "base64"));
    d.setAuthTag(Buffer.from(blob.tag, "base64"));
    return JSON.parse(Buffer.concat([d.update(Buffer.from(blob.dati, "base64")), d.final()]).toString("utf8"));
  }
  async #salva() {
    const iv = crypto.randomBytes(12);
    const c = crypto.createCipheriv(ALG, this.cifra, iv);
    const dati = Buffer.concat([c.update(JSON.stringify(this.dati), "utf8"), c.final()]);
    await writeFile(this.file, JSON.stringify({
      versione: 1, iv: iv.toString("base64"), tag: c.getAuthTag().toString("base64"),
      dati: dati.toString("base64"),
      _avviso: "Accesso al tuo negozio Etsy, cifrato. Non condividerlo.",
    }, null, 2), "utf8");
    try { await chmod(this.file, 0o600); } catch { /* non su Windows */ }
  }
}
