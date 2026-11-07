"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const lib = window.__Html5QrcodeLibrary__ || window;
  const { Html5Qrcode, Html5QrcodeSupportedFormats } = lib;
  const tokenCsrf = document.querySelector('meta[name="csrf-token"]').content;
  const pulsante = document.getElementById("avvia");
  const risultato = document.getElementById("risultato");
  const modulo = document.getElementById("manuale");
  const campo = document.getElementById("codice");
  const scanner = new Html5Qrcode("lettore", {
    verbose: false,
    formatsToSupport: [
      Html5QrcodeSupportedFormats.DATA_MATRIX,
      Html5QrcodeSupportedFormats.EAN_13,
      Html5QrcodeSupportedFormats.EAN_8,
      Html5QrcodeSupportedFormats.UPC_A,
      Html5QrcodeSupportedFormats.QR_CODE,
    ],
    experimentalFeatures: { useBarCodeDetectorIfSupported: true },
  });
  let attivo = false;

  const mostra = (oggetto) => { risultato.textContent = JSON.stringify(oggetto, null, 2); };

  async function analizza(codice) {
    mostra({ letto: codice });
    try {
      const risposta = await fetch("/test-scanner/analizza", {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": tokenCsrf },
        body: JSON.stringify({ codice }),
      });
      mostra({ letto: codice, server: await risposta.json() });
    } catch (e) {
      mostra({ letto: codice, errore: "Server non raggiungibile o sessione scaduta" });
    }
  }

  async function ferma() {
    if (!attivo) return;
    await scanner.stop();
    attivo = false;
    pulsante.textContent = "Avvia webcam";
  }

  pulsante.addEventListener("click", async () => {
    if (attivo) { await ferma(); return; }
    try {
      await scanner.start({ facingMode: "environment" }, { fps: 10 },
        async (testo) => { await ferma(); analizza(testo); }, () => {});
      attivo = true;
      pulsante.textContent = "Ferma webcam";
    } catch (e) {
      mostra({ errore: "Webcam non disponibile: " + e });
    }
  });

  modulo.addEventListener("submit", (ev) => { ev.preventDefault(); analizza(campo.value); });
});
