"""Retire les noms d'étudiants et les DA d'un texte avant son envoi à Claude.

L'anonymiseur couvre le **cours entier** : toutes les listes de classe (tous les groupes,
étudiants retirés compris) et tous les `equipe.json` rangés dans le cours. Peu importe de
quel rapport vient le texte : un coéquipier d'un autre groupe ou un ancien nom repris
dans un passage de plagiat est masqué comme les autres. Les listes restent locales.

Remplacements :
- `[PRÉNOM]` : un mot du prénom d'un étudiant; `[NOM]` : un mot du nom (si un mot est à
  la fois nom et prénom, `[NOM]`). Les noms composés (Tremblay-Roy, Jean-François) sont
  masqués mot par mot; accents, majuscules et casse sont ignorés (ALICE, Dubé, dube).
- `[DA]` : tout numéro de DA connu et toute suite de 6 à 9 chiffres isolée (un nombre
  de cette longueur dans un rapport de lab est de toute façon rare).
- Noms collés sans séparateur (« AliceDubé », « dube_alice », « alicedube ») : le mot
  est découpé en noms connus (4 lettres et plus), au besoin à la frontière minuscule/MAJUSCULE.

Noms très courts (3 lettres ou moins : Roy, Li, Wu, Bo) : un mot ordinaire ne doit pas
disparaître (« le », « Pa », « Li » de lithium...). Compromis :
- un mot courant (liste ci-dessous : le, la, de, du, ...) n'est jamais un nom;
- 3 lettres : masqué seulement en mot entier avec majuscule (« Roy », « ROY »), jamais « roy »;
- 2 lettres ou moins : masqué seulement avec majuscule ET collé (espaces, virgule ou trait
  d'union seulement) à un autre mot de nom ou de prénom (« Wu Li », « Li, Wu »).
Les noms de 4 lettres et plus sont masqués partout, majuscule ou non (la vie privée
passe avant le mot rare qui serait masqué à tort).

Le texte original n'est pas modifié : les positions des fautes restent celles du PDF.
"""

import re
from pathlib import Path

from . import stockage
from .bibliotheque import classes_du_cours, normaliser, racine

NOM, PRENOM, DA = "[NOM]", "[PRÉNOM]", "[DA]"
LONGUEUR_MIN_PARTOUT = 4  # à partir de là, masqué même sans majuscule
SEPARATEURS = re.compile(r"[\s,;:\-–—'’.]*")  # entre deux mots de nom « collés »
MOT = re.compile(r"[^\W_]+")  # lettres et chiffres; « _ » sépare comme une espace
MOTIF_DA = re.compile(r"(?<![0-9])[0-9]{6,9}(?![0-9])")

# Mots ordinaires de 3 lettres ou moins qui ne sont jamais traités comme un nom seul.
MOTS_COURANTS = frozenset("""
a au aux ce ces cet ci de des du d en et eu il je l la le les ma me mes mon ne ni on ou où
par pas pour qu que qui sa se ses si son sur ta te tes ton tu un une va vu y
the and for of to in is it at by an as be or on no
""".split())
MOTS_COURANTS = frozenset(normaliser(m) for m in MOTS_COURANTS)


def _mots(valeur: str) -> list[str]:
    return normaliser(str(valeur)).split()


def _equipes(cours: str) -> list[dict]:
    """Coéquipiers enregistrés (equipe.json) de tous les rapports du cours."""
    resultat = []
    for f in sorted(Path(racine() / cours).glob("*/*/*/equipe.json")):
        liste = stockage.lire_json(f, [])
        resultat += [m for m in liste if isinstance(m, dict)] if isinstance(liste, list) else []
    return resultat


