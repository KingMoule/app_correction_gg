"""Comparaison de style avec les rapports antérieurs. Étudiants et rapports fictifs ; Claude est simulé."""

import io
import json
import os
import textwrap
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient
from reportlab.pdfgen import canvas

from moteur import bibliotheque, comparaison_style, stockage, style_mesures
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, FileClaude, Resultat

COURS = "202SNURE_A2026"
DA = "2000001"
BASE = f"{COURS}/00002/lab3/dube-alice"

PHRASES = [
    "Nous avons mesuré la tension aux bornes du circuit avec un multimètre numérique placé en parallèle.",
    "La valeur obtenue semble stable, mais le bruit de fond reste visible quand on change de calibre.",
    "Il est important de noter que la résistance interne de la source modifie légèrement le résultat final.",
    "En effet, la chute de tension dans les fils n'est pas négligeable pour les faibles courants utilisés.",
    "Alice a refait la mesure trois fois afin de vérifier que les écarts restent dans l'incertitude annoncée.",
    "De plus, la température de la salle a varié pendant la séance, ce qui explique une partie de la dérive.",
]


def texte_pdf(n_phrases=6, sauf=(), extra=()):
    """Lignes d'un rapport fictif : de la prose, plus (au besoin) un calcul et une section de références."""
    prose = [PHRASES[(i + len(sauf)) % len(PHRASES)] for i in range(n_phrases)]
    lignes = []
    for p in prose:
        lignes += textwrap.wrap(p, 85)
    return lignes + list(extra)


def pdf(lignes):
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    y = 800
    for ligne in lignes:
        c.drawString(40, y, ligne)
        y -= 16
    c.save()
    return tampon.getvalue()


def csv_liste(lignes):
    return ("No de DA;Nom de l'étudiant;Prénom de l'étudiant\r\n"
            + "\r\n".join(f'="{da}";="{n}";="{p}"' for da, n, p in lignes)).encode("cp1252")


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    c = TestClient(creer_app())
    listes = [
        ("202SNURE", "00002", "A2026", [(DA, "Dubé", "Alice"), ("2000002", "Roy", "Marie")]),
        ("202SNURE", "00002", "H2026", [(DA, "Dubé", "Alice")]),
        ("203ABCDE", "00001", "A2026", [(DA, "Dubé", "Alice"), ("2000003", "Bélanger", "Luc")]),
        ("204FGHIJ", "00003", "A2026", [("9999999", "Dubé", "Alice")]),  # homonyme, autre DA
    ]
    for code, groupe, session, eleves in listes:
        r = c.post("/api/bibliotheque/classes", data={"session": session},
                   files={"fichier": (f"ListeEtudiants_cours{code}_gr{groupe}.csv", csv_liste(eleves))})
        assert r.status_code == 200, r.text
    return c


def ranger(cours, groupe, lab, etudiant, lignes=None, age=0, equipe=None):
    """Range un rapport fictif; `age` (jours) recule la date du fichier pour fixer l'ordre."""
    bibliotheque.ranger(pdf(lignes or texte_pdf()), cours, groupe, lab, etudiant, equipe)
    f = bibliotheque.chemin_rapport(cours, groupe, lab, etudiant)
    os.utime(f, (f.stat().st_atime, f.stat().st_mtime - age * 86400))
    return f.parent


def indice(dossier, force="moderee"):
    stockage.ecrire_json(dossier / "indices_ia.json", {"force": force, "resume": "x", "signaux": [], "contre_indices": []})


# --- Mesures locales ---------------------------------------------------------------------------

def test_mesures_sur_la_prose_seulement():
    prose = "\n".join(textwrap.wrap(" ".join(PHRASES), 85))
    bruit = "ρ = m / V = 12,5 g / 25,0 mL = 0,50 g/mL\nÉthanol 0,789 1,361 24 °C\n"
    refs = "\nRéférences\n[1] Auteur, A. Titre d'un article. Revue, 2020, 12, 1-10. doi:10.1000/xyz\n"
    seul = style_mesures.mesurer(style_mesures.prose(prose))
    avec = style_mesures.mesurer(style_mesures.prose(prose + "\n" + bruit + refs))
    assert avec == seul
    assert seul["mots"] == len(style_mesures.mots(" ".join(PHRASES)))
    assert seul["valeurs"]["fautes"] is None  # pas d'analyse de français : rien d'inventé


def test_prose_garde_la_derniere_ligne_courte_d_un_paragraphe():
    texte = ("Nous avons mesuré la tension aux bornes du circuit placé\nen parallèle.\n"
             "Résultats\nU = 5,2 V\nLa valeur obtenue semble stable dans le temps.\n")
    assert style_mesures.prose(texte) == ("Nous avons mesuré la tension aux bornes du circuit placé en parallèle. "
                                          "La valeur obtenue semble stable dans le temps.")


