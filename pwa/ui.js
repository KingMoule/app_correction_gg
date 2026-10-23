// Petits comportements des composants (composants.css) : icônes, toast, menu « … », zone de dépôt, contrôle segmenté.
// Tout est sous window.UI. Aucun HTML construit à partir de données : les libellés passent par textContent.
(() => {
  const NS = "http://www.w3.org/2000/svg";
  const SPRITE = "vendor/lucide-sprite.svg";

  // Icône Lucide du sprite : UI.icone("house") -> <svg class="ic">. `classes` : "s" (16 px) ou "l" (20 px).
  function icone(nom, classes = "") {
    const svg = document.createElementNS(NS, "svg");
    svg.setAttribute("class", ("ic " + classes).trim());
    svg.setAttribute("aria-hidden", "true");
    const use = document.createElementNS(NS, "use");
    use.setAttribute("href", `${SPRITE}#${nom}`);
    svg.append(use);
    return svg;
  }

  const el = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };

  // Toast : UI.toast("Faute acceptée", { action: { libelle: "Annuler", surClic: () => … }, erreur: false, duree: ms })
  // Avec une action le toast reste 6 s (sinon 3,5 s). Renvoie { fermer }.
  function toast(message, options = {}) {
    let zone = document.querySelector(".toasts");
    if (!zone) {
      zone = el("div", "toasts");
      zone.setAttribute("role", "status");
      zone.setAttribute("aria-live", "polite");
      document.body.append(zone);
    }
    const t = el("div", "toast" + (options.erreur ? " erreur" : ""));
    t.append(icone(options.erreur ? "circle-alert" : "circle-check"), el("span", "", message));
    let minuteur = null;
    const fermer = () => { clearTimeout(minuteur); t.remove(); };
    if (options.action) {
      const b = el("button", "btn", options.action.libelle);
      b.type = "button";
      b.onclick = () => { fermer(); options.action.surClic?.(); };
      t.append(b);
    }
    zone.append(t);
    minuteur = setTimeout(fermer, options.duree ?? (options.action ? 6000 : 3500));
    return { fermer };
  }

  // Menu « … » : UI.menu(bouton, [{ libelle, icone, surClic, danger, desactive }, { separateur: true }, …]). Ouvre au toucher du bouton.
  // Échap, un toucher ailleurs ou le choix d'un élément le ferment; flèches haut/bas pour naviguer.
  function menu(declencheur, elements) {
    let ouvert = null;
    const fermer = () => {
      if (!ouvert) return;
      ouvert.remove(); ouvert = null;
      declencheur.setAttribute("aria-expanded", "false");
      document.removeEventListener("pointerdown", dehors, true);
      document.removeEventListener("keydown", clavier, true);
    };
    const dehors = (e) => { if (ouvert && !ouvert.contains(e.target) && !declencheur.contains(e.target)) fermer(); };
    const clavier = (e) => {
      if (e.key === "Escape") { fermer(); declencheur.focus(); return; }
      if (e.key !== "ArrowDown" && e.key !== "ArrowUp") return;
      const items = [...ouvert.querySelectorAll("[role=menuitem]:not(:disabled)")];
      const i = items.indexOf(document.activeElement);
      items[(i + (e.key === "ArrowDown" ? 1 : -1) + items.length) % items.length]?.focus();
      e.preventDefault();
    };
    function ouvrir() {
      const m = el("div", "menu");
      m.setAttribute("role", "menu");
      for (const it of elements) {
        if (it.separateur) { m.append(el("hr")); continue; }
        const b = el("button", it.danger ? "danger" : "");
        b.type = "button"; b.setAttribute("role", "menuitem"); b.disabled = !!it.desactive;
        if (it.icone) b.append(icone(it.icone));
        b.append(el("span", "", it.libelle));
        b.onclick = () => { fermer(); it.surClic?.(); };
        m.append(b);
      }
      document.body.append(m);
      const r = declencheur.getBoundingClientRect();
      const gauche = Math.max(8, Math.min(innerWidth - m.offsetWidth - 8, r.right - m.offsetWidth));
      const bas = r.bottom + m.offsetHeight + 8 > innerHeight ? r.top - m.offsetHeight - 4 : r.bottom + 4;
      m.style.left = `${gauche + scrollX}px`;
      m.style.top = `${Math.max(8, bas) + scrollY}px`;
      ouvert = m;
      declencheur.setAttribute("aria-expanded", "true");
      m.querySelector("[role=menuitem]:not(:disabled)")?.focus();
      document.addEventListener("pointerdown", dehors, true);
      document.addEventListener("keydown", clavier, true);
    }
    declencheur.setAttribute("aria-haspopup", "menu");
    declencheur.setAttribute("aria-expanded", "false");
    declencheur.addEventListener("click", () => (ouvert ? fermer() : ouvrir()));
    return { fermer };
  }

  // Zone de dépôt : <label class="depot"><input type="file" multiple>…</label>. surFichiers(File[]) après un choix ou un glisser-déposer.
  function depot(zone, surFichiers) {
    const champ = zone.querySelector("input[type=file]");
    champ.addEventListener("change", () => { surFichiers([...champ.files]); champ.value = ""; });
    for (const ev of ["dragenter", "dragover"]) zone.addEventListener(ev, (e) => { e.preventDefault(); zone.classList.add("survol"); });
    for (const ev of ["dragleave", "drop"]) zone.addEventListener(ev, () => zone.classList.remove("survol"));
    zone.addEventListener("drop", (e) => {
      e.preventDefault();
      const fichiers = [...(e.dataTransfer?.files ?? [])];
      if (fichiers.length) surFichiers(fichiers);
    });
  }

  // Contrôle segmenté : UI.segmente(.seg, (bouton) => …) garde un seul bouton actif (classe `on` et aria-pressed).
  function segmente(seg, surChoix) {
    seg.addEventListener("click", (e) => {
      const b = e.target.closest("button");
      if (!b || !seg.contains(b)) return;
      for (const x of seg.querySelectorAll("button")) {
        x.classList.toggle("on", x === b);
        x.setAttribute("aria-pressed", String(x === b));
      }
      surChoix?.(b);
    });
  }

  // « 202SNURE_A2026 » -> « 202SNURE · A2026 » (l'identifiant du cours contient la session; il ne change pas)
  function titreCours(cle) {
    const m = /^(.+)_([AH]\d{4})$/.exec(cle ?? "");
    return m ? `${m[1]} · ${m[2]}` : (cle ?? "");
  }
  window.UI = { icone, toast, menu, depot, segmente, titreCours };
})();
