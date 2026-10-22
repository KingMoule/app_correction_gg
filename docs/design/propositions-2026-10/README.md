# Propositions de design, octobre 2026 : 3 directions

Guillaume trouve l'app encore peu professionnelle (par exemple, des boutons gris avec seulement du texte). Ce dossier propose 3 directions visuelles nettement différentes pour toute l'app. **Aucun code de l'app n'est touché** : la direction choisie sera implémentée dans un fil suivant.

- **Comparaison côte à côte** : [`comparaison.html`](comparaison.html) (aussi publiée comme Artifact privé, lisible sur l'iPad). Images dans `img/` (WebP), app actuelle dans `avant/`.
- **Maquettes** (HTML statique, données **fictives** seulement) : [`a-atelier.html`](a-atelier.html), [`b-ipad.html`](b-ipad.html), [`c-classe.html`](c-classe.html). Chaque fichier contient 9 écrans : accueil et bibliothèque, import, tableau de suivi, lecteur (paysage 1180 × 820), lecteur en portrait (820 × 1180), plagiat, export pour LÉA, code d'accès, états et retours. Un écran seul s'ouvre avec `#seul-<id>` (ex. `a-atelier.html#seul-lecteur`).
- Les maquettes chargent leurs polices depuis Google Fonts pour l'aperçu ; à l'implémentation, polices et icônes seront embarquées dans `pwa/vendor/` (hors ligne), avec leur licence.

## Démarche

1. **Constats** sur l'app actuelle, capturée le 2026-10-21 sur une bibliothèque fictive (moteur en `--local`, dossier temporaire, serveur arrêté ensuite).
2. **Recherche** par 3 sous-agents, refaite une 2e fois plus à fond : systèmes de design, galeries et apps reconnues, outils comparables. Principes repris, rien de copié.
3. **3 directions**, 9 écrans chacune, avec un raisonnement écrit.
4. **Critique indépendante** de chaque direction par un agent qui n'avait vu que les maquettes et ce raisonnement ; améliorations appliquées ou écartées avec la raison (voir plus bas).
5. **Vérifications** : contraste WCAG AA de chaque paire texte/fond (script, 71 paires, 0 échec) et cibles tactiles (script dans Chrome : aucun bouton ni lien sous 44 px dans les 3 maquettes).

## Constats sur l'app actuelle

1. **Navigation et actions en texte gris** : onglets du haut et boutons du lecteur (« Ajuster », « Exporter le PDF », « Français », « Réglages ») sont des rectangles de même poids. Rien ne dit ce qui est principal.
2. **Accueil et bibliothèque vides** : deux tiers de l'écran inutilisés ; l'arbre ne montre ni progression ni ce qui attend.
3. **Formulaires du navigateur** (import, plagiat) : « Choisir un fichier » natif, pas de zone de dépôt ni de résultat par fichier.
4. **Tableau de suivi** : quand un rapport a plusieurs paires de plagiat, la colonne liste tous les noms et la ligne devient très haute.
5. **Lecteur** : 2 lignes de boutons texte puis une ligne d'outils avant le PDF ; panneau des fautes sans fiche ni regroupement.

## Ce que dit la recherche

- **Un seul bouton plein par zone**, à droite ; secondaire blanc bordé ou teinté ; tertiaire en texte. Contre l'effet « bouton gris » : fond blanc bordé + ombre légère, ou fond teinté, avec icône + libellé (Refactoring UI, Carbon, Primer, Atlassian, HIG).
- **Pas de survol sur iPad** : libellé visible partout, sauf crayon, gomme, annuler, rétablir, partager (NN/g, HIG).
- **Barre du lecteur en 3 groupes** : navigation, outils, action principale « Terminé » à droite ; 2e toucher sur l'outil actif = réglages (HIG, GoodNotes, Notability, PDF Expert, Annotation d'Apple).
- **Panneau des fautes à la Antidote** : fiche en haut, catégories avec compteurs, faute traitée grisée mais visible, passage automatique à la suivante avec Annuler.
- **Enchaînement des copies à la Gradescope** : « 6 / 24 », précédent, suivant, « Terminé et suivant ».
- **Plagiat et IA à la Turnitin** : niveau en mots, jamais un verdict ; passages appariés et numérotés.
- **Retours** : toast bref avec Annuler, bannière persistante pour ce qui exige une action, progression chiffrée.
- **Licences vérifiées** : Lucide (ISC), Tabler, Phosphor, Heroicons (MIT), Material Symbols (Apache 2.0) ; polices Inter, Figtree, Fraunces, Caveat (OFL). **SF Symbols exclu** (réservé aux apps pour produits Apple). Les maquettes dessinent toutes leurs pictogrammes d'après la géométrie de Lucide ; le jeu cible de chaque direction est embarqué à l'implémentation.

## Règles communes aux 3 directions

