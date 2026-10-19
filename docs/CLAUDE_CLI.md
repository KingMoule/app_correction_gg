# Liaison avec Claude (`claude -p`)

## Conditions d'usage (vérifié le 2026-10-19)

Le moteur appelle Claude Code en ligne de commande, connecté au forfait de Guillaume (pas de clé API). Sources officielles :

- **Usage personnel permis.** « Advertised usage limits for Pro and Max plans assume ordinary, individual usage of Claude Code and the Agent SDK » ; l'authentification OAuth du forfait « is designed to support ordinary use of Claude Code ». Un outil perso qui lance `claude -p` sur son propre ordi, avec sa propre connexion, en fait partie. — [Legal and compliance](https://code.claude.com/docs/en/legal-and-compliance)
- **Ce qui est interdit** : offrir la connexion Claude.ai dans une application destinée à d'autres, router les requêtes d'autres personnes par un forfait, ou collecter/stocker les identifiants Claude.ai. Le moteur ne touche jamais aux identifiants : la connexion se fait avec Claude Code lui-même. **Ne pas partager l'app avec d'autres personnes** sans passer à une clé API. — même page
- **`-p` est le mode documenté** pour les scripts (`--output-format json`, `--json-schema`). — [Run Claude Code programmatically](https://code.claude.com/docs/en/headless)
- **Limites partagées** : l'usage de Claude Code et de Claude (web, mobile) compte dans les mêmes limites du forfait. — [Using Claude Code with your Pro or Max plan](https://support.claude.com/en/articles/11145838)
- Les conditions changent : à revérifier si le forfait change ou si un appel est refusé.

## Pièges pris en compte dans le code (`moteur/claude.py`)

- `--bare` n'est **pas** utilisé : il ignore la connexion au forfait et exige une clé API.
- `ANTHROPIC_API_KEY` est retirée de l'environnement de l'appel : si elle existait, Claude Code l'utiliserait et facturerait l'API.
- Le texte est envoyé par l'entrée standard (pas de limite d'argument ; plafond de 10 Mo).
- Appel lancé depuis un dossier vide : ni `CLAUDE.md` ni réglages d'un projet ne sont chargés.
- `--permission-mode dontAsk` : rien ne demande d'approbation (le moteur n'a besoin d'aucun outil).

## Utiliser le module

```python
from moteur.claude import ClientClaude, FileClaude, ClaudeNonConnecte, ClaudeLimite

file = FileClaude(ClientClaude(modele="sonnet"))   # une file pour tout le moteur
futur = file.soumettre("…<rapport>…</rapport>", schema={...}, systeme="…")
r = futur.result()        # r.structure (dict si schéma), r.texte, r.usage, r.cout_usd
```

Erreurs (toutes des `ClaudeErreur`) : `ClaudeIntrouvable` (non installé), `ClaudeNonConnecte` (lancer `claude` puis `/login`), `ClaudeLimite` (limite du forfait atteinte, réessayer après la réinitialisation), `ClaudeDelai`, `ClaudeSortieInvalide`, `ClaudeEchec`. Une erreur dans une tâche n'arrête pas la file.

## Test de consommation (à lancer par Guillaume)

Prérequis : Claude Code installé et connecté (`claude`, puis `/login` si besoin) ; `pip install -e .` fait une seule fois (installe aussi la lecture des PDF).

1. Dans Claude Code, tape `/usage` et note le pourcentage de la limite de session (5 h) et de la limite de la semaine **avant**. Ne rien faire d'autre avec Claude pendant le test.
2. Depuis le dossier du projet :
   ```
   python scripts/mesurer_consommation.py chemin/du/rapport.pdf
   ```
   Le script envoie 2 analyses (français, indices d'IA) et affiche les jetons et un coût *estimé* (équivalent API, non facturé avec le forfait).
3. Retape `/usage` : la différence de pourcentage = le coût réel du rapport dans le forfait.
4. Divise la marge voulue (ex. 20 % de la limite de session) par cette différence pour fixer la taille d'un lot. Note les valeurs dans `docs/PLAN.md`. Option `--modele haiku` ou `sonnet` pour comparer.

Le résumé chiffré est écrit dans `donnees/consommation/` (hors git). Le texte du rapport n'est jamais écrit dans le dépôt.
