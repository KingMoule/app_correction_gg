// Zoom à deux doigts du lecteur : calcul pur, sans DOM (testé avec Node, tests/js/pincement.test.js).
// Le point du document sous le milieu des doigts au début du geste (l'ancre, en pixels de `#taille` à zoom 1)
// reste sous le milieu COURANT des doigts : la position de défilement est recalculée en absolu à chaque
// mouvement, jamais corrigée par petites touches (le navigateur arrondit `scrollTop`, l'erreur s'accumulerait).
(function (racine) {
  "use strict";

  const bornes = (v, min, max) => Math.min(max, Math.max(min, v));

  // Ancre : point du document (unités de zoom 1) sous le milieu des doigts. `taille` : rectangle de #taille à l'écran.
  const ancre = (milieu, taille, zoom) => ({ x: (milieu.x - taille.left) / zoom, y: (milieu.y - taille.top) / zoom });

  // Zoom demandé par l'écart des doigts.
  const zoomCible = (zoomDebut, ecartDebut, ecart, min, max) => bornes((zoomDebut * ecart) / ecartDebut, min, max);

  // Position de défilement qui garde l'ancre sous le milieu des doigts.
  // `origine` : coin de #taille dans le contenu défilant, au zoom `zoom` (rect.left - fenetre.left + scrollLeft).
  // `fenetre` : coin de la zone de défilement à l'écran; `max` : défilement maximal { x, y }.
  function defilement(a, zoom, milieu, origine, fenetre, max) {
    return {
      left: bornes(origine.x + a.x * zoom - (milieu.x - fenetre.left), 0, max.x),
      top: bornes(origine.y + a.y * zoom - (milieu.y - fenetre.top), 0, max.y),
    };
  }

  // Les deux premiers doigts (le Pencil, touchType « stylus », ne pince jamais).
  const doigts = (touches) => [...touches].filter((t) => t.touchType !== "stylus").slice(0, 2);
  const milieuDe = (d) => ({ x: (d[0].clientX + d[1].clientX) / 2, y: (d[0].clientY + d[1].clientY) / 2 });
  const ecartDe = (d) => Math.hypot(d[0].clientX - d[1].clientX, d[0].clientY - d[1].clientY);

  const API = { ancre, zoomCible, defilement, doigts, milieuDe, ecartDe };
  racine.Pincement = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : globalThis);
