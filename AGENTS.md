# Anonimizador de Documentos

App web Flask para detectar y anonimizar datos personales en PDF/DOCX. Corre en Docker Compose con OpenCode como backend IA.

## Setup

```bash
docker compose up --build  # http://localhost:5000
# Si falta .env, se crea automáticamente desde .env.example al arrancar.
```

Sin Docker:
```bash
pip install -r requirements.txt
npm install -g opencode-ai@latest
./entrypoint.sh
```

## Variables de entorno (.env)

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | API key del proveedor LLM | `sk-or-v1-...` |
| `OPENAI_BASE_URL` | URL base del proveedor | `https://openrouter.ai/api/v1` |
| `MODEL_NAME` | Modelo a usar (formato provider/modelo) | `opencode/deepseek-v4-flash-free` |
| `FLASK_PORT` | Puerto del servidor | `5000` |
| `ADMIN_USER` | Usuario del panel admin | `adminanon` |
| `ADMIN_PASS` | Contraseña del panel admin | `cambiar-esta-clave` |
| `FLASK_SECRET_KEY` | Secret key para sesiones Flask | `cualquier-string-seguro` |
| `SESSION_COOKIE_SECURE` | Cookie de sesión segura (`0` local HTTP, `1` prod HTTPS) | `0` |
| `READY_MAX_INFLIGHT` | Umbral de requests concurrentes para marcar busy en `/ready` | `2` |
| `SESSION_BACKEND` | Backend de sesiones (`redis` o `cookie`) | `redis` |
| `REDIS_URL` | URL de Redis compartido (single/HA) | `redis://redis:6379/0` |
| `REDIS_CONFIG_KEY` | Key Redis para config compartida | `anonimizador:config` |
| `UPLOAD_TTL_SECONDS` | Tiempo de retención de uploads con PII (segundos) | `86400` |
| `LOGIN_WINDOW_SECONDS` | Ventana de rate limit login admin (segundos) | `300` |
| `LOGIN_MAX_ATTEMPTS` | Máximo de intentos de login por ventana | `5` |
| `LOCAL_INFERENCE_MAX` | Máximo de inferencias simultáneas en proveedor local | `3` |
| `LOCAL_INFERENCE_WAIT_SECONDS` | Espera máxima para tomar slot local en `/upload` | `90` |
| `LOCAL_INFERENCE_POLL_SECONDS` | Intervalo de polling para tomar slot local | `1.5` |
| `LOCAL_INFERENCE_SLOT_TTL_SECONDS` | TTL de seguridad de slot local en Redis | `180` |
| `MAX_UPLOAD_MB` | Tamaño máximo de subida en MB | `100` |
| `OCR_MAX_PAGES` | Máximo de páginas a procesar con OCR | `50` |
| `OCR_DPI` | Resolución para conversión de PDF a imagen | `200` |
| `OCR_LANG` | Idioma de Tesseract OCR | `spa` |
| `USE_AYMURAI` | Activar NER judicial AymurAI (`1`) o no (`0`). Se sobrescribe desde panel admin (`use_aymurai`) | `0` |
| `AYMURAI_BASE_URL` | URL del sidecar AymurAI. Se sobrescribe desde panel admin (`aymurai_url`) | `http://aymurai:8899` |
| `AYMURAI_TIMEOUT_SECONDS` | Timeout por llamada HTTP a AymurAI | `20` |
| `AYMURAI_MIN_SEGMENT_CHARS` | Mínimo de caracteres para enviar segmento a AymurAI | `15` |

## API

### Endpoints públicos

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Frontend web |
| `/upload` | POST | Subir PDF/DOCX (multipart `file`). Retorna `{segments, keywords, default_keywords, positions, reasoning, queue_notice, ai_status, analysis_mode}` |
| `/reanalyze-ai` | POST | Reintentar IA sobre archivo ya subido. Body: `{filename}` |
| `/export` | POST | Exportar anonimizado. Body JSON: `{filename, keywords[{word,type}], format:docx\|pdf, replacement}` |
| `/ready` | GET | Health de disponibilidad para HAProxy. Retorna `200` si libre y `503` si busy |

### Endpoints admin (requieren sesión)

