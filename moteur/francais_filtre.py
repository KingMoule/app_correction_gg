"""Filtrage du français : ne vérifier que la prose, avec des mots complets.

Le texte extrait d'un PDF mêle phrases, calculs, tableaux, unités et symboles. Trois
étages évitent de compter ces éléments comme des fautes :
1. `segmenter` : les lignes qui ne sont pas des phrases (calculs, tableaux, légendes
   courtes) et les jetons à chiffres ou symboles d'une phrase passent en « markup » pour
   LanguageTool (ignoré, mais compté dans les positions : les `zones` restent justes);
2. règles de typographie désactivées (espaces autour de la ponctuation : artefacts
   d'extraction);
3. `garder` : après coup, une faute d'orthographe n'est gardée que si elle porte sur un mot
   ordinaire (ni jeton à chiffre, ni 1 à 3 lettres, ni unité, sigle, formule, nom propre),
   et que le mot n'est pas dans le lexique de Guillaume.
"""

import re
from dataclasses import dataclass, field

from . import languagetool, stockage
from .config import dossier_donnees

# Règles et catégories LanguageTool qui produisent surtout du bruit sur un texte extrait d'un PDF.
REGLES_DESACTIVEES = [
    "COMMA_PARENTHESIS_WHITESPACE", "FRENCH_WHITESPACE", "WHITESPACE_RULE", "PARENTHESES",
    "NOMBRES_EN_LETTRES_2", "NOMBRES_EN_LETTRES", "ESPACE_UNITES", "UNITES", "APOS_TYP",
    # Sauts de ligne du PDF et jetons techniques retirés : ces règles se déclenchent à tort.
    "UPPERCASE_SENTENCE_START", "UNPAIRED_BRACKETS", "DOUBLES_ESPACES", "DETERMINER_SENT_END",
]
CATEGORIES_DESACTIVEES = ["TYPOGRAPHY"]

REGLES_ORTHOGRAPHE = {"FR_SPELLING_RULE", "MORFOLOGIK_RULE_FR_FR"}

_MOT = re.compile(r"^[^\W\d_]+(?:['’\-][^\W\d_]+)*$")
_ENTOURAGE = re.compile(r"^([(\[«\"“]*)(.*?)([.,;:!?)\]»\"”]*)$", re.S)
_SYMBOLES = set("=+×*/^<>±≈%_°²³√∆Δ∑·−→←≥≤|~#&@\\{}")
_FIN_PHRASE = set(".!?:;…")

# Titre d'une section de références : tout ce qui suit est ignoré (sources, souvent en anglais).
_TITRE_REFERENCES = re.compile(
    r"^\W*(\d+[.)]?\s*)?(bibliographie|r[ée]f[ée]rences( bibliographiques)?|sources|webographie|"
    r"ouvrages consult[ée]s|references|bibliography)\W*$", re.I)

# Unités et abréviations de 4 lettres ou plus que le correcteur ne connaît pas.
UNITES = {
    "mmol", "kmol", "mole", "moles", "kpa", "mpa", "atm", "khz", "mhz", "ghz", "ppm", "ohms",
    "watt", "watts", "volt", "volts", "kilo", "mmhg", "torr", "cmhg",
}


@dataclass
class Segmentation:
    parties: list[dict]
    lignes_markup: list[tuple[int, int]] = field(default_factory=list)  # lignes entières ignorées


def _est_mot(jeton: str) -> bool:
    # Les lettres mathématiques (𝑥, 𝒎𝑳 : hors plan de base) sont des symboles, pas des mots.
    return len(jeton) >= 3 and bool(_MOT.match(jeton)) and all(ord(c) <= 0xFFFF for c in jeton)


def _ligne_est_prose(jetons: list[str]) -> bool:
    if not jetons:
        return False
    nettoyes = [_ENTOURAGE.match(j).group(2) for j in jetons]
    mots = sum(1 for j in nettoyes if _est_mot(j))
    if mots < 3 or mots / len(jetons) < 0.5:
        return False
    return True


def ligne_est_prose(ligne: str) -> bool:
    """Une ligne de texte rédigé (et non un calcul, un tableau ou une légende courte)."""
    return _ligne_est_prose(ligne.split())


def _jeton_technique(coeur: str) -> bool:
    return any(c.isdigit() or c in _SYMBOLES for c in coeur)


