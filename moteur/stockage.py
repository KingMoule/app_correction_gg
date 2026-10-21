"""Lecture et écriture sûres des fichiers JSON de la bibliothèque (audit E1, E3, F5).

- `ecrire_json` : écriture atomique (temporaire unique dans le même dossier, fsync, `os.replace`),
  avec de courts nouveaux essais sous Windows quand un autre fil lit le fichier (PermissionError).
- `lire_json` : lecture tolérante; fichier absent, tronqué ou illisible = valeur par défaut
  (et une ligne dans le journal pour un fichier abîmé), jamais une erreur 500.
- `verrou(dossier)` / `modifier_json` : verrou par dossier pour les lecture-modification-écriture.

Le verrou protège les fils d'un même moteur (lot, requêtes HTTP); il est réentrant, donc un code
qui le tient peut appeler `ecrire_json`, `lire_json` ou `modifier_json` sur le même dossier. Lectures et
remplacements d'un même dossier sont ainsi sérialisés (sous Windows, `os.replace` échoue si un fil lit
le fichier); les lecteurs d'un autre processus (copie de sauvegarde) sont couverts par les nouveaux essais.
"""
from __future__ import annotations

import contextlib
import json
import logging
import os
import tempfile
import threading
import time
from pathlib import Path
from typing import Any, Callable

journal = logging.getLogger("moteur.stockage")

ESSAIS = 40          # nouveaux essais sur PermissionError (Windows : fichier ouvert par un lecteur)
ATTENTE = 0.005      # secondes, multipliées par le numéro de l'essai jusqu'à 0,05 s (≈ 1,5 s au plus)

_verrous: dict[str, threading.RLock] = {}
_verrous_garde = threading.Lock()


def verrou(dossier: Path | str) -> threading.RLock:
    """Verrou réentrant propre à un dossier (en général celui d'un rapport) : `with verrou(d): …`."""
    cle = os.path.normcase(os.path.abspath(dossier))
    with _verrous_garde:
        return _verrous.setdefault(cle, threading.RLock())


def _reessayer(operation: Callable[[], Any]) -> Any:
    for essai in range(1, ESSAIS + 1):
        try:
            return operation()
        except PermissionError:
            if essai == ESSAIS:
                raise
            time.sleep(min(ATTENTE * essai, 10 * ATTENTE))


def ecrire_octets(chemin: Path | str, contenu: bytes) -> None:
    """Écrit `contenu` de façon atomique : le fichier est soit l'ancien, soit le nouveau, jamais à moitié écrit."""
    chemin = Path(chemin)
    chemin.parent.mkdir(parents=True, exist_ok=True)
    fd, nom = tempfile.mkstemp(dir=chemin.parent, prefix=chemin.name + ".", suffix=".tmp")
    try:
        with os.fdopen(fd, "wb") as f:
            f.write(contenu)
            f.flush()
            os.fsync(f.fileno())
        with verrou(chemin.parent):  # un seul écrivain à la fois par dossier : pas de remplacement croisé
            _reessayer(lambda: os.replace(nom, chemin))
    except BaseException:
        with contextlib.suppress(OSError):
            os.unlink(nom)
        raise


def ecrire_json(chemin: Path | str, valeur: Any, *, indent: int | None = None,
                separators: tuple[str, str] | None = None, ensure_ascii: bool = False) -> None:
    """Écrit `valeur` en JSON (UTF-8) de façon atomique."""
    texte = json.dumps(valeur, ensure_ascii=ensure_ascii, indent=indent, separators=separators)
    ecrire_octets(chemin, texte.encode("utf-8"))


def lire_json(chemin: Path | str, defaut: Any = None) -> Any:
    """Contenu JSON du fichier, ou `defaut` s'il est absent, tronqué ou illisible (message au journal)."""
    chemin = Path(chemin)
    try:
        with verrou(chemin.parent):  # pas de lecture pendant un remplacement du même dossier (Windows)
            donnees = _reessayer(chemin.read_bytes)
    except FileNotFoundError:
        return defaut
    except OSError as e:
        journal.warning("Lecture impossible de %s : %s", chemin, e)
        return defaut
    try:
        return json.loads(donnees.decode("utf-8-sig"))
    except ValueError as e:  # JSON invalide ou UTF-8 invalide (fichier tronqué, par exemple)
        journal.warning("Fichier JSON abîmé, valeur par défaut utilisée : %s (%s)", chemin, e)
        return defaut


def modifier_json(chemin: Path | str, modifier: Callable[[Any], Any], defaut: Any = None, **options) -> Any:
    """Lecture-modification-écriture sous le verrou du dossier.

    `modifier(valeur)` reçoit le contenu actuel (ou `defaut`); s'il renvoie autre chose que `None`,
    c'est la nouvelle valeur, sinon la valeur reçue (modifiée sur place) est écrite. Renvoie la valeur écrite."""
    chemin = Path(chemin)
    with verrou(chemin.parent):
        valeur = lire_json(chemin, defaut)
        resultat = modifier(valeur)
        if resultat is not None:
            valeur = resultat
        ecrire_json(chemin, valeur, **options)
        return valeur
