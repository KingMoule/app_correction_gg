"""Sauvegarde et restauration des données de correction (voir docs/DEMARRAGE.md).

Une sauvegarde = une archive zip datée de tout le dossier de données, sauf les caches
recalculables. Elle est écrite dans un fichier temporaire puis renommée : jamais de
sauvegarde à moitié écrite. Rien n'est jamais supprimé dans le dossier de données; la
rotation ne touche que les anciennes archives `sauvegarde_*.zip` du dossier de sauvegardes.

Commandes : python -m moteur.sauvegarde {auto|sauvegarder|lister|restaurer}
"""

import argparse
import json
import os
import shutil
import sys
import time
import zipfile
from datetime import datetime
from pathlib import Path

from moteur.config import dossier_donnees

PREFIXE = "sauvegarde_"
FORMAT_DATE = "%Y%m%d-%H%M%S"
# Caches recalculables, exclus de l'archive (chemins relatifs au dossier de données).
EXCLUS = ("plagiat/textes",)
GARDER_RECENTES = 10
GARDER_SEMAINES = 8


class SauvegardeErreur(Exception):
    """Erreur à afficher telle quelle à Guillaume."""


def dossier_sauvegardes(donnees: Path | None = None) -> Path:
    """Dossier des archives : CORRECTION_SAUVEGARDES, sinon `<données>_sauvegardes`
    (à côté du dossier de données, hors OneDrive comme lui)."""
    valeur = os.environ.get("CORRECTION_SAUVEGARDES")
    if valeur:
        return Path(valeur)
    donnees = donnees or dossier_donnees()
    return donnees.parent / (donnees.name + "_sauvegardes")


def _exclu(relatif: str) -> bool:
    return any(relatif == e or relatif.startswith(e + "/") for e in EXCLUS)


def fichiers_a_sauvegarder(donnees: Path):
    """(chemin, nom dans l'archive) de chaque fichier à sauvegarder."""
    for chemin in sorted(donnees.rglob("*")):
        if not chemin.is_file():
            continue
        relatif = chemin.relative_to(donnees).as_posix()
        if not _exclu(relatif):
            yield chemin, relatif


def _lire_coherent(chemin: Path) -> bytes:
    """Contenu du fichier; un JSON est relu s'il est invalide (écriture en cours)."""
    for essai in range(4):
        contenu = chemin.read_bytes()
        if chemin.suffix.lower() != ".json":
            return contenu
        try:
            json.loads(contenu.decode("utf-8-sig"))
            return contenu
        except ValueError:
            time.sleep(0.2)
    return contenu


def sauvegarder(donnees: Path, destination: Path, maintenant: datetime | None = None) -> Path:
    """Crée l'archive datée et renvoie son chemin. Lève SauvegardeErreur en cas d'échec."""
    donnees, destination = donnees.resolve(), destination.resolve()
    if destination == donnees or donnees in destination.parents:
        raise SauvegardeErreur("Le dossier de sauvegardes ne peut pas être dans le dossier de données.")
    fichiers = list(fichiers_a_sauvegarder(donnees))
    if not fichiers:
        raise SauvegardeErreur("Aucune donnée à sauvegarder.")
    try:
        destination.mkdir(parents=True, exist_ok=True)
    except OSError as e:
        raise SauvegardeErreur(f"Dossier de sauvegardes inaccessible ({destination}) : {e}") from e
    nom = PREFIXE + (maintenant or datetime.now()).strftime(FORMAT_DATE)
    final = destination / (nom + ".zip")
    n = 2
    while final.exists():
        final = destination / f"{nom}_{n}.zip"
        n += 1
    temporaire = destination / (final.name + ".tmp")
    try:
        with zipfile.ZipFile(temporaire, "w", zipfile.ZIP_DEFLATED) as z:
            for chemin, relatif in fichiers:
                try:
                    z.writestr(relatif, _lire_coherent(chemin))
                except FileNotFoundError:
                    continue  # fichier supprimé pendant la copie
        with zipfile.ZipFile(temporaire) as z:
            if z.testzip() is not None:
                raise SauvegardeErreur("L'archive écrite est corrompue; sauvegarde annulée.")
        os.replace(temporaire, final)
    except SauvegardeErreur:
        temporaire.unlink(missing_ok=True)
        raise
    except OSError as e:
        temporaire.unlink(missing_ok=True)
        raise SauvegardeErreur(f"Écriture de la sauvegarde impossible : {e}") from e
    return final


