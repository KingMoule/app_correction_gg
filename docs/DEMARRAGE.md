# Démarrage de l'app (Windows + iPad)

Adresses par défaut : moteur sur le port **8001**, LanguageTool sur **8081**.

## À faire une seule fois

1. **Python** et le dépôt cloné. Dans le dossier du dépôt : `pip install -e ".[test]"`.
2. **Java** (pour LanguageTool) : `winget install EclipseAdoptium.Temurin.21.JRE`, puis **ouvrir une nouvelle fenêtre** de terminal (voir Dépannage).
3. **LanguageTool 6.6** : décompresser dans `C:\LanguageTool\LanguageTool-6.6`. Si le dossier est ailleurs, changer `LT_DOSSIER` en haut de `demarrer.bat`.
4. **Données hors OneDrive** (variable utilisateur) :
   ```
   setx CORRECTION_DONNEES C:\correction_donnees
   ```
   Puis ouvrir une nouvelle fenêtre de terminal.
5. **Claude Code** installé et connecté au compte (`claude` doit fonctionner dans un terminal). Voir `docs/CLAUDE_CLI.md`.
6. **Réseau en profil Privé** : Paramètres → Réseau et Internet → Wi-Fi → ton réseau → Profil de réseau → **Privé**.
7. **Pare-feu** : autoriser Python sur les réseaux **privés** (Windows le propose au premier lancement : cocher « Réseaux privés »). Sinon : Pare-feu Windows Defender → Autoriser une application → Python → colonne « Privé ».
8. **Code d'accès** : au **premier lancement** de `demarrer.bat`, la fenêtre Moteur demande de choisir un code (8 caractères au moins, rien ne s'affiche; le saisir deux fois). Il est gardé haché dans le dossier de données. Choisis-en un que tu n'utilises nulle part ailleurs.
9. **iPad** (quand le moteur tourne) : Safari → `http://<IP de l'ordi>:8001` → saisir le code → Partager → « Sur l'écran d'accueil », puis **ouvrir l'app installée et ressaisir le code** (elle a ses propres cookies, distincts de Safari). Le code est ensuite retenu un an.

## À chaque séance

**Ordi** : double-cliquer sur `demarrer.bat` (à la racine du dépôt). Avant le lancement, il met le dépôt à jour (voir ci-dessous). Deux fenêtres s'ouvrent : **LanguageTool** et **Moteur**. Les laisser ouvertes pendant la correction. Le moteur affiche l'adresse à utiliser sur l'iPad.

