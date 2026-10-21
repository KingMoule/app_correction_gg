"""Plagiat : comparaison locale de tous les rapports, puis analyse par Claude des paires confirmées.

Étapes (voir docs/PLAN.md, étape 3) :
1. `POST /api/plagiat/comparer` : programme local, gratuit. Chaque rapport de la bibliothèque
   (tous cours, groupes et labs) est comparé à tous les autres. Les suites de mots communes
   sont les « passages » ; le texte de l'énoncé du lab (s'il est téléversé) est ignoré.
2. Les paires dont le score atteint le seuil réglable sont proposées à Guillaume.
3. `POST /api/plagiat/paires/{cle}/confirmer` : seulement après sa confirmation, les passages
   (noms, prénoms et DA masqués) sont envoyés à Claude, qui juge copie, paraphrase ou coïncidence.

Rangement sous `<données>/plagiat/` : reglages.json, paires.json (dernière comparaison),
decisions.json (écarter / verdict de Claude), textes/<sha1>.json (cache du texte d'un PDF).
Les énoncés sont sous `bibliotheque/<cours>/_enonces/<lab>.pdf`.
"""

from __future__ import annotations

import hashlib
import tempfile
import threading
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from . import bibliotheque, pdf_texte, stockage
from .anonymat import Anonymiseur
from .claude import ClaudeErreur, FileClaude, file_par_defaut
from .config import dossier_donnees

router = APIRouter(prefix="/api/plagiat")

# Un passage commun compte à partir de MOTS_MIN mots consécutifs identiques.
MOTS_MIN = 8
# Une suite qu'on retrouve dans plus de rapports que cela est un texte courant
# (formule, énoncé non téléversé) : on ne s'en sert pas, ce qui borne aussi le temps de calcul.
RAPPORTS_MAX_PAR_SUITE = 40
SEUIL_DEFAUT = 0.2  # fraction du rapport couverte par des passages communs
CONTEXTE_MAX = 12000  # caractères de passages envoyés à Claude par paire

SCHEMA_VERDICT = {
    "type": "object",
    "properties": {
        "verdict": {"type": "string", "enum": ["copie", "paraphrase", "coincidence"]},
        "confiance": {"type": "string", "enum": ["faible", "moyenne", "elevee"]},
        "explication": {"type": "string"},
    },
    "required": ["verdict", "confiance", "explication"],
}

SYSTEME = (
    "Tu aides un enseignant de cégep à corriger des rapports de laboratoire de sciences. "
    "On te donne des passages identiques ou très semblables trouvés dans deux rapports "
    "d'étudiants (A et B). Juge s'il s'agit d'une copie (texte repris tel quel sans raison "
    "légitime), d'une paraphrase (même contenu reformulé de près) ou d'une coïncidence "
    "(vocabulaire technique imposé, formules, protocole, données partagées en équipe). "
    "Réponds en français, brièvement. Le verdict est un indice pour l'enseignant, "
    "qui décide : reste prudent, mentionne ce qui plaide dans l'autre sens. "
    "[NOM], [PRÉNOM] et [DA] remplacent un nom, un prénom et un numéro de DA masqués : ignore-les."
)


# --- Fichiers ---------------------------------------------------------------

_verrou = threading.RLock()


def dossier_plagiat() -> Path:
    chemin = dossier_donnees() / "plagiat"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def _lire(nom: str, defaut):
    return stockage.lire_json(dossier_plagiat() / nom, defaut)


def _ecrire(nom: str, valeur) -> None:
    stockage.ecrire_json(dossier_plagiat() / nom, valeur)


def chemin_enonce(cours: str, lab: str) -> Path:
    return (bibliotheque.racine() / bibliotheque.segment_sur(cours, "cours") / "_enonces"
            / f"{bibliotheque.segment_sur(lab, 'lab')}.pdf")


# --- Texte et suites de mots -------------------------------------------------

