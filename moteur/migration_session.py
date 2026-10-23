"""Migration du rangement sans session vers le rangement par session (voir docs/ARCHITECTURE.md).

Avant : `bibliotheque/202SNURE/<groupe>/…`. Après : `bibliotheque/202SNURE_A2026/<groupe>/…`.
Chaque ancien dossier de cours est **renommé** (même disque : un renommage, aucune copie, rien de supprimé),
puis les fichiers qui citent l'ancien nom de cours sont corrigés (`classe.json`, `_attente`, `_ecartes`, `_remplaces` (dossiers renommés), `reprendre.json`,
`exports.json`, comparaisons du plagiat). Avant de toucher à quoi que ce soit : sauvegarde automatique.

Idempotente : sans ancien dossier, rien ne se passe. Si un lancement est interrompu entre le renommage et la
correction des fichiers, le lancement suivant termine le travail. Après coup, le nombre de fichiers et de
rapports est comparé à celui d'avant; un écart est une erreur (la sauvegarde permet de revenir en arrière).
Un journal est écrit dans `<données>/migrations/`.

Commande : python -m moteur.migration_session [--session A2026] [--a-sec]
"""

import argparse
import json
import os
import sys
from datetime import datetime
from pathlib import Path

from . import sauvegarde, stockage
from . import session as sessions
from .config import dossier_donnees

SESSION_PAR_DEFAUT = "A2026"  # la session de toutes les données existantes (décision de Guillaume)


class MigrationErreur(Exception):
    """Erreur à afficher telle quelle à Guillaume."""


def session_de_migration(explicite: str | None = None) -> str:
    return sessions.valider(explicite or os.environ.get("CORRECTION_SESSION_MIGRATION") or SESSION_PAR_DEFAUT)


def anciens_cours(bibliotheque: Path) -> list[Path]:
    """Dossiers de cours sans session (hors `_attente`, `_ecartes`, `_remplaces`…)."""
    if not bibliotheque.is_dir():
        return []
    return [d for d in sorted(bibliotheque.iterdir())
            if d.is_dir() and not d.name.startswith("_") and sessions.separer(d.name)[1] is None]


def inventaire(donnees: Path) -> dict:
    """Nombre de fichiers (tout le dossier de données) et de rapports (`rapport.pdf`) avec leur taille totale."""
    fichiers = [f for f in donnees.rglob("*") if f.is_file() and "migrations" not in f.relative_to(donnees).parts[:1]]
    rapports = [f for f in fichiers if f.name == "rapport.pdf"]
    return {"fichiers": len(fichiers), "rapports": len(rapports),
            "octets_rapports": sum(f.stat().st_size for f in rapports)}


def _nouveau_nom(valeur, bibliotheque: Path, session: str):
    """Nom de cours avec session si `valeur` est un ancien nom dont le dossier a été renommé; sinon None."""
    if not isinstance(valeur, str) or sessions.separer(valeur)[1] is not None:
        return None
    cible = f"{valeur}_{session}"
    return cible if not (bibliotheque / valeur).exists() and (bibliotheque / cible).is_dir() else None


def _corriger(doc, bibliotheque: Path, session: str):
    """Copie de `doc` où chaque champ `cours` ancien est remplacé; (copie, nombre de remplacements)."""
    n = 0

    def marche(x):
        nonlocal n
        if isinstance(x, dict):
            sortie = {}
            for k, v in x.items():
                nouveau = _nouveau_nom(v, bibliotheque, session) if k == "cours" else None
                if nouveau:
                    n += 1
                sortie[k] = nouveau or marche(v)
            return sortie
        if isinstance(x, list):
            return [marche(v) for v in x]
        return x

    return marche(doc), n


def _reecrire(fichier: Path, bibliotheque: Path, session: str, journal: list[str], racine: Path) -> None:
    doc = stockage.lire_json(fichier)
    if doc is None:
        return
    nouveau, n = _corriger(doc, bibliotheque, session)
    if n:
        stockage.ecrire_json(fichier, nouveau, indent=1)
        journal.append(f"{fichier.relative_to(racine).as_posix()} : {n} nom(s) de cours corrigé(s)")


