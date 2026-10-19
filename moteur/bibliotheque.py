"""Bibliothèque : liste de classe, import des PDF par lot, rangement.

Rangement sous `<données>/bibliotheque/` :
    <cours>/<groupe>/classe.json                    liste de classe
    <cours>/<groupe>/<lab>/<étudiant>/rapport.pdf   rapport rangé
    _attente/<id>.pdf + <id>.json                   PDF à trancher par Guillaume
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


def lignes_du_fichier(nom: str, contenu: bytes) -> list[list[str]]:
    if nom.lower().endswith((".xlsx", ".xlsm")):
        from openpyxl import load_workbook

        feuille = load_workbook(io.BytesIO(contenu), read_only=True, data_only=True).active
        return [["" if c is None else str(c).strip() for c in ligne] for ligne in feuille.iter_rows(values_only=True)]
    if nom.lower().endswith(".csv"):
        try:
            texte = contenu.decode("utf-8-sig")
        except UnicodeDecodeError:
            texte = contenu.decode("latin-1")
        try:
            dialecte = csv.Sniffer().sniff(texte[:2000], delimiters=";,\t")
        except csv.Error:
            dialecte = csv.excel
        return [[c.strip() for c in ligne] for ligne in csv.reader(io.StringIO(texte), dialecte)]
    raise HTTPException(400, "Format non pris en charge : fichier Excel (.xlsx) ou CSV.")


def extraire_etudiants(lignes: list[list[str]]) -> list[dict]:
    """Repère la ligne d'en-tête (colonnes nom et prénom) puis lit les étudiants."""
    for i, ligne in enumerate(lignes[:15]):
        noms = [normaliser(c) for c in ligne]
        col_prenom = next((j for j, n in enumerate(noms) if n.startswith("prenom")), None)
        col_nom = next((j for j, n in enumerate(noms) if n in ("nom", "nom de famille", "nom famille")), None)
        if col_prenom is None or col_nom is None:
            continue
        etudiants, vus = [], {}
        for ligne in lignes[i + 1:]:
            nom = ligne[col_nom] if col_nom < len(ligne) else ""
            prenom = ligne[col_prenom] if col_prenom < len(ligne) else ""
            if not nom.strip():
                continue
            base = slug(f"{nom} {prenom}") or "etudiant"
            vus[base] = vus.get(base, 0) + 1
            ident = base if vus[base] == 1 else f"{base}-{vus[base]}"
            etudiants.append({"id": ident, "nom": nom.strip(), "prenom": prenom.strip()})
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

def candidats(nom_fichier: str, etudiants: list[dict]) -> list[dict]:
    """Étudiants dont le nom de famille figure dans le nom du fichier.

    Si plusieurs noms correspondent, on garde les plus longs (« Tremblay-Roy »
    l'emporte sur « Roy »). Le prénom départage seulement les homonymes.
    """
    cible = f" {normaliser(Path(nom_fichier).stem)} "
    trouves = [e for e in etudiants if f" {normaliser(e['nom'])} " in cible]
    if not trouves:
        return []
    plus_long = max(len(normaliser(e["nom"])) for e in trouves)
    trouves = [e for e in trouves if len(normaliser(e["nom"])) == plus_long]
    if len(trouves) > 1:
        par_prenom = [e for e in trouves if e["prenom"] and f" {normaliser(e['prenom'])} " in cible]
        if len(par_prenom) == 1:
            return par_prenom
    return trouves


def a_du_texte(contenu: bytes) -> bool:
    try:
        return any((p.extract_text() or "").strip() for p in PdfReader(io.BytesIO(contenu)).pages)
    except Exception:
        return False


def chemin_rapport(cours: str, groupe: str, lab: str, etudiant: str) -> Path:
    return dossier_groupe(cours, groupe) / segment_sur(lab, "lab") / etudiant / "rapport.pdf"


