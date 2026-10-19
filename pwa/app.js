// Point d'entrée de la PWA. Les écrans (bibliothèque, lecteur) viendront ici.
async function verifierMoteur() {
  const el = document.getElementById("etat");
  try {
    const r = await fetch("/api/etat");
    const d = await r.json();
    el.textContent = `Moteur connecté (v${d.version})`;
    el.className = "ok";
  } catch {
    el.textContent = "Moteur injoignable : l'ordi est-il allumé et sur le même Wi-Fi ?";
    el.className = "erreur";
  }
}
verifierMoteur();
