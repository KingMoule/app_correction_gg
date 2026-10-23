"""Tests de l'export par lot pour LÉA (Travaux.zip + tableau CSV). Bibliothèque fictive seulement."""

import csv
import io
import json
import re
import time
import zipfile

import pytest
from pypdf import PdfReader

from moteur import export_lot, plagiat
from tests.test_bibliotheque import client, deux_groupes, importer_cours, pdf  # noqa: F401

COURS = "202SNURE_A2026"
PAGE_ALICE = "Rapport de lab\nPar Alice Dubé et Anna Bele-Gombos"  # Anna est coéquipière d'Alice (autre groupe)


def faute(n: int) -> dict:
    return {"id": n, "debut": 0, "fin": 6, "texte": "mesure", "message": "", "regle": "", "categorie": "",
            "suggestions": ["mesurent"], "zones": [{"page": 1, "x0": 72, "y0": 90, "x1": 140, "y1": 102}]}


def ecrire_francais(dossier, decisions: dict, nb_fautes: int = 3, claude_ok: bool = True) -> None:
    (dossier / "francais.json").write_text(json.dumps({
        "version": 1, "fautes": [faute(i) for i in range(nb_fautes)],
        "decisions": decisions, "choix": {}, "masquees": [], "decalages": {},
        "claude": {"ok": claude_ok, "erreur": None if claude_ok else "limite atteinte", "ajoutees": 0}}), encoding="utf-8")


@pytest.fixture
def lab(client, tmp_path):
    """Lab 1 : Alice (+ Anna) corrigée, Zoé à trancher, Luc non analysé; Lab 2 : Alice seule."""
    deux_groupes(client)
    importer_cours(client, [
        ("dube_2000001_Rapport_remis.pdf", pdf(PAGE_ALICE)),
        ("martin_2000002_Rapport_remis.pdf", pdf("Zoe")),
        ("martin_1000002_Rapport_remis.pdf", pdf("Luc")),
    ])
    base = tmp_path / "bibliotheque" / COURS
    # Alice : 3 fautes décidées (2 acceptées); Zoé : une faute reste à trancher
    ecrire_francais(base / "00002/lab-1/dube-alice", {"0": "acceptee", "1": "refusee", "2": "acceptee"})
    ecrire_francais(base / "00002/lab-1/martin-zoe", {"0": "acceptee"})
    client.put("/api/francais/bareme/202SNURE_A2026", json={"points_par_faute": 0.75, "plafond": None})
    client.put(f"/api/bibliotheque/statut/{COURS}/00002/lab-1/dube-alice", json={"termine": True, "note": "17,5"})
    # Plagiat : paire Alice / Luc confirmée, verdict de Claude rendu
    ident = lambda g, e, nom: {"cours": COURS, "groupe": g, "lab": "lab-1", "etudiant": e, "nom": nom}  # noqa: E731
    plagiat._ecrire("paires.json", [{"cle": "x-y", "a": ident("00002", "dube-alice", "Alice Dubé"),
                                     "b": ident("00001", "martin-luc", "Luc Martin"), "score": 0.5, "passages": []}])
    plagiat._ecrire("decisions.json", {"x-y": {"statut": "analysee", "verdict": "paraphrase"}})
    (base / "00001/lab-1/martin-luc/indices_ia.json").write_text(json.dumps({"force": "moderee"}), encoding="utf-8")
    return client, tmp_path


def lire_csv(contenu: bytes) -> list[dict]:
    texte = contenu.decode("utf-8-sig")
    return list(csv.DictReader(io.StringIO(texte), delimiter=";"))


def exporter_zip(client, groupe=None, inacheves=True) -> zipfile.ZipFile:
    r = client.post(f"/api/export-lot/{COURS}/lab-1", json={"groupe": groupe, "inacheves": inacheves})
    assert r.status_code == 200, r.text
    for _ in range(100):
        etat = client.get("/api/export-lot/etat").json()
        if etat["statut"] != "en_cours":
            break
        time.sleep(0.05)
    assert etat["statut"] == "pret", etat
    q = f"?groupe={groupe}" if groupe else ""
    reponse = client.get(f"/api/export-lot/travaux/{COURS}/lab-1{q}")
    assert re.search(r'filename="Travaux_\d{4}-\d{2}-\d{2}_\d{2}h\d{2}\.zip"', reponse.headers["content-disposition"])
    return zipfile.ZipFile(io.BytesIO(reponse.content))


