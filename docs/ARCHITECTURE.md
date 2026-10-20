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
  anonymat.py  masque les noms d'étudiants avant tout envoi à Claude
  francais_filtre.py prose seulement pour le français (segmentation, filtre, lexique)
  francais_claude.py passe Claude sur le français (erreurs subtiles après LanguageTool)
  plagiat.py   comparaison locale de tous les rapports + analyse Claude des paires confirmées
  lot.py       analyse par lot (français + indices d'IA sur plusieurs rapports d'un lab)
  indices_ia.py API /api/indices-ia (analyse de style par Claude, texte pour Pangram)
  annotations.py API /api/annotations (traits du crayon, enregistrés à part du PDF)
  export.py    API /api/export (PDF annoté pour LÉA, créé à la demande)
  polices/     Caveat Bold (OFL), écriture manuscrite des corrections dans le PDF exporté
  __main__.py  commande de lancement
pwa/           app iPad (index.html + app.js : bibliothèque; lecteur.html/js/css : lecteur et annotation; plagiat.html/js/css : plagiat; lot.js : analyse par lot;
               vendor/ : pdf.js, copié dans le dépôt car l'iPad n'a pas forcément Internet)
scripts/       outils à lancer à la main (ex. test de consommation)
prototypes/    essais autonomes (ex. crayon), hors moteur
tests/         tests pytest
donnees/       données locales, exclu du dépôt (.gitignore)
docs/          plan (état et reste à faire), workflow, architecture, liaison Claude
```

## Lancer
```
pip install -e ".[test]"   # une seule fois
python -m moteur           # port 8001; affiche l'adresse à ouvrir sur l'iPad
pytest                     # tests
```
Sur l'iPad (même Wi-Fi) : ouvrir l'adresse affichée dans Safari, puis Partager → « Sur l'écran d'accueil ». Windows : `demarrer.bat` lance tout (guide : `docs/DEMARRAGE.md`). Option `--port` si le port est pris; option `--local` : accès depuis l'ordi seulement. Le dossier de données se change avec la variable `CORRECTION_DONNEES`.

## Ajouter une fonction
1. Créer `moteur/<fonction>.py` avec un `APIRouter` (préfixe `/api/<fonction>`).
2. L'inscrire dans `creer_app()` de `moteur/app.py`, avant le montage de la PWA.
3. Ajouter l'écran dans `pwa/` et un test dans `tests/`.
Les fichiers des étudiants vont seulement sous `donnees/`.

## Correction du français (étape 2, moteur)
- `POST /api/francais/analyser` (PDF en multipart, `points_par_faute`, `plafond`) : texte, fautes avec `zones` (rectangles en points PDF, origine en haut à gauche, par page) et pénalité si toutes acceptées.
- `POST /api/francais/bareme` : pénalité pour un nombre de fautes acceptées.
- LanguageTool : serveur local requis (Java), `java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081`; adresse via `LANGUAGETOOL_URL`. Sans serveur, l'API répond 503.
- `/analyser` est sans état : rien n'est conservé. Pour un rapport rangé : voir « Français sur un rapport rangé » plus bas.

### Filtrage : seulement la prose, avec des mots complets (`moteur/francais_filtre.py`)
- **Segmentation** : chaque ligne du texte extrait est « prose » (au moins 3 mots de 3 lettres ou plus et la moitié des jetons) ou non. Les lignes qui ne sont pas de la prose (calculs, tableaux, légendes courtes), tout ce qui suit un titre « Bibliographie / Références / Sources », et dans une phrase les jetons à chiffre ou symbole (« 3,5 », « mol/L ») passent en `markup` dans le paramètre `data` (annotation) de `/v2/check` : ignoré par LanguageTool mais compté dans les positions, donc les `zones` restent justes. Un nombre se lit « 2 » (`interpretAs`) pour ne pas fausser les accords.
- **Règles désactivées** (`disabledRules`, `disabledCategories`) : espaces et typographie (`COMMA_PARENTHESIS_WHITESPACE`, `FRENCH_WHITESPACE`, catégorie `TYPOGRAPHY`…), nombres en lettres, et quelques règles qui se déclenchent à tort sur les sauts de ligne du PDF. Gardés : grammaire, accords, confusions, mots répétés, orthographe, ponctuation double, tirets. Décision de Guillaume : la typographie ne compte pas.
- **Filtre après coup** (orthographe seulement) : sont retirés les jetons à chiffre ou symbole, de 1 à 3 lettres, les unités courantes, les formules (majuscule interne), sigles, noms propres (majuscule hors début de phrase ou de page) et les mots du lexique. Toute faute sur une ligne ignorée ou de texte vide est aussi retirée.
- **Décalage UTF-16** : LanguageTool compte en UTF-16, Python en points de code; sans conversion, les symboles mathématiques hors du plan de base (𝑥, 𝒎𝑳) décalaient les fautes suivantes et donnaient des fautes au `texte` vide (`languagetool._vers_points`).
- **Lexique global** (décision de Guillaume) : `<données>/lexique.json`, `GET` / `POST` / `DELETE /api/francais/lexique[/<mot>]`. Dans le lecteur, « Ajouter au lexique » (fiche d'une faute d'orthographe) ajoute le mot et refuse la faute.
- **Lecteur, fautes** : sur le PDF, une faute = surlignage du mot (pas de soulignement) + correction manuscrite. Mode « Déplacer la correction » dans la fiche : on glisse la correction au doigt ou à la souris (le crayon et le défilement ne sont pas touchés); « Remettre en place » efface le décalage. Toucher une faute dans le panneau centre le PDF sur elle (`centrerFaute` dans `pwa/francais.js` : position calculée depuis le DOM et le zoom, donc juste même si la page n'est pas rendue; marge de défilement en bas d'une demi-fenêtre).
- **Passe Claude** : les lignes ignorées ne lui sont pas envoyées, ses fautes qui les touchent sont écartées, et sa consigne exclut calculs, valeurs, unités, symboles et abréviations techniques.
- **Mesure** : `python scripts/mesurer_filtrage.py [--exemples N]` ré-analyse les rapports rangés et n'affiche que des comptes par règle, avant et après (sans la passe Claude; exemples à l'écran seulement).

## Limites connues
- Connexion en HTTP sur le réseau local : pas de service worker (réservé au HTTPS), donc pas de mode hors ligne. Le moteur doit être allumé pour corriger, ce qui est déjà le cas (voir PLAN.md).
- Pas d'authentification : à n'utiliser que sur le Wi-Fi maison.

## Bibliothèque (étape 1)
Liste de classe : CSV ou xlsx. CSV lu en UTF-8 (avec ou sans BOM), sinon cp1252; séparateur deviné sur la première ligne (`;`, `,` ou tabulation). Format réel d'Omnivox/LÉA (`ListeEtudiants_cours<N>_gr<N>.csv`) : colonnes « No de DA », « Nom de l'étudiant », « Prénom de l'étudiant », valeurs enrobées `="..."` (enrobage retiré), colonnes de remplissage et lignes vides ignorées. En-têtes de nom reconnus : nom, nom de famille, nom de l'étudiant. Le DA est gardé dans le champ facultatif `da` de chaque étudiant de `classe.json`.
Rangement : `donnees/bibliotheque/<cours>/<groupe>/classe.json` et `.../<lab>/<étudiant>/rapport.pdf`; les PDF à trancher sont dans `_attente/`.
Association (`associer`) : 1) le n° de DA (6 à 9 chiffres) lu dans le nom du fichier LÉA (`nom_2626310_Rapport…pdf`) est comparé au champ `da` des listes de classe; 2) sinon le nom de famille (sans accents ni casse) doit figurer dans le nom du fichier; le nom le plus long l'emporte; le prénom départage les homonymes; 3) en dernier, comparaison sans séparateurs (« BeleGombos » ~ « Bele-Gombos », nom de 4 lettres et plus). Sinon le fichier va « en attente » (`ambigu`, `aucune_correspondance`, `da_inconnu`, `deja_importe`; jamais écrasé sans choix de Guillaume). Les PDF sans texte sont refusés.
Import multi-groupes : `POST /api/bibliotheque/import` (cours, lab, `groupe` facultatif). Sans groupe, la recherche porte sur toutes les listes du cours et chaque PDF va au groupe de son étudiant; la réponse contient `ranges`, `en_attente` (avec la raison), `refuses` et `par_groupe` (nombre rangé par groupe). `POST /attente/{id}` prend `etudiant` et `groupe`; sans étudiant, le fichier est déplacé dans `_ecartes/` (récupérable), jamais supprimé.
Coéquipiers : à l'import, les étudiants du cours dont le nom ET le prénom figurent sur la première page sont enregistrés dans `<lab>/<étudiant>/equipe.json` (le rapport reste rangé une seule fois, au nom du déposant). Ils s'affichent dans la bibliothèque et le récapitulatif; le plagiat ignore les paires d'une même équipe.

## Annotations (étape 1)
- Fichier `.../<lab>/<étudiant>/annotations.json` à côté de `rapport.pdf`; le PDF n'est jamais modifié.
- `GET` / `PUT /api/annotations/<cours>/<groupe>/<lab>/<étudiant>` : `{version: 1, pages: {"1": [trait, …]}}`. Un trait : `outil` (crayon ou surligneur), `couleur` (#rrggbb), `largeur_min`, `largeur_max`, `courbe`, `points` [x, y, pression]. Coordonnées en points PDF, origine en haut à gauche (même repère que les zones des fautes).
- Lecteur (`lecteur.html?cours=…&groupe=…&lab=…&etudiant=…`) : pages en défilement continu, canvas créés seulement pour les pages proches de l'écran (mémoire de l'iPad), enregistrement automatique 0,8 s après chaque modification, nouvel essai si le moteur est injoignable.
- **Barre d'annotation** (`lecteur.html`, 2 lignes fixes en haut) : ligne 1 navigation/export/français/réglages, ligne 2 outils (crayon, surligneur, gomme avec pastille de la couleur de l'outil), 3 épaisseurs, 5 couleurs, annuler/rétablir, bascule crayon/gomme. Cibles de 44 px au moins. Réglage **par outil** (couleur et épaisseur) gardé dans `localStorage` (`reglages-lecteur`, clé lue avec repli sur les valeurs par défaut si l'ancien format est présent); le dernier outil de trait est rouvert, jamais la gomme. Épaisseurs prédéfinies (`EPAISSEURS` dans `lecteur.js`) : crayon = largeur min/max (pression entre les deux), surligneur = largeur fixe. Gomme : « Trait entier » (défaut) ou « Partielle » (coupe le trait). Surligneur : crayon immobile 0,55 s en fin de trait → ligne droite du départ à la position du crayon (le bout suit encore le crayon). Format `annotations.json` inchangé (version 1), donc aucune modification du moteur.
- Largeurs de trait en points PDF (réglages par défaut 0,6 à 3,8 pt, gomme 6 pt) : le prototype était à 816 px de large, la page est maintenant à l'échelle réelle du PDF. À ajuster dans « Réglages » sur l'iPad.

## Indices d'IA (étape 4)
- `POST /api/indices-ia/analyser/{cours}/{groupe}/{lab}/{etudiant}` : Claude (`claude -p`, file partagée, schéma JSON) analyse le style du rapport rangé; résultat gardé dans `indices_ia.json` à côté du PDF. `GET .../resultat/...` le relit, `GET .../texte/...` donne le texte brut.
- Sortie : `force` (faible / moderee / marquee), `resume`, `signaux` (observation + extrait cité, `verifie` = l'extrait est vraiment dans le rapport), `contre_indices`, `avertissement`. Toujours un indice à revérifier, jamais un verdict.
- Écran (`pwa/indices-ia.js`) : bouton « IA » à côté de chaque lab. Bouton Pangram : copie le texte dans le presse-papiers et ouvre pangram.com; Guillaume colle lui-même, aucun envoi automatique.
- Erreurs Claude : 503 (non connecté / introuvable), 429 (limite d'usage), 504 (délai), 502 (autre).

## Français sur un rapport rangé (étape 2)
- `POST /api/francais/rapport/<cours>/<groupe>/<lab>/<étudiant>/analyser` : analyse `rapport.pdf` et enregistre `francais.json` à côté. Une nouvelle analyse garde les décisions des fautes inchangées (même position et même texte).
- `GET` / `PUT` sur le même chemin sans `/analyser` : état (`fautes` avec `zones`, `decisions` {id: acceptee|refusee, absent = à trancher}, `choix` {id: correction écrite, défaut = 1re suggestion}, `masquees` [id] = correction manuscrite effacée, `decalages` {id: [dx, dy]} = correction manuscrite déplacée à la main, en points PDF (absent = position d'origine; repris par l'export et gardé par une nouvelle analyse pour les fautes inchangées), `nb_acceptees`, `penalite`, `bareme`). Le PUT renvoie l'état avec la pénalité recalculée : la formule n'existe que dans le moteur.
- `GET` / `PUT /api/francais/bareme/<cours>` : points par faute et plafond du cours (`<cours>/bareme.json`, vide = aucun plafond).
- Lecteur : bouton « Français » (analyse, résumé, barème, liste des fautes avec ✓/✗); tap sur une faute (double clic à la souris) pour sa fiche : suggestions, accepter/refuser, effacer la correction écrite. Fautes refusées : plus affichées. Correction manuscrite : police Caveat (OFL, `pwa/vendor/`).

- **Passe Claude** (seulement sur le rapport rangé, `/analyser/` sans état reste LanguageTool seul) : après LanguageTool, un appel `claude -p` (file partagée, schéma JSON) reçoit le texte et les extraits déjà signalés, avec les noms d'étudiants masqués (`moteur/anonymat.py` : nom et prénom de l'étudiant du rapport, noms de famille des autres étudiants du groupe d'au moins 4 lettres, remplacés par `[NOM]`; la liste de classe reste locale). La même protection s'applique à l'analyse d'indices d'IA; le plagiat envoie seulement des passages communs sous « rapport A/B » (noms non masqués dans ces passages). Une faute de Claude n'est gardée que si son extrait est dans le texte et ne chevauche aucune autre faute. Elle a le même format (`zones`, décisions, `choix`, `masquees`, barème, export) avec `source: "claude"` (LanguageTool : `"languagetool"`), `regle: "claude"` et sa correction comme unique suggestion.
- Si Claude échoue, le résultat LanguageTool est quand même enregistré; `claude: {ok, erreur: {code, message}, ajoutees}` dans l'état (codes 503 non connecté, 429 limite, 504 délai, 502 autre) et le panneau l'affiche. « Relancer l'analyse » refait la passe.

## Export du PDF annoté (étape 1)
- `GET /api/export/<cours>/<groupe>/<lab>/<étudiant>` : renvoie `<étudiant>_<lab>_annote.pdf`. Rien n'est écrit sur le disque : le rapport reste intact, le PDF annoté est recalculé à chaque demande (reportlab dessine une couche par page, pypdf la fusionne).
- Contenu : surlignages et traits du crayon (même largeur selon la pression qu'à l'écran), et les fautes de français **acceptées** seulement (surlignage rouge, correction manuscrite sauf si effacée). Les fautes refusées ou à trancher n'y sont pas. Le surligneur est en mode « produit » (multiply) : le texte reste lisible dessous.
- Lecteur : bouton « Exporter le PDF » (enregistre d'abord les modifications en attente, puis télécharge).
- Limite : les pages pivotées (`/Rotate`) ne sont pas gérées; les PDF exportés de Word n'en ont pas.

## Plagiat (étape 3)
- **Comparaison locale** (`POST /api/plagiat/comparer`, sans Claude) : chaque rapport de la bibliothèque (tous cours, groupes, labs) est comparé à tous les autres. Mots mis en minuscules, sans accents ni ponctuation; un passage commun = au moins 8 mots consécutifs identiques (`MOTS_MIN`). Score d'une paire = plus grande part d'un des deux rapports couverte par des passages communs. Un même étudiant n'est pas comparé à lui-même d'un lab à l'autre. Une suite de mots présente dans plus de 40 rapports est considérée comme du texte courant et ignorée.
- **Énoncé** : `POST /api/plagiat/enonces/{cours}/{lab}` (PDF), rangé sous `bibliotheque/<cours>/_enonces/<lab>.pdf`. Les mots qu'il couvre sont retirés des rapports (ni comparés ni comptés).
- **Seuil** : `GET/PUT /api/plagiat/reglages` (fraction, 0,2 par défaut). Les paires plus basses restent consultables.
- **Confirmation avant Claude** : `POST /api/plagiat/paires/{cle}/confirmer` est le seul chemin vers Claude. Une paire par appel; seuls les passages communs partent (sous les noms « rapport A/B », sans nom d'étudiant), au plus 12 000 caractères. Verdict : copie, paraphrase ou coïncidence + confiance + explication, présenté comme un indice. `…/ecarter` écarte une paire.
- **Données** sous `donnees/plagiat/` : `paires.json` (dernière comparaison), `decisions.json`, `reglages.json`, `textes/` (cache par empreinte du PDF; une décision suit le contenu des PDF, pas le nom). Un rapport remplacé donne une nouvelle paire, donc une nouvelle décision.
- Limite connue : des partenaires de lab qui partagent légitimement leurs données ressortent comme paires; c'est à Claude (consigne) et à Guillaume de trancher.

## Analyse par lot (Claude)
- Modèle : la file Claude du moteur utilise **Sonnet** par défaut (`claude.file_par_defaut`, variable `CORRECTION_MODELE` pour changer). Mesuré : environ 2 % de la session de 5 h par rapport (français + indices d'IA), donc environ 10 rapports par lot avec une marge de 20 %.
- `POST /api/lot/{cours}/{groupe}/{lab}` (`{n: 10 par défaut, 1 à 200, refaire: false}`) : lance un lot en arrière-plan (un seul à la fois, sinon 409; 409 aussi s'il n'y a rien à analyser). `GET /api/lot` : progression (`statut` en_cours / termine / arrete / limite / erreur, `fait`, `total`, `courant`, `erreurs`, `message`; état en mémoire, perdu au redémarrage du moteur). `POST /api/lot/arreter` : arrêt après le rapport en cours. `GET /api/lot/apercu/{cours}/{groupe}/{lab}?refaire=` : nombre de rapports qui seraient traités.
- Rapport « à analyser » : pas de `francais.json` (ou passe Claude du français en échec) ou pas de `indices_ia.json`; seule la partie manquante est faite. Avec `refaire`, tous les rapports du lab sont repris; les décisions des fautes inchangées sont gardées (comportement de `analyser_rapport`). Sans `refaire`, une analyse existante n'est jamais touchée.
- Arrêt propre : limite d'usage (429) ou Claude non connecté / LanguageTool absent (503) arrête le lot et garde les résultats; le message demande de reprendre après la réinitialisation. Les autres erreurs (504, 502…) sont notées pour le rapport touché et le lot continue.
- Écran : section « Analyse par lot » de la page d'accueil (choix du lab, N, case « Refaire », progression, arrêt, erreurs).

## Statut et archive (navigation)
- `PUT /api/bibliotheque/statut/<cours>/<groupe>/<lab>/<étudiant>` `{termine}` : écrit `statut.json` à côté du rapport. `PUT /api/bibliotheque/archive/<cours>/<groupe>/<lab>` `{archive}` : écrit `archive.json` dans le dossier du lab. Rien n'est déplacé.
- `GET /api/bibliotheque` ajoute `termines` (labs terminés) à chaque étudiant et `labs_archives` à chaque classe. Un lab est « terminé » à l'écran s'il est archivé ou si tous ses rapports sont terminés.
- `GET /api/plagiat/enonces/<cours>/<lab>` renvoie le PDF de l'énoncé (404 s'il n'y en a pas); le même chemin en POST le remplace.
- Écran : arbre `<details>` replié cours → lab (énoncé ici) → groupe → rapports, état ouvert/fermé et filtre gardés dans le `localStorage` de l'appareil.
- Navigation : `index.html` est une seule page à quatre vues (`#accueil`, `#biblio`, `#importer`, `#outils`) commutées par `aller()` dans `app.js` (adresse `/#biblio` possible). Le lecteur garde le dernier rapport ouvert dans le `localStorage` (clé `dernier`) pour « Continuer ».
- Lecteur : `navigation-lecteur.js` lit l'arbre de la bibliothèque, passe d'un rapport à l'autre du même groupe et lab (après avoir enregistré les traits et décisions via `toutEnregistrer()` de `lecteur.js`) et écrit le statut par `PUT /api/bibliotheque/statut/…`.
- Liens entre écrans : `window.choisirLot(cours, groupe, lab)` (`lot.js`) présélectionne le lab de l'analyse par lot; `plagiat.html?cours=…&lab=…` préremplit l'énoncé; `app.js` signale (`rendreEnoncesManquants`) les labs sans énoncé.
