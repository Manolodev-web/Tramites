# TrámiteClaro Bolivia (LexBolivia AI)
Auditoría de portales públicos con **HITS (Kleinberg)** + chatbot que prioriza fuentes oficiales.

## Estructura
```
tramiteclaro/
├── r/crawler_hits.R            # Capa A: crawler BFS + scraping + HITS (igraph) -> JSON
├── backend/                    # Capa B: API FastAPI (Render)
│   ├── main.py  requirements.txt  render.yaml
│   └── data/nodos_hits.json  aristas_grafo.json   # hoy: DATOS DE EJEMPLO ficticios
├── frontend/tramiteclaro.html  # Capa C: panel + chat (pegar en tu web)
└── README.md
```
## Ejecución rápida
1. **R** (desde la raíz del repo): `install.packages(c("httr","rvest","xml2","dplyr","igraph","jsonlite"))`,
   edita `seed_url` en `r/crawler_hits.R` y ejecuta `source("r/crawler_hits.R")`. Sobrescribe los JSON de ejemplo.
2. **API local**: `cd backend && pip install -r requirements.txt && uvicorn main:app --reload` → http://127.0.0.1:8000/docs
   (opcional: `export GROQ_API_KEY=...` o `GEMINI_API_KEY=...`; sin clave responde en modo de respaldo).
3. **Render**: sube el repo a GitHub → New Web Service → Root Directory `backend`,
   Build `pip install -r requirements.txt`, Start `uvicorn main:app --host 0.0.0.0 --port $PORT`
   (o usa `render.yaml`). Define `GROQ_API_KEY`/`GEMINI_API_KEY` y `ALLOWED_ORIGINS=https://tu-web.com`.
4. **Frontend**: pega `frontend/tramiteclaro.html` en tu página y cambia `TC_API`.
5. **Actualizar datos**: correr R → `git add backend/data && git commit && git push` (Render redespliega).

## Notas importantes
- Respeta el `robots.txt` y los términos de cada portal; el crawler usa pausa de 1 s y User-Agent identificable.
- Authority/Hub miden **estructura de enlaces**, no vigencia legal: el chatbot debe invitar a confirmar en la entidad.
- La limpieza de `<header>` puede borrar contenido en temas que lo usan como envoltorio del artículo; ajusta el XPath si pasa.
- Plan gratuito de Render: el primer request tras inactividad tarda ~50 s.
- Los modelos LLM se configuran con `GROQ_MODEL` / `GEMINI_MODEL`; verifica que sigan vigentes.

## Hoja de Ruta - Futuras Actualizaciones (v2.0)
- Portales con JavaScript dinámico: RSelenium / Playwright en el crawler.
- Actualización semanal automática con GitHub Actions (R → commit de JSON → redeploy).
- Lectura del texto de PDFs (pdftools) para indexar requisitos dentro de los formularios.
- Detección de vigencia (fechas, "derogado", versiones) como tercera señal del ranking.
- Embeddings multilingües + índice vectorial ligero (FAISS) combinados con HITS.
- Grafo 3D interactivo en el frontend (3d-force-graph) y comparación histórica de salud del portal.
- Multi-portal (SEPREC, SIN, Gestora, UMSA, Lexivox) con selector y caché por dominio.
- Rate limiting, caché de respuestas y registro de preguntas sin respuesta.

## v2.0 (en progreso) - Portales con JavaScript
1. Diagnóstico: `python v2/diagnostico_js.py https://portal.gob.bo/tramites` (dice si basta R o se necesita navegador).
2. Si requiere JS: `pip install playwright networkx && playwright install chromium` y
   `SEED_URL=https://... python v2/crawler_playwright.py` (mismos JSON, el backend no cambia).
3. Automático: workflow `.github/workflows/actualizar.yml` (define la variable `SEED_URL` en GitHub).
Pendiente v2.x: lectura de texto de PDFs, señal de vigencia, grafo 3D.
