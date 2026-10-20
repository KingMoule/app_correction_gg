# Plan général

Objectif : une seule app pour corriger les rapports de lab (français, annotation, plagiat, indices d'IA), au lieu de passer par Word, Dropbox, OneNote et l'iPad.

## État au 2026-10-19 (à lire en premier)

Tout est fusionné dans `main` jusqu'à la PR #22 (bibliothèque, lecteur et annotation, fautes de français, export du PDF annoté, plagiat, indices d'IA, passe Claude sur le français, mesure de consommation, compatibilité Windows, analyse par lot, démarrage en un clic, liste Omnivox, import par DA et multi-groupes). Reste à faire :

- [x] **Passe Claude sur le français** (étape 2) : faite et fusionnée (PR #17). Après LanguageTool, `claude -p` repère les erreurs subtiles; mêmes zones et décisions que LanguageTool. Consommation mesurée (ligne ci-dessous).
- [ ] **Essais de Guillaume sur l'iPad** : crayon dans l'app (le prototype seul est validé), tap sur une faute pour sa fiche, export du PDF depuis l'app installée sur l'écran d'accueil.
- [x] **Mesure faite (2026-10-19)** : 1 rapport (français + indices d'IA) = **3 % de la limite de session (5 h)**, limite de la semaine inchangée (pas de hausse visible). Conditions : modèle **Opus 5.5**, rapport de 3 pages. Estimation : avec une marge de 20 % de la session, environ 6 rapports par lot **avec Opus**. **Sonnet** (même rapport, 3 pages) = **2 % de la session**, semaine inchangée : environ 10 rapports par lot avec la même marge de 20 %. Les % affichés sont entiers : mesure approximative (±1 point). Option : mesurer `haiku`, ou refaire sur 3 à 5 rapports pour affiner.
- [~] **Analyse par lot** (fusionnée, PR #19) : fait côté moteur et écran (`moteur/lot.py`, `pwa/lot.js`) : au plus N rapports d'un lab (10 par défaut), arrêt propre sur limite d'usage, bouton Arrêter, case « Refaire aussi les analysés » (décision de Guillaume : par défaut, les rapports déjà analysés sont ignorés). Modèle par défaut du moteur : Sonnet. Reste : l'essayer sur de vrais rapports. Plagiat par lot : pas de changement (déjà une paire à la fois, après confirmation).
- [x] **Import de la liste de classe Omnivox** : le vrai CSV (cp1252, `;`, `="..."`, « Nom de l'étudiant », « No de DA ») est accepté; le DA est gardé (champ `da`). Reste : Guillaume réessaie avec son vrai fichier.
- [x] **Rangement fiable à l'import** (2026-10-19, premier essai réel) : association par n° de DA puis par nom (même sans séparateurs), import multi-groupes (groupe facultatif), coéquipiers repérés sur la page titre (décision de Guillaume : rapport rangé une fois au nom du déposant, équipe en métadonnée, note commune saisie dans LÉA, plagiat ignore l'équipe), récapitulatif par groupe. Cause du dossier `_attente` vide : « Écarter » supprimait le PDF sans confirmation (et 11 rapports avaient été rangés à la main); « Écarter » déplace maintenant dans `_ecartes/` après confirmation. Reste : Guillaume réessaie avec ses vrais PDF.
- [x] **Mise à jour automatique au démarrage** (2026-10-19) : `demarrer.bat` fait `git pull --ff-only` (sur `main` propre seulement), relance `pip install -e .` si `pyproject.toml` change, affiche la version; il s'exécute depuis une copie dans `%TEMP%` pour ne pas être lu de travers si le pull le modifie. Voir `docs/DEMARRAGE.md`. Reste : Guillaume l'essaie.
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
