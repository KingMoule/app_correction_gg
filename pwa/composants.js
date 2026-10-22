// Catalogue des composants (composants.html) : branche les démos et affiche le balisage de chaque bloc. Aucune donnée réelle.
(() => {
  const $ = (id) => document.getElementById(id);
  const sur = (tag, classe, texte) => {
    const e = document.createElement(tag);
    if (classe) e.className = classe;
    if (texte != null) e.textContent = texte;
    return e;
  };

  // Jetons : lus dans design.css, pas recopiés ici.
  const BASE = [["--bg", "fond"], ["--surface", "carte"], ["--surface-2", "fond 2"], ["--border", "bordure"], ["--border-champ", "contour de champ"],
    ["--texte", "texte"], ["--texte-2", "texte 2"], ["--texte-3", "texte 3"], ["--accent", "accent sarcelle"], ["--accent-fort", "accent fort"], ["--accent-doux", "accent doux"], ["--accent-bord", "bord d'accent"]];
  const ETATS = [["--ok", "fait"], ["--ok-fond", "fait, fond"], ["--attention", "à trancher"], ["--attention-fond", "à trancher, fond"], ["--danger", "faute, erreur"], ["--danger-fond", "faute, fond"],
    ["--plagiat", "plagiat"], ["--plagiat-fond", "plagiat, fond"], ["--ia", "indice d'IA"], ["--ia-fond", "indice d'IA, fond"], ["--claude", "Claude"], ["--claude-fond", "Claude, fond"]];
  const lire = (nom) => getComputedStyle(document.documentElement).getPropertyValue(nom).trim();
  for (const [zone, liste] of [[$("j-base"), BASE], [$("j-etats"), ETATS]]) {
    for (const [nom, role] of liste) {
      const j = sur("div", "jeton"), pastille = sur("i"), t = sur("div");
      pastille.style.background = `var(${nom})`;
      t.append(sur("code", "", nom), sur("span", "", `${lire(nom)} · ${role}`));
      j.append(pastille, t);
      zone.append(j);
    }
  }

  // Icônes du sprite
  fetch("vendor/lucide-sprite.svg").then((r) => r.text()).then((svg) => {
    const ids = [...svg.matchAll(/<symbol id="([^"]+)"/g)].map((m) => m[1]);
    $("liste-icones").replaceChildren(...ids.map((id) => { const d = sur("div"); d.append(UI.icone(id, "l"), sur("span", "", id)); return d; }));
  }).catch(() => {});

  // Menu, toasts, segmenté, onglets, dépôt
  const elementsMenu = [
    { libelle: "Ouvrir le rapport", icone: "file-text", surClic: () => UI.toast("Ouverture du rapport (démo)") },
    { libelle: "Analyser avec Claude", icone: "sparkles", surClic: () => UI.toast("Analyse lancée (démo)") },
    { libelle: "Marquer terminé", icone: "check", surClic: () => UI.toast("Marqué terminé", { action: { libelle: "Annuler", surClic: () => UI.toast("Annulé") } }) },
    { separateur: true },
    { libelle: "Écarter…", icone: "trash-2", danger: true, surClic: () => UI.toast("Confirmation demandée avant d'écarter (démo)") },
  ];
  UI.menu($("menu-demo"), elementsMenu);
  UI.menu($("b-menu"), elementsMenu);
  $("b-toast").onclick = () => UI.toast("Faute acceptée", { action: { libelle: "Annuler", surClic: () => UI.toast("Faute remise à trancher") } });
  $("b-toast-err").onclick = () => UI.toast("Enregistrement impossible : l'ordi ne répond pas", { erreur: true, action: { libelle: "Réessayer" } });
  for (const seg of document.querySelectorAll(".seg")) UI.segmente(seg);
  for (const o of $("d-onglets").querySelectorAll("[role=tab]")) {
    o.onclick = () => { for (const x of $("d-onglets").querySelectorAll("[role=tab]")) x.setAttribute("aria-selected", String(x === o)); };
  }
  for (const b of $("d-icones-seules").querySelectorAll("[aria-pressed]")) {
    b.onclick = () => {
      for (const x of $("d-icones-seules").querySelectorAll("[aria-pressed]")) { x.setAttribute("aria-pressed", String(x === b)); x.classList.toggle("on", x === b); }
    };
  }
  UI.depot($("d-depot"), (fichiers) => UI.toast(`${fichiers.length} fichier(s) reçu(s) (démo : rien n'est envoyé)`));

  // « HTML » sous les blocs qui en ont besoin : le balisage réel du bloc, pas une copie à maintenir
  for (const id of ["d-boutons", "d-pastilles", "d-seg", "d-onglets", "d-bannieres", "d-champs", "d-depot", "d-tableau"]) {
    const bloc = $(id);
    const d = sur("details"), s = sur("summary", "", "HTML"), pre = sur("pre");
    pre.textContent = bloc.outerHTML.replace(/ aria-pressed="(true|false)"/g, "").replace(/\s{2,}/g, "\n  ").trim();
    d.append(s, pre);
    bloc.closest(".demo").append(d);
  }
})();
