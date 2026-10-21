// Tests de la fusion des annotations (pwa/annotations-fusion.js). Lancés par tests/test_annotations_js.py.
const test = require("node:test");
const assert = require("node:assert");
const { fusionner, nouvelId } = require("../../pwa/annotations-fusion.js");

const t = (id) => ({ id, outil: "crayon", couleur: "#d32f2f", largeur_min: 1, largeur_max: 3, courbe: 1, points: [[1, 2, 0.5]] });
const base = (ids, supprimes = []) => ({ ids: new Set(ids), supprimes: new Set(supprimes) });
const ids = (pages) => Object.values(pages).flat().map((x) => x.id).sort();

test("union : traits ajoutés sur deux appareils", () => {
  const f = fusionner({ pages: { 1: [t("a"), t("local")] } }, { pages: { 1: [t("a"), t("distant")] }, supprimes: [] }, base(["a"]));
  assert.deepStrictEqual(ids(f.pages), ["a", "distant", "local"]);
});

test("gommage ici : le trait reste effacé même si le moteur l'a encore", () => {
  const f = fusionner({ pages: {} }, { pages: { 1: [t("a"), t("distant")] }, supprimes: [] }, base(["a"]));
  assert.deepStrictEqual(ids(f.pages), ["distant"]);
  assert.deepStrictEqual(f.supprimes, ["a"]);
});

test("gommage ailleurs : le trait effacé ne revient pas", () => {
  const f = fusionner({ pages: { 1: [t("a"), t("local")] } }, { pages: { 1: [] }, supprimes: ["a"] }, base(["a"]));
  assert.deepStrictEqual(ids(f.pages), ["local"]);
  assert.deepStrictEqual(f.supprimes, ["a"]);
});

test("annuler un gommage déjà enregistré : le trait revient", () => {
  const f = fusionner({ pages: { 1: [t("a")] } }, { pages: {}, supprimes: ["a"] }, base([], ["a"]));
  assert.deepStrictEqual(ids(f.pages), ["a"]);
  assert.deepStrictEqual(f.supprimes, []);
});

test("gommage partiel : l'original est supprimé, les morceaux ajoutés", () => {
  const f = fusionner({ pages: { 1: [t("m1"), t("m2")] } }, { pages: { 1: [t("a")] }, supprimes: [] }, base(["a"]));
  assert.deepStrictEqual(ids(f.pages), ["m1", "m2"]);
  assert.deepStrictEqual(f.supprimes, ["a"]);
});

test("fusion répétée : idempotente, aucun doublon", () => {
  const local = { pages: { 1: [t("a"), t("l")] } };
  const distant = { pages: { 1: [t("a"), t("l")] }, supprimes: [] };
  assert.deepStrictEqual(ids(fusionner(local, distant, base(["a"])).pages), ["a", "l"]);
});

test("identifiants distincts", () => {
  assert.notStrictEqual(nouvelId(), nouvelId());
});
