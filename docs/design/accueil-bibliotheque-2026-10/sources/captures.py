"""Captures des maquettes : chaque cadre (#seul-<id>) à sa taille réelle. Usage : python captures.py <dossier_html> <sortie> [fichier…]"""
import re, sys
from pathlib import Path
from playwright.sync_api import sync_playwright
src, sortie = Path(sys.argv[1]), Path(sys.argv[2]); sortie.mkdir(parents=True, exist_ok=True)
noms = sys.argv[3:] or [p.name for p in src.glob("p*.html")]
TAILLE = {"ipad": (1180, 820), "portrait": (820, 1180), "pc": (1440, 900)}
with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome")
    for nom in noms:
        html = (src / nom).read_text(encoding="utf-8")
        for id_, classe in re.findall(r'<div class="ecran" id="([^"]+)">.*?<div class="cadre (\w+)', html, re.S):
            l, h = TAILLE[classe]
            page = nav.new_page(viewport={"width": l, "height": h})
            erreurs = []
            page.on("console", lambda m: erreurs.append(m.text) if m.type == "error" else None)
            page.on("pageerror", lambda e: erreurs.append(str(e)))
            page.goto((src / nom).resolve().as_uri() + f"#seul-{id_}")
            page.wait_for_timeout(300)
            petits = page.evaluate("""() => [...document.querySelectorAll('.ecran.cible a, .ecran.cible button, .ecran.cible input, .ecran.cible select')]
              .filter(e => { const r = e.getBoundingClientRect(); return r.width > 0 && r.height > 0 && r.height < 44 && !e.closest('.resultats .grp') && !e.matches('.cq-conso, .cq-lot'); })
              .map(e => (e.className || e.tagName) + ':' + Math.round(e.getBoundingClientRect().height) + ' ' + (e.textContent||'').trim().slice(0,30))""")
            debord = page.evaluate("() => { const m = document.querySelector('.ecran.cible main'); return m ? m.scrollWidth - m.clientWidth : 0; }")
            page.screenshot(path=str(sortie / f"{nom[:-5]}-{id_}.png"))
            print(nom, id_, "erreurs:", erreurs, "| cibles < 44 px:", petits[:6], "| débordement:", debord)
            page.close()
    nav.close()
