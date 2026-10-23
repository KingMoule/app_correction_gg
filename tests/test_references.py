"""Tests de la vérification des références. Rapports FICTIFS ; réseau (Crossref, OpenAlex, pages) et Claude simulés."""

import io
import json
from concurrent.futures import Future

import httpx
import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur import lot, references, references_reseau as web
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, Resultat
from tests.test_bibliotheque import ELEVES, NOM_LISTE, xlsx

SULFATE = "10.1000/sulfate.2015"
CUIVRE = "10.1000/cuivre.2018"
INEXISTANT = "10.1000/fantome.2020"
AUTRE = "10.1000/autre.2019"

REPONSES = {
    SULFATE: ("Turbidimetric determination of sulfate ions in water",
              "Barium sulfate turbidity is used to measure the sulfate ion concentration in water samples."),
    CUIVRE: ("Copper corrosion in marine alloys", "We study the corrosion of copper and its oxides in seawater."),
    AUTRE: ("Gravimetric analysis of chloride", ""),
}


def reponse_crossref(doi):
    titre, resume = REPONSES[doi]
    m = {"title": [titre], "URL": f"https://doi.org/{doi}"}
    if resume:
        m["abstract"] = f"<jats:p>{resume}</jats:p>"
    return {"message": m}


class FauxReseau:
    """Transport httpx simulé : Crossref, OpenAlex, doi.org et deux pages web."""

    def __init__(self):
        self.requetes = []

    def __call__(self, requete: httpx.Request) -> httpx.Response:
        self.requetes.append(str(requete.url))
        u = requete.url
        if u.host == "api.crossref.org":
            if u.path.startswith("/works/10."):
                doi = u.path[len("/works/"):]
                return httpx.Response(200, json=reponse_crossref(doi)) if doi in REPONSES else httpx.Response(404)
            if "isbn" in dict(u.params).get("filter", ""):
                if "9782100545261" in u.params["filter"]:
                    return httpx.Response(200, json={"message": {"items": [{"title": ["Chimie analytique des solutions"], "URL": "x"}]}})
                return httpx.Response(200, json={"message": {"items": []}})
            return httpx.Response(200, json={"message": {"items": []}})
        if u.host == "api.openalex.org":
            return httpx.Response(404)
        if u.host == "doi.org":
            return httpx.Response(404, json={"responseCode": 100})
        if u.host == "exemple.test":
            if u.path == "/absente":
                return httpx.Response(404)
            return httpx.Response(200, headers={"content-type": "text/html; charset=utf-8"},
                                  text="<html><head><title>Guide du dosage</title></head><body><script>x</script>"
                                       "<p>Le dosage des sulfates par turbidimétrie.</p></body></html>")
        raise AssertionError(f"requête inattendue : {requete.url}")


def resolveur_faux(hote, port):
    if hote == "intranet.test":
        return [(2, 1, 6, "", ("192.168.1.5", 0))]
    if hote == "inexistant.test":
        raise OSError("nom inconnu")
    return [(2, 1, 6, "", ("93.184.216.34", 0))]