def _corriger_exports(donnees: Path, bibliotheque: Path, session: str, journal: list[str]) -> None:
    """`exports.json` : clés « cours/lab »."""
    fichier = donnees / "exports.json"
    doc = stockage.lire_json(fichier)
    if not isinstance(doc, dict):
        return
    nouveau, n = {}, 0
    for cle, valeur in doc.items():
        cours, _, lab = cle.partition("/")
        cible = _nouveau_nom(cours, bibliotheque, session)
        if cible and f"{cible}/{lab}" not in doc:
            nouveau[f"{cible}/{lab}"] = valeur
            n += 1
        else:
            nouveau[cle] = valeur
    if n:
        stockage.ecrire_json(fichier, nouveau, indent=1)
        journal.append(f"exports.json : {n} clé(s) de lab corrigée(s)")


def _remplaces_a_renommer(bibliotheque: Path, session: str) -> list[tuple[Path, Path]]:
    """Dossiers de `_remplaces/` au nom `<ancien cours>_<groupe>_…` à renommer en `<cours>_<session>_<groupe>_…`
    (la fiche d'étudiant les retrouve par le nom du cours)."""
    base = bibliotheque / "_remplaces"
    if not base.is_dir():
        return []
    a_faire = []
    for d in sorted(base.iterdir()):
        ancien, _, reste = d.name.partition("_")
        nouveau = _nouveau_nom(ancien, bibliotheque, session)
        if d.is_dir() and nouveau and reste and not sessions.MOTIF_CLE.match(f"{ancien}_{reste.split('_')[0]}"):
            a_faire.append((d, base / f"{nouveau}_{reste}"))
    return a_faire


def corriger_references(donnees: Path, session: str, journal: list[str]) -> None:
    """Corrige les fichiers qui citent un ancien nom de cours (idempotent, relançable)."""
    bibliotheque = donnees / "bibliotheque"
    for classe in sorted(bibliotheque.glob("*/*/classe.json")):
        if classe.parent.parent.name.startswith("_"):
            continue
        doc = stockage.lire_json(classe)
        if isinstance(doc, dict) and doc.get("cours") != classe.parent.parent.name \
                and sessions.separer(classe.parent.parent.name)[1] is not None:
            doc["cours"] = classe.parent.parent.name
            stockage.ecrire_json(classe, doc, indent=1)
            journal.append(f"{classe.relative_to(donnees).as_posix()} : cours = {doc['cours']}")
    for dossier in ("_attente", "_ecartes"):
        for meta in sorted((bibliotheque / dossier).glob("*.json")):
            _reecrire(meta, bibliotheque, session, journal, donnees)
    for source, cible in _remplaces_a_renommer(bibliotheque, session):
        if cible.exists():
            journal.append(f"_remplaces/{source.name} : laissé tel quel ({cible.name} existe déjà)")
            continue
        source.rename(cible)
        journal.append(f"_remplaces/{source.name} renommé en {cible.name}")
    _reecrire(donnees / "reprendre.json", bibliotheque, session, journal, donnees)
    _corriger_exports(donnees, bibliotheque, session, journal)
    plagiat = donnees / "plagiat"
    if plagiat.is_dir():
        for f in sorted(plagiat.rglob("*.json")):
            if "textes" not in f.relative_to(plagiat).parts[:1]:
                _reecrire(f, bibliotheque, session, journal, donnees)


