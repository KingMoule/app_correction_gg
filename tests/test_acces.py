"""Code d'accès (audit E6) : toutes les routes /api refusées sans session, Host, Origin, limite d'essais."""
import re

import pytest
from fastapi.routing import APIRoute
from fastapi.testclient import TestClient
from starlette.routing import Mount

from moteur import acces
from moteur.app import creer_app
from tests.test_bibliotheque import client  # noqa: F401
from tests.test_export import rapport  # noqa: F401  (rapport fictif importé)

CODE = "lab-secret-2026"


@pytest.fixture
def donnees(tmp_path, monkeypatch):
    monkeypatch.setenv("CORRECTION_DONNEES", str(tmp_path / "donnees"))
    return tmp_path / "donnees"


@pytest.fixture
def avec_code(donnees, monkeypatch):
    monkeypatch.delenv("CORRECTION_SANS_CODE")
    acces.definir_code(CODE)
    return TestClient(creer_app())


def connecte(client: TestClient) -> TestClient:
    r = client.post("/api/connexion", json={"code": CODE})
    assert r.status_code == 200
    return client


# ----- toutes les routes -----

def aplatir(routes, prefixe=""):
    """(chemin, méthodes, route) de toutes les routes, y compris celles des routeurs inclus (FastAPI récent :
    `_IncludedRouter` paresseux). Un type de route inconnu fait échouer le test plutôt que d'être ignoré."""
    for route in routes:
        if isinstance(route, APIRoute):
            yield prefixe + route.path, route.methods, route
        elif hasattr(route, "original_router"):
            yield from aplatir(route.original_router.routes, prefixe + route.include_context.prefix)
        elif isinstance(route, Mount):
            yield prefixe + route.path, None, route
        else:
            raise AssertionError(f"type de route inconnu, à protéger : {route!r}")


def routes_api(app):
    for chemin, methodes, route in aplatir(app.routes):
        if isinstance(route, APIRoute):
            for methode in sorted(methodes - {"HEAD", "OPTIONS"}):
                yield methode, re.sub(r"\{[^}]+\}", "x", chemin)


def test_il_y_a_des_routes_a_verifier():
    assert len(list(routes_api(creer_app()))) > 40


def test_seules_routes_hors_api_sont_la_pwa_statique():
    for chemin, methodes, route in aplatir(creer_app().routes):
        if methodes is None:
            assert chemin == "" and isinstance(route, Mount), chemin  # la PWA (aucune donnée)
        else:
            assert chemin.startswith("/api/"), f"route hors /api non protégée : {chemin}"


@pytest.mark.parametrize("methode,chemin", [pytest.param(m, p, id=f"{m} {p}")
                                            for m, p in routes_api(creer_app())
                                            if p not in acces.PUBLIQUES])
def test_route_api_refusee_sans_session(avec_code, methode, chemin):
    r = avec_code.request(methode, chemin)
    assert r.status_code == 401, f"{methode} {chemin} -> {r.status_code}"
    assert r.json() == {"detail": "Code d'accès requis."}


@pytest.mark.parametrize("methode,chemin", [pytest.param(m, p, id=f"{m} {p}")
                                            for m, p in routes_api(creer_app())
                                            if p not in acces.PUBLIQUES])
def test_route_api_refusee_avec_faux_cookie(avec_code, methode, chemin):
    r = avec_code.request(methode, chemin, cookies={acces.NOM_COOKIE: "9999999999.abc.deadbeef"})
    assert r.status_code == 401


def test_routes_publiques_sont_connues():
    assert {p for _, p in routes_api(creer_app()) if p in acces.PUBLIQUES} == acces.PUBLIQUES


def test_docs_et_openapi_desactives(avec_code):
    for chemin in ("/docs", "/redoc", "/openapi.json"):
        assert avec_code.get(chemin).status_code == 404


def test_pwa_statique_reste_publique(avec_code):
    assert "Correction de labs" in avec_code.get("/").text
    assert avec_code.get("/acces.html").status_code == 200
    assert avec_code.get("/manifest.webmanifest").status_code == 200


