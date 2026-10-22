// Gomme partielle du lecteur : fonctions pures, sans DOM (testées avec Node, tests/js/gomme.test.js).
// Les points couverts par la gomme (rayon + demi-largeur du trait, en points PDF) disparaissent; le trait
// est coupé en morceaux qui gardent outil, couleur, largeurs, courbe et pression, avec de nouveaux `id`.
(function (racine) {
  "use strict";

  const PAS = 1.5; // espacement des points d'essai le long d'un segment touché, en points PDF
  const LONGUEUR_MIN = 1; // un morceau plus court (en points PDF) est supprimé

  function distSegment(p, a, b) {
    const dx = b.x - a.x, dy = b.y - a.y, l2 = dx * dx + dy * dy;
    const u = l2 ? Math.max(0, Math.min(1, ((p.x - a.x) * dx + (p.y - a.y) * dy) / l2)) : 0;
    return Math.hypot(p.x - (a.x + u * dx), p.y - (a.y + u * dy));
  }

  // Boîte englobante des points, gardée sur le trait et recalculée si les points ont changé.
  function boite(s) {
    const pts = s.pts, b = s.boite;
    if (b && b.n === pts.length && b.dernier === pts[pts.length - 1]) return b;
    let x0 = Infinity, y0 = Infinity, x1 = -Infinity, y1 = -Infinity;
    for (const q of pts) { if (q.x < x0) x0 = q.x; if (q.x > x1) x1 = q.x; if (q.y < y0) y0 = q.y; if (q.y > y1) y1 = q.y; }
    return (s.boite = { x0, y0, x1, y1, n: pts.length, dernier: pts[pts.length - 1] });
  }

  const longueur = (m) => { let l = 0; for (let i = 1; i < m.length; i++) l += Math.hypot(m[i].x - m[i - 1].x, m[i].y - m[i - 1].y); return l; };

  // Morceaux de `s` qui restent hors du disque (p, rayon) : null si le trait n'est pas touché.
  function couper(s, p, rayon) {
    const rr = rayon + s.largeur_max / 2, pts = s.pts;
    const b = boite(s);
    if (p.x < b.x0 - rr || p.x > b.x1 + rr || p.y < b.y0 - rr || p.y > b.y1 + rr) return null;
    const dedans = (q) => Math.hypot(q.x - p.x, q.y - p.y) < rr;
    const morceaux = [];
    let courant = [], touche = false;
    const garder = (q) => courant.push(q);
    const trou = () => { touche = true; if (courant.length) morceaux.push(courant); courant = []; };
    if (dedans(pts[0])) trou(); else garder(pts[0]);
    for (let i = 1; i < pts.length; i++) {
      const a = pts[i - 1], c = pts[i];
      if (distSegment(p, a, c) < rr) { // segment proche de la gomme : points d'essai intermédiaires
        const n = Math.ceil(Math.hypot(c.x - a.x, c.y - a.y) / PAS);
        for (let k = 1; k < n; k++) {
          const f = k / n, q = { x: a.x + (c.x - a.x) * f, y: a.y + (c.y - a.y) * f, p: a.p + (c.p - a.p) * f };
          if (dedans(q)) trou(); else garder(q);
        }
      }
      if (dedans(c)) trou(); else garder(c);
    }
    if (!touche) return null;
    if (courant.length) morceaux.push(courant);
    return morceaux.filter((m) => m.length > 1 && longueur(m) >= LONGUEUR_MIN);
  }

  // Passe la gomme en p sur `traits`. `etat` ({ retires, ajoutes }) accumule le passage entier :
  // un trait d'origine coupé va dans `retires`, un morceau déjà créé pendant ce passage est simplement remplacé.
  // Renvoie la nouvelle liste (ordre gardé), ou null si rien n'est touché.
  function gommer(traits, p, rayon, etat, nouvelId) {
    const sortie = [];
    let touche = false;
    for (const s of traits) {
      const morceaux = couper(s, p, rayon);
      if (!morceaux) { sortie.push(s); continue; }
      touche = true;
      const k = etat.ajoutes.indexOf(s);
      if (k >= 0) etat.ajoutes.splice(k, 1); else etat.retires.push(s);
      for (const m of morceaux) {
        const n = { id: nouvelId(), outil: s.outil, couleur: s.couleur, courbe: s.courbe, largeur_min: s.largeur_min, largeur_max: s.largeur_max, pts: m };
        sortie.push(n); etat.ajoutes.push(n);
      }
    }
    return touche ? sortie : null;
  }

  const API = { couper, gommer, distSegment };
  racine.Gomme = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : globalThis);
