"use strict";
// Menu a tendina con ricerca, a tema Racoonix. Parte da un <select data-tendina> normale:
// senza JavaScript resta il menu del browser, con JavaScript diventa questo. Il valore inviato
// e' sempre quello del <select> (nascosto), che il server continua a controllare.
(() => {
  const t = (testo) => (window.racoonixTesto ? window.racoonixTesto(testo) : testo);
  const semplice = (s) => s.normalize("NFD").replace(/[\u0300-\u036f]/g, "").toLowerCase();
  let contatore = 0;

  function tendina(select) {
    contatore += 1;
    const id = `tendina-${contatore}`;
    const box = document.createElement("div");
    box.className = "tendina";

    const bottone = document.createElement("button");
    bottone.type = "button";
    bottone.className = "tendina-bottone";
    bottone.setAttribute("aria-haspopup", "listbox");
    bottone.setAttribute("aria-expanded", "false");

    const pannello = document.createElement("div");
    pannello.className = "tendina-pannello";
    pannello.hidden = true;

    const cerca = document.createElement("input");
    cerca.type = "search";
    cerca.className = "tendina-cerca";
    cerca.autocomplete = "off";
    cerca.spellcheck = false;
    cerca.placeholder = t("Cerca una citta'...");
    cerca.setAttribute("aria-controls", id);

    const elenco = document.createElement("ul");
    elenco.className = "tendina-elenco";
    elenco.id = id;
    elenco.setAttribute("role", "listbox");

    const vuoto = document.createElement("li");
    vuoto.className = "tendina-vuoto";
    vuoto.textContent = t("Nessun risultato");
    vuoto.hidden = true;

    // Le voci si creano con textContent: nessun testo diventa mai HTML
    const voci = [];
    const gruppi = [];
    const aggiungi = (opzione, gruppo) => {
      const voce = document.createElement("li");
      voce.className = "tendina-voce";
      voce.setAttribute("role", "option");
      voce.dataset.valore = opzione.value;
      voce.textContent = opzione.textContent;
      voce.dataset.cerca = semplice(`${opzione.textContent} ${opzione.value}`);
      elenco.appendChild(voce);
      voci.push({ voce, gruppo });
    };
    [...select.children].forEach((figlio) => {
      if (figlio.tagName === "OPTGROUP") {
        const titolo = document.createElement("li");
        titolo.className = "tendina-gruppo";
        titolo.setAttribute("role", "presentation");
        titolo.textContent = figlio.label;
        elenco.appendChild(titolo);
        gruppi.push(titolo);
        [...figlio.children].forEach((opzione) => aggiungi(opzione, titolo));
      } else if (figlio.tagName === "OPTION") {
        aggiungi(figlio, null);
      }
    });
    elenco.appendChild(vuoto);

    select.hidden = true;
    select.tabIndex = -1;
    select.after(box);
    box.append(bottone, pannello);
    pannello.append(cerca, elenco);

    let attiva = null;
    const visibili = () => voci.filter((v) => !v.voce.hidden).map((v) => v.voce);
    const evidenzia = (voce) => {
      if (attiva) attiva.classList.remove("attiva");
      attiva = voce;
      if (voce) {
        voce.classList.add("attiva");
        voce.scrollIntoView({ block: "nearest" });
      }
    };
    const aggiornaBottone = () => {
      const scelta = select.options[select.selectedIndex];
      bottone.textContent = scelta ? scelta.textContent : "";
      voci.forEach(({ voce }) => voce.setAttribute("aria-selected", String(scelta && voce.dataset.valore === scelta.value)));
    };
    const filtra = (testo) => {
      const q = semplice(testo.trim());
      voci.forEach(({ voce }) => { voce.hidden = q !== "" && !voce.dataset.cerca.includes(q); });
      gruppi.forEach((g) => { g.hidden = !voci.some((v) => v.gruppo === g && !v.voce.hidden); });
      const prime = visibili();
      vuoto.hidden = prime.length > 0;
      evidenzia(q ? prime[0] || null : null);
    };
    const apri = () => {
      pannello.hidden = false;
      bottone.setAttribute("aria-expanded", "true");
      cerca.value = "";
      filtra("");
      const scelta = voci.find(({ voce }) => voce.dataset.valore === select.value);
      if (scelta) evidenzia(scelta.voce);
      cerca.focus();
    };
    const chiudi = (rimettiFuoco) => {
      pannello.hidden = true;
      bottone.setAttribute("aria-expanded", "false");
      if (rimettiFuoco) bottone.focus();
    };
    const scegli = (voce) => {
      select.value = voce.dataset.valore;
      select.dispatchEvent(new Event("change", { bubbles: true }));
      aggiornaBottone();
      chiudi(true);
    };

    bottone.addEventListener("click", () => (pannello.hidden ? apri() : chiudi(true)));
    bottone.addEventListener("keydown", (e) => {
      if (e.key === "ArrowDown" || e.key === "Enter" || e.key === " ") { e.preventDefault(); apri(); }
    });
    cerca.addEventListener("input", () => filtra(cerca.value));
    cerca.addEventListener("keydown", (e) => {
      const elencoVisibile = visibili();
      const i = elencoVisibile.indexOf(attiva);
      if (e.key === "ArrowDown") { e.preventDefault(); evidenzia(elencoVisibile[Math.min(i + 1, elencoVisibile.length - 1)] || null); }
      else if (e.key === "ArrowUp") { e.preventDefault(); evidenzia(elencoVisibile[Math.max(i - 1, 0)] || null); }
      else if (e.key === "Enter") { e.preventDefault(); if (attiva) scegli(attiva); }
      else if (e.key === "Escape") { e.preventDefault(); chiudi(true); }
      else if (e.key === "Tab") { chiudi(false); }
    });
    elenco.addEventListener("click", (e) => {
      const voce = e.target.closest(".tendina-voce");
      if (voce) scegli(voce);
    });
    elenco.addEventListener("mousemove", (e) => {
      const voce = e.target.closest(".tendina-voce");
      if (voce && voce !== attiva) {
        if (attiva) attiva.classList.remove("attiva");
        attiva = voce;
        voce.classList.add("attiva");
      }
    });
    document.addEventListener("click", (e) => { if (!box.contains(e.target)) chiudi(false); });
    aggiornaBottone();
  }

  document.addEventListener("DOMContentLoaded", () => {
    document.querySelectorAll("select[data-tendina]").forEach(tendina);
  });
})();