def migrer(donnees: Path | None = None, session: str | None = None, a_sec: bool = False,
           destination_sauvegardes: Path | None = None) -> dict:
    """Migre vers `session`. Renvoie un compte rendu; `migre` est faux quand il n'y avait rien à faire."""
    donnees = donnees or dossier_donnees()
    session = session_de_migration(session)
    bibliotheque = donnees / "bibliotheque"
    anciens = anciens_cours(bibliotheque)
    a_corriger = bool(anciens) or _references_a_corriger(donnees, session)
    if not a_corriger:
        return {"migre": False, "session": session, "message": "Rien à migrer : le rangement a déjà des sessions."}
    conflits = [d.name for d in anciens if (bibliotheque / f"{d.name}_{session}").exists()]
    if conflits:
        raise MigrationErreur(
            f"Impossible de migrer : {', '.join(conflits)}_{session} existe déjà à côté de l'ancien dossier. "
            "Rien n'a été touché; renommer ou déplacer l'un des deux à la main, puis relancer.")
    plan = [(d.name, f"{d.name}_{session}") for d in anciens]
    if a_sec:
        return {"migre": False, "a_sec": True, "session": session, "renommages": plan, "avant": inventaire(donnees)}

    archive = None
    if anciens:  # sauvegarde seulement avant un renommage (la correction des références seule est relançable)
        try:
            archive = sauvegarde.sauvegarder(donnees, destination_sauvegardes or sauvegarde.dossier_sauvegardes(donnees))
        except sauvegarde.SauvegardeErreur as e:
            raise MigrationErreur(f"Sauvegarde impossible, rien n'a été touché : {e}") from e
    avant = inventaire(donnees)
    for ancien, nouveau in plan:
        os.rename(bibliotheque / ancien, bibliotheque / nouveau)
    journal: list[str] = []
    corriger_references(donnees, session, journal)
    apres = inventaire(donnees)
    compte = {"migre": True, "session": session, "renommages": plan, "avant": avant, "apres": apres,
              "sauvegarde": str(archive) if archive else None, "corrections": journal}
    if anciens and (apres["fichiers"] != avant["fichiers"] or apres["rapports"] != avant["rapports"]
                    or apres["octets_rapports"] != avant["octets_rapports"]):
        compte["erreur"] = "Les compteurs diffèrent après la migration."
    dossier = donnees / "migrations"
    dossier.mkdir(exist_ok=True)
    compte["date"] = datetime.now().astimezone().isoformat(timespec="seconds")
    stockage.ecrire_json(dossier / f"session_{datetime.now():%Y%m%d-%H%M%S}.json", compte, indent=1)
    if "erreur" in compte:
        raise MigrationErreur(f"{compte['erreur']} Avant : {avant}; après : {apres}. "
                              f"Revenir en arrière avec la sauvegarde {archive} (docs/DEMARRAGE.md).")
    return compte


def _references_a_corriger(donnees: Path, session: str) -> bool:
    """Vrai si un lancement précédent a renommé les dossiers sans finir de corriger les fichiers."""
    bibliotheque = donnees / "bibliotheque"
    for classe in bibliotheque.glob("*/*/classe.json"):
        doc = stockage.lire_json(classe)
        if not classe.parent.parent.name.startswith("_") and sessions.separer(classe.parent.parent.name)[1] \
                and isinstance(doc, dict) and doc.get("cours") != classe.parent.parent.name:
            return True
    if any(not c.exists() for _, c in _remplaces_a_renommer(bibliotheque, session)):
        return True
    for f in [*(bibliotheque / "_attente").glob("*.json"), *(bibliotheque / "_ecartes").glob("*.json"), donnees / "reprendre.json"]:
        doc = stockage.lire_json(f)
        if doc is not None and _corriger(doc, bibliotheque, session)[1]:
            return True
    return False


def executer_au_demarrage() -> None:
    """Appelée par `python -m moteur` avant le démarrage du serveur. Arrête le lancement en cas d'erreur."""
    try:
        compte = migrer()
    except MigrationErreur as e:
        print(f"MIGRATION DES SESSIONS ECHOUEE : {e}", file=sys.stderr)
        sys.exit(1)
    if compte["migre"]:
        n = compte["avant"]["rapports"]
        print(f"Rangement par session : {len(compte['renommages'])} cours rangé(s) dans {compte['session']} "
              f"({n} rapports, {compte['avant']['fichiers']} fichiers, comptes identiques). "
              f"Sauvegarde : {compte['sauvegarde']}")


def main(argv: list[str] | None = None) -> int:
    p = argparse.ArgumentParser(prog="python -m moteur.migration_session", description=__doc__.splitlines()[0])
    p.add_argument("--session", help=f"session des données existantes (défaut : {SESSION_PAR_DEFAUT})")
    p.add_argument("--a-sec", action="store_true", help="montre ce qui serait renommé, sans rien changer")
    args = p.parse_args(argv)
    try:
        compte = migrer(session=args.session, a_sec=args.a_sec)
    except MigrationErreur as e:
        print(f"MIGRATION ECHOUEE : {e}", file=sys.stderr)
        return 1
    print(json.dumps(compte, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
