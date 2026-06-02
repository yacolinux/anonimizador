# Workflow

## Objetivo

Este documento explica el flujo completo que sigue la app desde que el usuario sube un documento hasta que ve palabras marcadas en pantalla.

## Resumen rápido

1. El usuario sube un `PDF` o `DOCX` a `/upload`.
2. El backend extrae texto y lo divide en `segments`.
3. Sobre esos `segments` corre tres detecciones:
   - reglas `regex`
   - AymurAI (NER judicial opt-in desde panel admin, si `use_aymurai=true`)
   - análisis IA (opcional desde panel admin, si `use_opencode=true`; usa `opencode` o `API Directa`)
4. Los resultados se fusionan y convierten a posiciones dentro del documento.
5. El frontend recibe esas posiciones y marca las palabras en el texto visible.

## Paso 1: upload del documento

- El usuario sube un archivo desde la interfaz web.
- El backend recibe el archivo en `POST /upload`.
- El archivo se guarda temporalmente en `uploads/`.

## Paso 2: extracción de texto

Función principal:

- `extract_text(filepath)` en `app.py`

Según el tipo de archivo:

- `PDF`: usa `extract_text_pdf()` con `pdfplumber`
- `DOCX`: usa `extract_text_docx()` con `python-docx`

Si el PDF tiene poco texto extraíble:

- se activa `extract_text_ocr()`
- usa `pdf2image` + `pytesseract`

Resultado:

- una lista de `segments`, por ejemplo:

```json
{"type": "paragraph", "text": "Paciente: Juan Pérez"}
```

Los tipos más comunes son:

- `title`
- `paragraph`
- `list`

## Paso 3: detección por regex

Función principal:

- `detect_default_pii(segments)`

Cómo funciona:

- carga patrones desde `regex_patterns.json` con `get_pii_patterns()`
- recorre cada segmento
- aplica cada regex con `re.finditer(...)`
- genera posiciones exactas dentro del texto

Salida:

- `default_keywords`
- `default_positions`

Cada `position` contiene:

- `segment`
- `start`
- `end`
- `word`
- `type`

Ejemplos de entidades detectadas por regex:

- DNI
- direcciones
- edad
- sexo
- nombres con prefijo
- email
- palabras sensibles o judiciales

## Paso 4: detección por AymurAI (NER judicial opt-in desde admin)

Si `use_aymurai=true` en la config del panel admin, se activa una capa intermedia de detección judicial especializada. Se sobrescribe en runtime, no depende de env var.

Función principal:

- `call_aymurai_for_segments(segments)`

Cómo funciona:

- itera cada segmento con al menos `AYMURAI_MIN_SEGMENT_CHARS` caracteres
- envía cada segmento a `POST {AYMURAI_BASE_URL}/anonymizer/predict`
- recibe etiquetas con spans exactos (`start_char`, `end_char`)
- mapea labels AymurAI a tipos internos vía `map_aymurai_label_to_type()` (28 labels mapeados, fallback `"other"`)

Labels reales observados en API:

| Label AymurAI | `type` interno | Ejemplo |
|---|---|---|
| `PER` | `nombre` | "Juan Pérez" |
| `DNI` | `dni_argentino` | "30.123.456" |
| `DIRECCION` | `direccion` | "San Martín 1234" |
| `LOC` | `direccion` | Ubicaciones |
| `EDAD` | `edad` | "45 años" |

Labels no reconocidos caen a `type: "other"` (visible en UI/export).

Prioridad de spans:

- si `attrs.aymurai_alt_text/alt_start_char/alt_end_char` existen, se usan primero
- si no, se usan `text/start_char/end_char` originales

Alineación con texto real:

- `resolve_aymurai_range()` busca el texto real del segmento usando `find_normalized_ranges()` para manejar diferencias de normalización

Salida:

- `aymurai_keywords`
- `aymurai_positions` (con `segment`, `start`, `end`, `word`, `type`)

Degradación:

- si AymurAI falla, no está disponible o retorna `labels: []`, se loguea un warning y se continúa con `regex + opencode` sin interrumpir el upload

Variables de entorno (se sobrescriben desde panel admin en runtime):

| Variable | Default | Descripción |
|---|---|---|
| `USE_AYMURAI` | `0` | Activar (1) o desactivar (0) AymurAI. Sobrescrito por `use_aymurai` en config |
| `AYMURAI_BASE_URL` | `http://aymurai:8899` | URL del sidecar AymurAI. Sobrescrito por `aymurai_url` en config |
| `AYMURAI_TIMEOUT_SECONDS` | `20` | Timeout por llamada HTTP |
| `AYMURAI_MIN_SEGMENT_CHARS` | `15` | Mínimo de caracteres para enviar un segmento |

Sidecar:

- se despliega con `docker compose --profile aymurai up -d`
- definido en `docker-compose.yml` y `docker-compose.ha.yml` con profile `"aymurai"`
- imagen: `ghcr.io/aymurai/api:full` (~8GB)

