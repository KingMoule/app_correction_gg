"""Double remise d'une équipe : les deux coéquipiers ont chacun remis le rapport d'un même lab.

D'habitude un seul des deux remet et `equipe.json` rattache l'autre. Quand les deux remettent, rien ne
le disait : le suivi comptait deux rapports, le plagiat ignorait la paire (même équipe). Ici :
- **détection** : à l'import (`bibliotheque.trouver_double`, la seconde copie va dans « À trancher » avec la
  raison `double_remise`) et sur les labs déjà importés (`doubles_du_lab`, bannière de la page du lab);
- **comparaison** côte à côte des deux copies (déposant, date de remise lue dans le nom du fichier LÉA, pages,
  travail déjà fait) pour que Guillaume ne perde pas de travail sans le savoir;
- **choix** : garder l'une, l'autre ou les deux. Aucune présélection. La copie non gardée est **déplacée** avec tout
  son dossier (`_remplaces/`, avec `double_remise.json`) ou, si elle attendait encore, dans `_ecartes/`; jamais
  supprimée, et seulement après `confirmer: true`. Le coéquipier dont la copie est mise de côté reste rattaché
  dans `equipe.json` de la copie gardée (suivi, non remis, export LÉA). « Garder les deux » retire le lien d'équipe.
"""

import io
import re
from datetime import datetime

from fastapi import APIRouter, HTTPException
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader

from . import bibliotheque, stockage
from .bibliotheque import chemin_rapport, membres_equipe, racine, segment_sur

router = APIRouter(prefix="/api/bibliotheque")

REMIS_LE = re.compile(r"Remis[ _]le[ _](\d{4}-\d{2}-\d{2})[ _](\d{2})h(\d{2})m(\d{2})s", re.I)
CHAMPS = ("groupe", "id", "nom", "prenom")


def date_de_remise(nom_fichier: str | None) -> str | None:
    """Date ISO lue dans « …_Remis_le_2026-09-18_17h43m16s », sinon None."""
    m = REMIS_LE.search(nom_fichier or "")
    if not m:
        return None
    try:
        return datetime.fromisoformat(f"{m[1]}T{m[2]}:{m[3]}:{m[4]}").isoformat()
    except ValueError:
        return None


def _etudiant(cours: str, groupe: str, ident: str) -> dict:
    e = next((x for x in bibliotheque.etudiants_du_cours(cours) if (x["groupe"], x["id"]) == (groupe, ident)), None)
    if not e:
        raise HTTPException(404, "Étudiant absent de la liste de classe.")
    return {k: e[k] for k in CHAMPS}


def _pages(contenu: bytes) -> int | None:
    try:
        return len(PdfReader(io.BytesIO(contenu)).pages)
    except Exception:
        return None


def _travail(dossier) -> dict:
    """Ce que la copie a déjà : traits, analyses, note. Relit les petits JSON; jamais le PDF."""
    annotations = stockage.lire_json(dossier / "annotations.json", {})
    pages = annotations.get("pages") if isinstance(annotations, dict) else None
    traits = sum(len(v) for v in pages.values() if isinstance(v, list)) if isinstance(pages, dict) else 0
    francais = stockage.lire_json(dossier / "francais.json")
    if isinstance(francais, dict):
        decisions = francais.get("decisions") if isinstance(francais.get("decisions"), dict) else {}
        fr = {"fautes": len(francais.get("fautes") or []),
              "acceptees": sum(1 for d in decisions.values() if d == "acceptee")}
    else:
        fr = None
    ia = stockage.lire_json(dossier / "indices_ia.json")
    statut = stockage.lire_json(dossier / "statut.json", {})
    statut = statut if isinstance(statut, dict) else {}
    travail = {"traits": traits, "francais": fr,
               "ia": (ia.get("force") or "analysé") if isinstance(ia, dict) else None,
               "references": isinstance(stockage.lire_json(dossier / "references.json"), dict),
               "comparaison": isinstance(stockage.lire_json(dossier / "comparaison_style.json"), dict),
               "termine": bool(statut.get("termine")), "note": bibliotheque.lire_note(dossier)}
    travail["vide"] = not (traits or fr or travail["ia"] or travail["references"] or travail["comparaison"]
                           or travail["termine"] or travail["note"])
    return travail


