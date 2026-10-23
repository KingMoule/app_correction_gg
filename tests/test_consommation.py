"""Tests de la consommation de Claude : journal, fenêtres, calibrage, estimation. Données fictives."""

import json
from datetime import datetime, timedelta

import pytest
from fastapi.testclient import TestClient

from moteur import consommation as c
from moteur.app import creer_app
from moteur.claude import ClaudeLimite, FileClaude, Resultat

MAINTENANT = datetime(2026, 10, 22, 14, 0, 0)


class ClientFaux:
    modele = "sonnet"

    def __init__(self, reponses):
        self.reponses = list(reponses)

    def executer(self, prompt, schema=None, systeme=None):
        r = self.reponses.pop(0)
        if isinstance(r, Exception):
            raise r
        return r


def resultat(cout=0.04, entree=100, sortie=50):
    return Resultat(texte="", usage={"input_tokens": entree, "output_tokens": sortie,
                                     "cache_creation_input_tokens": 7, "cache_read_input_tokens": 9},
                    cout_usd=cout, brut={"modelUsage": {"claude-sonnet-5-5": {}}})


@pytest.fixture
def donnees(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path))
    horloge = {"t": MAINTENANT}
    monkeypatch.setattr(c, "_maintenant", lambda: horloge["t"])
    return horloge


def journal(tmp_path):
    return json.loads((tmp_path / "consommation" / "journal.json").read_text(encoding="utf-8"))


def ajouter(donnees, type_, cout, il_y_a=timedelta(0), rapport=("cours", "lab", "dupont-marie")):
    donnees["t"] = MAINTENANT - il_y_a
    with c.contexte(type_, *rapport):
        c.enregistrer_appel(resultat(cout), c.contexte_courant())
    donnees["t"] = MAINTENANT


def test_la_file_journalise_type_jetons_cout_et_modele(donnees, tmp_path):
    file = FileClaude(ClientFaux([resultat(0.05)]), journal=True)
    with c.contexte("ia", "cours", "lab", "dupont-marie"):
        file.soumettre("x").result(timeout=5)
    file.arreter()
    a = journal(tmp_path)["appels"][0]
    assert (a["type"], a["entree"], a["sortie"], a["cache_ecriture"], a["cache_lecture"]) == ("ia", 100, 50, 7, 9)
    assert a["cout"] == 0.05 and a["modele"] == "claude-sonnet-5-5"


def test_sans_journal_rien_nest_ecrit(donnees, tmp_path):
    file = FileClaude(ClientFaux([resultat()]))
    file.soumettre("x").result(timeout=5)
    file.arreter()
    assert not (tmp_path / "consommation").exists()


def test_aucune_donnee_d_etudiant_dans_le_journal(donnees, tmp_path):
    file = FileClaude(ClientFaux([resultat()]), journal=True)
    with c.contexte("francais", "202SNURE", "lab-3", "dupont-marie"):
        file.soumettre("<rapport>Marie Dupont, DA 1234567</rapport>").result(timeout=5)
    file.arreter()
    brut = (tmp_path / "consommation" / "journal.json").read_text(encoding="utf-8").lower()
    for interdit in ("dupont", "marie", "1234567", "202snure", "lab-3"):
        assert interdit not in brut
    a = journal(tmp_path)["appels"][0]
    assert len(a["rapport"]) == 8


def test_meme_rapport_meme_empreinte_autre_rapport_autre_empreinte(donnees, tmp_path):
    ajouter(donnees, "ia", 0.03)
    ajouter(donnees, "francais", 0.03)
    ajouter(donnees, "ia", 0.03, rapport=("cours", "lab", "roy-paul"))
    r = [a["rapport"] for a in journal(tmp_path)["appels"]]
    assert r[0] == r[1] != r[2]


