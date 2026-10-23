# Critique indépendante : Accueil et Bibliothèque (P1, P2, P3)

## 0. Ce que les captures montrent déjà (et qu'aucune proposition ne corrige en entier)

1. **Quatre sens de « corrigé » pour un même lab** (lab-2 NYA-A26) : « 34 / 80 » (terminés), « Groupe 01 · 20 à corriger » (= non terminés), « À corriger 10 » dans le suivi (= pas commencés), « 49 rapports corrigés » dans l'export (= analysés, fautes toutes tranchées, terminés ou non : `export_lot.py`). C'est la vraie raison pour laquelle « l'information ne parle pas ». Il faut un vocabulaire fixe, **Reçus / Analysés / Terminés / Exporté**, partout le même.
2. **Les mêmes labs apparaissent deux fois** sur l'accueil : la liste « Labs en cours » de la barre latérale et le tableau « Labs » montrent les 4 mêmes lignes avec les mêmes chiffres.
3. **Deux portes par lab** (« Suivi » et le chevron vers la bibliothèque) mènent à deux vues des mêmes rapports. La liste par étudiant de la bibliothèque (12 boutons « Annoter » identiques, sans état ni note) n'est qu'un suivi appauvri.
4. Le bloc du lab dans la bibliothèque a **deux boutons pleins** (« Suivi du lab », « Préparer Travaux.zip »), ce que la règle 4 de DESIGN.md interdit. L'interrupteur « Inclure les inachevés » est **activé par défaut** (`export-lea.js`) alors que PLAN.md dit « exclus sauf case ».
5. « À faire » mêle les exceptions et le travail normal : « 90 fautes à trancher · 18 rapports », ce sont simplement 18 rapports en cours, déjà comptés dans la progression.
6. **Session : un risque pour les données, pas seulement d'affichage.** `MOTIF_LISTE` (`bibliotheque.py`) n'accepte que `[A-Za-z0-9]+` : « NYA-A26 » ne peut pas venir d'un vrai fichier Omnivox. Si le vrai code ne contient pas la session, à l'automne 2027 la liste du gr. 01 **sera fusionnée** avec celle de 2026 (anciens étudiants « retirés ») et le nouveau « lab-2 » tombera dans le dossier de l'ancien, drapeau « archivé » compris. À vérifier sur un vrai nom de fichier avant de dessiner.
7. Les rapports **non remis** sont invisibles : le total d'un lab compte les rapports reçus, pas les inscrits, alors que le moteur connaît l'état « Non remis » (`export_lot.py`). Un lab peut passer « terminé » alors qu'il manque 3 rapports.

## 1. P1 « Le lab au centre »

**Points forts**
- Bonne unité : le lab, tous groupes confondus, sert à corriger, analyser et exporter. Le lecteur revient déjà au suivi (`navigation-lecteur.js`), l'écran que Guillaume apprécie : P1 en fait le pivot au lieu d'en créer un nouveau.
- Fin des deux entrées sans contexte : « Analyse par lot » (menu de 26 choix) et « Export LÉA » (qui ouvre la bibliothèque).
- La moins coûteuse : suivi et export existent; seul le lot par lab touche le moteur.
- Le lot en cours dans la barre (« Lot · lab-3 · 4 / 7 ») est une bonne idée.

**Points faibles**
- **Le cycle linéaire ne correspond pas à la pratique.** À 6-7 rapports par lot, un lab de 83 rapports demande environ 12 lots répartis sur plusieurs fenêtres de 5 h. L'analyse et la correction se chevauchent donc pendant des jours. Avec un seul bouton pour « la prochaine étape », l'accueil proposera « Lancer un lot » quand Guillaume veut corriger, ou l'inverse. La revue du plagiat porte sur toute la bibliothèque, pas sur un lab, et l'export se fait parfois groupe par groupe.
- Une carte par lab : 2-3 cours × 2-3 labs ouverts donnent 4 à 8 cartes d'environ 140 px, donc du défilement en paysage (820 px de haut). Le tableau dense actuel se lit plus vite.
- La redondance demeure : les labs restent dans la barre (« Labs en cours »), dans les cartes et dans la page Labs.
- « Regroupés par session » suppose une session qui n'existe pas dans les données : c'est un prérequis caché.
- Pas de recherche ni de vue par étudiant : rien pour une réclamation de note, pour « Zoé a-t-elle remis le lab 3 ? » ou pour suivre les coéquipiers d'un lab à l'autre.
- L'en-tête de la page du lab cumule 4 onglets, « Clore », « Corriger le suivant » et le sélecteur de groupe : c'est trop pour 820 px en portrait.

