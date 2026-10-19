# Architecture

## Pile technique
- **Moteur** : Python 3.10+, FastAPI + uvicorn. Choisi pour la suite : lecture de PDF, comparaison de textes (plagiat), appel de `claude -p` et LanguageTool sont tous simples en Python.
- **PWA** : HTML/CSS/JavaScript sans étape de compilation, servie par le moteur depuis `pwa/`. Aucun outil Node requis pour l'utiliser.
- **Tests** : pytest. **Contrôle** : GitHub Actions (`.github/workflows/ci.yml`) lance les tests à chaque PR.

## Structure
```
moteur/        API et logique (un module par fonction)
  app.py       assemble l'application, route /api/etat
  config.py    chemins, dossier de données
  bibliotheque.py  liste de classe, import des PDF, rangement cours/groupe/lab/étudiant
  pdf_texte.py extraction du texte d'un PDF + position de chaque mot
  languagetool.py client du serveur LanguageTool local
  bareme.py    pénalité (points par faute, plafond)
  francais.py  API /api/francais (analyser, bareme)
  __main__.py  commande de lancement
pwa/           app iPad (index.html, app.js, manifest, icône)
prototypes/    essais autonomes (ex. crayon), hors moteur
tests/         tests pytest
donnees/       données locales, exclu du dépôt (.gitignore)
docs/          plan, workflow, architecture
```

## Lancer
```
pip install -e ".[test]"   # une seule fois
python -m moteur           # affiche l'adresse à ouvrir sur l'iPad
pytest                     # tests
```
Sur l'iPad (même Wi-Fi) : ouvrir l'adresse affichée dans Safari, puis Partager → « Sur l'écran d'accueil ». Option `--local` : accès depuis l'ordi seulement. Le dossier de données se change avec la variable `CORRECTION_DONNEES`.

## Ajouter une fonction
1. Créer `moteur/<fonction>.py` avec un `APIRouter` (préfixe `/api/<fonction>`).
2. L'inscrire dans `creer_app()` de `moteur/app.py`, avant le montage de la PWA.
3. Ajouter l'écran dans `pwa/` et un test dans `tests/`.
Les fichiers des étudiants vont seulement sous `donnees/`.

## Correction du français (étape 2, moteur)
- `POST /api/francais/analyser` (PDF en multipart, `points_par_faute`, `plafond`) : texte, fautes avec `zones` (rectangles en points PDF, origine en haut à gauche, par page) et pénalité si toutes acceptées.
- `POST /api/francais/bareme` : pénalité pour un nombre de fautes acceptées.
- LanguageTool : serveur local requis (Java), `java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081`; adresse via `LANGUAGETOOL_URL`. Sans serveur, l'API répond 503.
- Sans état : rien n'est conservé; décisions accepter/refuser, rendu sur le PDF et passe Claude viendront dans d'autres fils.

## Limites connues
- Connexion en HTTP sur le réseau local : pas de service worker (réservé au HTTPS), donc pas de mode hors ligne. Le moteur doit être allumé pour corriger, ce qui est déjà le cas (voir PLAN.md).
- Pas d'authentification : à n'utiliser que sur le Wi-Fi maison.

## Bibliothèque (étape 1)
Rangement : `donnees/bibliotheque/<cours>/<groupe>/classe.json` et `.../<lab>/<étudiant>/rapport.pdf`; les PDF à trancher sont dans `_attente/`.
Association : le nom de famille (sans accents ni casse) doit figurer dans le nom du fichier; le nom le plus long l'emporte; le prénom départage les homonymes; sinon le fichier va « en attente » (ambigu, aucune correspondance ou rapport déjà importé, jamais écrasé sans choix de Guillaume). Les PDF sans texte sont refusés.