def _copie_rangee(cours: str, lab: str, groupe: str, ident: str) -> dict:
    dossier = chemin_rapport(cours, groupe, lab, ident).parent
    pdf = dossier / "rapport.pdf"
    if not pdf.is_file():
        raise HTTPException(404, "Rapport introuvable : la double remise n'existe plus.")
    fichier = (stockage.lire_json(dossier / "origine.json", {}) or {}).get("fichier")
    return {"source": "rangee", **_etudiant(cours, groupe, ident), "fichier": fichier, "remis_le": date_de_remise(fichier),
            "pages": _pages(pdf.read_bytes()), "travail": _travail(dossier),
            "pdf": f"/api/bibliotheque/rapport/{cours}/{groupe}/{lab}/{ident}"}


# --- Détection sur les labs déjà importés --------------------------------------

def doubles_du_lab(cours: str, lab: str) -> list[dict]:
    """Paires de coéquipiers qui ont chacun un rapport rangé pour ce lab : {a, b, nommage}.

    `a` nomme `b` (ou l'inverse, ou les deux) dans `equipe.json`. Les paires sont triées et sans doublon."""
    deposants = {}
    for e in bibliotheque.etudiants_du_cours(cours):
        dossier = chemin_rapport(cours, e["groupe"], lab, e["id"]).parent
        if (dossier / "rapport.pdf").is_file():
            deposants[(e["groupe"], e["id"])] = (e, {(m["groupe"], m["id"]) for m in membres_equipe(dossier)})
    paires = {}
    for cle, (e, nomme) in deposants.items():
        for autre in nomme & deposants.keys() - {cle}:
            deux = tuple(sorted((cle, autre)))
            paires.setdefault(deux, set()).add(cle)
    sortie = []
    for (ka, kb), noms in sorted(paires.items()):
        a, b = deposants[ka][0], deposants[kb][0]
        sortie.append({"a": {k: a[k] for k in CHAMPS}, "b": {k: b[k] for k in CHAMPS},
                       "nommage": "mutuel" if len(noms) == 2 else "a_nomme_b" if ka in noms else "b_nomme_a"})
    return sortie


def doubles_du_cours(cours: str) -> list[dict]:
    """Toutes les doubles remises d'un cours, lab par lab (`lab` ajouté à chaque paire)."""
    labs = sorted({d.name for g in (racine() / cours).glob("*/") if g.is_dir() for d in g.iterdir()
                   if d.is_dir() and not d.name.startswith("_")})
    return [{**p, "lab": lab} for lab in labs for p in doubles_du_lab(cours, lab)]


# --- Comparaison ---------------------------------------------------------------

def _la_paire(cours: str, lab: str, ga: str, ea: str, gb: str, eb: str) -> dict:
    segment_sur(lab, "lab")
    for p in doubles_du_lab(cours, lab):
        if {(p["a"]["groupe"], p["a"]["id"]), (p["b"]["groupe"], p["b"]["id"])} == {(ga, ea), (gb, eb)}:
            return p
    raise HTTPException(404, "Ces deux étudiants n'ont plus chacun un rapport rangé qui se nomme : plus de double remise.")


@router.get("/double/{cours}/{lab}/{ga}/{ea}/{gb}/{eb}")
def comparer_rangees(cours: str, lab: str, ga: str, ea: str, gb: str, eb: str) -> dict:
    """Les deux copies d'un lab déjà importé, côte à côte."""
    p = _la_paire(cours, lab, ga, ea, gb, eb)
    return {"cours": cours, "lab": lab, "nommage": p["nommage"],
            "copies": [_copie_rangee(cours, lab, p[k]["groupe"], p[k]["id"]) for k in ("a", "b")]}


def _fiche_attente(ident: str) -> tuple[dict, object]:
    segment_sur(ident, "id")
    dossier = racine() / "_attente"
    meta = stockage.lire_json(dossier / f"{ident}.json")
    if not isinstance(meta, dict) or not (dossier / f"{ident}.pdf").is_file():
        raise HTTPException(404, "Fichier en attente introuvable.")
    if meta.get("raison") != "double_remise" or not meta.get("candidats") or not meta.get("double"):
        raise HTTPException(409, "Ce fichier n'est pas une double remise.")
    return meta, dossier


@router.get("/attente/{ident}/pdf")
def pdf_en_attente(ident: str) -> FileResponse:
    segment_sur(ident, "id")
    chemin = racine() / "_attente" / f"{ident}.pdf"
    if not chemin.is_file():
        raise HTTPException(404, "Fichier en attente introuvable.")
    return FileResponse(chemin, media_type="application/pdf")


