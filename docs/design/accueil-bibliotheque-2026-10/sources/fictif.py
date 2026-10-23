"""Bibliothèque FICTIVE pour les captures (noms inventés). Usage : python fictif.py <dossier>"""
import io, json, random, sys, unicodedata
asc=lambda t: unicodedata.normalize("NFKD",t).encode("ascii","ignore").decode().lower()
from pathlib import Path
from reportlab.pdfgen import canvas

random.seed(7)
racine = Path(sys.argv[1]) / "bibliotheque"
PRENOMS = "Alexis Béatrice Camille Damien Éloïse Félix Gabrielle Hugo Inès Jérémy Kim Laurence Mathis Noémie Olivier Pénélope Raphaël Sarah Thomas Ulysse Victoria William Xavier Yasmine Zacharie Léa Antoine Rosalie Émile Juliette Charles Maëlle Nathan Florence".split()
NOMS = "Bérubé Cloutier Desrosiers Fontaine Gauvreau Hébert Imbeault Jolicoeur Lachance Marcoux Nadeau Ouellet Paradis Quessy Rioux Simard Thibodeau Vachon Leclerc Bolduc Lapointe Poirier Gosselin Bélanger Côté Drouin Lemieux Morin Pelletier Turcotte Boucher Caron Dufour Girard".split()


def pdf(texte):
    t = io.BytesIO(); c = canvas.Canvas(t)
    c.drawString(72, 750, texte); c.drawString(72, 720, "Introduction : on mesure la masse volumique de plusieurs solutions.")
    c.showPage(); c.drawString(72, 750, "Résultats et discussion."); c.save()
    return t.getvalue()


def faute(i):
    return {"id": i, "debut": i * 10, "fin": i * 10 + 6, "texte": "mesure", "message": "", "regle": "", "categorie": "",
            "suggestions": ["mesurent"], "zones": [{"page": 1, "x0": 72, "y0": 90 + 14 * i, "x1": 140, "y1": 102 + 14 * i}]}


def ecrire(p, d):
    p.parent.mkdir(parents=True, exist_ok=True); p.write_text(json.dumps(d), encoding="utf-8")


used = set()
def etudiant():
    while True:
        p, n = random.choice(PRENOMS), random.choice(NOMS)
        if (p, n) not in used:
            used.add((p, n)); return p, n


def classe(cours, groupe, n):
    ets = []
    for _ in range(n):
        p, nom = etudiant()
        ets.append({"id": f"{asc(nom)}-{asc(p)}", "nom": nom, "prenom": p, "da": str(random.randint(2300000, 2699999))})
    ecrire(racine / cours / groupe / "classe.json", {"cours": cours, "groupe": groupe, "etudiants": ets})
    return ets


def remplir(cours, groupe, ets, lab, profil, archive=False):
    """profil : fraction (terminés, en cours analysés, à trancher, juste annotés, rien)"""
    remis = ets[: max(1, len(ets) - random.randint(0, 2))]
    for i, e in enumerate(remis):
        d = racine / cours / groupe / lab / e["id"]
        d.mkdir(parents=True, exist_ok=True)
        (d / "rapport.pdf").write_bytes(pdf(f"{lab} - {e['prenom']} {e['nom']}"))
        ecrire(d / "origine.json", {"fichier": f"{e['nom']}_{e['da']}_Rapport.pdf"})
        r = random.random(); t, a, tr, an = profil
        if r < t:
            ecrire(d / "francais.json", {"version": 1, "fautes": [faute(k) for k in range(4)], "decisions": {str(k): "acceptee" for k in range(4)},
                                         "choix": {}, "masquees": [], "decalages": {}, "claude": {"ok": True, "erreur": None, "ajoutees": 1}})
            ecrire(d / "indices_ia.json", {"force": random.choice(["faible"] * 6 + ["moderee", "marquee"])})
            ecrire(d / "annotations.json", {"version": 1, "pages": {"1": [{"outil": "crayon", "couleur": "#d32f2f", "largeur_min": 1, "largeur_max": 2, "courbe": 1, "points": [[80, 80, .5], [140, 90, .5]]}]}})
            ecrire(d / "statut.json", {"termine": True, "note": f"{random.randint(13, 19)},{random.choice([0, 5])}"})
        elif r < t + a:
            ecrire(d / "francais.json", {"version": 1, "fautes": [faute(k) for k in range(3)], "decisions": {str(k): "acceptee" for k in range(3)},
                                         "choix": {}, "masquees": [], "decalages": {}, "claude": {"ok": random.random() > .15, "erreur": None, "ajoutees": 0}})
            ecrire(d / "indices_ia.json", {"force": random.choice(["faible", "faible", "moderee"])})
        elif r < t + a + tr:
            ecrire(d / "francais.json", {"version": 1, "fautes": [faute(k) for k in range(6)], "decisions": {"0": "acceptee"},
                                         "choix": {}, "masquees": [], "decalages": {}, "claude": {"ok": True, "erreur": None, "ajoutees": 2}})
            ecrire(d / "indices_ia.json", {"force": random.choice(["faible", "moderee", "marquee"])})
        elif r < t + a + tr + an:
            ecrire(d / "annotations.json", {"version": 1, "pages": {"1": [{"outil": "crayon", "couleur": "#1565c0", "largeur_min": 1, "largeur_max": 2, "courbe": 1, "points": [[80, 80, .5], [140, 90, .5]]}]}})
    if archive:
        ecrire(racine / cours / groupe / lab / "archive.json", {"archive": True})


# Session en cours (A26)
for cours, groupes in [("NYA-A26", ["01", "02", "03"]), ("NYB-A26", ["04"])]:
    for g in groupes:
        ets = classe(cours, g, random.randint(26, 32))
        if cours == "NYA-A26":
            remplir(cours, g, ets, "lab-1", (1, 0, 0, 0))
            remplir(cours, g, ets, "lab-2", (.45, .2, .2, .05))
            remplir(cours, g, ets, "lab-3", (0, 0, 0, .05))
        else:
            remplir(cours, g, ets, "lab-1", (.92, .08, 0, 0))
            remplir(cours, g, ets, "lab-2", (.1, .3, .35, .1))
# Session passée (H26), tout archivé
for cours, groupes in [("NYA-H26", ["01", "02"]), ("NYC-H26", ["05"])]:
    for g in groupes:
        ets = classe(cours, g, random.randint(25, 30))
        for lab in ["lab-1", "lab-2", "lab-3", "lab-4", "lab-5"]:
            remplir(cours, g, ets, lab, (1, 0, 0, 0), archive=True)

# Fichiers à trancher
att = racine / "_attente"
for i, (nom, raison) in enumerate([("Rapport_lab2_final.pdf", "aucune_correspondance"), ("Cote_2412345_Rapport.pdf", "da_inconnu"), ("Lachance_Rapport_Lab2.pdf", "ambigu")]):
    (att).mkdir(parents=True, exist_ok=True)
    (att / f"att{i}.pdf").write_bytes(pdf("Rapport"))
    ecrire(att / f"att{i}.json", {"id": f"att{i}", "fichier": nom, "cours": "NYA-A26", "groupe": "", "lab": "lab-2", "raison": raison, "da": "", "candidats": []})
print("ok", sum(1 for _ in racine.rglob("rapport.pdf")), "rapports")
