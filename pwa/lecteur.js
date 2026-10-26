// Lecteur de rapport : PDF en défilement continu, annotation au crayon / surligneur,
// gomme partielle, annuler/rétablir, zoom à deux doigts. Les annotations sont
// enregistrées dans le moteur (jamais dans le PDF). Coordonnées en points PDF.
'use strict';

const $ = (id) => document.getElementById(id);
const params = new URLSearchParams(location.search);
const ref = ["cours", "groupe", "lab", "etudiant"].map((k) => params.get(k));
const base = ref.map(encodeURIComponent).join("/");
const URL_PDF = `/api/bibliotheque/rapport/${base}`;
const URL_ANNOTATIONS = `/api/annotations/${base}`;
const URL_EXPORT = `/api/export/${base}`;

const COULEURS = ["#d32f2f", "#1565c0", "#2e7d32", "#111111", "#ef6c00"];
const SURLIGNEURS = ["#ff5252", "#40c4ff", "#69f0ae", "#ffee58", "#ffab40"];
const ESPACE = 12; // espace entre les pages, en px
// 3 épaisseurs par outil : crayon = largeurs min/max en points PDF (la pression joue entre les deux), surligneur = largeur fixe.
const EPAISSEURS = {
  crayon: [{ min: 0.4, max: 2.2 }, { min: 0.6, max: 3.8 }, { min: 1, max: 6.5 }],
  surligneur: [{ min: 7, max: 7 }, { min: 11, max: 11 }, { min: 16, max: 16 }],
};
const PALETTES = { crayon: COULEURS, surligneur: SURLIGNEURS };
const DELAI_DROIT = 550; // ms d'immobilité en fin de trait pour redresser le surligneur

// Réglage par outil, gardé sur l'appareil. Au chargement : le dernier outil de trait (jamais la gomme).
const reglages = {
  outil: "crayon", courbe: 1, gomme: 6, doigt: false,
  crayon: { couleur: 0, epaisseur: 1 }, surligneur: { couleur: 3, epaisseur: 1 },
};
try {
  const m = JSON.parse(localStorage.getItem("reglages-lecteur") || "{}");
  for (const k of ["courbe", "gomme", "doigt"]) if (typeof m[k] === typeof reglages[k]) reglages[k] = m[k];
  for (const o of ["crayon", "surligneur"]) {
    const t = m[o] || {};
    if (Number.isInteger(t.couleur) && t.couleur >= 0 && t.couleur < 5) reglages[o].couleur = t.couleur;
    if (Number.isInteger(t.epaisseur) && t.epaisseur >= 0 && t.epaisseur < 3) reglages[o].epaisseur = t.epaisseur;
  }
  if (m.outil === "surligneur") reglages.outil = "surligneur";
} catch { /* stockage indisponible */ }
const garderReglages = () => {
  try { localStorage.setItem("reglages-lecteur", JSON.stringify(reglages)); } catch { /* idem */ }
};

let pages = []; // { numero, w, h, pdf, el, traits, actif, plan {R, zone}, bg, net, hl, ink (canvas), hlx, inkx (contextes), cible, taches }
const histoire = { annuler: [], retablir: [] };
let zoom = 1;

function message(texte) { const m = $("message"); m.textContent = texte; m.hidden = !texte; }