def test_fautes_de_chemin_ne_contournent_pas(avec_code):
    for chemin in ("/api", "/api/", "//api/etat", "/api/etat/", "/api%2Fetat", "/API/etat", "/api/../api/etat"):
        r = avec_code.get(chemin)
        assert r.status_code in (401, 404), (chemin, r.status_code)
        assert "donnees" not in r.text


# ----- connexion -----

def test_cookie_valide_accepte(avec_code):
    assert avec_code.get("/api/etat").status_code == 401
    r = avec_code.post("/api/connexion", json={"code": CODE})
    assert r.status_code == 200
    cookie = r.headers["set-cookie"]
    assert "HttpOnly" in cookie and "SameSite=Strict" in cookie and "Max-Age=31536000" in cookie
    assert avec_code.get("/api/etat").status_code == 200
    assert avec_code.get("/api/connexion").json() == {"requis": True, "configure": True, "connecte": True}


def test_mauvais_code(avec_code):
    r = avec_code.post("/api/connexion", json={"code": "mauvais-code"})
    assert r.status_code == 401 and "set-cookie" not in r.headers
    assert avec_code.get("/api/etat").status_code == 401
    assert avec_code.get("/api/connexion").json()["connecte"] is False


def test_code_jamais_en_clair_sur_disque(avec_code, donnees):
    contenu = (donnees / "acces.json").read_text(encoding="utf-8")
    assert CODE not in contenu and "empreinte" in contenu


def test_code_trop_court_refuse(donnees):
    with pytest.raises(ValueError):
        acces.definir_code("1234567")


def test_aucun_code_defini_ferme_tout(donnees, monkeypatch):
    monkeypatch.delenv("CORRECTION_SANS_CODE")
    c = TestClient(creer_app())
    assert c.get("/api/etat").status_code == 401
    assert c.post("/api/connexion", json={"code": CODE}).status_code == 503


def test_deconnexion_efface_le_cookie(avec_code):
    connecte(avec_code)
    r = avec_code.post("/api/deconnexion")
    assert "Max-Age=0" in r.headers["set-cookie"]
    avec_code.cookies.clear()
    assert avec_code.get("/api/etat").status_code == 401


def test_nouveau_code_revoque_les_sessions(avec_code):
    connecte(avec_code)
    assert avec_code.get("/api/etat").status_code == 200
    acces.definir_code("un-autre-code-2026")
    assert avec_code.get("/api/etat").status_code == 401
    assert avec_code.post("/api/connexion", json={"code": CODE}).status_code == 401
    assert avec_code.post("/api/connexion", json={"code": "un-autre-code-2026"}).status_code == 200


def test_session_expiree_ou_modifiee(avec_code):
    jeton = acces.creer_jeton(maintenant=0)  # expire en 1971 + 1 an
    assert acces.jeton_valide(jeton) == (False, False)
    bon = acces.creer_jeton()
    assert acces.jeton_valide(bon) == (True, False)
    corps, _, sig = bon.rpartition(".")
    assert acces.jeton_valide(f"{int(corps.split('.')[0]) + 999}.{corps.split('.', 1)[1]}.{sig}") == (False, False)


def test_session_renouvelee_quand_elle_vieillit(avec_code):
    vieux = acces.creer_jeton(maintenant=__import__("time").time() - 200 * 24 * 3600)
    assert acces.jeton_valide(vieux) == (True, True)
    r = avec_code.get("/api/etat", cookies={acces.NOM_COOKIE: vieux})
    assert r.status_code == 200 and "session_correction=" in r.headers["set-cookie"]
    neuf = avec_code.get("/api/etat", cookies={acces.NOM_COOKIE: acces.creer_jeton()})
    assert "set-cookie" not in neuf.headers


def test_lien_ouvert_dans_le_navigateur_va_a_l_ecran_de_saisie(avec_code):
    r = avec_code.get("/api/export/travaux?a=1", headers={"Sec-Fetch-Mode": "navigate", "Accept": "text/html"},
                      follow_redirects=False)
    assert r.status_code == 303
    assert r.headers["location"] == "/acces.html?suite=%2Fapi%2Fexport%2Ftravaux%3Fa%3D1"


