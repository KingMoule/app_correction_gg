// Navigation entre les rapports d'un lab depuis le lecteur : Précédent, Rapport suivant (prochain non terminé),
// retour au tableau de suivi, « Terminé… » (note, puis « Terminer et ouvrir le suivant »). L'ordre est celui du tableau
// (groupe puis nom), lu en un seul appel : GET /api/suivi/<cours>/<lab>.
(async () => {
  if (ref.some((v) => !v)) return;
  const [cours, groupe, lab, etudiant] = ref;
  const API_BIB = "/api/bibliotheque";
  const filtreGroupe = params.has("fg") ? params.get("fg") : groupe; // « fg » vient du tableau (vide = tous les groupes)
  $("retour").href = `suivi.html?${new URLSearchParams({ cours, lab })}`;
  let suivi;
  try {
    const r = await fetch(`/api/suivi/${[cours, lab].map(encodeURIComponent).join("/")}?groupe=${encodeURIComponent(filtreGroupe)}`);
    if (r.ok) suivi = await r.json();
  } catch { /* moteur injoignable : le lecteur reste utilisable sans navigation */ }
  const liste = suivi?.rapports ?? [];
  const i = liste.findIndex((e) => e.groupe === groupe && e.etudiant === etudiant);
  if (i < 0) { $("suivi").hidden = true; return; }

  try { // la bibliothèque s'ouvre déjà dépliée sur ce lab au retour
    for (const cle of [cours, `${cours}/${lab}`, `${cours}/${lab}/${groupe}`]) localStorage.setItem("ouvert:" + cle, "1");
  } catch { /* stockage indisponible */ }

  const courant = liste[i];
  let termine = courant.termine;
  const nomComplet = `${courant.prenom} ${courant.nom}`;
  const coequipiers = (courant.equipe ?? []).filter((n) => n !== nomComplet);
  if (coequipiers.length) $("sous-titre").textContent += ` · avec ${coequipiers.join(", ")}`;

  // prochain rapport non terminé après celui-ci, puis depuis le début
  const prochain = () => [...liste.slice(i + 1), ...liste.slice(0, i)].find((e) => !e.termine);

  const afficher = () => {
    $("position").textContent = `${i + 1} / ${liste.length}`;
    $("statut").hidden = !termine;
    $("statut").className = "pastille p-fini";
    $("statut").textContent = "Terminé";
    const b = $("termine");
    b.classList.toggle("primaire", !termine);
    b.querySelector("span").textContent = termine ? "Ré-ouvrir" : "Terminé…";
    $("prec").disabled = i <= 0;
    $("suiv").disabled = !prochain();
    $("suiv").title = prochain() ? "Enregistre, puis ouvre le prochain rapport non terminé du lab"
      : "Aucun autre rapport à corriger";
  };

  const aller = async (e) => {
    if (!(await window.enregistrerAvant())) return;
    const q = new URLSearchParams(location.search);
    q.set("groupe", e.groupe);
    q.set("etudiant", e.etudiant);
    q.set("nom", `${e.prenom} ${e.nom}`);
    q.set("fg", filtreGroupe);
    location.href = `lecteur.html?${q}`;
  };

  // Marque le rapport terminé (avec sa note; vide = pas de note) ou le ré-ouvre. false = pas fait (rien d'enregistré, ou moteur qui refuse).
  const marquer = async (valeur, note) => {
    if (!(await window.enregistrerAvant())) return false;
    const corps = { termine: valeur };
    if (valeur) corps.note = note;
    let r;
    try {
      r = await fetch(`${API_BIB}/statut/${[cours, groupe, lab, etudiant].map(encodeURIComponent).join("/")}`, {
        method: "PUT", headers: { "Content-Type": "application/json" }, body: JSON.stringify(corps),
      });
    } catch { r = null; }
    if (!r?.ok) { alert("Impossible d'enregistrer le statut."); return false; }
    termine = courant.termine = valeur;
    if (valeur) courant.note = corps.note;
    afficher();
    return true;
  };

  const vers = (e) => {
    if (e) return aller(e);
    return window.enregistrerAvant().then((ok) => { if (ok) location.href = $("retour").href; }); // tous terminés : retour au tableau
  };

  // ----- fenêtre « Terminé… » -----
  const dlg = $("termine-fond");
  const FORCES = { faible: "Faible", moderee: "Modéré", marquee: "Marqué" };
  const fermerDialogue = () => { dlg.hidden = true; $("termine").focus(); };
  const ouvrirDialogue = () => {
    $("termine-titre").textContent = `Terminer le rapport de ${nomComplet}`;
    $("termine-equipe").textContent = coequipiers.length ? `avec ${coequipiers.join(", ")}` : "";
    $("termine-aide").textContent = coequipiers.length ? "Vide = sans note. La même note va aux coéquipiers." : "Vide = sans note.";
    const f = window.etatFrancais?.();
    $("t-fr").textContent = f ? (f.penalite ? `−${String(Math.round(f.penalite * 100) / 100).replace(".", ",")} pt` : "0 pt") : "Non analysé";
    $("t-fautes").textContent = f ? `${f.acceptees} acceptée${f.acceptees > 1 ? "s" : ""}${f.aTrancher ? ` · ${f.aTrancher} à trancher` : ""}` : "—";
    const force = window.forceIA ?? courant.ia;
    $("t-ia").textContent = force ? FORCES[force] ?? "Faible" : "Non analysé";
    $("termine-note").value = courant.note ?? "";
    const suite = prochain();
    $("termine-suivant").querySelector("span").textContent = suite ? "Terminer et ouvrir le suivant" : "Terminer et revenir au tableau";
    dlg.hidden = false;
    $("termine-note").focus();
  };
  const terminer = async (ouvrirSuite) => {
    const boutons = [$("termine-seul"), $("termine-suivant"), $("termine-annuler")];
    for (const b of boutons) b.disabled = true;
    try {
      if (!(await marquer(true, $("termine-note").value.trim()))) return;
      dlg.hidden = true;
      if (ouvrirSuite) await vers(prochain());
      else UI.toast("Rapport terminé", { action: { libelle: "Ré-ouvrir", surClic: () => marquer(false) } });
    } finally { for (const b of boutons) b.disabled = false; }
  };
  $("termine-annuler").onclick = fermerDialogue;
  $("termine-seul").onclick = () => terminer(false);
  $("termine-suivant").onclick = () => terminer(true);
  $("termine-note").onkeydown = (e) => { if (e.key === "Enter") terminer(true); };
  dlg.addEventListener("pointerdown", (e) => { if (e.target === dlg) fermerDialogue(); });
  document.addEventListener("keydown", (e) => { if (e.key === "Escape" && !dlg.hidden) fermerDialogue(); });

  $("prec").onclick = () => aller(liste[i - 1]);
  $("suiv").onclick = () => vers(prochain());
  $("termine").onclick = async () => {
    if (!termine) { ouvrirDialogue(); return; }
    if (await marquer(false)) UI.toast("Rapport ré-ouvert");
  };
  afficher();
})();
