"""Consommation de Claude : journal des appels, fenêtres glissantes, calibrage et estimation.

`claude -p` ne donne pas aux programmes le pourcentage officiel du forfait (seul `/usage`, dans
Claude Code, l'affiche). Ce module garde donc des mesures exactes (jetons et coût estimé de chaque
appel, tirés du JSON de `claude -p`) et en tire un pourcentage **estimé** : coût de la fenêtre ×
« % par dollar », rapport calé sur les valeurs de `/usage` que Guillaume saisit de temps en temps.
Sans calibrage, on utilise la mesure de docs/PLAN.md (environ 3 % de la session par rapport).

Le journal (`<données>/consommation/journal.json`) ne contient aucun texte d'étudiant ni nom : le
rapport concerné y figure sous une empreinte opaque (sel local), jamais par son identifiant de dossier
(qui est le nom de l'étudiant). Rotation : les appels de plus de 14 jours sont résumés par jour et par type.

Les appelants posent le contexte d'un appel avec `with contexte("francais", cours, lab, etudiant):`
autour de leurs `soumettre`; la file Claude le lit à la soumission et journalise le résultat.
"""

from __future__ import annotations

import contextlib
import contextvars
import hashlib
import math
import re
import secrets
import statistics
import threading
from datetime import datetime, timedelta

from fastapi import APIRouter
from pydantic import BaseModel, Field

from . import config, stockage

router = APIRouter(prefix="/api/consommation")

LIBELLES = {"francais": "Français", "ia": "Indices d'IA", "references": "Références", "plagiat": "Plagiat"}
TYPES = tuple(LIBELLES)

MARGE_DEFAUT = 20.0                 # % de la session gardés en réserve
FENETRE_SESSION = timedelta(hours=5)
FENETRE_SEMAINE = timedelta(days=7)
GARDE_JOURS = 14                    # au-delà, les appels sont résumés par jour
GARDE_RESUME_JOURS = 400
GARDE_CALIBRAGES = 5                # le rapport « % par dollar » est la médiane des derniers
COUT_MIN_CALIBRAGE = 0.05           # sous ce coût dans la fenêtre, une lecture ne permet pas de caler
MIN_MESURES = 3                     # appels d'un type nécessaires pour préférer la mesure au défaut

# Mesures de docs/PLAN.md (Sonnet) : ~0,107 $ par rapport pour ~3 % de la session de 5 h.
COUT_DEFAUT_USD = {"francais": 0.035, "ia": 0.032, "references": 0.040, "plagiat": 0.040}
PCT_PAR_USD_DEFAUT = 27.0

_verrou = threading.Lock()
_maintenant = datetime.now          # remplaçable par les tests

_ctx: contextvars.ContextVar = contextvars.ContextVar("consommation_contexte", default=None)


# --- Contexte d'un appel -------------------------------------------------------------------

@contextlib.contextmanager
def contexte(type_: str, *rapport: str):
    """Type d'appel (`francais`, `ia`, `references`, `plagiat`) et rapport concerné (cours, lab, étudiant…)."""
    jeton = _ctx.set({"type": type_, "rapport": tuple(rapport)})
    try:
        yield
    finally:
        _ctx.reset(jeton)


def contexte_courant() -> dict | None:
    return _ctx.get()


# --- Fichiers ------------------------------------------------------------------------------

def _dossier():
    return config.dossier_donnees() / "consommation"


def _nouveau_journal() -> dict:
    return {"version": 1, "sel": secrets.token_hex(8), "appels": [], "jours": {}, "limites": []}


def _lire_journal() -> dict:
    doc = stockage.lire_json(_dossier() / "journal.json")
    if not isinstance(doc, dict) or not isinstance(doc.get("appels"), list):
        return _nouveau_journal()
    doc.setdefault("sel", secrets.token_hex(8))
    doc.setdefault("jours", {})
    doc.setdefault("limites", [])
    return doc


def _reglages() -> dict:
    doc = stockage.lire_json(_dossier() / "reglages.json")
    doc = doc if isinstance(doc, dict) else {}
    doc.setdefault("marge_pct", MARGE_DEFAUT)
    doc.setdefault("calibrages", [])
    return doc


def _jour(t: float) -> str:
    return datetime.fromtimestamp(t).date().isoformat()


def _empreinte(sel: str, rapport: tuple) -> str | None:
    if not rapport:
        return None
    return hashlib.sha256((sel + "|" + "|".join(rapport)).encode("utf-8")).hexdigest()[:8]


