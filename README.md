# app_correction_gg

Outils pour corriger les rapports de laboratoire : bibliothèque de rapports (cours, groupe, lab, étudiant), annotation au crayon sur iPad, fautes de français (LanguageTool), plagiat, indices d'IA, export du PDF annoté pour LÉA.

Un moteur Python (FastAPI) tourne sur l'ordi; l'iPad utilise une app web installable (PWA) sur le même Wi-Fi.

- Lancer : `pip install -e ".[test]"` puis `python -m moteur` (tests : `pytest`).
- Plan et état : `docs/PLAN.md`. Structure : `docs/ARCHITECTURE.md`. Façon de travailler : `CLAUDE.md`.
- Aucun rapport d'étudiant dans le dépôt (données sous `donnees/`, exclu par `.gitignore`).