// ----- rail d'outils -----
const reglageTrait = () => reglages[reglages.outil === "surligneur" ? "surligneur" : "crayon"];
function couleurDe(o) { return PALETTES[o][reglages[o].couleur]; }
const OUTILS = ["crayon", "surligneur", "gomme"];
function majBarre() {
  const o = reglages.outil, gomme = o === "gomme";
  for (const k of OUTILS) { $("o-" + k).classList.toggle("on", k === o); $("o-" + k).setAttribute("aria-pressed", String(k === o)); }
  for (const k of ["crayon", "surligneur"]) $("o-" + k).querySelector("u").style.background = couleurDe(k);
  fermerPop();
  const t = reglages[gomme ? "crayon" : o];
  [...$("couleurs").children].forEach((b, i) => {
    b.disabled = gomme;
    b.firstChild.style.background = PALETTES[gomme ? "crayon" : o][i];
    b.classList.toggle("on", !gomme && i === t.couleur);
    b.setAttribute("aria-pressed", String(!gomme && i === t.couleur));
  });
}
// Fenêtre de l'outil actif, au 2e toucher : épaisseur du trait (crayon, surligneur); pour la gomme, le réglage de sa taille.
const hauteurTrait = (o, i) => Math.max(2, EPAISSEURS[o][i].max * (o === "surligneur" ? 0.7 : 1.4)) + "px";
let outilPop = null;
function fermerPop() { $("pop-outil").hidden = true; if (outilPop) outilPop.setAttribute("aria-expanded", "false"); outilPop = null; }
function ouvrirPop(bouton) {
  const o = reglages.outil, pop = $("pop-outil");
  pop.replaceChildren();
  pop.setAttribute("aria-label", "Épaisseur du trait");
  for (let i = 0; i < 3; i++) {
    const b = document.createElement("button"), trait = document.createElement("i");
    b.type = "button"; b.className = i === reglages[o].epaisseur ? "on" : ""; b.setAttribute("aria-label", `Épaisseur ${i + 1}`);
    trait.style.height = hauteurTrait(o, i);
    b.append(trait);
    b.onclick = () => { reglages[o].epaisseur = i; majBarre(); garderReglages(); };
    pop.append(b);
  }
  pop.hidden = false;
  const r = bouton.getBoundingClientRect();
  pop.style.left = r.right + 8 + "px";
  pop.style.top = Math.max(8, Math.min(innerHeight - pop.offsetHeight - 8, r.top)) + "px";
  outilPop = bouton; bouton.setAttribute("aria-expanded", "true");
}
document.addEventListener("pointerdown", (e) => {
  if (!e.target.closest("#pop-outil, .outil")) fermerPop();
  if (!e.target.closest("#reglages, #plus, .menu")) $("reglages").hidden = true;
});
COULEURS.forEach((_, i) => {
  const b = document.createElement("button"), pastille = document.createElement("i");
  b.type = "button"; b.className = "coul"; b.setAttribute("aria-label", `Couleur ${i + 1}`);
  b.append(pastille);
  b.onclick = () => { reglageTrait().couleur = i; majBarre(); garderReglages(); };
  $("couleurs").append(b);
});
function choisirOutil(o) {
  reglages.outil = o;
  majBarre();
  if (o !== "gomme") garderReglages();
}
for (const k of OUTILS) {
  $("o-" + k).setAttribute("aria-haspopup", "true"); $("o-" + k).setAttribute("aria-expanded", "false");
  $("o-" + k).title += " : touchez à nouveau pour ses réglages";
  $("o-" + k).onclick = () => {
    if (reglages.outil !== k) { choisirOutil(k); return; }
    if (k === "gomme") { $("reglages").hidden = !$("reglages").hidden; return; } // sa taille est dans les réglages
    if (outilPop === $("o-" + k)) fermerPop(); else { fermerPop(); ouvrirPop($("o-" + k)); }
  };
}
let dernierOutil = "crayon";
$("bascule").onclick = () => {
  if (reglages.outil === "gomme") choisirOutil(dernierOutil);
  else { dernierOutil = reglages.outil; choisirOutil("gomme"); }
};
for (const [id, cle] of [["r-courbe", "courbe"], ["r-gomme", "gomme"]]) {
  const el = $(id), sortie = el.parentElement.querySelector("b");
  el.value = reglages[cle];
  el.oninput = () => { reglages[cle] = +el.value; sortie.textContent = (+el.value).toFixed(1); garderReglages(); };
  sortie.textContent = (+el.value).toFixed(1);
}
$("r-doigt").checked = reglages.doigt;
$("r-doigt").onchange = (e) => { reglages.doigt = e.target.checked; garderReglages(); };
majBarre();

// ----- rendu des traits -----
function largeur(s, p) {
  return s.largeur_min + (s.largeur_max - s.largeur_min) * Math.pow(Math.min(1, Math.max(0, p)), s.courbe);
}
function segment(ctx, s, a, b, c) { // courbe quadratique a -> c, point de contrôle b
  ctx.lineWidth = largeur(s, (a.p + c.p) / 2);
  ctx.strokeStyle = s.couleur;
  ctx.beginPath(); ctx.moveTo(a.x, a.y); ctx.quadraticCurveTo(b.x, b.y, c.x, c.y); ctx.stroke();
}
const milieu = (a, b) => ({ x: (a.x + b.x) / 2, y: (a.y + b.y) / 2, p: (a.p + b.p) / 2 });
function ctxDe(pg, s) { // la couche d'un outil n'existe que pour une page qui a des traits de cet outil
  const cle = s.outil === "surligneur" ? "hl" : "ink";
  if (!pg.actif) return null;
  if (!pg[cle]) preparerTrait(pg, cle);
  return pg[cle + "x"];
}

function tracer(pg, s) {
  const ctx = ctxDe(pg, s), pts = s.pts;
  if (!ctx) return;
  if (pts.length === 1) {
    ctx.fillStyle = s.couleur;
    ctx.beginPath(); ctx.arc(pts[0].x, pts[0].y, largeur(s, pts[0].p) / 2, 0, 7); ctx.fill();
    return;
  }
  let prec = pts[0];
  for (let i = 1; i < pts.length; i++) {
    const m = milieu(pts[i - 1], pts[i]);
    segment(ctx, s, prec, pts[i - 1], m); prec = m;
  }
  segment(ctx, s, prec, pts[pts.length - 1], pts[pts.length - 1]);
}
function tracerEnDirect(pg, d) { // ne dessine que les nouveaux segments
  const s = d.s, pts = s.pts, ctx = ctxDe(pg, s);
  if (!ctx) return;
  if (pts.length === 1) { tracer(pg, s); return; }
  const depuis = Math.max(1, d.trace || 1);
  let prec = depuis === 1 ? pts[0] : milieu(pts[depuis - 2], pts[depuis - 1]);
  for (let i = depuis; i < pts.length; i++) {
    const m = milieu(pts[i - 1], pts[i]);
    segment(ctx, s, prec, pts[i - 1], m); prec = m;
  }
  d.trace = pts.length;
}
function redessiner(pg) {
  if (!pg.actif) return;
  for (const cle of ["hl", "ink"]) {
    const x = pg[cle + "x"];
    if (x) { x.save(); x.setTransform(1, 0, 0, 1, 0, 0); x.clearRect(0, 0, pg[cle].width, pg[cle].height); x.restore(); }
  }
  for (const s of pg.traits) tracer(pg, s);
}

