import sys
from pathlib import Path
from playwright.sync_api import sync_playwright
JS = r"""() => {
 const lum = c => { const [r,g,b] = c.map(v => { v/=255; return v<=.03928? v/12.92 : ((v+.055)/1.055)**2.4; }); return .2126*r+.7152*g+.0722*b; };
 const rgba = s => { const m = s.match(/[\d.]+/g).map(Number); return [m[0],m[1],m[2], m[3]===undefined?1:m[3]]; };
 const fond = el => { let e = el; while (e) { const c = rgba(getComputedStyle(e).backgroundColor); if (c[3] > .5) return c; e = e.parentElement; } return [255,255,255,1]; };
 const res = new Map(); let n = 0;
 for (const el of document.querySelectorAll('.cadre *')) {
   if (![...el.childNodes].some(t => t.nodeType === 3 && t.textContent.trim())) continue;
   if (el.closest('[disabled],[aria-disabled=true]')) continue;
   const cs = getComputedStyle(el); if (cs.visibility === 'hidden' || el.getClientRects().length === 0) continue;
   const c = rgba(cs.color), f = fond(el);
   const col = c.map((v,i) => i<3 ? v*c[3] + f[i]*(1-c[3]) : 1);
   const L1 = lum(col), L2 = lum(f), r = (Math.max(L1,L2)+.05)/(Math.min(L1,L2)+.05);
   const taille = parseFloat(cs.fontSize), gras = parseInt(cs.fontWeight) >= 700;
   const seuil = (taille >= 24 || (taille >= 18.66 && gras)) ? 3 : 4.5; n++;
   if (r < seuil) res.set(cs.color + ' sur ' + f.join(','), (el.textContent.trim().slice(0,30)) + ' ' + r.toFixed(2));
 }
 return [n, [...res.entries()]];
}"""
with sync_playwright() as p:
    nav = p.chromium.launch(channel="chrome")
    for f in sorted(Path(sys.argv[1]).glob("p*.html")):
        pg = nav.new_page(viewport={"width": 1500, "height": 900}); pg.goto(f.resolve().as_uri()); pg.wait_for_timeout(300)
        n, mauvais = pg.evaluate(JS); print(f.name, n, "textes vérifiés, sous AA :", mauvais)
    nav.close()
