// Résolution des canvas du lecteur : fonctions pures, sans DOM (testées avec Node, tests/js/resolution.test.js).
// Une page est dessinée à la résolution de l'écran (zoom × densité de pixels). Quand la page entière dépasserait le
// budget de pixels, seule la zone visible (avec une marge) est dessinée à cette résolution; la page entière reste
// en résolution de base dessous. Rectangles en pixels de la page (points PDF à l'échelle 1) : { x, y, w, h }.
(function (racine) {
  "use strict";

  // Limites vérifiées (iOS Safari rejette un canvas de plus de 16 777 216 pixels, et la mémoire totale des canvas
  // est plafonnée, de 224 à 384 Mo selon l'appareil et la version) : on reste bien en dessous.
  const LIMITES = {
    pixelsPlein: 3e6, // page entière : ≈ 12 Mo par couche (une lettre : jusqu'à 2,5×)
    pixelsZone: 6e6, // zone visible : ≈ 24 Mo par couche
    rMin: 1,
    rMax: 8,
    marge: 0.08, // part de la zone visible ajoutée de chaque côté
    pas: 0.25, // la résolution est arrondie à ce pas
  };

  const bas = (r, pas) => Math.floor(r / pas + 1e-9) * pas;

  // Résolution voulue : celle de l'écran (zoom × densité), arrondie vers le haut.
  function resolutionVoulue(zoom, dpr, lim = LIMITES) {
    const r = Math.ceil((zoom * (dpr || 1)) / lim.pas - 1e-9) * lim.pas;
    return Math.min(lim.rMax, Math.max(lim.rMin, r));
  }

  // Résolution la plus haute d'une page entière dans le budget.
  function resolutionPlein(w, h, lim = LIMITES) {
    return Math.max(lim.rMin, bas(Math.sqrt(lim.pixelsPlein / (w * h)), lim.pas));
  }

  // Zone visible agrandie de la marge, alignée sur 4 pixels de page et bornée à la page.
  function agrandir(visible, w, h, lim = LIMITES) {
    const mx = visible.w * lim.marge, my = visible.h * lim.marge;
    const x0 = Math.max(0, Math.floor((visible.x - mx) / 4) * 4), y0 = Math.max(0, Math.floor((visible.y - my) / 4) * 4);
    const x1 = Math.min(w, Math.ceil((visible.x + visible.w + mx) / 4) * 4), y1 = Math.min(h, Math.ceil((visible.y + visible.h + my) / 4) * 4);
    return { x: x0, y: y0, w: x1 - x0, h: y1 - y0 };
  }

  const contient = (zone, r, eps = 0.5) =>
    !!zone && !!r && r.x >= zone.x - eps && r.y >= zone.y - eps && r.x + r.w <= zone.x + zone.w + eps && r.y + r.h <= zone.y + zone.h + eps;

  // Intersection d'un rectangle d'écran (fenêtre) avec la page, en pixels de page; null si la page n'est pas à l'écran.
  // `page` : rectangle de la page à l'écran (getBoundingClientRect), `fenetre` : idem pour la zone de défilement.
  function zoneVisible(page, fenetre, w, h) {
    if (!page.width || !page.height) return null;
    const ex = page.width / w, ey = page.height / h;
    const x0 = Math.max(0, (fenetre.left - page.left) / ex), y0 = Math.max(0, (fenetre.top - page.top) / ey);
    const x1 = Math.min(w, (fenetre.right - page.left) / ex), y1 = Math.min(h, (fenetre.bottom - page.top) / ey);
    return x1 > x0 && y1 > y0 ? { x: x0, y: y0, w: x1 - x0, h: y1 - y0 } : null;
  }

  // Plan d'une page : { R, zone } (zone null = page entière). `visible` null : page voisine (hors de l'écran),
  // jamais au-delà de la résolution d'une page entière.
  function planifier({ w, h, zoom, dpr, visible }, lim = LIMITES) {
    const voulue = resolutionVoulue(zoom, dpr, lim), plein = resolutionPlein(w, h, lim);
    if (!visible || voulue <= plein) return { R: Math.min(voulue, plein), zone: null };
    const zone = agrandir(visible, w, h, lim), aire = zone.w * zone.h;
    const R = Math.max(plein, Math.min(voulue, bas(Math.sqrt(lim.pixelsZone / aire), lim.pas)));
    return { R, zone };
  }

  // Le plan en place suffit-il pour ce plan voulu ? (même résolution, zone qui couvre encore l'écran)
  function suffit(actuel, voulu, visible) {
    if (!actuel || actuel.R !== voulu.R) return false;
    if (!voulu.zone) return !actuel.zone;
    return !!actuel.zone && (!visible || contient(actuel.zone, visible));
  }

  // Pixels d'un canvas pour un plan (une couche).
  const pixels = (plan, w, h) => (plan.zone ? plan.zone.w * plan.zone.h : w * h) * plan.R * plan.R;

  const API = { LIMITES, resolutionVoulue, resolutionPlein, agrandir, contient, zoneVisible, planifier, suffit, pixels };
  racine.Resolution = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : globalThis);