def test_limite_notee_avec_heure_de_reprise(donnees, tmp_path):
    file = FileClaude(ClientFaux([ClaudeLimite("Claude usage limit reached. Your limit will reset at 5pm")]), journal=True)
    with pytest.raises(ClaudeLimite):
        file.soumettre("x").result(timeout=5)
    file.arreter()
    lim = c.resume()["limite"]
    assert lim["reprise_connue"] and lim["reprise"].startswith("2026-10-22T17:00")


def test_limite_sans_heure_dure_cinq_heures_puis_disparait(donnees):
    c.enregistrer_limite("Rate limit reached")
    assert c.resume()["limite"]["reprise_connue"] is False
    donnees["t"] = MAINTENANT + timedelta(hours=5, minutes=1)
    assert c.resume()["limite"] is None


@pytest.mark.parametrize("message,attendu", [
    ("resets 5pm", (17, 0)), ("resets at 12am", (0, 0)), ("limit will reset 17:40", (17, 40)), ("rien", None)])
def test_heure_de_reprise(message, attendu):
    t = c.heure_de_reprise(message, MAINTENANT)
    assert (None if t is None else (t.hour, t.minute)) == attendu


def test_fenetres_glissantes_5h_et_semaine(donnees):
    ajouter(donnees, "ia", 0.10)                                   # dans les 5 h
    ajouter(donnees, "ia", 0.20, il_y_a=timedelta(hours=4, minutes=59))
    ajouter(donnees, "ia", 0.40, il_y_a=timedelta(hours=5, minutes=1))   # hors 5 h, dans la semaine
    ajouter(donnees, "ia", 0.80, il_y_a=timedelta(days=6, hours=23))
    ajouter(donnees, "ia", 1.60, il_y_a=timedelta(days=7, hours=1))      # hors semaine
    r = c.resume()
    assert r["session"]["cout"] == pytest.approx(0.30) and r["session"]["appels"] == 2
    assert r["semaine"]["cout"] == pytest.approx(1.50) and r["semaine"]["appels"] == 4


def test_sans_calibrage_pourcentage_par_defaut_et_semaine_inconnue(donnees):
    ajouter(donnees, "ia", 0.10)
    r = c.resume()
    assert r["calibrage"]["calibre"] is False
    assert r["session"]["pct"] == pytest.approx(0.10 * c.PCT_PAR_USD_DEFAUT, abs=0.05)
    assert r["semaine"]["pct"] is None


def test_calibrage_deduit_le_pourcentage_par_dollar(donnees):
    ajouter(donnees, "ia", 0.50)
    r = c.enregistrer_calibrage(session=20, semaine=10)
    assert r["calibrage"]["calibre"] and r["calibrage"]["pct_par_usd"] == pytest.approx(40)
    assert r["session"]["pct"] == pytest.approx(20)
    assert r["semaine"]["pct"] == pytest.approx(10)
    assert r["calibrage"]["derniere"]["session"] == 20


def test_calibrage_trop_petit_est_note_sans_changer_le_ratio(donnees):
    ajouter(donnees, "ia", 0.01)
    r = c.enregistrer_calibrage(session=30)
    assert r["calibrage"]["calibre"] is False


def test_calibrage_median_des_derniers(donnees):
    ajouter(donnees, "ia", 1.0)
    for lu in (10, 20, 90):
        c.enregistrer_calibrage(session=lu)
    assert c.resume()["calibrage"]["pct_par_usd"] == pytest.approx(20)


def test_rapports_restants_et_lot_conseille(donnees):
    # calibrage 30 %/$ ; 3 types mesurés à 0,10 $ chacun => 9 % par rapport
    for t in ("francais", "ia", "references"):
        for _ in range(3):
            ajouter(donnees, t, 0.10, il_y_a=timedelta(days=2))
    ajouter(donnees, "plagiat", 0.20)
    c.enregistrer_calibrage(session=6)  # 6 % pour 0,20 $ dans la fenêtre => 30 %/$
    r = c.resume()
    assert r["pct_par_rapport"] == pytest.approx(9.0, abs=0.1)
    assert r["restants"] == (80 - 6) // 9 == 8
    assert r["lot_conseille"] == 8


