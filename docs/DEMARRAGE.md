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

**Ordi** : double-cliquer sur `demarrer.bat` (à la racine du dépôt). Deux fenêtres s'ouvrent : **LanguageTool** et **Moteur**. Les laisser ouvertes pendant la correction. Le moteur affiche l'adresse à utiliser sur l'iPad.

**iPad** : même Wi-Fi que l'ordi, ouvrir l'app installée (ou Safari → l'adresse affichée).

**Fin** : fermer les deux fenêtres.

Sans `demarrer.bat`, à la main (deux terminaux) :
```
cd C:\LanguageTool\LanguageTool-6.6
java -cp languagetool-server.jar org.languagetool.server.HTTPServer --port 8081
```
```
python -m moteur --port 8001
```

## Dépannage

- **« java » introuvable** : après l'installation de Java, les anciennes fenêtres ne le voient pas. Fermer le terminal et en ouvrir un nouveau (ou relancer `demarrer.bat`).
- **Port déjà utilisé** : le moteur le dit et s'arrête. Un autre programme occupe le port (par exemple un autre `server.py` sur 8000). Changer de port : `python -m moteur --port 8002`, ou `MOTEUR_PORT` dans `demarrer.bat`. L'adresse iPad change aussi. Pour LanguageTool, changer `LT_PORT` et définir `LANGUAGETOOL_URL` (ex. `http://localhost:8082`).
- **L'iPad n'atteint pas l'ordi** : vérifier que le réseau de l'ordi est en profil **Privé**, que Python est autorisé dans le pare-feu pour les réseaux privés, et que l'iPad est sur le même Wi-Fi (pas un réseau « invité »). Test depuis l'ordi : ouvrir `http://localhost:8001`.
- **Changement d'IP** : l'adresse de l'ordi peut changer (redémarrage du routeur). Relire l'adresse affichée dans la fenêtre Moteur et ouvrir cette adresse dans Safari. L'icône de l'écran d'accueil garde l'ancienne : la supprimer et la réinstaller. Option : réserver une adresse fixe pour l'ordi dans le routeur.
- **Erreur 503 sur le français** : LanguageTool n'est pas démarré (fenêtre fermée ou en erreur).
- **Données introuvables après changement** : la variable `CORRECTION_DONNEES` n'est lue que par les terminaux ouverts après `setx`.