def lister(destination: Path) -> list[tuple[datetime, Path]]:
    """Archives de sauvegarde, de la plus récente à la plus ancienne."""
    if not destination.is_dir():
        return []
    trouvees = []
    for p in destination.glob(PREFIXE + "*.zip"):
        try:
            date = datetime.strptime(p.stem[len(PREFIXE):][:15], FORMAT_DATE)
        except ValueError:
            continue
        trouvees.append((date, p))
    return sorted(trouvees, key=lambda x: (x[0], x[1].name), reverse=True)


def derniere_sauvegarde(destination: Path) -> datetime | None:
    archives = lister(destination)
    return archives[0][0] if archives else None


def a_supprimer(archives: list[tuple[datetime, Path]]) -> list[Path]:
    """Archives à retirer : on garde les 10 plus récentes et la plus récente de chacune
    des 8 dernières semaines (les 8 semaines les plus récentes qui ont une archive)."""
    gardees = {p for _, p in archives[:GARDER_RECENTES]}
    semaines = []
    for date, p in archives:  # de la plus récente à la plus ancienne
        cle = date.isocalendar()[:2]
        if cle not in semaines:
            semaines.append(cle)
            if len(semaines) <= GARDER_SEMAINES:
                gardees.add(p)
    return [p for _, p in archives if p not in gardees]


def appliquer_rotation(destination: Path) -> list[Path]:
    """Supprime les anciennes archives (et seulement elles). Renvoie ce qui a été retiré."""
    retirees = a_supprimer(lister(destination))
    for p in retirees:
        p.unlink(missing_ok=True)
    return retirees


def restaurer(archive: Path, cible: Path, remplacer: bool = False) -> Path | None:
    """Extrait l'archive dans `cible`.

    Si `cible` existe et n'est pas vide, rien n'est écrasé sans `remplacer=True` :
    l'ancien dossier est alors renommé `<cible>_avant_restauration_<date>` (et jamais
    supprimé). Renvoie ce nouveau nom (ou None s'il n'y avait rien à mettre de côté).
    """
    if not archive.is_file():
        raise SauvegardeErreur(f"Archive introuvable : {archive}")
    cible = cible.resolve()
    existe = cible.exists() and (not cible.is_dir() or any(cible.iterdir()))
    if existe and not remplacer:
        raise FileExistsError(str(cible))
    temporaire = cible.parent / f".restauration_{cible.name}_{os.getpid()}"
    if temporaire.exists():
        shutil.rmtree(temporaire)
    temporaire.mkdir(parents=True)
    try:
        with zipfile.ZipFile(archive) as z:
            racine = temporaire.resolve()
            for nom in z.namelist():
                destination = (racine / nom).resolve()
                if racine != destination and racine not in destination.parents:
                    raise SauvegardeErreur(f"Archive suspecte (chemin hors dossier) : {nom}")
            z.extractall(racine)
        ancien = None
        if existe:
            ancien = cible.parent / f"{cible.name}_avant_restauration_{datetime.now().strftime(FORMAT_DATE)}"
            n = 2
            while ancien.exists():
                ancien = cible.parent / f"{cible.name}_avant_restauration_{datetime.now().strftime(FORMAT_DATE)}_{n}"
                n += 1
            cible.rename(ancien)
        elif cible.is_dir():
            cible.rmdir()  # dossier vide
        temporaire.rename(cible)
        return ancien
    except BaseException:
        shutil.rmtree(temporaire, ignore_errors=True)
        raise


