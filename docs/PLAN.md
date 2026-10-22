# Plan général

Objectif : une seule app pour corriger les rapports de lab (français, annotation, plagiat, indices d'IA), au lieu de Word, Dropbox, OneNote et l'iPad.
Historique (étapes faites, réponses de revue, journal des PR) : `docs/HISTORIQUE.md`. Ne pas le lire sans raison. Audit de code : `docs/AUDIT-2026-10.md` (état de chaque constat en tête).

## État au 2026-10-20

Tout est fusionné dans `main` jusqu'à la PR #56. Les 4 étapes sont faites côté moteur et écrans : bibliothèque et import, lecteur et annotation au crayon, fautes de français (LanguageTool + passe Claude), plagiat, indices d'IA, analyse par lot, export du PDF annoté et du `Travaux.zip` pour LÉA, tableau de suivi d'un lab, sauvegarde, code d'accès. L'audit 2026-10 est corrigé sauf M8, F3, F4, F6 (voir l'audit). Design chaleureux appliqué (`docs/DESIGN.md`).

## Reste à faire

- [ ] **Refonte visuelle, direction A « Atelier » en sarcelle** (choisie le 2026-10-21) : PR 1 fondations (jetons, composants, coque, `pwa/composants.html`) faite; PR 2 (accueil avec « À faire », bibliothèque, import, code d'accès) en relecture; PR 3 (suivi en tableau dense avec balayage d'une ligne, plagiat, indices d'IA, lot, export LÉA) en relecture; PR 4 (lecteur : rail d'outils, inspecteur à onglets, fiche de la faute, feuille en portrait, fenêtre « Terminé… ») en relecture; le trait au crayon n'apparaissait qu'au relâchement (corrigé). Guide : `docs/DESIGN.md`.
- [ ] **Essais de Guillaume sur l'iPad** : crayon dans l'app, tap sur une faute, export du PDF depuis l'app installée, design, tableau de suivi (portrait compris), code d'accès (saisie dans l'app installée, coupure du Wi-Fi puis reconnexion), annotations iPad + PC sur le même rapport, décision de français après coupure du Wi-Fi.
- [ ] **Essais sur de vrais fichiers** : liste Omnivox réimportée, import de vrais PDF (rangement, coéquipiers), lot sur de vrais rapports, jugement des fautes de français gardées (seuils dans `francais_filtre.py`), `Travaux.zip` dans LÉA (nom des fichiers; les rapports importés avant l'export n'ont pas de nom d'origine), plagiat sur la vraie bibliothèque, `demarrer.bat` (mise à jour auto, sauvegarde).
- [ ] **M8 mémoire des canvas du lecteur** : mesurer sur l'iPad (rapport de 10 pages) avant de corriger.
- [ ] **F3, F4, F6 de l'audit** (validation de segment par `$`, plafond de taille des téléversements, copie par jour dans la rotation des sauvegardes) : faibles, non faits.
- [ ] **Sauvegarde sur un autre disque** : le 2e dossier est sur le même disque (voir `docs/DEMARRAGE.md`).
- [ ] **HTTPS sur l'iPad** (cookie en clair sur le Wi-Fi) : chantier à part, non planifié.
- [ ] Idées : rendu surligné du plagiat sur le PDF; lecture de la note écrite au crayon (écartée pour l'instant : la note se saisit à « Terminé »); mesure de consommation avec `haiku`.

## Décisions en vigueur (Guillaume)

### Architecture et données
- **Moteur local + PWA** : le moteur tourne sur l'ordi (Windows), l'iPad lit les rapports directement sur le même Wi-Fi (Guillaume corrige chez lui, ordi allumé). **PWA, pas d'app native** (le double tape du Pencil n'est pas transmis par Safari : bouton crayon/gomme à la place).
- **Claude via le forfait, sans API** : le moteur appelle `claude -p` connecté au compte de Guillaume (`docs/CLAUDE_CLI.md`). Usage personnel seulement : ne pas partager l'app. À revérifier si le forfait change.
- **Données personnelles** : dépôt privé, aucun rapport, liste de classe ni sauvegarde dedans (`.gitignore`). Tout reste dans le dossier local de l'ordi, hors OneDrive (avertissement au démarrage sinon). Avant tout envoi à Claude, noms, prénoms et DA du cours entier sont masqués.
- **Dropbox** inutile pour le transfert. **Téléversement dans LÉA** : manuel.
- **Indices d'IA et de plagiat** : toujours un indice à revérifier, jamais un verdict. Pangram : bouton qui copie le texte, Guillaume colle lui-même.

### Bibliothèque et import
- **PDF seulement** (exporté de Word, avec texte); les scans sont refusés. Taille : 1 à 5 pages.
- **Rangement** `cours / lab / groupe / étudiant` : l'énoncé s'applique au lab, donc le lab est au-dessus du groupe. Liste de classe Omnivox/LÉA (CSV ou Excel, `ListeEtudiants_cours<N>_gr<N>`) importée d'abord; le lab est indiqué à l'import; groupe facultatif (multi-groupes). Association par n° de DA, puis nom; cas ambigus laissés à Guillaume.
- **Jamais de suppression silencieuse** : « Écarter » déplace dans `_ecartes/` après confirmation; remplacer un rapport déjà importé demande une confirmation et met tout l'ancien dossier (annotations, fautes, note comprises) dans `_remplaces/`, on repart à neuf.
- **Réimport de liste** : fusion (DA puis nom), ids gardés, étudiants absents marqués « retiré » sans toucher aux rapports; homonymes sans DA = « à trancher ».
- **Coéquipiers** : rapport rangé une fois au nom du déposant; équipe en métadonnée (détection stricte sur la page titre, modifiable); note commune saisie dans LÉA; une ligne par coéquipier dans le CSV; le plagiat ignore les paires d'une même équipe.
- **Terminé** : bouton réversible par rapport; un lab dont tous les rapports sont terminés (ou marqué à la main) va dans « Terminés », rien n'est déplacé. États du suivi calculés, non stockés. « Rapport suivant » = prochain non terminé, en repartant du début.

### Correction
- **Français** : toujours LanguageTool puis passe Claude. **Prose seulement** (pas de calculs, tableaux, références); la typographie ne compte pas; lexique global. Faute = mot surligné en rouge + correction manuscrite effaçable (police Caveat), à accepter ou refuser; seules les acceptées sont exportées. **Barème** : points par faute et plafond réglables par cours (plafond vide = aucun).
- **Plagiat** : comparaison locale de toute la bibliothèque (tous labs, groupes, sessions); énoncé téléversé par lab, ses passages ignorés; seuil d'affichage réglable; **confirmation de Guillaume avant tout envoi à Claude**, une paire à la fois, passages masqués.
- **Indices d'IA** : analyse de style automatique par Claude.
- **Analyse par lot** : modèle par défaut **Sonnet** (`CORRECTION_MODELE`); 10 rapports par lot (marge de 20 % de la session de 5 h; mesuré : Opus 3 %, Sonnet 2 % par rapport de 3 pages, ±1 point); les rapports déjà analysés sont ignorés sauf case « Refaire »; arrêt propre sur limite d'usage; **une seule file Claude** pour tout le moteur, appel sans outils ni MCP.
- **Fiabilité** : tout JSON passe par `stockage.py` (écriture atomique, verrou); annotations et décisions de français ont une `revision` (409 sur révision périmée, fusion côté lecteur; un lot de décisions refusé est abandonné et l'état du moteur rechargé avec un avertissement).

### Lecteur et annotation
- Défilement continu, zoom à deux doigts; le doigt défile, **seul le crayon dessine**. Outils : crayon (pression), surligneur (redressé si le crayon reste immobile), gomme (trait entier par défaut, ou partielle), 5 couleurs, annuler/rétablir. **Pas de texte tapé** : la note finale reste dans LÉA. Annotations stockées à part du PDF; le PDF annoté n'existe qu'à l'export.
- Barre fixe en haut sur 2 lignes (navigation / outils), 3 épaisseurs prédéfinies, réglage par outil gardé sur l'appareil, cibles de 44 px.
- Panneau des fautes : colonne à droite (sous le PDF en portrait), fiche de la faute en haut du panneau; correction manuscrite déplaçable (décalage enregistré); pas de trait de rappel.
- Accueil : « Continuer » + « À corriger »; onglets Accueil / Bibliothèque / Importer / Lot et plagiat.
- **Design** (`docs/DESIGN.md`) : direction « Atelier » (barre latérale de 248 px, neutres froids, accent sarcelle, Inter, lignes de 52 px), appliquée écran par écran.

### Export et exploitation
- **Export LÉA** : `Travaux_<date>.zip` (PDF au nom d'origine + `_corrige`) et CSV (`;`, UTF-8 avec BOM, virgule décimale); inachevés exclus sauf case « inclure » et signalés; « Claude manquant » compte comme inachevé; l'export se déclare périmé si un rapport change; note saisie à « Terminé ».
- **Sauvegarde** : 2e dossier sur l'ordi (`C:\correction_donnees_sauvegardes`, `CORRECTION_SAUVEGARDES`), à chaque lancement de `demarrer.bat` (ni bouton ni tâche planifiée), 10 dernières + 1 par semaine sur 8 semaines, tout sauf `plagiat/textes/`; restauration sans jamais supprimer.
- **Code d'accès** : 8 caractères au moins, défini au premier lancement, session d'un an glissante, `--local` sans code, aucune route `/api/` publique.
- **Démarrage** : `demarrer.bat` en un clic, `git pull --ff-only` sur `main` propre (`docs/DEMARRAGE.md`).
