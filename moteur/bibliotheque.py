"""Bibliothèque : liste de classe, import des PDF par lot, rangement.

Rangement sous `<données>/bibliotheque/` :
    <cours>/<groupe>/classe.json                    liste de classe
    <cours>/<groupe>/<lab>/<étudiant>/rapport.pdf   rapport rangé
    <cours>/<groupe>/<lab>/<étudiant>/equipe.json   coéquipiers repérés sur la page titre
    <cours>/<groupe>/<lab>/<étudiant>/statut.json   {"termine": true} quand la correction est finie
    <cours>/<groupe>/<lab>/archive.json             {"archive": true} : lab rangé dans « Terminés »
    _attente/<id>.pdf + <id>.json                   PDF à trancher par Guillaume
    _ecartes/<id>.pdf + <id>.json                   PDF écartés (récupérables, jamais supprimés)
"""

import csv
import io
import json
import re
import unicodedata
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, UploadFile
from fastapi.responses import FileResponse
from pydantic import BaseModel
from pypdf import PdfReader

from .config import dossier_donnees

router = APIRouter(prefix="/api/bibliotheque")

MOTIF_LISTE = re.compile(r"ListeEtudiants_cours(?P<cours>[A-Za-z0-9]+)_gr(?P<groupe>[0-9]+)", re.I)
SEGMENT = re.compile(r"^[A-Za-z0-9_-]{1,40}$")


def racine() -> Path:
    chemin = dossier_donnees() / "bibliotheque"
    chemin.mkdir(parents=True, exist_ok=True)
    return chemin


def normaliser(texte: str) -> str:
    """Minuscules, sans accents, lettres et chiffres séparés par des espaces."""
    sans_accent = unicodedata.normalize("NFD", texte)
    sans_accent = "".join(c for c in sans_accent if unicodedata.category(c) != "Mn")
    return " ".join(re.findall(r"[a-z0-9]+", sans_accent.lower()))


def slug(texte: str) -> str:
    return normaliser(texte).replace(" ", "-")


def segment_sur(valeur: str, nom: str) -> str:
    if not SEGMENT.match(valeur):
        raise HTTPException(400, f"{nom} invalide : lettres, chiffres, - et _ seulement.")
    return valeur


# --- Liste de classe --------------------------------------------------------

def lire_cours_groupe(nom_fichier: str) -> tuple[str, str]:
    m = MOTIF_LISTE.search(nom_fichier)
    if not m:
        raise HTTPException(
            400,
            "Nom de fichier non reconnu : attendu ListeEtudiants_cours<NUMÉRO>_gr<NUMÉRO>.",
        )
    return m["cours"].upper(), m["groupe"]


ENROBAGE = re.compile(r'^="(.*)"$', re.S)
ENTETES_NOM = {"nom", "nom de famille", "nom famille", "nom de l etudiant", "nom etudiant"}
ENTETES_DA = {"da", "no de da", "no da", "numero de da", "numero da"}


def nettoyer_cellule(valeur: str) -> str:
    """Retire les espaces et l'enrobage `="..."` des exports Omnivox."""
    valeur = valeur.strip()
    m = ENROBAGE.match(valeur)
    return m[1].strip() if m else valeur


def decoder_csv(contenu: bytes) -> str:
    try:
        return contenu.decode("utf-8-sig")
    except UnicodeDecodeError:
        return contenu.decode("cp1252", errors="replace")


def lignes_du_fichier(nom: str, contenu: bytes) -> list[list[str]]:
    if nom.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        feuille = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True).active
        lignes = [["" if c is None else str(c) for c in ligne] for ligne in feuille.iter_rows(values_only=True)]
    elif nom.lower().endswith(".csv"):
        texte = decoder_csv(contenu)
        premiere = texte.lstrip().split(chr(10), 1)[0]
        delimiteur = max(";,\t", key=premiere.count) if any(d in premiere for d in ";,\t") else ";"
        lignes = list(csv.reader(io.StringIO(texte), delimiter=delimiteur))
    else:
        raise HTTPException(400, "Format non pris en charge : fichier Excel (.xlsx) ou CSV.")
    lignes = [[nettoyer_cellule(c) for c in ligne] for ligne in lignes]
    return [ligne for ligne in lignes if any(ligne)]


