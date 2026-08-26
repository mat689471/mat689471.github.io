/**
 * account.mjs — «Accedi con Google», «Accedi con Outlook».
 *
 * Un account di posta non si collega con una chiave da incollare: si collega
 * accedendo, sulla pagina del fornitore, dove la password la scrivi a loro e
 * non passa mai da qui. Quello che torna indietro e' un permesso revocabile,
 * limitato a quello che gli abbiamo chiesto (leggere e mandare posta).
 *
 * Un account alla volta: se vuoi mandare dall'altro indirizzo esci e rientri.
 * I permessi restano cifrati in dati/, con la stessa chiave della Cassaforte,
 * e non finiscono mai nel repository.
 *
 * Il flusso e' OAuth 2.0 con PKCE: partiamo con una verifica segreta, il
 * fornitore ci rimanda un codice usa e getta, e solo chi conosce quel segreto
 * puo' trasformarlo in un permesso. Cosi' un codice intercettato non basta.
 */

import crypto from "node:crypto";
import { readFile, writeFile, mkdir, chmod } from "node:fs/promises";
import path from "node:path";

const ALG = "aes-256-gcm";

/** I fornitori che sappiamo gestire. Aggiungerne uno vuol dire aggiungere qui. */
export const FORNITORI = {
  google: {
    nome: "Google",
    posta: "Gmail",
    icona: "🅶",
    colore: "#ea4335",
    autorizza: "https://accounts.google.com/o/oauth2/v2/auth",
    token: "https://oauth2.googleapis.com/token",
    profilo: "https://www.googleapis.com/oauth2/v3/userinfo",
    campoEmail: "email",
    ambiti: [
      "openid", "email",
      "https://www.googleapis.com/auth/gmail.send",
      "https://www.googleapis.com/auth/gmail.readonly",
    ],
    // 'offline' e' cio' che fa arrivare il permesso duraturo; senza, l'accesso
    // scade in un'ora e bisognerebbe rifare il giro ogni volta.
    extraAutorizza: { access_type: "offline", prompt: "consent" },
    console: "https://console.cloud.google.com/apis/credentials",
    tipoApp: 'Applicazione desktop ("Desktop app")',
    nota: "Se il tuo progetto Google è «in test», aggiungi il tuo indirizzo fra gli utenti di prova, altrimenti l'accesso viene rifiutato.",
  },
  microsoft: {
    nome: "Microsoft",
    posta: "Outlook, Hotmail, Live",
    icona: "🅼",
    colore: "#0078d4",
    autorizza: "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
    token: "https://login.microsoftonline.com/common/oauth2/v2.0/token",
    profilo: "https://graph.microsoft.com/v1.0/me",
    campoEmail: "mail",
    campoEmailAlt: "userPrincipalName",
    ambiti: ["offline_access", "User.Read", "Mail.Send", "Mail.Read"],
    extraAutorizza: {},
    console: "https://entra.microsoft.com/#view/Microsoft_AAD_RegisteredApps",
    tipoApp: 'App desktop ("Mobile and desktop applications")',
  },
};

export class Account {
  constructor(dirDati) {
    this.dir = dirDati;
    this.file = path.join(dirDati, "account.enc");
    this.fileMaster = path.join(dirDati, ".masterkey");
    this.chiave = null;
    this.dati = { app: {}, attivo: null };   // app: credenziali; attivo: chi e' entrato
    this.inCorso = new Map();                // state -> {fornitore, verifier, nato}
    this.redirect = null;                    // lo sa solo il server, che conosce la porta
  }

  async init(redirect) {
    this.redirect = redirect;
    await mkdir(this.dir, { recursive: true });
    this.chiave = await this.#masterKey();
    try {
      const blob = JSON.parse(await readFile(this.file, "utf8"));
      this.dati = this.#decifra(blob);
    } catch { /* primo avvio */ }
    this.dati.app = this.dati.app || {};
    return this;
  }

  // ---- quello che vede la pagina ----------------------------------------
  vista() {
    const configurati = {};
    for (const id of Object.keys(FORNITORI)) configurati[id] = !!(this.dati.app[id]?.clientId);
    const a = this.dati.attivo;
    return {
      ok: true,
      redirect: this.redirect,
      fornitori: Object.entries(FORNITORI).map(([id, f]) => ({
        id, nome: f.nome, posta: f.posta, icona: f.icona, colore: f.colore,
        console: f.console, tipoApp: f.tipoApp, nota: f.nota || "",
        configurato: configurati[id],
      })),
      attivo: a ? { fornitore: a.fornitore, email: a.email, nome: FORNITORI[a.fornitore]?.nome,
                    entrato: a.entrato } : null,
    };
  }

