"""Mesures de style locales (gratuites) sur la prose d'un rapport, et écart à l'habitude d'un étudiant.

Sert à la comparaison avec les rapports antérieurs (`comparaison_style.py`). Seule la prose compte : les lignes de
calcul, les tableaux et la section des références sont retirés avec le découpage de `francais_filtre.py`.
Rien ici n'appelle Claude ni LanguageTool. Les écarts sont des indices à revérifier, jamais un verdict.
"""

import re
import statistics
import unicodedata

from . import francais_filtre

# (clé, libellé, unité, plancher absolu de l'échelle) : le plancher évite qu'un étudiant très régulier
# (écart quasi nul entre ses rapports) fasse paraître la moindre différence énorme.
MESURES = [
    ("phrase_moy", "Longueur moyenne des phrases (mots)", "", 2.0),
    ("phrase_ecart", "Dispersion des phrases (écart-type, en mots)", "", 1.5),
    ("variete", "Variété du vocabulaire", "", 0.03),
    ("connecteurs", "Connecteurs pour 100 mots", "", 0.5),
    ("virgules", "Virgules pour 100 mots", "", 1.0),
    ("ponct_forte", "Points-virgules, deux-points et parenthèses pour 100 mots", "", 0.5),
    ("fautes", "Fautes de français pour 100 mots", "", 0.5),
]
LIBELLES = {c: (lib, unite) for c, lib, unite, _ in MESURES}
PLANCHERS = {c: p for c, _, _, p in MESURES}

FENETRE_VARIETE = 100   # mots par fenêtre : la variété se mesure sur un échantillon de taille fixe
PAS_VARIETE = 50
MIN_MOTS_PROSE = 30     # en dessous, les mesures n'ont aucun sens
SEUIL_ECART, SEUIL_FORT = 2.0, 3.5  # en échelles robustes

CONNECTEURS = [
    "de plus", "en effet", "par ailleurs", "ainsi", "cependant", "toutefois", "en outre", "de ce fait",
    "par conséquent", "néanmoins", "en conclusion", "en somme", "notamment", "d'ailleurs", "en revanche",
    "or", "donc", "puis", "ensuite", "enfin", "d'une part", "d'autre part", "il est important de",
    "il convient de", "autrement dit", "c'est pourquoi", "afin de", "en particulier", "de surcroît",
    "malgré", "pourtant", "alors que", "tandis que", "en raison de", "grâce à", "par exemple",
]


