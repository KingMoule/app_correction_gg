"""Analyse par lot : passe Claude sur le français et indices d'IA pour plusieurs rapports d'un lab.

Un lot traite au plus `n` rapports (10 par défaut : environ 2 % de la session de 5 h par
rapport avec Sonnet) qui n'ont pas encore été analysés, un à la fois, en arrière-plan.
Il s'arrête proprement sur une limite d'usage (429) ou si Claude / LanguageTool est
indisponible : ce qui est déjà obtenu reste enregistré. Il réutilise les analyses d'un
seul rapport (`francais.analyser_rapport`, `indices_ia.analyser`), donc les décisions
accepter/refuser et les analyses existantes ne sont jamais écrasées, sauf avec
`refaire` (les décisions des fautes inchangées sont alors gardées).
"""

import json
import threading

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from . import bibliotheque, francais, indices_ia

router = APIRouter(prefix="/api/lot")

N_DEFAUT = 10
N_MAX = 200

_verrou = threading.Lock()
_arret = threading.Event()
_etat: dict = {"statut": "inactif"}


class DemandeLot(BaseModel):
    n: int = Field(N_DEFAUT, ge=1, le=N_MAX)
    refaire: bool = False  # refaire aussi les rapports déjà analysés


def _dossier_lab(cours: str, groupe: str, lab: str):
    return bibliotheque.dossier_groupe(cours, groupe) / bibliotheque.segment_sur(lab, "lab")


def _rapports(cours: str, groupe: str, lab: str) -> list[str]:
    dossier = _dossier_lab(cours, groupe, lab)
    if not dossier.is_dir():
        raise HTTPException(404, "Lab introuvable.")
    return sorted(p.parent.name for p in dossier.glob("*/rapport.pdf"))


def a_faire(cours: str, groupe: str, lab: str, etudiant: str, refaire: bool = False) -> tuple[bool, bool]:
    """(français à faire, indices d'IA à faire). La passe Claude du français est à refaire
    si elle avait échoué (ex. limite d'usage atteinte en plein lot)."""
    if refaire:
        return True, True
    dossier = _dossier_lab(cours, groupe, lab) / etudiant
    fr = dossier / "francais.json"
    try:
        fr_ok = fr.is_file() and json.loads(fr.read_text(encoding="utf-8")).get("claude", {}).get("ok", False)
    except (OSError, ValueError):
        fr_ok = False
    return not fr_ok, not (dossier / "indices_ia.json").is_file()


def _selection(cours: str, groupe: str, lab: str, refaire: bool) -> list[tuple[str, bool, bool]]:
    sortie = []
    for e in _rapports(cours, groupe, lab):
        fr, ia = a_faire(cours, groupe, lab, e, refaire)
        if fr or ia:
            sortie.append((e, fr, ia))
    return sortie


def _noms(cours: str, groupe: str) -> dict[str, str]:
    try:
        classe = bibliotheque.charger_classe(cours, groupe)
    except HTTPException:
        return {}
    return {e["id"]: f"{e['prenom']} {e['nom']}" for e in classe["etudiants"]}


def _arreter_sur(code: int, detail: str) -> str | None:
    """Message d'arrêt du lot pour une erreur qui rendrait les suivantes inutiles, sinon None."""
    if code == 429:
        return "Limite d'usage atteinte : les résultats déjà obtenus sont gardés. Reprendre le lot après la réinitialisation de la limite."
    if code == 503:
        return f"Lot arrêté : {detail}"
    return None


def _executer(cours: str, groupe: str, lab: str, choisis: list[tuple[str, bool, bool]]) -> None:
    noms = _noms(cours, groupe)
    arret = None
    for e, fr, ia in choisis:
        if _arret.is_set():
            arret = ("arrete", "Lot arrêté à ta demande : les résultats déjà obtenus sont gardés.")
            break
        _maj(courant=noms.get(e, e))
        erreur = None  # (code, message) du rapport
        try:
            if fr:
                r = francais.analyser_rapport(cours, groupe, lab, e)
                c = (r.get("claude") or {}).get("erreur")
                if c:
                    erreur = (c["code"], c["message"])
            if ia and not (erreur and _arreter_sur(*erreur)):
                indices_ia.analyser(cours, groupe, lab, e)
        except HTTPException as x:
            erreur = (x.status_code, str(x.detail))
        except Exception as x:  # noqa: BLE001 : un rapport en échec n'arrête pas le lot
            erreur = (500, f"Erreur inattendue : {x}")
        if erreur:
            msg = _arreter_sur(*erreur)
            with _verrou:
                _etat["erreurs"].append({"etudiant": e, "nom": noms.get(e, e), "code": erreur[0], "message": erreur[1]})
            if msg:
                arret = ("limite" if erreur[0] == 429 else "erreur", msg)
                break
        else:
            _maj(fait=_etat["fait"] + 1)
    with _verrou:
        _etat["courant"] = None
        statut, message = arret or ("termine", "Lot terminé.")
        if statut == "termine" and _etat["erreurs"]:
            message = f"Lot terminé avec {len(_etat['erreurs'])} rapport(s) en erreur."
        _etat["statut"], _etat["message"] = statut, message


def _maj(**champs) -> None:
    with _verrou:
        _etat.update(champs)


@router.get("/apercu/{cours}/{groupe}/{lab}")
def apercu(cours: str, groupe: str, lab: str, refaire: bool = False) -> dict:
    """Combien de rapports du lab seraient traités (sans rien lancer)."""
    return {"total": len(_rapports(cours, groupe, lab)), "a_analyser": len(_selection(cours, groupe, lab, refaire))}


def _demarrer(cours: str, groupe: str, lab: str, choisis: list[tuple[str, bool, bool]], refaire: bool) -> dict:
    with _verrou:
        if _etat["statut"] == "en_cours":
            raise HTTPException(409, "Un lot est déjà en cours.")
        _arret.clear()
        _etat.clear()
        _etat.update(statut="en_cours", cours=cours, groupe=groupe, lab=lab, total=len(choisis), fait=0,
                     courant=None, erreurs=[], message="", refaire=refaire)
    threading.Thread(target=_executer, args=(cours, groupe, lab, choisis), daemon=True, name="lot").start()
    return etat()


@router.post("/{cours}/{groupe}/{lab}")
def lancer(cours: str, groupe: str, lab: str, d: DemandeLot = DemandeLot()) -> dict:
    choisis = _selection(cours, groupe, lab, d.refaire)[: d.n]
    if not choisis:
        raise HTTPException(409, "Aucun rapport à analyser dans ce lab.")
    return _demarrer(cours, groupe, lab, choisis, d.refaire)


@router.post("/{cours}/{groupe}/{lab}/{etudiant}")
def lancer_un(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    """Analyse un seul rapport (ce qui lui manque), avec la même progression que le lot (`GET /api/lot`)."""
    if etudiant not in _rapports(cours, groupe, lab):
        raise HTTPException(404, "Rapport introuvable.")
    fr, ia = a_faire(cours, groupe, lab, etudiant)
    if not (fr or ia):
        raise HTTPException(409, "Ce rapport est déjà analysé.")
    return _demarrer(cours, groupe, lab, [(etudiant, fr, ia)], False)


@router.get("")
def etat() -> dict:
    with _verrou:
        return json.loads(json.dumps(_etat))


@router.post("/arreter")
def arreter() -> dict:
    """Arrête après le rapport en cours."""
    _arret.set()
    return etat()