@pytest.fixture
def reseau(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    monkeypatch.delenv("CORRECTION_HORS_LIGNE", raising=False)
    monkeypatch.delenv("CORRECTION_CONTACT", raising=False)
    faux = FauxReseau()
    monkeypatch.setattr(web, "TRANSPORT", httpx.MockTransport(faux))
    monkeypatch.setattr(web, "RESOLVEUR", resolveur_faux)
    return faux


class FileFausse:
    """Claude simulé : « sans_lien » si la source parle de cuivre, « pertinente » sinon."""

    def __init__(self, erreur=None):
        self.erreur, self.appels = erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.appels.append((prompt, schema, systeme))
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
            return f
        envoyees = json.loads(prompt.split("<donnees>")[1].split("</donnees>")[0])
        verdicts = [{"id": e["id"], "verdict": "sans_lien" if "opper" in e["source"]["titre"] else "pertinente",
                     "explication": "La source traite du cuivre, la phrase des ions sulfate."
                     if "opper" in e["source"]["titre"] else "Même sujet."} for e in envoyees]
        f.set_result(Resultat(texte="", structure={"verdicts": verdicts}, usage={"output_tokens": 5}, cout_usd=0.01))
        return f


@pytest.fixture
def claude(monkeypatch):
    f = FileFausse()
    monkeypatch.setattr(references, "obtenir_file", lambda: f)
    return f


def calculer(texte, style="iso690"):
    r = web.Reseau()
    try:
        return references.calculer(texte, style, r, lambda t: t)
    finally:
        r.fermer()


def types(doc):
    return sorted(p["type"] for p in doc["liaison"])


# --- Rapports fictifs ---------------------------------------------------------------

RAPPORT_ISO = f"""Dosage des ions sulfate
La concentration en ions sulfate a été mesurée par turbidimétrie [1]. Le cuivre ne gêne pas ce
dosage [2]. La méthode est décrite dans un guide en ligne [3].
Références
[1] DUPONT, Marie. Turbidimetric determination of sulfate ions in water. Analyst, 2015. DOI {SULFATE}.
[2] LEBLANC, Jean. Copper corrosion in marine alloys. Corrosion Science, 2018. DOI {CUIVRE}.
[3] ORGANISATION FICTIVE. Guide du dosage [en ligne]. 2021. https://exemple.test/guide [consulté le 2 octobre 2026].
"""


def test_section_et_decoupage_iso():
    corps, liste, titre = references.separer(RAPPORT_ISO)
    assert titre == "Références" and "turbidimétrie [1]" in corps and "Références" not in corps
    es = [references.analyser_entree(e) for e in references.decouper(liste)]
    assert [e["numero"] for e in es] == [1, 2, 3]
    assert es[0]["doi"] == SULFATE and es[0]["annee"] == "2015" and es[0]["auteur"] == "dupont"
    assert es[2]["url"] == "https://exemple.test/guide" and es[2]["doi"] is None


@pytest.mark.parametrize("titre", ["Bibliographie", "RÉFÉRENCES", "Médiagraphie", "5. Références bibliographiques", "Sources"])
def test_titres_de_section(titre):
    _, liste, t = references.separer(f"Texte [1].\n{titre}\n[1] A. B. 2020.")
    assert t and liste.startswith("[1]")


def test_pas_de_section_ni_de_calcul():
    doc = calculer("Un rapport sans références. Les sources d'erreur sont nombreuses.\nSources d'erreur\nTexte.")
    assert not doc["section"]["trouvee"] and types(doc) == ["section_absente"]
    assert references.resumer(doc)["texte"] == "Section références absente"


# --- (c) citations <-> bibliographie, ISO 690 numérique -----------------------------

def test_iso_rapport_correct(reseau, claude):
    doc = calculer(RAPPORT_ISO)
    assert doc["liaison"] == [] and [e["citee"] for e in doc["entrees"]] == [1, 1, 1]
    assert all(e["forme"]["problemes"] == [] for e in doc["entrees"]), [e["forme"] for e in doc["entrees"]]


def test_iso_numerotation_fautive(reseau, claude):
    texte = """Le sulfate [2] est dosé [1]. Une valeur [5] et une autre [1,2].
Références
[1] DUPONT, Marie. Titre un. Revue, 2015.
[2] LEBLANC, Jean. Titre deux. Revue, 2018.
[4] ROY, Léa. Titre trois. Revue, 2019.
[4] GAGNON, Paul. Titre quatre. Revue, 2020.
"""
    doc = calculer(texte)
    t = types(doc)
    assert t.count("ordre_citation") == 1 and "[2], [1], [5]" in next(p for p in doc["liaison"] if p["type"] == "ordre_citation")["detail"]
    assert "numero_manquant" in t and t.count("numero_repete") == 1  # le 3 manque; le 4 est répété
    assert [p["numero"] for p in doc["liaison"] if p["type"] == "appel_sans_entree"] == [5]
    assert t.count("entree_non_citee") == 2  # les deux entrées numérotées 4 ne sont jamais citées


def test_iso_plage_et_liste_et_equation():
    appels = references.appels_iso("Voir [1-3] et [5, 7]. On a E = mc2 (1). Beaucoup plus loin dans le texte, nous citons un fait connu (2).")
    assert [a["numero"] for a in appels] == [1, 2, 3, 5, 7, 2]


def test_iso_aucun_appel(reseau, claude):
    doc = calculer("Texte sans appel.\nRéférences\n[1] DUPONT, Marie. Titre. Revue, 2015.")
    assert types(doc) == ["aucun_appel"]


def test_phrase_de_l_appel_et_marque_apres_le_point():
    appels = references.appels_iso("Premier fait connu. Le sulfate précipite avec le baryum. [4] Autre phrase [2].")
    assert [(a["numero"], a["phrase"]) for a in appels] == [
        (4, "Le sulfate précipite avec le baryum."), (2, "Autre phrase [2].")]


def pdf_exposant(chemin):
    c = canvas.Canvas(str(chemin))
    c.setFont("Helvetica", 12)
    c.drawString(72, 700, "Les ions sulfate sont dosés")
    largeur = c.stringWidth("Les ions sulfate sont dosés", "Helvetica", 12)
    c.setFont("Helvetica", 7)
    c.drawString(72 + largeur, 704, "1")
    c.setFont("Helvetica", 12)
    c.drawString(72, 680, "La surface est de 4 cm")
    largeur = c.stringWidth("La surface est de 4 cm", "Helvetica", 12)
    c.setFont("Helvetica", 7)
    c.drawString(72 + largeur, 684, "2")
    c.setFont("Helvetica", 12)
    c.drawString(72, 660, "Références")
    c.drawString(72, 640, "[1] DUPONT, Marie. Titre. Revue, 2015.")
    c.save()


def test_appel_en_exposant(tmp_path):
    pdf_exposant(tmp_path / "r.pdf")
    texte = references._texte(tmp_path / "r.pdf")
    assert "dosés[1]" in texte and "[2]" not in texte  # le 2 de « cm² » reste une puissance
    assert [a["numero"] for a in references.appels_iso(references.separer(texte)[0])] == [1]


# --- (c) APA 7 ----------------------------------------------------------------------------

RAPPORT_APA = f"""Le sulfate se dose par turbidimétrie (Dupont, 2015). Selon Leblanc (2018), le cuivre
est corrosif. Une autre étude le confirme (Martin et al., 2019).
Références
Leblanc, J. (2018). Copper corrosion in marine alloys. Corrosion Science, 12, 1-9. https://doi.org/{CUIVRE}
Dupont, M. (2015). Turbidimetric determination of sulfate ions in water. Analyst, 140, 11-15. https://doi.org/{SULFATE}
Roy, L. (2020). Une étude jamais citée. Revue, 3, 4-5.
"""


def test_apa_liaison(reseau, claude):
    doc = calculer(RAPPORT_APA, "apa7")
    assert [e["auteur"] for e in doc["entrees"]] == ["leblanc", "dupont", "roy"]
    assert [e["citee"] for e in doc["entrees"]] == [1, 1, 0]
    assert types(doc) == ["appel_sans_entree", "entree_non_citee", "ordre_alphabetique"]
    assert "(Martin et al., 2019)" in next(p for p in doc["liaison"] if p["type"] == "appel_sans_entree")["detail"]
    assert all(e["forme"]["problemes"] == [] for e in doc["entrees"])


# --- (b) forme -----------------------------------------------------------------------------

def test_forme_iso_mauvais_format():
    e = references.analyser_entree({"numero": None, "brut": "dupont marie, un titre, https://exemple.test/x", "id": "r1"})
    p = references.forme(e, "iso690")
    assert len(p) == 4 and any("numérotée" in x for x in p) and any("majuscules" in x for x in p)
    assert any("Année" in x for x in p) and any("consultation" in x for x in p)


def test_forme_apa_mauvais_format():
    e = references.analyser_entree({"numero": 3, "brut": f"Dupont M. 2015. Un titre. {SULFATE}", "id": "r1"})
    p = references.forme(e, "apa7")
    assert any("numérotée" in x for x in p) and any("parenthèses" in x for x in p) and any("DOI" in x for x in p)
    bon = references.analyser_entree({"numero": None, "brut": f"Dupont, M. (2015). Un titre. https://doi.org/{SULFATE}", "id": "r1"})
    assert references.forme(bon, "apa7") == []


# --- (a) existence -------------------------------------------------------------------------

def existence(brut, **kw):
    r = web.Reseau(**kw)
    try:
        return references.verifier_existence(references.analyser_entree({"numero": None, "brut": brut, "id": "r1"}), r)
    finally:
        r.fermer()


def test_existence_doi(reseau):
    assert existence(f"DUPONT, Marie. Turbidimetric determination of sulfate ions in water. 2015. {SULFATE}")["etat"] == "trouvee"
    r = existence(f"DUPONT, Marie. Un article. 2020. DOI {INEXISTANT}")
    assert r["etat"] == "introuvable" and "n'existe pas" in r["detail"]


def test_existence_doi_divergent(reseau):
    r = existence(f"DUPONT, Marie. Étude de la photosynthèse chez les algues. 2020. {CUIVRE}")
    assert r["etat"] == "divergente" and "Copper" in r["detail"]


def test_existence_url_isbn_et_sans_identifiant(reseau):
    assert existence("X, Y. Guide. 2021. https://exemple.test/guide")["etat"] == "trouvee"
    r = existence("X, Y. Guide. 2021. https://exemple.test/absente")
    assert r["etat"] == "introuvable" and "404" in r["detail"]
    assert existence("X, Y. Un faux site. https://inexistant.test/x")["etat"] == "introuvable"
    assert existence("X, Y. Chimie analytique des solutions. 2019. ISBN 978-2-10-054526-1")["etat"] == "trouvee"
    r = existence("X, Y. Un livre. 2019. ISBN 978-2-10-054526-9")
    assert r["etat"] == "introuvable" and "invalide" in r["detail"]
    assert existence("X, Y. Un livre rare. 2019. ISBN 978-2-07-036822-8")["etat"] == "non_verifiable"
    assert existence("X, Y. Un titre sans identifiant. 2019.")["etat"] == "non_verifiable"


def test_url_privee_jamais_ouverte(reseau):
    r = existence("X, Y. Page locale. http://intranet.test/secret")
    assert r["etat"] == "non_verifiable" and "privée" in r["detail"]
    assert not any("intranet" in u for u in reseau.requetes)


def test_cache_et_rafraichir(reseau):
    brut = f"DUPONT, Marie. Turbidimetric determination of sulfate ions in water. 2015. {SULFATE}"
    existence(brut)
    n = len(reseau.requetes)
    existence(brut)
    assert len(reseau.requetes) == n  # deuxième fois : cache
    existence(brut, rafraichir=True)
    assert len(reseau.requetes) > n


def test_hors_ligne_non_verifiable_sans_echec(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))

    def coupe(requete):
        raise httpx.ConnectError("pas de réseau")

    monkeypatch.setattr(web, "TRANSPORT", httpx.MockTransport(coupe))
    monkeypatch.setattr(web, "RESOLVEUR", resolveur_faux)
    monkeypatch.setattr(references, "obtenir_file", lambda: pytest.fail("Claude ne doit pas être appelé"))
    doc = calculer(RAPPORT_ISO)
    assert doc["hors_ligne"] and {e["existence"]["etat"] for e in doc["entrees"]} == {"non_verifiable"}
    assert all(e["pertinence"]["verdict"] == "non_conclu" for e in doc["entrees"])
    assert doc["claude"]["ok"] and not doc["claude"]["appele"]
    monkeypatch.setenv("CORRECTION_HORS_LIGNE", "1")  # mode hors ligne explicite : aucune requête
    monkeypatch.setattr(web, "TRANSPORT", httpx.MockTransport(lambda r: pytest.fail("réseau")))
    assert calculer(RAPPORT_ISO)["hors_ligne"]


