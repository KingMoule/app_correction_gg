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
  claude.py    appel de `claude -p` (file d'attente, erreurs) ; voir docs/CLAUDE_CLI.md
  bibliotheque.py  liste de classe, import des PDF, rangement cours/groupe/lab/étudiant
  pdf_texte.py extraction du texte d'un PDF + position de chaque mot
  languagetool.py client du serveur LanguageTool local
  bareme.py    pénalité (points par faute, plafond)
  francais.py  API /api/francais (analyser, bareme)
  annotations.py API /api/annotations (traits du crayon, enregistrés à part du PDF)
  __main__.py  commande de lancement
pwa/           app iPad (index.html + app.js : bibliothèque; lecteur.html/js/css : lecteur et annotation;
               vendor/ : pdf.js, copié dans le dépôt car l'iPad n'a pas forcément Internet)
scripts/       outils à lancer à la main (ex. test de consommation)
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

## Annotations (étape 1)
- Fichier `.../<lab>/<étudiant>/annotations.json` à côté de `rapport.pdf`; le PDF n'est jamais modifié.
- `GET` / `PUT /api/annotations/<cours>/<groupe>/<lab>/<étudiant>` : `{version: 1, pages: {"1": [trait, …]}}`. Un trait : `outil` (crayon ou surligneur), `couleur` (#rrggbb), `largeur_min`, `largeur_max`, `courbe`, `points` [x, y, pression]. Coordonnées en points PDF, origine en haut à gauche (même repère que les zones des fautes).
- Lecteur (`lecteur.html?cours=…&groupe=…&lab=…&etudiant=…`) : pages en défilement continu, canvas créés seulement pour les pages proches de l'écran (mémoire de l'iPad), enregistrement automatique 0,8 s après chaque modification, nouvel essai si le moteur est injoignable.
- Largeurs de trait en points PDF (réglages par défaut 0,6 à 3,8 pt, gomme 6 pt) : le prototype était à 816 px de large, la page est maintenant à l'échelle réelle du PDF. À ajuster dans « Réglages » sur l'iPad.
