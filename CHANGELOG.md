# Changelog

## 2026-06-01

### Added
- **Detección PII por AymurAI (NER judicial opt-in)**: nueva capa opcional entre regex e IA. Se activa desde panel admin (`use_aymurai=true`), sobrescribe env var en runtime.
  - `call_aymurai_for_segments()`: envía cada segmento al sidecar `POST /anonymizer/predict`.
  - `map_aymurai_label_to_type()`: mapea 28 labels AymurAI a tipos internos (23 mapeados, fallback `"other"`).
  - `extract_aymurai_label_payload()`: prioriza campos `alt_text/alt_start_char/alt_end_char` sobre originales.
  - `resolve_aymurai_range()`: alinea spans predichos al texto real del segmento vía `find_normalized_ranges()`.
  - Pipeline: `regex → AymurAI → IA → merge`.
- **Nuevas variables de entorno**: `USE_AYMURAI`, `AYMURAI_BASE_URL`, `AYMURAI_TIMEOUT_SECONDS`, `AYMURAI_MIN_SEGMENT_CHARS` en `.env` y `.env.example`.
- **Sidecar AymurAI**: servicio `aymurai` con profile `"aymurai"` en `docker-compose.yml` y `docker-compose.ha.yml`. Imagen `ghcr.io/aymurai/api:full`.
  - `docker compose --profile aymurai up -d` para levantarlo.
- **Tests de integración AymurAI**: `testing/test_aymurai_integration.py` (5 tests: mapeo de labels, fallback desconocido, prioridad alt, disabled retorna vacío, HTTP mockeado retorna posiciones).
- **Análisis completo**: `AYMURAI-ANALISIS.md` con mapeo de labels, diseño de integración, sidecar y estrategias.
- **Checkbox "Habilitar detección con OpenCode"** en panel admin: permite desactivar IA sin borrar config del modelo. Se salta `call_opencode_for_pii()` si `use_opencode=false`.
- **Checkbox "Habilitar AymurAI"** en panel admin: activa/desactiva AymurAI en runtime (sin depender de env var).
- **Campo `aymurai_url`** configurable desde panel admin: sobrescribe `AYMURAI_BASE_URL` en runtime.
- **Endpoint `/admin/aymurai-status`**: retorna estado del sidecar (`{enabled, use_aymurai, url, available, error}`).
- **Tab AymurAI** en panel admin: enable/disable, URL, guardar y probar conexión.
- **Tab "Elegir Modelo" renombrado a "OpenCode"** con checkbox de habilitación.
- **`Dockerfile.aymurai` + `aymurai-patch.py`**: parche de serialización JSON para `int64` de numpy en AymurAI.
- **Documentación actualizada**: `WORKFLOW.md`, `AGENTS.md`, `README.md`, `CHANGELOG.md`.

### Fixed
- Degradación segura: si AymurAI falla o `use_aymurai=false`, el flujo regex + IA queda intacto.
- **Serialización JSON AymurAI**: fix de `TypeError: Object of type int64 is not JSON serializable` vía `Dockerfile.aymurai` + `aymurai-patch.py`.

### Changed
- `run_detection_pipeline()` ahora ejecuta `call_aymurai_for_segments()` entre regex e IA.
- Respuesta `/upload` y `/reanalyze-ai` ahora incluyen `aymurai_positions` en el pipeline result.
- **Optimización IA**: cuando AymurAI cubre ≥30% de un segmento, ese segmento se excluye del texto enviado a opencode/API Directa, reduciendo tokens y latencia. Implementado via `_get_uncovered_segments()` con threshold configurable.

## 2026-05-31

### Added
- **Nuevo modo "API Directa"**: llamada HTTP directa a endpoints OpenAI-compatibles como alternativa a opencode (opcional, toggle en panel admin).
- **Soporte OCR para PDFs escaneados**: fallback automático si `pdfplumber` extrae <100 chars. Usa `pdf2image` + `pytesseract` (Tesseract 5 + modelo `spa`).
- **Nuevas variables de entorno**: `MAX_UPLOAD_MB=100`, `OCR_MAX_PAGES=50`, `OCR_DPI=200`, `OCR_LANG=spa`.
- **Campo `used_ocr` en respuesta `/upload` y `/reanalyze-ai`**: permite al frontend mostrar *"Documento escaneado detectado. Procesamiento OCR aplicado."*
- **Test unitario `test_anonymize_pdf_scanned_pdf_ocr_fallback`**: valida que el fallback OCR se dispare y exporte correctamente con `scansmpl.pdf`.
- **Job `unit-tests` en GitHub Actions**: corre `pytest testing/ -v` automáticamente en cada push/PR. Incluye `.env` temporal para CI.
- **Archivo `ACTIONS.md`**: documentación completa de workflows de CI/CD.
- **Panel admin (Elegir Modelo)**: nuevo campo `opencode_command` para definir la línea completa de comando de opencode con placeholders `{message}`, `{model}`, `{file}`.
- **Panel admin (UX)**: botón `Restaurar comando por defecto` con confirmación antes de sobrescribir un comando personalizado.
- **Panel admin (Elegir Modelo)**: nuevo campo `api_key` configurable por modelo/proveedor en `/admin/config` y `regex_patterns.json`.
- **Tests de endpoint admin config**: cobertura de `api_key` en `testing/test_security.py` (presencia en GET, roundtrip POST/GET, validación de tipo).
- **Guía `OLLAMA.md`**: documentación paso a paso para configurar Ollama remoto privado (endpoint, modelo, API key y comando opencode).
- **Modo API directa OpenAI (sin opencode)**:
  - Nuevo campo `use_direct_api` en `regex_patterns.json` y `/admin/config`.
  - Nueva función `call_direct_api_for_pii()`: llama a `{model_url}/chat/completions` con el mismo prompt y formato de respuesta que opencode.
  - Endpoint `POST /admin/test-api`: prueba de conectividad con el endpoint configurado.
  - Endpoint `GET /admin/api-logs`: registros de llamadas API directas (últimos 50).
  - Log en memoria de llamadas API con timestamp, status y duración.
  - Solapa `API Directa` con campos propios de `Elegir Modelo` y botón `Guardar configuración`.
  - Botón `Probar inferencia` en `Elegir Modelo` con popup de resultado.
  - Limpieza de salida de opencode para mostrar sólo el contenido útil en el popup de inferencia.
  - Arranque sin `.env`: `entrypoint.sh` crea el archivo desde `.env.example` si falta y lo carga al iniciar.

