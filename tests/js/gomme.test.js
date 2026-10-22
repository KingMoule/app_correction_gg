// Tests de la gomme partielle (pwa/gomme.js). Lancés par tests/test_annotations_js.py.
const test = require("node:test");
const assert = require("node:assert");
const { couper, gommer } = require("../../pwa/gomme.js");
const { fusionner } = require("../../pwa/annotations-fusion.js");

let compteur = 0;
const nouvelId = () => "n" + ++compteur;
// Trait horizontal de x = 0 à 100 (y = 10), un point tous les 10, pression croissante.
const ligne = (id = "a", extra = {}) => ({
  id, outil: "crayon", couleur: "#d32f2f", courbe: 1, largeur_min: 0.6, largeur_max: 2,
  pts: Array.from({ length: 11 }, (_, i) => ({ x: i * 10, y: 10, p: i / 10 })), ...extra,
});
const etat = () => ({ retires: [], ajoutes: [] });
const xs = (m) => [Math.min(...m.map((q) => q.x)), Math.max(...m.map((q) => q.x))];

test("coupe au milieu : deux morceaux, l'original est retiré, attributs gardés", () => {
  const s = ligne(), e = etat();
  const r = gommer([s], { x: 50, y: 10 }, 5, e, nouvelId);
  assert.strictEqual(r.length, 2);
  assert.deepStrictEqual(e.retires, [s]);
  assert.strictEqual(e.ajoutes.length, 2);
  for (const m of r) {
    assert.notStrictEqual(m.id, "a");
    assert.strictEqual(m.couleur, "#d32f2f"); assert.strictEqual(m.outil, "crayon");
    assert.strictEqual(m.largeur_min, 0.6); assert.strictEqual(m.largeur_max, 2); assert.strictEqual(m.courbe, 1);
  }
  const [g, d] = r.map((m) => xs(m.pts));
  assert.strictEqual(g[0], 0); assert.ok(g[1] < 50 - 5 && g[1] > 40);
  assert.ok(d[0] > 55 && d[0] < 60); assert.strictEqual(d[1], 100);
  assert.ok(r[0].id !== r[1].id);
});

test("la pression est conservée (points d'origine et interpolés)", () => {
  const r = gommer([ligne()], { x: 50, y: 10 }, 5, etat(), nouvelId);
  assert.strictEqual(r[0].pts[0].p, 0);
  assert.strictEqual(r[1].pts[r[1].pts.length - 1].p, 1);
  for (const m of r) for (const q of m.pts) assert.ok(Math.abs(q.p - q.x / 100) < 1e-9);
});

test("coupe au début : un seul morceau, la fin reste", () => {
  const r = gommer([ligne()], { x: 0, y: 10 }, 6, etat(), nouvelId);
  assert.strictEqual(r.length, 1);
  assert.ok(xs(r[0].pts)[0] > 7); assert.strictEqual(xs(r[0].pts)[1], 100);
});

test("coupe à la fin : un seul morceau, le début reste", () => {
  const r = gommer([ligne()], { x: 100, y: 10 }, 6, etat(), nouvelId);
  assert.strictEqual(r.length, 1);
  assert.strictEqual(xs(r[0].pts)[0], 0); assert.ok(xs(r[0].pts)[1] < 93);
});

test("gommer tout le trait : plus rien, l'original est retiré", () => {
  const e = etat();
  const r = gommer([ligne()], { x: 50, y: 10 }, 80, e, nouvelId);
  assert.deepStrictEqual(r, []);
  assert.strictEqual(e.retires.length, 1); assert.strictEqual(e.ajoutes.length, 0);
});

test("morceau trop court supprimé", () => {
  const s = ligne("c", { pts: [{ x: 0, y: 10, p: 0.5 }, { x: 0.4, y: 10, p: 0.5 }, { x: 30, y: 10, p: 0.5 }] });
  const r = gommer([s], { x: 15, y: 10 }, 12, etat(), nouvelId); // reste [0..0.4] hors gomme: trop court
  assert.ok(r.every((m) => xs(m.pts)[1] - xs(m.pts)[0] >= 1));
});

test("trait loin de la gomme : intact, null, objets identiques", () => {
  const s = ligne();
  assert.strictEqual(gommer([s], { x: 50, y: 60 }, 5, etat(), nouvelId), null);
  assert.strictEqual(couper(s, { x: 500, y: 10 }, 5), null);
});