def _ajouter_resume(jours: dict, a: dict) -> None:
    cible = jours.setdefault(_jour(a["t"]), {}).setdefault(a["type"], {"n": 0, "cout": 0.0, "jetons": 0})
    cible["n"] += 1
    cible["cout"] = round(cible["cout"] + a["cout"], 6)
    cible["jetons"] += a["entree"] + a["sortie"] + a["cache_ecriture"] + a["cache_lecture"]


def _faire_tourner(doc: dict, maintenant: datetime) -> None:
    """Résume les appels de plus de GARDE_JOURS jours par jour et par type; borne les listes."""
    limite = (maintenant - timedelta(days=GARDE_JOURS)).timestamp()
    anciens = [a for a in doc["appels"] if a["t"] < limite]
    if anciens:
        for a in anciens:
            _ajouter_resume(doc["jours"], a)
        doc["appels"] = [a for a in doc["appels"] if a["t"] >= limite]
    if len(doc["jours"]) > GARDE_RESUME_JOURS:
        for j in sorted(doc["jours"])[: len(doc["jours"]) - GARDE_RESUME_JOURS]:
            del doc["jours"][j]
    doc["limites"] = doc["limites"][-20:]


# --- Écriture (appelée par la file Claude) --------------------------------------------------

def enregistrer_appel(resultat, ctx: dict | None, modele: str | None = None) -> None:
    """Ajoute un appel réussi au journal. Ne lève jamais : le journal ne doit pas faire échouer un appel."""
    try:
        usage = getattr(resultat, "usage", None) or {}
        cout = getattr(resultat, "cout_usd", None)
        brut = getattr(resultat, "brut", None) or {}
        modeles = brut.get("modelUsage") if isinstance(brut, dict) else None
        if isinstance(modeles, dict) and modeles:
            modele = ", ".join(sorted(modeles))
        type_ = (ctx or {}).get("type")
        rapport = tuple((ctx or {}).get("rapport") or ())
        maintenant = _maintenant()
        with _verrou:
            def ajouter(doc):
                doc = doc if isinstance(doc, dict) and isinstance(doc.get("appels"), list) else _nouveau_journal()
                doc.setdefault("sel", secrets.token_hex(8)); doc.setdefault("jours", {}); doc.setdefault("limites", [])
                doc["appels"].append({
                    "t": maintenant.timestamp(),
                    "type": type_ if type_ in TYPES else "autre",
                    "modele": modele or "",
                    "entree": int(usage.get("input_tokens") or 0),
                    "sortie": int(usage.get("output_tokens") or 0),
                    "cache_ecriture": int(usage.get("cache_creation_input_tokens") or 0),
                    "cache_lecture": int(usage.get("cache_read_input_tokens") or 0),
                    "cout": float(cout) if isinstance(cout, (int, float)) else 0.0,
                    "rapport": _empreinte(doc["sel"], rapport),
                })
                _faire_tourner(doc, maintenant)
                return doc
            _dossier().mkdir(parents=True, exist_ok=True)
            stockage.modifier_json(_dossier() / "journal.json", ajouter)
    except Exception:  # noqa: BLE001
        stockage.journal.warning("Journal de consommation : écriture impossible", exc_info=True)


_RE_REPRISE = re.compile(r"reset\w*\s*(?:at\s*)?(\d{1,2})(?::(\d{2}))?\s*(am|pm)?", re.IGNORECASE)


def heure_de_reprise(message: str, maintenant: datetime) -> datetime | None:
    """Heure de reprise lue dans le message de limite de Claude (« … resets 5pm », « resets 17:40 »), sinon None.
    Format du message non garanti : lecture au mieux, l'absence de résultat est normale."""
    m = _RE_REPRISE.search(message or "")
    if not m:
        return None
    h, mi, ap = int(m.group(1)), int(m.group(2) or 0), (m.group(3) or "").lower()
    if ap == "pm" and h < 12:
        h += 12
    elif ap == "am" and h == 12:
        h = 0
    if h > 23 or mi > 59:
        return None
    t = maintenant.replace(hour=h, minute=mi, second=0, microsecond=0)
    return t if t > maintenant else t + timedelta(days=1)


def enregistrer_limite(message: str) -> None:
    """Note qu'une limite d'usage a été atteinte (avec l'heure de reprise si le message la donne)."""
    try:
        maintenant = _maintenant()
        reprise = heure_de_reprise(message, maintenant)
        with _verrou:
            def ajouter(doc):
                doc = doc if isinstance(doc, dict) and isinstance(doc.get("appels"), list) else _nouveau_journal()
                doc.setdefault("limites", [])
                doc["limites"].append({"t": maintenant.timestamp(), "message": (message or "")[:300],
                                       "reprise": reprise.timestamp() if reprise else None})
                _faire_tourner(doc, maintenant)
                return doc
            _dossier().mkdir(parents=True, exist_ok=True)
            stockage.modifier_json(_dossier() / "journal.json", ajouter)
    except Exception:  # noqa: BLE001
        stockage.journal.warning("Journal de consommation : écriture impossible", exc_info=True)