def ranger(contenu: bytes, cours: str, groupe: str, lab: str, etudiant: str) -> str:
    cible = chemin_rapport(cours, groupe, lab, etudiant)
    cible.parent.mkdir(parents=True, exist_ok=True)
    cible.write_bytes(contenu)
    return f"{cours}/{groupe}/{lab}/{etudiant}"


@router.post("/import")
async def importer_lot(
    cours: str = Form(...),
    groupe: str = Form(...),
    lab: str = Form(...),
    fichiers: list[UploadFile] = File(...),
) -> dict:
    """Importe un lot de PDF : range ceux qui correspondent à un seul étudiant,
    met les autres en attente, refuse les PDF sans texte."""
    lab = slug(lab)
    classe = charger_classe(cours, groupe)
    resultat = {"ranges": [], "en_attente": [], "refuses": []}
    for f in fichiers:
        nom = f.filename or "sans-nom.pdf"
        contenu = await f.read()
        if not contenu.startswith(b"%PDF") or not a_du_texte(contenu):
            resultat["refuses"].append({"fichier": nom, "raison": "PDF illisible ou sans texte (scan)"})
            continue
        trouves = candidats(nom, classe["etudiants"])
        deja = len(trouves) == 1 and chemin_rapport(cours, groupe, lab, trouves[0]["id"]).exists()
        if len(trouves) == 1 and not deja:
            ranger(contenu, cours, groupe, lab, trouves[0]["id"])
            resultat["ranges"].append({"fichier": nom, "etudiant": trouves[0]})
            continue
        raison = "deja_importe" if deja else ("ambigu" if trouves else "aucune_correspondance")
        ident = uuid.uuid4().hex[:12]
        dossier = racine() / "_attente"
        dossier.mkdir(exist_ok=True)
        (dossier / f"{ident}.pdf").write_bytes(contenu)
        meta = {"id": ident, "fichier": nom, "cours": cours, "groupe": groupe, "lab": lab,
                "raison": raison, "candidats": trouves}
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


@router.post("/attente/{ident}")
def trancher(ident: str, choix: Choix) -> dict:
    """Guillaume choisit l'étudiant (écrase un rapport déjà rangé) ou écarte le fichier."""
    segment_sur(ident, "id")
    dossier = racine() / "_attente"
    meta_f, pdf_f = dossier / f"{ident}.json", dossier / f"{ident}.pdf"
    if not meta_f.is_file():
        raise HTTPException(404, "Fichier en attente introuvable.")
    meta = json.loads(meta_f.read_text(encoding="utf-8"))
    if choix.etudiant:
        classe = charger_classe(meta["cours"], meta["groupe"])
        if choix.etudiant not in {e["id"] for e in classe["etudiants"]}:
            raise HTTPException(400, "Étudiant absent de la liste de classe.")
        ranger(pdf_f.read_bytes(), meta["cours"], meta["groupe"], meta["lab"], choix.etudiant)
    meta_f.unlink()
    pdf_f.unlink()
    return {"ok": True}


# --- Consultation -----------------------------------------------------------

@router.get("")
def arbre() -> list[dict]:
    """Cours > groupes > étudiants, avec les labs dont le rapport est rangé."""
    sortie = []
    for f in sorted(racine().glob("*/*/classe.json")):
        classe = json.loads(f.read_text(encoding="utf-8"))
        for e in classe["etudiants"]:
            e["labs"] = sorted(p.parent.parent.name for p in f.parent.glob(f"*/{e['id']}/rapport.pdf"))
        sortie.append(classe)
    return sortie


@router.get("/rapport/{cours}/{groupe}/{lab}/{etudiant}")
def rapport(cours: str, groupe: str, lab: str, etudiant: str) -> FileResponse:
    chemin = chemin_rapport(cours, groupe, lab, segment_sur(etudiant, "étudiant"))
    if not chemin.is_file():
        raise HTTPException(404, "Rapport introuvable.")
    return FileResponse(chemin, media_type="application/pdf")

