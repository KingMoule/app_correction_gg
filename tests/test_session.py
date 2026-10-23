"""Tests du rangement par session (A2026, H2027) et de la migration. Données fictives seulement."""

import json
import zipfile
from datetime import date

import pytest
from fastapi.testclient import TestClient

from moteur import migration_session, plagiat
from moteur import session as sessions
from moteur.app import creer_app
from tests.test_acces import aplatir
from tests.test_bibliotheque import client, deux_groupes, liste_csv, pdf  # noqa: F401
from tests.test_plagiat import COMMUN, pdf as pdf_texte

A, H = "202SNURE_A2026", "202SNURE_H2027"


def liste(client, session=None, groupe="00002", lignes=None):
    lignes = lignes or [("2000001", "Dubé", "Alice"), ("2000002", "Martin", "Zoé")]
    nom, contenu = liste_csv(lignes, groupe)
    r = client.post("/api/bibliotheque/classes", files={"fichier": (nom, contenu)}, data={"session": session} if session else {})
    assert r.status_code == 200, r.text
    return r.json()


def importer(client, cours, noms_pdf, lab="Lab 1", groupe="00002"):
    r = client.post("/api/bibliotheque/import", data={"cours": cours, "groupe": groupe, "lab": lab},
                    files=[("fichiers", (n, c, "application/pdf")) for n, c in noms_pdf])
    assert r.status_code == 200, r.text
    return r.json()


# --- La session ---------------------------------------------------------------

def test_session_proposee_d_apres_la_date():
    assert sessions.session_du_jour(date(2026, 10, 23)) == "A2026"
    assert sessions.session_du_jour(date(2026, 8, 1)) == "A2026"
    assert sessions.session_du_jour(date(2026, 12, 31)) == "A2026"
    assert sessions.session_du_jour(date(2027, 1, 1)) == "H2027"
    assert sessions.session_du_jour(date(2027, 7, 31)) == "H2027"  # pas d'été


def test_identifiant_de_cours_se_separe_sans_ambiguite():
    assert sessions.cle_cours("202snure", "a2026") == "202SNURE_A2026"
    assert sessions.separer("202SNURE_H2027") == ("202SNURE", "H2027")
    assert sessions.separer("202SNURE") == ("202SNURE", None)
    assert sessions.libelle("H2027") == "Hiver 2027"
    for mauvaise in ("E2026", "2026", "A26", "", "A2026x"):
        with pytest.raises(Exception):
            sessions.valider(mauvaise)


def test_session_courante_modifiable_et_liste_des_sessions(client, monkeypatch):
    monkeypatch.delenv("CORRECTION_SESSION")
    d = client.get("/api/bibliotheque/sessions").json()
    assert d["courante"] == d["deduite"] == sessions.session_du_jour()
    assert client.put("/api/bibliotheque/sessions/courante", json={"session": "H2027"}).json() == {"courante": "H2027"}
    assert client.put("/api/bibliotheque/sessions/courante", json={"session": "E2027"}).status_code == 400
    liste(client)  # sans session : la session choisie
    d = client.get("/api/bibliotheque/sessions").json()
    assert d["courante"] == "H2027" and d["sessions"][0] == {
        "session": "H2027", "libelle": "Hiver 2027", "courante": True, "cours": [H]}


# --- Deux sessions, même code de cours et même groupe ---------------------------

def deux_sessions(client):
    liste(client, "A2026")
    liste(client, "H2027", lignes=[("2000001", "Dubé", "Alice"), ("2000009", "Roy", "Léa")])
    importer(client, A, [("dube_2000001_Rapport.pdf", pdf("Alice automne"))])
    importer(client, H, [("dube_2000001_Rapport.pdf", pdf("Alice hiver")), ("roy_2000009_Rapport.pdf", pdf("Léa hiver"))])


