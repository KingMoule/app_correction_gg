// Coque de l'application : remplit la barre latérale (#coque-lat), gère le tiroir en portrait, l'état « Ordi connecté »,
// la ligne du lot en cours et les labs en cours. À charger après ui.js et avant app.js. Rien d'autre à appeler :
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
    { cle: "biblio", libelle: "Labs", icone: "flask-conical", href: "/#biblio" },
    { cle: "importer", libelle: "Importer", icone: "upload", href: "/#importer", badge: "badge-attente" },
    { cle: "plagiat", libelle: "Plagiat", icone: "scan-search", href: "plagiat.html" },
  ];
  // La vue « outils » (analyse par lot) n'a plus de lien : le lot se lance depuis l'accueil et la page du lab.
  const VUE_VERS_CLE = { accueil: "accueil", biblio: "biblio", importer: "importer" };

  // « lab-2 » -> « Lab 2 » (l'identifiant ne change pas, seulement le titre affiché)
  function titreLab(lab) {
    const m = /^lab[-_ ]?(\d+[a-z]?)$/i.exec(lab);
    if (m) return `Lab ${m[1]}`;
    const t = lab.replace(/[-_]+/g, " ").trim();
    return t.charAt(0).toUpperCase() + t.slice(1);
  }

  function lien(def) {
    const a = sur("a", "cq-lien");
    a.href = def.href;
    if (def.titre) a.title = def.titre;
    a.dataset.cle = def.cle;
    a.append(UI.icone(def.icone), sur("span", "", def.libelle));
    if (def.badge) { const b = sur("span", "cq-n alerte"); b.id = def.badge; b.hidden = true; a.append(b); }
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

  // Jauge de consommation de Claude (estimation, voir consommation.html) : cachée tant que le moteur ne répond pas
  const conso = sur("a", "cq-conso"); conso.href = "consommation.html"; conso.hidden = true; conso.dataset.cle = "conso";
  conso.title = "Consommation estimée de Claude (à calibrer avec /usage)";
  const consoTexte = sur("span", ""), consoValeur = sur("b", "");
  const consoLigne = sur("span", "l1"); consoLigne.append(consoTexte, consoValeur);
  const jauge = sur("span", "jauge"), jaugeBarre = sur("i"), jaugeRepere = sur("u");
  jauge.append(jaugeBarre, jaugeRepere);
  conso.append(consoLigne, jauge);

  // Lot en cours (visible seulement pendant un lot) : « Lot · Lab 3 · NYA » + « 4 / 7 », mène à la page du lab
  const lot = sur("a", "cq-lot"); lot.hidden = true; lot.dataset.cle = "lot";
  const lotTexte = sur("span", ""), lotN = sur("b", "");
  const lotLigne = sur("span", "l1"); lotLigne.append(lotTexte, lotN);
  const lotJauge = sur("span", "jauge"), lotBarre = sur("i");
  lotJauge.append(lotBarre);
  lot.append(lotLigne, lotJauge);

  lat.append(marque, nav, conso, lot, titreLabs, zoneLabs, pied);

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
  if (page === "consommation.html") conso.classList.add("on");
  if (page === "plagiat.html") marquer("plagiat");
  else if (page === "index.html") marquer(VUE_VERS_CLE[location.hash.slice(1)] ?? "accueil");

  // --- Labs en cours : au moins un rapport pas terminé et lab non archivé ---
  const labTermine = (c, lab) => {
    const avec = c.etudiants.filter((e) => e.labs.includes(lab));
    return c.labs_archives.includes(lab) || (avec.length > 0 && avec.every((e) => e.termines.includes(lab)));
  };
  const MAX_LABS = 6;
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
      a.title = `${UI.titreCours(u.cours)} · ${titreLab(u.lab)}`;
      const actif = page === "suivi.html" && courant.get("cours") === u.cours && courant.get("lab") === u.lab;
      if (actif) { a.classList.add("on"); a.setAttribute("aria-current", "page"); }
      a.append(sur("span", "", `${titreLab(u.lab)} · ${UI.titreCours(u.cours)}`), sur("span", "cq-n", `${u.faits} / ${u.total}`));
      return a;
    });
    if (enCours.length > MAX_LABS) {
      const plus = sur("a", "cq-lien", `+ ${enCours.length - MAX_LABS} autres dans Labs`);
      plus.href = "/#biblio";
      items.push(plus);
    }
    if (!items.length) items.push(sur("p", "cq-vide", arbre.length ? "Tout est terminé." : "Aucune classe importée."));
    zoneLabs.replaceChildren(...items);
  }

  let dernierStatut = null;
  // --- État du moteur et progression du lot (une seule requête périodique) ---
  async function surveiller() {
    let delai = 10000;
    try {
      const e = await (await fetch("/api/lot")).json();
      ordi.className = "cq-ordi ok";
      ordi.title = ordi.dataset.version || "";
      texteOrdi.textContent = "Ordi connecté";
      const actif = e.statut === "en_cours" && e.total > 0;
      lot.hidden = !actif;
      if (actif) {
        lot.href = `suivi.html?${new URLSearchParams({ cours: e.cours, lab: e.lab })}`;
        lotTexte.textContent = `Lot · ${titreLab(e.lab)} · ${e.cours}`;
        lotN.textContent = `${e.fait} / ${e.total}`;
        lotBarre.style.width = `${Math.round((100 * e.fait) / e.total)}%`;
        delai = 2000;
      }
      // Un seul lot à la fois : l'accueil (et la page du lab) s'y abonnent pour désactiver leurs boutons
      window.Coque.lot = e;
      if (e.statut !== dernierStatut || actif) document.dispatchEvent(new CustomEvent("coque:lot", { detail: e }));
      dernierStatut = e.statut;
      // Jauge : toutes les 8 s pendant un lot (chaque rapport ajoute des appels), sinon chaque minute
      if (Date.now() - derniereConso > (actif ? 8000 : 60000)) { derniereConso = Date.now(); majConso(); }
    } catch {
      ordi.className = "cq-ordi erreur";
      ordi.title = "L'ordi est-il allumé et sur le même Wi-Fi ?";
      texteOrdi.textContent = "Ordi injoignable";
    }
    setTimeout(surveiller, document.hidden ? 30000 : delai);
  }

  // --- Jauge de consommation : seuil d'alerte d'après la marge réglée dans la page Consommation ---
  const pct = (v) => `≈ ${Math.round(v)} %`;
  async function majConso() {
    try {
      const r = await (await fetch("/api/consommation")).json();
      // Total estimé (saisie récente de /usage + app depuis) s'il existe, sinon la part de l'app seulement.
      const ts = r.total?.session, total = ts?.etat === "ok";
      const plafond = r.plafond_pct, p = total ? ts.total : r.session.pct;
      const limite = r.limite;
      const niveau = limite || p >= plafond ? "danger" : p >= plafond - 15 ? "attention" : "";
      jauge.className = "jauge " + niveau;
      jaugeBarre.style.width = `${Math.min(100, limite ? 100 : p)}%`;
      jaugeRepere.style.left = `${plafond}%`;
      consoTexte.textContent = limite ? "Claude · limite atteinte" : total ? "Claude · 5 h" : "Claude · 5 h · app";
      conso.title = total ? `Total estimé du forfait (saisi il y a ${ts.age_min} min, plus l'app depuis) · reste ≈ ${Math.round(ts.reste)} %`
        : "Part de l'app seulement : la limite est partagée avec tes autres usages. Saisis /usage pour voir le total.";
      consoValeur.textContent = limite ? `reprise ${limite.reprise.slice(11, 16)}` : pct(p);
      conso.setAttribute("aria-label", limite ? `Limite de Claude atteinte, reprise vers ${limite.reprise.slice(11, 16)}`
        : `${total ? "Usage total estimé" : "Part de l'app seulement"} sur 5 heures : ${Math.round(p)} pour cent, arrêt conseillé à ${Math.round(plafond)}`);
      conso.hidden = false;
    } catch { conso.hidden = true; }
  }
  let derniereConso = 0;

  async function chargerLabs() {
    try { labs(await (await fetch("/api/bibliotheque")).json()); } catch { /* le pied de la barre signale déjà un moteur injoignable */ }
  }
  fetch("/api/etat").then((r) => r.json()).then((d) => { ordi.dataset.version = `Moteur v${d.version}`; }).catch(() => {});
  surveiller();
  // app.js fournit lui-même la bibliothèque (labs(arbre)); sans lui (suivi, plagiat), on la charge ici.
  if (page !== "index.html") {
    chargerLabs();
    // Ctrl+K : la recherche est dans la page Labs (sur index.html, app.js s'en charge lui-même).
    document.addEventListener("keydown", (ev) => {
      if ((ev.ctrlKey || ev.metaKey) && !ev.altKey && ev.key.toLowerCase() === "k") { ev.preventDefault(); location.href = "/#recherche"; }
    });
  }

  window.Coque = { marquer: (vue) => marquer(VUE_VERS_CLE[vue] ?? "accueil"), labs, majConso, titreLab, lot: null };
})();