# --- Calculs -------------------------------------------------------------------------------

def _cout(appels: list[dict], depuis: float) -> float:
    return sum(a["cout"] for a in appels if a["t"] >= depuis)


def _ratio(reglages: dict, cle: str) -> float | None:
    """Médiane des derniers « % par dollar » calibrés (session ou semaine), ou None."""
    valeurs = [c[cle + "_ratio"] for c in reglages["calibrages"][-GARDE_CALIBRAGES:] if c.get(cle + "_ratio")]
    return statistics.median(valeurs) if valeurs else None


def pct_par_usd(reglages: dict | None = None) -> tuple[float, bool]:
    """(% de la session de 5 h par dollar, calibré ?)."""
    r = _ratio(reglages or _reglages(), "session")
    return (r, True) if r else (PCT_PAR_USD_DEFAUT, False)


def cout_moyen_par_type(appels: list[dict], maintenant: datetime) -> tuple[dict[str, float], dict[str, bool]]:
    """Coût moyen d'un appel de chaque type sur 30 jours (mesure) ou valeur par défaut (si < MIN_MESURES appels)."""
    depuis = (maintenant - timedelta(days=30)).timestamp()
    moyens, mesures = {}, {}
    for t in TYPES:
        couts = [a["cout"] for a in appels if a["type"] == t and a["t"] >= depuis and a["cout"] > 0]
        mesures[t] = len(couts) >= MIN_MESURES
        moyens[t] = statistics.fmean(couts) if mesures[t] else COUT_DEFAUT_USD[t]
    return moyens, mesures


def _pct(cout: float, k: float) -> float:
    return round(cout * k, 1)


def limite_active(doc: dict, maintenant: datetime) -> dict | None:
    if not doc["limites"]:
        return None
    d = doc["limites"][-1]
    reprise = d.get("reprise") or d["t"] + FENETRE_SESSION.total_seconds()
    if maintenant.timestamp() >= reprise:
        return None
    return {"t": datetime.fromtimestamp(d["t"]).isoformat(timespec="seconds"), "message": d["message"],
            "reprise": datetime.fromtimestamp(reprise).isoformat(timespec="minutes"),
            "reprise_connue": bool(d.get("reprise"))}


def resume() -> dict:
    maintenant = _maintenant()
    doc, reg = _lire_journal(), _reglages()
    appels = doc["appels"]
    k, calibre = pct_par_usd(reg)
    ks = _ratio(reg, "semaine")
    t5 = (maintenant - FENETRE_SESSION).timestamp()
    t7 = (maintenant - FENETRE_SEMAINE).timestamp()
    c5, c7 = _cout(appels, t5), _cout(appels, t7)
    marge = float(reg["marge_pct"])
    plafond = 100 - marge
    moyens, mesures = cout_moyen_par_type(appels, maintenant)
    cout_rapport = moyens["francais"] + moyens["ia"] + moyens["references"]
    pct_rapport = max(cout_rapport * k, 0.1)
    utilise = _pct(c5, k)
    restants = max(0, math.floor((plafond - utilise) / pct_rapport))

    # par jour (7 derniers jours), en % d'une session de 5 h
    jours = []
    for i in range(6, -1, -1):
        j = (maintenant - timedelta(days=i)).date().isoformat()
        c = sum(a["cout"] for a in appels if _jour(a["t"]) == j) + sum(v["cout"] for v in doc["jours"].get(j, {}).values())
        jours.append({"date": j, "cout": round(c, 4), "pct": _pct(c, k)})

    # par type sur 7 jours
    par_type, total7 = [], c7 or 0.0
    for t in TYPES:
        cs = [a["cout"] for a in appels if a["type"] == t and a["t"] >= t7]
        c = sum(cs)
        par_type.append({"type": t, "libelle": LIBELLES[t], "appels": len(cs), "cout": round(c, 4),
                         "part": round(c / total7, 3) if total7 else 0.0,
                         "pct_moyen": _pct(moyens[t], k), "mesure": mesures[t]})
    derniere = reg["calibrages"][-1] if reg["calibrages"] else None
    return {
        "maintenant": maintenant.isoformat(timespec="seconds"),
        "session": {"cout": round(c5, 4), "pct": utilise, "appels": sum(1 for a in appels if a["t"] >= t5)},
        "semaine": {"cout": round(c7, 4), "pct": _pct(c7, ks) if ks else None,
                    "appels": sum(1 for a in appels if a["t"] >= t7)},
        "marge_pct": marge, "plafond_pct": plafond,
        "calibrage": {"calibre": calibre, "pct_par_usd": round(k, 2),
                      "semaine_calibree": ks is not None,
                      "derniere": ({**{c: derniere[c] for c in ("session", "semaine") if derniere.get(c) is not None},
                                    "date": datetime.fromtimestamp(derniere["t"]).isoformat(timespec="minutes"),
                                    "ecart": derniere.get("ecart")} if derniere else None)},
        "pct_par_rapport": round(pct_rapport, 1),
        "restants": restants,
        "lot_conseille": max(1, restants),
        "par_jour": jours,
        "par_type": par_type,
        "limite": limite_active(doc, maintenant),
    }


