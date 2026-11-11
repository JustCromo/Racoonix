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
      pulsante.textContent = (window.racoonixTesto ? window.racoonixTesto("Usa fotocamera") : "Usa fotocamera");
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
      pulsante.textContent = (window.racoonixTesto ? window.racoonixTesto("Ferma fotocamera") : "Ferma fotocamera");
    } catch (e) {
      pulsante.textContent = (window.racoonixTesto ? window.racoonixTesto("Fotocamera non disponibile") : "Fotocamera non disponibile");
    }
  });
  // Carico a raffica: la fotocamera si riaccende da sola, pronta per il prodotto successivo
  if (pulsante.dataset.raffica === "1") pulsante.click();
});