test("point isolé touché : supprimé", () => {
  const s = ligne("p", { pts: [{ x: 5, y: 5, p: 0.5 }] });
  const r = gommer([s], { x: 6, y: 5 }, 3, etat(), nouvelId);
  assert.deepStrictEqual(r, []);
});

test("plusieurs traits sous la gomme : seuls les touchés changent, ordre gardé", () => {
  const a = ligne("a"), b = ligne("b", { pts: a.pts.map((q) => ({ ...q, y: 14 })) });
  const loin = ligne("loin", { pts: a.pts.map((q) => ({ ...q, y: 90 })) });
  const e = etat();
  const r = gommer([a, loin, b], { x: 50, y: 12 }, 6, e, nouvelId);
  assert.deepStrictEqual(e.retires, [a, b]);
  assert.strictEqual(r.length, 5);
  assert.strictEqual(r[2], loin);
  assert.ok(r.slice(0, 2).every((m) => m.pts[0].y === 10) && r.slice(3).every((m) => m.pts[0].y === 14));
});

test("geste en plusieurs passages : un morceau recoupé n'est pas compté comme original", () => {
  const s = ligne(), e = etat();
  let traits = gommer([s], { x: 50, y: 10 }, 5, e, nouvelId);
  traits = gommer(traits, { x: 20, y: 10 }, 5, e, nouvelId);
  assert.deepStrictEqual(e.retires, [s]); // seul l'original est retiré
  assert.strictEqual(traits.length, 3);
  const ids = (l) => l.map((t) => t.id).sort();
  assert.deepStrictEqual(ids(e.ajoutes), ids(traits));
});

// Annuler / rétablir : réplique de `appliquer` de lecteur.js pour un passage de gomme (une seule action).
function defaire(traits, a) { return traits.filter((s) => !a.ajoutes.includes(s)).concat(a.retires); }
function refaire(traits, a) { return traits.filter((s) => !a.retires.includes(s)).concat(a.ajoutes); }

test("annuler puis rétablir un passage : un seul pas, mêmes objets", () => {
  const s = ligne(), e = etat();
  let traits = gommer([s], { x: 50, y: 10 }, 5, e, nouvelId);
  traits = gommer(traits, { x: 80, y: 10 }, 5, e, nouvelId); // même geste
  const apres = traits.slice();
  traits = defaire(traits, e);
  assert.deepStrictEqual(traits, [s]);
  traits = refaire(traits, e);
  assert.deepStrictEqual(traits.slice().sort((x, y) => x.id.localeCompare(y.id)), apres.sort((x, y) => x.id.localeCompare(y.id)));
});

test("boîte englobante recalculée si le trait change (surligneur redressé)", () => {
  const s = ligne("h", { outil: "surligneur", pts: [{ x: 0, y: 0, p: 0.5 }, { x: 10, y: 0, p: 0.5 }] });
  assert.strictEqual(couper(s, { x: 90, y: 0 }, 3), null);
  s.pts = [s.pts[0], { x: 100, y: 0, p: 0.5 }];
  const m = couper(s, { x: 90, y: 0 }, 3);
  assert.ok(m && m.length === 2);
});

test("fusion : trait coupé ici pendant qu'un autre appareil ajoute un trait", () => {
  const ser = (t) => ({ id: t.id, points: [[0, 0, 0.5]] });
  const s = ligne("a"), e = etat();
  const traits = gommer([s], { x: 50, y: 10 }, 5, e, nouvelId);
  const local = { pages: { 1: traits.map(ser) } };
  const distant = { pages: { 1: [ser(s), { id: "pc" }] }, supprimes: [] };
  const f = fusionner(local, distant, { ids: new Set(["a"]), supprimes: new Set() });
  const ids = f.pages[1].map((t) => t.id).sort();
  assert.deepStrictEqual(ids, [...traits.map((t) => t.id), "pc"].sort());
  assert.deepStrictEqual(f.supprimes, ["a"]);
});

test("performance : 300 traits dont un seul sous la gomme", () => {
  const traits = Array.from({ length: 300 }, (_, i) => ligne("t" + i, { pts: ligne().pts.map((q) => ({ ...q, y: 20 + i * 3 })) }));
  couper(traits[0], { x: 0, y: 0 }, 5); // chauffe
  const t0 = process.hrtime.bigint();
  for (let k = 0; k < 100; k++) gommer(traits, { x: 50, y: 20 + 150 * 3 }, 5, etat(), nouvelId);
  const ms = Number(process.hrtime.bigint() - t0) / 1e6;
  assert.ok(ms < 200, `${ms} ms pour 100 passages`);
});