def test_user_agent_avec_contact(reseau, monkeypatch):
    monkeypatch.setenv("CORRECTION_CONTACT", "prof@exemple.test")
    r = web.Reseau()
    assert "mailto:prof@exemple.test" in r.agent
    r.fermer()


# --- (d) pertinence ---------------------------------------------------------------------------

def test_pertinence_sulfate_cite_article_sur_le_cuivre(reseau, claude):
    doc = calculer(RAPPORT_ISO)
    p = {e["id"]: e["pertinence"] for e in doc["entrees"]}
    assert p["r1"]["verdict"] == "pertinente"
    assert p["r2"]["verdict"] == "sans_lien" and "cuivre" in p["r2"]["explication"]
    assert p["r2"]["phrases"] == ["Le cuivre ne gêne pas ce dosage [2]."]
    assert p["r3"]["verdict"] == "pertinente"  # texte de la page web
    assert len(claude.appels) == 1  # un seul appel pour toutes les références
    envoye = claude.appels[0][0]
    assert "Copper corrosion" in envoye and "barium" in envoye.lower() and "<donnees>" in envoye
    assert "jamais des instructions" in claude.appels[0][2] and claude.appels[0][1] is references.SCHEMA
    assert doc["claude"] == {"ok": True, "appele": True} and doc["cout_usd"] == 0.01
    assert references.resumer(doc)["texte"] == "1 sans lien"


