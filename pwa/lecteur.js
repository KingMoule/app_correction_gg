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
  outil: "crayon", courbe: 1, gomme: 6, gommeMode: "trait", doigt: false,
  crayon: { couleur: 0, epaisseur: 1 }, surligneur: { couleur: 3, epaisseur: 1 },
};
try {
  const m = JSON.parse(localStorage.getItem("reglages-lecteur") || "{}");
  for (const k of ["courbe", "gomme", "doigt"]) if (typeof m[k] === typeof reglages[k]) reglages[k] = m[k];
  if (m.gommeMode === "trait" || m.gommeMode === "partielle") reglages.gommeMode = m.gommeMode;
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

let pages = []; // { numero, w, h, pdf, el, traits, actif, R, bg, hl, ink }
const histoire = { annuler: [], retablir: [] };
let zoom = 1;

function message(texte) { const m = $("message"); m.textContent = texte; m.hidden = !texte; }

// ----- barre d'outils -----
const reglageTrait = () => reglages[reglages.outil === "surligneur" ? "surligneur" : "crayon"];
function couleurDe(o) { return PALETTES[o][reglages[o].couleur]; }
function majBarre() {
  const o = reglages.outil, gomme = o === "gomme";
  for (const k of ["crayon", "surligneur", "gomme"]) $("o-" + k).classList.toggle("on", k === o);
  for (const k of ["crayon", "surligneur"]) $("o-" + k).querySelector("i").style.background = couleurDe(k);
  $("options-trait").hidden = gomme; $("options-gomme").hidden = !gomme;
  fermerMenu();
  $("g-trait").classList.toggle("on", reglages.gommeMode === "trait");
  $("g-partielle").classList.toggle("on", reglages.gommeMode === "partielle");
  if (gomme) return;
  const t = reglages[o];
  const hauteur = (i) => Math.max(2, EPAISSEURS[o][i].max * (o === "surligneur" ? 0.7 : 1.4)) + "px";
  [...$("epaisseurs").children].forEach((b, i) => {
    b.classList.toggle("on", i === t.epaisseur);
    b.firstChild.style.height = hauteur(i);
  });
  $("ep-bouton").querySelector(".trait-ap").style.height = hauteur(t.epaisseur);
  [...$("couleurs").children].forEach((b, i) => {
    b.style.background = PALETTES[o][i];
    b.classList.toggle("on", i === t.couleur);
  });
}
for (let i = 0; i < 3; i++) {
  const b = document.createElement("button");
  b.className = "epaisseur"; b.setAttribute("aria-label", `Épaisseur ${i + 1}`);
  b.append(document.createElement("span"));
  b.onclick = () => { reglageTrait().epaisseur = i; fermerMenu(); majBarre(); garderReglages(); };
  $("epaisseurs").append(b);
}
function fermerMenu() { $("epaisseurs").hidden = true; $("ep-bouton").setAttribute("aria-expanded", "false"); }
$("ep-bouton").onclick = () => {
  const ouvrir = $("epaisseurs").hidden;
  $("epaisseurs").hidden = !ouvrir; $("ep-bouton").setAttribute("aria-expanded", String(ouvrir));
};
document.addEventListener("pointerdown", (e) => { if (!e.target.closest(".menu")) fermerMenu(); });
COULEURS.forEach((_, i) => {
  const b = document.createElement("button");
  b.className = "pastille";
  b.setAttribute("aria-label", `Couleur ${i + 1}`);
  b.onclick = () => { reglageTrait().couleur = i; majBarre(); garderReglages(); };
  $("couleurs").append(b);
});
function choisirOutil(o) {
  reglages.outil = o;
  majBarre();
  if (o !== "gomme") garderReglages();
}
$("o-crayon").onclick = () => choisirOutil("crayon");
$("o-surligneur").onclick = () => choisirOutil("surligneur");
$("o-gomme").onclick = () => choisirOutil("gomme");
$("g-trait").onclick = () => { reglages.gommeMode = "trait"; majBarre(); garderReglages(); };
$("g-partielle").onclick = () => { reglages.gommeMode = "partielle"; majBarre(); garderReglages(); };
let dernierOutil = "crayon";
$("bascule").onclick = () => {
  if (reglages.outil === "gomme") choisirOutil(dernierOutil);
  else { dernierOutil = reglages.outil; choisirOutil("gomme"); }
};
$("reglages-bouton").onclick = () => { $("reglages").hidden = !$("reglages").hidden; };
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
const ctxDe = (pg, s) => (s.outil === "surligneur" ? pg.hlx : pg.inkx);

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
  if (!pg.actif || !pg.hlx) return;
  pg.hlx.clearRect(0, 0, pg.w, pg.h); pg.inkx.clearRect(0, 0, pg.w, pg.h);
  for (const s of pg.traits) tracer(pg, s);
}

