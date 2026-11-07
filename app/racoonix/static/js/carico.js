"use strict";
document.addEventListener("DOMContentLoaded", () => {
  const lib = window.__Html5QrcodeLibrary__ || window;
  const { Html5Qrcode, Html5QrcodeSupportedFormats: F } = lib;
  const pulsante = document.getElementById("avvia");
  const modulo = document.getElementById("modulo-codice");
  const campo = document.getElementById("codice");
  const scanner = new Html5Qrcode("lettore", {
    verbose: false,
    formatsToSupport: [F.EAN_13, F.EAN_8, F.UPC_A, F.CODE_128, F.DATA_MATRIX, F.QR_CODE],
    experimentalFeatures: { useBarCodeDetectorIfSupported: true },
  });
  let attivo = false;

  pulsante.addEventListener("click", async () => {
    if (attivo) {
      await scanner.stop();
      attivo = false;
      pulsante.textContent = "Usa fotocamera";
      return;
    }
    try {
      await scanner.start({ facingMode: "environment" }, { fps: 10 }, async (testo) => {
        await scanner.stop();
        attivo = false;
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