def mots_du_pdf(contenu: bytes) -> list[str]:
    """Mots du PDF dans l'ordre (cache par contenu : un PDF n'est lu qu'une fois)."""
    sha = hashlib.sha1(contenu).hexdigest()
    cache = dossier_plagiat() / "textes" / f"{sha}.json"
    en_cache = stockage.lire_json(cache)  # un cache abîmé est simplement recalculé
    if isinstance(en_cache, list):
        return en_cache
    with tempfile.TemporaryDirectory() as d:
        f = Path(d) / "rapport.pdf"
        f.write_bytes(contenu)
        mots = pdf_texte.extraire(f).texte.split()
    stockage.ecrire_json(cache, mots)
    return mots


def jetons(mots: list[str]) -> tuple[list[str], list[str]]:
    """(mots d'origine, formes comparées) : sans accents ni ponctuation ni casse.
    Les mots sans lettre ni chiffre sont omis des deux listes."""
    origine, formes = [], []
    for m in mots:
        forme = bibliotheque.normaliser(m).replace(" ", "")
        if forme:
            origine.append(m)
            formes.append(forme)
    return origine, formes


def suites(formes: list[str]) -> list[tuple[str, ...]]:
    return [tuple(formes[i:i + MOTS_MIN]) for i in range(max(0, len(formes) - MOTS_MIN + 1))]


def _union(intervalles: list[tuple[int, int]]) -> list[tuple[int, int]]:
    fusion: list[tuple[int, int]] = []
    for a, b in sorted(intervalles):
        if fusion and a <= fusion[-1][1]:
            fusion[-1] = (fusion[-1][0], max(fusion[-1][1], b))
        else:
            fusion.append((a, b))
    return fusion


class Rapport:
    def __init__(self, ident: dict, contenu: bytes, enonce: set | None):
        self.ident = ident
        self.sha = hashlib.sha1(contenu).hexdigest()
        self.origine, self.formes = jetons(mots_du_pdf(contenu))
        self.suites = suites(self.formes)
        # Mots couverts par l'énoncé : ignorés (ni comptés, ni comparés).
        ignores = [False] * len(self.formes)
        if enonce:
            for i, s in enumerate(self.suites):
                if s in enonce:
                    ignores[i:i + MOTS_MIN] = [True] * MOTS_MIN
        self.ignores = ignores
        self.utiles = max(1, ignores.count(False))


def passages_communs(a: Rapport, b: Rapport, positions: list[tuple[int, int]]) -> list[dict]:
    """Fusionne les suites communes voisines (même diagonale) en passages."""
    par_diag: dict[int, list[int]] = {}
    for i, j in positions:
        par_diag.setdefault(i - j, []).append(i)
    bruts = []
    for diag, debuts in par_diag.items():
        debuts.sort()
        d = f = debuts[0]
        for i in debuts[1:] + [None]:
            if i is not None and i <= f + 1:
                f = i
                continue
            bruts.append((d, f + MOTS_MIN, d - diag, f + MOTS_MIN - diag))  # [a0,a1) [b0,b1)
            if i is not None:
                d = f = i
    # On retire un passage entièrement contenu dans un plus long (répétitions internes).
    bruts.sort(key=lambda p: p[0] - p[1])
    gardes: list[tuple[int, int, int, int]] = []
    for p in bruts:
        if not any(g[0] <= p[0] and p[1] <= g[1] and g[2] <= p[2] and p[3] <= g[3] for g in gardes):
            gardes.append(p)
    gardes.sort()
    return [{"a": [p[0], p[1]], "b": [p[2], p[3]],
             "mots": p[1] - p[0],
             "texte_a": " ".join(a.origine[p[0]:p[1]]),
             "texte_b": " ".join(b.origine[p[2]:p[3]])} for p in gardes]