def _sans_accent(texte: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFD", texte) if unicodedata.category(c) != "Mn")


_MOT = re.compile(r"[^\W\d_]+(?:['’\-][^\W\d_]+)*")
_PHRASES = re.compile(r"(?<=[.!?…])\s+")
_CONNECTEURS = [(c, re.compile(r"(?<![^\W\d_])" + re.escape(_sans_accent(c).replace("’", "'")) + r"(?![^\W\d_])"))
                for c in CONNECTEURS]


def _technique(ligne: str) -> bool:
    return any(francais_filtre._jeton_technique(francais_filtre._ENTOURAGE.match(j).group(2)) for j in ligne.split())


def prose(texte: str) -> str:
    """Le texte sans calculs, tableaux ni références, en paragraphes continus (les sauts de ligne du PDF deviennent des espaces).

    Une ligne qui n'est pas de la prose à elle seule (dernière ligne courte d'un paragraphe : « en parallèle. ») est gardée
    quand elle prolonge une phrase de la ligne précédente et ne contient ni chiffre ni symbole."""
    paragraphes, courant, precedente, fin_phrase = [], [], False, True
    for ligne in texte.split("\n"):
        s = ligne.strip()
        if francais_filtre._TITRE_REFERENCES.match(s):
            break  # tout ce qui suit est la liste des sources
        if not s:
            paragraphes.append(" ".join(courant)); courant, precedente = [], False
            continue
        garde = francais_filtre.ligne_est_prose(s) or (
            precedente and not _technique(s) and (not fin_phrase or s[-1] in ".!?…"))
        if garde:
            courant.append(s)
        precedente, fin_phrase = garde, s[-1] in ".!?:;…"
    paragraphes.append(" ".join(courant))
    return "\n\n".join(re.sub(r"\s+", " ", p).strip() for p in paragraphes if p.strip())


def mots(texte: str) -> list[str]:
    return [m.group(0).lower().replace("’", "'") for m in _MOT.finditer(texte)]


def phrases(texte: str) -> list[str]:
    """Phrases d'au moins 3 mots."""
    sortie = []
    for p in texte.split("\n\n"):
        sortie += [s.strip() for s in _PHRASES.split(p) if len(mots(s)) >= 3]
    return sortie


def _variete(m: list[str]) -> float | None:
    """Rapport mots différents / mots sur des fenêtres de 100 mots, moyenné (None si moins de 100 mots)."""
    if len(m) < FENETRE_VARIETE:
        return None
    fenetres = [len(set(m[i:i + FENETRE_VARIETE])) / FENETRE_VARIETE
                for i in range(0, len(m) - FENETRE_VARIETE + 1, PAS_VARIETE)]
    return statistics.fmean(fenetres)


def connecteurs_utilises(texte: str) -> dict[str, int]:
    base = " ".join(_sans_accent(texte.lower()).replace("’", "'").split())
    trouves = {}
    for c, motif in _CONNECTEURS:
        n = len(motif.findall(base))
        if n:
            trouves[c] = n
    return trouves


def mesurer(texte_prose: str, taux_fautes: float | None = None) -> dict:
    """Mesures d'un rapport. `taux_fautes` (pour 100 mots) vient de `francais.json` quand il existe."""
    m = mots(texte_prose)
    n = len(m)
    if n < MIN_MOTS_PROSE:
        return {"mots": n, "valeurs": {c: None for c, *_ in MESURES} | {"fautes": taux_fautes}, "connecteurs": {}}
    longueurs = [len(mots(s)) for s in phrases(texte_prose)]
    pour100 = 100 / n
    valeurs = {
        "phrase_moy": statistics.fmean(longueurs) if longueurs else None,
        "phrase_ecart": statistics.pstdev(longueurs) if len(longueurs) > 1 else None,
        "variete": _variete(m),
        "connecteurs": sum(connecteurs_utilises(texte_prose).values()) * pour100,
        "virgules": texte_prose.count(",") * pour100,
        "ponct_forte": sum(texte_prose.count(c) for c in ";:(") * pour100,
        "fautes": taux_fautes,
    }
    return {"mots": n, "valeurs": valeurs, "connecteurs": connecteurs_utilises(texte_prose)}


# --- Écart à l'habitude ---------------------------------------------------------------------

def moyenne_ponderee(valeurs: list[float], poids: list[float]) -> float:
    return sum(v * p for v, p in zip(valeurs, poids)) / sum(poids)


def mediane_ponderee(valeurs: list[float], poids: list[float]) -> float:
    paires = sorted(zip(valeurs, poids))
    moitie = sum(poids) / 2
    cumul = 0.0
    for v, p in paires:
        cumul += p
        if cumul >= moitie:
            return v
    return paires[-1][0]


def echelle_robuste(valeurs: list[float], poids: list[float], cle: str) -> float:
    """Écart robuste (MAD pondérée autour de la médiane, × 1,4826), jamais sous le plancher de la mesure
    ni sous 10 % de l'habitude : avec 2 ou 3 rapports, la dispersion observée est trop incertaine pour s'y fier seule."""
    med = mediane_ponderee(valeurs, poids)
    mad = mediane_ponderee([abs(v - med) for v in valeurs], poids)
    return max(1.4826 * mad, PLANCHERS[cle], 0.1 * abs(moyenne_ponderee(valeurs, poids)))


def comparer(courant: dict, anterieurs: list[dict], poids: list[float]) -> list[dict]:
    """Une ligne par mesure : valeur du rapport, habitude (moyenne pondérée), écart en échelles robustes et son niveau.

    `courant` et chaque élément de `anterieurs` sont des résultats de `mesurer`. Une mesure absente (None) chez le rapport,
    ou chez moins de 2 rapports antérieurs, est présentée sans écart."""
    lignes = []
    for cle, libelle, unite, _ in MESURES:
        v = courant["valeurs"].get(cle)
        paires = [(a["valeurs"].get(cle), p) for a, p in zip(anterieurs, poids) if a["valeurs"].get(cle) is not None]
        ligne = {"cle": cle, "libelle": libelle, "unite": unite, "valeur": _arrondi(v), "habitude": None,
                 "ecart": None, "niveau": "inconnu", "sens": None, "n": len(paires)}
        if v is not None and len(paires) >= 2:
            vals, ps = [x for x, _ in paires], [p for _, p in paires]
            habitude = moyenne_ponderee(vals, ps)
            z = (v - habitude) / echelle_robuste(vals, ps, cle)
            ligne.update(habitude=_arrondi(habitude), ecart=round(z, 1),
                         niveau="fort" if abs(z) >= SEUIL_FORT else "ecart" if abs(z) >= SEUIL_ECART else "habituel",
                         sens=None if abs(z) < SEUIL_ECART else "haut" if z > 0 else "bas")
        lignes.append(ligne)
    return lignes


def _arrondi(v: float | None) -> float | None:
    return None if v is None else round(v, 2)


# --- Extraits comparables -------------------------------------------------------------------

LONGUEUR_PASSAGE_MAX = 450
MOTS_PASSAGE_MIN = 20


def passages(texte_prose: str, combien: int) -> list[str]:
    """Jusqu'à `combien` passages de 1 à 3 phrases (20 mots au moins), répartis dans le rapport."""
    groupes, courant = [], []
    for s in phrases(texte_prose):
        courant.append(s)
        if len(courant) == 3 or len(mots(" ".join(courant))) >= 2 * MOTS_PASSAGE_MIN:
            groupes.append(" ".join(courant))
            courant = []
    if courant:
        groupes.append(" ".join(courant))
    groupes = [g[:LONGUEUR_PASSAGE_MAX].rstrip() for g in groupes if len(mots(g)) >= MOTS_PASSAGE_MIN]
    if combien <= 0 or not groupes:
        return []
    if len(groupes) <= combien:
        return groupes
    # indices répartis (milieu de chaque tranche)
    return [groupes[int((i + 0.5) * len(groupes) / combien)] for i in range(combien)]
