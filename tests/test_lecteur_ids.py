"""Garde-fou du lecteur : chaque identifiant que ses scripts demandent par $("id") existe dans lecteur.html
(un identifiant manquant fait planter tout le script au chargement : écran sans outils)."""
import re
from pathlib import Path

import pytest

PWA = Path(__file__).resolve().parent.parent / "pwa"
SCRIPTS = ["lecteur.js", "francais.js", "inspecteur.js", "navigation-lecteur.js"]
HTML = (PWA / "lecteur.html").read_text(encoding="utf-8")
IDS = set(re.findall(r'\bid="([^"]+)"', HTML))
# Identifiants construits : $("o-" + outil), $("onglet-" + nom)
CONSTRUITS = {f"o-{k}" for k in ("crayon", "surligneur", "gomme")} | {f"onglet-{k}" for k in ("francais", "ia", "plagiat")}


@pytest.mark.parametrize("script", SCRIPTS)
def test_identifiants_du_script_dans_la_page(script):
    demandes = set(re.findall(r'\$\("([\w-]+)"\)', (PWA / script).read_text(encoding="utf-8")))
    assert demandes, "aucun $(\"id\") trouvé : la regex ne suit plus le code"
    assert demandes <= IDS, sorted(demandes - IDS)


def test_identifiants_construits_dans_la_page():
    assert CONSTRUITS <= IDS, sorted(CONSTRUITS - IDS)


def test_pas_d_identifiant_en_double():
    ids = re.findall(r'\bid="([^"]+)"', HTML)
    assert len(ids) == len(set(ids)), sorted({i for i in ids if ids.count(i) > 1})


def test_scripts_de_la_page_dans_l_ordre():
    """navigation-lecteur.js et inspecteur.js utilisent `ref`, `base` et `params` de lecteur.js : ils viennent après."""
    noms = re.findall(r'<script[^>]+src="([^"]+)"', HTML)
    locaux = [n for n in noms if not n.startswith(("vendor/", "http"))]
    assert locaux.index("lecteur.js") < locaux.index("francais.js") < locaux.index("inspecteur.js") < locaux.index("navigation-lecteur.js")
    assert locaux.index("ui.js") < locaux.index("lecteur.js")
