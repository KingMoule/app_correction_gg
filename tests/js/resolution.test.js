// Tests de la résolution des canvas du lecteur (pwa/resolution.js). Lancés par tests/test_annotations_js.py.
const test = require("node:test");
const assert = require("node:assert");
const R = require("../../pwa/resolution.js");

const LETTRE = { w: 612, h: 792 };
const MAX_SURFACE_IOS = 16777216; // pixels d'un canvas d'iOS Safari

test("résolution voulue : zoom × densité, arrondie vers le haut, bornée", () => {
  assert.equal(R.resolutionVoulue(1, 2), 2);
  assert.equal(R.resolutionVoulue(1.1, 2), 2.25);
  assert.equal(R.resolutionVoulue(4, 2), 8);
  assert.equal(R.resolutionVoulue(5, 3), R.LIMITES.rMax);
  assert.equal(R.resolutionVoulue(0.3, 1), R.LIMITES.rMin);
  assert.equal(R.resolutionVoulue(2, undefined), 2);
});

test("page entière : sous le budget jusqu'à son plafond, plus de plafond fixe de 3", () => {
  const p = R.resolutionPlein(LETTRE.w, LETTRE.h);
  assert.ok(p >= 2 && p <= 3);
  assert.ok(LETTRE.w * LETTRE.h * p * p <= R.LIMITES.pixelsPlein);
});

test("zoom 1 sur écran densité 2 : page entière à 2×, sans zone", () => {
  const plan = R.planifier({ ...LETTRE, zoom: 1, dpr: 2, visible: { x: 0, y: 0, w: 612, h: 792 } });
  assert.deepEqual(plan, { R: 2, zone: null });
});

test("zoom 4 densité 2 : zone visible à la résolution de l'écran (8×), jamais la page entière", () => {
  const visible = { x: 100, y: 300, w: 205, h: 295 }; // 820 × 1180 px d'écran à zoom 4
  const plan = R.planifier({ ...LETTRE, zoom: 4, dpr: 2, visible });
  assert.equal(plan.R, 8);
  assert.ok(plan.zone);
  assert.ok(R.contient(plan.zone, visible));
  assert.ok(R.pixels(plan, LETTRE.w, LETTRE.h) <= R.LIMITES.pixelsZone);
  assert.ok(R.pixels(plan, LETTRE.w, LETTRE.h) < MAX_SURFACE_IOS / 2);
});

test("la zone grande est ramenée au budget, sans descendre sous la page entière", () => {
  const visible = { x: 0, y: 0, w: 612, h: 792 };
  const plan = R.planifier({ ...LETTRE, zoom: 3.5, dpr: 2, visible });
  assert.ok(R.pixels(plan, LETTRE.w, LETTRE.h) <= R.LIMITES.pixelsPlein * 1.05 || plan.zone);
  assert.ok(plan.R >= R.resolutionPlein(LETTRE.w, LETTRE.h));
});

test("page voisine (hors écran) : jamais au-delà d'une page entière", () => {
  const plan = R.planifier({ ...LETTRE, zoom: 4, dpr: 2, visible: null });
  assert.equal(plan.zone, null);
  assert.ok(R.pixels(plan, LETTRE.w, LETTRE.h) <= R.LIMITES.pixelsPlein);
});

test("budget : quel que soit le zoom, un canvas reste sous la moitié de la limite d'iOS", () => {
  for (const zoom of [0.3, 0.5, 1, 1.5, 2, 3, 4, 5]) for (const dpr of [1, 2, 3]) {
    for (const visible of [null, { x: 0, y: 0, w: 612 / zoom, h: 792 / zoom }, { x: 50, y: 60, w: 205, h: 295 }]) {
      const plan = R.planifier({ ...LETTRE, zoom, dpr, visible });
      assert.ok(R.pixels(plan, LETTRE.w, LETTRE.h) <= MAX_SURFACE_IOS / 2, `zoom ${zoom} dpr ${dpr}`);
    }
  }
});

test("zone agrandie : alignée sur 4, bornée à la page", () => {
  const z = R.agrandir({ x: 1, y: 1, w: 50, h: 50 }, 612, 792);
  assert.deepEqual([z.x % 4, z.y % 4, z.x, z.y], [0, 0, 0, 0]);
  const bord = R.agrandir({ x: 600, y: 780, w: 12, h: 12 }, 612, 792);
  assert.ok(bord.x + bord.w <= 612 && bord.y + bord.h <= 792);
});

test("zone visible : intersection de la fenêtre et de la page, en pixels de page", () => {
  // page à l'échelle 2, coin en (-100, -200) : la fenêtre voit de (100/2, 200/2)
  const page = { left: -100, top: -200, width: 1224, height: 1584 };
  const fenetre = { left: 0, top: 0, right: 400, bottom: 600 };
  assert.deepEqual(R.zoneVisible(page, fenetre, 612, 792), { x: 50, y: 100, w: 200, h: 300 });
  assert.equal(R.zoneVisible({ left: 0, top: 900, width: 612, height: 792 }, fenetre, 612, 792), null);
});

test("suffit : même résolution et zone qui couvre encore l'écran", () => {
  const visible = { x: 100, y: 300, w: 205, h: 295 };
  const plan = R.planifier({ ...LETTRE, zoom: 4, dpr: 2, visible });
  assert.ok(R.suffit(plan, plan, visible));
  assert.ok(R.suffit(plan, plan, { ...visible, x: visible.x + 5 }));
  assert.ok(!R.suffit(plan, plan, { ...visible, y: visible.y + 200 })); // l'écran est sorti de la zone
  assert.ok(!R.suffit(plan, { ...plan, R: 4 }, visible));
  assert.ok(!R.suffit(plan, { R: plan.R, zone: null }, visible));
  assert.ok(!R.suffit(null, plan, visible));
});