class Anonymiseur:
    def __init__(self, noms: set[str], prenoms: set[str], das: set[str] = frozenset()):
        self.noms = {m for m in noms if m and m not in MOTS_COURANTS}
        self.prenoms = {m for m in prenoms if m and m not in MOTS_COURANTS} - self.noms
        self.das = set(das)
        self.connus = self.noms | self.prenoms
        self.longs = {m for m in self.connus if len(m) >= LONGUEUR_MIN_PARTOUT}

    @classmethod
    def pour(cls, *cours: str) -> "Anonymiseur":
        """Anonymiseur d'un ou plusieurs cours; sans liste de classe, ne masque que les DA."""
        noms, prenoms, das = set(), set(), set()
        for c in dict.fromkeys(cours):
            try:
                personnes = [e for classe in classes_du_cours(c) for e in classe["etudiants"]]
                personnes += _equipes(c)
            except Exception:
                continue
            for e in personnes:
                if not isinstance(e, dict):
                    continue
                noms.update(_mots(e.get("nom", "")))
                prenoms.update(_mots(e.get("prenom", "")))
                da = re.sub(r"\D", "", str(e.get("da") or ""))
                if da:
                    das.add(da)
        return cls(noms, prenoms, das)

    # --- classement d'un mot ---------------------------------------------------

    def _etiquette(self, forme: str) -> str | None:
        return NOM if forme in self.noms else PRENOM if forme in self.prenoms else None

    def _decouper(self, mot: str) -> list[tuple[int, int, str]] | None:
        """Mot collé « AliceDubé » : ses morceaux (début, fin, étiquette) s'il est fait
        seulement de noms connus de 4 lettres et plus, sinon None."""
        # frontières de casse d'abord (« AliceDubé » -> Alice, Dubé), sinon découpe libre
        coupes = [0] + [i for i in range(1, len(mot)) if mot[i - 1].islower() and mot[i].isupper()] + [len(mot)]
        if len(coupes) > 2:
            morceaux = [(a, b, self._etiquette(normaliser(mot[a:b]).replace(" ", ""))) for a, b in zip(coupes, coupes[1:])]
            if all(e and len(normaliser(mot[a:b])) >= LONGUEUR_MIN_PARTOUT for a, b, e in morceaux):
                return morceaux
        # découpe libre sur la forme normalisée (positions suivies lettre par lettre)
        indices, forme = [], ""
        for i, c in enumerate(mot):
            n = normaliser(c).replace(" ", "")
            if n:
                indices.append(i)
                forme += n[0] if len(n) == 1 else n  # « æ » etc. rares : ignorés par la suite
        if len(forme) != len(indices) or len(forme) < 2 * LONGUEUR_MIN_PARTOUT:
            return None
        meilleurs: dict[int, list[tuple[int, int]]] = {0: []}
        for fin in range(1, len(forme) + 1):
            for debut in range(0, fin - LONGUEUR_MIN_PARTOUT + 1):
                if debut in meilleurs and forme[debut:fin] in self.longs:
                    meilleurs[fin] = meilleurs[debut] + [(debut, fin)]
                    break
        if len(forme) not in meilleurs or len(meilleurs[len(forme)]) < 2:
            return None
        return [(indices[a], indices[b - 1] + 1, self._etiquette(forme[a:b])) for a, b in meilleurs[len(forme)]]

    def _verdicts(self, texte: str, mots: list[re.Match]) -> list[str | None]:
        """Étiquette de chaque mot du texte (None = gardé)."""
        formes = [normaliser(m.group(0)).replace(" ", "") for m in mots]
        res: list[str | None] = []
        for m, f in zip(mots, formes):
            brut = m.group(0)
            if f in self.das:
                res.append(DA)
            elif f in self.longs:
                res.append(self._etiquette(f))
            elif f in self.connus and len(f) == 3 and brut[0].isupper():
                res.append(self._etiquette(f))
            else:
                res.append(None)
        # mots de 2 lettres ou moins : seulement collés à un autre mot de nom ou de prénom
        for i, (m, f) in enumerate(zip(mots, formes)):
            if res[i] or f not in self.connus or len(f) > 2 or not m.group(0)[0].isupper():
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(mots) and (res[j] in (NOM, PRENOM) or formes[j] in self.connus):
                    entre = texte[min(m.end(), mots[j].end()):max(m.start(), mots[j].start())]
                    if SEPARATEURS.fullmatch(entre):
                        res[i] = self._etiquette(f)
                        break
        return res

    # --- API -------------------------------------------------------------------

    def masquer(self, texte: str) -> str:
        """Texte sans noms, prénoms ni DA (voir l'en-tête du module pour les règles)."""
        if not texte:
            return texte
        remplacements: list[tuple[int, int, str]] = []
        mots = list(MOT.finditer(texte))
        verdicts = self._verdicts(texte, mots)
        for m, v in zip(mots, verdicts):
            if v:
                remplacements.append((m.start(), m.end(), v))
                continue
            brut = m.group(0)
            if len(brut) >= 2 * LONGUEUR_MIN_PARTOUT and not brut.isdigit():
                morceaux = self._decouper(brut)
                if morceaux:
                    remplacements += [(m.start() + a, m.start() + b, e) for a, b, e in morceaux]
        for m in MOTIF_DA.finditer(texte):  # toute suite de 6 à 9 chiffres, DA connu ou non
            if not any(a <= m.start() < b for a, b, _ in remplacements):
                remplacements.append((m.start(), m.end(), DA))
        morceaux_sortie, fin = [], 0
        for a, b, etiquette in sorted(remplacements):
            if a < fin:
                continue
            morceaux_sortie += [texte[fin:a], etiquette]
            fin = b
        return "".join(morceaux_sortie) + texte[fin:]