// ----- pages : canvas créés seulement pour les pages proches de l'écran (mémoire de l'iPad) -----
// Résolution et zone dessinée : pwa/resolution.js. Fond : la page entière en résolution de base, plus un « net » à la
// résolution de l'écran sur la zone visible quand la page entière coûterait trop de pixels (grand zoom). Surligneur
// et encre : même zone et même résolution que le net, créés seulement pour une page qui a des traits de cet outil.
// Tout rendu est repoussé pendant le pincement, le crayon et le défilement (`programmerPlans`) et annulé s'il est périmé.
const COUCHES = { bg: "fond", net: "fond-net", hl: "surligneur", ink: "encre" };
const densite = () => window.devicePixelRatio || 1;

function libererCanvas(c) { if (c) { c.width = c.height = 0; c.remove(); } } // vide la mémoire sans attendre le ramasse-miettes
function nouveauCanvas(pg, cle, zone, R) { // taille CSS exacte : un pixel de canvas = 1/R point
  const c = document.createElement("canvas");
  c.className = COUCHES[cle];
  c.width = Math.ceil((zone ? zone.w : pg.w) * R); c.height = Math.ceil((zone ? zone.h : pg.h) * R);
  c.style.left = (zone ? zone.x : 0) + "px"; c.style.top = (zone ? zone.y : 0) + "px";
  c.style.width = c.width / R + "px"; c.style.height = c.height / R + "px";
  return c;
}
function preparerTrait(pg, cle) { // (re)crée la couche des traits selon le plan de la page
  const { R, zone } = pg.plan, c = nouveauCanvas(pg, cle, zone, R);
  libererCanvas(pg[cle]); pg[cle] = c; pg.el.append(c);
  const x = pg[cle + "x"] = c.getContext("2d");
  x.setTransform(R, 0, 0, R, -(zone ? zone.x : 0) * R, -(zone ? zone.y : 0) * R);
  x.lineCap = "round"; x.lineJoin = "round";
}
async function rendreCouche(pg, cle, zone, R) { // fond ou net : rendu dans un nouveau canvas, échangé une fois fini
  const avant = pg.taches[cle];
  if (avant) avant.cancel();
  const mien = (pg.cible[cle] = { zone, R });
  const c = nouveauCanvas(pg, cle, zone, R), z = zone || { x: 0, y: 0 };
  const tache = (pg.taches[cle] = pg.pdf.render({
    canvasContext: c.getContext("2d"),
    viewport: pg.pdf.getViewport({ scale: R, offsetX: -z.x * R, offsetY: -z.y * R }),
  }));
  try { await tache.promise; } catch (e) {
    libererCanvas(c);
    if (!e || e.name !== "RenderingCancelledException") console.error("Rendu du PDF :", e);
    return;
  }
  if (pg.taches[cle] === tache) pg.taches[cle] = null;
  if (!pg.actif || pg.cible[cle] !== mien) { libererCanvas(c); return; } // périmé
  const ancien = pg[cle];
  if (ancien) ancien.replaceWith(c); else pg.el.append(c);
  libererCanvas(ancien); pg[cle] = c;
  if (cle === "bg") {
    pg.bgR = R;
    if (!pg.plan.zone && pg.net) { libererCanvas(pg.net); pg.net = null; pg.cible.net = null; } // retour en page entière
  }
  majDebug();
}
const memeZone = (a, b) => a === b || (!!a && !!b && a.x === b.x && a.y === b.y && a.w === b.w && a.h === b.h);
function appliquerPlan(pg, plan) {
  pg.plan = plan;
  for (const cle of ["hl", "ink"]) if (pg[cle]) preparerTrait(pg, cle);
  redessiner(pg);
  const base = plan.zone ? Resolution.resolutionPlein(pg.w, pg.h) : plan.R; // le fond de base couvre toute la page
  if (!pg.cible.bg || pg.cible.bg.R !== base) rendreCouche(pg, "bg", null, base);
  if (plan.zone) {
    const n = pg.cible.net;
    if (!n || n.R !== plan.R || !memeZone(n.zone, plan.zone)) rendreCouche(pg, "net", plan.zone, plan.R);
  } else if (pg.net && pg.bgR === base) {
    if (pg.taches.net) pg.taches.net.cancel();
    libererCanvas(pg.net); pg.net = null; pg.cible.net = null;
  }
  majDebug();
}
const zoneVisiblePage = (pg) => Resolution.zoneVisible(pg.el.getBoundingClientRect(), fenetre.getBoundingClientRect(), pg.w, pg.h);
function rafraichir(pg) {
  if (!pg.actif) return;
  const visible = zoneVisiblePage(pg), voulu = Resolution.planifier({ w: pg.w, h: pg.h, zoom, dpr: densite(), visible });
  if (!Resolution.suffit(pg.plan, voulu, visible)) appliquerPlan(pg, voulu);
}
function activer(pg) {
  if (pg.actif) return;
  pg.actif = true; rafraichir(pg);
}
function desactiver(pg) {
  if (!pg.actif) return;
  pg.actif = false;
  for (const t of Object.values(pg.taches)) if (t) t.cancel();
  for (const cle of Object.keys(COUCHES)) { libererCanvas(pg[cle]); pg[cle] = null; pg[cle + "x"] = null; } // la couche des fautes (DOM léger) reste en place
  pg.taches = {}; pg.cible = {}; pg.plan = null; pg.bgR = 0;
  majDebug();
}
let minuteriePlans = null;
function programmerPlans(delai) { // après le défilement, le pincement ou un changement de zoom
  clearTimeout(minuteriePlans);
  minuteriePlans = setTimeout(function lancer() {
    if (pincement || enCours.size) { minuteriePlans = setTimeout(lancer, 200); return; }
    pages.forEach(rafraichir);
  }, delai);
}

