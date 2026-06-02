# GitHub Actions

Este repositorio tiene **2 workflows** de CI que corren en cada `push`, `pull_request` y `workflow_dispatch`.

## Workflows

### 1. `unit-tests.yml` — Unit & Security Tests

**Tiempo:** ~10 segundos (3 jobs paralelos)

| Job | Qué corre | Tests | Tiempo |
|---|---|---|---|
| `unit-tests` | 9 archivos de tests unitarios | ~139 tests | ~5s |
| `security-tests` | `test_security.py` | 41 tests | ~3s |
| `quality-tests` | `test_anonymization_quality.py` | 46 tests | ~3s |

#### Cómo funciona

1. Checkout del repositorio
2. Crea `.env` temporal desde `.env.example`
3. Construye la imagen Docker (`docker compose build web`)
4. Corre los tests dentro del container con `docker compose run`
5. Sube resultados como artifact (siempre, incluso si fallan)

#### Detalle por job

**`unit-tests`** — Funciones internas aisladas:
- `test_regex_detection.py` — Detección PII por regex
- `test_parse_llm_response.py` — Parser de output de IA
- `test_unicode_normalization.py` — Normalización Unicode
- `test_replace_normalized.py` — Función de reemplazo
- `test_filename_validation.py` — Validación de filenames
- `test_admin_config_validation.py` — Config del panel admin
- `test_aymurai_integration.py` — Integración AymurAI (NER judicial)
- `test_export_docx.py` — Anonimización DOCX
- `test_export_pdf.py` — Anonimización PDF (incluye fallback OCR con `scansmpl.pdf`)

**`security-tests`** — Seguridad de la API:
- Subida de archivos no permitidos (exe, txt, zip, path traversal, null byte)
- Path traversal en filenames y exports
- Rate limit de login admin (bloqueo tras 5 intentos)
- Cookies HttpOnly + SameSite=Lax
- Auth requerida en endpoints admin y `/uploads/`
- Validación de config admin (regex inválido, URL inválida, longitud)
- Reanalyze con filename inválido
- Endpoint `/ready`

**`quality-tests`** — Calidad de anonimización con documentos sintéticos:
- DNI, CUIL/CUIT, nombres, domicilios, expedientes
- Víctimas, imputados, menores
- Delitos sexuales, violencia, fallecimientos
- Organismos judiciales
- End-to-end: documento completo con merge sin duplicados

#### Ejecutar localmente

```bash
# Todos
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v

# Unitarios
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/ -v \
  --ignore=testing/test_security.py \
  --ignore=testing/test_anonymization_quality.py

# Seguridad
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_security.py -v

# Calidad
docker compose run --rm -e SESSION_BACKEND=cookie web pytest testing/test_anonymization_quality.py -v
```

---

### 2. `smoke-tests.yml` — Smoke Tests E2E + Unit Tests

**Tiempo:** ~5-10 minutos (3 jobs + resumen)

| Job | Qué corre | Timeout |
|---|---|---|
| `unit-tests` | `pytest testing/ -v` (218 tests) | 15 min |
| `smoke-single` | `testing/smoke_single.sh` (1 instancia) | 35 min |
| `smoke-ha` | `testing/smoke_ha.sh` (HAProxy + 5 instancias) | 45 min |
| `summary` | Resumen textual (siempre, aunque fallen) | — |

#### Cómo funciona

1. Checkout del repositorio
2. Permisos de ejecución en scripts de testing
3. Crea `.env` temporal desde `.env.example`
4. Ejecuta el smoke test correspondiente (levanta stack Docker completo)
5. Sube logs como artifact (siempre, incluso si fallan)

#### Qué valida `unit-tests` (dentro de `smoke-tests.yml`)

- 218 tests pytest (unitarios, seguridad, calidad)
- Fallback OCR con `scansmpl.pdf` (`test_anonymize_pdf_scanned_pdf_ocr_fallback`)
- Levanta solo Redis (`docker compose up -d redis`) y corre `pytest testing/ -v`

#### Qué valida `smoke-single`

- Levantado de stack single (`docker-compose.yml`)
- `GET /ready` responde `200`
- Flujo `upload → export` (DOCX) responde `200`

#### Qué valida `smoke-ha`

- Levantado de stack HA (`docker-compose.ha.yml`)
- `GET /ready` por HAProxy responde `200`
- Flujo `upload → export` por HAProxy responde `200`
- Stats HAProxy accesibles en `http://localhost:8404/stats`
- Página 503 con auto-refresh cuando no hay backends
- Recuperación al reactivar backends

#### Ejecutar localmente

```bash
# Single
./testing/smoke_single.sh

# HA
./testing/smoke_ha.sh

# Ambos
./testing/run_all.sh
```

---

## Resumen de workflows

| Workflow | Archivo | Jobs | Tiempo | Trigger |
|---|---|---|---|---|
| Unit & Security Tests | `.github/workflows/unit-tests.yml` | 3 (paralelos) | ~10s | push, PR, manual |
| Smoke Tests + Unit Tests | `.github/workflows/smoke-tests.yml` | 3 + summary | 5-10 min | push, PR, manual |

## Flujo recomendado

1. **PR review**: `unit-tests.yml` da feedback inmediato (< 1 min)
2. **Merge**: `smoke-tests.yml` valida el stack completo
3. Si los unit tests fallan, no tiene sentido ejecutar smoke tests

## Artifacts

Cada job sube artifacts incluso si falla, para facilitar debugging:

| Workflow | Job | Artifact | Contenido |
|---|---|---|---|
| `unit-tests.yml` | `unit-tests` | `unit-test-results` | Directorio `testing/` completo |
| `unit-tests.yml` | `security-tests` | `security-test-results` | Directorio `testing/` completo |
| `unit-tests.yml` | `quality-tests` | `quality-test-results` | Directorio `testing/` completo |
| `smoke-tests.yml` | `unit-tests` | `pytest-output` | `testing/logs/` y logs de pytest |
| `smoke-tests.yml` | `smoke-single` | `smoke-single-logs` | `testing/logs/smoke-single-*.log` |
| `smoke-tests.yml` | `smoke-ha` | `smoke-ha-logs` | `testing/logs/smoke-ha-*.log` |