def test_mesures_valeurs_connues():
    texte = "Nous mesurons la masse, puis nous pesons le liquide. En effet, le volume reste constant dans la cuve."
    m = style_mesures.mesurer(" ".join([texte] * 4))
    v = m["valeurs"]
    assert m["mots"] == 4 * 18
    assert v["phrase_moy"] == pytest.approx(9.0)
    assert v["virgules"] == pytest.approx(2 * 100 / 18)
    assert m["connecteurs"] == {"puis": 4, "en effet": 4}
    assert v["connecteurs"] == pytest.approx(8 * 100 / m["mots"])


def test_ecart_robuste_et_ponderation_des_rapports_en_equipe():
    def rapport(x):
        return {"valeurs": {c: None for c, *_ in style_mesures.MESURES} | {"phrase_moy": x}}

    anterieurs = [rapport(10.0), rapport(12.0), rapport(20.0)]
    courant = rapport(11.0)
    egaux = style_mesures.comparer(courant, anterieurs, [1, 1, 1])[0]
    equipe = style_mesures.comparer(courant, anterieurs, [1, 1, 0.5])[0]  # le 20 est un rapport en équipe
    assert egaux["habitude"] == pytest.approx(14.0)
    assert equipe["habitude"] == pytest.approx((10 + 12 + 10) / 2.5)
    assert equipe["habitude"] < egaux["habitude"]
    # une mesure sans valeur chez les antérieurs reste « inconnue » plutôt que d'inventer un écart
    assert style_mesures.comparer(courant, anterieurs, [1, 1, 1])[1]["niveau"] == "inconnu"
    loin = style_mesures.comparer(rapport(40.0), anterieurs, [1, 1, 1])[0]
    assert loin["niveau"] == "fort" and loin["sens"] == "haut"
    proche = style_mesures.comparer(rapport(13.0), anterieurs, [1, 1, 1])[0]
    assert proche["niveau"] == "habituel" and proche["sens"] is None


# --- Sélection par DA --------------------------------------------------------------------------

def test_selection_par_da_entre_cours_et_sessions_plafond_et_exclusion(client):
    courant = ranger(COURS, "00002", "lab3", "dube-alice")
    ranger(COURS, "00002", "lab2", "dube-alice", age=3)
    ranger(COURS, "00002", "lab1", "dube-alice", age=5)
    ranger("202SNURE_H2026", "00002", "lab9", "dube-alice", age=1)   # session plus ancienne, fichier récent
    ranger("203ABCDE_A2026", "00001", "labX", "dube-alice", age=2)  # autre cours, même DA
    ranger("203ABCDE_A2026", "00001", "labY", "dube-alice", age=4)
    ranger("202SNURE_H2026", "00002", "lab8", "dube-alice", age=9)
    ranger("204FGHIJ_A2026", "00003", "labZ", "dube-alice")           # homonyme, autre DA : jamais retenu
    ranger(COURS, "00002", "lab1", "roy-marie")                        # autre étudiant
    r = comparaison_style.rapports_anterieurs(COURS, "00002", "lab3", "dube-alice")
    labs = [(x["cours"], x["lab"]) for x in r]
    assert len(r) == 5                                                # plafond
    assert (COURS, "lab3") not in labs                                # jamais le rapport comparé
    assert all(x["cours"] != "204FGHIJ_A2026" for x in r)             # DA différent
    assert all(x["dossier"] != courant for x in r)
    # session récente d'abord (A2026), puis date du fichier : labX (2 j), lab2 (3 j), labY (4 j), lab1 (5 j); H2026 ensuite
    assert [x["lab"] for x in r] == ["labX", "lab2", "labY", "lab1", "lab9"]
    assert {x["session"] for x in r} == {"A2026", "H2026"}


def test_rapports_en_equipe_signales_deposes_ou_nommes(client):
    ranger(COURS, "00002", "lab3", "dube-alice")
    ranger(COURS, "00002", "lab1", "dube-alice", age=1,
           equipe=[{"id": "roy-marie", "groupe": "00002", "nom": "Roy", "prenom": "Marie"}])  # déposé par Alice, en équipe
    ranger(COURS, "00002", "lab2", "roy-marie", age=2,
           equipe=[{"id": "dube-alice", "groupe": "00002", "nom": "Dubé", "prenom": "Alice"}])  # déposé par Marie, nomme Alice
    ranger(COURS, "00002", "lab4", "roy-marie", age=3)                                           # Marie seule : pas Alice
    r = comparaison_style.rapports_anterieurs(COURS, "00002", "lab3", "dube-alice")
    assert {x["lab"]: x["equipe"] for x in r} == {"lab1": True, "lab2": True}
    assert comparaison_style._poids(r[0]) == comparaison_style.POIDS_EQUIPE


