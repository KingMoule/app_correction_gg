"""Filtrage du français : prose seulement, mots complets. Textes fictifs."""

import json
import urllib.parse

import httpx
from fastapi.testclient import TestClient

from moteur import francais_claude, francais_filtre as ff, languagetool
from moteur.app import creer_app
from moteur.languagetool import Faute

PROSE = "Les étudiants ont mesuré la masse volumique de chaque liquide avec soin."
CALCUL = "ρ = m / V = 12,5 g / 25,0 mL = 0,50 g/mL"
TABLEAU = "Éthanol 0,789 1,361 24 °C"


def reconstitue(seg):
    return "".join(p.get("text", p.get("markup", "")) for p in seg.parties)


def test_segmentation_ne_perd_aucun_caractere():
    texte = f"{PROSE}\n{CALCUL}\n{TABLEAU}\n\nLa valeur mesurée est de 3,5 mol/L ± 0,1 selon le tableau.\n"
    seg = ff.segmenter(texte)
    assert reconstitue(seg) == texte


def test_calculs_et_tableaux_sont_ignores_la_prose_est_gardee():
    texte = f"{PROSE}\n{CALCUL}\n{TABLEAU}"
    seg = ff.segmenter(texte)
    ignores = [texte[d:f] for d, f in seg.lignes_markup]
    assert ignores == [CALCUL, TABLEAU]
    assert any(p.get("text", "").startswith(PROSE) for p in seg.parties)


def test_jetons_a_chiffres_ou_symboles_en_markup_dans_une_phrase():
    texte = "La concentration obtenue est de 3,5 mol/L pour la solution préparée."
    seg = ff.segmenter(texte)
    markups = [p["markup"] for p in seg.parties if "markup" in p]
    assert markups == ["3,5", "mol/L"]
    assert seg.lignes_markup == []


def test_references_ignorees():
    texte = f"{PROSE}\nBibliographie\n1. Smith, J. Capillary Viscometry for Routine Measurements.\n"
    seg = ff.segmenter(texte)
    assert any("Capillary" in p.get("markup", "") for p in seg.parties)
    assert not any("Capillary" in p.get("text", "") for p in seg.parties)


def faute(texte, mot, regle="FR_SPELLING_RULE"):
    d = texte.index(mot)
    return Faute(d, d + len(mot), mot, "m", regle, "TYPOS")


def test_orthographe_jetons_techniques_retires():
    texte = "On utilise du NaCl, du ml, un pH de 7, une tension V2 et un résultat Pearson ici."
    seg = ff.segmenter(texte)
    for mot in ["NaCl", "ml", "pH", "V2", "Pearson", "ab"]:
        t = texte if mot in texte else texte + " ab"
        assert not ff.garder(faute(t, mot), t, seg, set()), mot


def test_orthographe_vrai_mot_garde_sauf_lexique():
    texte = "Les étudiants ont observé une viscosité expériementale importante."
    seg = ff.segmenter(texte)
    f = faute(texte, "expériementale")
    assert ff.garder(f, texte, seg, set())
    assert not ff.garder(f, texte, seg, {"expériementale"})


def test_autres_regles_gardees_mais_pas_les_fautes_vides_ou_sur_calcul():
    texte = f"{PROSE}\n{CALCUL}"
    seg = ff.segmenter(texte)
    ok = Faute(4, 13, "étudiants", "m", "ACCORD", "GRAMMAR")
    vide = Faute(4, 4, "", "m", "FR_SPELLING_RULE", "TYPOS")
    d = texte.index("12,5")
    sur_calcul = Faute(d, d + 4, "12,5", "m", "REPETITION", "STYLE")
    assert ff.garder(ok, texte, seg, set())
    assert not ff.garder(vide, texte, seg, set())
    assert not ff.garder(sur_calcul, texte, seg, set())


def test_decalage_utf16_des_symboles_hors_plan_de_base():
    texte = "Soit 𝑥 et 𝑦. Les étudiants mesure la tension."
    u16 = len("Soit 𝑥 et 𝑦. Les étudiants ".encode("utf-16-le")) // 2  # position vue par LanguageTool

    def handler(request):
        return httpx.Response(200, json={"matches": [{
            "offset": u16, "length": 6, "message": "Accord",
            "rule": {"id": "ACCORD", "category": {"id": "GRAMMAR"}}, "replacements": []}]})

    fautes = languagetool.verifier(texte, client=httpx.Client(transport=httpx.MockTransport(handler)))
    assert fautes[0].texte == "mesure"


def test_languagetool_recoit_markup_et_regles_desactivees():
    recu = {}

    def handler(request):
        recu.update(urllib.parse.parse_qs(request.content.decode()))
        return httpx.Response(200, json={"matches": []})

    texte = f"{PROSE}\n{CALCUL}"
    ff.fautes_prose(texte, client=httpx.Client(transport=httpx.MockTransport(handler)))
    parties = json.loads(recu["data"][0])["annotation"]
    assert "".join(p.get("text", p.get("markup", "")) for p in parties) == texte
    assert "FRENCH_WHITESPACE" in recu["disabledRules"][0]
    assert "TYPOGRAPHY" in recu["disabledCategories"][0]
    assert "text" not in recu


def test_claude_ne_recoit_pas_les_calculs_et_ses_fautes_dessus_sont_ecartees():
    texte = f"{PROSE}\n{CALCUL}\nIl a manger hier soir dans le laboratoire de chimie."
    seg = ff.segmenter(texte)
    envoye = ff.prose_pour_claude(texte, seg)
    assert CALCUL not in envoye and "a manger" in envoye
    gardees = francais_claude.fautes_claude(
        texte, [], {"fautes": [{"extrait": "g/mL", "correction": "g/mL.", "message": "x"}]}, seg.lignes_markup)
    assert gardees == []


def test_consigne_claude_ignore_calculs_et_symboles():
    assert "calculs" in francais_claude.SYSTEME and "symboles" in francais_claude.SYSTEME


def test_api_lexique(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    c = TestClient(creer_app())
    assert c.get("/api/francais/lexique").json() == {"mots": []}
    assert c.post("/api/francais/lexique", json={"mot": " Viscosimètre "}).json() == {"mots": ["viscosimètre"]}
    assert c.post("/api/francais/lexique", json={"mot": "deux mots"}).status_code == 422
    assert c.delete("/api/francais/lexique/viscosimètre").json() == {"mots": []}
