"use strict";
// Aiuti comuni a tutte le pagine: occhio sulle password, pulsante "Copia", avvisi a comparsa.
(() => {
  const sprite = document.body.dataset.icone;
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
      bottone.setAttribute("aria-label", "Mostra password");
      bottone.innerHTML = icona("eye");
      bottone.addEventListener("click", () => {
        const nascosta = campo.type === "password";
        campo.type = nascosta ? "text" : "password";
        bottone.innerHTML = icona(nascosta ? "eye-off" : "eye");
        bottone.setAttribute("aria-label", nascosta ? "Nascondi password" : "Mostra password");
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
      const ripristina = () => { bottone.innerHTML = icona("copy") + "<span>Copia</span>"; };
      ripristina();
      bottone.addEventListener("click", async () => {
        try {
          await navigator.clipboard.writeText(blocco.textContent.trim());
          bottone.innerHTML = icona("check") + "<span>Copiato</span>";
        } catch (e) {
          bottone.innerHTML = icona("copy") + "<span>Non riuscito</span>";
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
      chiudi.setAttribute("aria-label", "Chiudi avviso");
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

  // Le liste con data-aggiorna (Cose da fare, Utenti) si ricaricano ogni 20 secondi, conservando i filtri
  // e i riquadri aperti. Mai mentre stai scrivendo, ne' con la scheda del browser in secondo piano.
  setInterval(() => {
    if (!window.htmx || document.hidden) return;
    const attivo = document.activeElement;
    const scrivendo = attivo && ["INPUT", "SELECT", "TEXTAREA"].includes(attivo.tagName);
    document.querySelectorAll("[data-aggiorna]").forEach((contenitore) => {
      const modulo = contenitore.dataset.modulo && document.getElementById(contenitore.dataset.modulo);
      if (scrivendo && (contenitore.contains(attivo) || (modulo && modulo.contains(attivo)))) return;
      let url = contenitore.dataset.aggiorna;
      if (modulo) url += "?" + new URLSearchParams(new FormData(modulo)).toString();
      const aperti = [...contenitore.querySelectorAll("details[open][id]")].map((d) => d.id);
      window.htmx.ajax("GET", url, { target: "#" + contenitore.id, swap: contenitore.dataset.swap || "outerHTML" })
        .then(() => aperti.forEach((id) => { const d = document.getElementById(id); if (d) d.open = true; }));
    });
  }, 20000);

  const applica = (radice) => { occhi(radice); copie(radice); avvisi(radice); };
  document.addEventListener("DOMContentLoaded", () => applica(document));
  document.addEventListener("htmx:afterSettle", (evento) => applica(evento.target));
})();
