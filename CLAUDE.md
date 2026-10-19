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

## Dépôt
- Branche de travail : celle du fil ; PR brouillon vers `main`.
- Commits petits, message clair en français ou en anglais (rester cohérent).

## Compaction
Lors d'un /compact, conserve : la liste des fichiers modifiés, les commandes de test et les décisions prises.
