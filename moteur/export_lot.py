"""Export par lot pour LÉA : `Travaux.zip` (PDF corrigés) et tableau récapitulatif (CSV).

Rien n'est écrit dans la bibliothèque : le ZIP est construit en mémoire, en arrière-plan
(avec progression), le tableau à la demande. Un lab = un groupe, ou tous les groupes d'un cours.
Un rapport est rangé une seule fois, au nom du déposant : le ZIP a donc un PDF par rapport,
mais le tableau a une ligne par membre de l'équipe (même note, même pénalité).
"""

import csv
import io
import re
import threading
import zipfile
from datetime import datetime
from pathlib import Path

from fastapi import APIRouter, HTTPException
from fastapi.responses import Response
from pydantic import BaseModel

from . import bibliotheque, config, plagiat, stockage
from .annotations import lire
from .bareme import penalite
from .export import annoter, fautes_acceptees
from .francais import lire_bareme

router = APIRouter(prefix="/api/export-lot")

NOM_ZIP = "Travaux"  # + horodatage + « .zip » (voir `nom_zip`)
ETATS = {"corrige": "Corrigé", "claude_manquant": "Claude manquant", "a_trancher": "À trancher",
         "non_analyse": "Non analysé", "non_remis": "Non remis"}
# Fichiers dont le changement rend un export périmé (rapport remplacé, réanalyse, décision, trait, note…)
FICHIERS_SURVEILLES = ("rapport.pdf", "francais.json", "annotations.json", "statut.json", "equipe.json", "indices_ia.json")
COLONNES = ["DA", "Nom", "Prénom", "Groupe", "Équipe", "Fautes acceptées", "Pénalité français", "Note", "Terminé",
            "État", "Indice d'IA (à revérifier)", "Plagiat confirmé (à revérifier)"]
FORCES_IA = {"faible": "faible", "moderee": "modérée", "marquee": "marquée"}


# --- Collecte ----------------------------------------------------------------

def _json(fichier: Path):
    return stockage.lire_json(fichier)


def claude_fait(doc: dict | None) -> bool:
    """La passe Claude du français a-t-elle réussi ? Absente (ancien fichier) ou échouée = non."""
    return bool(doc and (doc.get("claude") or {}).get("ok"))


def etat_francais(doc: dict | None) -> tuple[str, int]:
    """(état, nombre de fautes acceptées) d'après `francais.json`.

    Tout tranché mais sans passe Claude réussie = « claude_manquant » : ce n'est pas un rapport complet.
    """
    if doc is None:
        return "non_analyse", 0
    decisions = doc.get("decisions", {})
    nb = sum(1 for d in decisions.values() if d == "acceptee")
    a_trancher = any(str(f["id"]) not in decisions for f in doc.get("fautes", []))
    if a_trancher:
        return "a_trancher", nb
    return ("corrige" if claude_fait(doc) else "claude_manquant"), nb


def signature(dossier: Path) -> dict[str, str]:
    """Empreinte (date de modification + taille) des fichiers qui changent le contenu de l'export."""
    sortie = {}
    for nom in FICHIERS_SURVEILLES:
        try:
            st = (dossier / nom).stat()
        except OSError:
            continue
        sortie[nom] = f"{st.st_mtime_ns}:{st.st_size}"
    return sortie


def horodatage(maintenant: datetime | None = None) -> str:
    """Date et heure locales pour un nom de fichier : `2026-10-20_14h32` (pas de « : » sous Windows)."""
    return (maintenant or datetime.now()).strftime("%Y-%m-%d_%Hh%M")


def nom_zip(stamp: str) -> str:
    return f"{NOM_ZIP}_{stamp}.zip"


def _fichier_exports() -> Path:
    return config.dossier_donnees() / "exports.json"  # hors de la bibliothèque : elle reste intacte


def _cle_lab(cours: str, lab: str) -> str:
    return f"{cours}/{lab}"


def noter_export(cours: str, lab: str, rapports: list[dict], iso: str) -> None:
    """Retient, rapport par rapport, ce qui vient de partir (date + empreinte prise AVANT la construction)."""
    chemin = _fichier_exports()
    with stockage.verrou(chemin.parent):
        tout = stockage.lire_json(chemin, {}) or {}
        lab_doc = tout.setdefault(_cle_lab(cours, lab), {})
        for r in rapports:
            lab_doc[f"{r['groupe']}/{r['etudiant']['id']}"] = {"date": iso, "sig": r["sig"]}
        stockage.ecrire_json(chemin, tout, indent=1)


