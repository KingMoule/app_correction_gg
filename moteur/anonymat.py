"""Retire les noms d'étudiants d'un texte avant son envoi à Claude.

Les noms viennent de la liste de classe (locale). Sont masqués (« [NOM] ») :
- les mots du nom et du prénom de l'étudiant du rapport;
- les noms de famille des autres étudiants du groupe (au moins 4 lettres, pour ne pas
  masquer de petits mots courants), et leur prénom quand il touche un nom masqué
  (« Marie Gagnon »).
Le texte original n'est pas modifié : les positions des fautes restent celles du PDF.
"""

import re

from .bibliotheque import charger_classe, normaliser

MASQUE = "[NOM]"
LONGUEUR_MIN_AUTRES = 4


def _mots(valeur: str) -> set[str]:
    return set(normaliser(valeur).split())


class Anonymiseur:
    def __init__(self, propres: set[str], noms_autres: set[str], prenoms_autres: set[str]):
        self.propres, self.noms_autres, self.prenoms_autres = propres, noms_autres, prenoms_autres

    @classmethod
    def pour(cls, cours: str, groupe: str, etudiant: str) -> "Anonymiseur":
        """Anonymiseur du rapport d'un étudiant; sans liste de classe, ne masque rien."""
        try:
            liste = charger_classe(cours, groupe)["etudiants"]
        except Exception:
            liste = []
        propres, noms, prenoms = set(), set(), set()
        for e in liste:
            if e["id"] == etudiant:
                propres |= _mots(e["nom"]) | _mots(e["prenom"])
            else:
                noms |= {m for m in _mots(e["nom"]) if len(m) >= LONGUEUR_MIN_AUTRES}
                prenoms |= _mots(e["prenom"])
        return cls(propres, noms - propres, prenoms - propres)

    def masquer(self, texte: str) -> str:
        mots = list(re.finditer(r"\w+", texte))
        cachés = [normaliser(m.group(0)) in self.propres | self.noms_autres for m in mots]
        # un prénom d'un autre étudiant collé (espaces seulement) à un nom masqué
        for i, m in enumerate(mots):
            if cachés[i] or normaliser(m.group(0)) not in self.prenoms_autres:
                continue
            for j in (i - 1, i + 1):
                if 0 <= j < len(mots) and cachés[j]:
                    entre = texte[min(m.end(), mots[j].end()):max(m.start(), mots[j].start())]
                    if entre.strip() == "":
                        cachés[i] = True
        morceaux, fin = [], 0
        for m, cache in zip(mots, cachés):
            if cache:
                morceaux += [texte[fin:m.start()], MASQUE]
                fin = m.end()
        return "".join(morceaux) + texte[fin:]
