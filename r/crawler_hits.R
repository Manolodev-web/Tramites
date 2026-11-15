# =============================================================================
# TrámiteClaro Bolivia - Capa A: Crawler + Scraper + HITS (Kleinberg)
# Ejecutar en RStudio desde la RAÍZ del repo:  source("r/crawler_hits.R")
# Salida: backend/data/nodos_hits.json y aristas_grafo.json
# =============================================================================
# install.packages(c("httr","rvest","xml2","dplyr","igraph","jsonlite"))
suppressPackageStartupMessages({
  library(httr); library(rvest); library(xml2)
  library(dplyr); library(igraph); library(jsonlite)
})

# ----------------------------- CONFIGURACIÓN ---------------------------------
seed_url   <- "https://www.seprec.gob.bo/"   # <- CAMBIA por la sección de trámites a auditar
max_pages  <- 80                              # páginas a descargar y parsear (BFS acotado)
max_audit  <- 120                             # URLs descubiertas pero no parseadas: solo HEAD
delay_secs <- 1                               # pausa entre peticiones (cortesía)
timeout_s  <- 15
ssl_verify <- TRUE                            # FALSE si el portal tiene certificado mal configurado
out_dir    <- file.path("backend", "data")
ua_string  <- "TramiteClaroBot/1.0 (proyecto academico; auditoria de enlaces)"

# ----------------------------- UTILIDADES ------------------------------------
`%||%` <- function(a, b) if (is.null(a)) b else a
normalize_url <- function(u) { u <- sub("#.*$", "", u); sub("/+$", "", u) }
host_of <- function(u) sub("^www\\.", "", tolower(xml2::url_parse(u)$server))
is_doc  <- function(u) grepl("\\.(pdf|docx?|xlsx?|pptx?|zip|rar|odt)(\\?.*)?$", tolower(u))
squish  <- function(x) trimws(gsub("\\s+", " ", x))
seed_url  <- "https://www.seprec.gob.bo/index.php/lista-servicios-page"
seed_host <- host_of(seed_url)
http_cfg  <- config(ssl_verifypeer = ssl_verify, ssl_verifyhost = if (ssl_verify) 2L else 0L)

# Devuelve list(status, html). status = 0 si hubo error de red/timeout.
fetch_url <- function(u, method = "GET") {
  Sys.sleep(delay_secs)
  resp <- tryCatch({
    if (method == "GET") GET(u, user_agent(ua_string), timeout(timeout_s), http_cfg)
    else HEAD(u, user_agent(ua_string), timeout(timeout_s), http_cfg)
  }, error = function(e) NULL)
  if (is.null(resp)) return(list(status = 0L, html = NULL))
  st <- status_code(resp); html <- NULL
  ct <- tolower(headers(resp)[["content-type"]] %||% "")
  if (method == "GET" && st < 400 && grepl("html", ct)) {
    html <- tryCatch(read_html(content(resp, "text", encoding = "UTF-8")), error = function(e) NULL)
  }
  list(status = st, html = html)
}

# Limpieza de ruido estructural + texto principal + enlaces contextuales
extract_page <- function(doc, base_url) {
  titulo <- tryCatch(html_text2(html_element(doc, "title")), error = function(e) "")
  if (is.na(titulo)) titulo <- ""
  ruido <- html_elements(doc, xpath =
    "//nav|//header|//footer|//aside|//script|//style|//noscript|//*[@role='navigation']")
  invisible(lapply(ruido, function(n) try(xml_remove(n), silent = TRUE)))
  main <- html_element(doc, xpath = "//main|//article|//*[@id='content']|//*[@id='main']")
  if (inherits(main, "xml_missing")) main <- html_element(doc, "body")
  texto <- tryCatch(squish(html_text2(main)), error = function(e) "")
  hrefs <- tryCatch(html_attr(html_elements(main, "a[href]"), "href"), error = function(e) character())
  hrefs <- hrefs[!is.na(hrefs) & !grepl("^(mailto:|tel:|javascript:|#)", hrefs)]
  abs   <- unique(normalize_url(url_absolute(hrefs, base_url)))
  abs   <- abs[grepl("^https?://", abs)]
  list(titulo = trimws(titulo), texto = texto, links = abs)
}

# ----------------------------- 1) CRAWLER BFS --------------------------------
cat("== Crawling desde:", seed_url, "\n")
queue <- seed_url; visited <- character()
pages <- list(); edges <- list()