def test_zip_noms_d_origine_et_contenu(lab):
    client, _ = lab
    z = exporter_zip(client)
    assert sorted(z.namelist()) == ["dube_2000001_Rapport_remis_corrige.pdf",
                                    "martin_1000002_Rapport_remis_corrige.pdf",
                                    "martin_2000002_Rapport_remis_corrige.pdf"]  # un PDF par rapport (pas par coéquipier)
    alice = PdfReader(io.BytesIO(z.read("dube_2000001_Rapport_remis_corrige.pdf")))
    assert "Alice" in alice.pages[0].extract_text()
    original = PdfReader(io.BytesIO((lab[1] / "bibliotheque" / COURS / "00002/lab-1/dube-alice/rapport.pdf").read_bytes()))
    # le rendu annoté est le même que l'export unitaire (fautes acceptées dessinées par-dessus)
    unitaire = client.get(f"/api/export/{COURS}/00002/lab-1/dube-alice").content
    assert z.read("dube_2000001_Rapport_remis_corrige.pdf") == unitaire
    assert len(alice.pages) == len(original.pages)


def test_zip_une_classe_seulement_et_sans_inacheves(lab):
    client, _ = lab
    assert exporter_zip(client, groupe="00001").namelist() == ["martin_1000002_Rapport_remis_corrige.pdf"]
    assert exporter_zip(client, inacheves=False).namelist() == ["dube_2000001_Rapport_remis_corrige.pdf"]


def test_inacheves_exclus_par_defaut(lab):
    """Sans le paramètre, seuls les rapports « Corrigé » partent (ZIP et tableau)."""
    client, _ = lab
    par_defaut = lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1").content)
    assert par_defaut == lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=false").content)
    assert len(par_defaut) < len(lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content))
    assert client.post(f"/api/export-lot/{COURS}/lab-1", json={}).status_code == 200
    for _ in range(100):
        if client.get("/api/export-lot/etat").json()["statut"] != "en_cours":
            break
        time.sleep(0.05)
    z = zipfile.ZipFile(io.BytesIO(client.get(f"/api/export-lot/travaux/{COURS}/lab-1").content))
    assert z.namelist() == ["dube_2000001_Rapport_remis_corrige.pdf"]


def test_apercu_compte_les_inacheves(lab):
    client, _ = lab
    a = client.get(f"/api/export-lot/apercu/{COURS}/lab-1").json()
    assert (a["total"], a["corrige"], a["a_trancher"], a["non_analyse"]) == (3, 1, 1, 1)
    assert a["groupes"] == ["00001", "00002"]


def test_tableau_csv_encodage_excel_francais(lab):
    client, _ = lab
    r = client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true")
    assert r.status_code == 200 and re.search(r"Recapitulatif_202SNURE_A2026_lab-1_\d{4}-\d{2}-\d{2}_\d{2}h\d{2}\.csv", r.headers["content-disposition"])
    assert r.content.startswith(b"\xef\xbb\xbf")  # BOM : Excel lit l'UTF-8
    en_tete = r.content.decode("utf-8-sig").splitlines()[0]
    assert en_tete.split(";")[:3] == ["DA", "Nom", "Prénom"] and "État" in en_tete  # « ; » et accents
    assert "Dubé" in r.content.decode("utf-8-sig") and "Dubé".encode("utf-8") in r.content


def test_tableau_lignes_penalites_equipe_etats(lab):
    client, _ = lab
    lignes = {(l["Nom"], l["Prénom"]): l for l in lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content)}
    assert len(lignes) == 4  # Alice, Anna (coéquipière), Luc, Zoé : une ligne chacun
    alice, anna = lignes[("Dubé", "Alice")], lignes[("Bele-Gombos", "Anna")]
    assert alice["DA"] == "2000001" and alice["Groupe"] == "00002"
    assert (alice["Fautes acceptées"], alice["Pénalité français"], alice["Note"], alice["État"]) == ("2", "1,5", "17,5", "Corrigé")
    assert alice["Terminé"] == "oui" and alice["Équipe"].startswith("déposant")
    # la coéquipière reçoit la même note et la même pénalité, avec son propre DA et son groupe
    assert (anna["DA"], anna["Groupe"]) == ("1000001", "00001")
    assert (anna["Fautes acceptées"], anna["Pénalité français"], anna["Note"], anna["État"]) == ("2", "1,5", "17,5", "Corrigé")
    assert "Alice" in anna["Équipe"]
    zoe, luc = lignes[("Martin", "Zoé")], lignes[("Martin", "Luc")]
    assert (zoe["État"], zoe["Fautes acceptées"], zoe["Pénalité français"]) == ("À trancher", "1", "0,75")
    assert (luc["État"], luc["Fautes acceptées"], luc["Pénalité français"], luc["Terminé"]) == ("Non analysé", "0", "0", "non")
    # indices toujours libellés « à revérifier »
    assert luc["Indice d'IA (à revérifier)"] == "modérée" and alice["Indice d'IA (à revérifier)"] == ""
    assert "paraphrase avec Luc Martin" in alice["Plagiat confirmé (à revérifier)"]
    assert "paraphrase avec Alice Dubé" in luc["Plagiat confirmé (à revérifier)"]