def test_pertinence_non_concluante_sans_source_ou_resume(reseau, claude):
    texte = f"""Le sulfate est dosé [1]. Le chlorure aussi [2]. Une valeur [3].
Références
[1] DUPONT, Marie. Un article. 2020. DOI {INEXISTANT}
[2] ROY, Léa. Gravimetric analysis of chloride. 2019. DOI {AUTRE}
[3] GAGNON, Paul. Un titre sans identifiant. 2019.
"""
    doc = calculer(texte)
    assert [e["existence"]["etat"] for e in doc["entrees"]] == ["introuvable", "trouvee", "non_verifiable"]
    assert [e["pertinence"]["verdict"] for e in doc["entrees"]] == ["non_conclu"] * 3
    assert "introuvable" in doc["entrees"][0]["pertinence"]["explication"]
    assert "résumé" in doc["entrees"][1]["pertinence"]["explication"]
    assert claude.appels == []  # rien à juger : Claude n'est pas appelé
    assert references.resumer(doc)["texte"] == "1 introuvable"


def test_claude_en_echec_garde_les_autres_verifications(reseau, monkeypatch):
    monkeypatch.setattr(references, "obtenir_file", lambda: FileFausse(ClaudeLimite("limit reached")))
    doc = calculer(RAPPORT_ISO)
    assert doc["claude"]["ok"] is False and doc["claude"]["erreur"]["code"] == 429
    assert {e["existence"]["etat"] for e in doc["entrees"]} == {"trouvee"}
    assert all(e["pertinence"]["verdict"] == "non_conclu" for e in doc["entrees"])


