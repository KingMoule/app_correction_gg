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

1. [ ] **Moteur et app iPad** : bibliothèque (cours, lab, étudiant), import Word/PDF, lecteur PDF avec annotation au crayon rouge (Apple Pencil), export du PDF annoté prêt pour LÉA.
2. [ ] **Correction du français** : LanguageTool sur le texte du Word, acceptation/refus de chaque correction, option de passage par Claude pour les erreurs subtiles.
3. [ ] **Plagiat** : comparaison automatique de chaque nouveau rapport avec tous ceux déjà dans la bibliothèque (passages communs, côte à côte, score), puis analyse par Claude des paires suspectes seulement.
4. [ ] **Indices d'IA** : analyse de style par Claude, lien vers Pangram (API payante possible plus tard), résultat présenté comme un indice.

## À préciser au début de chaque étape

- Étape 1 : emplacement du dossier de la bibliothèque, nom des cours/labs, taille type d'un rapport.
- Étape 2 : niveau de vérification voulu (LanguageTool seul ou avec Claude).
- Étape 3 : taille des lots selon le test de consommation.
- Étape 4 : outils de détection à brancher.
