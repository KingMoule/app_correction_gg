// Tests du zoom à deux doigts (pwa/pincement.js) : le point du document sous le milieu des doigts reste sous eux.
// Modèle du navigateur : #taille centrée (margin auto) sous 12 px de marge, défilement arrondi (comme Safari),
// et du défilement natif parasite qui s'ajoute entre deux mouvements.
const test = require("node:test");
const assert = require("node:assert");
const P = require("../../pwa/pincement.js");

const FEN = { left: 60, top: 50, w: 760, h: 700 }; // zone de défilement à l'écran
const PAGE = { w: 612, h: 792, n: 5, espace: 12 }; // 5 pages lettre
const HAUT = PAGE.n * (PAGE.h + PAGE.espace);

function navigateur(zoomInitial, scrollInitial, arrondi) {
  const nav = { zoom: zoomInitial, sx: 0, sy: 0 };
  const largeur = () => PAGE.w * nav.zoom, hauteur = () => HAUT * nav.zoom;
  const contenuW = () => Math.max(FEN.w, largeur()), contenuH = () => 12 + hauteur() + 350;
  nav.max = () => ({ x: contenuW() - FEN.w, y: contenuH() - FEN.h });
  nav.fixer = (x, y) => { // scrollLeft / scrollTop : borné puis arrondi
    const m = nav.max();
    nav.sx = arrondi(Math.min(m.x, Math.max(0, x))); nav.sy = arrondi(Math.min(m.y, Math.max(0, y)));
  };
  nav.origine = () => ({ x: Math.max(0, (FEN.w - largeur()) / 2), y: 12 }); // #taille dans le contenu
  nav.rect = () => { const o = nav.origine(); return { left: FEN.left + o.x - nav.sx, top: FEN.top + o.y - nav.sy }; };
  nav.fixer(...scrollInitial);
  return nav;
}

// Simule un pincement : l'écart des doigts grandit (ou rétrécit) et leur milieu se déplace. Rend l'écart maximal
// (en px) entre le point du document visé et le milieu des doigts, pendant et après le geste.
function pincer({ zoom0, scroll0, depart, facteur, deplacement, pas = 60, arrondi = Math.floor, parasite = 0 }) {
  const nav = navigateur(zoom0, scroll0, arrondi);
  const d0 = 120, a = P.ancre(depart, nav.rect(), nav.zoom);
  let pire = 0;
  for (let i = 1; i <= pas; i++) {
    const t = i / pas, milieu = { x: depart.x + deplacement.x * t, y: depart.y + deplacement.y * t };
    nav.zoom = P.zoomCible(zoom0, d0, d0 * Math.pow(facteur, t), 0.3, 5);
    const r = nav.rect(), o = { x: r.left - FEN.left + nav.sx, y: r.top - FEN.top + nav.sy };
    const c = P.defilement(a, nav.zoom, milieu, o, FEN, nav.max());
    nav.fixer(c.left, c.top);
    // le point du document visé, tel qu'il est à l'écran
    const r2 = nav.rect(), ecran = { x: r2.left + a.x * nav.zoom, y: r2.top + a.y * nav.zoom };
    const m = nav.max(), horsBornes = c.top <= 0 || c.top >= m.y || c.left <= 0 || c.left >= m.x;
    if (!horsBornes) pire = Math.max(pire, Math.hypot(ecran.x - milieu.x, ecran.y - milieu.y));
    if (parasite) nav.fixer(nav.sx + (i % 2 ? parasite : -parasite), nav.sy + (i % 2 ? parasite : -parasite) * 3); // défilement natif entre deux mouvements
  }
  return pire;
}

// départs : haut, milieu et bas d'une page, page 3 ; zooms de départ variés
const POSITIONS = [
  ["haut de la page 1", [0, 0]],
  ["milieu de la page 1", [0, 380]],
  ["bas de la page 1", [0, 780]],
  ["page 3", [40, 2 * 804 + 300]],
];
for (const [nom, scroll0] of POSITIONS) for (const zoom0 of [0.8, 1.1, 2, 3.5]) {
  test(`le point sous les doigts reste sous les doigts : ${nom}, zoom de départ ${zoom0}`, () => {
    const depart = { x: FEN.left + 380, y: FEN.top + 300 };
    for (const facteur of [2.2, 1.6, 0.6]) {
      for (const arrondi of [Math.floor, Math.round, Math.ceil]) {
        const e = pincer({ zoom0, scroll0, depart, facteur, deplacement: { x: -40, y: 55 }, arrondi });
        assert.ok(e < 2, `écart ${e.toFixed(2)} px (facteur ${facteur})`);
      }
    }
  });
}

test("milieu immobile, sans déplacement : l'écart reste sous 2 px même avec un arrondi vers le bas", () => {
  const e = pincer({ zoom0: 1, scroll0: [0, 1200], depart: { x: 440, y: 350 }, facteur: 3, deplacement: { x: 0, y: 0 }, pas: 200 });
  assert.ok(e < 2, String(e));
});

test("du défilement natif parasite entre deux mouvements ne fait pas dériver le geste", () => {
  const e = pincer({ zoom0: 1.5, scroll0: [0, 1500], depart: { x: 440, y: 350 }, facteur: 2, deplacement: { x: 10, y: -20 }, pas: 120, parasite: 1.5 });
  assert.ok(e < 4, String(e)); // l'erreur d'un mouvement n'est jamais reportée sur le suivant
});

test("l'ancienne correction par petites touches dérivait (arrondi vers le haut ou vers le bas à chaque mouvement)", () => {
  for (const [arrondi, sens] of [[Math.floor, "haut"], [Math.ceil, "bas"]]) {
    const nav = navigateur(1, [0, 1200], arrondi), c = { x: 440, y: 350 }, a = P.ancre(c, nav.rect(), 1);
    for (let i = 0; i < 200; i++) { // scroll += écart constaté, relu après arrondi
      const r = nav.rect(), ux = (c.x - r.left) / nav.zoom, uy = (c.y - r.top) / nav.zoom;
      nav.zoom = 1 + (i + 1) * 0.01;
      const r2 = nav.rect();
      nav.fixer(nav.sx + r2.left + ux * nav.zoom - c.x, nav.sy + r2.top + uy * nav.zoom - c.y);
    }
    const r = nav.rect(), ecart = Math.abs(r.top + a.y * nav.zoom - c.y);
    assert.ok(ecart > 2, `dérive vers le ${sens} : ${ecart.toFixed(1)} px`);
  }
});

test("doigts : le Pencil est ignoré, deux doigts seulement", () => {
  const t = (x, y, type = "direct") => ({ clientX: x, clientY: y, touchType: type });
  const d = P.doigts([t(0, 0), t(10, 0, "stylus"), t(20, 0), t(40, 0)]);
  assert.equal(d.length, 2);
  assert.deepEqual(P.milieuDe(d), { x: 10, y: 0 });
  assert.equal(P.ecartDe(d), 20);
  assert.equal(P.doigts([t(0, 0), t(5, 5, "stylus")]).length, 1);
});

test("zoom cible borné", () => {
  assert.equal(P.zoomCible(1, 100, 1000, 0.3, 5), 5);
  assert.equal(P.zoomCible(1, 100, 1, 0.3, 5), 0.3);
});
