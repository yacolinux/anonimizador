# Testing

Suite de tests para el Anonimizador de Documentos. 210 tests en 3 categorías: unitarios, seguridad y calidad de anonimización.

## Estructura

```
testing/
├── conftest.py                    # Fixtures compartidos, helpers, reset de config
├── requirements-test.txt          # Dependencias de test (pytest, pytest-cov)
├── test_regex_detection.py        # Tests unitarios: detección PII por regex
├── test_parse_llm_response.py     # Tests unitarios: parser de output de IA
├── test_unicode_normalization.py  # Tests unitarios: normalización Unicode
├── test_replace_normalized.py     # Tests unitarios: función de reemplazo
├── test_filename_validation.py    # Tests unitarios: validación de filenames
├── test_admin_config_validation.py# Tests unitarios: config del panel admin
├── test_export_docx.py            # Tests unitarios: export/anonimización DOCX
├── test_export_pdf.py             # Tests unitarios: export/anonimización PDF
├── test_security.py               # Tests de seguridad (upload, export, admin, rate limit)
├── test_anonymization_quality.py  # Tests de calidad con documentos sintéticos
├── smoke_single.sh                # Smoke test: stack single (1 instancia)
├── smoke_ha.sh                    # Smoke test: stack HA (HAProxy + 5 instancias)
├── run_all.sh                     # Ejecuta smoke_single + smoke_ha
├── lib.sh                         # Helpers compartidos (logs, asserts HTTP)
└── logs/                          # Logs de ejecución (gitignored)
```

## Ejecución

### Todos los tests

```bash
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v
```

### Por categoría

```bash
# Solo unitarios
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v \
  --ignore=testing/test_security.py \
  --ignore=testing/test_anonymization_quality.py \
  --ignore=testing/smoke_single.sh \
  --ignore=testing/smoke_ha.sh \
  --ignore=testing/run_all.sh

# Solo seguridad
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_security.py -v

# Solo calidad
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_anonymization_quality.py -v

# Un archivo específico
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_regex_detection.py -v

# Un test específico
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_regex_detection.py::test_detect_default_pii_dni -v

# Con cobertura
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v --cov=app --cov-report=term-missing
```

### Smoke tests (E2E con Docker)

```bash
# Stack single
./testing/smoke_single.sh

# Stack HA
./testing/smoke_ha.sh

# Ambos
./testing/run_all.sh
```

## Resumen de tests

### Unitarios (130 tests)

| Archivo | Tests | Qué cubre |
|---|---|---|
| `test_regex_detection.py` | 20 | DNI (con/sin puntos), dirección, edad, sexo, nombre, email, palabras sensibles (abus, viol, homicid, forens, expediente, denuncia, etc.), posiciones correctas, sin falsos positivos |
| `test_parse_llm_response.py` | 24 | JSON fenced (con/sin lang), inline array, pair notation, tablas markdown, malformed JSON, ANSI escape codes, fallback a bracket extraction, empty/none/whitespace |
| `test_unicode_normalization.py` | 18 | NFKD decomposition, combining marks, acentos (Pérez→Perez), find_word_positions accent-insensitive, múltiples matches, no match |
| `test_replace_normalized.py` | 20 | Reemplazo simple, con acentos, variantes sin acento, múltiples ocurrencias, números, dirección, replacement custom, loop infinito prevention, case insensitive |
| `test_filename_validation.py` | 17 | UUID válido (docx/pdf), extensión inválida (exe/txt/zip), path traversal, doble extensión, symlink, `is_path_inside_uploads` |
| `test_admin_config_validation.py` | 14 | Save/load config, fallback a default cuando archivo falta, model_url/model_name, empty patterns, `is_local_model_provider` |
| `test_export_docx.py` | 8 | Reemplazo keywords, preserva non-PII, empty keywords, múltiples párrafos, celdas de tabla, replacement string custom, keyword con acento, output BytesIO |
| `test_export_pdf.py` | 10 | Reemplazo keywords, preserva non-PII, empty keywords, title segment, list segment, múltiples segmentos, replacement custom, title custom, acentos, output BytesIO |

### Seguridad (34 tests)

| Clase | Tests | Qué cubre |
|---|---|---|
| `TestFileUploadSecurity` | 8 | exe/txt/zip rechazados, no filename, no file key, path traversal, null byte, doble extensión |
| `TestPathTraversal` | 5 | `is_path_inside_uploads` con rutas fuera, dotdot, symlink, ruta válida |
| `TestExportSecurity` | 7 | No filename, filename inválido, file inexistente, body vacío, formato inválido, PDF→DOCX rechazado |
| `TestAdminRateLimit` | 4 | Bloqueo después de 5 intentos, login exitoso, logout limpia sesión, endpoints sin auth |
| `TestCookieAndHeaders` | 2 | HttpOnly en cookie de sesión, SameSite=Lax |
| `TestUploadsEndpoint` | 2 | UUID inválido, filename inexistente |
| `TestAdminConfigValidation` | 3 | Regex inválido se guarda, empty patterns, requiere auth |
| `TestReanalyzeSecurity` | 2 | Filename inválido, file inexistente |
| `TestReadyEndpoint` | 1 | Retorna JSON con ready/busy/inflight |

