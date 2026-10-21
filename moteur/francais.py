"""API de la correction du français : extraction du PDF, fautes, décisions, barème.

`/analyser` est sans état (PDF reçu, rien conservé). Pour un rapport rangé dans la
bibliothèque, l'analyse et les décisions de Guillaume (accepter/refuser, correction
choisie) sont enregistrées dans `francais.json` à côté de `rapport.pdf`; le barème
est par cours (`<cours>/bareme.json`).
"""

import hashlib
import tempfile
from dataclasses import asdict
from pathlib import Path
from typing import Literal

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, ValidationError

from . import francais_claude, francais_filtre, languagetool, pdf_texte, stockage
from .anonymat import Anonymiseur
from .bareme import Bareme, penalite
from .bibliotheque import chemin_rapport, racine, segment_sur

router = APIRouter(prefix="/api/francais")


class DemandeBareme(BaseModel):
    nb_fautes: int
    bareme: Bareme = Bareme()


@router.post("/bareme")
def calculer_bareme(d: DemandeBareme) -> dict:
    return {"nb_fautes": d.nb_fautes, "penalite": penalite(d.nb_fautes, d.bareme)}


def analyser_fichier(chemin: Path, avec_claude: bool = False, anonymiseur=None) -> tuple[pdf_texte.TexteExtrait, list[dict], dict | None]:
    """Texte extrait, fautes (avec `zones` à surligner) et erreur de la passe Claude, ou HTTPException.

    Avec `avec_claude`, la passe Claude s'ajoute à LanguageTool; si elle échoue, les fautes
    LanguageTool restent et l'erreur ({code, message}) est rendue à part."""
    try:
        extrait = pdf_texte.extraire(chemin)
    except pdf_texte.PdfSansTexte as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(400, f"PDF illisible : {e}")
    try:
        seg = francais_filtre.segmenter(extrait.texte)
        fautes = francais_filtre.fautes_prose(extrait.texte, seg)
    except languagetool.LanguageToolIndisponible as e:
        raise HTTPException(503, str(e))
    liste = [{**asdict(f), "source": "languagetool"} for f in fautes]
    erreur = None
    if avec_claude:
        ajoutees, erreur = francais_claude.passe(extrait.texte, liste, anonymiseur, seg)
        liste = sorted(liste + ajoutees, key=lambda f: (f["debut"], f["fin"]))
    ids = attribuer_ids(liste)
    return extrait, [{"id": i, **f, "zones": extrait.zones(f["debut"], f["fin"])} for i, f in zip(ids, liste)], erreur


# --- Ids stables des fautes -----------------------------------------------------

def id_faute(debut: int, fin: int, texte: str) -> str:
    """Id d'une faute : empreinte de sa position et de son texte, donc le même d'une analyse à l'autre
    (un id par rang glissait quand une réanalyse ajoutait une faute avant les autres : audit C1)."""
    return f"{debut}-{fin}-{hashlib.sha1(texte.encode('utf-8')).hexdigest()[:6]}"


def attribuer_ids(fautes: list[dict]) -> list[str]:
    """Un id unique par faute (suffixe `-2`, `-3`… si deux fautes ont exactement la même empreinte)."""
    vus: dict[str, int] = {}
    ids = []
    for f in fautes:
        base = id_faute(f["debut"], f["fin"], f["texte"])
        vus[base] = vus.get(base, 0) + 1
        ids.append(base if vus[base] == 1 else f"{base}-{vus[base]}")
    return ids


@router.post("/analyser")
async def analyser(
    pdf: UploadFile = File(...),
    points_par_faute: float = Form(0.5),
    plafond: float | None = Form(None),
) -> dict:
    """Texte, fautes (avec zones à surligner) et pénalité si toutes sont acceptées."""
    contenu = await pdf.read()
    with tempfile.TemporaryDirectory() as d:
        chemin = Path(d) / "rapport.pdf"
        chemin.write_bytes(contenu)
        extrait, fautes, _ = analyser_fichier(chemin)
    bareme = Bareme(points_par_faute=points_par_faute, plafond=plafond)
    return {
        "texte": extrait.texte,
        "pages": [asdict(p) for p in extrait.pages],
        "fautes": fautes,
        "penalite_si_toutes_acceptees": penalite(len(fautes), bareme),
    }


# --- Barème par cours -------------------------------------------------------

def fichier_bareme(cours: str) -> Path:
    dossier = racine() / segment_sur(cours, "cours")
    if not dossier.is_dir():
        raise HTTPException(404, f"Cours inconnu : {cours}.")
    return dossier / "bareme.json"


def lire_bareme(cours: str) -> Bareme:
    f = fichier_bareme(cours)
    donnees = stockage.lire_json(f)
    try:
        return Bareme.model_validate(donnees) if donnees is not None else Bareme()
    except ValidationError as e:
        stockage.journal.warning("Barème illisible dans %s : %s", f, e)
        return Bareme()


@router.get("/bareme/{cours}")
def obtenir_bareme(cours: str) -> Bareme:
    return lire_bareme(cours)