// Compteur de pixels de canvas actifs (constat M8), désactivé par défaut : lecteur.html?debug=canvas
function mesurerCanvas() {
  let pixels = 0, n = 0;
  for (const pg of pages) for (const cle of Object.keys(COUCHES)) if (pg[cle]) { pixels += pg[cle].width * pg[cle].height; n++; }
  return { canvas: n, mpx: +(pixels / 1e6).toFixed(1), mo: Math.round((pixels * 4) / 1048576) };
}
let affichageDebug = null;
function majDebug() {
  if (params.get("debug") !== "canvas") return;
  if (!affichageDebug) {
    affichageDebug = document.createElement("div");
    affichageDebug.style.cssText = "position:fixed;left:8px;bottom:8px;z-index:200;padding:2px 8px;border-radius:6px;background:#000a;color:#fff;font:11px monospace;pointer-events:none";
    document.body.append(affichageDebug);
  }
  const m = mesurerCanvas();
  affichageDebug.textContent = `canvas ${m.canvas} · ${m.mpx} Mpx · ${m.mo} Mo · zoom ${zoom.toFixed(2)}`;
}

// ----- saisie -----
const enCours = new Map(); // pointerId -> { pg, s, trace } ou { pg, gomme, retires, ajoutes }
let dernierP = 0.5;
const accepte = (e) => e.pointerType === "pen" || e.pointerType === "mouse" || (e.pointerType === "touch" && reglages.doigt);
const pression = (e) => (e.pointerType === "pen" ? e.pressure || 0.01 : 0.5);
function position(e, pg) {
  const r = pg.el.getBoundingClientRect();
  return { x: ((e.clientX - r.left) * pg.w) / r.width, y: ((e.clientY - r.top) * pg.h) / r.height };
}

// Surligneur : crayon immobile en fin de trait -> le trait devient une ligne droite du départ à la position du crayon.
function armerRedressement(d, p) {
  if (d.s.outil !== "surligneur") return;
  d.ref = p; clearTimeout(d.minuterie);
  d.minuterie = setTimeout(() => {
    if (d.s.pts.length < 3) return;
    d.droit = true;
    d.s.pts = [d.s.pts[0], { ...d.s.pts[d.s.pts.length - 1], p: 0.5 }];
    redessiner(d.pg);
  }, DELAI_DROIT);
}