# ----- limite d'essais -----

def test_limite_d_essais(avec_code):
    for _ in range(4):
        assert avec_code.post("/api/connexion", json={"code": "faux-code-x"}).status_code == 401
    r = avec_code.post("/api/connexion", json={"code": "faux-code-x"})  # 5e échec : blocage
    assert r.status_code == 401 and r.json()["attente"] == 30
    r = avec_code.post("/api/connexion", json={"code": CODE})  # même le bon code est refusé pendant le blocage
    assert r.status_code == 429 and int(r.headers["Retry-After"]) > 0
    assert avec_code.get("/api/etat").status_code == 401


def test_limite_qui_grandit_et_se_leve():
    t = [0.0]
    lim = acces.LimiteEssais(horloge=lambda: t[0])
    for _ in range(5):
        lim.echec("a")
    assert lim.attente("a") == 30
    t[0] = 31
    assert lim.attente("a") == 0
    lim.echec("a")
    assert lim.attente("a") == 60
    for _ in range(20):
        lim.echec("a")
    assert lim.attente("a") == 900
    assert lim.attente("autre") == 0
    lim.succes("a")
    assert lim.attente("a") == 0


def test_succes_remet_le_compteur_a_zero(avec_code):
    for _ in range(3):
        avec_code.post("/api/connexion", json={"code": "faux-code-x"})
    assert avec_code.post("/api/connexion", json={"code": CODE}).status_code == 200
    for _ in range(3):
        assert avec_code.post("/api/connexion", json={"code": "faux-code-x"}).status_code == 401


# ----- Host et Origin -----

@pytest.mark.parametrize("host", ["evil.example", "evil.example:8001", "192.168.1.5.evil.example", "localhost.evil.example"])
def test_host_etranger_refuse(avec_code, host):
    connecte(avec_code)
    assert avec_code.get("/api/etat", headers={"Host": host}).status_code == 403
    assert avec_code.get("/", headers={"Host": host}).status_code == 403


@pytest.mark.parametrize("host", ["localhost:8001", "127.0.0.1:8001", "[::1]:8001", "192.168.1.23:8001", "testserver"])
def test_host_local_accepte(avec_code, host):
    connecte(avec_code)
    assert avec_code.get("/api/etat", headers={"Host": host}).status_code == 200


def test_host_etranger_refuse_meme_en_mode_local(donnees):
    c = TestClient(creer_app())  # CORRECTION_SANS_CODE=1 (conftest)
    assert c.get("/api/etat").status_code == 200
    assert c.get("/api/etat", headers={"Host": "evil.example"}).status_code == 403


def test_hote_supplementaire_par_variable(avec_code, monkeypatch):
    monkeypatch.setenv("CORRECTION_HOTES", "testserver, monordi.local")
    assert avec_code.get("/api/connexion", headers={"Host": "monordi.local:8001"}).status_code == 200


@pytest.mark.parametrize("origine", ["http://site-malveillant.example", "null", "http://localhost:9999"])
def test_origin_etranger_refuse_sur_ecriture(avec_code, origine):
    connecte(avec_code)
    for methode, chemin in [("POST", "/api/lot/arreter"), ("PUT", "/api/francais/lexique"), ("DELETE", "/api/x")]:
        r = avec_code.request(methode, chemin, headers={"Origin": origine, "Content-Type": "text/plain"})
        assert r.status_code == 403, (methode, chemin, r.status_code)
    r = avec_code.post("/api/connexion", json={"code": CODE}, headers={"Origin": origine})
    assert r.status_code == 403


def test_scenario_audit_liste_de_classe_depuis_un_autre_site(donnees):
    """Mode local (sans code) : le POST d'un site étranger ne remplace pas la liste de classe."""
    c = TestClient(creer_app())
    r = c.post("/api/bibliotheque/classes", headers={"Origin": "http://site-malveillant.example"},
               files={"fichier": ("ListeEtudiants_cours101_gr00001.csv", b"Nom;Prenom\nPirate;X\n")})
    assert r.status_code == 403
    assert not (donnees / "bibliotheque").exists()


