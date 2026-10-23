# Accueil et Bibliothèque : analyse et 3 maquettes (octobre 2026)

Guillaume aime la direction A « Atelier » en sarcelle (PR #59 à #62), mais pas l'**Accueil** ni la **Bibliothèque** : l'information présentée et la navigation d'un menu à l'autre. Ce dossier ne touche **aucun code de l'app**.

- Comparaison (aussi publiée comme Artifact privé, lisible sur l'iPad) : [`comparaison.html`](comparaison.html).
- Maquettes (HTML statique, données **fictives**) : [`p1-lab.html`](p1-lab.html), [`p2-carnet.html`](p2-carnet.html), [`p3-aujourdhui.html`](p3-aujourdhui.html). Un écran seul : `#seul-<id>`.
- Captures de l'app actuelle : `captures/` (moteur en `--local`, bibliothèque fictive de 721 rapports : 4 cours, 2 sessions, 15 labs, tous les états; serveur arrêté ensuite). Images des maquettes : `img/`.

## 1. Raisonnement : pourquoi ces deux onglets sont ainsi

**Intentions reconstituées** (docs, PR 2, maquette A) :
- **Accueil** : l'ancien accueil était vide aux deux tiers (constat 2 de `propositions-2026-10`). La PR 2 l'a rempli avec trois idées : *reprendre* (carte « Reprendre là où tu étais », 1 toucher), *ce qui demande une action* (bloc « À faire » emprunté à la direction C : fichiers à associer, fautes à trancher par lab, paires de plagiat, export à refaire) et *où en sont les labs* (tableau Lab / Progression / Export LÉA, filtre En cours / Terminés / Tout).
- **Bibliothèque** : elle reflète le **rangement sur disque** (`cours / lab / groupe / étudiant`, le lab au-dessus du groupe parce que l'énoncé s'applique au lab). Historiquement, c'était *toute* l'app (étape 1) : chaque fonction ajoutée s'y est greffée là où elle s'appliquait (énoncé et export au lab, lot et plagiat au groupe, annotation, français, IA, équipe et « Terminé » au rapport). Le tableau de suivi (2026-10-20) est arrivé ensuite pour le travail rapport par rapport, sans retirer la liste de la bibliothèque.
- **Barre latérale** : navigation **par fonction** (Importer, Analyse par lot, Plagiat, Export LÉA) + raccourcis « Labs en cours » vers le suivi + jauge de Claude (PR #66).

**Parcours réels** (iPad paysage, départ = Accueil, défilement non compté) :

| Tâche | Touchers | Chemin actuel |
|---|---|---|
| Reprendre le dernier rapport | 1 | Reprendre |
| Corriger le prochain rapport d'un lab | 2 | Labs en cours → Corriger le suivant |
| Ouvrir le rapport d'un étudiant (lab en cours) | 2 + défiler 80 lignes, ou 5 | Suivi; ou Bibliothèque → cours → lab → groupe → Annoter (+1 s'il est terminé) |
| Même chose, session passée | 7 + défiler | Bibliothèque → filtre → cours → lab → groupe → Terminés → Annoter |
| Lancer un lot sur un lab de 3 groupes | 9 | Analyse par lot → liste de 26 couples cours·groupe·lab → Lancer, ×3 groupes (le bouton du suivi ne garde pas le lab) |
| Exporter un lab terminé | 3 à 5 | À faire → défiler → Préparer → Télécharger; ou Export LÉA → bibliothèque repliée → cours → lab → … |
| Téléverser l'énoncé | 5 | Bibliothèque → cours → lab → Téléverser → fichier |
| Modifier l'équipe d'un rapport | 6 | Bibliothèque → cours → lab → groupe → « … » → Équipe |
| Clore un lab de 3 groupes | 6 par groupe | Bibliothèque → cours → lab → groupe → « … » → Marquer le lab terminé |

## 2. Critique de ce raisonnement

**Points forts** : reprendre en 1 toucher; « Corriger le suivant » à 2 touchers de partout grâce aux labs de la barre; « À faire » est le seul endroit qui rassemble ce qui traverse les labs (import, plagiat, export périmé); rien n'est caché ni supprimé; filtres et dépliage gardés sur l'appareil; style cohérent, cibles de 44 px.

**Points faibles** :
1. **Même information trois fois** : les 4 labs en cours sont dans la barre, dans « À faire » et dans le tableau « Labs » de l'accueil. L'espace répète au lieu d'informer.
2. **Deux portes pour un même lab** : « Suivi » (le tableau riche) et le chevron vers la bibliothèque (énoncé, export, groupes, liste d'étudiants **sans état**). Il faut savoir quelle porte a quelle action; le suivi n'a ni énoncé, ni export, ni clôture.
3. **Information choisie d'après le rangement, pas d'après le travail** : le vrai cycle d'un lab est importer → énoncé → **analyser (Claude, 6 à 7 rapports par lot, un lab de 80 = une dizaine de lots sur plusieurs fenêtres de 5 h)** → corriger → revoir les indices → exporter → déposer dans LÉA → clore. L'accueil ne montre que « terminés / total » et l'export : « 0 / 83 » ne dit pas que rien n'est analysé, alors que l'analyse est le goulot (budget Claude).
4. **« À faire » compte la mauvaise unité** : « 90 fautes à trancher » *est* le travail de correction, pas une tâche à part; ce chiffre dominera toujours la liste. Il manque : lots à lancer, énoncé manquant, « Claude manquant », limite atteinte avec l'heure de reprise, lab fini mais pas clos.
5. **Bibliothèque profonde et muette** : 4 niveaux repliés, aucune recherche (nom, DA), une ligne d'étudiant = nom + « Annoter » sans état (fautes, IA, plagiat, note); le bloc d'export (≈ 400 px) s'intercale entre le lab et ses groupes même à mi-correction; un groupe ouvert fait défiler la page à 2 100 px.
6. **Pas de session** : le code du cours vient du fichier Omnivox (`ListeEtudiants_cours<code>_gr<n°>`) et le rangement n'a pas de session. Le filtre « En cours » affiche encore les cours de la session passée (vides une fois ouverts); le lot propose 26 couples dont les archivés; « Énoncé manquant (15) » compte les labs clos. **Risque de données à vérifier** : si le code et le n° de groupe d'Omnivox restent les mêmes d'une session à l'autre, la liste d'automne fusionnera avec celle d'hiver et le « lab-1 » d'automne tombera dans le dossier de celui d'hiver.
7. **Menus par fonction sans contexte** : « Export LÉA » mène à la bibliothèque repliée (l'explication n'est qu'une infobulle, invisible sur l'iPad); « Analyse par lot » oblige à rechoisir le lab dans une liste, **par groupe**, alors que le suivi et l'export sont **par lab**.
8. **Portrait** : la barre devient un tiroir; les raccourcis « Labs en cours » coûtent un toucher de plus.
9. **Libellés** : « Annoter », « Reprendre », « Corriger le suivant » pour la même action; « Terminé » pour un rapport et pour un lab; titres bruts (« lab-2 »).

## 3. Trois propositions (version 1, avant la critique)

- **P1 « Le lab au centre »** (objet) : une seule page par lab (suivi + analyse + énoncé + export), le cycle en étapes; l'accueil montre chaque lab en cours avec **une seule action suivante**; la Bibliothèque devient **Labs** (liste de labs par session et cours, sans étudiants).
- **P2 « Le carnet de la session »** (personnes) : la **session** devient une donnée, **recherche** partout (nom, DA), accueil par **groupe**, Bibliothèque en **grille étudiants × labs** avec fiche d'étudiant.
- **P3 « Aujourd'hui »** (tâches) : l'accueil est une **file de tâches priorisée**, chaque tâche a son bouton; la Bibliothèque devient archives et recherche; barre latérale réduite.

## 4. Critique indépendante (second agent Opus, sans mon raisonnement)

Texte complet : [`critique-independante.md`](critique-independante.md). L'essentiel :
- **Ce qu'aucune des trois ne corrigeait** : **quatre sens de « corrigé »** pour un même lab (34/80 terminés, « 20 à corriger » = non terminés, « À corriger 10 » = pas commencés, « 49 rapports corrigés » de l'export = tout tranché); deux boutons pleins dans le bloc du lab (règle 4 enfreinte); interrupteur « inclure les inachevés » **coché par défaut** (`export-lea.js:63`) alors que PLAN.md dit « exclus sauf case »; **non remis invisibles**; la session est un **risque de données** (vérifié : `MOTIF_LISTE` n'accepte que `[A-Za-z0-9]+`).
- **P1** : bonne unité, la moins chère; mais **une seule « étape suivante » ne colle pas** (l'analyse par lots de 7 et la correction se chevauchent pendant des jours), cartes trop hautes, pas de recherche.
- **P2** : seule à traiter la session, recherche et fiche utiles; mais **accueil par groupe = mauvaise unité**, grille qui ne tient pas « jamais la couleur seule », sélecteur de session global = un mode piège.
- **P3** : la **rubrique Claude** (« possible après 17 h 40 ») est la meilleure idée des trois; mais **ordre calculé = boîte noire**, « Plus tard » cache des choses, plus de vue d'ensemble.
- **Touchers** : plusieurs chiffres optimistes (corrigés ci-dessous); tâches oubliées : **relancer un lot à chaque fenêtre de 5 h** (≈ 12 fois pour un lab de 83), import + « À trancher », rapport en retard, réclamation de note d'une session passée, réglages par cours.
- **Recommandation de l'agent** : P1 comme base, avec la session, la recherche et la fiche de P2, et « À faire » en exceptions + rubrique Claude de P3.

## 5. Décisions communes (signées par les deux agents)

1. **Vocabulaire fixe** partout : **Reçus / Analysés / Terminés / Export**; « corrigé » disparaît. Non remis = inscrit non retiré sans rapport ni place dans une équipe.
2. **Session déduite** de la date d'import de la liste (A/H/É + année), confirmée seulement en cas de doute; **pas de mode global** : session courante par défaut, passées repliées et en **lecture seule** (hors lot, énoncés manquants, « À faire »); « Clore la session » dans le « … » de la session.
3. **Recherche** sur toutes les sessions; un résultat = un rapport, avec session, état et note.
4. **« À faire » = exceptions seulement**, rubriques fixes (Bloquant, Revoir, Clore); plus jamais « N fautes à trancher ».
5. **Claude** : « ≈ 38 % · lot conseillé : 7 » ou « reprise 17 h 40 », d'après l'estimation du moteur; **lot par lab**, dans l'ordre de correction, lancé en **une touche** avec un toast « Arrêter ».
6. « Analyse par lot » et « Export LÉA » **quittent la barre latérale**; le lot en cours s'affiche sous la jauge; l'écran du lot va dans le suivi.
7. Réglages d'un cours (barème, style des références, réimporter la liste) dans le « … » du cours.
8. **Un seul bouton plein par zone**, tableaux compris; titres lisibles (« Lab 2 »).
9. « Labs en cours » gardé dans la barre de P1 et P3 (6 au plus), retiré dans P2.
10. P1 = **agir**, P2 = **trouver**, P3 = **aujourd'hui** : trois directions nettement différentes.
11. En portrait, la recherche est dans la barre du haut, jamais dans le tiroir.

**Désaccords et arbitrages** :
- *« Labs en cours » dans la barre* : l'agent voulait le retirer (doublon sur l'accueil); gardé dans P1 et P3 parce que c'est le seul moyen de changer de lab depuis le suivi, le plagiat ou la consommation (barre = aller, accueil = état + action). Retiré dans P2, au prix d'une touche.
- *Accueil de P2* : je voulais garder le groupe au centre pour distinguer P2; l'agent a montré que la correction, le lot et l'export se font par lab. Arbitrage : une ligne **par lab, ventilée par groupe, sans bouton** (P2 lit, P1 agit).
- *Feuille de confirmation avant un lot* (P3) : retirée; le bouton porte l'estimation et le toast offre « Arrêter ».
- *Grille de P2 sur 84 lignes* : gardée sans limiter à un groupe, avec en-têtes figés et sélecteur « Tous · 01 · 02 · 03 » gardé sur l'appareil.

## 6. Maquettes finales

| | **P1 « Le lab au centre » : agir** | **P2 « Le carnet » : trouver** | **P3 « Aujourd'hui » : quoi faire** |
|---|---|---|---|
| Accueil | en-tête chiffré (Reprendre, analysés à corriger, à analyser, Claude) + puces d'exceptions + **tableau des labs en cours** (État, Export, « Corriger », « Analyser 7 · 21 % ») | **recherche** en grand + **Récents** (tous appareils) + exceptions + une ligne par lab **ventilée par groupe**, sans bouton | Reprendre + **5 rubriques dans un ordre fixe** : Bloquant, Corriger, Claude, Revoir, Clore; « Fait aujourd'hui » |
| Bibliothèque | **Labs** : recherche, session courante par cours (une ligne par lab), sessions passées repliées; **page du lab** = suivi à 3 onglets | **Carnet** : étudiants × labs (une case = note ou mot), en-têtes figés, **fiche d'étudiant** (panneau, feuille en portrait) | **Archives et recherche** : session courante en une ligne, sessions passées en cartes, « Mis de côté » (écartés, remplacés) |
| Barre latérale | Accueil, Labs, Importer, Plagiat, jauge, labs en cours | Accueil, Carnet, Importer, Plagiat, jauge, cours de la session | recherche, Aujourd'hui, Bibliothèque, Importer, Plagiat, jauge, lot en cours, labs en cours |
| Pour | une porte par lab, actions dans le contexte, la moins chère | n'importe quel étudiant en 2 touches, non remis et notes d'un coup d'œil | le moins de touches, rien à mémoriser, la contrainte Claude au premier plan |
| Contre | pas de vue par étudiant hors recherche | changer de lab coûte une touche; nouvelle vue (le carnet) à construire | moins de vue d'ensemble; « Fait aujourd'hui » demande l'heure des « Terminé » |

**Touchers** (chiffres de l'agent, adoptés; iPad paysage, départ = accueil; tâches 6 et 7 sur PC) :

| Tâche | Actuel | P1 | P2 | P3 |
|---|---|---|---|---|
| 1. Relancer un lot (fenêtre renouvelée) | 4 + saisie | 1 | 2 | 1 |
| 2. Corriger le suivant d'un autre lab | 2 | 1 | 2 | 1 |
| 3. Changer de lab depuis le lecteur | 3 | 3 | 4 | 3 |
| 4. Rapport d'un étudiant, lab en cours | 2 + défiler | 3 (recherche) ou 2 + défiler | 2 | 2 |
| 5. Rapport et note d'une session passée | 5 + défiler | 3 | 2 | 2 |
| 6. Importer un lab + 3 « À trancher » (PC) | ≈ 11 | ≈ 11 | ≈ 11 | ≈ 11 |
| 7. Exporter un lab terminé (PC) | 3 | 2 | 2 | 2 |
| 8. Téléverser l'énoncé | 3 | 2 | 2 | 2 |
| 9. Modifier une équipe | 7-8 | 4-5 | 4-5 | 4-5 |
| 10. Clore un lab de 3 groupes (rare) | 18 | 3 | 3 | 3 |

**Vérifications** : contraste WCAG AA de chaque texte des 3 maquettes (script `sources/contraste.py` : 1 558 textes, 0 échec); cibles ≥ 44 px (script `sources/captures.py` : 0 écart); aucune erreur de console. Données **fictives** (noms inventés). Les maquettes sont autonomes (jetons, composants et coque de la PWA, Inter et Lucide en ligne); pour les régénérer : `python sources/construire.py <dépôt> <sortie>`.

## Recommandation

**Choisie par Guillaume le 2026-10-23.** **P1 « Le lab au centre »**, avec la fiche d'étudiant de P2 ouverte depuis la recherche. Elle part de l'écran que Guillaume aime déjà (le suivi, qui devient la page du lab), donne une seule porte par lab, met le lot de Claude à une touche et coûte le moins à construire. P3 est la meilleure si Guillaume préfère qu'on lui dise quoi faire plutôt que de voir ses labs; P2 si ses questions sont surtout « où en est tel étudiant ».

## Dépendances et suites (hors maquettes)

- **Session** : vérifier d'abord un vrai nom de fichier Omnivox (le code de cours ou le n° de groupe changent-ils d'une session à l'autre ?), sinon la liste et le « lab-1 » de la session suivante tombent dans ceux de la précédente.
- **Lot par lab** (moteur, aujourd'hui par groupe), dans l'ordre de correction; écran du lot dans le suivi.
- « **Équipe…** » dans le menu « … » du suivi (aujourd'hui seulement dans la bibliothèque).
- « Reprendre » et « Récents » **enregistrés par le moteur** (aujourd'hui `localStorage` : le PC ne voit pas l'iPad).
- **Inachevés exclus par défaut** à l'export (`export-lea.js:63`, contraire à PLAN.md); notes vides signalées avant l'export.
- Énoncé demandé à l'import du lab; heure de chaque « Terminé » dans `statut.json` (pour « Fait aujourd'hui »).