  /** Le credenziali dell'app, quelle che crei una volta sola sulla console. */
  async configura(fornitore, clientId, clientSecret) {
    if (!FORNITORI[fornitore]) throw new Error("fornitore sconosciuto");
    if (!String(clientId || "").trim()) throw new Error("serve l'ID client");
    this.dati.app[fornitore] = {
      clientId: String(clientId).trim(),
      clientSecret: String(clientSecret || "").trim(),
    };
    await this.#salva();
    return { ok: true };
  }

  // ---- il giro di accesso ------------------------------------------------
  /** L'indirizzo della pagina di accesso del fornitore. */
  urlAccesso(fornitore) {
    const f = FORNITORI[fornitore];
    if (!f) throw new Error("fornitore sconosciuto");
    const app = this.dati.app[fornitore];
    if (!app?.clientId) throw new Error("prima inserisci l'ID client di " + f.nome);

    const verifier = crypto.randomBytes(32).toString("base64url");
    const challenge = crypto.createHash("sha256").update(verifier).digest("base64url");
    const state = crypto.randomBytes(16).toString("base64url");
    this.#pulisciScaduti();
    this.inCorso.set(state, { fornitore, verifier, nato: Date.now() });

    const p = new URLSearchParams({
      client_id: app.clientId,
      redirect_uri: this.redirect,
      response_type: "code",
      scope: f.ambiti.join(" "),
      state,
      code_challenge: challenge,
      code_challenge_method: "S256",
      ...f.extraAutorizza,
    });
    return f.autorizza + "?" + p.toString();
  }

  /** Il fornitore ci rimanda qui con un codice: lo trasformiamo in permesso. */
  async completa(code, state) {
    this.#pulisciScaduti();
    const attesa = this.inCorso.get(state);
    // Lo 'state' lega la risposta alla richiesta che abbiamo fatto noi: senza
    // questo controllo un indirizzo confezionato da altri potrebbe collegare
    // un account che non hai scelto tu.
    if (!attesa) throw new Error("richiesta scaduta o non riconosciuta: riprova dall'inizio");
    this.inCorso.delete(state);

    const f = FORNITORI[attesa.fornitore];
    const app = this.dati.app[attesa.fornitore];
    const corpo = new URLSearchParams({
      client_id: app.clientId,
      code,
      code_verifier: attesa.verifier,
      grant_type: "authorization_code",
      redirect_uri: this.redirect,
    });
    if (app.clientSecret) corpo.set("client_secret", app.clientSecret);

    const t = await this.#postaForm(f.token, corpo);
    if (!t.refresh_token && !t.access_token) throw new Error("il fornitore non ha dato nessun permesso");

    const email = await this.#email(f, t.access_token);
    this.dati.attivo = {
      fornitore: attesa.fornitore,
      email,
      refresh: t.refresh_token || null,
      access: t.access_token || null,
      scade: Date.now() + (Number(t.expires_in) || 3600) * 1000,
      entrato: new Date().toISOString(),
    };
    await this.#salva();
    return { ok: true, email, fornitore: attesa.fornitore };
  }

  async esci() {
    this.dati.attivo = null;
    await this.#salva();
    return { ok: true };
  }

  /** Un accesso valido adesso: se e' scaduto lo rinnova da solo. */
  async accessoValido() {
    const a = this.dati.attivo;
    if (!a) throw new Error("nessun account collegato: entra dal Quartier Generale");
    if (a.access && Date.now() < a.scade - 60000) return a;   // un minuto di margine
    if (!a.refresh) throw new Error("l'accesso e' scaduto: esci e rientra");

    const f = FORNITORI[a.fornitore];
    const app = this.dati.app[a.fornitore];
    const corpo = new URLSearchParams({
      client_id: app.clientId,
      refresh_token: a.refresh,
      grant_type: "refresh_token",
    });
    if (app.clientSecret) corpo.set("client_secret", app.clientSecret);
    if (a.fornitore === "microsoft") corpo.set("scope", f.ambiti.join(" "));

    const t = await this.#postaForm(f.token, corpo);
    a.access = t.access_token;
    a.scade = Date.now() + (Number(t.expires_in) || 3600) * 1000;
    if (t.refresh_token) a.refresh = t.refresh_token;   // alcuni lo ruotano
    await this.#salva();
    return a;
  }

  // ---- mandare una mail --------------------------------------------------
  async manda({ a, oggetto, testo }) {
    const dest = String(a || "").trim();
    if (!dest) throw new Error("manca il destinatario");
    const acc = await this.accessoValido();
    return acc.fornitore === "google"
      ? this.#mandaGoogle(acc, dest, oggetto || "", testo || "")
      : this.#mandaMicrosoft(acc, dest, oggetto || "", testo || "");
  }