def test_plafond_du_bareme(lab):
    client, _ = lab
    client.put("/api/francais/bareme/202SNURE_A2026", json={"points_par_faute": 0.75, "plafond": 1})
    alice = next(l for l in lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content) if l["Nom"] == "Dubé")
    assert alice["Pénalité français"] == "1"


def test_tableau_sans_inacheves_et_groupe(lab):
    client, _ = lab
    corriges = lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=false").content)
    assert {l["Nom"] for l in corriges} == {"Dubé", "Bele-Gombos"}  # Alice et sa coéquipière seulement
    g1 = lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?groupe=00001&inacheves=true").content)
    assert {l["Prénom"] for l in g1} == {"Anna", "Luc"}


def test_non_remis_signales(lab):
    client, _ = lab
    # Lab 2 : seule Alice a remis (avec Anna); Luc et Zoé n'ont rien remis
    client.post("/api/bibliotheque/import", data={"cours": COURS, "groupe": "", "lab": "Lab 2"},
                files=[("fichiers", ("dube_2000001_L2.pdf", pdf(PAGE_ALICE), "application/pdf"))])
    etats = {l["Prénom"]: l["État"] for l in lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-2?inacheves=true").content)}
    assert etats == {"Alice": "Non analysé", "Anna": "Non analysé", "Luc": "Non remis", "Zoé": "Non remis"}


def test_rien_n_est_ecrit_dans_la_bibliotheque(lab):
    client, tmp = lab
    avant = {p: p.stat().st_mtime_ns for p in (tmp / "bibliotheque").rglob("*") if p.is_file()}
    exporter_zip(client)
    client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true")
    apres = {p: p.stat().st_mtime_ns for p in (tmp / "bibliotheque").rglob("*") if p.is_file()}
    assert avant == apres


def test_note_gardee_a_la_reouverture_et_dans_l_arbre(lab):
    client, _ = lab
    url = f"/api/bibliotheque/statut/{COURS}/00002/lab-1/dube-alice"
    assert client.put(url, json={"termine": False}).json() == {"termine": False, "note": "17,5"}  # note absente = gardée
    arbre = client.get("/api/bibliotheque").json()
    alice = next(e for c in arbre for e in c["etudiants"] if e["id"] == "dube-alice")
    assert alice["notes"] == {"lab-1": "17,5"} and alice["termines"] == []
    assert client.put(url, json={"termine": True, "note": ""}).json()["note"] == ""  # vidée explicitement


def test_export_sans_rapport(lab):
    client, _ = lab
    assert client.post(f"/api/export-lot/{COURS}/lab-9", json={}).status_code == 404
    assert client.get("/api/export-lot/apercu/COURS_INCONNU/lab-1").status_code == 404


def test_noms_de_fichier_surs_et_repli():
    e = {"id": "a-b", "nom": "Dubé", "prenom": "Alice", "da": "2000001"}
    base = {"etudiant": e}
    assert export_lot.nom_pdf({**base, "origine": "../../evil\\x:y.pdf"}, "lab-1") == "x_y_corrige.pdf"
    assert export_lot.nom_pdf({**base, "origine": None}, "lab-1") == "2000001_Dubé_lab-1_corrige.pdf"


def test_cellules_sans_formule_ni_date():
    assert export_lot._cellule("=SOMME(A1)") == "'=SOMME(A1)"
    assert export_lot._cellule("-cmd") == "'-cmd" and export_lot._cellule("-3") == "-3"
    assert export_lot._cellule(1.5) == "1,5" and export_lot._cellule(2.0) == "2" and export_lot._cellule(0.0) == "0"


# --- États d'export (audit F1, F2) ---------------------------------------------

def etat_export(client, groupe=None) -> dict:
    q = f"?groupe={groupe}" if groupe else ""
    return client.get(f"/api/export-lot/apercu/{COURS}/lab-1{q}").json()["export"]


def test_noms_horodates():
    from datetime import datetime
    stamp = export_lot.horodatage(datetime(2026, 10, 20, 9, 5))
    assert stamp == "2026-10-20_09h05"  # pas de « : » (interdit sous Windows)
    assert export_lot.nom_zip(stamp) == "Travaux_2026-10-20_09h05.zip"
    assert export_lot.nom_tableau(COURS, "lab-1", stamp) == "Recapitulatif_202SNURE_A2026_lab-1_2026-10-20_09h05.csv"


def test_export_perime_apres_decision_puis_trait_puis_a_jour(lab):
    client, tmp = lab
    assert etat_export(client)["statut"] == "jamais"
    exporter_zip(client)
    ex = etat_export(client)
    assert (ex["statut"], ex["modifies"], ex["non_exportes"]) == ("a_jour", 0, 0) and ex["date"]
    assert client.get(f"/api/suivi/{COURS}/lab-1").json()["export"]["statut"] == "a_jour"
    # une décision de français change : périmé
    time.sleep(0.02)
    ecrire_francais(tmp / "bibliotheque" / COURS / "00002/lab-1/dube-alice", {"0": "refusee", "1": "refusee", "2": "acceptee"})
    assert etat_export(client)["statut"] == "perime"
    assert client.get(f"/api/suivi/{COURS}/lab-1").json()["export"]["statut"] == "perime"
    exporter_zip(client)
    assert etat_export(client)["statut"] == "a_jour"  # un nouvel export remet à jour
    # un trait au crayon : périmé de nouveau
    time.sleep(0.02)
    url = f"/api/annotations/{COURS}/00002/lab-1/dube-alice"
    assert client.put(url, json={"version": 1, "pages": {"1": [{"outil": "crayon", "couleur": "#ff0000", "largeur_min": 1,
                                                                 "largeur_max": 2, "courbe": 1, "points": [[10, 10, 0.5]]}]}}).status_code == 200
    assert etat_export(client)["statut"] == "perime"


def test_export_perime_si_rapport_remplace_ou_note_changee(lab):
    client, tmp = lab
    exporter_zip(client)
    time.sleep(0.02)
    (tmp / "bibliotheque" / COURS / "00001/lab-1/martin-luc/rapport.pdf").write_bytes(pdf("Luc, nouvelle version"))
    ex = etat_export(client)
    assert (ex["statut"], ex["modifies"]) == ("perime", 1)


def test_export_partiel_compte_les_non_exportes(lab):
    client, _ = lab
    exporter_zip(client, groupe="00001")
    ex = etat_export(client)
    assert (ex["statut"], ex["non_exportes"]) == ("a_jour", 2)  # Alice et Zoé (groupe 00002) pas encore partis
    assert etat_export(client, "00002")["statut"] == "jamais"


def test_claude_manquant_dans_apercu_tableau_et_suivi(lab):
    client, tmp = lab
    alice = tmp / "bibliotheque" / COURS / "00002/lab-1/dube-alice"
    ecrire_francais(alice, {"0": "acceptee", "1": "refusee", "2": "acceptee"}, claude_ok=False)
    a = client.get(f"/api/export-lot/apercu/{COURS}/lab-1").json()
    assert (a["corrige"], a["claude_manquant"], a["a_trancher"]) == (0, 1, 1)
    ligne = next(l for l in lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=true").content) if l["Nom"] == "Dubé")
    assert ligne["État"] == "Claude manquant"
    # sans inachevés, un rapport « Claude manquant » ne part pas comme s'il était complet
    assert lire_csv(client.get(f"/api/export-lot/tableau/{COURS}/lab-1?inacheves=false").content) == []
    suivi = {r["etudiant"]: r for r in client.get(f"/api/suivi/{COURS}/lab-1").json()["rapports"]}
    assert suivi["dube-alice"]["francais"]["claude_manquant"] is True
    # un ancien francais.json sans clé « claude » est aussi « Claude manquant »
    doc = json.loads((alice / "francais.json").read_text(encoding="utf-8"))
    del doc["claude"]
    (alice / "francais.json").write_text(json.dumps(doc), encoding="utf-8")
    assert export_lot.etat_francais(doc) == ("claude_manquant", 2)
    doc["claude"] = {"ok": True}
    assert export_lot.etat_francais(doc) == ("corrige", 2)


def test_telechargement_refuse_un_autre_lab_ou_groupe(lab):
    client, _ = lab
    exporter_zip(client, groupe="00001")
    assert client.get(f"/api/export-lot/travaux/{COURS}/lab-1?groupe=00001").status_code == 200
    assert client.get(f"/api/export-lot/travaux/{COURS}/lab-1").status_code == 404  # export d'un seul groupe
    assert client.get(f"/api/export-lot/travaux/{COURS}/lab-2?groupe=00001").status_code == 404