def estimer(choisis: list[tuple]) -> dict:
    """Estimation d'un lot : `choisis` = [(étudiant, français, IA, références)] comme dans lot.py."""
    maintenant = _maintenant()
    doc, reg = _lire_journal(), _reglages()
    k, calibre = pct_par_usd(reg)
    moyens, mesures = cout_moyen_par_type(doc["appels"], maintenant)
    cle = ("francais", "ia", "references")
    cout = sum(moyens[t] for _, *flags in choisis for t, f in zip(cle, flags) if f)
    utilise = _pct(_cout(doc["appels"], (maintenant - FENETRE_SESSION).timestamp()), k)
    plafond = 100 - float(reg["marge_pct"])
    pct = _pct(cout, k)
    n = len(choisis)
    pct_unitaire = (pct / n) if n and pct else 0.0
    max_rapports = n if not pct_unitaire else max(0, math.floor((plafond - utilise) / pct_unitaire))
    return {"n": n, "cout": round(cout, 4), "pct": pct, "utilise": utilise, "apres": round(utilise + pct, 1),
            "plafond_pct": plafond, "marge_pct": float(reg["marge_pct"]),
            "depasse": utilise + pct > plafond, "max_rapports": min(n, max_rapports),
            "calibre": calibre, "mesure": all(mesures[t] for t in cle)}


def enregistrer_calibrage(session: float, semaine: float | None = None) -> dict:
    """Mémorise une lecture de `/usage` et en déduit le rapport « % par dollar »."""
    maintenant = _maintenant()
    doc = _lire_journal()
    c5 = _cout(doc["appels"], (maintenant - FENETRE_SESSION).timestamp())
    c7 = _cout(doc["appels"], (maintenant - FENETRE_SEMAINE).timestamp())
    avant = _pct(c5, pct_par_usd()[0])
    entree = {"t": maintenant.timestamp(), "session": session, "semaine": semaine,
              "cout_5h": round(c5, 4), "cout_semaine": round(c7, 4), "ecart": round(session - avant, 1)}
    if c5 >= COUT_MIN_CALIBRAGE and session > 0:
        entree["session_ratio"] = session / c5
    if semaine is not None and c7 >= COUT_MIN_CALIBRAGE and semaine > 0:
        entree["semaine_ratio"] = semaine / c7
    with _verrou:
        def ajouter(reg):
            reg = reg if isinstance(reg, dict) else {}
            reg.setdefault("marge_pct", MARGE_DEFAUT)
            reg["calibrages"] = (reg.get("calibrages") or [])[-(GARDE_CALIBRAGES * 4):] + [entree]
            return reg
        _dossier().mkdir(parents=True, exist_ok=True)
        stockage.modifier_json(_dossier() / "reglages.json", ajouter)
    return resume()


# --- API -----------------------------------------------------------------------------------

class Calibrage(BaseModel):
    session: float = Field(ge=0, le=100)
    semaine: float | None = Field(None, ge=0, le=100)


class Reglages(BaseModel):
    marge_pct: float = Field(ge=0, le=90)


@router.get("")
def lire() -> dict:
    return resume()


@router.post("/calibrage")
def calibrer(c: Calibrage) -> dict:
    return enregistrer_calibrage(c.session, c.semaine)


@router.post("/reglages")
def regler(r: Reglages) -> dict:
    with _verrou:
        def maj(reg):
            reg = reg if isinstance(reg, dict) else {}
            reg["marge_pct"] = r.marge_pct
            reg.setdefault("calibrages", [])
            return reg
        _dossier().mkdir(parents=True, exist_ok=True)
        stockage.modifier_json(_dossier() / "reglages.json", maj)
    return resume()