- Le rouge ne dit que **faute** (et erreur bloquante). Plagiat en bleu-vert, indice d'IA en violet avec une icône de loupe, Claude (l'outil) avec des étincelles : on ne confond plus « analysé par Claude » et « écrit par une IA ».
- Sur le PDF : faute **à trancher** = surlignage + correction manuscrite pâle ; **acceptée** = correction pleine ; **refusée** = plus aucune marque (comme dans l'app).
- « **Terminé…** » ouvre la saisie de la note (reportée dans le CSV pour LÉA) avec « Terminer et ouvrir le suivant ».
- Les 5 couleurs d'annotation et le rouge des fautes ne changent pas ; le PDF reste au centre ; cibles d'au moins 44 px.

## Direction A — « Atelier » (outil pro sobre, façon Linear / Notion)

1. **Barre latérale claire de 248 px** : Accueil, Bibliothèque, Importer, Analyse par lot (avec sa progression), Plagiat, Export LÉA, puis les labs en cours ; réglages et « Ordi connecté » en pied. Elle disparaît dans le lecteur.
2. **Neutres froids + un seul accent** (indigo dans les maquettes ; la sarcelle de Guillaume s'y substitue d'un jeton, voir la comparaison). L'accent ne sert qu'à l'action principale, à la sélection et à l'outil actif ; avatars et labs restent neutres.
3. **Inter** (OFL) en 15 px, minimum 13 px, titres en 600, chiffres tabulaires.
4. **Boutons** : primaire plein, secondaire blanc bordé avec ombre fine ; le style discret est réservé aux icônes de barre.
5. **Suivi en tableau dense** (lignes de 52 px), filtres segmentés avec compteurs, colonne Note, un menu « … » par ligne au lieu de 4 boutons ; action principale « Corriger le suivant ».
6. **Pastilles d'état** point + mot sur fond pâle.
7. **Lecteur** : une seule ligne en haut (retour, étudiant, « Enregistré », ‹ 6 / 24 ›, « Terminé… ») ; **rail d'outils vertical à gauche** ; **inspecteur de 320 px** à onglets Français / Indice IA / Plagiat ; page à 700 px.
8. **Fiche de la faute** en tête de l'inspecteur, liste par catégories en dessous ; toast « Faute acceptée · Annuler ».
9. **Portrait** : rail à gauche, feuille Français sous le PDF à 3 hauteurs.
10. **Icônes** : Lucide (ISC), trait de 1,75 px.

## Direction B — « Natif iPad » (comme si Apple l'avait faite)

1. **Barre d'onglets flottante en haut** (iPadOS 18), navigation seulement : Accueil, Bibliothèque, Plagiat, Réglages ; « + Importer » dans la barre de la bibliothèque.
2. **Grands titres** (34 px), police système (SF Pro sur l'iPad), corps 17 px.
3. **Listes groupées en encarts**, tuiles d'icône grises comme dans Réglages.
4. **Capsules = boutons seulement** (plein bleu `#0062d1`, teinté) ; **états = point + texte coloré**, sans fond, avec des rôles fixes (orange à trancher, vert fait, indigo en cours, violet IA, bleu-vert plagiat).
5. **Import et export en feuilles modales** ; confirmation avant Claude en **alerte** iPadOS ; note en **popover** sur « Terminer… ».
6. **Suivi en vue liste façon Fichiers**, colonnes triables (avec Note), **balayage** d'une ligne pour Analyser ou Terminer.
7. **Lecteur plein écran** : barre de navigation (Lab 4, nom, ‹ 6 sur 24 ›, Français, Partager, « … », « Terminer… ») ; **palette de stylos flottante en bas** ; épaisseurs en popover au 2e toucher.
8. **Inspecteur Français** : résumé chiffré, fiche avec ‹ ›, autres fautes, section « Indices » ; bannière « Acceptée · Annuler ».
9. **Portrait** : feuille du bas à poignée (crans bas, moyen, grand) ; palette complète au-dessus.
10. **Icônes** : Phosphor (MIT) à l'implémentation, le plus proche de SF Symbols.
11. **Limites d'une PWA** : barres de Safari si l'app n'est pas installée, flou d'arrière-plan coûteux sur le PDF (fonds opaques au lecteur), partage par `navigator.share`, pas de vibration ; l'allure iOS est étrange sur le PC de Windows.

## Direction C — « Salle des profs » (chaleureux et affirmé, en cartes)

1. **Rail de navigation foncé de 92 px** (sapin profond), icône + libellé toujours visibles : Accueil, Bibliothèque, Importer, Plagiat, Réglages ; « Ordi connecté » écrit en pied. Lot et export passent par le suivi d'un lab.
2. **Palette** : papier crème, cartes blanc cassé, sapin (l'accent de Guillaume) pour les actions et la sélection ; **une seule table d'états** (neutre, sapin clair, sapin plein ✓, ambre, prune, bleu ciel, rouge).
3. **Fraunces** (OFL) pour les titres seulement, **Figtree** (OFL) pour le texte et les chiffres.
4. **Boutons plats** (rayon 12, 48 px), secondaire bordé de 1,5 px ; cartes rayon 16.
5. **Accueil** : carte « Reprendre » en sapin plein, bloc « À faire », cartes de lab avec un liseré de couleur par cours, bibliothèque.
6. **Suivi en colonnes compactes** À corriger / En cours / Terminés (elles se remplissent seules, pas de glisser-déposer), bascule en tableau.
7. **Lecteur** : barre haute avec l'étudiant, « Enregistré », ‹ 6 sur 24 › ; **palette en carte flottante à gauche avec libellés**, Annuler et Rétablir ; à droite, cartes : résumé Français, fiche (annonce la faute suivante), catégories, indice d'IA.
8. **Portrait** : palette en bandeau flottant, cartes en bas.
9. **Plagiat** : passages en bleu numérotés et appariés ; « Un indice, pas un verdict ».
10. **Export en 3 étapes** (vérifier, préparer le ZIP avec progression, déposer dans LÉA).
11. **Icônes** : Tabler (MIT), trait de 2 px, souvent dans une tuile.

## Critiques et améliorations

Le détail (ce qui a été appliqué, ce qui a été écarté et pourquoi) est dans [`comparaison.html`](comparaison.html), section « Critiques indépendantes ». Écartés communs aux 3 : changer une des 5 couleurs d'annotation (contrainte de Guillaume ; l'orange tient 3:1 pour un trait) et changer la couleur de départ du crayon (choix de Guillaume, à poser à l'implémentation).