| Endpoint | Método | Descripción |
|---|---|---|
| `/admin/login` | POST | Login admin. Body: `{user, password}` |
| `/admin/logout` | POST | Cerrar sesión admin |
| `/admin/status` | GET | Estado de sesión. Retorna `{logged_in: bool}` |
| `/admin/config` | GET | Obtener configuración actual. Retorna `{patterns, prompt, model_url, model_name, api_key, opencode_command, use_direct_api, use_opencode, use_aymurai, aymurai_url}` |
| `/admin/config` | POST | Guardar configuración. Body: `{patterns[], prompt, model_url, model_name, api_key, opencode_command, use_direct_api, use_opencode, use_aymurai, aymurai_url}` |
| `/admin/test-api` | POST | Prueba de conectividad endpoint API |
| `/admin/test-inference` | POST | Prueba de inferencia con prompt de ejemplo |
| `/admin/api-logs` | GET | Registro de llamadas API directas |
| `/admin/config/restore-defaults` | POST | Restaurar Prompt y Patrones Regex a defaults (preserva modelo, API key y API Directa) |
| `/admin/aymurai-status` | GET | Estado del sidecar AymurAI. Retorna `{enabled, use_aymurai, url, available, error}` |

## Arquitectura

```
anonimizador/
├── app.py                  # Backend Flask (API endpoints, detección PII, export)
├── entrypoint.sh           # Genera auth.json de opencode al iniciar
├── regex_patterns.json     # Patrones regex editables + prompt + config modelo (generado dinámicamente)
├── templates/index.html    # Frontend HTML (SPA)
├── static/
│   ├── style.css           # CSS con tema oscuro/claro
│   └── app.js              # Lógica frontend: upload, PII toggle, export, admin panel
├── docker-compose.yml      # Orquestación Docker (incluye sidecar AymurAI con profile)
├── docker-compose.ha.yml   # Pool HA completo: haproxy + 5 instancias activas + redis + AymurAI
├── haproxy.cfg             # Config base de HAProxy para correr en host
├── haproxy.ha.cfg          # Config de HAProxy usada por docker-compose.ha.yml
├── haproxy-503.http        # Pagina 503 con auto-reintento cada 10s
├── HAPROXY.md              # Guía de balanceo
├── OPERACION-HA.md         # Runbook single + HA
├── TESTING.md              # Documentación completa de tests
├── testing/
│   ├── conftest.py                    # Fixtures compartidos, reset de config
│   ├── requirements-test.txt          # Dependencias de test
│   ├── test_regex_detection.py        # Unit: detección PII por regex (20 tests)
│   ├── test_parse_llm_response.py     # Unit: parser de output de IA (24 tests)
│   ├── test_unicode_normalization.py  # Unit: normalización Unicode (18 tests)
│   ├── test_replace_normalized.py     # Unit: función de reemplazo (20 tests)
│   ├── test_filename_validation.py    # Unit: validación de filenames (17 tests)
│   ├── test_admin_config_validation.py# Unit: config del panel admin (14 tests)
│   ├── test_export_docx.py            # Unit: export/anonimización DOCX (10 tests)
│   ├── test_export_pdf.py             # Unit: export/anonimización PDF (11 tests)
│   ├── test_security.py               # Seguridad: upload, export, admin, rate limit (41 tests)
│   ├── test_anonymization_quality.py  # Calidad con documentos sintéticos (46 tests)
│   ├── smoke_single.sh                # Smoke: stack single
│   ├── smoke_ha.sh                    # Smoke: stack HA
│   ├── run_all.sh                     # Ejecuta smoke_single + smoke_ha
│   ├── lib.sh                         # Helpers compartidos
│   └── logs/                          # Logs de ejecución
├── .github/workflows/
│   ├── smoke-tests.yml     # CI: smoke tests E2E (single + HA)
│   └── unit-tests.yml      # CI: unitarios + seguridad + calidad
├── Dockerfile              # python:3.11-slim + Node.js 22 + opencode-ai
├── Dockerfile.aymurai      # Parche de serialización JSON para int64 de numpy
├── aymurai-patch.py        # Monkey-patch de int64 en app AymurAI
├── requirements.txt        # Dependencias Python
└── .env                    # Configuración sensible
```

### Componentes backend (`app.py`)

