"use strict";
// Piccoli aiuti comuni a tutte le pagine: occhio sulle password e pulsante "Copia".
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

  const applica = (radice) => { occhi(radice); copie(radice); };
  document.addEventListener("DOMContentLoaded", () => applica(document));
  document.addEventListener("htmx:afterSettle", (evento) => applica(evento.target));
})();