  async #mandaGoogle(acc, dest, oggetto, testo) {
    // Gmail vuole il messaggio grezzo in formato RFC 822. L'oggetto va
    // codificato: senza, accenti e emoji arrivano storti.
    const sogg = "=?UTF-8?B?" + Buffer.from(oggetto, "utf8").toString("base64") + "?=";
    const grezzo = [
      "To: " + dest,
      "From: " + acc.email,
      "Subject: " + sogg,
      "MIME-Version: 1.0",
      'Content-Type: text/plain; charset="UTF-8"',
      "Content-Transfer-Encoding: base64",
      "",
      Buffer.from(testo, "utf8").toString("base64"),
    ].join("\r\n");
    const r = await this.#postaJson(
      "https://gmail.googleapis.com/gmail/v1/users/me/messages/send",
      { raw: Buffer.from(grezzo, "utf8").toString("base64url") }, acc.access);
    return { ok: true, id: r.id, da: acc.email, a: dest };
  }

  async #mandaMicrosoft(acc, dest, oggetto, testo) {
    await this.#postaJson("https://graph.microsoft.com/v1.0/me/sendMail", {
      message: {
        subject: oggetto,
        body: { contentType: "Text", content: testo },
        toRecipients: [{ emailAddress: { address: dest } }],
      },
      saveToSentItems: true,
    }, acc.access);
    return { ok: true, da: acc.email, a: dest };
  }

  // ---- utilita' ----------------------------------------------------------
  async #email(f, access) {
    try {
      const p = await this.#prendiJson(f.profilo, access);
      return p[f.campoEmail] || p[f.campoEmailAlt] || "(indirizzo non leggibile)";
    } catch { return "(indirizzo non leggibile)"; }
  }

  async #postaForm(url, corpo) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/x-www-form-urlencoded" },
      body: corpo.toString(),
    });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(this.#spiega(t, r.status));
    return t;
  }

  async #postaJson(url, corpo, access) {
    const r = await fetch(url, {
      method: "POST",
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + access },
      body: JSON.stringify(corpo),
    });
    if (r.status === 202 || r.status === 204) return {};
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(this.#spiega(t, r.status));
    return t;
  }

  async #prendiJson(url, access) {
    const r = await fetch(url, { headers: { Authorization: "Bearer " + access } });
    const t = await r.json().catch(() => ({}));
    if (!r.ok) throw new Error(this.#spiega(t, r.status));
    return t;
  }

  /** Gli errori dei fornitori sono criptici: qui diventano leggibili. */
  #spiega(t, stato) {
    const codice = t.error?.code || t.error || "";
    const desc = t.error_description || t.error?.message || "";
    if (codice === "invalid_grant")
      return "il permesso non vale piu' (revocato, o scaduto per inattivita'): esci e rientra";
    if (codice === "redirect_uri_mismatch")
      return "l'indirizzo di ritorno non coincide con quello registrato sulla console del fornitore";
    if (codice === "invalid_client")
      return "ID client o segreto sbagliati: ricontrollali sulla console del fornitore";
    if (stato === 403 && /insufficient|scope/i.test(String(desc)))
      return "permessi insufficienti: esci e rientra accettando tutte le richieste";
    return [codice, desc].filter(Boolean).join(" - ") || ("errore HTTP " + stato);
  }

  #pulisciScaduti() {
    const limite = Date.now() - 10 * 60 * 1000;   // dieci minuti per fare l'accesso
    for (const [s, v] of this.inCorso) if (v.nato < limite) this.inCorso.delete(s);
  }

  async #masterKey() {
    try {
      return Buffer.from(await readFile(this.fileMaster, "utf8"), "base64");
    } catch {
      const k = crypto.randomBytes(32);
      await mkdir(this.dir, { recursive: true });
      await writeFile(this.fileMaster, k.toString("base64"), "utf8");
      try { await chmod(this.fileMaster, 0o600); } catch { /* non su Windows */ }
      return k;
    }
  }

  #decifra(blob) {
    const d = crypto.createDecipheriv(ALG, this.chiave, Buffer.from(blob.iv, "base64"));
    d.setAuthTag(Buffer.from(blob.tag, "base64"));
    return JSON.parse(Buffer.concat([d.update(Buffer.from(blob.dati, "base64")), d.final()]).toString("utf8"));
  }

  async #salva() {
    const iv = crypto.randomBytes(12);
    const c = crypto.createCipheriv(ALG, this.chiave, iv);
    const dati = Buffer.concat([c.update(JSON.stringify(this.dati), "utf8"), c.final()]);
    await writeFile(this.file, JSON.stringify({
      versione: 1, iv: iv.toString("base64"), tag: c.getAuthTag().toString("base64"),
      dati: dati.toString("base64"),
      _avviso: "Permessi di accesso alla tua posta, cifrati. Non condividerlo.",
    }, null, 2), "utf8");
    try { await chmod(this.file, 0o600); } catch { /* non su Windows */ }
  }
}
