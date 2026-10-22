// Coque de l'application : remplit la barre latérale (#coque-lat), gère le tiroir en portrait, l'état « Ordi connecté »,
// la progression du lot et les labs en cours. À charger après ui.js et avant app.js. Rien d'autre à appeler :
// window.Coque.marquer(vue) (app.js, au changement de vue) et window.Coque.labs(arbre) (app.js, après chargement de la bibliothèque).
(() => {
  const lat = document.getElementById("coque-lat");
  if (!lat) return;
  const coque = lat.closest(".coque");
  const page = location.pathname.split("/").pop() || "index.html";
  const sur = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };

  const LIENS = [
    { cle: "accueil", libelle: "Accueil", icone: "house", href: "/#accueil" },
    { cle: "biblio", libelle: "Bibliothèque", icone: "library", href: "/#biblio" },
    { cle: "importer", libelle: "Importer", icone: "upload", href: "/#importer", badge: "badge-attente" },
    { cle: "lot", libelle: "Analyse par lot", icone: "layers", href: "/#outils", lot: true },
    { cle: "plagiat", libelle: "Plagiat", icone: "scan-search", href: "plagiat.html" },
    // L'export se lance depuis un lab de la bibliothèque (pas encore d'écran à lui) : jamais marqué actif.
    { cle: "export", libelle: "Export LÉA", icone: "file-down", href: "/#biblio", titre: "Se lance depuis un lab de la bibliothèque" },
  ];
  const VUE_VERS_CLE = { accueil: "accueil", biblio: "biblio", importer: "importer", outils: "lot" };

  function lien(def) {
    const a = sur("a", "cq-lien");
    a.href = def.href;
    if (def.titre) a.title = def.titre;
    a.dataset.cle = def.cle;
    a.append(UI.icone(def.icone), sur("span", "", def.libelle));
    if (def.badge) { const b = sur("span", "cq-n alerte"); b.id = def.badge; b.hidden = true; a.append(b); }
    if (def.lot) {
      const n = sur("span", "cq-n"); n.id = "cq-lot-n"; n.hidden = true;
      const barre = document.createElement("progress");
      barre.className = "cq-lot-barre"; barre.id = "cq-lot-barre"; barre.hidden = true;
      barre.setAttribute("aria-label", "Progression de l'analyse par lot");
      a.append(n, barre);
    }
    return a;
  }

  // --- Construction ---
  const marque = sur("div", "cq-marque");
  const logo = sur("span", "cq-logo"); logo.append(UI.icone("graduation-cap"));
  const nomApp = sur("span", "", "Correction"); nomApp.append(sur("small", "", "Rapports de lab"));
  marque.append(logo, nomApp);

  const nav = sur("nav", "cq-nav");
  nav.setAttribute("aria-label", "Navigation");
  nav.append(...LIENS.map(lien));

  const titreLabs = sur("p", "cq-titre", "Labs en cours");
  const zoneLabs = sur("div", "cq-labs"); zoneLabs.id = "cq-labs";

  const reglages = sur("span", "cq-lien");
  reglages.setAttribute("aria-disabled", "true");
  reglages.title = "Bientôt";
  reglages.append(UI.icone("settings"), sur("span", "", "Réglages"));
  const ordi = sur("div", "cq-ordi"); ordi.id = "cq-ordi";
  const texteOrdi = sur("span", "", "Connexion…");
  const deco = sur("button", "btn tertiaire", "Se déconnecter");
  deco.id = "deconnexion"; deco.type = "button"; deco.title = "Oublier le code sur cet appareil";
  ordi.append(sur("i", "cq-point"), texteOrdi, deco);
  const pied = sur("div", "cq-pied"); pied.append(reglages, ordi);

  lat.append(marque, nav, titreLabs, zoneLabs, pied);

  // Tiroir (portrait) : barre du haut avec « Menu » + voile
  const corps = coque.querySelector(".coque-corps");
  const haut = sur("header", "coque-haut");
  const menu = sur("button", "btn", "Menu");
  menu.type = "button"; menu.prepend(UI.icone("panel-right"));
  menu.setAttribute("aria-expanded", "false"); menu.setAttribute("aria-controls", "coque-lat");
  haut.append(menu, sur("b", "", "Correction"));
  corps.prepend(haut);
  const voile = sur("div", "cq-voile");
  coque.append(voile);
  const basculer = (ouvert) => {
    coque.classList.toggle("ouverte", ouvert);
    menu.setAttribute("aria-expanded", String(ouvert));
  };
  menu.onclick = () => basculer(!coque.classList.contains("ouverte"));
  voile.onclick = () => basculer(false);
  lat.addEventListener("click", (e) => { if (e.target.closest("a")) basculer(false); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape") basculer(false); });

  // --- Lien actif ---
  function marquer(cle) {
    for (const a of lat.querySelectorAll(".cq-lien[data-cle]")) {
      const actif = a.dataset.cle === cle;
      a.classList.toggle("on", actif);
      if (actif) a.setAttribute("aria-current", "page"); else a.removeAttribute("aria-current");
    }
  }
  if (page === "plagiat.html") marquer("plagiat");
  else if (page === "index.html") marquer(VUE_VERS_CLE[location.hash.slice(1)] ?? "accueil");

  // --- Labs en cours : au moins un rapport pas terminé et lab non archivé ---
  const labTermine = (c, lab) => {
    const avec = c.etudiants.filter((e) => e.labs.includes(lab));
    return c.labs_archives.includes(lab) || (avec.length > 0 && avec.every((e) => e.termines.includes(lab)));
  };
  const MAX_LABS = 8;
  function labs(arbre) {
    const parLab = new Map();
    for (const c of arbre) {
      for (const lab of new Set(c.etudiants.flatMap((e) => e.labs))) {
        const cle = JSON.stringify([c.cours, lab]);
        const u = parLab.get(cle) ?? { cours: c.cours, lab, total: 0, faits: 0, fini: true };
        u.total += c.etudiants.filter((e) => e.labs.includes(lab)).length;
        u.faits += c.etudiants.filter((e) => e.termines.includes(lab)).length;
        u.fini = u.fini && labTermine(c, lab);
        parLab.set(cle, u);
      }
    }
    const enCours = [...parLab.values()].filter((u) => !u.fini)
      .sort((a, b) => a.cours.localeCompare(b.cours, "fr") || a.lab.localeCompare(b.lab, "fr", { numeric: true }));
    const courant = new URLSearchParams(location.search);
    const items = enCours.slice(0, MAX_LABS).map((u) => {
      const a = sur("a", "cq-lien");
      a.href = `suivi.html?${new URLSearchParams({ cours: u.cours, lab: u.lab })}`;
      a.title = `${u.cours} · ${u.lab}`;
      const actif = page === "suivi.html" && courant.get("cours") === u.cours && courant.get("lab") === u.lab;
      if (actif) { a.classList.add("on"); a.setAttribute("aria-current", "page"); }
      a.append(sur("span", "", `${u.lab} · ${u.cours}`), sur("span", "cq-n", `${u.faits} / ${u.total}`));
      return a;
    });
    if (enCours.length > MAX_LABS) {
      const plus = sur("a", "cq-lien", `+ ${enCours.length - MAX_LABS} autres dans la bibliothèque`);
      plus.href = "/#biblio";
      items.push(plus);
    }
    if (!items.length) items.push(sur("p", "cq-vide", arbre.length ? "Tout est terminé." : "Aucune classe importée."));
    zoneLabs.replaceChildren(...items);
  }

  // --- État du moteur et progression du lot (une seule requête périodique) ---
  async function surveiller() {
    let delai = 10000;
    try {
      const e = await (await fetch("/api/lot")).json();
      ordi.className = "cq-ordi ok";
      ordi.title = ordi.dataset.version || "";
      texteOrdi.textContent = "Ordi connecté";
      const n = document.getElementById("cq-lot-n"), barre = document.getElementById("cq-lot-barre");
      const actif = e.statut === "en_cours" && e.total > 0;
      n.hidden = barre.hidden = !actif;
      if (actif) {
        n.textContent = `${e.fait} / ${e.total}`;
        barre.max = e.total; barre.value = e.fait;
        delai = 2000;
      }
    } catch {
      ordi.className = "cq-ordi erreur";
      ordi.title = "L'ordi est-il allumé et sur le même Wi-Fi ?";
      texteOrdi.textContent = "Ordi injoignable";
    }
    setTimeout(surveiller, document.hidden ? 30000 : delai);
  }

  async function chargerLabs() {
    try { labs(await (await fetch("/api/bibliotheque")).json()); } catch { /* le pied de la barre signale déjà un moteur injoignable */ }
  }
  fetch("/api/etat").then((r) => r.json()).then((d) => { ordi.dataset.version = `Moteur v${d.version}`; }).catch(() => {});
  surveiller();
  // app.js fournit lui-même la bibliothèque (labs(arbre)); sans lui (suivi, plagiat), on la charge ici.
  if (page !== "index.html") chargerLabs();

  window.Coque = { marquer: (vue) => marquer(VUE_VERS_CLE[vue] ?? "accueil"), labs };
})();