### Fixed
- **Bug en `/export` PDF**: `extract_text()` devuelve tupla `(segments, used_ocr)`. Se corrigió desempaquetado en `anonymize_pdf()` para evitar `TypeError`.
- **Exportación DOCX → PDF**: se corrigió un fallo real con ciertos `.docx` complejos (`FPDFException: Not enough horizontal space to render a single character`).
- **Regresión de formato en export DOCX/PDF**: se mejoró la preservación de `runs` en DOCX y el render de headings/tablas al generar PDF desde DOCX.
- **Exportaciones múltiples sobre el mismo upload**: `/export` ya no borra el archivo original después del primer download, evitando fallos al exportar primero PDF y luego DOCX (o viceversa).
- **Razonamiento IA en el flujo de upload**: verificado que el backend sigue retornando `reasoning` en `/upload`; el contenido no se elimina durante el análisis ni la reexportación.
- **GitHub Actions (`unit-tests.yml` y `smoke-tests.yml`)**: creación explícita de `.env` temporal en cada job para evitar fallo `env file .../.env not found`.
- **UX panel admin**: si `/admin/config` responde `401`, ahora la UI vuelve al login y muestra mensaje claro sobre `SESSION_COOKIE_SECURE=0` en HTTP local.
- **Panel admin “Prompt/Patrones vacíos” tras pruebas**: se evitó contaminación de Redis productivo usando keys de config aisladas en tests/smoke (`REDIS_CONFIG_KEY` efímero).

### Changed
- **Límite de subida**: `MAX_CONTENT_LENGTH` ahora configurable vía `MAX_UPLOAD_MB` (default 100MB).
- **Dependencias Docker**: `tesseract-ocr`, `tesseract-ocr-spa`, `poppler-utils` instalados en `Dockerfile`.
- **Dependencias Python**: `pdf2image`, `pytesseract` agregados a `requirements.txt`.
- **`SESSION_COOKIE_SECURE`**: defaults/documentación alineados para desarrollo local (`0`) y producción HTTPS (`1`) en `.env.example`, `README.md`, `AGENTS.md`, `OPERACION-HA.md`.
- **Documentación actualizada**: `README.md`, `AGENTS.md`, `testing/README.md`, `ACTIONS.md`, `CHANGELOG.md`.
- **Persistencia de config admin**: `regex_patterns.json` y `/admin/config` ahora incluyen `opencode_command`.
- **Ejecución de OpenCode**: `call_opencode_for_pii()` ahora usa `api_key` configurada en admin (fallback a `OPENAI_API_KEY`).
- **UI API key en admin**: el campo de API key se muestra en texto plano en “Elegir Modelo” (según requerimiento operativo).
- **Scripts smoke**: `testing/smoke_single.sh` y `testing/smoke_ha.sh` exportan `REDIS_CONFIG_KEY` aislada para no pisar config compartida.
- **Documentación actualizada**: `README.md` (nota de soporte Ollama) y `OPERACION-HA.md` (sección Ollama remoto en HA).
- **Panel admin**: nuevo 4to tab "API Directa" con toggle, botón de prueba de conexión y visor de logs.

### Incident
- **Config admin “vacía” en UI**: se detectó que Redis mantenía una config de prueba (`prompt: "test"`, patrón `\\d+`) en la key `anonimizador:config`.
- **Resolución aplicada**: se limpió la key en Redis y se reinició `web`; el backend rebootstrapió la configuración por defecto desde `regex_patterns.json`.
- **Lección operativa**: en entornos de prueba, evitar persistir configs de test en Redis compartido o resetear `anonimizador:config` al finalizar tests manuales.

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