def test_referer_etranger_refuse_si_pas_d_origin(avec_code):
    connecte(avec_code)
    r = avec_code.post("/api/lot/arreter", headers={"Referer": "http://site-malveillant.example/page"})
    assert r.status_code == 403
    r = avec_code.post("/api/lot/arreter", headers={"Referer": "http://testserver/lecteur.html"})
    assert r.status_code == 200


def test_origin_identique_et_lecture_croisee(avec_code):
    connecte(avec_code)
    assert avec_code.post("/api/lot/arreter", headers={"Origin": "http://testserver"}).status_code == 200
    # une lecture (GET) n'est pas filtrée par Origin : c'est le cookie SameSite=Strict et le CORS absent qui protègent
    assert avec_code.get("/api/etat", headers={"Origin": "http://autre.example"}).status_code == 200


# ----- mode local -----

def test_mode_local_sans_code(donnees):
    c = TestClient(creer_app())
    assert c.get("/api/etat").status_code == 200
    assert c.get("/api/connexion").json()["requis"] is False


def test_lancement_local_ne_demande_pas_de_code(donnees, monkeypatch):
    import sys
    from moteur import __main__ as demarrage
    appels = []
    monkeypatch.setattr(sys, "argv", ["moteur", "--local", "--port", "0"])
    monkeypatch.setattr(demarrage, "port_libre", lambda *a: True)
    monkeypatch.setattr(demarrage.uvicorn, "run", lambda *a, **k: appels.append(k))
    demarrage.main()
    assert appels and not acces.est_configure()


def test_premier_lancement_reseau_demande_le_code(donnees, monkeypatch):
    import sys
    from moteur import __main__ as demarrage
    monkeypatch.setattr(sys, "argv", ["moteur", "--port", "0"])
    monkeypatch.setattr(demarrage, "port_libre", lambda *a: True)
    monkeypatch.setattr(demarrage.uvicorn, "run", lambda *a, **k: None)
    saisies = iter([CODE, CODE])
    monkeypatch.setattr(acces.getpass, "getpass", lambda *a: next(saisies))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: True, raising=False)
    demarrage.main()
    assert acces.est_configure() and acces.verifier_code(CODE)


def test_premier_lancement_sans_terminal_s_arrete(donnees, monkeypatch, capsys):
    import sys
    from moteur import __main__ as demarrage
    monkeypatch.setattr(sys, "argv", ["moteur", "--port", "0"])
    monkeypatch.setattr(demarrage, "port_libre", lambda *a: True)
    monkeypatch.setattr(demarrage.uvicorn, "run", lambda *a, **k: pytest.fail("ne doit pas démarrer sans code"))
    monkeypatch.setattr(sys.stdin, "isatty", lambda: False, raising=False)
    with pytest.raises(SystemExit):
        demarrage.main()
    assert "nouveau-code" in capsys.readouterr().err


# ----- fichiers sensibles -----

def test_pdf_et_exports_proteges(rapport, monkeypatch):
    """Un vrai rapport existe : son PDF, ses annotations et les exports sont refusés sans session, servis avec."""
    client, _ = rapport
    monkeypatch.delenv("CORRECTION_SANS_CODE")
    acces.definir_code(CODE)
    urls = ["/api/bibliotheque/rapport/202SNURE/00002/lab-3/dube-alice",
            "/api/annotations/202SNURE/00002/lab-3/dube-alice",
            "/api/export/202SNURE/00002/lab-3/dube-alice",
            "/api/export-lot/travaux", "/api/export-lot/tableau/202SNURE/lab-3",
            "/api/bibliotheque", "/api/indices-ia/texte/202SNURE/00002/lab-3/dube-alice"]
    for url in urls:
        assert client.get(url).status_code == 401, url
    client.post("/api/connexion", json={"code": CODE})
    assert client.get(urls[0]).content.startswith(b"%PDF")
    assert client.get(urls[2]).content.startswith(b"%PDF")