def extraire_etudiants(lignes: list[list[str]]) -> list[dict]:
    """Repère la ligne d'en-tête (colonnes nom et prénom) puis lit les étudiants.

    Le « No de DA » est gardé (champ `da`) s'il est présent; colonnes et lignes vides ignorées.
    """
    for i, ligne in enumerate(lignes[:15]):
        noms = [normaliser(c) for c in ligne]
        col_prenom = next((j for j, n in enumerate(noms) if n.startswith("prenom")), None)
        col_nom = next((j for j, n in enumerate(noms) if n in ENTETES_NOM), None)
        if col_prenom is None or col_nom is None:
            continue
        col_da = next((j for j, n in enumerate(noms) if n in ENTETES_DA), None)
        etudiants, vus = [], {}
        for ligne in lignes[i + 1:]:
            nom = ligne[col_nom] if col_nom < len(ligne) else ""
            prenom = ligne[col_prenom] if col_prenom < len(ligne) else ""
            if not nom.strip():
                continue
            base = slug(f"{nom} {prenom}") or "etudiant"
            vus[base] = vus.get(base, 0) + 1
            ident = base if vus[base] == 1 else f"{base}-{vus[base]}"
            etudiant = {"id": ident, "nom": nom.strip(), "prenom": prenom.strip()}
            da = ligne[col_da].strip() if col_da is not None and col_da < len(ligne) else ""
            if da:
                etudiant["da"] = da
            etudiants.append(etudiant)
        return etudiants
    raise HTTPException(400, "Colonnes « Nom » et « Prénom » introuvables dans les premières lignes.")


def dossier_groupe(cours: str, groupe: str) -> Path:
    return racine() / segment_sur(cours, "cours") / segment_sur(groupe, "groupe")


def charger_classe(cours: str, groupe: str) -> dict:
    fichier = dossier_groupe(cours, groupe) / "classe.json"
    if not fichier.is_file():
        raise HTTPException(404, f"Aucune liste de classe pour {cours} groupe {groupe}.")
    return json.loads(fichier.read_text(encoding="utf-8"))


@router.post("/classes")
async def importer_classe(fichier: UploadFile = File(...)) -> dict:
    cours, groupe = lire_cours_groupe(fichier.filename or "")
    etudiants = extraire_etudiants(lignes_du_fichier(fichier.filename, await fichier.read()))
    if not etudiants:
        raise HTTPException(400, "La liste ne contient aucun étudiant.")
    dossier = dossier_groupe(cours, groupe)
    dossier.mkdir(parents=True, exist_ok=True)
    classe = {"cours": cours, "groupe": groupe, "etudiants": etudiants}
    (dossier / "classe.json").write_text(json.dumps(classe, ensure_ascii=False, indent=1), encoding="utf-8")
    return classe


# --- Association d'un PDF à un étudiant -------------------------------------

MOTIF_DA = re.compile(r"(?<![0-9])([0-9]{6,9})(?![0-9])")
LONGUEUR_MIN_COMPACT = 4  # en dessous, « roy » ne doit pas se coller dans un autre mot


def extraire_da(nom_fichier: str) -> str | None:
    """N° de DA dans le nom du fichier LÉA (« nom_2626310_Rapport… »), 6 à 9 chiffres."""
    m = MOTIF_DA.search(Path(nom_fichier).stem)
    return m[1] if m else None


def candidats_par_nom(nom_fichier: str, etudiants: list[dict]) -> list[dict]:
    """Étudiants dont le nom de famille figure dans le nom du fichier.

    Si plusieurs noms correspondent, on garde les plus longs (« Tremblay-Roy »
    l'emporte sur « Roy »). Le prénom départage seulement les homonymes.
    Sans résultat, on compare sans séparateurs (« Bele-Gombos » ~ « BeleGombos »).
    """
    texte = normaliser(Path(nom_fichier).stem)
    cible = f" {texte} "
    jetons = set(texte.split())

    def compact(e: dict) -> str:
        return normaliser(e["nom"]).replace(" ", "")

    trouves = [e for e in etudiants if f" {normaliser(e['nom'])} " in cible]
    if not trouves:
        trouves = [e for e in etudiants if len(compact(e)) >= LONGUEUR_MIN_COMPACT and compact(e) in jetons]
    if not trouves:
        return []
    plus_long = max(len(compact(e)) for e in trouves)
    trouves = [e for e in trouves if len(compact(e)) == plus_long]
    if len(trouves) > 1:
        par_prenom = [e for e in trouves if e["prenom"] and f" {normaliser(e['prenom'])} " in cible]
        if len(par_prenom) == 1:
            return par_prenom
    return trouves


def associer(nom_fichier: str, etudiants: list[dict]) -> tuple[list[dict], str | None]:
    """(étudiants possibles, DA lu dans le nom). Le DA gagne; sinon le nom de famille."""
    da = extraire_da(nom_fichier)
    if da:
        par_da = [e for e in etudiants if e.get("da") == da]
        if par_da:
            return par_da, da
    return candidats_par_nom(nom_fichier, etudiants), da


def candidats(nom_fichier: str, etudiants: list[dict]) -> list[dict]:
    return associer(nom_fichier, etudiants)[0]


