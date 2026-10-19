# Workflow Claude Code pour les Projets (beta)

Principe : le contexte est la ressource à protéger. Plus il est gros, plus chaque message coûte cher et plus la qualité baisse.

## 1. Choisir le modèle

| Tâche | Modèle |
|---|---|
| Défaut : coder, corriger, scripts, PR | **Sonnet 5.5** |
| Recherche simple, tri, reformatage, résumés, tâches répétitives | **Haiku 5.5** |
| Architecture, bogue difficile, planification complexe | **Opus 5.5** (ou Fable 5.1), puis retour à Sonnet |

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
- Effort de raisonnement bas pour les tâches simples, élevé seulement pour les problèmes difficiles.
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

## 5. Cycle recommandé

1. **Explorer** (petit, ciblé) → 2. **Plan** court validé → 3. **Implémenter** → 4. **Vérifier** avec sortie réelle → 5. **PR brouillon** → 6. Fermer le fil.

Tâche d'une phrase (typo, renommage) : sauter le plan.

## 6. Texte court pour les « instructions du projet »

```
Réponds en français, de façon brève (résultat d'abord).
Modèle par défaut : Sonnet. Haiku pour tâches simples, Opus seulement si nécessaire.
Un fil par objectif. Lis uniquement les fichiers utiles. Plan court avant toute
modification touchant plusieurs fichiers. Vérifie et montre la sortie réelle.
Ne commite jamais de rapports d'étudiants. Voir CLAUDE.md et docs/WORKFLOW.md du dépôt.
```

## Sources
Documentation Claude Code : « Manage costs effectively » et « Best practices » (code.claude.com/docs).