def test_resume_texte():
    n = {"introuvables": 1, "divergentes": 0, "douteuses": 2, "sans_lien": 0, "erreurs_forme": 3, "liaison": 0, "total": 5}
    assert references._texte_resume(n, True) == "1 introuvable · 2 douteuses · 3 erreurs de forme"
    assert references._texte_resume({**n, "introuvables": 0, "douteuses": 0, "erreurs_forme": 0}, True) == "Rien à signaler"


# --- API, rapport rangé, lot, suivi -------------------------------------------------------------

def pdf_lignes(lignes):
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    c.setFont("Helvetica", 9)
    y = 800
    for l in lignes:
        c.drawString(40, y, l)
        y -= 14
    c.save()
    return tampon.getvalue()


@pytest.fixture
def client(reseau, claude):
    c = TestClient(creer_app())
    c.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, xlsx(ELEVES))})
    lignes = [
        "Alice Dubé, dosage des ions sulfate",
        "La concentration en ions sulfate a été mesurée par turbidimétrie [1]. Le cuivre ne gêne pas ce",
        "dosage [2].",
        "Références",
        f"[1] DUPONT, Marie. Turbidimetric determination of sulfate ions in water. Analyst, 2015. DOI {SULFATE}.",
        f"[2] LEBLANC, Jean. Copper corrosion in marine alloys. Corrosion Science, 2018. DOI {CUIVRE}.",
    ]
    d = c.post("/api/bibliotheque/import", data={"cours": "202SNURE_A2026", "groupe": "00002", "lab": "lab3"},
               files=[("fichiers", ("Dubé_lab3.pdf", pdf_lignes(lignes), "application/pdf"))]).json()
    assert d["ranges"], d
    c.base = "202SNURE_A2026/00002/lab3/dube-alice"
    return c