### Calidad de anonimización (46 tests)

| Categoría | Tests | Documentos sintéticos |
|---|---|---|
| **DNI** | 3 | `30.123.456` (con puntos), `30123456` (sin puntos), anonimización en DOCX |
| **CUIL/CUIT** | 2 | `20-30123456-7`, anonimización en DOCX |
| **Nombres y apellidos** | 5 | `Juan Carlos Martínez`, `José Martínez` (con acento), `Gomez` (sin acento), anonimización |
| **Domicilios** | 5 | `Calle San Martín 1234`, `Av. Corrientes 2567`, `Domicilio: Calle Pellegrini 888`, `Pasaje San Lorenzo 456`, `Ruta Nacional 8 km 45` |
| **Expedientes** | 2 | `Expediente N° 12345/2024` |
| **Víctimas** | 2 | `La víctima sufrió lesiones graves`, `La víctima realizó la denuncia` |
| **Imputados** | 2 | `El imputado fue detenido`, `El imputado, Roberto Gómez, fue notificado` |
| **Menores** | 2 | `menor de edad`, `abuso sexual contra una menor` |
| **Delitos sexuales** | 4 | `abuso sexual`, `agredida`, `amenazas de muerte`, `lesiones compatibles` |
| **Violencia** | 2 | `Violencia de género`, `violencia doméstica` |
| **Fallecimientos** | 6 | `fallecimiento`, `cadaver`, `homicidio agravado`, `femicidio`, `autopsia`, `necropsia` |
| **Organismos judiciales** | 8 | `Juzgado de Familia`, `pericia forense`, `identificación`, `documentación`, `expediente`, `condena`, `denuncia`, `testigo` |
| **End-to-End** | 4 | Documento completo con todos los tipos, anonimización DOCX, merge sin duplicados, sin overlap |

## Qué testean y qué NO testean

### Tests unitarios

| Archivo | ✅ Testea | ❌ NO testea |
|---|---|---|
| `test_regex_detection.py` | Cada patrón regex contra textos específicos, posiciones de match, tipos de retorno, sin falsos positivos básicos | La IA (opencode), extracción de texto real de PDF/DOCX, rendimiento con documentos grandes |
| `test_parse_llm_response.py` | Todos los formatos de respuesta posibles de la IA (JSON fenced, inline, tablas, malformed, ANSI codes) | La invocación real de opencode, la calidad del análisis de la IA, timeouts del subprocess |
| `test_unicode_normalization.py` | NFKD decomposition, combining marks, matching accent-insensitive, find_word_positions | La extracción de texto de archivos reales con encoding variado, normalización en el frontend |
| `test_replace_normalized.py` | Reemplazo con/sin acentos, múltiples ocurrencias, edge cases (empty keyword, empty text), case insensitive | El reemplazo dentro de DOCX/PDF reales (eso va en export tests), rendimiento con textos largos |
| `test_filename_validation.py` | Formato UUID, extensiones válidas/inválidas, path traversal en strings, `is_path_inside_uploads` | La subida real de archivos por HTTP, validación de MIME type, tamaño máximo de archivo |
| `test_admin_config_validation.py` | Save/load de config, fallback a default, model_url/model_name, empty patterns, `is_local_model_provider` | La persistencia real en Redis, la UI del panel admin, la aplicación inmediata de cambios |
| `test_export_docx.py` | Reemplazo de keywords en DOCX, preservación de non-PII, tablas, celdas, acentos, custom replacement | El formato visual del DOCX resultante (colores, bold), compatibilidad con versiones de Word |
| `test_export_pdf.py` | Reemplazo de keywords en PDF, preservación de non-PII, segmentos title/list, acentos, custom title | La calidad visual del PDF generado, compatibilidad con lectores de PDF, fonts embebidos |

### Tests de seguridad

| Clase | ✅ Testea | ❌ NO testea |
|---|---|---|
| `TestFileUploadSecurity` | Rechazo de extensiones no permitidas, path traversal en filename, null bytes, doble extensión | Inyección de código en el contenido del archivo, malware scanning, rate limit de upload |
| `TestPathTraversal` | `is_path_inside_uploads` con rutas absolutas fuera, dotdot, symlinks en path | Symlinks reales en el filesystem, bypass de realpath, race conditions TOCTOU |
| `TestExportSecurity` | Filename inválido, file inexistente, body vacío, formato inválido, PDF→DOCX rechazado | Path traversal en export real (el filename se valida con UUID), inyección en keywords |
| `TestAdminRateLimit` | Bloqueo después de 5 intentos fallidos, login exitoso, logout limpia sesión, endpoints sin auth | Rate limit distribuido en HA (múltiples instancias), brute force con IPs rotativas, timing attacks |
| `TestCookieAndHeaders` | HttpOnly y SameSite=Lax en cookies de sesión | Secure flag (requiere HTTPS real), CSRF tokens, XSS en cookies |
| `TestUploadsEndpoint` | Acceso a archivos inexistentes retorna 404 | Listado de directorio de uploads, acceso directo a archivos de otros usuarios |
| `TestAdminConfigValidation` | Regex inválido se guarda sin crash, empty patterns, requiere auth para save | Validación de regex compilable, XSS en prompt guardado, inyección en patterns |
| `TestReanalyzeSecurity` | Filename inválido y file inexistente retornan error | Race condition entre upload y reanalyze, DoS por reanalyze masivo |
| `TestReadyEndpoint` | Retorna JSON con ready/busy/inflight | El comportamiento bajo carga real, el threshold de READY_MAX_INFLIGHT |

