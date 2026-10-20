"""Mesure du filtrage du français sur les rapports déjà rangés (comptes seulement).

    python scripts/mesurer_filtrage.py [--exemples N]

Relit chaque `rapport.pdf` de la bibliothèque locale, compte les fautes LanguageTool
« avant » (tout le texte, toutes les règles) et « après » (prose seulement, règles
filtrées), par règle. La passe Claude n'est jamais lancée. Rien n'est écrit sur disque.
`--exemples N` affiche aussi N fautes gardées et N retirées (à l'écran seulement, pour que
Guillaume juge; ne jamais les copier dans le dépôt, un test ou une PR).
LanguageTool doit tourner (voir demarrer.bat).
"""

import argparse
import sys
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from moteur import francais_filtre, languagetool, pdf_texte  # noqa: E402
from moteur.bibliotheque import racine  # noqa: E402


def contexte(texte: str, f) -> str:
    d, e = max(0, f.debut - 30), f.fin + 30
    return (texte[d:f.debut] + "[[" + texte[f.debut:f.fin] + "]]" + texte[f.fin:e]).replace("\n", " ⏎ ")


def main() -> None:
    sys.stdout.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser()
    ap.add_argument("--exemples", type=int, default=0)
    n = ap.parse_args().exemples
    avant, apres = Counter(), Counter()
    par_rapport = []
    gardees, retirees = [], []
    for pdf in sorted(racine().rglob("rapport.pdf")):
        texte = pdf_texte.extraire(pdf).texte
        brutes = languagetool.verifier(texte)
        seg = francais_filtre.segmenter(texte)
        gardes = francais_filtre.fautes_prose(texte, seg)
        cles = {(f.debut, f.fin) for f in gardes}
        avant.update(f.regle for f in brutes)
        apres.update(f.regle for f in gardes)
        par_rapport.append((len(brutes), len(gardes)))
        gardees += [(texte, f) for f in gardes]
        retirees += [(texte, f) for f in brutes if (f.debut, f.fin) not in cles]
    print(f"{len(par_rapport)} rapports")
    print("Par rapport (avant -> après) :", ", ".join(f"{a}->{b}" for a, b in par_rapport))
    print(f"Total : {sum(avant.values())} -> {sum(apres.values())}")
    print(f"{'règle':40} avant  après")
    for r in sorted(avant | apres, key=lambda r: -avant[r]):
        print(f"{r:40} {avant[r]:5} {apres[r]:6}")
    if n:
        pas = max(1, len(gardees) // n)
        print("\nGardées :")
        for t, f in gardees[::pas][:n]:
            print(f"  [{f.regle}] {contexte(t, f)}")
        pas = max(1, len(retirees) // n)
        print("\nRetirées :")
        for t, f in retirees[::pas][:n]:
            print(f"  [{f.regle}] {contexte(t, f)}")


if __name__ == "__main__":
    main()