@router.get("/attente/{ident}/double")
def comparer_attente(ident: str) -> dict:
    """La copie qui attend (la seconde) et celle déjà rangée, côte à côte."""
    meta, dossier = _fiche_attente(ident)
    cours, lab, nouveau = meta["cours"], meta["lab"], meta["candidats"][0]
    existant = meta["double"]["existant"]
    nouvelle = {"source": "attente", **{k: nouveau[k] for k in CHAMPS}, "fichier": meta.get("fichier"),
                "remis_le": date_de_remise(meta.get("fichier")), "pages": _pages((dossier / f"{ident}.pdf").read_bytes()),
                "travail": {"vide": True}, "pdf": f"/api/bibliotheque/attente/{ident}/pdf"}
    return {"cours": cours, "lab": lab, "nommage": meta["double"]["nommage"], "id": ident,
            "copies": [_copie_rangee(cours, lab, existant["groupe"], existant["id"]), nouvelle]}


# --- Choix ---------------------------------------------------------------------

class Membre(BaseModel):
    groupe: str
    id: str


class ChoixRangees(BaseModel):
    a: Membre
    b: Membre
    choix: str            # « a » ou « b » : la copie à garder; « les_deux » : deux rapports distincts
    confirmer: bool = False


class ChoixAttente(BaseModel):
    choix: str            # « existante », « nouvelle » ou « les_deux »
    confirmer: bool = False


def _ecrire_equipe(dossier, membres: list[dict], exclu: tuple[str, str]) -> None:
    """Remplace `equipe.json` (sans doublon ni le déposant); liste vide = fichier retiré."""
    vus, propres = set(), []
    for m in membres:
        cle = (m["groupe"], m["id"])
        if cle != exclu and cle not in vus:
            vus.add(cle)
            propres.append({k: m[k] for k in CHAMPS})
    with stockage.verrou(dossier):
        if propres:
            stockage.ecrire_json(dossier / "equipe.json", propres)
        elif (dossier / "equipe.json").exists():
            (dossier / "equipe.json").unlink()


def _retirer_lien(dossier, autre: tuple[str, str]) -> None:
    restant = [m for m in membres_equipe(dossier) if (m["groupe"], m["id"]) != autre]
    _ecrire_equipe(dossier, restant, ("", ""))


def _mettre_de_cote(cours: str, lab: str, copie: dict, garde: dict) -> str:
    """Déplace tout le dossier de la copie non gardée dans `_remplaces/` et y note pourquoi. Rien n'est supprimé."""
    dossier = chemin_rapport(cours, copie["groupe"], lab, copie["id"]).parent
    cible = bibliotheque.mettre_de_cote(dossier, f"{cours}_{copie['groupe']}_{lab}_{copie['id']}")
    stockage.ecrire_json(cible / "double_remise.json", {
        "raison": "double_remise", "date": datetime.now().isoformat(timespec="seconds"), "cours": cours, "lab": lab,
        "ecartee": {k: copie[k] for k in CHAMPS}, "gardee": {k: garde[k] for k in CHAMPS}})
    return cible.name


def _exiger_confirmation(confirmer: bool, phrase: str) -> None:
    if not confirmer:
        raise HTTPException(409, f"Confirmation requise : {phrase}")


def _resume_mise_de_cote(copie: dict) -> str:
    return (f"la copie de {copie['prenom']} {copie['nom']} sera mise de côté, avec tout son dossier (annotations, analyses, "
            "note), dans le dossier _remplaces (récupérable).")