**Améliorations, de la plus à la moins importante**
1. Remplacer « une seule étape suivante » par **deux actions fixes par lab** : « Corriger le suivant » en bouton plein, présent tant qu'il reste un rapport analysé non terminé, et une action Claude secondaire (« Analyser 7 · ≈ 21 % » ou « après 17 h 40 »). L'export ne s'affiche que s'il est prêt ou périmé. La barre d'étapes devient une ligne d'état : « Reçus 80 · Analysés 67 · Terminés 34 · Export : jamais ».
2. Présenter l'accueil en **tableau dense** (une ligne de 52 à 64 px par lab, colonnes Analysés / Terminés / Export / action) plutôt qu'en cartes, et retirer « Labs en cours » de la barre.
3. Ajouter une **recherche** par nom ou DA en tête de la page Labs. L'arbre chargé contient déjà tous les étudiants : aucun travail côté moteur.
4. Faire un lot par lab qui **analyse dans l'ordre de correction** (d'abord les prochains « Corriger le suivant ») et qui mémorise où il en est.
5. Page du lab à 3 onglets (Rapports, Claude, Export); l'énoncé passe dans un bandeau du lab et se demande à l'import.
6. « Équipe… » dans le menu « … » du suivi et du lecteur : l'équipe ne se modifie aujourd'hui que dans la bibliothèque (`app.js`), que P1 supprime.

## 2. P2 « Le carnet de la session »

**Points forts**
- C'est la seule proposition qui traite la **session** comme une donnée, et le point 0.6 montre que c'est nécessaire.
- La recherche et la fiche d'étudiant répondent aux questions centrées sur un étudiant : courriel, réclamation, rapport remplacé ou écarté.
- La grille montre les **non remis** et les notes, comme Omnivox et LÉA.

**Points faibles**
- **L'accueil est organisé par groupe**, alors que la correction, le lot et l'export se font par lab. Le lab-2 de NYA apparaît dans 3 cartes; 7 groupes × 5 labs font 35 pastilles; et il n'y a pas de chemin direct vers « Corriger le suivant ».
- La grille ne peut pas respecter « jamais la couleur seule » : une case d'environ 90 px (et 44 px de haut au moins) ne porte pas à la fois un mot d'état, une note et des marques IA/plagiat avec leur mot. Les « petites marques » deviennent des icônes seules. Et avec 3 groupes de 28, un cours fait 84 lignes : le carnet défile autant que le suivi.
- Les actions du lab sont cachées dans un **menu d'en-tête de colonne** : peu visibles, 4 à 5 touches pour lancer un lot ou exporter.
- Le **sélecteur de session global est un mode** : réglé sur H26 pour une réclamation, il donne le lendemain un accueil vide. Contradiction aussi : « tout l'écran est filtré », mais D = 3 suppose une recherche qui ignore le filtre.
- Une troisième vue des rapports (carnet, suivi, lecteur) : vers laquelle le lecteur revient-il ?

