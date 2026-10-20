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
8. **iPad** (quand le moteur tourne) : Safari → `http://<IP de l'ordi>:8001` → Partager → « Sur l'écran d'accueil ».

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

## Dépannage

- **« Mise à jour sautée »** : le message dit pourquoi (branche autre que `main`, modifications locales). Le moteur démarre avec la version actuelle; remettre le clone sur `main` propre pour retrouver la mise à jour.

- **« java » introuvable** : après l'installation de Java, les anciennes fenêtres ne le voient pas. Fermer le terminal et en ouvrir un nouveau (ou relancer `demarrer.bat`).
- **Port déjà utilisé** : le moteur le dit et s'arrête. Un autre programme occupe le port (par exemple un autre `server.py` sur 8000). Changer de port : `python -m moteur --port 8002`, ou `MOTEUR_PORT` dans `demarrer.bat`. L'adresse iPad change aussi. Pour LanguageTool, changer `LT_PORT` et définir `LANGUAGETOOL_URL` (ex. `http://localhost:8082`).
- **L'iPad n'atteint pas l'ordi** : vérifier que le réseau de l'ordi est en profil **Privé**, que Python est autorisé dans le pare-feu pour les réseaux privés, et que l'iPad est sur le même Wi-Fi (pas un réseau « invité »). Test depuis l'ordi : ouvrir `http://localhost:8001`.
- **Changement d'IP** : l'adresse de l'ordi peut changer (redémarrage du routeur). Relire l'adresse affichée dans la fenêtre Moteur et ouvrir cette adresse dans Safari. L'icône de l'écran d'accueil garde l'ancienne : la supprimer et la réinstaller. Option : réserver une adresse fixe pour l'ordi dans le routeur.
- **Erreur 503 sur le français** : LanguageTool n'est pas démarré (fenêtre fermée ou en erreur).
- **Données introuvables après changement** : la variable `CORRECTION_DONNEES` n'est lue que par les terminaux ouverts après `setx`.