## Paso 5: detección por IA (con optimización de cobertura)

Función orquestadora:

- `run_detection_pipeline(segments, ...)`

### Optimización: texto reducido para IA

Antes de enviar texto a la IA, el pipeline corre regex + AymurAI y calcula la cobertura de cada segmento:

- `_segment_coverage_ratio()` mide qué proporción de caracteres del segmento está cubierta por posiciones de regex o AymurAI
- si un segmento tiene ≥30% de sus caracteres cubiertos, se excluye del texto enviado a la IA
- `_get_uncovered_segments()` recolecta solo los segmentos con <30% de cobertura
- si todos los segmentos están cubiertos, la IA se omite completamente (`ai_status: "skipped"`)

Esto reduce tokens, latencia y costo sin perder cobertura, porque los segmentos ya cubiertos no aportan información nueva.

Ejemplo real con AymurAI activo:

| Segmento | Texto | Cobertura | Enviado a IA |
|---|---|---|---|
| 0 | "Test" | 0% | Sí |
| 1 | "Paciente: Juan Pérez, DNI 30.123.456" | 81% (regex + AymurAI) | No |
| 2 | "Domicilio: Calle San Martín 1234" | 94% (regex + AymurAI) | No |
| 3 | "La víctima sufrió lesiones graves..." | 27% (solo regex "lesiones") | Sí |

### Modo de análisis

Después de armar el texto reducido, decide el modo de análisis:

- si `use_opencode=false` en config: se salta la IA completamente (`ai_status: "skipped"`)
- si `use_direct_api` está activo: `call_direct_api_for_pii()`
- si no: `call_opencode_for_pii()`

### Modo OpenCode

- arma un prompt con `get_opencode_prompt()`
- inserta el texto del documento en `{text}`
- escribe el prompt a un archivo temporal
- ejecuta `opencode run ... --file {file}`
- toma la salida completa del proceso
- parsea esa salida con `parse_pii_from_output()`

### Modo API Directa

- arma el mismo prompt
- hace `POST {model_url}/chat/completions`
- toma el contenido de la respuesta
- parsea el contenido con `parse_pii_from_output()`

### Qué devuelve la IA

La IA no devuelve posiciones exactas en el documento.

Devuelve keywords del tipo:

```json
{"word": "Juan Pérez", "type": "nombre"}
```

## Paso 6: convertir keywords IA a posiciones reales

Función principal:

- `find_word_positions(segments, keywords)`

Cómo funciona:

- recorre cada segmento
- busca cada keyword dentro del texto del segmento
- usa `normalize_text()` para hacer matching robusto con acentos
- genera `ai_positions`

Importante:

- regex produce posiciones directamente
- IA produce palabras
- luego esas palabras se reubican en el documento con `find_word_positions()`

## Paso 7: merge de resultados

Dentro de `run_detection_pipeline()`:

- se combinan:
  - `default_positions` de regex
  - `aymurai_positions` de AymurAI (si activo)
  - `ai_positions` de IA
- se eliminan duplicados (misma clave `(segment, start, end, word)`)
- se ordena por segmento y rango

Resultado final devuelto al frontend:

- `positions`
- `keywords`
- `default_keywords`
- `reasoning`
- `ai_status`

## Paso 8: frontend marca el documento

Archivo principal:

- `static/app.js`

Flujo:

- el resultado del upload se guarda en `currentData`
- `applyAnalysisResult(data, true)` toma `data.positions`
- esas posiciones se guardan en `allPositions`
- `renderDocument(currentData.segments)` reconstruye el HTML del documento
- cada ocurrencia marcada se resalta visualmente y queda clickeable

El usuario ve:

- el texto del documento
- palabras detectadas resaltadas
- una lista lateral de entidades agrupadas

## Qué son “otras entidades”

Son entidades que normalmente no salen de regex sino del análisis IA o AymurAI.

Ejemplos:

- nombres completos sin prefijo
- organismos
- números de causa
- montos
- fechas
- datos contextuales sin patrón fijo

Estas entidades entran por:

- `call_aymurai_for_segments()` (NER judicial, si `USE_AYMURAI=1`)
- `call_opencode_for_pii()`
- o `call_direct_api_for_pii()`

Y después pasan por:

- `find_word_positions()`

## Resumen técnico final

- `extract_text*()` extrae texto
- `detect_default_pii()` detecta PII por regex
- `call_aymurai_for_segments()` detecta entidades judiciales vía AymurAI (opt-in desde admin, entre regex e IA)
- `_get_uncovered_segments()` filtra segmentos ya cubiertos (≥30%) antes de enviar a IA
- `call_opencode_for_pii()` o `call_direct_api_for_pii()` detectan PII por IA solo sobre texto no cubierto (si `use_opencode=true` en config)
- `find_word_positions()` ubica en el documento lo que encontró la IA
- `run_detection_pipeline()` fusiona todo (regex + AymurAI + IA)
- `renderDocument()` pinta en frontend las palabras marcadas que ve el usuario
