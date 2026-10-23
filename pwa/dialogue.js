// Boîtes de dialogue de la direction Atelier (PR 3/4) : remplacent confirm() et prompt() du navigateur.
//   Dialogue.confirmer({ titre, texte, ok, annuler, danger }) -> Promise<boolean>
//   Dialogue.saisir({ titre, texte, etiquette, valeur, aide, ok, annuler, inputmode }) -> Promise<string | null> (null = annulé)
// Éléments <dialog> natifs (Échap ferme, focus piégé); textContent seulement : aucun HTML venu des données.
(() => {
  if (!document.querySelector("link[href='dialogue.css']")) {
    const l = document.createElement("link");
    l.rel = "stylesheet"; l.href = "dialogue.css";
    document.head.append(l);
  }
  const el = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };

  function ouvrir({ titre, texte, champ, ok = "OK", annuler = "Annuler", danger = false }) {
    return new Promise((resoudre) => {
      const d = el("dialog", "dialogue");
      const forme = el("form"); forme.method = "dialog";
      forme.append(el("h2", "", titre));
      if (texte) for (const ligne of String(texte).split("\n\n")) forme.append(el("p", "", ligne));
      let saisie = null;
      if (champ) {
        const c = el("label", "champ");
        c.append(el("span", "etiquette", champ.etiquette));
        saisie = el("input", "saisie");
        saisie.type = "text"; saisie.value = champ.valeur ?? "";
        if (champ.inputmode) saisie.inputMode = champ.inputmode;
        saisie.autocomplete = "off";
        c.append(saisie);
        if (champ.aide) c.append(el("span", "aide", champ.aide));
        forme.append(c);
      }
      const pied = el("div", "dialogue-pied");
      const non = el("button", "btn", annuler); non.type = "button";
      const oui = el("button", "btn " + (danger ? "danger" : "primaire"), ok); oui.type = "submit";
      pied.append(non, oui);
      forme.append(pied);
      d.append(forme);
      let resultat = null;
      non.onclick = () => d.close();
      forme.addEventListener("submit", () => { resultat = champ ? saisie.value : true; });
      d.addEventListener("close", () => { d.remove(); resoudre(resultat); });
      document.body.append(d);
      d.showModal();
      (saisie || oui).focus();
      saisie?.select();
    });
  }

  // Formulaire à plusieurs champs : champs = [{ cle, etiquette, valeur, aide, inputmode, options: [{ valeur, libelle }] }]
  // (`options` = liste déroulante). Renvoie { cle: valeur } ou null si annulé.
  function formulaire({ titre, texte, champs, ok = "Enregistrer", annuler = "Annuler" }) {
    return new Promise((resoudre) => {
      const d = el("dialog", "dialogue");
      const forme = el("form"); forme.method = "dialog";
      forme.append(el("h2", "", titre));
      if (texte) forme.append(el("p", "", texte));
      const saisies = {};
      for (const c of champs) {
        const l = el("label", "champ");
        l.append(el("span", "etiquette", c.etiquette));
        let s;
        if (c.options) {
          s = el("select", "saisie");
          for (const o of c.options) { const op = el("option", "", o.libelle); op.value = o.valeur; s.append(op); }
          s.value = c.valeur;
        } else {
          s = el("input", "saisie"); s.type = "text"; s.value = c.valeur ?? ""; s.autocomplete = "off";
          if (c.inputmode) s.inputMode = c.inputmode;
        }
        saisies[c.cle] = s;
        l.append(s);
        if (c.aide) l.append(el("span", "aide", c.aide));
        forme.append(l);
      }
      const pied = el("div", "dialogue-pied");
      const non = el("button", "btn", annuler); non.type = "button";
      const oui = el("button", "btn primaire", ok); oui.type = "submit";
      pied.append(non, oui);
      forme.append(pied);
      d.append(forme);
      let resultat = null;
      non.onclick = () => d.close();
      forme.addEventListener("submit", () => { resultat = Object.fromEntries(Object.entries(saisies).map(([k, v]) => [k, v.value])); });
      d.addEventListener("close", () => { d.remove(); resoudre(resultat); });
      document.body.append(d);
      d.showModal();
      Object.values(saisies)[0]?.focus();
    });
  }

  window.Dialogue = {
    formulaire,
    confirmer: async (o) => (await ouvrir(o)) === true,
    saisir: (o) => ouvrir({ ...o, champ: { etiquette: o.etiquette, valeur: o.valeur, aide: o.aide, inputmode: o.inputmode } }),
  };
})();
