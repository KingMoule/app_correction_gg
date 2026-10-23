// Maquettes : chaque écran est écrit une fois dans un <template id="m-…"> et cloné dans ses cadres (iPad, portrait, PC).
// Les cadres sont des conteneurs CSS (@container) : la même page se met en page selon la largeur du cadre.
// #seul-<id> affiche un seul cadre à sa taille réelle (captures).
(() => {
  for (const cadre of document.querySelectorAll("[data-modele]")) {
    const corps = document.getElementById(cadre.dataset.modele).content.cloneNode(true);
    const lat = document.getElementById(cadre.dataset.lat || "lat").content.cloneNode(true);
    const coque = document.createElement("div");
    coque.className = "coque";
    const aside = document.createElement("aside");
    aside.className = "coque-lat";
    aside.append(lat);
    const droite = document.createElement("div");
    droite.className = "coque-corps";
    const haut = document.getElementById("haut").content.cloneNode(true);
    droite.append(haut, corps);
    coque.append(aside, droite);
    cadre.append(coque);
    if (cadre.dataset.q) for (const i of cadre.querySelectorAll("main input[type=search]")) i.value = cadre.dataset.q;
    for (const a of cadre.querySelectorAll(`.cq-lien[data-cle="${cadre.dataset.actif}"]`)) a.classList.add("on");
  }
  const seul = location.hash.match(/^#seul-(.+)$/);
  if (seul) {
    document.body.classList.add("seul");
    document.getElementById(seul[1])?.classList.add("cible");
  }
})();