// Les événements viennent de la page (les canvas ne couvrent que la zone rendue); la couche des fautes garde les siens.
const surLaPage = (e, pg) => e.target === pg.el || e.target instanceof HTMLCanvasElement;
function brancherSaisie(pg) {
  const ink = pg.el;
  ink.addEventListener("pointerdown", (e) => {
    if (!accepte(e) || !pg.actif || !surLaPage(e, pg)) return;
    if (pg.plan.zone) rafraichir(pg); // la zone rendue doit couvrir l'écran avant le premier point
    e.preventDefault(); ink.setPointerCapture(e.pointerId);
    const p = position(e, pg); p.p = dernierP = pression(e);
    if (reglages.outil === "gomme") {
      const d = { pg, gomme: true, retires: [], ajoutes: [] };
      enCours.set(e.pointerId, d); gommerVers(d, p); return;
    }
    const o = reglages.outil, ep = EPAISSEURS[o][reglages[o].epaisseur];
    const s = {
      id: FusionAnnotations.nouvelId(), outil: o, couleur: couleurDe(o), courbe: o === "surligneur" ? 1 : reglages.courbe, pts: [p],
      largeur_min: ep.min, largeur_max: ep.max,
    };
    const d = { pg, s, trace: 0, droit: false, minuterie: null };
    enCours.set(e.pointerId, d);
    pg.traits.push(s); tracerEnDirect(pg, d);
    armerRedressement(d, p);
  }, { passive: false });

  ink.addEventListener("pointermove", (e) => {
    const d = enCours.get(e.pointerId);
    if (!d) return;
    e.preventDefault();
    const groupes = e.getCoalescedEvents ? e.getCoalescedEvents() : [];
    for (const ev of groupes.length ? groupes : [e]) {
      const p = position(ev, pg);
      if (d.gomme) { gommerVers(d, p); continue; }
      if (d.droit) { d.s.pts = [d.s.pts[0], { ...p, p: 0.5 }]; continue; } // trait redressé : le bout suit le crayon
      const dernier = d.s.pts[d.s.pts.length - 1];
      if (Math.hypot(p.x - dernier.x, p.y - dernier.y) < 0.3) continue;
      p.p = dernierP = dernierP * 0.5 + pression(ev) * 0.5; // lisse la pression
      d.s.pts.push(p);
      if (d.ref && Math.hypot(p.x - d.ref.x, p.y - d.ref.y) > 3) armerRedressement(d, p); // d.ref : surligneur seulement
    }
    if (d.gomme) return;
    if (d.droit) redessiner(pg); else tracerEnDirect(pg, d);
  }, { passive: false });

  const fin = (e) => {
    const d = enCours.get(e.pointerId);
    if (!d) return;
    enCours.delete(e.pointerId);
    clearTimeout(d.minuterie);
    if (d.gomme) {
      if (d.retires.length || d.ajoutes.length) empiler({ type: "gomme", pg, retires: d.retires, ajoutes: d.ajoutes });
    } else {
      tracer(pg, d.s);
      empiler({ type: "ajout", pg, s: d.s });
    }
  };
  ink.addEventListener("pointerup", fin); ink.addEventListener("pointercancel", fin);

  // Un tap du doigt (ou un double clic à la souris) sélectionne la faute de français sous le doigt.
  let appui = null;
  ink.addEventListener("pointerdown", (e) => { if (!surLaPage(e, pg)) return; appui = e.pointerType === "touch" ? { x: e.clientX, y: e.clientY, t: performance.now() } : null; });
  ink.addEventListener("pointerup", (e) => {
    if (!appui || reglages.doigt) return;
    const tap = Math.hypot(e.clientX - appui.x, e.clientY - appui.y) < 10 && performance.now() - appui.t < 500;
    appui = null;
    if (tap && window.surToucher) window.surToucher(pg, position(e, pg));
  });
  ink.addEventListener("dblclick", (e) => { if (surLaPage(e, pg) && window.surToucher) window.surToucher(pg, position(e, pg)); });
  ink.addEventListener("contextmenu", (e) => e.preventDefault());
}

// Le Pencil ne doit ni défiler ni zoomer ; le doigt oui (touchType « stylus » d'iPadOS).
for (const type of ["touchstart", "touchmove"]) {
  $("pile").addEventListener(type, (e) => {
    for (const t of e.changedTouches) if (t.touchType === "stylus" || reglages.doigt) { e.preventDefault(); return; }
  }, { passive: false });
}

// ----- gomme partielle : retire les points sous la gomme et coupe le trait (pwa/gomme.js) -----
function gommerEn(d, p) {
  const pg = d.pg, reste = Gomme.gommer(pg.traits, p, reglages.gomme, d, FusionAnnotations.nouvelId);
  if (reste) { pg.traits = reste; redessiner(pg); marquerModifie(); }
}
function gommerVers(d, p) { // comble les trous si la gomme va vite
  const dernier = d.dernier; d.dernier = p;
  if (!dernier) { gommerEn(d, p); return; }
  const n = Math.max(1, Math.ceil(Math.hypot(p.x - dernier.x, p.y - dernier.y) / 2));
  for (let k = 1; k <= n; k++) gommerEn(d, { x: dernier.x + ((p.x - dernier.x) * k) / n, y: dernier.y + ((p.y - dernier.y) * k) / n });
}