**iPad** : même Wi-Fi que l'ordi, ouvrir l'app installée (ou Safari → l'adresse affichée).

**Fin** : fermer les deux fenêtres.

**Mise à jour automatique** : au démarrage, `demarrer.bat` fait `git pull --ff-only` seulement si le dépôt est sur `main` sans modification locale. Sinon (autre branche, fichiers modifiés, pas d'Internet, erreur git), il l'écrit et démarre quand même avec la version actuelle; il ne fait jamais de reset ni de stash. Si `pyproject.toml` a changé, il relance `python -m pip install -e .`. Il affiche la version obtenue (`git log -1 --oneline`). Comme `demarrer.bat` fait partie du dépôt, il se copie dans `%TEMP%\demarrer_copie.bat` et exécute la copie (cmd lit un .bat par décalage : un `git pull` qui le modifierait en cours de route fausserait la suite). Pour l'essayer sans lancer Java ni le moteur : `set DEMARRER_ESSAI=1`.

Sans `demarrer.bat`, à la main (deux terminaux) :
```
cd C:\LanguageTool\LanguageTool-6.6
java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
```
```
python -m moteur --port 8001
```

## Code d'accès

- **Qui l'exige** : tout appareil sauf l'ordi lancé en `--local` (`python -m moteur --local` : pas de code, ordi seulement). L'écran de saisie apparaît par-dessus l'écran en cours et **les modifications en attente sont conservées** (décisions de français, traits) : saisis le code, elles sont envoyées.
- **Changer le code** (fermer d'abord la fenêtre Moteur, ou non : c'est pris en compte tout de suite) :
  ```
  python -m moteur.acces nouveau-code
  ```
  Tous les appareils sont déconnectés et doivent ressaisir le nouveau code. Même commande si tu as **oublié le code**.
- **Se déconnecter** : bouton « Se déconnecter » dans la barre de l'accueil (cet appareil seulement).
- **Trop d'essais** : après 4 mauvais codes, attente de 30 s, qui double à chaque nouvel échec (15 min au plus). Redémarrer le moteur remet les compteurs à zéro.
- **Hôtes permis** : `localhost`, toute adresse IP et le nom de l'ordi. Pour un autre nom (ex. `monordi.local`) : variable `CORRECTION_HOTES` (séparés par des virgules).
- **Limite** : en HTTP, le cookie circule en clair sur le Wi-Fi. Le code protège contre les appareils qui n'ont pas le code (invités, objets connectés) et contre les sites web malveillants, pas contre quelqu'un qui écoute le réseau.

## Sauvegarde et restauration

**Automatique** : à chaque lancement, `demarrer.bat` crée (avant de démarrer le moteur, donc sans fichier à moitié écrit) une archive `sauvegarde_AAAAMMJJ-HHMMSS.zip` de tout le dossier de données, sauf `plagiat/textes/` (cache recalculé tout seul). Les PDF d'origine, annotations, décisions, résultats Claude, lexique et barèmes y sont. Il affiche « Dernière sauvegarde : … ». Si la sauvegarde échoue (dossier inaccessible), il l'écrit en clair et démarre quand même.

**Où** : `C:\correction_donnees_sauvegardes` par défaut (à côté des données, hors OneDrive). Pour protéger d'une panne du disque, pointer vers un autre disque ou une clé USB :
```
setx CORRECTION_SAUVEGARDES D:\correction_sauvegardes
```
(puis nouvelle fenêtre de terminal). Aucune copie dans un nuage : décision à prendre par Guillaume selon les règles du collège.

**Combien** : les 10 dernières archives, plus la plus récente de chacune des 8 dernières semaines. La rotation ne supprime que d'anciennes `sauvegarde_*.zip` du dossier de sauvegardes, jamais rien dans les données.

**À la main** (dans le dossier du dépôt) :
```
python -m moteur.sauvegarde sauvegarder
python -m moteur.sauvegarde lister
```

**Restaurer** (fermer d'abord la fenêtre Moteur) :
```
python -m moteur.sauvegarde restaurer
```
Remet la plus récente archive dans le dossier de données. S'il n'est pas vide, la commande demande confirmation, puis le **renomme** en `correction_donnees_avant_restauration_<date>` (rien n'est supprimé). Pour une autre archive : `restaurer <chemin du zip>`. Pour inspecter sans toucher aux données : `restaurer --cible C:\essai_restauration`. `--oui` saute la question.

## Rangement par session (migration au premier lancement après la mise à jour)

Les cours sont maintenant rangés **par session** (`A2026` = automne 2026, `H2027` = hiver 2027) : le code de cours et le n° de groupe d'Omnivox reviennent d'une session à l'autre, et sans la session les listes, les labs, les notes et les coéquipiers se mélangeraient.

**Au prochain lancement de `demarrer.bat`** (premier lancement après la mise à jour, `git pull` automatique) :
1. la sauvegarde habituelle se fait, puis le moteur en fait **une deuxième, juste avant la migration** (message « Rangement par session… Sauvegarde : … ») : si elle échoue, rien n'est touché et le moteur ne démarre pas;
2. chaque ancien dossier de cours est **renommé** (`bibliotheque\202SNURE` devient `bibliotheque\202SNURE_A2026`) : un renommage, aucun fichier copié, déplacé ni supprimé; `_enonces`, le barème et le style des références suivent le cours; `_attente`, `_ecartes` (nom du cours corrigé dans leurs fiches) et `_remplaces` (dossiers renommés `<cours>_A2026_<groupe>_…`) restent dans leur dossier, rien n'est supprimé; le lexique est global et ne change pas;
3. les fichiers qui citent l'ancien nom (listes de classe, fichiers en attente, « Reprendre », états d'export, comparaisons de plagiat) sont corrigés; les décisions de plagiat sont gardées;
4. le nombre de fichiers, de rapports et leur taille totale sont comparés avant et après : un écart arrête le lancement avec la marche à suivre. Un journal est écrit dans `<données>\migrations\`.
Toutes les données existantes vont dans la session **A2026** (changer : variable `CORRECTION_SESSION_MIGRATION`, ou `python -m moteur.migration_session --session H2026`). Les lancements suivants ne font rien (la migration est idempotente). Pour voir ce qui serait renommé sans rien changer : `python -m moteur.migration_session --a-sec`.

**Revenir en arrière** : fermer la fenêtre Moteur, `python -m moteur.sauvegarde lister`, puis `python -m moteur.sauvegarde restaurer <archive d'avant>` (la sauvegarde d'avant la migration porte l'heure du message). Le dossier actuel est renommé `…_avant_restauration_<date>`, jamais supprimé. Attention : le lancement suivant refera la migration; pour rester sur l'ancien rangement, revenir aussi à l'ancienne version du programme (`git checkout` du commit d'avant la PR). La rotation garde les 10 dernières archives : ne pas relancer dix fois avant d'avoir vérifié.

**Au quotidien** : l'import d'une liste de classe demande la session (proposée d'après la date : août à décembre = A, janvier à juillet = H; modifiable, ou « session en cours » dans Labs). L'accueil et Labs montrent la session en cours; les autres sont dans « Sessions passées » (Labs), et la recherche et le plagiat couvrent toutes les sessions.

## Dépannage

- **« Mise à jour sautée »** : le message dit pourquoi (branche autre que `main`, modifications locales). Le moteur démarre avec la version actuelle; remettre le clone sur `main` propre pour retrouver la mise à jour.

- **« java » introuvable** : après l'installation de Java, les anciennes fenêtres ne le voient pas. Fermer le terminal et en ouvrir un nouveau (ou relancer `demarrer.bat`).
- **Port déjà utilisé** : le moteur le dit et s'arrête. Un autre programme occupe le port (par exemple un autre `server.py` sur 8000). Changer de port : `python -m moteur --port 8002`, ou `MOTEUR_PORT` dans `demarrer.bat`. L'adresse iPad change aussi. Pour LanguageTool, changer `LT_PORT` et définir `LANGUAGETOOL_URL` (ex. `http://localhost:8082`).
- **L'iPad n'atteint pas l'ordi** : vérifier que le réseau de l'ordi est en profil **Privé**, que Python est autorisé dans le pare-feu pour les réseaux privés, et que l'iPad est sur le même Wi-Fi (pas un réseau « invité »). Test depuis l'ordi : ouvrir `http://localhost:8001`.
- **Changement d'IP** : l'adresse de l'ordi peut changer (redémarrage du routeur). Relire l'adresse affichée dans la fenêtre Moteur et ouvrir cette adresse dans Safari. L'icône de l'écran d'accueil garde l'ancienne : la supprimer et la réinstaller. Option : réserver une adresse fixe pour l'ordi dans le routeur.
- **« Aucun code d'accès n'est défini »** : lancer `python -m moteur.acces nouveau-code`.
- **L'iPad affiche l'écran du code à chaque fois** : cookies bloqués ou site ouvert sous deux adresses (l'IP a changé : voir « Changement d'IP »).
- **Erreur 503 sur le français** : LanguageTool n'est pas démarré (fenêtre fermée ou en erreur).
- **Données introuvables après changement** : la variable `CORRECTION_DONNEES` n'est lue que par les terminaux ouverts après `setx`.