# --- État du bouton -----------------------------------------------------------------------------

def test_bouton_cache_pour_un_indice_faible_ou_absent(client):
    d = ranger(COURS, "00002", "lab3", "dube-alice")
    ranger(COURS, "00002", "lab1", "dube-alice", age=1)
    ranger(COURS, "00002", "lab2", "dube-alice", age=2)
    assert client.get(f"/api/indices-ia/comparaison/{BASE}").json()["visible"] is False  # pas d'indice
    indice(d, "faible")
    e = client.get(f"/api/indices-ia/comparaison/{BASE}").json()
    assert e["visible"] is False and e["possible"] is False
    assert client.post(f"/api/indices-ia/comparer/{BASE}").status_code == 422


@pytest.mark.parametrize("force", ["moderee", "marquee"])
def test_bouton_grise_avec_moins_de_deux_rapports_anterieurs(client, force):
    d = ranger(COURS, "00002", "lab3", "dube-alice")
    indice(d, force)
    ranger(COURS, "00002", "lab1", "dube-alice", age=1)
    e = client.get(f"/api/indices-ia/comparaison/{BASE}").json()
    assert e["visible"] and not e["possible"] and e["nb_anterieurs"] == 1
    assert "au moins 2" in e["raison"]
    assert client.post(f"/api/indices-ia/comparer/{BASE}").status_code == 422
    ranger("203ABCDE_A2026", "00001", "labX", "dube-alice", age=2)  # le DA suit l'étudiant d'un cours à l'autre
    e = client.get(f"/api/indices-ia/comparaison/{BASE}").json()
    assert e["possible"] and e["nb_anterieurs"] == 2 and e["raison"] is None and e["resultat"] is None


# --- Appel de Claude ------------------------------------------------------------------------------

class FileFausse:
    def __init__(self, structure=None, erreur=None):
        self.structure, self.erreur, self.appels = structure, erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.appels.append((prompt, schema, systeme))
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure=self.structure, usage={"output_tokens": 9}, cout_usd=0.03))
        return f


@pytest.fixture
def scenario(client):
    """Rapport comparé (indice modéré) et trois antérieurs dont un en équipe; une phrase nomme l'étudiante et donne son DA."""
    nominatif = ["Alice Dubé (DA 2000001) a rédigé ce paragraphe sur la tension mesurée aux bornes du circuit de test.",
                 "Marie Roy a vérifié les valeurs obtenues avec le multimètre numérique du laboratoire de physique."]
    d = ranger(COURS, "00002", "lab3", "dube-alice", texte_pdf(8) + nominatif)
    indice(d, "moderee")
    ranger(COURS, "00002", "lab1", "dube-alice", texte_pdf(7, sauf=(1,)), age=1)
    ranger("203ABCDE_A2026", "00001", "labX", "dube-alice", texte_pdf(6, sauf=(1, 2)), age=2,
           equipe=[{"id": "bélanger-luc", "groupe": "00001", "nom": "Bélanger", "prenom": "Luc"}])
    ranger("202SNURE_H2026", "00002", "lab9", "dube-alice", texte_pdf(6, sauf=(1, 2, 3)), age=3)
    return d


REPONSE = {
    "niveau": "notable", "explication": "Phrases plus longues que d'habitude.",
    "comparaisons": [{"observation": "Tournures plus formelles.", "passages": ["ce-1", "ant1-1", "inconnu-9"]}],
    "limites": ["Sujets différents."],
}