def test_deux_sessions_restent_separees(client, tmp_path):
    deux_sessions(client)
    assert (tmp_path / "bibliotheque" / A / "00002/lab-1/dube-alice/rapport.pdf").is_file()
    assert (tmp_path / "bibliotheque" / H / "00002/lab-1/dube-alice/rapport.pdf").is_file()
    arbre = {c["cours"]: c for c in client.get("/api/bibliotheque").json()}
    assert set(arbre) == {A, H}
    assert (arbre[A]["code"], arbre[A]["session"]) == ("202SNURE", "A2026")
    assert [e["id"] for e in arbre[A]["etudiants"]] == ["dube-alice", "martin-zoe"]
    assert [e["id"] for e in arbre[H]["etudiants"]] == ["dube-alice", "roy-lea"]  # la liste d'hiver n'a pas fusionné
    # Terminer le rapport d'automne ne touche pas celui d'hiver.
    assert client.put(f"/api/bibliotheque/statut/{A}/00002/lab-1/dube-alice", json={"termine": True, "note": "18"}).status_code == 200
    arbre = {c["cours"]: c for c in client.get("/api/bibliotheque").json()}
    assert arbre[A]["etudiants"][0]["termines"] == ["lab-1"] and arbre[H]["etudiants"][0]["termines"] == []
    assert client.get(f"/api/suivi/{H}/lab-1").json()["compte"]["termines"] == 0
    assert client.get(f"/api/suivi/{A}/lab-1").json()["compte"]["termines"] == 1


def test_suivi_lot_et_export_par_session(client):
    deux_sessions(client)
    s_a, s_h = client.get(f"/api/suivi/{A}/lab-1").json(), client.get(f"/api/suivi/{H}/lab-1").json()
    assert (s_a["session"], s_a["total"], s_a["compte"]["inscrits"]) == ("A2026", 1, 2)
    assert (s_h["session"], s_h["total"], s_h["compte"]["inscrits"]) == ("H2027", 2, 2)
    assert [r["nom"] for r in s_h["non_remis"]] == [] and [r["nom"] for r in s_a["non_remis"]] == ["Martin"]
    assert client.get(f"/api/lot/apercu/{A}/lab-1").json()["a_analyser"] == 1
    assert client.get(f"/api/lot/apercu/{H}/lab-1").json()["a_analyser"] == 2
    assert client.get(f"/api/export-lot/apercu/{A}/lab-1").json()["total"] == 1
    assert client.get(f"/api/export-lot/apercu/{H}/lab-1").json()["total"] == 2
    assert "202SNURE_H2027_lab-1" in client.get(f"/api/export-lot/tableau/{H}/lab-1").headers["content-disposition"]


def test_enonce_et_reglages_par_session(client):
    liste(client, "A2026")
    client.put(f"/api/francais/bareme/{A}", json={"points_par_faute": 0.5, "plafond": 3})
    client.put(f"/api/references/style/{A}", json={"style": "apa7"})
    liste(client, "H2027")  # nouvelle session : reprend le barème et le style de la précédente, par copie
    assert client.get(f"/api/francais/bareme/{H}").json()["points_par_faute"] == 0.5
    assert client.get(f"/api/references/style/{H}").json()["style"] == "apa7"
    client.put(f"/api/francais/bareme/{H}", json={"points_par_faute": 1, "plafond": None})
    assert client.get(f"/api/francais/bareme/{A}").json()["points_par_faute"] == 0.5
    client.post(f"/api/plagiat/enonces/{A}/lab-1", files={"pdf": ("e.pdf", pdf("Enoncé"), "application/pdf")})
    assert client.get(f"/api/plagiat/enonces/{A}/lab-1").status_code == 200
    assert client.get(f"/api/plagiat/enonces/{H}/lab-1").status_code == 404