// ----- annuler / rétablir (toutes pages confondues) -----
function majBoutons() { $("annuler").disabled = !histoire.annuler.length; $("retablir").disabled = !histoire.retablir.length; }
function empiler(action) { histoire.annuler.push(action); histoire.retablir = []; majBoutons(); marquerModifie(); }
function appliquer(a, sens) { // sens : +1 refaire, -1 défaire
  const pg = a.pg;
  if (a.type === "ajout") {
    if (sens > 0) pg.traits.push(a.s); else pg.traits = pg.traits.filter((s) => s !== a.s);
  } else {
    const [sortent, entrent] = sens > 0 ? [a.retires, a.ajoutes] : [a.ajoutes, a.retires];
    pg.traits = pg.traits.filter((s) => !sortent.includes(s));
    pg.traits.push(...entrent);
  }
  redessiner(pg); majBoutons(); marquerModifie();
  pg.el.scrollIntoView({ block: "nearest" });
}
// Attendre que les dernières modifications (traits, décisions de français) soient enregistrées.
// true = confirmé par le moteur; false = pas enregistré (moteur injoignable, décisions refusées) : ne pas quitter le rapport.
async function toutEnregistrer() {
  for (let i = 0; i < 3 && (modifie || envoi); i++) {
    clearTimeout(minuterie);
    await enregistrer();
    while (envoi) await new Promise((r) => setTimeout(r, 100));
  }
  const francaisOk = window.viderDecisions ? await window.viderDecisions() : true;
  return francaisOk && !modifie && !envoi;
}
// Variante pour les boutons qui quittent ou exportent : prévient Guillaume si tout n'est pas enregistré.
async function enregistrerAvant() {
  if (await toutEnregistrer()) return true;
  alert("Des modifications ne sont pas encore enregistrées (moteur injoignable ou décisions rechargées). " +
    "Rien n'a été perdu à l'écran : vérifiez l'indicateur « Non enregistré », puis réessayez.");
  return false;
}
window.toutEnregistrer = toutEnregistrer;
window.enregistrerAvant = enregistrerAvant;
async function exporterPdf() { if (await enregistrerAvant()) location.href = URL_EXPORT; }
$("annuler").onclick = () => { const a = histoire.annuler.pop(); if (a) { appliquer(a, -1); histoire.retablir.push(a); majBoutons(); } };
$("retablir").onclick = () => { const a = histoire.retablir.pop(); if (a) { appliquer(a, +1); histoire.annuler.push(a); majBoutons(); } };

// ----- enregistrement dans le moteur -----
const arrondi = (n) => Math.round(n * 100) / 100;
// Révision et état connu du moteur à la dernière synchronisation (voir annotations-fusion.js).
let revision = 0, baseFusion = { ids: new Set(), supprimes: new Set() }, avisFusion = false;
function traitSerialise(s) {
  return {
    id: s.id, outil: s.outil, couleur: s.couleur, largeur_min: s.largeur_min, largeur_max: s.largeur_max, courbe: s.courbe,
    points: s.pts.map((q) => [arrondi(q.x), arrondi(q.y), arrondi(q.p)]),
  };
}
function serialiserPages() {
  const out = {};
  for (const pg of pages) if (pg.traits.length) out[pg.numero] = pg.traits.map(traitSerialise);
  return out;
}
function serialiser() {
  const doc = { version: 2, revision, pages: serialiserPages(), supprimes: [] };
  const presents = FusionAnnotations.identifiants(doc.pages);
  doc.supprimes = [...new Set([...baseFusion.ids, ...baseFusion.supprimes])].filter((id) => !presents.has(id));
  return doc;
}
function memoriserBase(doc) { // ce que le moteur a maintenant : sert à distinguer « effacé ici » de « ajouté ailleurs »
  revision = doc.revision;
  baseFusion = { ids: FusionAnnotations.identifiants(doc.pages), supprimes: new Set(doc.supprimes || []) };
}
function chargerTraits(doc) {
  const connus = new Map(pages.flatMap((pg) => pg.traits).map((s) => [s.id, s])); // garde les objets (annuler/rétablir)
  for (const pg of pages) {
    pg.traits = (doc.pages[pg.numero] || []).map((t) => connus.get(t.id) || ({
      id: t.id, outil: t.outil, couleur: t.couleur, largeur_min: t.largeur_min, largeur_max: t.largeur_max, courbe: t.courbe,
      pts: t.points.map(([x, y, p]) => ({ x, y, p })),
    }));
    redessiner(pg);
  }
}
// Le moteur a une révision plus récente (un autre appareil a écrit) : on fusionne, sans rien perdre.
function fusionnerAvec(distant) {
  const fusion = FusionAnnotations.fusionner({ pages: serialiserPages() }, distant, baseFusion);
  chargerTraits({ pages: fusion.pages });
  memoriserBase({ revision: distant.revision, pages: distant.pages, supprimes: distant.supprimes });
  avisFusion = true;
}
let modifie = false, envoi = false, minuterie = null;
// Un seul indicateur pour les traits et les décisions de français : l'erreur d'abord, puis ce qui attend, puis « Enregistré ».
const etatsEnreg = { traits: { texte: "Enregistré", erreur: false }, francais: { texte: "Enregistré", erreur: false } };
function afficherEnreg() {
  const { traits, francais } = etatsEnreg;
  const nomme = (e) => (e === francais ? "Français : " : "") + e.texte;
  const attend = (e) => !e.erreur && !e.texte.startsWith("Enregistré");
  const [phase, texte] = traits.erreur ? ["erreur", nomme(traits)] : francais.erreur ? ["erreur", nomme(francais)]
    : attend(traits) ? ["attente", nomme(traits)] : attend(francais) ? ["attente", nomme(francais)] : ["ok", traits.texte];
  $("sauvegarde").textContent = texte;
  $("enreg").className = "enreg " + phase;
  $("enreg").querySelector("use").setAttribute("href", `vendor/lucide-sprite.svg#${{ ok: "check", attente: "loader", erreur: "circle-alert" }[phase]}`);
}
function etatSauvegarde(texte, erreur) { etatsEnreg.traits = { texte, erreur: !!erreur }; afficherEnreg(); }
window.etatSauvegardeFrancais = (texte, erreur) => { etatsEnreg.francais = { texte, erreur: !!erreur }; afficherEnreg(); };
function marquerModifie() {
  modifie = true; etatSauvegarde("Modifié…");
  clearTimeout(minuterie); minuterie = setTimeout(enregistrer, 800);
}
async function enregistrer(arret) {
  if (!modifie || (envoi && !arret)) return;
  envoi = true; modifie = false; etatSauvegarde("Enregistrement…");
  try {
    const doc = serialiser();
    const r = await fetch(URL_ANNOTATIONS, {
      method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify(doc), keepalive: arret === true,
    });
    if (r.status === 409) { // un autre appareil a enregistré entre-temps : fusion puis nouvel envoi
      fusionnerAvec((await r.json()).actuel);
      modifie = true; clearTimeout(minuterie); minuterie = setTimeout(enregistrer, 0);
      etatSauvegarde("Fusion avec un autre appareil…");
      return;
    }
    if (!r.ok) throw new Error(r.status);
    memoriserBase({ revision: (await r.json()).revision, pages: doc.pages, supprimes: doc.supprimes });
    if (!modifie) {
      etatSauvegarde(avisFusion ? "Enregistré · traits d'un autre appareil fusionnés" : "Enregistré");
      avisFusion = false;
    }
  } catch {
    modifie = true; etatSauvegarde("Non enregistré : nouvel essai…", true);
    clearTimeout(minuterie); minuterie = setTimeout(enregistrer, 4000);
  } finally {
    envoi = false;
    if (modifie && !minuterie) minuterie = setTimeout(enregistrer, 800);
  }
}
window.addEventListener("pagehide", () => enregistrer(true));
document.addEventListener("visibilitychange", () => { if (document.visibilityState === "hidden") enregistrer(true); });

