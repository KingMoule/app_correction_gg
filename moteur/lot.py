"""Analyse par lot : français, indices d'IA et références pour plusieurs rapports d'un lab.

Un lot traite au plus `n` rapports (10 par défaut : environ 2 % de la session de 5 h par
rapport avec Sonnet pour le français et l'IA; les références s'y ajoutent) qui n'ont pas encore été analysés, un à la fois, en arrière-plan.
Il s'arrête proprement sur une limite d'usage (429) ou si Claude / LanguageTool est
indisponible : ce qui est déjà obtenu reste enregistré. Il réutilise les analyses d'un
seul rapport (`francais.analyser_rapport`, `indices_ia.analyser`), donc les décisions
accepter/refuser et les analyses existantes ne sont jamais écrasées, sauf avec
`refaire` (les décisions des fautes inchangées sont alors gardées).
"""

import json
import threading

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from . import bibliotheque, consommation, francais, indices_ia, references, stockage

router = APIRouter(prefix="/api/lot")

N_DEFAUT = 10
N_MAX = 200

_verrou = threading.Lock()
_arret = threading.Event()
_etat: dict = {"statut": "inactif"}


class DemandeLot(BaseModel):
    n: int = Field(N_DEFAUT, ge=1, le=N_MAX)
    refaire: bool = False  # refaire aussi les rapports déjà analysés


class DemandeLotLab(DemandeLot):
    groupe: str | None = None  # un seul groupe du cours (absent = tous les groupes)


def _dossier_lab(cours: str, groupe: str, lab: str):
    return bibliotheque.dossier_groupe(cours, groupe) / bibliotheque.segment_sur(lab, "lab")


def _rapports(cours: str, groupe: str, lab: str) -> list[str]:
    dossier = _dossier_lab(cours, groupe, lab)
    if not dossier.is_dir():
        raise HTTPException(404, "Lab introuvable.")
    return sorted(p.parent.name for p in dossier.glob("*/rapport.pdf"))


def a_faire(cours: str, groupe: str, lab: str, etudiant: str, refaire: bool = False) -> tuple[bool, bool, bool]:
    """(français, indices d'IA, références) à faire. La passe Claude du français et celle des
    références sont à refaire si elles avaient échoué (ex. limite d'usage atteinte en plein lot)."""
    if refaire:
        return True, True, True
    dossier = _dossier_lab(cours, groupe, lab) / etudiant
    fr = dossier / "francais.json"
    doc = stockage.lire_json(fr)
    fr_ok = isinstance(doc, dict) and bool(doc.get("claude", {}).get("ok", False))
    ref = stockage.lire_json(dossier / "references.json")
    ref_ok = isinstance(ref, dict) and bool((ref.get("claude") or {}).get("ok", False))
    return not fr_ok, not (dossier / "indices_ia.json").is_file(), not ref_ok


Choix = tuple[str, str, bool, bool, bool]  # (groupe, étudiant, français, IA, références)


def _selection(cours: str, groupe: str, lab: str, refaire: bool) -> list[Choix]:
    sortie = []
    for e in _rapports(cours, groupe, lab):
        faire = a_faire(cours, groupe, lab, e, refaire)
        if any(faire):
            sortie.append((groupe, e, *faire))
    return sortie


def _selection_lab(cours: str, lab: str, groupe: str | None, refaire: bool) -> tuple[int, list[Choix]]:
    """(rapports du lab, rapports à analyser) pour tous les groupes du cours (ou un seul), dans l'ordre
    de « Corriger le suivant » : ordre du suivi (groupe, puis nom), en commençant par le prochain rapport non
    terminé et en reprenant du début ensuite, pour que les prochains rapports à corriger soient analysés d'abord."""
    bibliotheque.segment_sur(lab, "lab")
    classes = [c for c in bibliotheque.classes_du_cours(cours) if not groupe or c["groupe"] == groupe]
    if not classes:
        raise HTTPException(404, f"Aucune liste de classe pour {cours}" + (f" groupe {groupe}." if groupe else "."))
    rapports = []  # (groupe, nom normalisé, prénom normalisé, id, terminé)
    for c in classes:
        for e in c["etudiants"]:
            dossier = bibliotheque.chemin_rapport(cours, c["groupe"], lab, e["id"]).parent
            if (dossier / "rapport.pdf").is_file():
                rapports.append((c["groupe"], bibliotheque.normaliser(e["nom"]), bibliotheque.normaliser(e["prenom"]),
                                 e["id"], bibliotheque._termine(dossier)))
    rapports.sort(key=lambda r: r[:3])
    debut = next((i for i, r in enumerate(rapports) if not r[4]), 0)
    choisis = []
    for g, _, _, e, _ in rapports[debut:] + rapports[:debut]:
        faire = a_faire(cours, g, lab, e, refaire)
        if any(faire):
            choisis.append((g, e, *faire))
    return len(rapports), choisis


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