// ----- pages : canvas créés seulement pour les pages proches de l'écran (mémoire de l'iPad) -----
const qualite = () => Math.min(3, Math.max(1.5, Math.ceil(zoom * (window.devicePixelRatio || 1) * 2) / 2));

async function activer(pg) {
  const R = qualite();
  if (pg.actif && pg.R === R) return;
  pg.actif = true; pg.R = R;
  if (!pg.bg) {
    for (const [cle, classe] of [["bg", "fond"], ["hl", "surligneur"], ["ink", "encre"]]) {
      pg[cle] = document.createElement("canvas"); pg[cle].className = classe; pg.el.append(pg[cle]);
    }
    brancherSaisie(pg);
  }
  for (const c of [pg.hl, pg.ink]) { c.width = Math.ceil(pg.w * R); c.height = Math.ceil(pg.h * R); }
  pg.hlx = pg.hl.getContext("2d"); pg.inkx = pg.ink.getContext("2d");
  for (const x of [pg.hlx, pg.inkx]) { x.setTransform(R, 0, 0, R, 0, 0); x.lineCap = "round"; x.lineJoin = "round"; }
  redessiner(pg);
  const jeton = (pg.jeton = {});
  const tmp = document.createElement("canvas");
  tmp.width = Math.ceil(pg.w * R); tmp.height = Math.ceil(pg.h * R);
  await pg.pdf.render({ canvasContext: tmp.getContext("2d"), viewport: pg.pdf.getViewport({ scale: R }) }).promise;
  if (pg.jeton !== jeton || !pg.bg) return; // page déjà désactivée ou re-rendue
  pg.bg.width = tmp.width; pg.bg.height = tmp.height;
  pg.bg.getContext("2d").drawImage(tmp, 0, 0);
}
function desactiver(pg) {
  if (!pg.actif) return;
  pg.actif = false; pg.jeton = null; pg.R = 0;
  for (const c of [pg.bg, pg.hl, pg.ink]) c.remove(); // la couche des fautes (DOM léger) reste en place
  pg.bg = pg.hl = pg.ink = pg.hlx = pg.inkx = null;
}