def test_le_plagiat_compare_toutes_les_sessions(client):
    liste(client, "A2026")
    liste(client, "H2027")
    texte = pdf_texte("Introduction. " + COMMUN + " Conclusion de l'automne sur les erreurs de mesure du circuit.")
    copie = pdf_texte("Resume. " + COMMUN + " Autre conclusion de l'hiver ecrite par une autre equipe de labo.")
    importer(client, A, [("dube_2000001_R.pdf", texte)])
    importer(client, H, [("martin_2000002_R.pdf", copie)])
    assert client.post("/api/plagiat/comparer").status_code == 200
    assert plagiat.attendre_comparaison()["etat"] == "termine"
    paires = client.get("/api/plagiat/paires").json()["paires"]
    assert len(paires) == 1
    assert {paires[0]["a"]["cours"], paires[0]["b"]["cours"]} == {A, H}


def test_anonymiseur_couvre_le_cours_de_la_bonne_session(client):
    from moteur.anonymat import Anonymiseur
    deux_sessions(client)
    assert "[NOM]" in Anonymiseur.pour(H).masquer("Léa Roy a mesuré")
    assert "Roy" in Anonymiseur.pour(A).masquer("Léa Roy a mesuré")  # Roy n'est pas dans la liste d'automne


def test_routes_refusent_un_cours_sans_session_sans_rien_creer(client, tmp_path):
    """Un ancien appel (cours sans session) répond 4xx et ne crée aucun dossier."""
    deux_sessions(client)
    avant = sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*"))
    app = creer_app()
    essais = 0
    for chemin, methodes, route in aplatir(app.routes):
        if "{cours}" not in chemin or not chemin.startswith("/api/") or not methodes:
            continue
        url = chemin.replace("{cours}", "202SNURE").replace("{groupe}", "00002").replace("{lab}", "lab-1")                     .replace("{etudiant}", "dube-alice").replace("{cle}", "x")
        for methode in sorted(methodes - {"HEAD", "OPTIONS"}):
            if methode == "POST" and chemin.startswith(("/api/export-lot/", "/api/lot/")):
                continue  # lancent un travail en arrière-plan : couverts par leurs propres tests
            r = client.request(methode, url, json={})
            assert 400 <= r.status_code < 500, (methode, url, r.status_code, r.text[:200])
            essais += 1
    assert essais > 10
    assert sorted(p.relative_to(tmp_path).as_posix() for p in tmp_path.rglob("*")) == avant


# --- Migration de l'ancien rangement -------------------------------------------

def ecrire(chemin, doc):
    chemin.parent.mkdir(parents=True, exist_ok=True)
    chemin.write_text(json.dumps(doc), encoding="utf-8")


def ancienne_bibliotheque(donnees):
    """Rangement d'avant les sessions (fictif) : un cours, deux groupes, rapports, caches, fichiers à la racine."""
    b = donnees / "bibliotheque"
    for groupe, ids in (("00001", ["bele-anna"]), ("00002", ["dube-alice", "roy-lea"])):
        ecrire(b / "202SNURE" / groupe / "classe.json", {"cours": "202SNURE", "groupe": groupe,
               "etudiants": [{"id": i, "nom": i, "prenom": "X"} for i in ids]})
        for i in ids:
            dossier = b / "202SNURE" / groupe / "lab-1" / i
            dossier.mkdir(parents=True)
            (dossier / "rapport.pdf").write_bytes(pdf(f"Rapport {i}"))
            ecrire(dossier / "francais.json", {"version": 1, "fautes": []})
    ecrire(b / "202SNURE" / "bareme.json", {"points_par_faute": 0.5, "plafond": None})
    ecrire(b / "202SNURE" / "style_references.json", {"style": "apa7"})
    (b / "202SNURE" / "_enonces").mkdir()
    (b / "202SNURE" / "_enonces" / "lab-1.pdf").write_bytes(pdf("Enoncé"))
    ecrire(b / "_attente" / "abc.json", {"id": "abc", "fichier": "x.pdf", "cours": "202SNURE", "groupe": None, "lab": "lab-2"})
    (b / "_attente" / "abc.pdf").write_bytes(pdf("En attente"))
    (b / "_ecartes").mkdir()
    (b / "_ecartes" / "e.pdf").write_bytes(pdf("Écarté"))
    ecrire(b / "_remplaces" / "202SNURE_00002_lab-1_dube-alice_20261001-101010" / "rapport.pdf.json", {})
    ecrire(donnees / "reprendre.json", {"recents": [{"cours": "202SNURE", "groupe": "00002", "lab": "lab-1", "etudiant": "dube-alice"}]})
    ecrire(donnees / "exports.json", {"202SNURE/lab-1": {"00002/dube-alice": {"date": "x", "sig": "y"}}})
    ecrire(donnees / "lexique.json", ["ohm"])
    ecrire(donnees / "plagiat" / "paires.json", {"version": 2, "paires": [
        {"cle": "k", "score": 0.5, "a": {"cours": "202SNURE", "groupe": "00002", "lab": "lab-2", "etudiant": "dube-alice"},
         "b": {"cours": "202SNURE", "groupe": "00002", "lab": "lab-2", "etudiant": "roy-lea"}}]})
    ecrire(donnees / "plagiat" / "decisions.json", {"k": {"statut": "ecartee"}})
    ecrire(donnees / "plagiat" / "textes" / "h.json", ["mot"])