**Améliorations, de la plus à la moins importante**
1. Mettre le lab au centre de l'accueil et garder la grille **seulement dans la Bibliothèque**, comme vue d'un cours.
2. **Déduire** la session (date d'import de la liste → A/H/É + année) et ne la faire confirmer qu'en cas de doute. Pas de mode global : la session courante par défaut, les sessions passées en sections repliées, et une recherche qui couvre toujours toutes les sessions en indiquant la session de chaque résultat.
3. Une case = un seul mot ou nombre (« 16,0 », « en cours », « à corriger », « non remis »). L'IA, le plagiat et les références restent dans le suivi.
4. En-tête de colonne = lien direct vers la page du lab (1 touche), pas un menu.
5. Garder la fiche d'étudiant telle quelle, accessible depuis la recherche et depuis le nom dans le suivi.

## 3. P3 « Aujourd'hui »

**Points forts**
- Le moins de touches pour le travail courant, et la plus robuste en portrait : tout est sur l'accueil, rien n'est caché dans le tiroir.
- La **rubrique Claude** dit quand relancer (« possible après 17 h 40 ») : c'est la contrainte la plus pénible au quotidien, et la seule proposition qui la traite.
- Énoncé manquant, export périmé, lab à clore : les vraies exceptions sont bien regroupées.
- La bibliothèque est aplatie (recherche + une ligne par lab) : fini l'arbre à 4 niveaux.

**Points faibles**
- **L'ordre calculé est une boîte noire.** Avec 3 cours, la file compte 15 à 25 lignes; si l'ordre change d'un soir à l'autre, Guillaume ne retrouve plus rien. « Corriger 46 restants » n'est pas une tâche mais le travail lui-même : mêlé aux exceptions, il les noie.
- « Plus tard » ajoute un état caché (stocké où, sur quel appareil ?) et peut faire oublier un export périmé déjà déposé dans LÉA.
- Plus de vue d'ensemble des labs. Si la ligne « Corriger » ouvre le rapport suivant, comment ouvre-t-on le suivi du lab ?
- Lot et export lancés depuis l'accueil : leurs options (groupe, inachevés, CSV, refaire) doivent tenir dans une feuille.

**Améliorations, de la plus à la moins importante**
1. **Rubriques fixes dans un ordre fixe**, sans score : Bloquant, Corriger (une ligne stable par lab, triée par cours), Claude, Revoir, Clore. Une rubrique vide disparaît, les autres ne bougent pas.
2. La ligne « Corriger » a deux cibles : le bouton fait « Corriger le suivant », la ligne ouvre le suivi du lab.
3. Retirer « Plus tard », ou le limiter à Revoir, jamais sur Bloquant ni sur un export périmé.
4. Taille du lot calculée d'après la marge restante, pas un « 7 » fixe : la capture du lot affiche « 10 rapports ≈ 11 % » (non calibré) contre 3 % par rapport dans PLAN.md; le libellé doit reprendre l'estimation du moteur.
5. Mettre la recherche aussi sur l'accueil ou dans la barre.

## 4. Le tableau des touchers

**Chiffres optimistes ou faux**
- **B, P1 = 1** : seulement si l'étape calculée est « Corriger »; sinon 2.
- **C, P3 « 2 (recherche) »** : la recherche est dans la Bibliothèque, donc Bibliothèque + champ + résultat = 3. **P2 « 2 (grille) »** : Carnet + onglet du bon cours + case = 3 dès qu'on n'est pas déjà sur le bon cours, plus le défilement de 84 lignes. **P2 « 2 (recherche) »** : 3 si l'étudiant a plusieurs labs et que le résultat ouvre sa fiche.
- **D, P2 = 3** : seulement si la recherche ignore le filtre de session, ce que la proposition ne dit pas.
- **E, Actuel = 9** : compte 3 lots de groupe, alors qu'un seul lot tourne à la fois et que chacun serait plafonné à 6-7 rapports. Un lot de 7 coûte aujourd'hui 4 touches plus une saisie (barre, menu, choix parmi 26, Lancer). **P3 = 1** contredit sa feuille de confirmation : 2. **P2 = 3** : plutôt 4 à 5 (Carnet, onglet, menu de colonne, Analyser, Lancer). Le vrai coût est le nombre de lots (environ 12 pour lab-3), qu'aucune proposition ne réduit.
- **F, P2 = 3** : plutôt 5 (Carnet, menu, Exporter, Préparer, Télécharger). Il faudrait aussi mesurer F et l'import **sur le PC**, où ces tâches se font.
- **G, Actuel = 5** : le chevron du tableau de l'accueil ouvre directement le bloc Énoncé, donc c'est 3, et l'écart avec les propositions est plus faible qu'annoncé. **P3 = 1** est impossible : toucher la tâche puis choisir le fichier, c'est au moins 2.
- **H** : les comptes s'arrêtent avant la modification elle-même (1 à 2 touches de plus).
- **I** est rare (un lab se termine seul quand tous ses rapports le sont) : il pèse peu dans le choix.
- **Portrait** : toute navigation par la barre coûte une touche de plus (« Menu »), ce qui pénalise P1 et P2 plus que P3.

**Tâches fréquentes oubliées**
1. **Relancer un lot quand la fenêtre de 5 h se renouvelle** : environ 12 fois pour un lab de 83 rapports, la tâche la plus répétée de toutes.
2. **Importer les PDF d'un lab et régler les fichiers « À trancher »** (sur le PC, à chaque lab).
3. **Ajouter un rapport en retard** à un lab déjà exporté (l'export devient périmé).
4. **Changer de lab** en pleine correction, depuis le lecteur.
5. **Retrouver la note et le PDF annoté** d'un étudiant (réclamation), y compris d'une session passée.
6. **Vérifier avant l'export** les notes vides (une note vide est permise) et les inachevés.
7. **Régler un cours** (barème, style des références) : « Réglages » est désactivé, et aucune proposition ne dit où vivent les réglages par cours.
8. **Début et fin de session** : importer 6 à 8 listes, puis archiver d'un coup la session finie.

## 5. Ce qui manque aux trois

- Le vocabulaire unique (0.1) et un **état chiffré** par lab : reçus sur attendus (non remis), analysés, terminés, exporté.
- La session comme donnée, **et** « Clore la session » : tout est archivé et sort du lot, des énoncés manquants et des filtres.
- Un **plan d'analyse** par lab : « 83 à analyser, environ 12 lots, prochain possible à 17 h 40 », dans l'ordre de correction; « Corriger le suivant » préfère un rapport déjà analysé.
- « Reprendre » enregistré par le moteur : il est lu aujourd'hui dans le `localStorage`, donc sur le PC il montre le dernier rapport ouvert sur le PC, pas sur l'iPad.
- L'**énoncé demandé à l'import** du lab (une zone de dépôt de plus) : la tâche G disparaît presque.
- Les **réglages par cours** dans le menu « … » de l'en-tête du cours (barème, style des références, réimporter la liste).
- Un état vide pour le **début de session** : les sessions passées sont encore là, mais rien de courant.

## 6. Emprunts et recommandation

- À **P1** : la page du lab comme seul pivot (suivi, Claude, export), le lot par lab, le lot en cours dans la barre, la fin des menus sans contexte.
- À **P2** : la session (déduite), la recherche sur toutes les sessions, la fiche d'étudiant, les non remis; la grille comme **vue facultative d'un cours** dans la Bibliothèque.
- À **P3** : « À faire » réduit aux **exceptions**, en rubriques fixes (Bloquant, Revoir, Clore), la rubrique Claude avec l'heure de reprise, la taille du lot calculée.

**Recommandation : P1 comme base, corrigée.** Elle part de ce que Guillaume aime (le suivi), donne une seule porte par lab, coûte le moins cher et supporte l'accumulation des sessions si on lui ajoute la session de P2. P2 met au centre de l'accueil la mauvaise unité (le groupe), et sa grille se heurte sur l'iPad aux règles de couleur et de 44 px. P3 dit quoi faire, mais perd la vue d'ensemble et dépend d'un ordre calculé fragile : elle supprime la navigation au lieu de la réparer, alors que c'est justement la navigation et l'information qui déplaisent.

**Pour les maquettes finales :**
- **Accueil** : un en-tête chiffré (à corriger, à analyser, « Claude ≈ 14 % » ou heure de reprise); le tableau des labs en cours, avec leur état chiffré, « Corriger le suivant » et l'action Claude; une colonne « À faire » réduite aux exceptions.
- **Labs (ex-Bibliothèque)** : recherche en tête; la session courante ouverte, rangée par cours, avec un menu « … » par cours (réglages, liste, carnet); les sessions passées repliées.
- **Page du lab** : le suivi, avec 3 onglets.

Avant de dessiner, vérifier le nom réel d'un fichier Omnivox (point 0.6).