def etat_export(cours: str, lab: str, dossiers: dict[str, Path]) -> dict:
    """État du dernier export pour les rapports donnés (`{"groupe/étudiant": dossier}`).

    `jamais` : aucun n'a été exporté; `perime` : au moins un a changé depuis (décision, trait, réanalyse,
    rapport remplacé, note…); `a_jour` sinon. `non_exportes` = rapports jamais partis (export partiel).
    """
    notes = (stockage.lire_json(_fichier_exports(), {}) or {}).get(_cle_lab(cours, lab), {})
    dates, modifies, non_exportes = [], [], 0
    for cle, dossier in dossiers.items():
        n = notes.get(cle)
        if not n:
            non_exportes += 1
            continue
        dates.append(n["date"])
        if signature(dossier) != n["sig"]:
            modifies.append(cle)
    statut = "jamais" if not dates else ("perime" if modifies else "a_jour")
    return {"statut": statut, "date": max(dates) if dates else None, "modifies": len(modifies),
            "non_exportes": non_exportes}


def _plagiat_confirme() -> list[tuple[dict, dict, dict]]:
    """Paires dont Claude a rendu un verdict (donc confirmées par Guillaume) : (a, b, verdict)."""
    return [(p["a"], p["b"], p["resultat"]) for p in plagiat.etat_des_paires() if p["statut"] == "analysee"]


def _texte_plagiat(cours, groupe, lab, etudiant, paires) -> str:
    morceaux = []
    for a, b, d in paires:
        for moi, autre in ((a, b), (b, a)):
            if (moi["cours"], moi["groupe"], moi["lab"], moi["etudiant"]) == (cours, groupe, lab, etudiant):
                verdict = d.get("verdict", "?")
                morceaux.append(f"{verdict} avec {autre.get('nom') or autre['etudiant']} ({autre['lab']})")
    return " ; ".join(morceaux)


def collecter(cours: str, lab: str, groupe: str | None) -> list[dict]:
    """Rapports du lab (un par déposant), triés par groupe puis nom, avec leur état."""
    bibliotheque.segment_sur(lab, "lab")
    classes = [c for c in bibliotheque.classes_du_cours(cours) if not groupe or c["groupe"] == groupe]
    if not classes:
        raise HTTPException(404, f"Aucune liste de classe pour {cours}" + (f" groupe {groupe}." if groupe else "."))
    bareme = lire_bareme(cours)
    paires = _plagiat_confirme()
    rapports = []
    for c in classes:
        for e in c["etudiants"]:
            dossier = bibliotheque.chemin_rapport(cours, c["groupe"], lab, e["id"]).parent
            if not (dossier / "rapport.pdf").is_file():
                continue
            etat, nb = etat_francais(_json(dossier / "francais.json"))
            ia = (_json(dossier / "indices_ia.json") or {}).get("force")
            equipe = _json(dossier / "equipe.json") or []
            rapports.append({
                "groupe": c["groupe"], "etudiant": e, "dossier": dossier, "equipe": equipe, "etat": etat, "nb": nb,
                "penalite": penalite(nb, bareme), "note": bibliotheque.lire_note(dossier),
                "termine": bool(_json(dossier / "statut.json") and _json(dossier / "statut.json").get("termine")),
                "ia": FORCES_IA.get(ia, ""),
                "plagiat": _texte_plagiat(cours, c["groupe"], lab, e["id"], paires),
                "origine": (_json(dossier / "origine.json") or {}).get("fichier"),
                "sig": signature(dossier),
            })
    rapports.sort(key=lambda r: (r["groupe"], bibliotheque.normaliser(r["etudiant"]["nom"]),
                                 bibliotheque.normaliser(r["etudiant"]["prenom"])))
    return rapports


def retenir(rapports: list[dict], inacheves: bool) -> list[dict]:
    return rapports if inacheves else [r for r in rapports if r["etat"] == "corrige"]


# --- Tableau -----------------------------------------------------------------

def _cellule(valeur) -> str:
    """Texte sûr pour un tableur : une formule (=, +, @) serait exécutée à l'ouverture."""
    if isinstance(valeur, float):
        return f"{valeur:.2f}".replace(".", ",").rstrip("0").rstrip(",") or "0"  # virgule décimale d'Excel français
    texte = str(valeur)
    if texte[:1] in ("=", "+", "@", "\t", "\r") or re.match(r"-\D", texte):
        return "'" + texte
    return texte