def test_migration_de_l_ancien_format(tmp_path):
    donnees, sauvegardes = tmp_path / "donnees", tmp_path / "sauvegardes"
    ancienne_bibliotheque(donnees)
    avant = migration_session.inventaire(donnees)
    compte = migration_session.migrer(donnees, "A2026", destination_sauvegardes=sauvegardes)
    assert compte["migre"] and compte["renommages"] == [("202SNURE", "202SNURE_A2026")]
    assert compte["avant"] == avant and compte["apres"] == avant  # mêmes nombres de fichiers, de rapports, d'octets
    assert avant["rapports"] == 3
    b = donnees / "bibliotheque"
    assert not (b / "202SNURE").exists()
    nouveau = b / "202SNURE_A2026"
    assert (nouveau / "00002/lab-1/dube-alice/rapport.pdf").is_file()
    for f in ("bareme.json", "style_references.json", "_enonces/lab-1.pdf"):
        assert (nouveau / f).is_file()
    assert json.loads((nouveau / "00001/classe.json").read_text(encoding="utf-8"))["cours"] == "202SNURE_A2026"
    assert json.loads((b / "_attente/abc.json").read_text(encoding="utf-8"))["cours"] == "202SNURE_A2026"
    assert (b / "_ecartes/e.pdf").is_file() and (b / "_attente/abc.pdf").is_file()
    assert (b / "_remplaces/202SNURE_00002_lab-1_dube-alice_20261001-101010").is_dir()
    assert json.loads((donnees / "reprendre.json").read_text(encoding="utf-8"))["recents"][0]["cours"] == "202SNURE_A2026"
    assert list(json.loads((donnees / "exports.json").read_text(encoding="utf-8"))) == ["202SNURE_A2026/lab-1"]
    paires = json.loads((donnees / "plagiat/paires.json").read_text(encoding="utf-8"))["paires"][0]
    assert paires["a"]["cours"] == paires["b"]["cours"] == "202SNURE_A2026"
    assert json.loads((donnees / "plagiat/decisions.json").read_text(encoding="utf-8")) == {"k": {"statut": "ecartee"}}
    # La sauvegarde faite avant contient l'ancien rangement; le journal est écrit.
    archive = zipfile.ZipFile(compte["sauvegarde"])
    assert "bibliotheque/202SNURE/00002/lab-1/dube-alice/rapport.pdf" in archive.namelist()
    assert len(list((donnees / "migrations").glob("session_*.json"))) == 1


def test_migration_idempotente(tmp_path):
    donnees, sauvegardes = tmp_path / "donnees", tmp_path / "sauvegardes"
    ancienne_bibliotheque(donnees)
    migration_session.migrer(donnees, "A2026", destination_sauvegardes=sauvegardes)
    etat = sorted((p.relative_to(donnees).as_posix(), p.read_bytes()) for p in donnees.rglob("*") if p.is_file()
                  and "migrations" not in p.parts)
    deuxieme = migration_session.migrer(donnees, "A2026", destination_sauvegardes=sauvegardes)
    assert deuxieme["migre"] is False
    assert len(list(sauvegardes.glob("*.zip"))) == 1  # pas de nouvelle sauvegarde
    assert sorted((p.relative_to(donnees).as_posix(), p.read_bytes()) for p in donnees.rglob("*") if p.is_file()
                  and "migrations" not in p.parts) == etat


