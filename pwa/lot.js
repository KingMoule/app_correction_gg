// Écran « Analyse par lot » : lance, suit et arrête l'analyse Claude de plusieurs rapports d'un lab.
(() => {
  const el = (id) => document.getElementById(id);
  let minuteur = null;

  const noeud = (tag, contenu) => {
    const n = document.createElement(tag);
    n.textContent = contenu; // jamais de HTML : les noms viennent de la bibliothèque
    return n;
  };
  const erreur = async (r) => (await r.json().catch(() => ({}))).detail || `Erreur ${r.status}`;
  const labChoisi = () => {
    const v = el("lot-lab").value;
    return v ? JSON.parse(v) : null;
  };
  const url = (l, debut = "/api/lot") => `${debut}/${[l.cours, l.groupe, l.lab].map(encodeURIComponent).join("/")}`;

  window.rafraichirLot = (arbre) => {
    const courant = el("lot-lab").value;
    const options = [];
    for (const c of arbre) {
      const labs = new Set(c.etudiants.flatMap((e) => e.labs));
      for (const lab of [...labs].sort()) {
        const o = noeud("option", `${c.cours} · groupe ${c.groupe} · ${lab}`);
        o.value = JSON.stringify({ cours: c.cours, groupe: c.groupe, lab });
        options.push(o);
      }
    }
    el("lot-lab").replaceChildren(...options);
    if (courant && options.some((o) => o.value === courant)) el("lot-lab").value = courant;
    apercu();
  };

  async function apercu() {
    const l = labChoisi();
    el("lot-apercu").textContent = "";
    if (!l) return;
    try {
      const r = await fetch(`${url(l, "/api/lot/apercu")}?refaire=${el("lot-refaire").checked}`);
      if (!r.ok) return;
      const d = await r.json();
      el("lot-apercu").textContent = `${d.a_analyser} rapport(s) à analyser sur ${d.total}.`;
    } catch { /* moteur injoignable : l'état général l'indique déjà */ }
  }

  const LIBELLES = { en_cours: "En cours", termine: "Terminé", arrete: "Arrêté", limite: "Limite d'usage atteinte", erreur: "Arrêté sur erreur" };

  function afficher(e) {
    const actif = e.statut === "en_cours";
    el("lot-lancer").disabled = actif;
    el("lot-arreter").hidden = !actif;
    el("lot-barre").hidden = !e.total;
    if (e.total) { el("lot-barre").max = e.total; el("lot-barre").value = e.fait; }
    if (!e.total) { el("lot-etat").textContent = ""; el("lot-erreurs").replaceChildren(); return; }
    const suite = actif && e.courant ? ` · en cours : ${e.courant}` : "";
    el("lot-etat").textContent = `${LIBELLES[e.statut] ?? e.statut} : ${e.fait} / ${e.total}${suite}. ${e.message || ""}`;
    el("lot-erreurs").replaceChildren(...e.erreurs.map((x) => noeud("li", `${x.nom} : ${x.message}`)));
  }

  async function suivre() {
    clearTimeout(minuteur);
    try {
      const e = await (await fetch("/api/lot")).json();
      afficher(e);
      if (e.statut === "en_cours") minuteur = setTimeout(suivre, 2000);
      else if (e.total) apercu();
    } catch {
      el("lot-etat").textContent = "Moteur injoignable.";
      minuteur = setTimeout(suivre, 5000);
    }
  }

  el("lot-lab").onchange = apercu;
  el("lot-refaire").onchange = apercu;

  el("lot-lancer").onclick = async () => {
    const l = labChoisi();
    if (!l) return;
    const n = Math.max(1, Math.min(200, parseInt(el("lot-n").value, 10) || 10));
    const r = await fetch(url(l), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ n, refaire: el("lot-refaire").checked }),
    });
    if (!r.ok) { el("lot-etat").textContent = await erreur(r); return; }
    suivre();
  };

  el("lot-arreter").onclick = async () => {
    await fetch("/api/lot/arreter", { method: "POST" });
    suivre();
  };

  suivre(); // reprend l'affichage d'un lot déjà en cours après un rechargement de la page
})();