def message_statut(destination: Path) -> str:
    date = derniere_sauvegarde(destination)
    if date is None:
        return f"Aucune sauvegarde dans {destination}."
    jours = (datetime.now() - date).days
    quand = "aujourd'hui" if jours <= 0 else f"il y a {jours} jour{'s' if jours > 1 else ''}"
    return f"Dernière sauvegarde : {date:%Y-%m-%d %H:%M} ({quand}), dans {destination}."


def _cmd_sauvegarder(args, silencieux_si_vide: bool) -> int:
    donnees = Path(args.donnees) if args.donnees else dossier_donnees()
    destination = Path(args.destination) if args.destination else dossier_sauvegardes(donnees)
    try:
        archive = sauvegarder(donnees, destination)
    except SauvegardeErreur as e:
        if silencieux_si_vide and str(e).startswith("Aucune donnée"):
            print("Sauvegarde : rien à sauvegarder pour l'instant.")
            return 0
        print(f"SAUVEGARDE ECHOUEE : {e}", file=sys.stderr)
        return 1
    retirees = appliquer_rotation(destination)
    taille = archive.stat().st_size / 1_000_000
    print(f"Sauvegarde faite : {archive.name} ({taille:.1f} Mo)"
          + (f"; {len(retirees)} ancienne(s) archive(s) retirée(s)." if retirees else "."))
    print(message_statut(destination))
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python -m moteur.sauvegarde", description=__doc__.splitlines()[0])
    sous = parser.add_subparsers(dest="commande", required=True)
    for nom, aide in (("auto", "sauvegarde sans bloquer le démarrage (utilisée par demarrer.bat)"),
                      ("sauvegarder", "crée une archive maintenant")):
        p = sous.add_parser(nom, help=aide)
        p.add_argument("--donnees", help="dossier de données (défaut : CORRECTION_DONNEES)")
        p.add_argument("--destination", help="dossier de sauvegardes (défaut : CORRECTION_SAUVEGARDES)")
    p = sous.add_parser("lister", help="liste les archives")
    p.add_argument("--destination")
    p = sous.add_parser("restaurer", help="remet une archive dans un dossier")
    p.add_argument("archive", nargs="?", help="chemin de l'archive (défaut : la plus récente)")
    p.add_argument("--cible", help="dossier à créer (défaut : le dossier de données actuel)")
    p.add_argument("--destination")
    p.add_argument("--oui", action="store_true", help="ne pas demander confirmation avant de mettre l'actuel de côté")
    args = parser.parse_args(argv)

    if args.commande in ("auto", "sauvegarder"):
        code = _cmd_sauvegarder(args, silencieux_si_vide=args.commande == "auto")
        return 0 if args.commande == "auto" else code  # auto ne bloque jamais le démarrage
    destination = Path(args.destination) if args.destination else dossier_sauvegardes()
    if args.commande == "lister":
        archives = lister(destination)
        if not archives:
            print(f"Aucune sauvegarde dans {destination}.")
        for date, p in archives:
            print(f"{date:%Y-%m-%d %H:%M}  {p.stat().st_size / 1_000_000:7.1f} Mo  {p}")
        return 0
    # restaurer
    if args.archive:
        archive = Path(args.archive)
    else:
        archives = lister(destination)
        if not archives:
            print(f"Aucune sauvegarde dans {destination}.", file=sys.stderr)
            return 1
        archive = archives[0][1]
    cible = Path(args.cible) if args.cible else dossier_donnees()
    remplacer = False
    if cible.exists() and (not cible.is_dir() or any(cible.iterdir())):
        print(f"Le dossier {cible} existe déjà. Il sera RENOMMÉ (pas supprimé) avant la restauration de {archive.name}.")
        if args.oui or input("Continuer ? (o/n) ").strip().lower() in ("o", "oui", "y"):
            remplacer = True
        else:
            print("Restauration annulée, rien n'a été modifié.")
            return 1
    try:
        ancien = restaurer(archive, cible, remplacer)
    except SauvegardeErreur as e:
        print(f"RESTAURATION ECHOUEE : {e}", file=sys.stderr)
        return 1
    if ancien:
        print(f"Ancien dossier conservé : {ancien}")
    print(f"Restauré dans {cible}.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
