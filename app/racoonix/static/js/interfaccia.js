"use strict";
// Aiuti comuni a tutte le pagine: occhio sulle password, pulsante "Copia", avvisi a comparsa.
(() => {
  const sprite = document.body.dataset.icone;
  // Testi tradotti: la pagina li porta come dati JSON, qui si leggono e basta
  const blocco = document.getElementById("testi");
  const testi = blocco ? JSON.parse(blocco.textContent) : {};
  const t = (chiave) => testi[chiave] || chiave;
  window.racoonixTesto = t;
  const conTesto = (nome, testo) => {
    const span = document.createElement("span");
    span.textContent = testo;
    return icona(nome) + span.outerHTML;
  };
  const icona = (nome) => `<svg class="icona" aria-hidden="true"><use href="${sprite}#${nome}"></use></svg>`;

  function occhi(radice) {
    radice.querySelectorAll('input[type="password"]:not([data-occhio])').forEach((campo) => {
      campo.dataset.occhio = "1";
      const involucro = document.createElement("span");
      involucro.className = "campo-password";
      campo.parentNode.insertBefore(involucro, campo);
      involucro.appendChild(campo);
      const bottone = document.createElement("button");
      bottone.type = "button";
      bottone.className = "occhio";
      bottone.setAttribute("aria-label", t("Mostra password"));
      bottone.innerHTML = icona("eye");
      bottone.addEventListener("click", () => {
        const nascosta = campo.type === "password";
        campo.type = nascosta ? "text" : "password";
        bottone.innerHTML = icona(nascosta ? "eye-off" : "eye");
        bottone.setAttribute("aria-label", nascosta ? t("Nascondi password") : t("Mostra password"));
      });
      involucro.appendChild(bottone);
    });
  }

  function copie(radice) {
    radice.querySelectorAll("pre:not([data-copia])").forEach((blocco) => {
      blocco.dataset.copia = "1";
      const involucro = document.createElement("div");
      involucro.className = "blocco-copia";
      blocco.parentNode.insertBefore(involucro, blocco);
      involucro.appendChild(blocco);
      const bottone = document.createElement("button");
      bottone.type = "button";
      bottone.className = "copia piccolo";
      const ripristina = () => { bottone.innerHTML = conTesto("copy", t("Copia")); };
      ripristina();
      bottone.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(blocco.textContent.trim());
          bottone.innerHTML = conTesto("check", t("Copiato"));
        } catch (e) {
          bottone.innerHTML = conTesto("copy", t("Non riuscito"));
        }
        setTimeout(ripristina, 1800);
      });
      involucro.appendChild(bottone);
    });
  }

  let contenitore = null;
  function contenitoreAvvisi() {
    if (!contenitore) {
      contenitore = document.createElement("div");
      contenitore.className = "avvisi";
      contenitore.setAttribute("role", "status");
      contenitore.setAttribute("aria-live", "polite");
      document.body.appendChild(contenitore);
    }
    return contenitore;
  }

  function avvisi(radice) {
    radice.querySelectorAll(".flash:not([data-avviso])").forEach((messaggio) => {
      messaggio.dataset.avviso = "1";
      const errore = messaggio.classList.contains("errore");
      const avviso = document.createElement("div");
      avviso.className = "avviso " + (errore ? "errore" : "ok");
      avviso.innerHTML = icona(errore ? "alert-triangle" : "circle-check");
      const testo = document.createElement("span");
      testo.textContent = messaggio.textContent.trim();
      const chiudi = document.createElement("button");
      chiudi.type = "button";
      chiudi.className = "chiudi";
      chiudi.setAttribute("aria-label", t("Chiudi avviso"));
      chiudi.textContent = "×";
      avviso.append(testo, chiudi);
      contenitoreAvvisi().appendChild(avviso);
      messaggio.remove();

      let timer;
      const togli = () => {
        clearTimeout(timer);
        avviso.classList.add("via");
        setTimeout(() => avviso.remove(), 250);
      };
      const avvia = () => { timer = setTimeout(togli, errore ? 9000 : 4500); };
      avviso.addEventListener("mouseenter", () => clearTimeout(timer));
      avviso.addEventListener("mouseleave", avvia);
      chiudi.addEventListener("click", togli);
      avvia();
    });
  }

  // Le liste con data-aggiorna (Cose da fare, Inventario, Ordini...) si ricaricano conservando filtri e riquadri
  // aperti. Mai mentre stai scrivendo, ne' con la scheda del browser in secondo piano.
  function aggiornaTutto() {
    if (!window.htmx || document.hidden) return;
    document.body.dispatchEvent(new CustomEvent("racoonix:aggiorna"));
    const attivo = document.activeElement;
    const scrivendo = attivo && ["INPUT", "SELECT", "TEXTAREA"].includes(attivo.tagName);
    document.querySelectorAll("[data-aggiorna]").forEach((contenitore) => {
      const modulo = contenitore.dataset.modulo && document.getElementById(contenitore.dataset.modulo);
      if (scrivendo && (contenitore.contains(attivo) || (modulo && modulo.contains(attivo)))) return;
      const modificato = [...contenitore.querySelectorAll("input, textarea, select")].some((c) =>
        c.type === "checkbox" || c.type === "radio" ? c.checked !== c.defaultChecked
          : c.tagName === "SELECT" ? [...c.options].some((o) => o.selected !== o.defaultSelected)
          : c.value !== c.defaultValue);
      if (modificato) return;
      let url = contenitore.dataset.aggiorna;
      if (modulo) url += "?" + new URLSearchParams(new FormData(modulo)).toString();
      const aperti = [...contenitore.querySelectorAll("details[open][id]")].map((d) => d.id);
      window.htmx.ajax("GET", url, { target: "#" + contenitore.id, swap: contenitore.dataset.swap || "outerHTML", select: contenitore.dataset.seleziona,
        headers: { "X-Racoonix-Auto": "1" } })
        .then(() => aperti.forEach((id) => { const d = document.getElementById(id); if (d) d.open = true; }));
    });
  }

  // Ogni 3 secondi una domanda leggerissima al server: "e' cambiato qualcosa?". Se si', si aggiorna subito.
  // Comunque, per sicurezza, un aggiornamento completo ogni minuto.
  let versione = null;
  async function controlla() {
    if (document.hidden || !document.querySelector(".contatore, [data-aggiorna]")) return;
    try {
      const risposta = await fetch("/stato/versione", { credentials: "same-origin", cache: "no-store", headers: { "X-Racoonix-Auto": "1" } });
      if (!risposta.ok || !(risposta.headers.get("Content-Type") || "").includes("json")) return;
      const { v } = await risposta.json();
      if (versione !== null && v !== versione) aggiornaTutto();
      versione = v;
    } catch (_errore) { /* rete assente per un attimo: si riprova al giro dopo */ }
  }
  setInterval(controlla, 3000);
  setInterval(aggiornaTutto, 60000);
  // Tornando sulla scheda del browser (o riaccendendo il telefono), controllo subito
  document.addEventListener("visibilitychange", () => { if (!document.hidden) controlla(); });

  const applica = (radice) => { occhi(radice); copie(radice); avvisi(radice); };
  document.addEventListener("DOMContentLoaded", () => applica(document));
  document.addEventListener("htmx:afterSettle", (evento) => applica(evento.target));
})();

// Calendario: si apre cliccando in qualunque punto del campo data, non solo sull'icona
document.addEventListener("click", (e) => {
  const campo = e.target.closest && e.target.closest('input[type="date"]');
  if (campo && typeof campo.showPicker === "function") {
    try { campo.showPicker(); } catch (_errore) { /* il browser non lo permette: resta l'icona */ }
  }
});

// Un doppio tocco su "Carica" o "Salva" non deve inviare il modulo due volte
document.addEventListener("submit", (e) => {
  const form = e.target;
  if (form.hasAttribute("hx-post") || form.hasAttribute("hx-get") || e.defaultPrevented) return;
  if (form.dataset.inviato === "1") { e.preventDefault(); return; }
  form.dataset.inviato = "1";
});
// Tornando indietro con il browser, i moduli si possono usare di nuovo
window.addEventListener("pageshow", () => {
  document.querySelectorAll("form[data-inviato]").forEach((f) => delete f.dataset.inviato);
});