while (length(queue) > 0 && length(visited) < max_pages) {
  u <- queue[1]; queue <- queue[-1]
  if (u %in% visited) next
  visited <- c(visited, u)
  cat(sprintf("[%d/%d] %s\n", length(visited), max_pages, u))

  if (is_doc(u)) {                       # PDFs/DOCs: solo auditar estado
    r <- fetch_url(u, "HEAD")
    pages[[u]] <- list(url = u, titulo = basename(u), texto = "", status = r$status)
    next
  }
  r <- fetch_url(u, "GET")
  if (is.null(r$html)) {
    pages[[u]] <- list(url = u, titulo = "", texto = "", status = r$status); next
  }
  pg <- extract_page(r$html, u)
  pages[[u]] <- list(url = u, titulo = pg$titulo, texto = pg$texto, status = r$status)

  internos <- pg$links[vapply(pg$links, function(l) host_of(l) == seed_host, logical(1))]
  internos <- setdiff(internos, u)       # sin autoenlaces
  if (length(internos)) {
    edges[[length(edges) + 1]] <- data.frame(source = u, target = internos, stringsAsFactors = FALSE)
    queue <- c(queue, setdiff(internos, c(visited, queue)))
  }
}
if (length(edges) == 0)
  stop("No se encontraron enlaces internos. Revisa seed_url o si el portal es 100% JavaScript (ver v2.0).")
edges_df <- distinct(bind_rows(edges))

# --------------------- 2) AUDITORÍA HTTP DE LO DESCUBIERTO -------------------
todas <- unique(c(edges_df$source, edges_df$target))
pendientes <- setdiff(todas, names(pages))
cat("== Auditando (HEAD)", min(length(pendientes), max_audit), "de", length(pendientes), "URLs no visitadas\n")
for (u in head(pendientes, max_audit)) {
  r <- fetch_url(u, "HEAD")
  if (r$status %in% c(403, 405, 501)) r <- fetch_url(u, "GET")   # algunos servidores rechazan HEAD
  pages[[u]] <- list(url = u, titulo = basename(u), texto = "", status = r$status)
}
for (u in setdiff(pendientes, names(pages)))
  pages[[u]] <- list(url = u, titulo = basename(u), texto = "", status = NA_integer_)

nodos <- bind_rows(lapply(pages, function(p)
  data.frame(url = p$url, titulo = p$titulo, resumen_texto = substr(p$texto, 1, 3000),
             status_http = as.integer(p$status), stringsAsFactors = FALSE)))
nodos <- nodos[nodos$url %in% todas, ]
vacio <- nodos$titulo == ""
nodos$titulo[vacio] <- basename(nodos$url[vacio])

# ----------------------------- 3) HITS FORMAL --------------------------------
g <- graph_from_data_frame(edges_df, directed = TRUE, vertices = nodos[, "url", drop = FALSE])
hub  <- hub_score(g, scale = TRUE)$vector          # normalizado: máximo = 1
auth <- authority_score(g, scale = TRUE)$vector
idx  <- match(nodos$url, V(g)$name)
nodos$hub_score     <- round(hub[idx], 6)
nodos$auth_score    <- round(auth[idx], 6)
nodos$grado_entrada <- as.integer(degree(g, mode = "in")[idx])
nodos$grado_salida  <- as.integer(degree(g, mode = "out")[idx])
d <- distances(g, v = seed_url, to = V(g), mode = "out")[1, ]
nodos$profundidad <- ifelse(is.finite(d[idx]), as.integer(d[idx]), NA_integer_)  # clics desde la semilla

# ----------------------------- 4) MÉTRICAS RESUMEN ---------------------------
rotos <- nodos %>% filter(!is.na(status_http), status_http >= 400 | status_http == 0)
cat("\n=== RESUMEN ===\n")
cat(sprintf("Nodos: %d | Aristas: %d | Enlaces rotos: %d (%.1f%%)\n",
            nrow(nodos), ecount(g), nrow(rotos), 100 * nrow(rotos) / nrow(nodos)))
cat("\nTop 5 Authorities (fuentes oficiales):\n")
print(nodos %>% arrange(desc(auth_score)) %>% select(url, auth_score, status_http) %>% head(5))
cat("\nTop 5 Hubs (guías de trámites):\n")
print(nodos %>% arrange(desc(hub_score)) %>% select(url, hub_score, status_http) %>% head(5))

# ----------------------------- 5) EXPORTACIÓN --------------------------------
dir.create(out_dir, recursive = TRUE, showWarnings = FALSE)
write_json(nodos, file.path(out_dir, "nodos_hits.json"), na = "null", auto_unbox = TRUE, digits = 6)
write_json(edges_df, file.path(out_dir, "aristas_grafo.json"), auto_unbox = TRUE)
cat("\nListo. Archivos en:", normalizePath(out_dir), "\n  -> git add backend/data && git commit && git push\n")