- **Flask app** con gunicorn (2 workers, timeout 180s)
- **Redis opcional/compartido** para sesiones admin, rate limit y config distribuida
- **Endpoint `/ready`** para balanceo: reporta estado de ocupación por requests en vuelo (`inflight`)
- **Extracción de texto**: `pdfplumber` para PDF, `python-docx` para DOCX
- **Detección PII por regex**: `detect_default_pii()` lee patrones desde `regex_patterns.json`
- **Detección PII por AymurAI** (opt-in desde panel admin): `call_aymurai_for_segments()` llama a sidecar NER judicial vía `POST /anonymizer/predict` (timeout y URL configurables desde admin)
- **Detección PII por IA** (opcional desde panel admin): `call_opencode_for_pii()` ejecuta `opencode run` como subprocess (timeout 120s). Se desactiva con `use_opencode=false` en config
- **Proveedor local**: healthcheck HTTP + semáforo Redis global para concurrencia de inferencias
- **Normalización Unicode**: `normalize_text()` usa NFKD + elimina combining marks
- **Export DOCX**: reemplaza sobre el documento original preservando mejor `runs`, negritas, itálicas y estructura básica
- **Export PDF**: usa `fpdf2` con DejaVuSans; si el origen es DOCX, renderiza directamente desde el DOCX para conservar mejor headings, listas y tablas básicas
- **Reexport**: el archivo subido no se borra tras el primer `/export`; se mantiene hasta el TTL de cleanup para permitir exportar DOCX y PDF sobre el mismo análisis
- **Panel admin**: sesiones Flask con `admin_required` decorator

### Frontend (`index.html` + `style.css` + `app.js`)

- **SPA vanilla JS** sin frameworks
- **Tema oscuro por defecto** con toggle a claro (persistido en localStorage)
- **Panel documento**: texto con palabras PII resaltadas en amarillo (clickeables para toggle)
- **Panel lateral**: lista de PII agrupadas, checkbox "marcar todas", agregar palabras manualmente
- **Botón "Copiar Texto Anonimizado"**: copia el texto con reemplazos al portapapeles
- **Botón "Ver Razonamiento"**: modal con output completo de la IA
- **Flujo IA local ocupada**: popup "Proveedor ocupado", reintento cada 5s, botón "Continuar sin IA" y botón "Reintentar con IA"
- **Panel admin**: botón discreto ⚙ en esquina inferior izquierda, login → tabs (Prompt, Patrones Regex, OpenCode con checkbox "Habilitar detección con OpenCode" + `model_url`, `model_name`, `api_key`, `opencode_command`, botón guardar y botón probar inferencia; API Directa con `model_url`, `model_name`, `api_key`, toggle, guardar y test/logs; AymurAI con checkbox "Habilitar AymurAI", `aymurai_url`, botón guardar y botón probar conexión) + botón global restaurar config por defecto

## Detección de PII

Tres capas combinadas en `/upload`:

1. **Regex configurable** (`detect_default_pii`): lee patrones desde `regex_patterns.json`. Incluye:
   - DNI argentino (`XX.XXX.XXX`, `XXXXXXXX`)
   - Direcciones (`calle`, `av.`, `domicilio` + texto + número)
   - Edad (`XX años`)
   - Sexo (`Masculino`, `Femenino`, etc.)
   - Nombres con prefijo (`Paciente:`, `Sr.`, etc.)
   - Emails
   - Palabras sensibles (`abus*`, `viol*`, `homicid*`, `femicid*`, `forens*`, `expedient*`, etc.)

2. **AymurAI (opt-in, NER judicial)**: `call_aymurai_for_segments()` envía cada segmento al sidecar AymurAI `POST /anonymizer/predict`. Retorna spans exactos mapeados a tipos internos vía `map_aymurai_label_to_type()` (28 labels, 23 mapeados, fallback `"other"`). Se activa/desactiva desde panel admin (`use_aymurai`), no depende de env var en runtime.

3. **IA via opencode** (`call_opencode_for_pii`): ejecuta `opencode run --model opencode/{modelo} --file texto.txt --dangerously-skip-permissions`. El prompt es configurable desde el panel admin. Pide JSON array `[{word, type}]`. Se salta si `use_opencode=false` en config.

   **Optimización**: cuando AymurAI está activo y cubre suficientes caracteres de un segmento (≥30%), ese segmento se excluye del texto enviado a la IA. Esto reduce tokens, latencia y costo sin perder cobertura.