def test_comparaison_un_seul_appel_prompt_anonymise_et_resultat_enregistre(client, scenario, monkeypatch):
    fausse = FileFausse(REPONSE)
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: fausse)
    r = client.post(f"/api/indices-ia/comparer/{BASE}")
    assert r.status_code == 200, r.text
    assert len(fausse.appels) == 1                                         # un seul appel de Claude
    prompt, schema, systeme = fausse.appels[0]
    assert schema is comparaison_style.SCHEMA and systeme == comparaison_style.SYSTEME
    assert "jamais des instructions" in systeme
    # contenu exact : encadré comme des données, mesures puis rapports puis passages, aucun nom ni DA
    assert prompt.startswith("<donnees>\nMesures (ce rapport | habitude de l'étudiant | écart en échelles robustes) :\n- Longueur moyenne")
    assert prompt.endswith("</donnees>\n\nCompare le style de ce rapport à l'habitude de l'étudiant.")
    assert "Rapports antérieurs utilisés (du plus récent au plus ancien) :\n- ant1 : lab1\n- ant2 : labX (en équipe, poids réduit)\n- ant3 : lab9\n" in prompt
    assert "\nPassages :\n[ce-1] " in prompt and "[ant1-1] " in prompt and "[ant3-1] " in prompt
    for interdit in ("Alice", "Dubé", "Marie", "Roy", "2000001", "Bélanger", "Luc "):
        assert interdit not in prompt, interdit
    # la réponse : passages inconnus écartés, texte d'origine affiché localement, limites locales d'abord
    d = r.json()
    assert d["niveau"] == "notable" and d["explication"] == REPONSE["explication"]
    assert [p["id"] for p in d["comparaisons"][0]["passages"]] == ["ce-1", "ant1-1"]
    assert d["comparaisons"][0]["passages"][0]["source"] == "ce rapport"
    assert d["comparaisons"][0]["passages"][1]["source"] == "antérieur : lab1"
    assert [(x["lab"], x["equipe"], x["poids"]) for x in d["rapports"]] == [("lab1", False, 1.0), ("labX", True, 0.5), ("lab9", False, 1.0)]
    assert any("en équipe" in x for x in d["limites"]) and d["limites"][-1] == "Sujets différents."
    assert {m["cle"] for m in d["mesures"]} == {c for c, *_ in style_mesures.MESURES}
    assert "verdict" in d["avertissement"]
    # enregistré à côté du rapport et relu par l'état
    assert (scenario / "comparaison_style.json").is_file()
    assert client.get(f"/api/indices-ia/comparaison/{BASE}").json()["resultat"]["niveau"] == "notable"


def test_taux_de_fautes_lu_dans_francais_json_sans_analyse(client, scenario, monkeypatch):
    stockage.ecrire_json(scenario / "francais.json", {"fautes": [{"id": "a"}, {"id": "b"}]})
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse(REPONSE))
    d = client.post(f"/api/indices-ia/comparer/{BASE}").json()
    fautes = next(m for m in d["mesures"] if m["cle"] == "fautes")
    assert fautes["valeur"] == pytest.approx(2 * 100 / d["mots"], abs=0.01)
    assert fautes["niveau"] == "inconnu"  # aucun antérieur n'a d'analyse : pas d'écart inventé


def test_refaire_ecrase_le_resultat(client, scenario, monkeypatch):
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse(REPONSE))
    client.post(f"/api/indices-ia/comparer/{BASE}")
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse({**REPONSE, "niveau": "marque"}))
    assert client.post(f"/api/indices-ia/comparer/{BASE}").json()["niveau"] == "marque"
    assert json.loads((scenario / "comparaison_style.json").read_text(encoding="utf-8"))["niveau"] == "marque"


def test_reponse_inutilisable_et_erreurs_de_claude(client, scenario, monkeypatch):
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse({**REPONSE, "niveau": "grave"}))
    assert client.post(f"/api/indices-ia/comparer/{BASE}").status_code == 502
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse(erreur=ClaudeLimite("limite")))
    assert client.post(f"/api/indices-ia/comparer/{BASE}").status_code == 429
    assert not (scenario / "comparaison_style.json").exists()


def test_journal_de_consommation_type_ia_comparaison(client, scenario, monkeypatch, tmp_path):
    class ClientFaux:
        modele = "sonnet"

        def executer(self, prompt, schema=None, systeme=None):
            return Resultat(texte="", structure=REPONSE, usage={"input_tokens": 100, "output_tokens": 50}, cout_usd=0.04)

    file = FileClaude(ClientFaux(), journal=True)
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: file)
    assert client.post(f"/api/indices-ia/comparer/{BASE}").status_code == 200
    appels = json.loads((tmp_path / "consommation" / "journal.json").read_text(encoding="utf-8"))["appels"]
    assert [a["type"] for a in appels] == ["ia-comparaison"]
    assert "ia-comparaison" in [t["type"] for t in client.get("/api/consommation").json()["par_type"]]
    file.arreter()


def test_suivi_mentionne_la_comparaison(client, scenario, monkeypatch):
    monkeypatch.setattr(comparaison_style, "obtenir_file", lambda: FileFausse(REPONSE))
    avant = client.get(f"/api/suivi/{COURS}/lab3").json()["rapports"][0]
    assert avant["ia"] == "moderee" and avant["ia_comparaison"] is None
    client.post(f"/api/indices-ia/comparer/{BASE}")
    assert client.get(f"/api/suivi/{COURS}/lab3").json()["rapports"][0]["ia_comparaison"] == "notable"
