"""Tests du plagiat. Textes et étudiants fictifs ; Claude est simulé (aucun appel réel)."""

import io
import time
from concurrent.futures import Future

import pytest
from fastapi.testclient import TestClient
from openpyxl import Workbook
from reportlab.pdfgen import canvas

from moteur import plagiat
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, Resultat


NOM_LISTE = "ListeEtudiants_cours202SNURE_gr00002.xlsx"


def xlsx(lignes) -> bytes:
    wb = Workbook()
    for ligne in lignes:
        wb.active.append(ligne)
    tampon = io.BytesIO()
    wb.save(tampon)
    return tampon.getvalue()


ENONCE = ("Objectif du laboratoire : mesurer la resistance equivalente d'un circuit en serie "
          "puis en parallele avec un multimetre numerique et comparer aux valeurs theoriques calculees.")
COMMUN = ("nous avons observe que la tension aux bornes de la resistance diminue lorsque la temperature "
          "augmente ce qui confirme la dependance attendue du materiau utilise dans le circuit")
ELEVES = [["Nom", "Prénom"], ["Alpha", "Anne"], ["Beta", "Boris"], ["Gamma", "Gaëlle"], ["Delta", "Denis"]]


def pdf(*paragraphes: str) -> bytes:
    tampon = io.BytesIO()
    c = canvas.Canvas(tampon)
    y = 800
    for para in paragraphes:
        mots, ligne = para.split(), ""
        for m in mots:
            if len(ligne) + len(m) > 80:
                c.drawString(40, y, ligne)
                y -= 14
                ligne = ""
            ligne += m + " "
        c.drawString(40, y, ligne)
        y -= 20
    c.save()
    return tampon.getvalue()


class FileFactice:
    def __init__(self, reponse=None, erreur=None):
        self.reponse, self.erreur, self.prompts = reponse, erreur, []

    def soumettre(self, prompt, schema=None, systeme=None):
        self.prompts.append(prompt)
        f = Future()
        if self.erreur:
            f.set_exception(self.erreur)
        else:
            f.set_result(Resultat(texte="", structure=self.reponse))
        return f