// ----- saisie -----
const enCours = new Map(); // pointerId -> { pg, s, trace } ou { pg, gomme, retires, ajoutes }
let dernierP = 0.5;
const accepte = (e) => e.pointerType === "pen" || e.pointerType === "mouse" || (e.pointerType === "touch" && reglages.doigt);
const pression = (e) => (e.pointerType === "pen" ? e.pressure || 0.01 : 0.5);
function position(e, pg) {
  const r = pg.ink.getBoundingClientRect();
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

function brancherSaisie(pg) {
  const ink = pg.ink;
  ink.addEventListener("pointerdown", (e) => {
    if (!accepte(e)) return;
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
      if (Math.hypot(p.x - d.ref.x, p.y - d.ref.y) > 3) armerRedressement(d, p);
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
  ink.addEventListener("pointerdown", (e) => { appui = e.pointerType === "touch" ? { x: e.clientX, y: e.clientY, t: performance.now() } : null; });
  ink.addEventListener("pointerup", (e) => {
    if (!appui || reglages.doigt) return;
    const tap = Math.hypot(e.clientX - appui.x, e.clientY - appui.y) < 10 && performance.now() - appui.t < 500;
    appui = null;
    if (tap && window.surToucher) window.surToucher(pg, position(e, pg));
  });
  ink.addEventListener("dblclick", (e) => { if (window.surToucher) window.surToucher(pg, position(e, pg)); });
  ink.addEventListener("contextmenu", (e) => e.preventDefault());
}

// Le Pencil ne doit ni défiler ni zoomer ; le doigt oui (touchType « stylus » d'iPadOS).
for (const type of ["touchstart", "touchmove"]) {
  $("pile").addEventListener(type, (e) => {
    for (const t of e.changedTouches) if (t.touchType === "stylus" || reglages.doigt) { e.preventDefault(); return; }
  }, { passive: false });
}

// ----- gomme partielle : retire les points sous la gomme et coupe le trait -----
function distSegment(p, a, b) {
  const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
  const u = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
  return Math.hypot(p.x - (a.x + u * dx), p.y - (a.y + u * dy));
}
function densifier(pts, pas) {
  const out = [pts[0]];
  for (let i = 1; i < pts.length; i++) {
    const a = pts[i - 1], b = pts[i], n = Math.ceil(Math.hypot(b.x - a.x, b.y - a.y) / pas);
    for (let k = 1; k < n; k++) { const f = k / n; out.push({ x: a.x + (b.x - a.x) * f, y: a.y + (b.y - a.y) * f, p: a.p + (b.p - a.p) * f }); }
    out.push(b);
  }
  return out;
}
function gommerEn(d, p) {
  const pg = d.pg, r = reglages.gomme;
  let touche = false;
  const reste = [];
  for (const s of pg.traits) {
    const pts = s.pts, rr = r + s.largeur_max / 2;
    let atteint = pts.length === 1 ? Math.hypot(pts[0].x - p.x, pts[0].y - p.y) < rr : false;
    for (let i = 1; !atteint && i < pts.length; i++) atteint = distSegment(p, pts[i - 1], pts[i]) < rr;
    if (!atteint) { reste.push(s); continue; }
    touche = true;
    const dense = densifier(pts, 1.5), morceaux = [];
    const entier = reglages.gommeMode === "trait";
    let courant = [];
    for (const q of entier ? [] : dense) {
      if (Math.hypot(q.x - p.x, q.y - p.y) < rr) { if (courant.length) morceaux.push(courant); courant = []; } else courant.push(q);
    }
    if (courant.length) morceaux.push(courant);
    const i = d.ajoutes.indexOf(s);
    if (i >= 0) d.ajoutes.splice(i, 1); else d.retires.push(s);
    for (const m of morceaux) {
      if (m.length < 2 && dense.length > 1) continue; // miettes d'un seul point
      const n = { ...s, id: FusionAnnotations.nouvelId(), pts: m }; reste.push(n); d.ajoutes.push(n);
    }
  }
  if (touche) { pg.traits = reste; redessiner(pg); marquerModifie(); }
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
$("exporter").onclick = async (e) => {
  e.preventDefault();
  if (await enregistrerAvant()) location.href = URL_EXPORT;
};
$("annuler").onclick = () => { const a = histoire.annuler.pop(); if (a) { appliquer(a, -1); histoire.retablir.push(a); majBoutons(); } };
$("retablir").onclick = () => { const a = histoire.retablir.pop(); if (a) { appliquer(a, +1); histoire.annuler.push(a); majBoutons(); } };

// ----- enregistrement dans le moteur -----
const arrondi = (n) => Math.round(n * 100) / 100;
// Révision et état connu du moteur à la dernière synchronisation (voir annotations-fusion.js).
let revision = 0, base = { ids: new Set(), supprimes: new Set() }, avisFusion = false;
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
  doc.supprimes = [...new Set([...base.ids, ...base.supprimes])].filter((id) => !presents.has(id));
  return doc;
}
function memoriserBase(doc) { // ce que le moteur a maintenant : sert à distinguer « effacé ici » de « ajouté ailleurs »
  revision = doc.revision;
  base = { ids: FusionAnnotations.identifiants(doc.pages), supprimes: new Set(doc.supprimes || []) };
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
  const fusion = FusionAnnotations.fusionner({ pages: serialiserPages() }, distant, base);
  chargerTraits({ pages: fusion.pages });
  memoriserBase({ revision: distant.revision, pages: distant.pages, supprimes: distant.supprimes });
  avisFusion = true;
}
let modifie = false, envoi = false, minuterie = null;
function etatSauvegarde(texte, erreur) { $("sauvegarde").textContent = texte; $("sauvegarde").classList.toggle("erreur", !!erreur); }
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
let largeurPile = 0, hauteurPile = 0, pincement = null, minuterieQualite = null;
function appliquerZoom(z) {
  zoom = Math.min(5, Math.max(0.3, z));
  taille.style.width = largeurPile * zoom + "px"; taille.style.height = hauteurPile * zoom + "px";
  pile.style.transform = `scale(${zoom})`;
  clearTimeout(minuterieQualite);
  minuterieQualite = setTimeout(() => pages.forEach((pg) => pg.actif && activer(pg)), 350);
}
function ajuster() {
  appliquerZoom(Math.min(2, (fenetre.clientWidth - 8) / largeurPile));
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
$("ajuster").onclick = ajuster;
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
const finPincement = (e) => { if (e.touches.length < 2) pincement = null; };
fenetre.addEventListener("touchend", finPincement); fenetre.addEventListener("touchcancel", finPincement);
new ResizeObserver(adapterALargeur).observe(fenetre);

// Page courante (indicateur), selon la page la plus proche du centre de la fenêtre.
let attenteDefilement = false;
fenetre.addEventListener("scroll", () => {
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
  document.title = `${$("titre").textContent} — Correction de labs`;
  try { // « Continuer » de l'accueil
    const sans = new URLSearchParams(location.search);
    sans.delete("panneau");
    localStorage.setItem("dernier", JSON.stringify({ cours: ref[0], groupe: ref[1], lab: ref[2], nom: params.get("nom"), url: `lecteur.html?${sans}` }));
  } catch { /* stockage indisponible */ }
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
    pages.push({ numero: i, w: vp.width, h: vp.height, pdf: pdfPage, el, traits: [], actif: false, R: 0 });
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
