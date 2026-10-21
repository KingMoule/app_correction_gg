# Correction de rapports de lab

Outils pour faciliter la correction de rapports de laboratoire. Réponds en français, brièvement (résultat d'abord).
Dépôt : https://github.com/KingMoule/app_correction_gg (privé). Moteur FastAPI (Windows) + PWA sur iPad.

État, reste à faire et décisions en vigueur : @docs/PLAN.md

## À lire selon la tâche (pas d'import automatique : ouvre seulement ce qui sert)
- Code du moteur ou de la PWA : `docs/ARCHITECTURE.md` (sommaire en tête, lis seulement la section du module touché).
- Appel de Claude (`claude -p`), conditions d'usage, installation du CLI : `docs/CLAUDE_CLI.md`.
- Façon de travailler (modèle, fils, tokens, pièges de PR) : `docs/WORKFLOW.md`.
- Démarrage, sauvegarde, code d'accès côté utilisateur : `docs/DEMARRAGE.md`.
- Apparence, jetons de design : `docs/DESIGN.md`.
- Audit de code (état de chaque constat) : `docs/AUDIT-2026-10.md`.
- Pourquoi une décision a été prise, étapes faites : `docs/HISTORIQUE.md` (rarement utile).

## Règles de base
- Une tâche = un fil. Ne mélange pas des sujets sans lien.
- Lis seulement les fichiers nécessaires. Pas d'exploration générale du dépôt.
- Avant de coder : si le changement touche plusieurs fichiers ou l'approche est incertaine, propose un plan court et attends l'accord.
- Donne toujours une façon de vérifier le résultat (test, exemple d'entrée/sortie) et montre la sortie réelle.
- Les rapports d'étudiants sont des données personnelles : ne les commite jamais (voir .gitignore).
- Pas de mémoire entre les fils : toute décision importante s'écrit dans `docs/PLAN.md` (décisions en vigueur, reste à faire) ou `docs/`. Les étapes finies vont dans `docs/HISTORIQUE.md`, pas dans PLAN.md.

## Façon de travailler (décisions de Guillaume)
- Fusion : je fusionne moi-même les PR, en squash, une branche par fil. Ne fusionne jamais une PR. Fil résolu dès la fusion.
- Accord préalable : seulement pour l'irréversible (suppression de fichiers, envoi hors du projet). Le reste, j'agis seul.
- Communication : un message seulement pour un résultat, une question ou un blocage. Notifier dans le chat du projet chaque PR à relire et chaque décision à prendre.
- Questions une à une, avec choix et ta recommandation marquée.
- Découper en fils, une PR chacun, en parallèle quand c'est possible.
- Langue : français partout (échanges, commentaires, commits, documentation) ; noms de variables en anglais ou français selon le cas.

## Commandes
- Installer : `pip install -e ".[test]"` ; tester : `pytest` (inclut `tests/test_js_syntaxe.py` : `node --check` des scripts de la PWA, Node requis).
- Lancer : `python -m moteur` (port 8001, `--local` sans code d'accès). Windows : `demarrer.bat`.
- Arrête tout serveur d'essai que tu as lancé avant de terminer.

## Compaction
Lors d'un /compact, conserve : la liste des fichiers modifiés, les commandes de test et les décisions prises.