def _executer(cours: str, lab: str, choisis: list[Choix]) -> None:
    noms = {g: _noms(cours, g) for g in {c[0] for c in choisis}}
    arret = None
    for groupe, e, fr, ia, ref in choisis:
        if _arret.is_set():
            arret = ("arrete", "Lot arrêté à ta demande : les résultats déjà obtenus sont gardés.")
            break
        _maj(courant=noms[groupe].get(e, e), groupe_courant=groupe)
        erreur = None  # (code, message) du rapport
        try:
            if fr:
                r = francais.analyser_rapport(cours, groupe, lab, e)
                c = (r.get("claude") or {}).get("erreur")
                if c:
                    erreur = (c["code"], c["message"])
            if ia and not (erreur and _arreter_sur(*erreur)):
                indices_ia.analyser(cours, groupe, lab, e)
            if ref and not (erreur and _arreter_sur(*erreur)):
                c = (references.analyser_rapport(cours, groupe, lab, e).get("claude") or {}).get("erreur")
                if c:
                    erreur = (c["code"], c["message"])
        except HTTPException as x:
            erreur = (x.status_code, str(x.detail))
        except Exception as x:  # noqa: BLE001 : un rapport en échec n'arrête pas le lot
            erreur = (500, f"Erreur inattendue : {x}")
        if erreur:
            msg = _arreter_sur(*erreur)
            with _verrou:
                _etat["erreurs"].append({"groupe": groupe, "etudiant": e, "nom": noms[groupe].get(e, e), "code": erreur[0], "message": erreur[1]})
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


def _flags(choisis: list[Choix]) -> list[tuple]:
    return [c[1:] for c in choisis]  # `consommation.estimer` attend (étudiant, français, IA, références)


@router.get("/apercu/{cours}/{groupe}/{lab}")
def apercu(cours: str, groupe: str, lab: str, refaire: bool = False, n: int = Query(N_DEFAUT, ge=1, le=N_MAX)) -> dict:
    """Combien de rapports du lab seraient traités (sans rien lancer) et ce qu'un lot de `n` coûterait
    (estimation : `consommation.estimer`, aucune donnée envoyée)."""
    choisis = _selection(cours, groupe, lab, refaire)
    return {"total": len(_rapports(cours, groupe, lab)), "a_analyser": len(choisis),
            "estimation": consommation.estimer(_flags(choisis[:n]))}


@router.get("/apercu/{cours}/{lab}")
def apercu_lab(cours: str, lab: str, groupe: str | None = None, refaire: bool = False,
               n: int = Query(N_DEFAUT, ge=1, le=N_MAX)) -> dict:
    """Même chose pour tout le lab (tous les groupes du cours, ou `groupe`), dans l'ordre de correction."""
    total, choisis = _selection_lab(cours, lab, groupe, refaire)
    return {"total": total, "a_analyser": len(choisis), "estimation": consommation.estimer(_flags(choisis[:n]))}


def _demarrer(cours: str, groupe: str | None, lab: str, choisis: list[Choix], refaire: bool) -> dict:
    with _verrou:
        if _etat["statut"] == "en_cours":
            raise HTTPException(409, "Un lot est déjà en cours.")
        _arret.clear()
        _etat.clear()
        _etat.update(statut="en_cours", cours=cours, groupe=groupe, lab=lab, total=len(choisis), fait=0,
                     courant=None, erreurs=[], message="", refaire=refaire)
    threading.Thread(target=_executer, args=(cours, lab, choisis), daemon=True, name="lot").start()
    return etat()


@router.post("/{cours}/{groupe}/{lab}")
def lancer(cours: str, groupe: str, lab: str, d: DemandeLot = DemandeLot()) -> dict:
    choisis = _selection(cours, groupe, lab, d.refaire)[: d.n]
    if not choisis:
        raise HTTPException(409, "Aucun rapport à analyser dans ce lab.")
    return _demarrer(cours, groupe, lab, choisis, d.refaire)


@router.post("/{cours}/{lab}")
def lancer_lab(cours: str, lab: str, d: DemandeLotLab = DemandeLotLab()) -> dict:
    """Lot pour tout le lab : les `n` premiers rapports à analyser dans l'ordre de correction (groupes confondus).
    `groupe` dans le corps limite à un groupe. `groupe` de la réponse (`GET /api/lot`) est null pour tous les groupes."""
    choisis = _selection_lab(cours, lab, d.groupe, d.refaire)[1][: d.n]
    if not choisis:
        raise HTTPException(409, "Aucun rapport à analyser dans ce lab.")
    return _demarrer(cours, d.groupe, lab, choisis, d.refaire)


@router.post("/{cours}/{groupe}/{lab}/{etudiant}")
def lancer_un(cours: str, groupe: str, lab: str, etudiant: str) -> dict:
    """Analyse un seul rapport (ce qui lui manque), avec la même progression que le lot (`GET /api/lot`)."""
    if etudiant not in _rapports(cours, groupe, lab):
        raise HTTPException(404, "Rapport introuvable.")
    faire = a_faire(cours, groupe, lab, etudiant)
    if not any(faire):
        raise HTTPException(409, "Ce rapport est déjà analysé.")
    return _demarrer(cours, groupe, lab, [(groupe, etudiant, *faire)], False)


@router.get("")
def etat() -> dict:
    with _verrou:
        return json.loads(json.dumps(_etat))


@router.post("/arreter")
def arreter() -> dict:
    """Arrête après le rapport en cours."""
    _arret.set()
    return etat()
