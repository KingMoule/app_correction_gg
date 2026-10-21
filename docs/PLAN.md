# Plan général

Objectif : une seule app pour corriger les rapports de lab (français, annotation, plagiat, indices d'IA), au lieu de passer par Word, Dropbox, OneNote et l'iPad.

## État au 2026-10-19 (à lire en premier)

Tout est fusionné dans `main` jusqu'à la PR #22 (bibliothèque, lecteur et annotation, fautes de français, export du PDF annoté, plagiat, indices d'IA, passe Claude sur le français, mesure de consommation, compatibilité Windows, analyse par lot, démarrage en un clic, liste Omnivox, import par DA et multi-groupes). Reste à faire :

- [x] **Passe Claude sur le français** (étape 2) : faite et fusionnée (PR #17). Après LanguageTool, `claude -p` repère les erreurs subtiles; mêmes zones et décisions que LanguageTool. Consommation mesurée (ligne ci-dessous).
- [~] **Design** (2026-10-20) : direction chaleureuse, accent sarcelle, fond clair, lignes de 48 px (décisions de Guillaume, voir `docs/DESIGN.md`). PR #38 (proposition), #39 (jetons, navigation, accueil, bibliothèque, import), #41 (suivi, plagiat), PR lecteur. Reste après fusion : l'essayer sur l'iPad.
- [ ] **Essais de Guillaume sur l'iPad** : crayon dans l'app (le prototype seul est validé), tap sur une faute pour sa fiche, export du PDF depuis l'app installée sur l'écran d'accueil.
- [x] **Mesure faite (2026-10-19)** : 1 rapport (français + indices d'IA) = **3 % de la limite de session (5 h)**, limite de la semaine inchangée (pas de hausse visible). Conditions : modèle **Opus 5.5**, rapport de 3 pages. Estimation : avec une marge de 20 % de la session, environ 6 rapports par lot **avec Opus**. **Sonnet** (même rapport, 3 pages) = **2 % de la session**, semaine inchangée : environ 10 rapports par lot avec la même marge de 20 %. Les % affichés sont entiers : mesure approximative (±1 point). Option : mesurer `haiku`, ou refaire sur 3 à 5 rapports pour affiner.
- [~] **Analyse par lot** (fusionnée, PR #19) : fait côté moteur et écran (`moteur/lot.py`, `pwa/lot.js`) : au plus N rapports d'un lab (10 par défaut), arrêt propre sur limite d'usage, bouton Arrêter, case « Refaire aussi les analysés » (décision de Guillaume : par défaut, les rapports déjà analysés sont ignorés). Modèle par défaut du moteur : Sonnet. Reste : l'essayer sur de vrais rapports. Plagiat par lot : pas de changement (déjà une paire à la fois, après confirmation).
- [x] **Import de la liste de classe Omnivox** : le vrai CSV (cp1252, `;`, `="..."`, « Nom de l'étudiant », « No de DA ») est accepté; le DA est gardé (champ `da`). Reste : Guillaume réessaie avec son vrai fichier.
- [x] **Remplacement d'un rapport (audit PR 4, C3)** (2026-10-20) : trancher un `deja_importe` demande une confirmation explicite (409 sans `remplacer`) et déplace l'ancien dossier au complet dans `_remplaces/` (corrections, statut et note comprises) au lieu de les mélanger au nouveau PDF. Décision par défaut : tout est mis de côté, on repart à neuf (pas de report des annotations au crayon).
- [x] **Rangement fiable à l'import** (2026-10-19, premier essai réel) : association par n° de DA puis par nom (même sans séparateurs), import multi-groupes (groupe facultatif), coéquipiers repérés sur la page titre (décision de Guillaume : rapport rangé une fois au nom du déposant, équipe en métadonnée, note commune saisie dans LÉA, plagiat ignore l'équipe), récapitulatif par groupe. Cause du dossier `_attente` vide : « Écarter » supprimait le PDF sans confirmation (et 11 rapports avaient été rangés à la main); « Écarter » déplace maintenant dans `_ecartes/` après confirmation. Reste : Guillaume réessaie avec ses vrais PDF.
- [x] **Mise à jour automatique au démarrage** (2026-10-19) : `demarrer.bat` fait `git pull --ff-only` (sur `main` propre seulement), relance `pip install -e .` si `pyproject.toml` change, affiche la version; il s'exécute depuis une copie dans `%TEMP%` pour ne pas être lu de travers si le pull le modifie. Voir `docs/DEMARRAGE.md`. Reste : Guillaume l'essaie.
- [x] **Français : prose seulement** (2026-10-19, plainte « environ 100 fautes pour 2 pages ») : LanguageTool ne voit plus les calculs, tableaux, symboles ni références (markup), typographie désactivée, filtre des jetons techniques, lexique global, décalage UTF-16 corrigé, consigne Claude renforcée. Mesure sur 11 rapports rangés : 458 → environ 22 fautes (voir `docs/ARCHITECTURE.md`). Décisions de Guillaume : typographie non comptée, lexique global. Reste : Guillaume juge les fautes gardées sur ses vrais rapports (regler les seuils dans `francais_filtre.py` au besoin).
- [x] **Lecteur : le panneau des fautes ne cache plus le PDF** (2026-10-19) : le panneau Français est une colonne à droite (largeur inchangée), le PDF occupe la zone restante et se remet à l'échelle (zoom relatif et page en haut conservés, coordonnées en points PDF donc zones et traits restent alignés). La fiche d'une faute est dans le panneau, en haut (décision de Guillaume). En portrait (hauteur > largeur), le panneau passe sous le PDF (42 % de la hauteur). Reste : Guillaume l'essaie sur l'iPad.
- [x] **Lecteur : fautes et écriture manuscrite visibles sur toutes les pages** (2026-10-19) : la couche `.fautes` passait sous les canvas des pages activées après elle (donc seule la page 1 la montrait); `z-index: 1`. Export du PDF vérifié (test sur 3 pages), sans bogue. Reste : Guillaume l'essaie.
- [x] **Lecteur : retouches des fautes** (2026-10-19) : plus de pointillé sous le mot; correction manuscrite déplaçable (mode « Déplacer » dans la fiche, décalage enregistré dans `francais.json`, repris par l'export, gardé à la réanalyse, « Remettre en place »); toucher une faute dans le panneau la centre dans la zone du PDF. Décision : pas de trait de rappel (texte clair). Reste : Guillaume l'essaie sur l'iPad.
  - **Correctif (2026-10-19)** : la correction revenait en place à la sortie du mode « Déplacer ». Causes : (1) le décalage n'était mémorisé qu'à la fin du geste (pointerup / pointercancel), qui peut manquer sur iPad Safari : il est maintenant mémorisé et envoyé à chaque mouvement; (2) un `francais.json` analysé avant les décalages n'avait pas la clé `decalages` : le moteur la fournit toujours.
- [x] **Export par lot pour LÉA** (2026-10-20, PR à relire) : `Travaux.zip` des PDF corrigés (noms d'origine de LÉA + `_corrige`) et tableau CSV (une ligne par coéquipier, pénalité de français, note, état, indices IA et plagiat « à revérifier »), depuis la bibliothèque; note demandée à « Terminé ». Détails dans `docs/ARCHITECTURE.md`. Reste : Guillaume l'essaie avec un vrai lot (téléversement de `Travaux.zip` dans LÉA : nom des fichiers à vérifier; les rapports importés avant cette PR n'ont pas de nom d'origine et prennent le nom de repli).
- [x] **Tableau de suivi d'un lab et « Rapport suivant »** (2026-10-20, PR à relire) : écran `suivi.html` (une ligne par rapport : annotation, français, indice d'IA, plagiat, état; filtres À corriger / groupe / À revoir; actions Ouvrir, Analyser, Terminé), un seul appel `GET /api/suivi/<cours>/<lab>`; lecteur : Tableau, Précédent, Rapport suivant. Détails dans `docs/ARCHITECTURE.md`. Reste : Guillaume l'essaie sur l'iPad (portrait compris).
  - Décisions (toutes « recommandation acceptée par Guillaume », 2026-10-20) : emplacement = écran du lab; ordre = groupe puis nom (aussi pour « suivant »); filtres = À corriger / Tous, groupe, À revoir; actions de ligne = Ouvrir, Analyser, Terminé; maquette validée telle quelle; états globaux = terminé (bouton existant), en cours (traits, français ou IA présents), à corriger (rien), sans nouvel état stocké; « Rapport suivant » = prochain non terminé, en repartant du début.
- [ ] **Plus tard (idée de Guillaume)** : lire la note écrite au crayon à la fin du rapport; remplacée pour l'instant par la saisie à « Terminé ».
- [x] **Sauvegarde des données** (2026-10-20, PR à relire) : décisions de Guillaume : destination = 2e dossier sur l'ordi (`C:\correction_donnees_sauvegardes`, réglable avec `CORRECTION_SAUVEGARDES`), moment = à chaque lancement de `demarrer.bat` (pas de bouton ni de tâche planifiée), conservation = 10 dernières + 1 par semaine (8 semaines), contenu = tout sauf `plagiat/textes/`. Restauration : `python -m moteur.sauvegarde restaurer` (renomme l'actuel, ne supprime rien). Reste : Guillaume essaie; **limite connue** : un 2e dossier sur le même disque ne protège pas d'une panne du disque, voir `docs/DEMARRAGE.md` pour viser un autre disque ou une clé USB.
- [x] **Écriture JSON sûre** (2026-10-20, audit E1, E3, F5, M9; PR à relire) : `moteur/stockage.py` (écriture atomique à temporaire unique avec nouvel essai Windows, lecture tolérante, verrou par dossier) utilisé par tous les modules; CI Ubuntu + Windows. Base des PR 2 (décisions de français) et 3 (annotations avec révision) de `docs/AUDIT-2026-10.md`. Détails dans `docs/ARCHITECTURE.md`. Reste : voir les constats suivants de l'audit.
- [x] **Annotations avec révision (audit E2, PR 3)** (2026-10-20, PR à relire) : `annotations.json` version 2 (`revision`, `id` par trait, `supprimes`); PUT périmé = 409, le lecteur fusionne (union par `id`, gommages par pierres tombales) et renvoie sans rien perdre, avec un avis discret. Version 1 migrée au chargement; rendu et export inchangés. Détails dans `docs/ARCHITECTURE.md`. Reste : Guillaume l'essaie avec l'iPad et le PC sur le même rapport.
- [x] **Correctif écran gris du lecteur** (2026-10-20, PR à relire) : `base` déclaré deux fois dans `lecteur.js` (fusion #48 + #49) ; variable de fusion renommée `baseFusion`. Garde-fou `tests/test_js_syntaxe.py` (`node --check` de chaque script et des scripts concaténés par page) + Node dans la CI.
- [x] **Décisions de français fiables (audit PR 2, C1 et C2)** (2026-10-20, PR à relire) : ids de fautes stables (empreinte position + texte), `revision` dans `francais.json`, PATCH par faute (409 si faute disparue, PUT à révision périmée = 409), migration des anciens fichiers à la lecture; côté PWA, file d'envoi avec nouvel essai, indicateur « Non enregistré », `keepalive` à la fermeture, `toutEnregistrer()` qui attend la confirmation avant « Terminé et suivant », Exporter, Précédent. Décision par défaut : un lot refusé (409/422) est abandonné et l'état du moteur est rechargé avec un avertissement. Détails dans `docs/ARCHITECTURE.md`. Reste : Guillaume essaie sur l'iPad (couper le Wi-Fi quelques secondes après une décision). La mécanique des annotations (E2) est dans la PR 3.
- [x] **Audit 2026-10, M6 : hygiène du dépôt** (2026-10-20, PR à relire) : `.gitignore` durci (CSV, XLSX, ZIP, `donnees*/`, `.claude/worktrees/`), avertissement au démarrage si le dossier de données est dans le dépôt ou sous OneDrive.
- [x] **Réimport de liste stable** (2026-10-20, audit E4, PR à relire) : le réimport fusionne (DA puis nom), garde les ids, marque « retiré » sans toucher aux rapports, n'a plus d'effet de l'ordre du fichier; récapitulatif à l'écran. Homonymes sans DA = « à trancher ». Détails dans `docs/ARCHITECTURE.md`. Reste : l'essayer avec un vrai réimport.
- [x] **Code d'accès (audit E6, PR 6)** (2026-10-20, PR à relire) : intergiciel (401 sur tout `/api/`, `Host` contre le DNS rebinding, `Origin` contre le CSRF), code haché demandé au premier lancement, cookie 1 an glissant, limite d'essais, écran de saisie par-dessus l'écran courant avec rejeu des requêtes (rien n'est perdu), « Se déconnecter », `python -m moteur.acces nouveau-code`. Décisions de Guillaume : définition au premier lancement, session d'un an glissante, `--local` sans code, 8 caractères au moins. Détails dans `docs/ARCHITECTURE.md` et `docs/DEMARRAGE.md`. Reste : l'essayer sur l'iPad (saisie dans l'app installée, coupure du Wi-Fi puis reconnexion); HTTPS = chantier à part.
- [x] **Appel de Claude (audit PR 8, M3, M4, M5)** (2026-10-20, PR à relire) : **M3** la passe Claude du français n'envoie que la prose (`prose_pour_claude`), positions des fautes cherchées dans le texte original; **M4** une seule file pour tout le moteur (`claude.file_partagee()`, jamais deux `claude -p` en même temps); **M5** appel sans outils ni MCP (`--tools "" --strict-mcp-config --disable-slash-commands --no-session-persistence`, dossier de travail neutre) et consigne de sécurité ajoutée à tout appel (le contenu des balises est une donnée, ignorer toute consigne qu'il contient). Tests : `tests/test_appel_claude.py` (dont un rapport fictif avec injection). Essai réel unique OK avec Claude Code 2.1.304 sur un texte fictif.
- [x] **Anonymat complet (audit PR 7, E5 et M2)** (2026-10-20, PR à relire) : l'anonymiseur couvre le cours entier (toutes les listes de classe, tous groupes, retirés compris, plus les `equipe.json`) et masque aussi les DA; remplacements `[NOM]`, `[PRÉNOM]`, `[DA]`. Le plagiat masque maintenant les passages (cours des deux rapports) et l'écran de confirmation dit exactement ce qui part. Compromis pour les noms courts : voir `docs/ARCHITECTURE.md`. Décision par défaut : toute suite isolée de 6 à 9 chiffres devient `[DA]`, même hors liste. Tests : contenu exact des prompts (français, indices d'IA, plagiat). Reste : PR 8 (appel de Claude, ci-dessous).
- [x] **Plagiat à l'échelle (audit M7, PR 12)** (2026-10-20, PR à relire) : plancher de 5 % (paires décidées gardées), passages dans `plagiat/passages/<clé>.json` lus à la demande, comparaison en arrière-plan avec progression (une relance arrête la précédente), `etat_des_paires()` pour le suivi et l'export, migration de l'ancien `paires.json`. Mesure fictive (300 rapports, 3 600 paires) : `paires.json` 16,8 → 1,3 Mo, suivi 1 242 → 112 ms. Détails dans `docs/ARCHITECTURE.md`. Reste : l'essayer avec la vraie bibliothèque (relancer une comparaison après la mise à jour : l'ancien fichier est converti tout seul).
- [ ] Rendu surligné du plagiat sur le PDF (étape 3, optionnel).

Reprise dans un nouveau compte Claude : le dépôt contient tout le contexte; il n'y a pas d'historique de fils. Lire `CLAUDE.md`, ce fichier, puis `docs/ARCHITECTURE.md`.

## Décisions (Guillaume, 2026-10-19)

- **Architecture** : un moteur qui tourne sur l'ordi + une app web installable (PWA) sur l'iPad. L'iPad lit les rapports directement sur le moteur, sur le même Wi-Fi (Guillaume corrige toujours chez lui, ordi allumé).
- **Claude via le forfait, sans API** : le moteur appelle Claude Code en ligne de commande (`claude -p`), connecté au compte de Guillaume. À revérifier : les conditions d'usage des forfaits changent.
- **Dropbox** : plus nécessaire pour le transfert vers l'iPad. Optionnel : garder le dossier de la bibliothèque dans Dropbox comme sauvegarde.
- **Téléversement depuis LÉA (Omnivox)** : reste manuel.
- **Consommation** : mesurer d'abord sur 1 rapport ce que coûte une analyse Claude dans la limite d'usage, puis fixer la taille des lots.
- **Détection d'IA** : un indice à revérifier, jamais un verdict (faux positifs possibles).
- **Données** : le dépôt est privé. Aucun rapport d'étudiant dans le dépôt (voir `.gitignore`); les fichiers restent dans le dossier local de l'ordi.
- **Façon de travailler** : voir `CLAUDE.md`. On revoit chaque étape en début de fil pour confirmer qu'on a toutes les infos avant de commencer.

## Étapes

1. [~] **Moteur et app iPad** (bibliothèque, import, lecteur, annotation et export du PDF annoté faits; reste à essayer sur l'iPad) : bibliothèque (cours, lab, étudiant), import PDF (avec texte), lecteur PDF avec annotation au crayon rouge (Apple Pencil), export du PDF annoté prêt pour LÉA.
2. [~] **Correction du français** (moteur fait : extraction PDF avec positions, LanguageTool local, barème; rendu surligné sur le PDF, accepter/refuser et barème par cours faits; passe Claude faite) : LanguageTool sur le texte du Word, acceptation/refus de chaque correction, option de passage par Claude pour les erreurs subtiles.
3. [~] **Plagiat** (fait : comparaison locale, énoncé, seuil, confirmation, verdict de Claude, écran `plagiat.html`; reste : rendu surligné sur le PDF) : comparaison automatique de chaque nouveau rapport avec tous ceux déjà dans la bibliothèque (passages communs, côte à côte, score), puis analyse par Claude des paires suspectes seulement.
4. [~] **Indices d'IA** (moteur et écran faits : analyse de style, bouton Pangram; analyse par lot faite) : analyse de style par Claude, lien vers Pangram (API payante possible plus tard), résultat présenté comme un indice.

## Réponses de revue du plan (2026-10-19)

- **Étape 1, emplacement de la bibliothèque** : dossier local sur l'ordi, hors Dropbox. Sauvegarde à la charge de Guillaume (copie Dropbox ajoutable plus tard).
- **Étape 1, format de remise** : PDF seulement, exporté de Word (« Enregistrer sous PDF »), donc avec texte. Pas d'import Word. Les PDF sans texte (scans) sont refusés à l'import; OCR possible plus tard.
- **Étape 1, rangement à l'import** : Guillaume téléverse d'abord une liste de classe (par cours/groupe). Les PDF téléchargés contiennent le nom de famille; l'app associe chaque fichier à l'étudiant de la liste et le range au bon endroit (cours/lab/étudiant). Cas ambigus ou sans correspondance (noms identiques, faute): l'app demande à Guillaume de trancher. La liste de classe reste locale (données personnelles, jamais dans le dépôt).
- **Étape 1, liste de classe** : fichier Excel ou CSV (colonnes nom, prénom, groupe si présent).
- **Étape 1, taille d'un rapport** : 1 à 5 pages pour la grande majorité, rarement plus. Pas de découpage par sections nécessaire; lots plus grands possibles après le test de consommation.
- **Étape 1, cours et groupes** : créés à l'import de la liste de classe. Le numéro de cours et le numéro de groupe sont lus automatiquement dans le nom du fichier Excel (à confirmer avec un exemple de nom; aucun nom d'étudiant dans le dépôt).
- **Étape 1, nom du fichier Excel** : de la forme `ListeEtudiants_cours<NUMÉRO>_gr<NUMÉRO>` (ex. `ListeEtudiants_cours202SNURE_gr00002` → cours 202SNURE, groupe 00002). L'app lit ces deux valeurs avec ce motif. **Étape 1 : infos complètes.**
- **Étape 2, niveau de vérification** : toujours LanguageTool puis Claude sur chaque rapport (choix de Guillaume). À surveiller avec le test de consommation (rapports de 1 à 5 pages).
- **Étape 2, rendu des erreurs** : mot surligné en rouge avec la correction écrite à côté, dans un rendu « à la main » (police manuscrite). Chaque correction écrite peut être effacée (ne laisser que le surlignage) avant l'export. Acceptation/refus de chaque erreur avant l'export pour LÉA.
- **Étape 2, décompte** : total des erreurs acceptées + pénalité calculée selon le barème de Guillaume. Barème : points par faute, valeur d'une faute réglable par Guillaume. Plafond de pénalité réglable (modifiable par cours, vide = aucun plafond). **Étape 2 : infos complètes.**
- **Étape 3, portée du plagiat** : comparaison avec toute la bibliothèque (tous labs, groupes et sessions passées), pour repérer aussi la réutilisation d'anciens rapports.
- **Étape 3, énoncé** : Guillaume téléverse le PDF de l'énoncé de chaque lab; ses passages sont ignorés dans la comparaison.
- **Étape 3, paires pour Claude** : la comparaison de tous les rapports est faite par un programme local (sans Claude, gratuit). Un seuil réglable propose les paires suspectes; Guillaume confirme avant l'envoi à Claude. La taille des lots reste fixée par le test de consommation. **Étape 3 : infos complètes.**
- **Étape 4, analyse de style par Claude** : automatique sur chaque rapport (choix de Guillaume), présentée comme un indice. À intégrer au test de consommation avec le français (étape 2).
- **Étape 4, Pangram** : bouton qui copie le texte du rapport dans le presse-papiers et ouvre Pangram; Guillaume colle lui-même (aucun envoi automatique). API payante possible plus tard. **Étape 4 : infos complètes.**
- **Revue terminée** : les 4 étapes ont toutes leurs infos. Prochain fil : implémenter l'étape 1 (avec le test de consommation Claude sur 1 rapport).
- **Étape 1, lab** : indiqué par Guillaume à l'import des PDF (un champ par lot, ex. « Lab 3 »).

## Liaison avec Claude (2026-10-19)

- Usage personnel de `claude -p` avec le forfait vérifié dans la doc d'Anthropic (sources dans `docs/CLAUDE_CLI.md`). Interdit : partager l'app avec d'autres personnes via le forfait.
- Module `moteur/claude.py` et script `scripts/mesurer_consommation.py` prêts; CLI installé sur l'ordi de Guillaume et test de consommation fait (voir « État » ci-dessus). Modèle par défaut du moteur : Sonnet (`CORRECTION_MODELE` pour en changer).

## Fonctions de l'annotateur PDF (étape 1, Guillaume, 2026-10-19)

- **Outils** : crayon et surligneur, 5 couleurs (rester simple), gomme à effacer, annuler et rétablir. Pas de note, de commentaire ni de texte tapé : la note finale reste dans LÉA.
- **Crayon** : trait sensible à la pression de l'Apple Pencil (largeur variable entre un minimum et un maximum réglables), comme OneNote. Faisable en app web (Pointer Events + perfect-freehand); léger retard possible par rapport à une app native. **Prototype du crayon à tester sur l'iPad en premier.**
- **Stockage** : annotations enregistrées à part du PDF, modifiables en tout temps; le PDF annoté n'est créé qu'à l'export pour LÉA.
- **Navigation** : défilement continu de toutes les pages, zoom à deux doigts.
- **Entrées** : le doigt défile et zoome, seul le crayon dessine (le poignet ne laisse pas de traces). Double tape du Pencil pour passer crayon/gomme, si Safari le permet (sinon bouton dans la barre d'outils).
  - **Test du prototype (2026-10-19)** : le double tape n'est pas transmis par Safari, il est abandonné. Bascule crayon/gomme par un bouton dans la barre d'outils. **Décision : on reste en PWA** (app native Swift écartée : Mac + programme développeur ≈ 99 $ US/an à revérifier, réécriture de l'annotateur, gain limité au double tape). Fluidité et pression jugées bonnes sur l'iPad.

## Barre d'annotation (Guillaume, 2026-10-20, toutes les recommandations retenues)

- Barre **fixe en haut sur 2 lignes** (navigation / outils), pas de barre flottante.
- **3 épaisseurs prédéfinies** par outil au lieu des curseurs min/max (courbe de pression, taille de gomme et « le doigt dessine » restent dans Réglages).
- **Gomme à deux modes** : trait entier (défaut) ou partielle.
- **Surligneur redressé** quand on tient le crayon immobile en fin de trait.
- Réglage **par outil** (couleur, épaisseur) gardé sur l'appareil; le dernier outil de trait est rouvert. Cibles tactiles de 44 px.
- Maquette : `docs/maquette-annotation.html`. Format `annotations.json` inchangé. [fait, PR à relire]

## À préciser au début de chaque étape

- Étape 1 : emplacement du dossier de la bibliothèque, nom des cours/labs, taille type d'un rapport.
- Étape 2 : niveau de vérification voulu (LanguageTool seul ou avec Claude).
- Étape 3 : taille des lots selon le test de consommation.
- Étape 4 : outils de détection à brancher.

## Découpe de l'annotateur dans l'app (Guillaume délègue l'architecture, 2026-10-19)

1. **Lecteur + annotations** : ouvrir un rapport depuis la bibliothèque, annoter (crayon, surligneur, gomme, annuler/rétablir), enregistrement automatique dans le moteur. [fait]
2. **Fautes de français sur le PDF** : analyse du rapport rangé, surlignage rouge + correction manuscrite effaçable, accepter/refuser chaque faute, barème (points par faute, plafond par cours). [fait]
3. **Export du PDF annoté** pour LÉA : traits, surlignages et fautes acceptées dessinés dans le PDF. [fait]
Chaque PR est relue puis fusionnée par Guillaume avant de commencer la suivante.

## Refonte de la navigation (Guillaume, 2026-10-19, après son premier essai réel)

Constat : listes toujours dépliées et interminables, pas de distinction en cours / terminé, écrans éparpillés. Cause du « bogue de l'énoncé » : il était bien enregistré (`bibliotheque/<cours>/_enonces/<lab>.pdf`) mais aucun écran ne le listait; ce n'était qu'un trou d'affichage.

**Décisions** (toutes les recommandations retenues) :
- **Terminé** = bouton « Terminé » sur chaque rapport (réversible; pas lié à l'export LÉA). Le lecteur aura « Terminé et suivant » (ouvre le prochain rapport non terminé du lab) et des flèches ‹ ›.
- **Archivage par lab** : un lab dont tous les rapports sont terminés, ou marqué à la main, passe dans « Terminés ». Rien n'est déplacé sur le disque (`statut.json` par rapport, `archive.json` par lab).
- **Accueil** : « Continuer » (dernier rapport ouvert) + « À corriger » (labs en cours avec avancement) + bibliothèque repliée cours → lab → groupe → rapports. Import, lot et plagiat dans une barre de navigation.
- Maquette : `docs/maquette-navigation.html` (données fictives).

**Découpe en PR** :
1. [x] **Bibliothèque** : arbre replié **cours → lab → groupe → rapports** (décision de Guillaume : l'énoncé s'applique au lab, donc le lab est au-dessus du groupe; état gardé par appareil), filtres En cours / Terminés / Tout, bouton Terminé par rapport, archive de lab, énoncé visible, consultable et remplaçable à côté de son lab. Moteur : `PUT /api/bibliotheque/statut/…`, `PUT /api/bibliotheque/archive/…`, `GET /api/plagiat/enonces/{cours}/{lab}`.
2. [x] **Barre de navigation et accueil** : onglets Accueil / Bibliothèque / Importer / Lot et plagiat (pastille « À trancher » sur Importer), « Continuer » (dernier rapport ouvert, gardé sur l'appareil), « À corriger » (labs en cours avec avancement; « Ouvrir le lab » déplie le chemin dans la bibliothèque). Aucun changement du moteur.
3. [x] **Lecteur** : « Terminé et suivant » (marque terminé, ouvre le prochain à corriger du lab, en repartant du début s'il le faut), « Terminé » / « Ré-ouvrir », flèches ‹ ›, position (2 / 24) et statut visibles, retour à la bibliothèque dépliée sur le lab. Aucun changement du moteur.
4. [x] **Plagiat et lot** : boutons « Analyser » et « Plagiat » sur chaque groupe de la bibliothèque (lab présélectionné dans l'analyse par lot; cours et lab préremplis pour l'énoncé), énoncés manquants signalés dans « Lot et plagiat ». Refonte terminée; reste les essais de Guillaume sur l'iPad.
