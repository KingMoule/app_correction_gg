// Fusion des annotations de deux appareils (audit E2). Fonctions pures, sans DOM : testées avec Node
// (tests/js/annotations-fusion.test.js). Un trait est identifié par un `id` stable; les traits effacés
// sont gardés dans `supprimes` (pierres tombales) pour qu'un gommage survive à la fusion.
(function (racine) {
  "use strict";

  // Identifiant aléatoire (crypto.randomUUID n'existe pas en http sur le réseau local).
  function nouvelId() {
    const c = racine.crypto;
    if (c && c.getRandomValues) {
      const o = new Uint8Array(8); c.getRandomValues(o);
      return Array.from(o, (b) => b.toString(16).padStart(2, "0")).join("");
    }
    return Date.now().toString(16) + Math.random().toString(16).slice(2, 10);
  }

  const identifiants = (pages) => new Set(Object.values(pages).flat().map((t) => t.id));

  // local, distant : { pages: {"1": [trait]}, supprimes?: [id] } (traits sérialisés, avec `id`).
  // base : { ids: Set, supprimes: Set } = ce que ce lecteur savait du moteur à la dernière synchronisation.
  // Règles : un trait est gardé s'il est dans le moteur ou ajouté ici, sauf s'il a été effacé ici
  // (dans la base mais plus dans local) ou effacé ailleurs depuis la base (nouvelle pierre tombale).
  // Un trait effacé ici puis rétabli par « annuler » est de nouveau dans local : il revient.
  function fusionner(local, distant, base) {
    const idsLocaux = identifiants(local.pages);
    const effacesIci = new Set([...base.ids].filter((id) => !idsLocaux.has(id)));
    const pierresDistantes = new Set(distant.supprimes || []);
    const effacesAilleurs = new Set([...pierresDistantes].filter((id) => !base.supprimes.has(id)));
    const idsDistants = identifiants(distant.pages);
    const pages = {};
    for (const [n, traits] of Object.entries(distant.pages)) {
      const gardes = traits.filter((t) => !effacesIci.has(t.id));
      if (gardes.length) pages[n] = gardes;
    }
    for (const [n, traits] of Object.entries(local.pages)) {
      for (const t of traits) {
        if (idsDistants.has(t.id) || effacesAilleurs.has(t.id)) continue;
        (pages[n] = pages[n] || []).push(t);
      }
    }
    const presents = identifiants(pages);
    const supprimes = [...new Set([...pierresDistantes, ...effacesIci])].filter((id) => !presents.has(id));
    return { pages, supprimes };
  }

  const API = { nouvelId, fusionner, identifiants };
  racine.FusionAnnotations = API;
  if (typeof module !== "undefined" && module.exports) module.exports = API;
})(typeof window !== "undefined" ? window : globalThis);