def test_marge_reglable_change_les_restants(donnees):
    assert c.resume()["marge_pct"] == 20
    avant = c.resume()["restants"]
    r = c.regler(c.Reglages(marge_pct=50))
    assert r["plafond_pct"] == 50 and r["restants"] < avant


def test_estimation_du_lot_par_defaut_puis_mesuree(donnees):
    lot = [("a", True, True, True), ("b", True, True, True)]
    e = c.estimer(lot)
    assert e["mesure"] is False and e["calibre"] is False
    assert e["cout"] == pytest.approx(2 * sum(c.COUT_DEFAUT_USD[t] for t in ("francais", "ia", "references")))
    for t in ("francais", "ia", "references"):
        for _ in range(3):
            ajouter(donnees, t, 0.20, il_y_a=timedelta(days=1))
    e = c.estimer(lot)
    assert e["mesure"] is True and e["cout"] == pytest.approx(1.2)


def test_estimation_ne_compte_que_ce_qui_reste_a_faire(donnees):
    e = c.estimer([("a", False, True, False)])
    assert e["cout"] == pytest.approx(c.COUT_DEFAUT_USD["ia"])


def test_estimation_signale_le_depassement_de_la_marge(donnees):
    ajouter(donnees, "ia", 0.30)  # ~8 % utilisés
    lot = [(str(i), True, True, True) for i in range(40)]
    e = c.estimer(lot)
    assert e["depasse"] is True and 0 < e["max_rapports"] < 40
    ok = c.estimer(lot[: e["max_rapports"]])
    assert ok["depasse"] is False


def test_rotation_resume_les_vieux_appels_par_jour(donnees, tmp_path):
    ajouter(donnees, "ia", 0.10, il_y_a=timedelta(days=20))
    ajouter(donnees, "francais", 0.05, il_y_a=timedelta(days=20))
    ajouter(donnees, "ia", 0.10)
    doc = journal(tmp_path)
    assert len(doc["appels"]) == 1
    jour = (MAINTENANT - timedelta(days=20)).date().isoformat()
    assert doc["jours"][jour]["ia"]["n"] == 1 and doc["jours"][jour]["francais"]["cout"] == pytest.approx(0.05)
    assert "rapport" not in json.dumps(doc["jours"])


def test_par_jour_et_par_type(donnees):
    ajouter(donnees, "ia", 0.10)
    ajouter(donnees, "francais", 0.30, il_y_a=timedelta(days=1))
    r = c.resume()
    assert len(r["par_jour"]) == 7 and r["par_jour"][-1]["cout"] == pytest.approx(0.10)
    assert r["par_jour"][-2]["cout"] == pytest.approx(0.30)
    ia = next(t for t in r["par_type"] if t["type"] == "ia")
    assert ia["appels"] == 1 and ia["part"] == pytest.approx(0.25)


def test_journal_abime_ne_casse_rien(donnees, tmp_path):
    (tmp_path / "consommation").mkdir()
    (tmp_path / "consommation" / "journal.json").write_text("{pas du json", encoding="utf-8")
    assert c.resume()["session"]["cout"] == 0
    ajouter(donnees, "ia", 0.1)
    assert len(journal(tmp_path)["appels"]) == 1


def test_api(donnees):
    cl = TestClient(creer_app())
    ajouter(donnees, "ia", 0.5)
    assert cl.get("/api/consommation").json()["session"]["cout"] == pytest.approx(0.5)
    r = cl.post("/api/consommation/calibrage", json={"session": 25}).json()
    assert r["calibrage"]["calibre"]
    assert cl.post("/api/consommation/calibrage", json={"session": 140}).status_code == 422
    assert cl.post("/api/consommation/reglages", json={"marge_pct": 30}).json()["marge_pct"] == 30