def lignes_tableau(cours: str, lab: str, groupe: str | None, inacheves: bool) -> list[list[str]]:
    rapports = retenir(collecter(cours, lab, groupe), inacheves)
    tous = {(c["groupe"], e["id"]): e for c in bibliotheque.classes_du_cours(cours) for e in c["etudiants"]}
    visibles = {(g, i) for (g, i) in tous if not groupe or g == groupe}
    lignes, vus = [], set()

    def ajouter(e, g, r, equipe):
        vus.add((g, e["id"]))
        lignes.append([e.get("da", ""), e["nom"], e["prenom"], g, equipe,
                       r["nb"] if r else "", r["penalite"] if r else "", r["note"] if r else "",
                       ("oui" if r["termine"] else "non") if r else "",
                       ETATS[r["etat"]] if r else ETATS["non_remis"], r["ia"] if r else "", r["plagiat"] if r else ""])

    deposants = {(r["groupe"], r["etudiant"]["id"]) for r in rapports}
    for r in rapports:
        e = r["etudiant"]
        membres = [f"{m['prenom']} {m['nom']}" for m in r["equipe"]]
        ajouter(e, r["groupe"], r, f"déposant ; avec {', '.join(membres)}" if membres else "")
        for m in r["equipe"]:
            cle = (m["groupe"], m["id"])
            autre = tous.get(cle) or m
            if cle not in deposants and cle not in vus:  # un coéquipier qui a son propre rapport garde sa ligne
                ajouter(autre, m["groupe"], r, f"équipe de {e['prenom']} {e['nom']}")
    if inacheves:  # étudiants sans rapport (ni déposant, ni coéquipier)
        for cle, e in sorted(tous.items(), key=lambda kv: (kv[0][0], bibliotheque.normaliser(kv[1]["nom"]))):
            if cle in visibles and cle not in vus:
                ajouter(e, cle[0], None, "")
    lignes.sort(key=lambda l: (l[3], bibliotheque.normaliser(l[1]), bibliotheque.normaliser(l[2])))
    return lignes


def nom_tableau(cours: str, lab: str, stamp: str) -> str:
    return re.sub(r"[^A-Za-z0-9_-]", "_", f"Recapitulatif_{cours}_{lab}_{stamp}") + ".csv"


def tableau_csv(cours: str, lab: str, groupe: str | None, inacheves: bool) -> bytes:
    """CSV pour Excel français : séparateur « ; », UTF-8 avec BOM (accents lisibles), virgule décimale."""
    tampon = io.StringIO()
    w = csv.writer(tampon, delimiter=";", lineterminator="\r\n")
    w.writerow(COLONNES)
    for ligne in lignes_tableau(cours, lab, groupe, inacheves):
        w.writerow([_cellule(v) for v in ligne])
    return tampon.getvalue().encode("utf-8-sig")


# --- ZIP ---------------------------------------------------------------------

def nom_pdf(r: dict, lab: str) -> str:
    """Nom d'origine du PDF de LÉA + `_corrige`; à défaut `<DA>_<nom>_<lab>_corrige.pdf`."""
    if r["origine"]:
        base = Path(r["origine"].replace("\\", "/")).stem
    else:
        e = r["etudiant"]
        base = f"{e.get('da') or e['id']}_{e['nom']}_{lab}"
    base = re.sub(r'[\x00-\x1f<>:"/\\|?*]+', "_", base).strip(" ._") or "rapport"
    return f"{base}_corrige.pdf"


def construire_zip(cours: str, lab: str, rapports: list[dict], progression=None) -> bytes:
    tampon = io.BytesIO()
    pris: set[str] = set()
    with zipfile.ZipFile(tampon, "w", zipfile.ZIP_DEFLATED) as z:
        for n, r in enumerate(rapports):
            e = r["etudiant"]
            if progression:
                progression(n, f"{e['prenom']} {e['nom']}")
            g, i = r["groupe"], e["id"]
            nom = nom_pdf(r, lab)
            suffixe = 2
            while nom.lower() in pris:  # deux rapports de même nom : on ne perd jamais l'un des deux
                nom = nom_pdf(r, lab)[:-4] + f"_{suffixe}.pdf"
                suffixe += 1
            pris.add(nom.lower())
            pdf = annoter(r["dossier"] / "rapport.pdf", lire(cours, g, lab, i), fautes_acceptees(r["dossier"] / "francais.json"))
            z.writestr(nom, pdf)
    return tampon.getvalue()


