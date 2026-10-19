# Plan général

Objectif : une seule app pour corriger les rapports de lab (français, annotation, plagiat, indices d'IA), au lieu de passer par Word, Dropbox, OneNote et l'iPad.

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

1. [ ] **Moteur et app iPad** : bibliothèque (cours, lab, étudiant), import PDF (avec texte), lecteur PDF avec annotation au crayon rouge (Apple Pencil), export du PDF annoté prêt pour LÉA.
2. [ ] **Correction du français** : LanguageTool sur le texte du Word, acceptation/refus de chaque correction, option de passage par Claude pour les erreurs subtiles.
3. [ ] **Plagiat** : comparaison automatique de chaque nouveau rapport avec tous ceux déjà dans la bibliothèque (passages communs, côte à côte, score), puis analyse par Claude des paires suspectes seulement.
4. [ ] **Indices d'IA** : analyse de style par Claude, lien vers Pangram (API payante possible plus tard), résultat présenté comme un indice.

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

## Fonctions de l'annotateur PDF (étape 1, Guillaume, 2026-10-19)

- **Outils** : crayon et surligneur, 5 couleurs (rester simple), gomme à effacer, annuler et rétablir. Pas de note, de commentaire ni de texte tapé : la note finale reste dans LÉA.
- **Crayon** : trait sensible à la pression de l'Apple Pencil (largeur variable entre un minimum et un maximum réglables), comme OneNote. Faisable en app web (Pointer Events + perfect-freehand); léger retard possible par rapport à une app native. **Prototype du crayon à tester sur l'iPad en premier.**
- **Stockage** : annotations enregistrées à part du PDF, modifiables en tout temps; le PDF annoté n'est créé qu'à l'export pour LÉA.
- **Navigation** : défilement continu de toutes les pages, zoom à deux doigts.
- **Entrées** : le doigt défile et zoome, seul le crayon dessine (le poignet ne laisse pas de traces). Double tape du Pencil pour passer crayon/gomme, si Safari le permet (sinon bouton dans la barre d'outils).

## À préciser au début de chaque étape

- Étape 1 : emplacement du dossier de la bibliothèque, nom des cours/labs, taille type d'un rapport.
- Étape 2 : niveau de vérification voulu (LanguageTool seul ou avec Claude).
- Étape 3 : taille des lots selon le test de consommation.
- Étape 4 : outils de détection à brancher.
