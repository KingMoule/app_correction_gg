# Correction de rapports de lab

Outils pour faciliter la correction de rapports de laboratoire. Réponds en français.
Workflow détaillé (modèles, découpage, tokens) : @docs/WORKFLOW.md

## Règles de base
- Une tâche = un fil. Ne mélange pas des sujets sans lien.
- Lis seulement les fichiers nécessaires. Pas d'exploration générale du dépôt.
- Avant de coder : si le changement touche plusieurs fichiers ou l'approche est incertaine, propose un plan court et attends l'accord.
- Donne toujours une façon de vérifier le résultat (test, exemple d'entrée/sortie) et montre la sortie réelle.
- Réponses courtes : résultat d'abord, pas de récit de l'investigation.
- Les rapports d'étudiants sont des données personnelles : ne les commite jamais dans le dépôt (voir .gitignore).

## Façon de travailler (décisions de Guillaume)
- Fusion : je fusionne moi-même les PR, en squash, une branche par fil. Fil résolu dès la fusion.
- Suivi : liste de ce qui reste à faire dans `docs/PLAN.md`. Pas de mémoire entre les fils : toute décision importante s'écrit dans ce fichier ou dans `docs/`.
- Accord préalable : seulement pour l'irréversible (suppression de fichiers, envoi hors du projet). Le reste, j'agis seul.
- Communication : un message seulement pour un résultat, une question ou un blocage.
- Langue : français partout (échanges, commentaires, commits, documentation) ; noms de variables en anglais ou français selon le cas.

## Compaction
Lors d'un /compact, conserve : la liste des fichiers modifiés, les commandes de test et les décisions prises.