@router.post("/double/{cours}/{lab}")
def choisir_rangees(cours: str, lab: str, corps: ChoixRangees) -> dict:
    """Double remise sur un lab déjà importé : garder `a`, `b` ou les deux."""
    p = _la_paire(cours, lab, corps.a.groupe, corps.a.id, corps.b.groupe, corps.b.id)
    if corps.choix not in ("a", "b", "les_deux"):
        raise HTTPException(400, "choix : a, b ou les_deux.")
    da = chemin_rapport(cours, p["a"]["groupe"], lab, p["a"]["id"]).parent
    db = chemin_rapport(cours, p["b"]["groupe"], lab, p["b"]["id"]).parent
    ka, kb = (p["a"]["groupe"], p["a"]["id"]), (p["b"]["groupe"], p["b"]["id"])
    if corps.choix == "les_deux":  # deux rapports distincts : plus de lien d'équipe pour ce lab
        _retirer_lien(da, kb)
        _retirer_lien(db, ka)
        return {"ok": True, "choix": "les_deux"}
    garde, ecarte = (p["a"], p["b"]) if corps.choix == "a" else (p["b"], p["a"])
    _exiger_confirmation(corps.confirmer, _resume_mise_de_cote(ecarte))
    d_garde = chemin_rapport(cours, garde["groupe"], lab, garde["id"]).parent
    d_ecarte = chemin_rapport(cours, ecarte["groupe"], lab, ecarte["id"]).parent
    # Le coéquipier reste rattaché (suivi, non remis, export), avec les autres membres que l'une ou l'autre copie nommait.
    _ecrire_equipe(d_garde, membres_equipe(d_garde) + [ecarte] + membres_equipe(d_ecarte), (garde["groupe"], garde["id"]))
    dossier = _mettre_de_cote(cours, lab, ecarte, garde)
    return {"ok": True, "choix": corps.choix, "mis_de_cote": dossier}


@router.post("/attente/{ident}/double")
def choisir_attente(ident: str, corps: ChoixAttente) -> dict:
    """Double remise à l'import : garder la copie déjà rangée, la nouvelle ou les deux."""
    meta, dossier_attente = _fiche_attente(ident)
    if corps.choix not in ("existante", "nouvelle", "les_deux"):
        raise HTTPException(400, "choix : existante, nouvelle ou les_deux.")
    cours, lab, nouveau = meta["cours"], meta["lab"], meta["candidats"][0]
    existant = meta["double"]["existant"]
    d_exist = chemin_rapport(cours, existant["groupe"], lab, existant["id"]).parent
    if not (d_exist / "rapport.pdf").is_file():
        raise HTTPException(409, f"La copie de {existant['prenom']} {existant['nom']} n'est plus rangée : "
                                 "ranger celle-ci normalement.")
    if (chemin_rapport(cours, nouveau["groupe"], lab, nouveau["id"]).parent / "rapport.pdf").is_file():
        raise HTTPException(409, "Cet étudiant a déjà un rapport rangé pour ce lab.")
    pdf_f, meta_f = dossier_attente / f"{ident}.pdf", dossier_attente / f"{ident}.json"
    cle_n, cle_e = (nouveau["groupe"], nouveau["id"]), (existant["groupe"], existant["id"])

    if corps.choix == "existante":
        _exiger_confirmation(corps.confirmer, f"le fichier de {nouveau['prenom']} {nouveau['nom']} sera mis de côté dans le "
                                              "dossier _ecartes (récupérable).")
        _ecrire_equipe(d_exist, membres_equipe(d_exist) + [nouveau], cle_e)
        ecartes = racine() / "_ecartes"
        ecartes.mkdir(exist_ok=True)
        pdf_f.replace(ecartes / f"{ident}.pdf")
        stockage.ecrire_json(ecartes / f"{ident}.json", meta)
        meta_f.unlink()
        return {"ok": True, "choix": "existante"}

    tous = bibliotheque.etudiants_du_cours(cours)
    contenu = pdf_f.read_bytes()
    detectes = bibliotheque.coequipiers(contenu, tous, nouveau)
    if corps.choix == "les_deux":
        bibliotheque.ranger(contenu, cours, nouveau["groupe"], lab, nouveau["id"],
                            [m for m in detectes if (m["groupe"], m["id"]) != cle_e], meta.get("fichier"))
        _retirer_lien(d_exist, cle_n)
    else:  # nouvelle : l'ancienne copie est mise de côté avec tout son dossier
        _exiger_confirmation(corps.confirmer, _resume_mise_de_cote(existant))
        ancienne = membres_equipe(d_exist)
        _mettre_de_cote(cours, lab, existant, nouveau)
        bibliotheque.ranger(contenu, cours, nouveau["groupe"], lab, nouveau["id"], None, meta.get("fichier"))
        _ecrire_equipe(chemin_rapport(cours, nouveau["groupe"], lab, nouveau["id"]).parent,
                       detectes + [existant] + ancienne, cle_n)
    pdf_f.unlink()
    meta_f.unlink()
    return {"ok": True, "choix": corps.choix}
