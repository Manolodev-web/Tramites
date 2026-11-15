"""TrámiteClaro v2 - Crawler con navegador headless (portales con JavaScript).
Produce LOS MISMOS JSON que r/crawler_hits.R -> el backend no cambia.
Uso:  pip install playwright networkx && playwright install chromium
      SEED_URL=https://portal.gob.bo/tramites python v2/crawler_playwright.py"""
import json, os, re, sys, time
from pathlib import Path
from urllib.parse import urldefrag, urlparse
import networkx as nx
from playwright.sync_api import sync_playwright

SEED = (os.getenv("SEED_URL") or (sys.argv[1] if len(sys.argv) > 1 else "")).strip()
if not SEED: sys.exit("Define SEED_URL o pasa la URL como argumento.")
MAX_PAGES, MAX_AUDIT = int(os.getenv("MAX_PAGES", "80")), int(os.getenv("MAX_AUDIT", "120"))
DELAY = float(os.getenv("DELAY_SECS", "1"))
OUT = Path(__file__).resolve().parent.parent / "backend" / "data"
DOC = re.compile(r"\.(pdf|docx?|xlsx?|pptx?|zip|rar|odt)(\?.*)?$", re.I)
NOISE = "nav, header, footer, aside, script, style, noscript, [role=navigation]"
EXTRACT = """(noise) => {
  document.querySelectorAll(noise).forEach(e => e.remove());
  const m = document.querySelector('main, article, #content, #main') || document.body;
  return {title: document.title || '', text: (m.innerText || '').replace(/\\s+/g, ' ').trim().slice(0, 500),
          hrefs: [...m.querySelectorAll('a[href]')].map(a => a.href)};
}"""

norm = lambda u: urldefrag(u)[0].rstrip("/")
host = lambda u: (urlparse(u).hostname or "").removeprefix("www.")
SEED = norm(SEED); SH = host(SEED)

def status_of(ctx, u):
    try:
        r = ctx.request.head(u, timeout=15000)
        if r.status in (403, 405, 501): r = ctx.request.get(u, timeout=15000)
        return r.status
    except Exception:
        return 0

def sitemap_urls(ctx):
    try:
        r = ctx.request.get(f"{urlparse(SEED).scheme}://{urlparse(SEED).netloc}/sitemap.xml", timeout=15000)
        if r.ok: return [norm(x) for x in re.findall(r"<loc>\s*([^<\s]+)\s*</loc>", r.text())
                         if host(x) == SH and not x.endswith(".xml")][:MAX_PAGES]
    except Exception: pass
    return []

def main():
    G, info, visited, queue = nx.DiGraph(), {}, [], [SEED]
    with sync_playwright() as p:
        br = p.chromium.launch()
        ctx = br.new_context(user_agent="TramiteClaroBot/1.0 (proyecto academico)", ignore_https_errors=True)
        page = ctx.new_page()
        sm = sitemap_urls(ctx); print(f"sitemap.xml: {len(sm)} URLs aportadas")
        while queue and len(visited) < MAX_PAGES:
            u = queue.pop(0)
            if u in visited: continue
            visited.append(u); print(f"[{len(visited)}/{MAX_PAGES}] {u}")
            time.sleep(DELAY)
            if DOC.search(u):
                info[u] = {"titulo": u.rsplit("/", 1)[-1], "resumen_texto": "", "status_http": status_of(ctx, u)}
            else:
                try:
                    resp = page.goto(u, wait_until="domcontentloaded", timeout=30000)
                    st = resp.status if resp else 0
                    try: page.wait_for_load_state("networkidle", timeout=8000)
                    except Exception: pass
                    page.evaluate("window.scrollTo(0, document.body.scrollHeight)"); page.wait_for_timeout(500)
                    d = page.evaluate(EXTRACT, NOISE)
                except Exception:
                    info[u] = {"titulo": u.rsplit("/", 1)[-1], "resumen_texto": "", "status_http": 0}; continue
                info[u] = {"titulo": d["title"].strip() or u.rsplit("/", 1)[-1], "resumen_texto": d["text"], "status_http": st}
                for h in dict.fromkeys(norm(x) for x in d["hrefs"] if x.startswith("http")):
                    if host(h) == SH and h != u:
                        G.add_edge(u, h)
                        if h not in visited and h not in queue: queue.append(h)
            if not queue and sm:                       # cuando se agota el BFS, completa con el sitemap
                queue = [x for x in sm if x not in visited]; sm = []
        pend = [n for n in G.nodes if n not in info]
        print(f"Auditando {min(len(pend), MAX_AUDIT)} de {len(pend)} URLs no visitadas")
        for u in pend[:MAX_AUDIT]:
            time.sleep(DELAY); info[u] = {"titulo": u.rsplit("/", 1)[-1], "resumen_texto": "", "status_http": status_of(ctx, u)}
        br.close()
    if G.number_of_edges() == 0:
        sys.exit("Sin enlaces internos: la navegación no usa <a href> (clics/login/captcha). Usa sitemap o lista manual.")
    try: hubs, auths = nx.hits(G, max_iter=1000, tol=1e-10, normalized=True)
    except nx.PowerIterationFailedConvergence: hubs, auths = nx.hits(G, max_iter=5000, tol=1e-6, normalized=True)
    mh, ma = max(hubs.values()) or 1, max(auths.values()) or 1
    depth = nx.single_source_shortest_path_length(G, SEED) if SEED in G else {}
    nodes = [{"url": u, "titulo": info.get(u, {}).get("titulo", u), "resumen_texto": info.get(u, {}).get("resumen_texto", ""),
              "status_http": info.get(u, {}).get("status_http"), "hub_score": round(hubs[u] / mh, 6),
              "auth_score": round(auths[u] / ma, 6), "grado_entrada": G.in_degree(u), "grado_salida": G.out_degree(u),
              "profundidad": depth.get(u)} for u in G.nodes]
    rotos = [n for n in nodes if n["status_http"] is not None and (n["status_http"] >= 400 or n["status_http"] == 0)]
    print(f"\nNodos {len(nodes)} | Aristas {G.number_of_edges()} | Rotos {len(rotos)} ({100*len(rotos)/len(nodes):.1f}%)")
    for k in ("auth_score", "hub_score"):
        print(f"Top 5 {k}:", [(n['url'], n[k]) for n in sorted(nodes, key=lambda x: -x[k])[:5]])
    OUT.mkdir(parents=True, exist_ok=True)
    (OUT / "nodos_hits.json").write_text(json.dumps(nodes, ensure_ascii=False), encoding="utf-8")
    (OUT / "aristas_grafo.json").write_text(json.dumps([{"source": a, "target": b} for a, b in G.edges]), encoding="utf-8")
    print("JSON escritos en", OUT)

if __name__ == "__main__": main()