Posiciones combinadas (sin duplicados) ordenadas por segmento. Orden de pipeline: regex → AymurAI → IA → merge.

## Configuración de modelo

El modelo se configura en `.env` (`MODEL_NAME`) y puede sobrescribirse desde el panel admin (tab "OpenCode"). La configuración se guarda en `regex_patterns.json` con campos `model_url`, `model_name`, `api_key` y `opencode_command`.

- **Formato**: `provider/modelo` (ej: `opencode/deepseek-v4-flash-free`)
- **Provider `opencode`**: usa la API key configurada en `auth.json` (generado por `entrypoint.sh` desde `OPENAI_API_KEY`)
- **Modelos locales**: se puede configurar cualquier endpoint compatible OpenAI cambiando `model_url` (ej: `http://localhost:11434/v1` para Ollama)

## Particularidades

- **Normalización Unicode**: `normalize_text()` usa NFKD + elimina combining marks. Crucial para acentos (Pérez vs Perez). Afecta `find_word_positions`, `anonymize_docx`, `anonymize_pdf`.
- **Texto de reemplazo default**: `[REDACTADO]` (configurable en el frontend)
- **Export PDF → DOCX**: no permitido (python-docx no puede abrir PDFs). El frontend deshabilita la opción DOCX y muestra un mensaje explicativo.
- **Timeout subprocess**: 120s para opencode (gunicorn timeout 180s)
- **Subida máxima**: 100MB por defecto (`MAX_UPLOAD_MB`)
- **Auth opencode**: `entrypoint.sh` escribe `~/.local/share/opencode/auth.json` si `OPENAI_API_KEY` está definida
- **HA / balanceo**: endpoint `/ready` + `READY_MAX_INFLIGHT` para que HAProxy enrute sólo a instancias libres
- **Sticky admin**: mantener afinidad `/admin/*` en HAProxy

## HA (5 a 10 instancias)

- `docker-compose.ha.yml` incluye `haproxy` dentro del stack (app en `localhost:8081`, stats en `localhost:8404/stats`)
- `docker-compose.ha.yml` trae `web1..web5` activas por default (`5001..5005` para debug)
- `docker-compose.ha.yml` incluye **un solo Redis** compartido para todas las instancias
- `web6..web10` quedan comentadas para escalar a 10 sin rediseñar compose
- Config y backend de HAProxy recomendados en `HAPROXY.md`
- Operación paso a paso: `OPERACION-HA.md`

## Pruebas

```bash
# Crear DOCX de prueba dentro del container
docker exec -i anonimizador-web-1 python3 -c "
from docx import Document
d = Document()
d.add_heading('Test', level=1)
d.add_paragraph('Paciente: Juan Pérez, DNI 30.123.456')
d.save('/tmp/test.docx')"
docker cp anonimizador-web-1:/tmp/test.docx /tmp/test.docx

# Test upload
curl -s -F "file=@/tmp/test.docx" http://localhost:5000/upload | python3 -m json.tool

# Test export
curl -s -F "file=@/tmp/test.docx" http://localhost:5000/upload > /tmp/r.json
python3 -c "
import json
r = json.load(open('/tmp/r.json'))
kw = [{'word': p['word'], 'type': p['type']} for p in r['positions']]
print(json.dumps({'filename': r['filename'], 'keywords': kw, 'format': 'docx'}))
" | curl -s -X POST -H 'Content-Type: application/json' -d @- http://localhost:5000/export -o /tmp/anon.docx

# Test admin login
curl -s -c /tmp/cookies.txt -X POST -H 'Content-Type: application/json' \
  -d '{"user":"adminanon","password":"cambiar-esta-clave"}' http://localhost:5000/admin/login

# Test admin config
curl -s -b /tmp/cookies.txt http://localhost:5000/admin/config | python3 -m json.tool
```

## Testing automatizado

### Ejecución

```bash
# Todos los tests (226 tests, ~2s)
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v

# Solo unitarios (134 tests)

docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v \
  --ignore=testing/test_security.py \
  --ignore=testing/test_anonymization_quality.py

# Solo seguridad (41 tests)
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_security.py -v

# Solo calidad (46 tests)
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_anonymization_quality.py -v

# Smoke tests E2E
./testing/run_all.sh
```

### Tests unitarios (139 tests)

Funciones internas de `app.py` testeadas en aislamiento:

| Archivo | Funciones testeadas | Qué valida |
|---|---|---|
| `test_regex_detection.py` (20) | `detect_default_pii`, `get_pii_patterns` | Cada patrón regex contra textos específicos: DNI con/sin puntos, dirección (calle/av/domicilio/pasaje/ruta), edad, sexo, nombre con prefijo, email, palabras sensibles (abus/viol/homicid/femicid/forens/expedient/denuncia/etc.), posiciones correctas, sin falsos positivos |
| `test_parse_llm_response.py` (24) | `parse_pii_from_output` | Todos los formatos de respuesta de IA: JSON fenced con/sin lang, inline array, pair notation con comillas, tablas markdown, malformed JSON, ANSI escape codes, fallback a bracket extraction, empty/none/whitespace, priorización fenced sobre inline |
| `test_unicode_normalization.py` (18) | `normalize_text`, `find_word_positions` | NFKD decomposition, combining marks, acentos (Pérez→Perez), matching accent-insensitive, múltiples matches en un segmento, no match, composed vs decomposed chars |
| `test_replace_normalized.py` (20) | `replace_normalized` | Reemplazo simple, con acentos, variantes sin acento, múltiples ocurrencias, números, dirección, replacement custom, prevención de loop infinito con keyword vacío, case insensitive |
| `test_filename_validation.py` (17) | `is_valid_upload_filename`, `allowed_file`, `is_path_inside_uploads` | UUID válido (docx/pdf), extensión inválida (exe/txt/zip), path traversal en string, doble extensión, symlink, rutas absolutas fuera de uploads |
| `test_admin_config_validation.py` (14) | `save_regex_config`, `load_regex_config`, `get_pii_patterns`, `get_opencode_prompt`, `get_model_config`, `is_local_model_provider` | Save/load de config, fallback a default cuando archivo falta, model_url/model_name, empty patterns, detección de proveedor local |
| `test_aymurai_integration.py` (5) | `use_aymurai`, `call_aymurai_for_segments`, `map_aymurai_label_to_type`, `extract_aymurai_label_payload`, `resolve_aymurai_range` | Mapeo de labels AymurAI a tipos internos, fallback a 'other', prioridad de campos alt, disabled retorna vacío, HTTP mockeado retorna posiciones |
| `test_export_docx.py` (8) | `anonymize_docx` | Reemplazo de keywords, preservación de non-PII, empty keywords, múltiples párrafos, celdas de tabla, replacement string custom, keyword con acento, output BytesIO |
| `test_export_pdf.py` (11) | `anonymize_pdf`, `extract_text_pdf` | Reemplazo de keywords, preservación de non-PII, empty keywords, segmentos title/list, múltiples segmentos, replacement custom, title custom, acentos, output BytesIO, fallback OCR con PDF escaneado |

### Tests de seguridad (41 tests)

Validan que la app resista ataques comunes:

| Clase | Qué testea |
|---|---|
| `TestFileUploadSecurity` (8) | Rechazo de exe/txt/zip, no filename, no file key, path traversal en filename, null byte, doble extensión |
| `TestPathTraversal` (5) | `is_path_inside_uploads` con rutas absolutas fuera, dotdot, symlinks en path, ruta válida |
| `TestExportSecurity` (7) | No filename, filename inválido, file inexistente (404), body vacío, formato inválido (400), PDF→DOCX rechazado (400) |
| `TestAdminRateLimit` (4) | Bloqueo después de 5 intentos fallidos (429), login exitoso (200), logout limpia sesión, endpoints sin auth (401) |
| `TestCookieAndHeaders` (2) | HttpOnly y SameSite=Lax en cookies de sesión |
| `TestUploadsEndpoint` (2) | Acceso a archivos inexistentes retorna 404, path traversal en URL |
| `TestAdminConfigValidation` (3) | Regex inválido se guarda sin crash, empty patterns, requiere auth para save |
| `TestReanalyzeSecurity` (2) | Filename inválido (400), file inexistente (404) |
| `TestReadyEndpoint` (1) | Retorna JSON con ready/busy/inflight |

### Tests de calidad de anonimización (46 tests)

Documentos sintéticos con PII anotada verifican que la detección regex funcione:

| Categoría | Textos de prueba | Qué se espera detectar |
|---|---|---|
| **DNI** | `30.123.456`, `30123456` | Patrón con puntos y sin puntos |
| **CUIL/CUIT** | `20-30123456-7` | Formato con guiones |
| **Nombres y apellidos** | `Paciente: Juan Carlos Martínez`, `José Martínez` | Nombre con prefijo, con acentos |
| **Domicilios** | `Calle San Martín 1234`, `Av. Corrientes 2567`, `Domicilio: Calle Pellegrini 888`, `Pasaje San Lorenzo 456`, `Ruta Nacional 8 km 45` | 5 variantes de dirección |
| **Expedientes** | `Expediente N° 12345/2024` | Palabra "expediente" como sensible |
| **Víctimas** | `La víctima sufrió lesiones graves`, `La víctima realizó la denuncia` | "lesiones", "denuncia" |
| **Imputados** | `El imputado fue detenido`, `El imputado, Roberto Gómez, fue notificado` | "imputado", "detenido" |
| **Menores** | `menor de edad`, `abuso sexual contra una menor` | "abuso" |
| **Delitos sexuales** | `abuso sexual`, `agredida`, `amenazas de muerte`, `lesiones compatibles` | "abus", "agred", "amenaz", "lesion" |
| **Violencia** | `Violencia de género`, `violencia doméstica` | "viol" |
| **Fallecimientos** | `fallecimiento`, `cadaver`, `homicidio agravado`, `femicidio`, `autopsia`, `necropsia` | "fallec", "cadav", "homicid", "femicid", "autops", "necrops" |
| **Organismos judiciales** | `pericia forense`, `identificación`, `documentación`, `condena`, `denuncia`, `testigo` | "forens", "perici", "identif", "conden", "denunci", "testig" |
| **End-to-End** | Documento completo con 15 párrafos de PII | Detección múltiple, merge sin duplicados, anonimización DOCX |

### Qué NO testean

- **IA real**: los tests unitarios no invocan `opencode` ni LLMs externos. La detección por IA se valida solo a nivel de parser (`parse_pii_from_output`)
- **Frontend**: no hay tests de JavaScript/UI. Los smoke tests bash validan el flujo upload→export pero no interacciones del usuario
- **Documentos escaneados**: OCR no está cubierto. Solo se testean PDFs con texto extraíble y DOCX
- **Rendimiento**: no hay tests de carga ni benchmarks. Los smoke tests usan un solo documento de prueba
- **HA distribuido**: rate limit y sesiones se testean en 1 instancia con Redis local. No se valida comportamiento con 5 instancias concurrentes
- **Palabras sin patrón regex**: "víctima", "menor", "cadáver" (con acento) no tienen patrones regex dedicados y no se detectan automáticamente. Los tests reflejan este comportamiento actual

### CI / GitHub Actions

Dos workflows independientes:

| Workflow | Jobs | Tiempo | Qué valida |
|---|---|---|---|
| `unit-tests.yml` | `unit-tests`, `security-tests`, `quality-tests` (paralelos) | ~10s | Funciones internas, seguridad, calidad de anonimización |
| `smoke-tests.yml` | `smoke-single`, `smoke-ha` | 5-10 min | Stack Docker completo, HAProxy, flujo upload→export |

Ambos corren en `push`, `pull_request` y `workflow_dispatch`.

### Fixtures compartidos (`conftest.py`)

| Helper | Descripción |
|---|---|
| `reset_config_file()` | Resetea `regex_patterns.json` a defaults y limpia Redis config key (DB 15) |
| `pytest.fixture(autouse=True)` | Ejecuta `reset_config_file()` antes de cada test |
| `create_synthetic_docx()` | Genera DOCX con párrafos, headings, listas y tablas |
| `create_synthetic_pdf()` | Genera PDF con texto plano |
| `pii_doc_paragraphs()` | Retorna 15 párrafos sintéticos con todos los tipos de PII |
| `cleanup_temp_files()` | Limpia archivos temporales creados en tests |

### Configuración de test

El `conftest.py` configura el ambiente:

- `FLASK_SECRET_KEY`: `test-secret-key`
- `ADMIN_USER`: `admin` / `ADMIN_PASS`: `testpass`
- `REDIS_URL`: `redis://redis:6379/15` (DB aislada para tests)
- `REDIS_CONFIG_KEY`: `anonimizador:config:test`
- `SESSION_BACKEND`: `cookie`