// ----- zoom à deux doigts (la barre d'outils reste fixe) -----
const fenetre = $("fenetre"), taille = $("taille"), pile = $("pile");
let largeurPile = 0, hauteurPile = 0, pincement = null;
function appliquerZoom(z) {
  zoom = Math.min(5, Math.max(0.3, z));
  taille.style.width = largeurPile * zoom + "px"; taille.style.height = hauteurPile * zoom + "px";
  pile.style.transform = `scale(${zoom})`;
  programmerPlans(350); // net seulement quand le zoom s'arrête
  majDebug();
}
const LARGEUR_PAGE = 700; // largeur visée d'une page à l'ouverture, en px (la maquette Atelier)
function ajuster(pleineLargeur) {
  const fit = (fenetre.clientWidth - 8) / largeurPile;
  appliquerZoom(Math.min(2, pleineLargeur === true ? fit : Math.min(fit, LARGEUR_PAGE / largeurPile)));
  fenetre.scrollLeft = 0; fenetre.scrollTop = 0;
}
// Quand la zone du PDF change de taille (panneau des fautes ouvert/fermé, rotation, fenêtre) :
// même facteur de zoom relatif, même endroit du rapport en haut de la fenêtre. Les coordonnées
// restent en points PDF (c'est le zoom CSS de #pile qui s'adapte), donc rien ne se décale.
let largeurFenetre = 0;
function adapterALargeur() {
  // Marge en bas d'une demi-fenêtre : permet de centrer même une faute de la fin de la dernière page.
  fenetre.style.paddingBottom = Math.max(60, Math.round(fenetre.clientHeight / 2)) + "px";
  const l = fenetre.clientWidth;
  if (!largeurPile || !l) return;
  if (!largeurFenetre) { largeurFenetre = l; return; }
  if (l === largeurFenetre) return;
  const hautU = (fenetre.scrollTop - 12) / zoom, gaucheU = fenetre.scrollLeft / zoom;
  appliquerZoom((zoom * l) / largeurFenetre);
  largeurFenetre = l;
  fenetre.scrollTop = Math.max(0, hautU * zoom + 12); fenetre.scrollLeft = gaucheU * zoom;
}
UI.menu($("plus"), [
  { libelle: "Ajuster à la largeur", icone: "maximize", surClic: () => ajuster(true) },
  { libelle: "Exporter le PDF annoté", icone: "file-down", surClic: exporterPdf },
  { libelle: "Réglages du crayon", icone: "sliders-horizontal", surClic: () => { $("reglages").hidden = !$("reglages").hidden; } },
  { separateur: true },
  { libelle: "Bibliothèque", icone: "library", surClic: () => { location.href = "/#biblio"; } },
]);
const ecart = (t) => Math.hypot(t[0].clientX - t[1].clientX, t[0].clientY - t[1].clientY);
fenetre.addEventListener("touchstart", (e) => {
  if (e.touches.length === 2 && !reglages.doigt && [...e.touches].every((t) => t.touchType !== "stylus")) pincement = { d: ecart(e.touches), z: zoom };
}, { passive: false });
fenetre.addEventListener("touchmove", (e) => {
  if (!pincement || e.touches.length !== 2) return;
  e.preventDefault();
  const cx = (e.touches[0].clientX + e.touches[1].clientX) / 2, cy = (e.touches[0].clientY + e.touches[1].clientY) / 2;
  const r = taille.getBoundingClientRect(), ux = (cx - r.left) / zoom, uy = (cy - r.top) / zoom;
  appliquerZoom((pincement.z * ecart(e.touches)) / pincement.d);
  const r2 = taille.getBoundingClientRect();
  fenetre.scrollLeft += r2.left + ux * zoom - cx; fenetre.scrollTop += r2.top + uy * zoom - cy;
}, { passive: false });
const finPincement = (e) => { if (e.touches.length < 2 && pincement) { pincement = null; programmerPlans(100); } };
fenetre.addEventListener("touchend", finPincement); fenetre.addEventListener("touchcancel", finPincement);
new ResizeObserver(adapterALargeur).observe(fenetre);