def comparer_rapports(rapports: list[Rapport]) -> list[dict]:
    """Toutes les paires qui ont au moins un passage commun, triées par score décroissant."""
    index: dict[tuple[str, ...], list[tuple[int, int]]] = {}
    for n, r in enumerate(rapports):
        for i, s in enumerate(r.suites):
            if not r.ignores[i]:
                index.setdefault(s, []).append((n, i))
    positions: dict[tuple[int, int], list[tuple[int, int]]] = {}
    for postes in index.values():
        if len(postes) < 2 or len({n for n, _ in postes}) > RAPPORTS_MAX_PAR_SUITE:
            continue
        for x, (n1, i) in enumerate(postes):
            for n2, j in postes[x + 1:]:
                if n1 == n2 or _meme_etudiant(rapports[n1].ident, rapports[n2].ident):
                    continue
                if n1 < n2:
                    positions.setdefault((n1, n2), []).append((i, j))
                else:
                    positions.setdefault((n2, n1), []).append((j, i))
    paires = []
    for (n1, n2), pos in positions.items():
        a, b = rapports[n1], rapports[n2]
        passages = passages_communs(a, b, sorted(set(pos)))
        couverts_a = sum(y - x for x, y in _union([tuple(p["a"]) for p in passages]))
        couverts_b = sum(y - x for x, y in _union([tuple(p["b"]) for p in passages]))
        cov_a, cov_b = couverts_a / a.utiles, couverts_b / b.utiles
        cle = "-".join(sorted([a.sha[:12], b.sha[:12]]))
        if a.sha == b.sha:  # textes identiques : plusieurs paires pourraient avoir la même clé
            ids = sorted(f"{r.ident['cours']}/{r.ident['groupe']}/{r.ident['lab']}/{r.ident['etudiant']}" for r in (a, b))
            cle += "-" + hashlib.sha1("|".join(ids).encode()).hexdigest()[:6]
        if a.sha > b.sha:  # clé stable : A est toujours le plus petit hachage
            a, b, passages = b, a, [{**p, "a": p["b"], "b": p["a"],
                                     "texte_a": p["texte_b"], "texte_b": p["texte_a"]} for p in passages]
            cov_a, cov_b = cov_b, cov_a
        paires.append({
            "cle": cle,
            "a": a.ident, "b": b.ident,
            "score": round(max(cov_a, cov_b), 4),
            "couverture_a": round(cov_a, 4), "couverture_b": round(cov_b, 4),
            "nb_passages": len(passages), "mots_communs": max(couverts_a, couverts_b),
            "passages": passages,
        })
    paires.sort(key=lambda p: (-p["score"], p["cle"]))
    return paires


def _meme_etudiant(x: dict, y: dict) -> bool:
    """Un même étudiant qui réutilise son propre texte d'un lab à l'autre n'est pas visé."""
    if (x["cours"], x["groupe"], x["etudiant"]) == (y["cours"], y["groupe"], y["etudiant"]):
        return True
    # Coéquipiers d'un même lab : le texte commun est normal, pas un plagiat.
    if x["cours"] == y["cours"] and x["lab"] == y["lab"]:
        return (f"{y['groupe']}/{y['etudiant']}" in x.get("equipe", [])
                or f"{x['groupe']}/{x['etudiant']}" in y.get("equipe", []))
    return False


# --- Bibliothèque -----------------------------------------------------------

def _enonces() -> dict[tuple[str, str], set]:
    resultat = {}
    for f in bibliotheque.racine().glob("*/_enonces/*.pdf"):
        try:
            resultat[(f.parent.parent.name, f.stem)] = set(suites(jetons(mots_du_pdf(f.read_bytes()))[1]))
        except Exception:  # énoncé illisible : on compare sans lui
            continue
    return resultat


def charger_rapports() -> tuple[list[Rapport], list[str]]:
    enonces = _enonces()
    rapports, ignores = [], []
    for f in sorted(bibliotheque.racine().glob("*/*/*/*/rapport.pdf")):
        etudiant_dir = f.parent
        lab, groupe, cours = etudiant_dir.parent.name, etudiant_dir.parent.parent.name, etudiant_dir.parent.parent.parent.name
        ident = {"cours": cours, "groupe": groupe, "lab": lab, "etudiant": etudiant_dir.name,
                 "nom": _nom(cours, groupe, etudiant_dir.name)}
        fichier_equipe = etudiant_dir / "equipe.json"
        if fichier_equipe.is_file():
            ident["equipe"] = [f"{c['groupe']}/{c['id']}" for c in stockage.lire_json(fichier_equipe, [])]
        try:
            rapports.append(Rapport(ident, f.read_bytes(), enonces.get((cours, lab))))
        except Exception:
            ignores.append(f"{cours}/{groupe}/{lab}/{etudiant_dir.name}")
    return rapports, ignores