def segmenter(texte: str) -> Segmentation:
    """Découpe `texte` en parties vérifiées (`text`) et ignorées (`markup`), sans rien perdre."""
    parties: list[dict] = []
    lignes: list[tuple[int, int]] = []

    def ajouter(type_: str, contenu: str, lecture: str | None = None) -> None:
        if not contenu:
            return
        if parties and type_ in parties[-1] and lecture is None and "interpretAs" not in parties[-1]:
            parties[-1][type_] += contenu
            return
        p = {type_: contenu}
        if lecture is not None:
            p["interpretAs"] = lecture
        parties.append(p)

    pos = 0
    en_references = False
    for ligne in texte.split("\n"):
        jetons = ligne.split()
        en_references = en_references or bool(_TITRE_REFERENCES.match(ligne))
        if en_references or not _ligne_est_prose(jetons):
            if ligne.strip():
                lignes.append((pos, pos + len(ligne)))
                ajouter("markup", ligne)
            else:
                ajouter("text", ligne)
        else:
            reste = 0
            for m in re.finditer(r"\S+", ligne):
                ajouter("text", ligne[reste : m.start()])
                avant, coeur, apres = _ENTOURAGE.match(m.group(0)).groups()
                if _jeton_technique(coeur):
                    ajouter("text", avant)
                    # Un nombre se lit « 2 » (pluriel, ne gêne pas les accords); un symbole, rien.
                    ajouter("markup", coeur, "2" if any(c.isdigit() for c in coeur) else "")
                    ajouter("text", apres)
                else:
                    ajouter("text", m.group(0))
                reste = m.end()
            ajouter("text", ligne[reste:])
        pos += len(ligne)
        if pos < len(texte):
            ajouter("text", "\n")
            pos += 1
    return Segmentation(parties, lignes)


def prose_pour_claude(texte: str, seg: Segmentation) -> str:
    """`texte` sans les lignes de calcul ou de tableau (les positions ne servent pas à Claude)."""
    sortie, pos = [], 0
    for d, f in seg.lignes_markup:
        sortie.append(texte[pos:d])
        pos = f
    sortie.append(texte[pos:])
    return re.sub(r"\n{3,}", "\n\n", "".join(sortie))


# --- Lexique de Guillaume (global) --------------------------------------------

def fichier_lexique():
    return dossier_donnees() / "lexique.json"


def lire_lexique() -> set[str]:
    mots = stockage.lire_json(fichier_lexique(), [])
    return {str(m).lower() for m in mots} if isinstance(mots, list) else set()


def ecrire_lexique(mots: set[str]) -> None:
    stockage.ecrire_json(fichier_lexique(), sorted(mots))


def modifier_lexique(modifier) -> set[str]:
    """Lecture-modification-écriture du lexique sous verrou : `modifier(mots)` renvoie le nouvel ensemble."""
    f = fichier_lexique()
    with stockage.verrou(f.parent):
        mots = modifier(lire_lexique())
        ecrire_lexique(mots)
        return mots


# --- Filtre après coup ----------------------------------------------------------

def _orthographe_a_garder(mot: str, texte: str, debut: int, lexique: set[str]) -> bool:
    if not mot or not _MOT.match(mot):  # chiffre, symbole, ponctuation ou texte vide
        return False
    lettres = re.sub(r"[^\w]|_", "", mot)
    if len(lettres) <= 3 or mot.lower() in UNITES or mot.lower() in lexique:
        return False
    if re.search(r"[a-zà-ÿ][A-ZÀ-Ý]", mot) or (mot.isupper() and len(lettres) >= 2):
        return False  # formule ou sigle
    if mot[0].isupper():
        avant = texte[:debut].rstrip()
        if not avant or avant[-1] not in _FIN_PHRASE:
            return False  # nom propre (milieu de phrase, page titre sans point)
    return True


def garder(faute, texte: str, seg: Segmentation, lexique: set[str]) -> bool:
    if any(faute.debut < f and d < faute.fin for d, f in seg.lignes_markup):
        return False
    if faute.regle in REGLES_ORTHOGRAPHE:
        return _orthographe_a_garder(faute.texte, texte, faute.debut, lexique)
    return bool(faute.texte.strip())


def fautes_prose(texte: str, seg: Segmentation | None = None, client=None) -> list:
    """Fautes de la prose seulement : LanguageTool sur les phrases, puis filtre."""
    seg = seg or segmenter(texte)
    brutes = languagetool.verifier(
        texte, client=client, parties=seg.parties,
        regles_off=",".join(REGLES_DESACTIVEES), categories_off=",".join(CATEGORIES_DESACTIVEES),
    )
    lexique = lire_lexique()
    return [f for f in brutes if garder(f, texte, seg, lexique)]
