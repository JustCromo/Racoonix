"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const lib = window.__Html5QrcodeLibrary__ || window;
  const { Html5Qrcode, Html5QrcodeSupportedFormats: F } = lib;
  const modulo = document.getElementById("modulo-codice");
  const campo = document.getElementById("codice");
  const pulsante = document.getElementById("avvia");
  const scanner = new Html5Qrcode("lettore", {
    verbose: false,
    formatsToSupport: [F.EAN_13, F.EAN_8, F.UPC_A, F.CODE_128, F.DATA_MATRIX, F.QR_CODE],
    experimentalFeatures: { useBarCodeDetectorIfSupported: true },
  });
  let attivo = false;

  modulo.addEventListener("htmx:afterRequest", () => {
    campo.value = "";
    campo.focus();
  });

  async function ferma(testo) {
    if (!attivo) return;
    await scanner.stop();
    attivo = false;
    pulsante.textContent = testo;
  }

  pulsante.addEventListener("click", async () => {
    if (attivo) { await ferma("Usa fotocamera"); return; }
    try {
      await scanner.start({ facingMode: "environment" }, { fps: 10 }, async (testo) => {
        await ferma("Leggi un altro prodotto");
        campo.value = testo;
        modulo.requestSubmit();
      }, () => {});
      attivo = true;
      pulsante.textContent = "Ferma fotocamera";
    } catch (e) {
      pulsante.textContent = "Fotocamera non disponibile";
    }
  });
});