def _nom(cours: str, groupe: str, etudiant: str) -> str:
    try:
        for e in bibliotheque.charger_classe(cours, groupe)["etudiants"]:
            if e["id"] == etudiant:
                return f"{e['prenom']} {e['nom']}".strip()
    except HTTPException:
        pass
    return etudiant


# --- État : seuil, décisions, tâches en cours ---------------------------------

_en_cours: set[str] = set()


def seuil() -> float:
    return float(_lire("reglages.json", {}).get("seuil", SEUIL_DEFAUT))


def _statut(cle: str, score: float, decisions: dict) -> str:
    if cle in _en_cours:
        return "en_cours"
    d = decisions.get(cle)
    if d:
        return d["statut"]  # ecartee, analysee ou erreur
    return "a_confirmer" if score >= seuil() else "sous_seuil"


def _resume(p: dict, decisions: dict) -> dict:
    r = {k: v for k, v in p.items() if k != "passages"}
    r["statut"] = _statut(p["cle"], p["score"], decisions)
    d = decisions.get(p["cle"], {})
    if r["statut"] in ("analysee", "erreur"):
        r["resultat"] = {k: v for k, v in d.items() if k != "statut"}
    return r


class Reglages(BaseModel):
    seuil: float = Field(ge=0, le=1)


@router.get("/reglages")
def lire_reglages() -> dict:
    return {"seuil": seuil(), "mots_min": MOTS_MIN}


@router.put("/reglages")
def changer_reglages(r: Reglages) -> dict:
    with _verrou:
        _ecrire("reglages.json", {"seuil": r.seuil})
    return lire_reglages()


@router.post("/enonces/{cours}/{lab}")
async def televerser_enonce(cours: str, lab: str, pdf: UploadFile = File(...)) -> dict:
    """Énoncé du lab : ses passages sont ignorés dans la comparaison. Remplace le précédent."""
    lab = bibliotheque.slug(lab)  # même forme qu'à l'import (« Lab 3 » -> lab-3)
    contenu = await pdf.read()
    if not contenu.startswith(b"%PDF"):
        raise HTTPException(400, "Le fichier n'est pas un PDF.")
    try:
        mots_du_pdf(contenu)
    except pdf_texte.PdfSansTexte as e:
        raise HTTPException(422, str(e))
    except Exception as e:
        raise HTTPException(400, f"PDF illisible : {e}")
    cible = chemin_enonce(cours, lab)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return {"cours": cours, "lab": lab}


@router.get("/enonces/{cours}/{lab}")
def lire_enonce(cours: str, lab: str) -> FileResponse:
    cible = chemin_enonce(cours, bibliotheque.slug(lab))
    if not cible.is_file():
        raise HTTPException(404, "Aucun énoncé pour ce lab.")
    return FileResponse(cible, media_type="application/pdf")


@router.get("/enonces")
def lister_enonces() -> list[dict]:
    return [{"cours": c, "lab": l} for c, l in sorted(_enonces())]


@router.post("/comparer")
def comparer() -> dict:
    """Compare tous les rapports de la bibliothèque entre eux (local, sans Claude)."""
    with _verrou:
        rapports, illisibles = charger_rapports()
        paires = comparer_rapports(rapports)
        _ecrire("paires.json", paires)
    return {"rapports": len(rapports), "illisibles": illisibles, **lister()}


@router.get("/paires")
def lister() -> dict:
    decisions = _lire("decisions.json", {})
    paires = [_resume(p, decisions) for p in _lire("paires.json", [])]
    return {"seuil": seuil(), "paires": paires}


def _paire(cle: str) -> dict:
    for p in _lire("paires.json", []):
        if p["cle"] == cle:
            return p
    raise HTTPException(404, "Paire inconnue : relancer la comparaison.")