// Page courante (indicateur), selon la page la plus proche du centre de la fenêtre.
let attenteDefilement = false;
fenetre.addEventListener("scroll", () => {
  programmerPlans(150); // la zone nette suit l'écran quand le défilement s'arrête
  if (attenteDefilement) return;
  attenteDefilement = true;
  requestAnimationFrame(() => {
    attenteDefilement = false;
    const f = fenetre.getBoundingClientRect(), centre = f.top + f.height / 2;
    let meilleur = pages[0], ecartMin = Infinity;
    for (const pg of pages) {
      const r = pg.el.getBoundingClientRect(), e = Math.abs(r.top + r.height / 2 - centre);
      if (e < ecartMin) { ecartMin = e; meilleur = pg; }
    }
    if (meilleur) $("page-info").textContent = `Page ${meilleur.numero} / ${pages.length}`;
  });
});

// ----- ouverture du rapport -----
async function ouvrir() {
  if (ref.some((v) => !v)) { message("Rapport non précisé : ouvrir le lecteur depuis la bibliothèque."); return; }
  $("titre").textContent = params.get("nom") || `${ref[3]} · ${ref[2]}`;
  $("avatar").textContent = $("titre").textContent.split(/\s+/).filter(Boolean).slice(0, 2).map((m) => m[0].toUpperCase()).join("");
  $("sous-titre").textContent = `${ref[2]} · gr. ${ref[1]}`;
  document.title = `${$("titre").textContent} — Correction de labs`;
  try { // « Reprendre » et « Récents » enregistrés par le moteur (échec silencieux)
    const ipad = /iPad|iPhone/.test(navigator.userAgent) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    fetch("/api/reprendre", { method: "PUT", headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ cours: ref[0], groupe: ref[1], lab: ref[2], etudiant: ref[3], appareil: ipad ? "iPad" : "PC" }) }).catch(() => {});
  } catch { /* envoi impossible */ }
  pdfjsLib.GlobalWorkerOptions.workerSrc = "vendor/pdf.worker.min.js";
  let doc, annotations;
  try {
    const [rp, ra] = await Promise.all([fetch(URL_PDF), fetch(URL_ANNOTATIONS)]);
    if (!rp.ok || !ra.ok) throw new Error("introuvable");
    doc = await pdfjsLib.getDocument({ data: await rp.arrayBuffer() }).promise;
    annotations = await ra.json();
  } catch {
    message("Rapport introuvable ou moteur injoignable.");
    return;
  }
  const observateur = new IntersectionObserver((entrees) => {
    for (const en of entrees) {
      const pg = pages[+en.target.dataset.index];
      if (en.isIntersecting) activer(pg); else desactiver(pg);
    }
  }, { root: fenetre, rootMargin: "100% 0px" });
  for (let i = 1; i <= doc.numPages; i++) {
    const pdfPage = await doc.getPage(i), vp = pdfPage.getViewport({ scale: 1 });
    const el = document.createElement("div");
    el.className = "page"; el.dataset.index = i - 1;
    el.style.width = vp.width + "px"; el.style.height = vp.height + "px";
    pile.append(el);
    pages.push({ numero: i, w: vp.width, h: vp.height, pdf: pdfPage, el, traits: [], actif: false, plan: null, bgR: 0, cible: {}, taches: {} });
    brancherSaisie(pages[pages.length - 1]);
    largeurPile = Math.max(largeurPile, vp.width);
    hauteurPile += vp.height + ESPACE;
  }
  pile.style.width = largeurPile + "px";
  chargerTraits(annotations); memoriserBase(annotations);
  ajuster(); largeurFenetre = fenetre.clientWidth;
  pages.forEach((pg) => observateur.observe(pg.el));
  $("page-info").textContent = `Page 1 / ${pages.length}`;
  majBoutons();
}
ouvrir();