def etudiants_du_cours(cours: str, groupe: str | None = None) -> list[dict]:
    """Étudiants de tous les groupes du cours (ou d'un seul), chacun avec son `groupe`."""
    segment_sur(cours, "cours")
    sortie = []
    for f in sorted((racine() / cours).glob("*/classe.json")):
        if groupe and f.parent.name != groupe:
            continue
        sortie += [{**e, "groupe": f.parent.name} for e in json.loads(f.read_text(encoding="utf-8"))["etudiants"]]
    return sortie


def a_du_texte(contenu: bytes) -> bool:
    try:
        return any((p.extract_text() or "").strip() for p in PdfReader(io.BytesIO(contenu)).pages)
    except Exception:
        return False


def coequipiers(contenu: bytes, etudiants: list[dict], exclu: dict | None) -> list[dict]:
    """Étudiants du cours dont le nom ET le prénom figurent sur la première page."""
    try:
        page = normaliser(PdfReader(io.BytesIO(contenu)).pages[0].extract_text() or "")
    except Exception:
        return []
    page = f" {page} "
    trouves = []
    for e in etudiants:
        if exclu and (e["groupe"], e["id"]) == (exclu["groupe"], exclu["id"]):
            continue
        nom, prenom = normaliser(e["nom"]), normaliser(e["prenom"])
        if nom and prenom and f" {nom} " in page and f" {prenom} " in page:
            trouves.append({k: e[k] for k in ("id", "groupe", "nom", "prenom")})
    return trouves


def chemin_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> Path:
    return dossier_groupe(cours, groupe) / segment_sur(lab, "lab") / etudiant / "rapport.pdf"


def ranger(contenu: bytes, cours: str, groupe: str, lab: str, etudiant: str, equipe: list[dict] | None = None) -> str:
    cible = chemin_rapport(cours, groupe, lab, etudiant)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    fichier_equipe = cible.parent / "equipe.json"
    if equipe:
        fichier_equipe.write_text(json.dumps(equipe, ensure_ascii=False), encoding="utf-8")
    elif fichier_equipe.exists():
        fichier_equipe.unlink()  # nouveau rapport : l'ancienne équipe ne s'applique plus
    return f"{cours}/{groupe}/{lab}/{etudiant}"


