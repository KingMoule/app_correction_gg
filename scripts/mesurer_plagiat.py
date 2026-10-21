"""Mesure du plagiat sur une bibliothèque FICTIVE (aucune donnée réelle).

Usage : python scripts/mesurer_plagiat.py [dossier_de_travail] [nb_rapports]

Génère `nb_rapports` rapports (300 par défaut, 2 à 5 pages) répartis sur 3 labs et 4 groupes de
25 étudiants, puis mesure : temps de comparaison, taille de `paires.json` (et des passages),
temps de réponse du suivi d'un lab et de l'export CSV. Fonctionne avec l'ancienne comparaison
(synchrone) et la nouvelle (arrière-plan).
"""

from __future__ import annotations

import io
import os
import random
import shutil
import sys
import time
from pathlib import Path

RACINE = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(RACINE))

from openpyxl import Workbook  # noqa: E402
from reportlab.pdfgen import canvas  # noqa: E402

LABS = ["lab-1", "lab-2", "lab-3"]
GROUPES = ["00001", "00002", "00003", "00004"]
PAR_GROUPE = 25
MOTS = [f"mot{i}" for i in range(1500)]


def phrase(rng: random.Random, n: int) -> list[str]:
    return [rng.choice(MOTS) for _ in range(n)]


def pdf(mots: list[str], pages: int) -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    par_page = max(1, len(mots) // pages)
    for p in range(pages):
        y = 800
        morceau = mots[p * par_page:(p + 1) * par_page if p < pages - 1 else len(mots)]
        for i in range(0, len(morceau), 12):
            c.drawString(40, y, " ".join(morceau[i:i + 12]))
            y -= 12
            if y < 40:
                break
        c.showPage()
    c.save()
    return tampon.getvalue()


def liste(nb: int) -> bytes:
    wb = Workbook()
    wb.active.append(["Nom", "Prénom"])
    for i in range(nb):
        wb.active.append([f"Nom{i:02d}", f"Pre{i:02d}"])
    t = io.BytesIO()
    wb.save(t)
    return t.getvalue()


def generer(client, total: int) -> int:
    rng = random.Random(7)
    par_cellule = max(1, total // (len(LABS) * len(GROUPES)))
    n = 0
    for g in GROUPES:
        r = client.post("/api/bibliotheque/classes",
                        files={"fichier": (f"ListeEtudiants_cours101FIC_gr{g}.xlsx", liste(PAR_GROUPE))})
        assert r.status_code == 200, r.text
    for lab in LABS:
        for gi, g in enumerate(GROUPES):
            protocole = phrase(random.Random(f"{lab}{g}"), 300)  # protocole commun à la cellule (comme l'audit)
            lots = []
            for e in range(par_cellule):
                pages = rng.randint(2, 5)
                propre = phrase(rng, 350 * pages)
                mots = propre[:150] + protocole + propre[150:]
                if e % 10 == 3:  # quelques vraies copies partielles dans la cellule
                    mots = lots[-1][1][:400] + phrase(rng, 200) + mots[600:]
                lots.append((f"Nom{e:02d}", mots, pages))
            r = client.post("/api/bibliotheque/import", data={"cours": "101FIC", "groupe": g, "lab": lab},
                            files=[("fichiers", (f"{nom}.pdf", pdf(m, p), "application/pdf")) for nom, m, p in lots])
            assert r.status_code == 200, r.text
            n += len(lots)
    return n


def taille(chemin: Path) -> int:
    return sum(f.stat().st_size for f in chemin.rglob("*") if f.is_file()) if chemin.is_dir() else (
        chemin.stat().st_size if chemin.is_file() else 0)


def main() -> None:
    travail = Path(sys.argv[1] if len(sys.argv) > 1 else "mesure_plagiat").resolve()
    total = int(sys.argv[2]) if len(sys.argv) > 2 else 300
    if not (travail / "bibliotheque").is_dir():
        travail.mkdir(parents=True, exist_ok=True)
    os.environ["CORRECTION_DONNEES"] = str(travail)
    os.environ["CORRECTION_SANS_CODE"] = "1"
    os.environ["CORRECTION_HOTES"] = "testserver"
    from fastapi.testclient import TestClient
    from moteur.app import creer_app
    client = TestClient(creer_app())
    if not (travail / "bibliotheque").is_dir() or not any((travail / "bibliotheque").rglob("rapport.pdf")):
        t = time.perf_counter()
        n = generer(client, total)
        print(f"Bibliothèque fictive : {n} rapports générés en {time.perf_counter() - t:.1f} s")
    # Repartir d'un état sans comparaison (le cache de textes est gardé : il sert aux deux versions).
    for nom in ("paires.json", "decisions.json", "passages"):
        cible = travail / "plagiat" / nom
        shutil.rmtree(cible, ignore_errors=True) if cible.is_dir() else cible.unlink(missing_ok=True)
    def comparer() -> float:
        t0 = time.perf_counter()
        r = client.post("/api/plagiat/comparer")
        if "etat" in r.json():  # nouvelle version : arrière-plan
            while client.get("/api/plagiat/comparer/etat").json()["etat"] == "en_cours":
                time.sleep(0.05)
        return time.perf_counter() - t0

    print(f"Première comparaison (avec lecture des PDF) : {comparer():.1f} s")
    duree = comparer()
    paires = client.get("/api/plagiat/paires").json()["paires"]
    d = travail / "plagiat"
    print(f"Comparaison (textes en cache) : {duree:.2f} s, {len(paires)} paires")
    print(f"paires.json : {taille(d / 'paires.json') / 1e6:.2f} Mo; passages/ : {taille(d / 'passages') / 1e6:.2f} Mo")

    def chrono(url: str, fois: int = 5) -> float:
        t0 = time.perf_counter()
        for _ in range(fois):
            assert client.get(url).status_code == 200
        return (time.perf_counter() - t0) / fois * 1000

    print(f"Suivi d'un lab (/api/suivi/101FIC/lab-1) : {chrono('/api/suivi/101FIC/lab-1'):.0f} ms")
    print(f"Liste des paires (/api/plagiat/paires) : {chrono('/api/plagiat/paires'):.0f} ms")
    if paires:
        print(f"Détail d'une paire : {chrono('/api/plagiat/paires/' + paires[0]['cle']):.0f} ms")


if __name__ == "__main__":
    main()