@router.put("/bareme/{cours}")
def regler_bareme(cours: str, bareme: Bareme) -> Bareme:
    ecrire(fichier_bareme(cours), bareme.model_dump())
    return bareme


# --- Rapport rangé : analyse et décisions enregistrées ------------------------

class Decisions(BaseModel):
    """État complet (PUT). `revision` = celle du `francais.json` lu par le lecteur : périmée = 409."""
    revision: int
    decisions: dict[str, Literal["acceptee", "refusee"]] = {}  # id de faute -> décision; absent = à trancher
    choix: dict[str, str] = {}  # id de faute -> correction écrite (par défaut : 1re suggestion)
    masquees: list[str] = []  # fautes dont la correction manuscrite est effacée (surlignage seul)
    decalages: dict[str, tuple[float, float]] = {}  # id de faute -> déplacement (dx, dy) de la correction, en points PDF


class ChangementFaute(BaseModel):
    """Changement d'une seule faute (PATCH) : seuls les champs fournis sont touchés.

    `decision`, `choix` et `decalage` à null = retour à l'état d'origine (à trancher, 1re suggestion, en place)."""
    decision: Literal["acceptee", "refusee"] | None = None
    choix: str | None = None
    masquee: bool = False
    decalage: tuple[float, float] | None = None


class Changements(BaseModel):
    fautes: dict[str, ChangementFaute]


def ecrire(fichier: Path, contenu: dict) -> None:
    stockage.ecrire_json(fichier, contenu, separators=(",", ":"))


def _migrer(doc: dict) -> dict:
    """Anciens `francais.json` (id = rang entier, sans révision) -> ids stables et `revision` 0.

    Faite à chaque lecture, sans réécrire le fichier : décisions, choix, masquées et décalages sont
    conservés sous leur nouvel id, et la même opération donne toujours les mêmes ids."""
    fautes = doc["fautes"]
    if all(isinstance(f.get("id"), str) for f in fautes):
        doc.setdefault("revision", 0)
        return doc
    nouveaux = attribuer_ids(fautes)
    renom = {str(f["id"]): n for f, n in zip(fautes, nouveaux)}
    doc["fautes"] = [{**f, "id": n} for f, n in zip(fautes, nouveaux)]
    doc["decisions"] = {renom[k]: v for k, v in doc["decisions"].items() if k in renom}
    doc["choix"] = {renom[k]: v for k, v in doc["choix"].items() if k in renom}
    doc["decalages"] = {renom[k]: v for k, v in doc.get("decalages", {}).items() if k in renom}
    doc["masquees"] = [renom[str(m)] for m in doc["masquees"] if str(m) in renom]
    doc["version"] = 2
    doc.setdefault("revision", 0)
    return doc


def _lire_analyse(f: Path) -> dict | None:
    """`francais.json` valide et migré, ou None s'il est absent ou abîmé (le rapport est alors à réanalyser)."""
    doc = stockage.lire_json(f)
    if isinstance(doc, dict) and isinstance(doc.get("fautes"), list) and all(k in doc for k in ("decisions", "choix", "masquees")):
        return _migrer(doc)
    if doc is not None:
        stockage.journal.warning("Analyse de français inutilisable dans %s : réanalyse nécessaire.", f)
    return None


def fichiers_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> tuple[Path, Path]:
    rapport = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not rapport.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return rapport, rapport.with_name("francais.json")