### Tests de calidad de anonimización

| Categoría | ✅ Testea | ❌ NO testea |
|---|---|---|
| **DNI** | Detección con puntos (`30.123.456`) y sin puntos (`30123456`), anonimización en DOCX | DNI en imágenes escaneadas, DNI en tablas complejas de PDF, pasaportes |
| **CUIL/CUIT** | Detección del formato `20-30123456-7`, anonimización | CUIL/CUIT sin guiones, CUIL/CUIT en contextos no estándar |
| **Nombres y apellidos** | Nombres con prefijo `Paciente:`, nombres con acentos, anonimización | Nombres sin prefijo, nombres compuestos complejos, apellidos con partículas (de, del, la) |
| **Domicilios** | Calle, Av., Domicilio, Pasaje, Ruta + texto + número | Direcciones sin número, direcciones en formato postal completo, CP |
| **Expedientes** | Detección de palabra "expediente" como sensible | Número de expediente como PII, expedientes en tablas |
| **Víctimas** | Detección de "lesiones" y "denuncia" en contexto de víctima | La palabra "víctima" en sí (no tiene patrón regex dedicado) |
| **Imputados** | Detección de "imputado" y "detenido" | Nombres de imputados sin la palabra "imputado" |
| **Menores** | Detección de "abuso" en contexto de menor | La palabra "menor" en sí (no tiene patrón regex dedicado) |
| **Delitos sexuales** | Detección de "abuso", "agred", "amenaz", "lesion" | Delitos sexuales descritos sin estas palabras clave |
| **Violencia** | Detección de "viol" (violencia, violento) | Violencia descrita sin la raíz "viol" |
| **Fallecimientos** | Detección de "fallec", "homicid", "femicid", "autops", "necrops" | "cadáver" con acento (el patrón `cadav\w*` no matchea `cadáver`), muerte por causas naturales |
| **Organismos judiciales** | Detección de "forens", "perici", "identif", "conden", "denunci", "document", "expedient" | Nombres propios de juzgados, números de juzgado, fechas de audiencias |
| **End-to-End** | Documento completo con múltiples tipos de PII, merge sin duplicados, anonimización DOCX | Documentos reales con formatting complejo, imágenes, headers/footers |

## Fixtures compartidos (`conftest.py`)

| Fixture / Helper | Descripción |
|---|---|
| `reset_config_file()` | Resetea `regex_patterns.json` a defaults y limpia Redis config key |
| `pytest.fixture(autouse=True)` | Ejecuta `reset_config_file()` antes de cada test |
| `create_synthetic_docx()` | Genera DOCX con párrafos, headings, listas y tablas |
| `create_synthetic_pdf()` | Genera PDF con texto plano |
| `pii_doc_paragraphs()` | Retorna párrafos sintéticos con todos los tipos de PII |
| `cleanup_temp_files()` | Limpia archivos temporales creados en tests |

## Configuración de test

El `conftest.py` configura el ambiente de test:

- `FLASK_SECRET_KEY`: `test-secret-key`
- `ADMIN_USER`: `admin` / `ADMIN_PASS`: `testpass`
- `REDIS_URL`: `redis://redis:6379/15` (DB aislada para tests)
- `REDIS_CONFIG_KEY`: `anonimizador:config:test`
- `SESSION_BACKEND`: `cookie` (no Redis para sesiones)
- `OPENAI_BASE_URL`: `https://api.test.com/v1` (no se usa en tests unitarios)

## CI / GitHub Actions

### Workflow 1: `unit-tests.yml` (Unitarios + Seguridad + Calidad)

Se ejecuta en **~10 segundos** con 3 jobs paralelos:

| Job | Qué corre | Tiempo |
|---|---|---|
| `unit-tests` | 8 archivos de tests unitarios (~130 tests) | ~5s |
| `security-tests` | `test_security.py` (34 tests) | ~3s |
| `quality-tests` | `test_anonymization_quality.py` (46 tests) | ~3s |

Cada job levanta un Redis efímero y corre los tests dentro del container Docker.

### Workflow 2: `smoke-tests.yml` (E2E con Docker Compose)

Se ejecuta en **~5-10 minutos** con 2 jobs:

| Job | Qué corre | Timeout |
|---|---|---|
| `smoke-single` | `smoke_single.sh` (1 instancia) | 35 min |
| `smoke-ha` | `smoke_ha.sh` (HAProxy + 5 instancias) | 45 min |

### Flujo recomendado

1. **PR review**: los unit tests dan feedback inmediato (< 1 min)
2. **Merge**: los smoke tests validan el stack completo
3. Si los unit tests fallan, no tiene sentido ejecutar smoke tests