@router.post("/import")
async def importer_lot(
    cours: str = Form(...),
    lab: str = Form(...),
    groupe: str = Form(""),
    fichiers: list[UploadFile] = File(...),
) -> dict:
    """Importe un lot de PDF. Sans `groupe`, chaque PDF va au groupe de son étudiant
    (le DA est unique dans le cours). Range ceux qui correspondent à un seul étudiant,
    met les autres en attente (avec la raison), refuse les PDF sans texte."""
    lab = slug(lab)
    groupe = groupe.strip() or None
    if groupe:
        charger_classe(cours, groupe)  # 404 si la liste est absente
    etudiants = etudiants_du_cours(cours, groupe)
    if not etudiants:
        raise HTTPException(404, f"Aucune liste de classe pour {cours}.")
    resultat = {"ranges": [], "en_attente": [], "refuses": [], "par_groupe": {}}
    for f in fichiers:
        nom = f.filename or "sans-nom.pdf"
        contenu = await f.read()
        if not contenu.startswith(b"%PDF") or not a_du_texte(contenu):
            resultat["refuses"].append({"fichier": nom, "raison": "PDF illisible ou sans texte (scan)"})
            continue
        trouves, da = associer(nom, etudiants)
        deja = len(trouves) == 1 and chemin_rapport(cours, trouves[0]["groupe"], lab, trouves[0]["id"]).exists()
        if len(trouves) == 1 and not deja:
            e = trouves[0]
            equipe = coequipiers(contenu, etudiants, e)
            ranger(contenu, cours, e["groupe"], lab, e["id"], equipe)
            resultat["ranges"].append({"fichier": nom, "etudiant": e, "groupe": e["groupe"], "equipe": equipe})
            resultat["par_groupe"][e["groupe"]] = resultat["par_groupe"].get(e["groupe"], 0) + 1
            continue
        if deja:
            raison = "deja_importe"
        elif trouves:
            raison = "ambigu"
        else:
            raison = "da_inconnu" if da else "aucune_correspondance"
        ident = uuid.uuid4().hex[:12]
        dossier = racine() / "_attente"
        dossier.mkdir(exist_ok=True)
        (dossier / f"{ident}.pdf").write_bytes(contenu)
        meta = {"id": ident, "fichier": nom, "cours": cours, "groupe": groupe, "lab": lab,
                "raison": raison, "da": da, "candidats": trouves}
        (dossier / f"{ident}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
        resultat["en_attente"].append(meta)
    return resultat


@router.get("/attente")
def lister_attente() -> list[dict]:
    dossier = racine() / "_attente"
    if not dossier.is_dir():
        return []
    return [json.loads(f.read_text(encoding="utf-8")) for f in sorted(dossier.glob("*.json"))]


class Choix(BaseModel):
    etudiant: str | None = None  # id de l'étudiant; vide = écarter le fichier
    groupe: str | None = None    # groupe de l'étudiant (sinon celui du lot)


@router.post("/attente/{ident}")
def trancher(ident: str, choix: Choix) -> dict:
    """Guillaume choisit l'étudiant (écrase un rapport déjà rangé) ou écarte le fichier.

    Un fichier écarté est déplacé dans `_ecartes/` (récupérable), jamais supprimé."""
    segment_sur(ident, "id")
    dossier = racine() / "_attente"
    meta_f, pdf_f = dossier / f"{ident}.json", dossier / f"{ident}.pdf"
    if not meta_f.is_file():
        raise HTTPException(404, "Fichier en attente introuvable.")
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    contenu = pdf_f.read_bytes()
    if choix.etudiant:
        groupe = choix.groupe or meta.get("groupe")
        tous = etudiants_du_cours(meta["cours"])
        e = next((x for x in tous if x["id"] == choix.etudiant and x["groupe"] == groupe), None)
        if not e:
            raise HTTPException(400, "Étudiant absent de la liste de classe.")
        ranger(contenu, meta["cours"], e["groupe"], meta["lab"], e["id"], coequipiers(contenu, tous, e))
        pdf_f.unlink()
    else:
        ecartes = racine() / "_ecartes"
        ecartes.mkdir(exist_ok=True)
        pdf_f.replace(ecartes / f"{ident}.pdf")
        (ecartes / f"{ident}.json").write_text(json.dumps(meta, ensure_ascii=False), encoding="utf-8")
    meta_f.unlink()
    return {"ok": True}


# --- Consultation -----------------------------------------------------------

@router.get("")
def arbre() -> list[dict]:
    """Cours > groupes > étudiants, avec les labs dont le rapport est rangé."""
    sortie = []
    for f in sorted(racine().glob("*/*/classe.json")):
        classe = json.loads(f.read_text(encoding="utf-8"))
        for e in classe["etudiants"]:
            rapports = sorted(f.parent.glob(f"*/{e['id']}/rapport.pdf"))
            e["labs"] = [p.parent.parent.name for p in rapports]
            equipes = {p.parent.parent.name: json.loads((p.parent / "equipe.json").read_text(encoding="utf-8"))
                       for p in rapports if (p.parent / "equipe.json").is_file()}
            if equipes:
                e["equipes"] = equipes
            e["termines"] = [p.parent.parent.name for p in rapports if _termine(p.parent)]
        classe["labs_archives"] = sorted(a.parent.name for a in f.parent.glob("*/archive.json") if _lire_drapeau(a, "archive"))
        sortie.append(classe)
    return sortie


def _lire_drapeau(fichier: Path, cle: str) -> bool:
    try:
        return bool(json.loads(fichier.read_text(encoding="utf-8")).get(cle))
    except (OSError, ValueError, AttributeError):
        return False


def _termine(dossier_rapport: Path) -> bool:
    return _lire_drapeau(dossier_rapport / "statut.json", "termine")


class Termine(BaseModel):
    termine: bool


class Archive(BaseModel):
    archive: bool


@router.put("/statut/{cours}/{groupe}/{lab}/{etudiant}")
def changer_statut(cours: str, groupe: str, lab: str, etudiant: str, corps: Termine) -> dict:
    """Marque un rapport terminé (ou le remet en cours). Le rapport doit exister."""
    segment_sur(etudiant, "étudiant")
    dossier = chemin_rapport(cours, groupe, lab, etudiant).parent
    if not (dossier / "rapport.pdf").is_file():
        raise HTTPException(404, "Rapport introuvable.")
    (dossier / "statut.json").write_text(json.dumps({"termine": corps.termine}), encoding="utf-8")
    return {"termine": corps.termine}


@router.put("/archive/{cours}/{groupe}/{lab}")
def changer_archive(cours: str, groupe: str, lab: str, corps: Archive) -> dict:
    """Archive un lab (il passe dans « Terminés » à l'écran; rien n'est déplacé ni supprimé)."""
    dossier = dossier_groupe(cours, groupe) / segment_sur(lab, "lab")
    if not dossier.is_dir():
        raise HTTPException(404, "Lab introuvable.")
    (dossier / "archive.json").write_text(json.dumps({"archive": corps.archive}), encoding="utf-8")
    return {"archive": corps.archive}


@router.get("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def rapport(cours: str, groupe: str, lab: str, etudiant: str) -> FileResponse:
    chemin = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not chemin.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return FileResponse(chemin, media_type="application/pdf")