def etat(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    _, f = fichiers_rapport(cours, groupe, lab, etudiant)
    bareme = lire_bareme(cours)
    doc = _lire_analyse(f)
    if doc is None:
        return {"analyse": False, "revision": 0, "fautes": [], "decisions": {}, "choix": {}, "masquees": [],
                "decalages": {}, "nb_acceptees": 0, "penalite": 0.0, "bareme": bareme.model_dump()}
    nb = sum(1 for d in doc["decisions"].values() if d == "acceptee")
    doc.setdefault("decalages", {})  # analyses faites avant l'ajout des décalages
    return {"analyse": True, **doc, "nb_acceptees": nb, "penalite": penalite(nb, bareme),
            "bareme": bareme.model_dump()}


@router.get("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def obtenir(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    return etat(cours, groupe, lab, etudiant)


@router.post("/rapport/{cours}/{groupe}/{lab}/{etudiant}/analyser")
def analyser_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    """Analyse le rapport rangé. Une nouvelle analyse garde les décisions des fautes inchangées."""
    rapport, f = fichiers_rapport(cours, groupe, lab, etudiant)
    extrait, fautes, erreur = analyser_fichier(rapport, avec_claude=True,
                                              anonymiseur=Anonymiseur.pour(cours, groupe, etudiant))
    with stockage.verrou(f.parent):  # l'analyse (longue) est finie : fusion et écriture sans interruption
        ancien = _lire_analyse(f)
        nouveau = _fusionner(fautes, erreur, ancien)
        ecrire(f, nouveau)
    return etat(cours, groupe, lab, etudiant)


def _fusionner(fautes: list[dict], erreur: str | None, ancien: dict | None) -> dict:
    """Nouveau `francais.json` : garde les décisions des fautes inchangées et, si Claude a échoué, ses anciennes fautes.

    Les ids sont des empreintes (position + texte) : une faute inchangée garde son id, donc ses décisions,
    et un lecteur resté ouvert avec d'anciens ids ne peut pas les réattribuer à une autre faute."""
    if erreur and ancien:
        # Claude indisponible : on garde les fautes de Claude déjà trouvées (et leurs décisions).
        deja = [(x["debut"], x["fin"]) for x in fautes]
        reprises = [x for x in ancien["fautes"] if x.get("source") == "claude"
                    and not any(x["debut"] < b and a < x["fin"] for a, b in deja)]
        if reprises:
            fautes = sorted(fautes + reprises, key=lambda x: (x["debut"], x["fin"]))
    nouveau = {"version": 2, "revision": (ancien["revision"] + 1) if ancien else 1,
               "fautes": fautes, "decisions": {}, "choix": {}, "masquees": [],
               "decalages": {}, "claude": {"ok": erreur is None, "erreur": erreur,
                          "ajoutees": sum(1 for x in fautes if x.get("source") == "claude")}}
    if ancien:
        ids = {x["id"] for x in fautes}
        nouveau["decisions"] = {k: v for k, v in ancien["decisions"].items() if k in ids}
        nouveau["choix"] = {k: v for k, v in ancien["choix"].items() if k in ids}
        nouveau["decalages"] = {k: v for k, v in ancien.get("decalages", {}).items() if k in ids}
        nouveau["masquees"] = [m for m in ancien["masquees"] if m in ids]
    return nouveau


@router.put("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def enregistrer_decisions(cours: str, groupe: str, lab: str, etudiant: str, d: Decisions) -> dict:
    """Remplace tout l'état. Refusé (409) si le lecteur est resté sur une révision périmée : un autre appareil
    ou une réanalyse a modifié le rapport entre-temps. Préférer le PATCH (une faute à la fois)."""
    _, f = fichiers_rapport(cours, groupe, lab, etudiant)
    with stockage.verrou(f.parent):
        doc = _lire_analyse(f)
        if doc is None:
            raise HTTPException(409, "Rapport pas encore analysé.")
        if d.revision != doc["revision"]:
            raise HTTPException(409, "Les décisions ont changé depuis le chargement (autre appareil ou nouvelle "
                                     "analyse) : l'état à jour doit être rechargé.")
        ids = {x["id"] for x in doc["fautes"]}
        if not (set(d.decisions) | set(d.choix) | set(d.decalages) | set(d.masquees)) <= ids:
            raise HTTPException(422, "Faute inconnue.")
        doc.update(d.model_dump(exclude={"revision"}))
        doc["revision"] += 1
        ecrire(f, doc)
    return etat(cours, groupe, lab, etudiant)


@router.patch("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def modifier_decisions(cours: str, groupe: str, lab: str, etudiant: str, c: Changements) -> dict:
    """Applique les changements de quelques fautes, sans toucher aux autres : deux appareils qui décident
    sur des fautes différentes ne s'écrasent pas. Une faute qui n'existe plus (rapport réanalysé) = 409."""
    _, f = fichiers_rapport(cours, groupe, lab, etudiant)
    with stockage.verrou(f.parent):
        doc = _lire_analyse(f)
        if doc is None:
            raise HTTPException(409, "Rapport pas encore analysé.")
        ids = {x["id"] for x in doc["fautes"]}
        if not set(c.fautes) <= ids:
            raise HTTPException(409, "Une faute n'existe plus : le rapport a été réanalysé. L'état à jour doit être rechargé.")
        doc.setdefault("decalages", {})
        for fid, ch in c.fautes.items():
            donnees = ch.model_dump()
            for champ in ch.model_fields_set:
                valeur = donnees[champ]
                if champ == "masquee":
                    doc["masquees"] = [m for m in doc["masquees"] if m != fid] + ([fid] if valeur else [])
                    continue
                cible = doc[{"decision": "decisions", "choix": "choix", "decalage": "decalages"}[champ]]
                if valeur is None:
                    cible.pop(fid, None)
                else:
                    cible[fid] = valeur
        doc["revision"] += 1
        ecrire(f, doc)
    return etat(cours, groupe, lab, etudiant)


# --- Lexique global (mots d'orthographe à ignorer) ------------------------------

class MotLexique(BaseModel):
    mot: str


@router.get("/lexique")
def obtenir_lexique() -> dict:
    return {"mots": sorted(francais_filtre.lire_lexique())}


@router.post("/lexique")
def ajouter_au_lexique(m: MotLexique) -> dict:
    """Ajoute un mot : ignoré par les prochaines analyses, de tous les cours."""
    mot = m.mot.strip().lower()
    if not mot or len(mot) > 60 or any(c.isspace() for c in mot):
        raise HTTPException(422, "Un seul mot, sans espace.")
    mots = francais_filtre.modifier_lexique(lambda m: m | {mot})
    return {"mots": sorted(mots)}


@router.delete("/lexique/{mot}")
def retirer_du_lexique(mot: str) -> dict:
    mots = francais_filtre.modifier_lexique(lambda m: m - {mot.strip().lower()})
    return {"mots": sorted(mots)}