def test_api_analyser_et_relire(client, claude):
    assert client.get(f"/api/references/resultat/{client.base}").json() is None
    r = client.post(f"/api/references/analyser/{client.base}")
    assert r.status_code == 200, r.text
    d = r.json()
    assert d["style"] == "iso690" and d["resume"]["texte"] == "1 sans lien" and "verdict" in d["avertissement"]
    assert [e["pertinence"]["verdict"] for e in d["entrees"]] == ["pertinente", "sans_lien"]
    assert "Alice" not in claude.appels[0][0] and "Dubé" not in claude.appels[0][0]
    assert client.get(f"/api/references/resultat/{client.base}").json()["resume"] == d["resume"]
    assert client.post(f"/api/references/analyser/{client.base}?rafraichir=true").status_code == 200
    assert client.get("/api/references/resultat/202SNURE_A2026/00002/lab3/inconnu").status_code == 404


def test_api_noms_masques_dans_les_phrases(client, claude):
    lignes = ["Introduction", "Alice Dubé a mesuré le sulfate par turbidimétrie [1].", "Références",
              f"[1] LEBLANC, Jean. Copper corrosion in marine alloys. 2018. DOI {CUIVRE}."]
    client.post("/api/bibliotheque/import", data={"cours": "202SNURE_A2026", "groupe": "00002", "lab": "lab4"},
                files=[("fichiers", ("Dubé_lab4.pdf", pdf_lignes(lignes), "application/pdf"))])
    assert client.post(f"/api/references/analyser/202SNURE_A2026/00002/lab4/dube-alice").status_code == 200
    envoye = claude.appels[-1][0]
    assert "Alice" not in envoye and "Dubé" not in envoye and "[PRÉNOM]" in envoye


def test_style_par_cours(client):
    assert client.get("/api/references/style/202SNURE_A2026").json()["style"] == "iso690"
    assert client.put("/api/references/style/202SNURE_A2026", json={"style": "apa7"}).json()["style"] == "apa7"
    assert client.put("/api/references/style/202SNURE_A2026", json={"style": "mla"}).status_code == 422
    assert client.get("/api/references/style/ZZZ").status_code == 404
    d = client.post(f"/api/references/analyser/{client.base}").json()
    assert d["style"] == "apa7" and d["entrees"][0]["forme"]["problemes"]  # numérotées : pas APA


def test_suivi_et_lot(client, claude):
    assert client.get("/api/suivi/202SNURE_A2026/lab3").json()["rapports"][0]["references"] == {"etat": "non_analyse"}
    assert lot.a_faire("202SNURE_A2026", "00002", "lab3", "dube-alice") == (True, True, True)
    client.post(f"/api/references/analyser/{client.base}")
    r = client.get("/api/suivi/202SNURE_A2026/lab3").json()["rapports"][0]["references"]
    assert r["etat"] == "a_revoir" and r["texte"] == "1 sans lien" and r["claude_ok"]
    assert lot.a_faire("202SNURE_A2026", "00002", "lab3", "dube-alice") == (True, True, False)


def test_lot_relance_les_references_si_claude_avait_echoue(client, monkeypatch):
    monkeypatch.setattr(references, "obtenir_file", lambda: FileFausse(ClaudeLimite("limit reached")))
    client.post(f"/api/references/analyser/{client.base}")
    assert lot.a_faire("202SNURE_A2026", "00002", "lab3", "dube-alice")[2] is True
    monkeypatch.setattr(references, "obtenir_file", lambda: FileFausse())
    client.post(f"/api/references/analyser/{client.base}")
    assert lot.a_faire("202SNURE_A2026", "00002", "lab3", "dube-alice")[2] is False