# --- Travail en arrière-plan ---------------------------------------------------

_verrou = threading.Lock()
_etat: dict = {"statut": "inactif"}
_zip: bytes = b""
_nom_zip = NOM_ZIP + ".zip"


class Demande(BaseModel):
    groupe: str | None = None  # vide = tous les groupes du cours
    inacheves: bool = True     # inclure les rapports à trancher / non analysés


def _executer(cours: str, lab: str, rapports: list[dict], iso: str) -> None:
    global _zip
    try:
        contenu = construire_zip(cours, lab, rapports,
                                 lambda fait, courant: _maj(fait=fait, courant=courant))
        noter_export(cours, lab, rapports, iso)
        with _verrou:
            _zip = contenu
            _etat.update(statut="pret", fait=len(rapports), courant=None, taille=len(contenu))
    except Exception as x:  # noqa: BLE001 : l'écran affiche l'erreur
        with _verrou:
            _etat.update(statut="erreur", courant=None, message=f"Export impossible : {x}")


def _maj(**champs) -> None:
    with _verrou:
        _etat.update(champs)


def _compter(rapports: list[dict]) -> dict:
    n = {"total": len(rapports), "corrige": 0, "claude_manquant": 0, "a_trancher": 0, "non_analyse": 0}
    for r in rapports:
        n[r["etat"]] += 1
    return n


@router.get("/apercu/{cours}/{lab}")
def apercu(cours: str, lab: str, groupe: str | None = None) -> dict:
    """Combien de rapports partiraient, et combien sont inachevés."""
    rapports = collecter(cours, lab, groupe or None)
    dossiers = {f"{r['groupe']}/{r['etudiant']['id']}": r["dossier"] for r in rapports}
    return {**_compter(rapports), "groupes": sorted({r["groupe"] for r in rapports}),
            "export": etat_export(cours, lab, dossiers)}


@router.post("/{cours}/{lab}")
def lancer(cours: str, lab: str, d: Demande) -> dict:
    global _zip, _nom_zip
    rapports = retenir(collecter(cours, lab, d.groupe or None), d.inacheves)
    if not rapports:
        raise HTTPException(404, "Aucun rapport à exporter pour ce choix.")
    with _verrou:
        if _etat["statut"] == "en_cours":
            raise HTTPException(409, "Un export est déjà en cours.")
        _zip = b""  # libère le ZIP précédent
        maintenant = datetime.now()
        _nom_zip = nom_zip(horodatage(maintenant))
        _etat.clear()
        _etat.update(statut="en_cours", cours=cours, lab=lab, groupe=d.groupe or None, fait=0, total=len(rapports),
                     nom=_nom_zip, date=maintenant.isoformat(timespec="seconds"),
                     courant=None, groupes=sorted({r["groupe"] for r in rapports}), inacheves=_compter(rapports))
    threading.Thread(target=_executer, args=(cours, lab, rapports, _etat["date"]), daemon=True).start()
    return dict(_etat)


@router.get("/etat")
def etat() -> dict:
    with _verrou:
        return dict(_etat)


@router.get("/travaux/{cours}/{lab}")
def telecharger_zip(cours: str, lab: str, groupe: str | None = None) -> Response:
    """Le ZIP prêt, à condition qu'il soit bien celui de ce cours, ce lab et ce groupe (jamais un autre par erreur)."""
    with _verrou:
        if _etat["statut"] != "pret" or not _zip:
            raise HTTPException(404, "Aucun export prêt.")
        if (_etat.get("cours"), _etat.get("lab"), _etat.get("groupe")) != (cours, lab, groupe or None):
            raise HTTPException(404, "Le ZIP prêt est celui d'un autre lab ou groupe : refais l'export.")
        contenu, nom = _zip, _nom_zip
    return Response(contenu, media_type="application/zip",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})


@router.get("/tableau/{cours}/{lab}")
def telecharger_tableau(cours: str, lab: str, groupe: str | None = None, inacheves: bool = True) -> Response:
    contenu = tableau_csv(cours, lab, groupe or None, inacheves)
    nom = nom_tableau(cours, lab, horodatage())
    return Response(contenu, media_type="text/csv; charset=utf-8",
                    headers={"Content-Disposition": f'attachment; filename="{nom}"'})