@pytest.fixture
def client(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    plagiat._en_cours.clear()
    c = TestClient(creer_app())
    assert c.post("/api/bibliotheque/classes", files={"fichier": (NOM_LISTE, xlsx(ELEVES))}).status_code == 200
    return c


def comparer(client) -> dict:
    """Lance la comparaison (arrière-plan), attend sa fin et renvoie la liste des paires comme avant."""
    assert client.post("/api/plagiat/comparer").status_code == 200
    etat = plagiat.attendre_comparaison()
    assert etat["etat"] == "termine", etat
    return {**etat, **client.get("/api/plagiat/paires").json()}


def importer(client, lab, **rapports):
    """rapports : nom de famille -> PDF."""
    r = client.post("/api/bibliotheque/import", data={"cours": "202SNURE_A2026", "groupe": "00002", "lab": lab},
                    files=[("fichiers", (f"{n}.pdf", p, "application/pdf")) for n, p in rapports.items()])
    assert r.status_code == 200 and not r.json()["en_attente"], r.json()


def test_paire_copiee_detectee_et_independants_non(client):
    original = "Introduction. " + COMMUN + " Conclusion personnelle de la premiere equipe sur les erreurs de mesure."
    copie = "Resume different. " + COMMUN + " Autre conclusion tres differente ecrite par une autre equipe de labo."
    independant = "Texte entierement different sur les moteurs electriques et les champs magnetiques rotatifs en regime permanent."
    importer(client, "lab-1", Alpha=pdf(original), Beta=pdf(copie), Gamma=pdf(independant))
    r = comparer(client)
    assert r["rapports"] == 3
    assert len(r["paires"]) == 1
    p = r["paires"][0]
    assert {p["a"]["etudiant"], p["b"]["etudiant"]} == {"alpha-anne", "beta-boris"}
    assert p["score"] > 0.5 and p["statut"] == "a_confirmer"
    d = client.get(f"/api/plagiat/paires/{p['cle']}").json()
    assert len(d["passages"]) == 1
    assert "tension aux bornes de la resistance" in d["passages"][0]["texte_a"]
    assert d["passages"][0]["texte_a"] == d["passages"][0]["texte_b"]


def test_un_mot_change_coupe_le_passage_mais_les_deux_morceaux_restent(client):
    a = pdf("zero un deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze")
    b = pdf("zero un deux trois quatre cinq six sept huit neuf XXX onze douze treize quatorze quinze seize")
    importer(client, "lab-1", Alpha=a, Beta=b)
    p = comparer(client)["paires"][0]
    d = client.get(f"/api/plagiat/paires/{p['cle']}").json()
    assert [x["mots"] for x in d["passages"]] == [10]  # le morceau de 5 mots après le mot changé est trop court


def test_enonce_ignore(client):
    a = pdf(ENONCE + " Mes resultats personnels sont presentes dans le tableau un ci joint.")
    b = pdf(ENONCE + " Voici ce que mon equipe a obtenu pendant la seance de mercredi apres midi.")
    importer(client, "lab-1", Alpha=a, Beta=b)
    assert len(comparer(client)["paires"]) == 1
    r = client.post("/api/plagiat/enonces/202SNURE_A2026/lab-1", files={"pdf": ("e.pdf", pdf(ENONCE), "application/pdf")})
    assert r.status_code == 200
    assert client.get("/api/plagiat/enonces").json() == [{"cours": "202SNURE_A2026", "lab": "lab-1"}]
    assert comparer(client)["paires"] == []


def test_meme_etudiant_et_labs_differents(client):
    texte = pdf(COMMUN)
    importer(client, "lab-1", Alpha=texte, Delta=pdf("autre sujet sans rapport avec les resistances ni aucun autre texte ici"))
    importer(client, "lab-2", Alpha=texte)  # même étudiant : ignoré
    assert comparer(client)["paires"] == []
    importer(client, "lab-2", Beta=texte)   # autre étudiant, ancien lab : repéré
    p = comparer(client)["paires"]
    # Beta est comparé aux deux copies d'Alpha, mais Alpha n'est jamais comparé à lui-même.
    assert len(p) == 2 and all("beta-boris" in (x["a"]["etudiant"], x["b"]["etudiant"]) for x in p)


def test_seuil_reglable(client):
    importer(client, "lab-1",
             Alpha=pdf(COMMUN + " fin une deux trois quatre cinq six sept huit neuf dix onze douze treize quatorze quinze seize dixsept dixhuit dixneuf vingt"),
             Beta=pdf(COMMUN + " autre fin tout a fait differente puisque ecrite separement par un autre etudiant ensuite apres"))
    p = comparer(client)["paires"][0]
    assert p["statut"] == "a_confirmer"
    client.put("/api/plagiat/reglages", json={"seuil": 0.99})
    assert client.get("/api/plagiat/paires").json()["paires"][0]["statut"] == "sous_seuil"
    assert client.put("/api/plagiat/reglages", json={"seuil": 2}).status_code == 422


def _paire_copiee(client):
    importer(client, "lab-1", Alpha=pdf(COMMUN + " fin A"), Beta=pdf(COMMUN + " fin B"))
    return comparer(client)["paires"][0]["cle"]


def attendre(client, cle, statut):
    for _ in range(50):
        p = next(x for x in client.get("/api/plagiat/paires").json()["paires"] if x["cle"] == cle)
        if p["statut"] == statut:
            return p
        time.sleep(0.05)
    raise AssertionError(p["statut"])


def test_rien_envoye_sans_confirmation_puis_verdict(client, monkeypatch):
    file = FileFactice({"verdict": "copie", "confiance": "elevee", "explication": "Texte identique."})
    monkeypatch.setattr(plagiat, "file_claude", lambda: file)
    cle = _paire_copiee(client)
    assert file.prompts == []  # la comparaison seule n'appelle jamais Claude
    assert client.post(f"/api/plagiat/paires/{cle}/confirmer").json()["statut"] == "en_cours"
    p = attendre(client, cle, "analysee")
    assert p["resultat"]["verdict"] == "copie" and p["resultat"]["explication"] == "Texte identique."
    assert len(file.prompts) == 1
    # Ni noms d'étudiants ni identifiants dans ce qui part chez Claude.
    for mot in ("Alpha", "Beta", "Anne", "alpha-anne", "202SNURE_A2026"):
        assert mot not in file.prompts[0]
    assert "tension aux bornes" in file.prompts[0]


def test_erreur_claude_gardee_et_nouvelle_tentative(client, monkeypatch):
    monkeypatch.setattr(plagiat, "file_claude", lambda: FileFactice(erreur=ClaudeLimite("Limite atteinte")))
    cle = _paire_copiee(client)
    client.post(f"/api/plagiat/paires/{cle}/confirmer")
    p = attendre(client, cle, "erreur")
    assert "Limite atteinte" in p["resultat"]["erreur"]
    monkeypatch.setattr(plagiat, "file_claude", lambda: FileFactice({"verdict": "coincidence", "confiance": "faible", "explication": "x"}))
    client.post(f"/api/plagiat/paires/{cle}/confirmer")
    assert attendre(client, cle, "analysee")["resultat"]["verdict"] == "coincidence"


def test_ecarter_et_paire_inconnue(client, monkeypatch):
    file = FileFactice({"verdict": "copie", "confiance": "elevee", "explication": "x"})
    monkeypatch.setattr(plagiat, "file_claude", lambda: file)
    cle = _paire_copiee(client)
    client.post(f"/api/plagiat/paires/{cle}/ecarter")
    assert client.get("/api/plagiat/paires").json()["paires"][0]["statut"] == "ecartee"
    assert client.post("/api/plagiat/paires/inconnue/confirmer").status_code == 404
    assert file.prompts == []


def test_enonce_consultable_et_remplacable(client):
    assert client.get("/api/plagiat/enonces/202SNURE_A2026/Lab 3").status_code == 404
    for texte in ("Enonce un deux trois", "Enonce remplace quatre cinq"):
        r = client.post("/api/plagiat/enonces/202SNURE_A2026/Lab 3", files={"pdf": ("e.pdf", pdf(texte), "application/pdf")})
        assert r.status_code == 200
    r = client.get("/api/plagiat/enonces/202SNURE_A2026/Lab 3")
    assert r.status_code == 200 and r.headers["content-type"] == "application/pdf"
    assert client.get("/api/plagiat/enonces").json() == [{"cours": "202SNURE_A2026", "lab": "lab-3"}]


# --- Plagiat à l'échelle (audit M7) ----------------------------------------------------

def _remplissage(prefixe: str, n: int) -> str:
    return " ".join(f"{prefixe}{i}x" for i in range(n))


def _lire_paires_json(tmp_path):
    import json
    return json.loads((tmp_path / "plagiat" / "paires.json").read_text(encoding="utf-8"))


def _paire_faible(client):
    """Deux rapports de 300 mots qui partagent 10 mots seulement (environ 3 %, sous le plancher)."""
    commun = "un deux trois quatre cinq six sept huit neuf dix"
    importer(client, "lab-1", Alpha=pdf(_remplissage("aa", 150) + " " + commun + " " + _remplissage("ab", 150)),
             Beta=pdf(_remplissage("ba", 150) + " " + commun + " " + _remplissage("bb", 150)))


def test_plancher_ecarte_les_paires_trop_faibles(client, tmp_path):
    _paire_faible(client)
    r = comparer(client)
    assert r["paires"] == [] and _lire_paires_json(tmp_path)["paires"] == []
    assert not list((tmp_path / "plagiat" / "passages").glob("*.json"))
    assert r["plancher"] == plagiat.PLANCHER


def test_plancher_garde_une_paire_qui_a_une_decision(client, tmp_path):
    _paire_faible(client)
    rapports, _ = plagiat.charger_rapports()
    assert plagiat.comparer_rapports(rapports, decidees=set()) == []  # sous le plancher, sans décision
    cle = "-".join(sorted(r.sha[:12] for r in rapports))
    toutes = plagiat.comparer_rapports(rapports, decidees={cle})
    assert len(toutes) == 1 and toutes[0]["score"] < plagiat.PLANCHER and toutes[0]["cle"] == cle
    plagiat._ecrire("decisions.json", {cle: {"statut": "ecartee"}})
    r = comparer(client)
    assert [p["statut"] for p in r["paires"]] == ["ecartee"]
    assert (tmp_path / "plagiat" / "passages" / f"{cle}.json").is_file()


def test_passages_a_part_et_charges_a_la_demande(client, tmp_path, monkeypatch):
    cle = _paire_copiee(client)
    brut = _lire_paires_json(tmp_path)
    assert brut["version"] == plagiat.VERSION_PAIRES
    assert all("passages" not in p for p in brut["paires"])  # paires.json reste léger
    assert (tmp_path / "plagiat" / "passages" / f"{cle}.json").is_file()
    assert all("passages" not in p for p in client.get("/api/plagiat/paires").json()["paires"])
    assert len(client.get(f"/api/plagiat/paires/{cle}").json()["passages"]) == 1
    # Passages absents (fichier supprimé) : message clair, pas d'envoi à Claude.
    (tmp_path / "plagiat" / "passages" / f"{cle}.json").unlink()
    assert client.get(f"/api/plagiat/paires/{cle}").status_code == 404
    file = FileFactice({"verdict": "copie", "confiance": "elevee", "explication": "x"})
    monkeypatch.setattr(plagiat, "file_claude", lambda: file)
    assert client.post(f"/api/plagiat/paires/{cle}/confirmer").status_code == 404 and file.prompts == []
    assert client.get("/api/plagiat/paires/..%2Fdecisions").status_code == 404


def test_migration_de_l_ancien_format_garde_les_decisions(client, tmp_path):
    ident = lambda e: {"cours": "202SNURE_A2026", "groupe": "00002", "lab": "lab-1", "etudiant": e, "nom": e}  # noqa: E731
    passage = {"a": [0, 9], "b": [0, 9], "mots": 9, "texte_a": "t", "texte_b": "t"}

    def paire(cle, score):
        return {"cle": cle, "a": ident("alpha-anne"), "b": ident("beta-boris"), "score": score,
                "couverture_a": score, "couverture_b": score, "nb_passages": 1, "mots_communs": 9, "passages": [passage]}

    plagiat._ecrire("paires.json", [paire("fort", 0.6), paire("faible", 0.01), paire("faible-decidee", 0.02)])
    plagiat._ecrire("decisions.json", {"fort": {"statut": "analysee", "verdict": "copie", "confiance": "elevee", "explication": "e"},
                                       "faible-decidee": {"statut": "ecartee"}})
    d = {p["cle"]: p for p in client.get("/api/plagiat/paires").json()["paires"]}
    assert set(d) == {"fort", "faible-decidee"}  # « faible » (sans décision, sous le plancher) disparaît
    assert d["fort"]["statut"] == "analysee" and d["fort"]["resultat"]["verdict"] == "copie"
    assert d["faible-decidee"]["statut"] == "ecartee"
    assert _lire_paires_json(tmp_path)["version"] == plagiat.VERSION_PAIRES  # fichier réécrit au nouveau format
    assert client.get("/api/plagiat/paires/fort").json()["passages"] == [passage]  # passages déplacés à part
    assert (tmp_path / "plagiat" / "decisions.json").is_file()


def test_etat_des_paires_cache_et_statuts(client, monkeypatch):
    cle = _paire_copiee(client)
    etat = plagiat.etat_des_paires()
    assert [(p["cle"], p["statut"]) for p in etat] == [(cle, "a_confirmer")] and "passages" not in etat[0]
    lectures = []
    vrai = plagiat.stockage.lire_json
    monkeypatch.setattr(plagiat.stockage, "lire_json", lambda c, d=None: (lectures.append(str(c)), vrai(c, d))[1])
    for _ in range(3):
        plagiat.etat_des_paires()
    assert not [c for c in lectures if c.endswith("paires.json")]  # cache : paires.json n'est pas relu
    client.put("/api/plagiat/reglages", json={"seuil": 0.99})
    assert plagiat.etat_des_paires()[0]["statut"] == "sous_seuil"  # le seuil et les décisions, eux, sont à jour
    client.post(f"/api/plagiat/paires/{cle}/ecarter")
    assert plagiat.etat_des_paires()[0]["statut"] == "ecartee"
    comparer(client)  # une nouvelle comparaison invalide le cache
    assert any(c.endswith("paires.json") for c in lectures)


def test_comparaison_en_arriere_plan_avec_progression(client):
    _paire_copiee(client)
    r = client.post("/api/plagiat/comparer").json()
    assert r["etat"] in ("en_cours", "termine")
    fin = plagiat.attendre_comparaison()
    assert fin["etat"] == "termine" and fin["rapports"] == 2 and fin["paires"] == 1
    assert client.get("/api/plagiat/comparer/etat").json()["etat"] == "termine"
    assert client.get("/api/plagiat/paires").status_code == 200  # les autres écrans répondent


def test_relancer_arrete_la_comparaison_en_cours(client, monkeypatch, tmp_path):
    import threading
    importer(client, "lab-1", Alpha=pdf(COMMUN + " fin A"), Beta=pdf(COMMUN + " fin B"))
    reel = plagiat.charger_rapports
    appels = []
    demarre = threading.Event()

    def lent(progression=None):
        appels.append(1)
        if len(appels) == 1:  # la 1re comparaison attend d'être arrêtée par la relance
            demarre.set()
            for _ in range(500):
                progression.maj("lecture", 0, 1)  # lève Annulee quand la relance arrive
                time.sleep(0.01)
            raise AssertionError("la comparaison n'a pas été arrêtée")
        return reel(progression)

    monkeypatch.setattr(plagiat, "charger_rapports", lent)
    client.post("/api/plagiat/comparer")
    assert demarre.wait(5)
    assert client.get("/api/plagiat/comparer/etat").json()["etat"] == "en_cours"
    premier = plagiat._job
    client.post("/api/plagiat/comparer")  # relance pendant que la 1re tourne
    fin = plagiat.attendre_comparaison()
    assert premier.etat["etat"] == "annule"  # la 1re s'est arrêtée proprement
    assert fin["etat"] == "termine" and fin["paires"] == 1 and len(appels) == 2
    assert len(_lire_paires_json(tmp_path)["paires"]) == 1  # une seule écriture, par la 2e


def test_comparaison_en_erreur_est_signalee_et_garde_l_ancien_resultat(client, monkeypatch):
    _paire_copiee(client)

    def casse(progression=None):
        raise RuntimeError("disque plein")

    monkeypatch.setattr(plagiat, "charger_rapports", casse)
    client.post("/api/plagiat/comparer")
    fin = plagiat.attendre_comparaison()
    assert fin["etat"] == "erreur" and "disque plein" in fin["erreur"]
    assert len(client.get("/api/plagiat/paires").json()["paires"]) == 1  # l'ancien résultat reste