def test_migration_a_sec_ne_change_rien(tmp_path):
    donnees = tmp_path / "donnees"
    ancienne_bibliotheque(donnees)
    avant = sorted(p.relative_to(donnees).as_posix() for p in donnees.rglob("*"))
    compte = migration_session.migrer(donnees, "A2026", a_sec=True, destination_sauvegardes=tmp_path / "s")
    assert compte["a_sec"] and compte["renommages"] == [("202SNURE", "202SNURE_A2026")]
    assert sorted(p.relative_to(donnees).as_posix() for p in donnees.rglob("*")) == avant
    assert not (tmp_path / "s").exists()


def test_migration_reprend_apres_une_interruption(tmp_path):
    """Dossiers renommés mais fichiers pas encore corrigés : le lancement suivant termine le travail."""
    donnees = tmp_path / "donnees"
    ancienne_bibliotheque(donnees)
    (donnees / "bibliotheque" / "202SNURE").rename(donnees / "bibliotheque" / "202SNURE_A2026")
    compte = migration_session.migrer(donnees, "A2026", destination_sauvegardes=tmp_path / "s")
    assert compte["migre"] and compte["renommages"] == []
    assert json.loads((donnees / "reprendre.json").read_text(encoding="utf-8"))["recents"][0]["cours"] == "202SNURE_A2026"
    assert migration_session.migrer(donnees, "A2026", destination_sauvegardes=tmp_path / "s")["migre"] is False


def test_migration_refuse_un_conflit_sans_rien_toucher(tmp_path):
    donnees = tmp_path / "donnees"
    ancienne_bibliotheque(donnees)
    (donnees / "bibliotheque" / "202SNURE_A2026" / "00002").mkdir(parents=True)
    avant = sorted(p.relative_to(donnees).as_posix() for p in donnees.rglob("*"))
    with pytest.raises(migration_session.MigrationErreur, match="existe déjà"):
        migration_session.migrer(donnees, "A2026", destination_sauvegardes=tmp_path / "s")
    assert sorted(p.relative_to(donnees).as_posix() for p in donnees.rglob("*")) == avant


def test_migration_sans_sauvegarde_possible_ne_touche_a_rien(tmp_path, monkeypatch):
    donnees = tmp_path / "donnees"
    ancienne_bibliotheque(donnees)

    def echec(*a, **k):
        raise migration_session.sauvegarde.SauvegardeErreur("disque plein")
    monkeypatch.setattr(migration_session.sauvegarde, "sauvegarder", echec)
    with pytest.raises(migration_session.MigrationErreur, match="disque plein"):
        migration_session.migrer(donnees, "A2026", destination_sauvegardes=tmp_path / "s")
    assert (donnees / "bibliotheque" / "202SNURE").is_dir()


def test_apres_migration_l_app_fonctionne(tmp_path, monkeypatch):
    donnees = tmp_path / "donnees"
    ancienne_bibliotheque(donnees)
    migration_session.migrer(donnees, "A2026", destination_sauvegardes=tmp_path / "s")
    monkeypatch.setenv("CORRECTION_DONNEES", str(donnees))
    c = TestClient(creer_app())
    arbre = c.get("/api/bibliotheque").json()
    assert {x["cours"] for x in arbre} == {"202SNURE_A2026"} and {x["session"] for x in arbre} == {"A2026"}
    assert c.get("/api/bibliotheque/rapport/202SNURE_A2026/00002/lab-1/dube-alice").status_code == 200
    assert c.get("/api/suivi/202SNURE_A2026/lab-1").json()["total"] == 3
    assert c.get("/api/bibliotheque/attente").json()[0]["cours"] == "202SNURE_A2026"
