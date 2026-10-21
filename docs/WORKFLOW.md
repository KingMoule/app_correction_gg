# Workflow Claude Code pour les Projets (beta)

Principe : le contexte est la ressource à protéger. Plus il est gros, plus chaque message coûte cher et plus la qualité baisse.

## 1. Choisir le modèle

| Tâche | Modèle |
|---|---|
| Défaut : coder, corriger, scripts, PR | **Sonnet 5.5** |
| Recherche simple, tri, reformatage, résumés, tâches répétitives | **Haiku 5.5** |
| Architecture, bogue difficile, planification complexe | **Opus 5.5** (ou Fable 5.1), puis retour à Sonnet |

Astuces : `/model opusplan` = Opus pour planifier, Sonnet pour exécuter. Fable 5.1 (`/model fable`) seulement pour les problèmes très ambigus, il peut consommer des crédits d'usage. Les sous-agents héritent du modèle du fil : fixer `model: haiku` pour les tâches simples.

Règle : commence par Sonnet. Monte d'un cran seulement après un échec réel. Ne laisse jamais Opus comme défaut. Les sous-agents simples vont sur Haiku.

## 2. Diviser le travail

- **1 fil = 1 objectif** (une fonction, un bogue, un document). Fil terminé = fil résolu ; nouveau sujet = nouveau fil.
- Gros chantier : fil 1 *explorer/planifier* → écrire le plan dans `docs/PLAN.md` → fil 2 *implémenter* à partir du plan (contexte propre).
- Recherches qui lisent beaucoup de fichiers : à déléguer à un sous-agent (seul le résumé revient).
- Pas de fils parallèles inutiles : chacun consomme sa propre part de tokens.

## 3. Réduire les tokens

- Prompts précis : fichier, comportement attendu, critère de réussite. Éviter « améliore le projet ».
- Un fil trop long ou corrigé plus de 2 fois pour la même erreur : repartir à neuf avec un meilleur énoncé.
- Garder `CLAUDE.md` court (< 100 lignes) ; les procédures rares vont dans des *skills*, pas dans `CLAUDE.md`.
- Ne pas coller de gros fichiers ou logs en entier : donner le chemin ou les lignes utiles.
- Effort de raisonnement (`/effort`) : `low` pour les petits changements, `medium` (défaut) au quotidien, `high`/`xhigh` seulement pour les problèmes difficiles. `ultrathink` dans un prompt = réflexion accrue ponctuelle.
- Compacter plus tôt si les fils s'allongent (`/autocompact`), en précisant quoi garder : `/compact garde les fichiers modifiés et les tests`.
- Pauses > 1 h dans un fil long = cache perdu : préférer un nouveau fil avec un résumé.
- Désactiver les connecteurs inutilisés.

## 4. Modèle de demande (copier-coller)

```
Objectif : …
Fichiers concernés : …
Contraintes : …
Vérification : (exemple d'entrée → sortie attendue / test à passer)
Hors sujet : …
```

Conseils de rédaction (doc Anthropic) : donner le contexte et le but, des exemples d'entrée/sortie, séparer instructions et documents avec des balises (`<rapport>…</rapport>`), mettre les longs documents en premier et la question à la fin.

## 5. Cycle recommandé

1. **Explorer** (petit, ciblé) → 2. **Plan** court validé → 3. **Implémenter** → 4. **Vérifier** avec sortie réelle → 5. **PR brouillon** → 6. Fermer le fil.

Tâche d'une phrase (typo, renommage) : sauter le plan.

## 5b. Leçons de ce projet (plus de 50 PR)

- **Contexte au démarrage** : `CLAUDE.md` n'importe (`@`) que `docs/PLAN.md` (état, reste à faire, décisions en vigueur), le tout sous 15 Ko. Les autres docs sont des pointeurs sans `@`, ouverts selon la tâche. Quand une étape est finie, son récit va dans `docs/HISTORIQUE.md`; `PLAN.md` ne garde que ce qui contraint encore le code. Mesure : `wc -c CLAUDE.md docs/PLAN.md`.
- **Une décision = une ligne dans `PLAN.md`** (section « Décisions en vigueur »), formulée une fois. Pas de mémoire entre les fils.
- **PR empilées : vérifier la base.** Une PR ouverte sur la branche d'une autre peut être fusionnée dans cette branche au lieu de `main` (arrivé avec #41 et #42 : le travail n'était pas dans `main`). Avant d'annoncer une PR prête, `gh pr view --json baseRefName` doit dire `main`; sinon la rebaser ou changer sa base. Après la fusion de la PR de dessous, vérifier que la suivante repart bien de `main`.
- **Deux PR sans conflit de texte peuvent casser le JS** (PR #53 : `base` déclaré deux fois par la fusion de #48 et #49, écran gris). Avant d'annoncer : fusionner `origin/main` dans la branche, puis `pytest` (inclut `tests/test_js_syntaxe.py`, qui lance `node --check` sur chaque script et sur les scripts concaténés par page). Un conflit absent ne prouve rien.
- **Arrêter les serveurs d'essai** lancés pendant un fil (moteur, LanguageTool, aperçu) avant de terminer : ils tiennent le port 8001 et des fichiers de données.
- **Le clone est hors de OneDrive** (`C:\dev\app_correction_gg`), comme les données : OneDrive synchronise `.git` et les rapports et peut verrouiller des fichiers. Les worktrees des fils sont dans `.claude/worktrees/` (ignoré par git).
- **CI Ubuntu et Windows** : certaines erreurs (`os.replace`, encodage cp1252) n'apparaissent que sous Windows; ne pas annoncer « CI verte » avant les deux.
- **Jamais de fusion par Claude** : Guillaume fusionne, en squash. « PR prête à relire » = poussée, sans conflit avec `main`, CI verte.

## 6. Texte court pour les « instructions du projet »

```
Réponds en français, de façon brève (résultat d'abord).
Modèle par défaut : Sonnet. Haiku pour tâches simples, Opus seulement si nécessaire.
Un fil par objectif. Lis uniquement les fichiers utiles. Plan court avant toute
modification touchant plusieurs fichiers. Vérifie et montre la sortie réelle.
Ne commite jamais de rapports d'étudiants. Voir CLAUDE.md et docs/WORKFLOW.md du dépôt.
```

## Sources
- Claude Code : Manage costs, Best practices, Model configuration (code.claude.com/docs/en/costs, /best-practices, /model-config)
- Anthropic : Prompt engineering (platform.claude.com/docs/en/build-with-claude/prompt-engineering/overview)
