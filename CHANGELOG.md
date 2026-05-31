# Changelog

## 2026-05-31

### Added
- **Soporte OCR para PDFs escaneados**: fallback automático si `pdfplumber` extrae <100 chars. Usa `pdf2image` + `pytesseract` (Tesseract 5 + modelo `spa`).
- **Nuevas variables de entorno**: `MAX_UPLOAD_MB=100`, `OCR_MAX_PAGES=50`, `OCR_DPI=200`, `OCR_LANG=spa`.
- **Campo `used_ocr` en respuesta `/upload` y `/reanalyze-ai`**: permite al frontend mostrar *"Documento escaneado detectado. Procesamiento OCR aplicado."*
- **Test unitario `test_anonymize_pdf_scanned_pdf_ocr_fallback`**: valida que el fallback OCR se dispare y exporte correctamente con `scansmpl.pdf`.
- **Job `unit-tests` en GitHub Actions**: corre `pytest testing/ -v` automáticamente en cada push/PR. Incluye `.env` temporal para CI.
- **Archivo `ACTIONS.md`**: documentación completa de workflows de CI/CD.

### Fixed
- **Bug en `/export` PDF**: `extract_text()` devuelve tupla `(segments, used_ocr)`. Se corrigió desempaquetado en `anonymize_pdf()` para evitar `TypeError`.
- **GitHub Actions `unit-tests`**: agregado paso `cp .env.example .env` antes de ejecutar `docker compose run` para evitar fallo por archivo faltante.

### Changed
- **Límite de subida**: `MAX_CONTENT_LENGTH` ahora configurable vía `MAX_UPLOAD_MB` (default 100MB).
- **Dependencias Docker**: `tesseract-ocr`, `tesseract-ocr-spa`, `poppler-utils` instalados en `Dockerfile`.
- **Dependencias Python**: `pdf2image`, `pytesseract` agregados a `requirements.txt`.
- **Documentación actualizada**: `README.md`, `AGENTS.md`, `testing/README.md`, `ACTIONS.md`.

---

## 2026-05-30

### Added
- **Suite de tests pytest** (214 tests en 3 categorías):
  - 130 tests unitarios (regex, parser IA, Unicode, reemplazo, filenames, config admin, export DOCX/PDF)
  - 34 tests de seguridad (upload, path traversal, rate limit, cookies, auth, validación config)
  - 46 tests de calidad de anonimización (DNI, CUIL, nombres, domicilios, expedientes, víctimas, imputados, menores, delitos sexuales, violencia, fallecimientos, organismos judiciales, end-to-end)
  - Detalle completo en `TESTING.md`
- **GitHub Actions `unit-tests.yml`**: 3 jobs paralelos (unitarios, seguridad, calidad) en ~10s. Detalle en `ACTIONS.md`
- **Thread de limpieza periódica** de uploads con PII (cada 60s)
- **Borrado de archivos originales** post-export (DOCX y PDF)
- **Validación de config admin** antes de guardar: regex compilable, longitud máx, schema de patterns, URL de modelo con esquema http/https

### Changed
- **Redis ya no expuesto al host**: `ports` → `expose` en `docker-compose.yml` y `docker-compose.ha.yml` (solo red interna de Docker)
- **TTL de uploads**: default de 24h → 15 min (`UPLOAD_TTL_SECONDS=900`)
- **Endpoint `/uploads/<filename>`** ahora requiere autenticación admin (`@admin_required`)
- **`DEFAULT_PATTERNS_DATA`** en `app.py` ahora incluye los 29 patrones de `regex_patterns.json` (palabras sensibles)
- **`replace_normalized`**: fix de loop infinito con keyword vacío (retorna texto sin modificar)
- **`.env.example`**: `UPLOAD_TTL_SECONDS` default a 900, eliminada variable `REDIS_PORT`
- **`Dockerfile`**: agrega `pytest` y `pytest-cov` para tests en CI
- **Documentación actualizada**:
  - `README.md` — sección testing simplificada, arquitectura actualizada
  - `AGENTS.md` — documentación completa de tests (qué testea y qué NO)
  - `TESTING.md` — nuevo archivo con detalle de 214 tests
  - `ACTIONS.md` — nuevo archivo con documentación de GitHub Actions
  - `CHANGELOG.md` — este archivo

### Verified
- 214 tests pasando (0 failures)
- Modo single-instance funcional (`docker-compose.yml`)
- Modo HA funcional (`docker-compose.ha.yml`)

### Notes
- Redis solo accesible desde la red interna de Docker. Si se necesita acceso desde host para debugging, usar un compose separado con `ports`.
- Los tests de calidad reflejan el comportamiento actual: palabras como "víctima", "menor", "cadáver" (con acento) no tienen patrones regex dedicados.
- El endpoint `/uploads/<filename>` ahora solo es accesible con sesión admin activa.

---

## 2026-05-30 (anterior)

### Added
- HAProxy integrado en `docker-compose.ha.yml` para levantar stack HA completo en un solo comando.
- Nueva config `haproxy.ha.cfg` para backend Docker (`web1..web5`) con healthcheck sobre `/ready`.
- Endpoint de app balanceada en `http://localhost:8081` y stats en `http://localhost:8404/stats`.
- Endpoint `POST /reanalyze-ai` para reintento de IA sobre archivo ya subido.
- Pagina 503 custom `haproxy-503.http` con auto-reintento cada 10 segundos.

### Changed
- Balanceo publico ajustado a `leastconn` + afinidad por IP (`stick-table` + `stick on src`) para mantener el flujo `/upload` -> `/export` en la misma instancia.
- Se mantiene sticky por cookie para rutas admin (`/admin/*`).
- Flujo IA local: healthcheck HTTP del proveedor + semaforo Redis de concurrencia + estados `ai_status`/`analysis_mode` + `queue_notice`.
- Frontend: popup `Proveedor ocupado` con reintento cada 5s, `Continuar sin IA` y `Reintentar con IA`.
- Documentacion actualizada para reflejar arquitectura y operacion HA actual:
  - `README.md`
  - `HAPROXY.md`
  - `OPERACION-HA.md`
  - `AGENTS.md`
  - `ACCESO-CONCURRENTE-PLAN.md`

### Verified
- Modo single-instance funcional (`docker-compose.yml`):
  - `GET /ready` en `http://localhost:5000/ready` responde `200`.
  - Flujo `upload -> export` (DOCX) responde `200`.
- Modo HA funcional (`docker-compose.ha.yml`):
  - `GET /ready` por HAProxy en `http://localhost:8081/ready` responde `200`.
  - Flujo `upload -> export` por HAProxy responde `200`.
  - Stats HAProxy accesibles en `http://localhost:8404/stats`.

### Notes
- En este entorno `:8080` estaba ocupado; por eso HAProxy se expone en `:8081`.
- Si se requiere `http://localhost:80`, cambiar el mapeo de puertos de `haproxy` en `docker-compose.ha.yml` a `80:80`.
