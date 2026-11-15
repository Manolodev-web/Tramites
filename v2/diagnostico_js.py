"""¿El portal necesita JavaScript? Compara enlaces del HTML crudo vs. el HTML renderizado.
Uso:  python v2/diagnostico_js.py https://portal.gob.bo/tramites
Requiere: pip install httpx beautifulsoup4   (y opcional: playwright + `playwright install chromium`)"""
import re, sys
from urllib.parse import urljoin, urlparse
import httpx
from bs4 import BeautifulSoup

url = sys.argv[1]
host = urlparse(url).hostname.removeprefix("www.")
HDR = {"User-Agent": "TramiteClaroBot/1.0 (diagnostico academico)"}

def internos(hrefs, base):
    out = set()
    for h in hrefs:
        if not h or h.startswith(("#", "mailto:", "tel:", "javascript:")): continue
        a = urljoin(base, h)
        if (urlparse(a).hostname or "").removeprefix("www.") == host: out.add(a.split("#")[0])
    return out

r = httpx.get(url, headers=HDR, follow_redirects=True, timeout=20, verify=False)
soup = BeautifulSoup(r.text, "html.parser")
raw = internos([a.get("href") for a in soup.find_all("a")], url)
marcas = [m for m, p in {"React/Next": r'id="root"|__NEXT_DATA__|data-reactroot', "Angular": r"ng-version|<app-root",
          "Vue/Nuxt": r"id=\"app\"|__NUXT__|data-v-", "Aviso noscript": r"<noscript>[^<]*(javascript|JavaScript)"}.items()
          if re.search(p, r.text)]
print(f"HTTP {r.status_code} | enlaces internos en HTML crudo: {len(raw)} | marcas SPA: {marcas or 'ninguna'}")

base = f"{urlparse(url).scheme}://{urlparse(url).netloc}"
for nombre, ruta in [("sitemap", "/sitemap.xml"), ("WordPress API", "/wp-json/wp/v2/pages?per_page=1")]:
    try:
        s = httpx.get(base + ruta, headers=HDR, timeout=10, verify=False, follow_redirects=True).status_code
        print(f"{nombre}: {'DISPONIBLE' if s == 200 else f'no ({s})'}  {base + ruta}")
    except Exception:
        print(f"{nombre}: no accesible")

try:
    from playwright.sync_api import sync_playwright
    with sync_playwright() as p:
        b = p.chromium.launch(); pg = b.new_page(); pg.goto(url, wait_until="domcontentloaded", timeout=30000)
        try: pg.wait_for_load_state("networkidle", timeout=8000)
        except Exception: pass
        ren = internos(pg.eval_on_selector_all("a[href]", "els => els.map(e => e.href)"), url); b.close()
    print(f"enlaces internos RENDERIZADOS: {len(ren)}")
    if len(ren) > max(5, 3 * len(raw)):
        print("VEREDICTO: necesita JavaScript -> usa v2/crawler_playwright.py")
    elif not ren:
        print("VEREDICTO: ni renderizado hay enlaces <a href>: navegación por clics/login/captcha. Usa sitemap o lista manual de URLs.")
    else:
        print("VEREDICTO: HTML estático suficiente -> r/crawler_hits.R funciona.")
except ImportError:
    print("(Instala playwright para el veredicto completo.) Si el crudo tiene <5 enlaces y hay marcas SPA, probablemente necesitas JS.")
