# Prototype du crayon

Page autonome (un seul fichier, `index.html`) pour tester sur l'iPad la fluidité du trait et la largeur selon la pression de l'Apple Pencil, à comparer avec OneNote. Jetable : ne fait pas partie de l'app finale.

## Ouvrir sur l'iPad (même Wi-Fi que l'ordi)

Sur l'ordi, dans ce dossier :

    python3 -m http.server 8000

Puis dans Safari sur l'iPad : `http://<adresse-IP-de-l'ordi>:8000` (ex. `http://192.168.1.25:8000`).
Adresse de l'ordi : `ipconfig` (Windows) ou `ifconfig`/Préférences Système (Mac). Optionnel : Partager > Sur l'écran d'accueil pour avoir le plein écran.

Le chargement d'un PDF utilise pdf.js depuis internet (cdnjs) ; la feuille blanche fonctionne sans.

## À tester

- Largeur : réglages Min / Max / Courbe (courbe < 1 = le trait grossit plus vite).
- Doigt = défilement et zoom (pincer) ; Pencil = dessin. La case « Le doigt dessine aussi » sert aux essais à la souris.
- Crayon, surligneur, 5 couleurs, gomme (efface le trait touché), annuler/rétablir par page.
- Ligne d'info en haut : pression reçue, inclinaison, temps de traitement par événement.

Limites connues : gomme par trait entier, pas de double tape du Pencil, pas d'export.