@router.get("/paires/{cle}")
def detail(cle: str) -> dict:
    p = _paire(cle)
    return {**_resume(p, _lire("decisions.json", {})), "passages": p["passages"]}


def _decider(cle: str, valeur: dict) -> None:
    with _verrou:
        decisions = _lire("decisions.json", {})
        decisions[cle] = valeur
        _ecrire("decisions.json", decisions)


@router.post("/paires/{cle}/ecarter")
def ecarter(cle: str) -> dict:
    _paire(cle)
    _decider(cle, {"statut": "ecartee"})
    return {"ok": True}


# --- Claude (après confirmation) ---------------------------------------------

_file: FileClaude | None = None


def file_claude() -> FileClaude:
    """File Claude du moteur (créée au premier envoi). Les tests la remplacent."""
    global _file
    if _file is None:
        _file = file_par_defaut()
    return _file


def construire_prompt(p: dict) -> str:
    """Passages seulement, sous les noms neutres A et B : pas de rapports entiers, et noms,
    prénoms et DA de tous les étudiants des cours des deux rapports masqués (un passage peut
    reprendre une page titre)."""
    masquer = Anonymiseur.pour(p["a"]["cours"], p["b"]["cours"]).masquer
    blocs, taille = [], 0
    for n, ps in enumerate(sorted(p["passages"], key=lambda x: -x["mots"]), start=1):
        bloc = (f"<passage numero=\"{n}\" mots=\"{ps['mots']}\">\n"
                f"<rapport_a>{masquer(ps['texte_a'])}</rapport_a>\n<rapport_b>{masquer(ps['texte_b'])}</rapport_b>\n</passage>")
        if taille + len(bloc) > CONTEXTE_MAX:
            break
        blocs.append(bloc)
        taille += len(bloc)
    return (
        f"<passages>\n" + "\n".join(blocs) + "\n</passages>\n\n"
        f"Le programme a trouvé {p['nb_passages']} passage(s) commun(s) "
        f"({round(p['couverture_a'] * 100)} % du rapport A, {round(p['couverture_b'] * 100)} % du rapport B), "
        f"{len(blocs)} montré(s) ci-dessus. Les passages de l'énoncé du lab sont déjà retirés. "
        "Les équipes de laboratoire partagent parfois leurs données et mesures. "
        "Donne ton verdict (copie, paraphrase ou coïncidence), ta confiance et une explication courte."
    )


def _terminer(cle: str, futur) -> None:
    try:
        r = futur.result()
        s = r.structure if isinstance(r.structure, dict) else {}
        if s.get("verdict") not in SCHEMA_VERDICT["properties"]["verdict"]["enum"]:
            raise ClaudeErreur("Réponse de Claude sans verdict utilisable.")
        valeur = {"statut": "analysee", "verdict": s["verdict"], "confiance": s.get("confiance", ""),
                  "explication": s.get("explication", "")}
    except BaseException as e:  # noqa: BLE001 : on garde le message pour l'écran
        valeur = {"statut": "erreur", "erreur": str(e) or type(e).__name__, "type": type(e).__name__}
    with _verrou:
        _en_cours.discard(cle)
        _decider(cle, valeur)


@router.post("/paires/{cle}/confirmer")
def confirmer(cle: str) -> dict:
    """Guillaume a confirmé : la paire est envoyée à Claude (réponse tout de suite, résultat plus tard)."""
    with _verrou:
        p = _paire(cle)
        if cle in _en_cours:
            return {"statut": "en_cours"}
        _en_cours.add(cle)
        decisions = _lire("decisions.json", {})
        decisions.pop(cle, None)  # nouvelle tentative après une erreur ou une décision d'écarter
        _ecrire("decisions.json", decisions)
    try:
        futur = file_claude().soumettre(construire_prompt(p), schema=SCHEMA_VERDICT, systeme=SYSTEME)
    except BaseException:
        with _verrou:
            _en_cours.discard(cle)
        raise
    futur.add_done_callback(lambda f: _terminer(cle, f))
    return {"statut": "en_cours"}
