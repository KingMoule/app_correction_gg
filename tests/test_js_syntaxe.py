"""Garde-fou JavaScript : syntaxe de chaque script de la PWA, et identifiants de niveau fichier en double.

Les scripts d'une même page partagent la portée globale : une `const`/`let` déclarée deux fois
dans deux fichiers chargés ensemble fait rejeter le second fichier (écran gris du lecteur).
Ignoré avec un message si Node est absent.
"""
import re
import shutil
import subprocess
from pathlib import Path

import pytest

PWA = Path(__file__).resolve().parent.parent / "pwa"
SCRIPTS = sorted(p for p in PWA.glob("*.js"))
PAGES = sorted(PWA.glob("*.html"))


def _node():
    node = shutil.which("node")
    if node is None:
        pytest.skip("Node.js absent : la syntaxe des scripts de la PWA n'est pas vérifiée (installer Node).")
    return node


def _verifier(node, fichier):
    return subprocess.run([node, "--check", str(fichier)], capture_output=True, text=True, encoding="utf-8", timeout=60)


@pytest.mark.parametrize("fichier", SCRIPTS, ids=lambda f: f.name)
def test_syntaxe_script(fichier):
    r = _verifier(_node(), fichier)
    assert r.returncode == 0, r.stderr


@pytest.mark.parametrize("page", PAGES, ids=lambda f: f.name)
def test_pas_de_doublon_entre_scripts_d_une_page(page, tmp_path):
    node = _node()
    noms = re.findall(r'<script[^>]+src="([^"]+)"', page.read_text(encoding="utf-8"))
    locaux = [n for n in noms if not n.startswith(("vendor/", "http"))]
    assert locaux, f"aucun script local dans {page.name}"
    colle = tmp_path / "page.js"
    colle.write_text(";\n".join((PWA / n).read_text(encoding="utf-8") for n in locaux), encoding="utf-8")
    r = _verifier(node, colle)
    assert r.returncode == 0, f"{page.name} ({', '.join(locaux)}) :\n{r.stderr}"
