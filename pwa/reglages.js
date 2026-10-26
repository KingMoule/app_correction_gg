// Page « Réglages » : seuil du plagiat (GET/PUT /api/plagiat/reglages) et style des références par cours de la session
// en cours (GET/PUT /api/references/style/<cours>). Mêmes routes que l'écran Plagiat et l'onglet Références : une seule valeur.
(() => {
  const el = (id) => document.getElementById(id);
  const sur = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };
  const json = (url, options) => fetch(url, options).then((r) => (r.ok ? r.json() : Promise.reject(r)));
  const put = (url, corps) => json(url, { method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps) });
  const echec = (message) => UI.toast(message, { erreur: true });

  // --- Plagiat ---
  const seuil = el("seuil");
  let seuilEnregistre = null;
  json("/api/plagiat/reglages").then((d) => {
    seuilEnregistre = Math.round(d.seuil * 100);
    seuil.value = seuilEnregistre; seuil.disabled = false;
  }).catch(() => echec("Seuil introuvable : le moteur répond-il ?"));
  seuil.onchange = async () => {
    const v = Math.round(Number(seuil.value));
    if (seuil.value.trim() === "" || Number.isNaN(v) || v < 0 || v > 100) {
      seuil.value = seuilEnregistre; echec("Le seuil est un pourcentage entre 0 et 100."); return;
    }
    try {
      const d = await put("/api/plagiat/reglages", { seuil: v / 100 });
      seuilEnregistre = Math.round(d.seuil * 100); seuil.value = seuilEnregistre;
      UI.toast("Enregistré");
    } catch { seuil.value = seuilEnregistre; echec("Seuil non enregistré."); }
  };

  // --- Style des références, par cours de la session en cours ---
  const zone = el("cours");
  const pluriel = (n, mot) => `${n} ${mot}${n > 1 ? "s" : ""}`;

  function ligne(c, info, s) {
    const l = sur("div", "rg-ligne rg-cours");
    const texte = sur("div", "rg-texte"), nom = sur("b", "", `${UI.titreCours(c).split(" · ")[0]} `);
    nom.append(sur("small", "", `· ${c.split("_")[1] ?? ""}`));
    const labs = new Set(info?.etudiants.flatMap((e) => e.labs) ?? []).size;
    texte.append(nom, sur("span", "mu", info ? `${pluriel(info.etudiants.length, "étudiant")} · ${pluriel(labs, "lab")}` : ""));
    const valeur = sur("div", "rg-valeur"), seg = sur("div", "seg");
    seg.setAttribute("role", "group"); seg.setAttribute("aria-label", `Style des références de ${UI.titreCours(c)}`);
    const boutons = Object.entries(s.styles).map(([cle, libelle]) => {
      const b = sur("button", "", libelle); b.type = "button"; b.dataset.style = cle; return b;
    });
    const marquer = (cle) => boutons.forEach((b) => { const on = b.dataset.style === cle; b.classList.toggle("on", on); b.setAttribute("aria-pressed", String(on)); });
    marquer(s.style);
    let courant = s.style;
    for (const b of boutons) b.onclick = async () => {
      if (b.dataset.style === courant) return;
      try {
        const r = await put(`/api/references/style/${encodeURIComponent(c)}`, { style: b.dataset.style });
        courant = r.style; marquer(courant); UI.toast("Enregistré");
      } catch { marquer(courant); echec("Style non enregistré."); }
    };
    seg.append(...boutons); valeur.append(seg); l.append(texte, valeur);
    return l;
  }

  async function cours() {
    try {
      const [sess, arbre] = await Promise.all([json("/api/bibliotheque/sessions"), json("/api/bibliotheque")]);
      const courante = sess.sessions.find((x) => x.courante);
      const liste = courante?.cours ?? [];
      el("h-ref").textContent = `Style des références · ${courante ? courante.libelle : ""}`.replace(/ · $/, "");
      if (!liste.length) {
        const icone = UI.icone("graduation-cap");
        const a = sur("a", "btn primaire", "Importer une liste"); a.href = "/#importer";
        zone.className = "vide rg-carte";
        zone.replaceChildren(icone, sur("p", "", "Aucun cours pour l'instant : importe d'abord une liste de classe."), a);
        return;
      }
      const styles = await Promise.all(liste.map((c) => json(`/api/references/style/${encodeURIComponent(c)}`)));
      zone.className = "rg-carte";
      zone.replaceChildren(...liste.map((c, i) => ligne(c, arbre.find((x) => x.cours === c), styles[i])));
      el("note-ref").hidden = false;
    } catch { zone.replaceChildren(sur("p", "rg-ligne mu", "Cours introuvables : le moteur répond-il ?")); }
  }
  cours();
})();
