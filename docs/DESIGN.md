# Design de l'interface

**Direction en vigueur : « Atelier » en sarcelle** (choisie par Guillaume le 2026-10-21, elle remplace la direction « chaleureuse » du 2026-10-20). Outil pro sobre : barre latérale, neutres froids, un seul accent, Inter. Catalogue vivant : [`pwa/composants.html`](../pwa/composants.html) (ouvrir via le moteur : `http://localhost:8001/composants.html`). Maquettes de référence, raisonnement et critiques : [`design/propositions-2026-10/`](design/propositions-2026-10/README.md) (direction A, section « A avec ta sarcelle » de `comparaison.html`).

## État de l'application

- **PR 1 (faite) : fondations.** Jetons (`design.css`), composants (`composants.css`, `ui.js`), coque (`coque.css`, `coque.js`), catalogue. La coque et la nouvelle typographie sont appliquées à l'accueil, la bibliothèque, l'import, le lot, le suivi et le plagiat, **sans refaire leur contenu**.
- **PR 2 (faite)** : accueil (bloc « À faire » de la direction C, labs avec progression), bibliothèque (cours > lab > groupe repliés, une ligne par rapport avec un menu « … »), import (étapes, zones de dépôt, résultat par fichier, « À trancher »), code d'accès. Rien d'ajouté aux fichiers communs; `style.css` garde une section « Hérité » encore utilisée par le suivi et le plagiat. **PR 3 (faite)** : suivi en tableau dense (menu « … », balayage d'une ligne au doigt dans `suivi.js`), plagiat (liste + passages appariés), indices d'IA, lot et export (`outils.css`, chargé par `lot.js`, `indices-ia.js` et `export-lea.js`); boîtes de dialogue `dialogue.js` à la place de `confirm()` et `prompt()`. **PR 4 (faite) : lecteur** (une ligne en haut, rail d'outils à gauche, inspecteur de 320 px à onglets Français / Indice IA / Plagiat, fiche de la faute, page à 700 px, feuille à 3 crans en portrait, fenêtre « Terminé… »). Le lecteur n'a pas de coque; il charge `design.css`, `composants.css` et `lecteur.css`, et `ui.js` pour les toasts et le menu « … ».
- Les écrans pas encore refaits utilisent encore les anciens noms (`.bk`, `.gros`, `.pastille`, `.carte`, boutons des `<section>`), restylés par `design.css` pour rester cohérents. Une PR d'écran remplace ces noms par ceux du catalogue et supprime ce qu'elle n'utilise plus.

## Règles

1. **Un seul accent**, la sarcelle : action principale, sélection, outil actif, lien actif. Avatars, labs et pastilles restent neutres.
2. **Couleurs d'état fixes** : rouge = faute ou erreur bloquante, **jamais autre chose**; bleu-vert = plagiat; violet + loupe = indice d'IA; neutre + étincelles = Claude (l'outil), pour ne pas confondre « analysé par Claude » et « écrit par une IA »; vert = fait; ambre = à trancher. Jamais la couleur seule : toujours un mot.
3. **Les 5 couleurs d'annotation et le rouge des fautes (`--faute`) ne changent pas.**
4. **Un seul bouton plein par zone**, à droite. Libellé visible partout; **icône seule** seulement pour crayon, gomme, annuler, rétablir, partager (avec `aria-label`).
5. **Cibles d'au moins 44 px**, 8 px entre cibles voisines; texte d'au moins 13 px; contraste WCAG AA (texte ≥ 4,5:1, contour de champ ≥ 3:1).
6. **Hors ligne** : aucune ressource externe. Inter et Lucide sont dans `pwa/vendor/` avec leur licence.
7. **Pas de mode sombre** (décision du 2026-10-20). Tout passe par des variables : un thème sombre n'aurait qu'à les redéfinir. Le lecteur garde ses variables propres.
8. **Retours** : toast bref avec « Annuler » pour un succès ou une action réversible; bannière persistante pour ce qui exige une action; progression chiffrée (« 9 / 12 »); état vide avec une phrase qui dit quoi faire et un bouton.

## Jetons (`pwa/design.css`)

| Famille | Jetons |
|---|---|
| Neutres | `--bg #fafafa`, `--side #f4f4f5`, `--surface #fff`, `--surface-2/-3`, `--border`, `--border-fort`, `--border-champ` (contour des champs), `--texte`, `--texte-2`, `--texte-3` |
| Accent sarcelle | `--accent #0f6f66`, `--accent-fort #0a554e`, `--accent-doux #e1f0ed`, `--accent-bord #a9d3cc`, `--sur-accent` |
| États | `--ok`/`--ok-fond`/`--ok-point`, `--attention`/`-fond`/`-point`, `--danger`/`-fond`, `--plagiat`/`-fond`, `--ia`/`-fond`, `--claude`/`-fond`, `--neutre`/`-fond`, `--faute` |
| Typographie | `Inter` variable (latin), 15 px (`--t`), minimum 13 px (`--t-min`), 14 px (`--t-s`), titres en 600 (24 px d'écran, 18 px de section), `.num` = chiffres tabulaires |
| Espacements | `--e1` 4, `--e2` 8, `--e3` 12, `--e4` 16, `--e5` 24, `--e6` 32 |
| Rayons, ombres | `--r-xs` 6, `--r-s` 8, `--r-m` 12; `--ombre` (fine), `--ombre-pop` (menus, toasts) |
| Tailles | `--cible` 44, `--ligne` 48 (listes), `--ligne-tableau` 52, `--lateral` 248 |

Anciens noms conservés : `--info`, `--info-fond`, `--neutre-fond`, `--e1…e6`, `--ligne`, etc.

## Composants (guide d'usage)

Chargement d'une page : `design.css`, `composants.css`, puis `coque.css` (si coque), puis les feuilles de l'écran. Scripts : `ui.js` puis `coque.js` avant ceux de l'écran. Le lecteur charge `design.css`, `composants.css` et `lecteur.css` (pas de coque).

| Composant | Balisage | Quand |
|---|---|---|
| Bouton primaire / secondaire / tertiaire / danger | `.btn.primaire`, `.btn`, `.btn.tertiaire`, `.btn.danger` (+ icône `svg.ic` avant le libellé) | Primaire : l'action de la zone. Secondaire : les autres. Tertiaire : lien d'action discret. Danger : écarter, remplacer (avec confirmation). |
| Bouton icône seule | `.btn-ico` (+ `.on` ou `aria-pressed`) avec `aria-label` | Les 5 usages ci-dessus et le déclencheur « … » d'un menu. |
| Contrôle segmenté | `.seg` > `button.on` + `.n` (compteur); `UI.segmente(seg, rappel)` | Filtres exclusifs avec compteurs. |
| Onglets | `.onglets` > `[role=tab][aria-selected]` | Inspecteur (Français, Indice IA, Plagiat). |
| Pastille d'état | `.pastille` (+ `.p-fini`, `.p-nouv`, `.p-neutre`, `.p-erreur`, `.p-plagiat`, `.p-ia`, `.p-claude`) | Défaut = à trancher. `p-ia` et `p-claude` portent une icône (loupe, étincelles) à la place du point. |
| Menu « … » | `UI.menu(bouton, [{libelle, icone, surClic, danger}, {separateur:true}])` | Une ligne de tableau : un menu au lieu de 3 ou 4 boutons. |
| Toast | `UI.toast(texte, {action:{libelle:"Annuler", surClic}, erreur})` | Succès bref et actions réversibles; 3,5 s (6 s avec action). |
| Bannière | `.banniere` (+ `.attention`, `.erreur`, `.ok`) avec `role="status"` (ou `alert`) | Ce qui exige une action ou une précaution (« indice, jamais un verdict »). |
| Champ | `label.champ` > `.etiquette` + `.saisie` + `.aide` / `.message` (`.invalide`); `.champ-icone`; `.interrupteur` | Tout formulaire : 44 px, 16 px de texte. |
| Zone de dépôt | `label.depot` > `input[type=file]`; `UI.depot(zone, rappel)`; `.depot-liste` | Import de PDF, liste de classe, énoncé. Une ligne par fichier avec sa pastille. |
| Tableau dense | `.tableau-defil` > `table.tableau` (`tr.groupe`, `tr.sel`, `td.nombre`, `.avatar`, `.nom-etu`) | Suivi, plagiat, export : lignes de 52 px. |
| Progression chiffrée | `.progression` (`.progression-tete` + `progress` ou `.barre > i.fait/.cours`) | Lot, export, avancement d'un lab. |
| État vide | `.vide.carte` : icône, phrase, bouton | Toute liste vide. |
| Icônes | `<svg class="ic"><use href="vendor/lucide-sprite.svg#nom"/></svg>` ou `UI.icone("nom")` (`.s` 16 px, `.l` 20 px) | Trait de 1,75 px, `currentColor`. |

Ajouter une icône : l'ajouter à la liste de `scripts/sprite_lucide.mjs`, relancer le script (instructions en tête), commiter le sprite. Ne jamais éditer le sprite à la main.

### Coque (`coque.css`, `coque.js`)

Page : `<body class="avec-coque"><div class="coque"><aside id="coque-lat" class="coque-lat"></aside><div class="coque-corps"><main>…</main></div></div>`, puis `ui.js`, `coque.js`. `coque.js` construit la barre : Accueil, Bibliothèque, Importer (badge `#badge-attente`, rempli par `app.js`), Analyse par lot (progression `n / total` et barre tant qu'un lot tourne), Plagiat, Export LÉA (mène à la bibliothèque : l'export se lance depuis un lab, jamais marqué actif), « Labs en cours » (lien vers le suivi, `faits / total`), et en pied Réglages (pas encore de page : désactivé, à brancher) et « Ordi connecté » avec « Se déconnecter » (`#deconnexion`, géré par `acces.js`). Sous la navigation, la jauge de consommation de Claude (« Claude · 5 h ≈ 14 % », filet de 4 px avec repère de la marge; ambre près du repère, rouge à la limite) mène à `consommation.html` (`consommation.css`). Sous 900 px (iPad en portrait) la barre devient un tiroir ouvert par « Menu ». Le lecteur n'a pas de coque. Une page à vue interne (l'accueil) appelle `Coque.marquer(vue)`; une page qui connaît déjà la bibliothèque appelle `Coque.labs(arbre)`.

## Vérification d'un écran refait

- Captures à 1180 × 820 (iPad paysage), 820 × 1180 (portrait) et PC, moteur en `--local` sur une bibliothèque **fictive** (dossier temporaire, jamais `C:\correction_donnees`), console sans erreur, serveur arrêté ensuite.
- `pytest` (inclut `tests/test_js_syntaxe.py`).
- Aucun comportement retiré : mêmes `id` que les scripts de l'écran attendent.

## Historique des décisions de design

- 2026-10-20 : direction « chaleureuse » (sarcelle `#0f6f66`, fond crème), pas de mode sombre, lignes de 48 px. Maquette : `maquette-design.html`, constats sur l'ancienne app : `design/avant/`.
- 2026-10-21 : trois directions comparées (A « Atelier », B « Natif iPad », C « Salle des profs »). **A retenue en sarcelle**, avec deux emprunts (bloc « À faire » de C à l'accueil, balayage d'une ligne du suivi de B). Le pas de mode sombre est maintenu.
- Principes de recherche (Refactoring UI, HIG, Material, Radix, Primer, Atlassian, WCAG 2.2, NN/g) : voir `design/propositions-2026-10/README.md`.
