# Análisis de AymurAI

## Resumen

Sí, AymurAI puede encajar como componente adicional antes de la IA actual, pero no como reemplazo total del flujo existente.

La mejor posición para integrarlo sería como una capa especializada de detección judicial en español entre `regex` y `opencode`.

## Qué es AymurAI

AymurAI es un backend/API orientado al procesamiento de fallos judiciales relacionados con violencia de género en Latinoamérica.

Su arquitectura general se basa en tres etapas:

- preprocesamiento
- inferencia
- postprocesamiento

Utiliza un modelo NER judicial en español basado en `Flair`, además de otros componentes para clasificación y postprocesado.

Características relevantes:

- API propia
- despliegue Docker
- funcionamiento offline una vez desplegado
- foco en documentos judiciales en español

Imagen Docker pública observada en su documentación:

```bash
ghcr.io/aymurai/api:full
```

## Endpoints relevantes

### 1. Extracción de documento

Endpoint:

- `POST /misc/document-extract`

Función:

- extrae texto del archivo
- lo normaliza
- lo devuelve dividido en párrafos

Esto es útil si se quisiera comparar su extracción contra la extracción actual.

### 2. Predicción de anonimización

Endpoint:

- `POST /anonymizer/predict`

Entrada:

- un texto o párrafo

Salida:

- el documento procesado
- una lista de entidades con spans reales

Ejemplo de forma de respuesta:

```json
{
  "document": "...",
  "labels": [
    {
      "text": "Ramiro Marrón",
      "start_char": 9,
      "end_char": 23,
      "attrs": { ... }
    }
  ]
}
```

Esto es especialmente valioso porque devuelve offsets exactos, no sólo keywords.

## Qué aporta frente al flujo actual

Hoy la app actual funciona así:

1. extracción de texto
2. detección por `regex`
3. detección por `opencode` o `API Directa`
4. merge de posiciones
5. marcado en frontend

Con AymurAI, el flujo recomendable sería:

1. extracción actual
2. `regex`
3. AymurAI sobre cada segmento/párrafo
4. merge `regex + AymurAI`
5. `opencode` sólo como capa de cobertura final
6. merge final

## Beneficios posibles

- mejor recall en lenguaje judicial en español
- detección más estructurada de entidades jurídicas
- spans exactos sin necesidad de reubicar keywords por texto
- menor dependencia del LLM para entidades repetitivas o más predecibles
- posible reducción de costo y ruido si el LLM recibe menos contexto o sólo casos residuales
- capacidad de correr offline/local una vez desplegado

## Estrategias de integración posibles

### Opción 1: prefiltro de entidades

Usar AymurAI para detectar entidades antes del LLM.

Todo lo detectado por AymurAI:

- ya se marca directamente
- no depende del LLM

El LLM quedaría para detectar entidades faltantes o más ambiguas.

Esta es la opción más recomendable.

### Opción 2: prefiltro por párrafos

Si `regex` y AymurAI no detectan nada relevante en un párrafo:

- ese párrafo no se manda al LLM

Esto puede reducir:

- costo
- tiempo
- ruido semántico

### Opción 3: filtro documental por relevancia

AymurAI también tiene lógica de filtrado de decisiones irrelevantes.

Eso podría servir para priorizar partes del documento, pero para esta app no parece conveniente usarlo como filtro duro, porque el objetivo principal es anonimizar, no clasificar expedientes.

## Limitaciones

### 1. Dominio muy específico

Está entrenado para documentos judiciales, especialmente vinculados a violencia de género.

Puede rendir bien en:

- expedientes
- resoluciones
- pericias
- informes judiciales

Puede rendir peor en:

- documentos médicos no judiciales
- contratos
- CVs
- textos administrativos generales

### 2. Taxonomía diferente

Las entidades de AymurAI probablemente no coinciden 1:1 con los `type` de esta app.

Sería necesario mapear:

- `attrs` de AymurAI
- a categorías internas como `nombre`, `dni`, `direccion`, `sensible`, etc.

### 3. Costo operativo del stack

El backend de AymurAI trae una base pesada:

- `torch`
- `tensorflow`
- `flair`
- migraciones de base de datos
- imagen Docker grande

En su documentación aparece un despliegue `full` con una huella considerable y sugerencias de recursos que pueden llegar a varios GB de RAM.

### 4. Patrón de uso por párrafo

El endpoint público observado de predicción está orientado a texto/párrafo.

Eso implica que, si se integra tal cual, podría requerir:

- múltiples llamadas HTTP por documento
- o una adaptación/caché/batch local

## Qué no conviene usar

No parece conveniente usar AymurAI para reemplazar:

- la exportación DOCX/PDF actual
- la UI actual
- el flujo de selección manual de entidades

Tampoco parece buena idea tomar su endpoint de anonimización documental completa como caja negra para sustituir la lógica actual, porque esta app ya resuelve bien:

- frontend
- marcado interactivo
- exportación
- control del flujo de anonimización

## Recomendación técnica

La mejor estrategia sería incorporarlo como detector judicial especializado opcional.

Orden sugerido del pipeline:

1. `regex`
2. `AymurAI`
3. `opencode`
4. merge final

De esa forma:

- `regex` cubre patrones determinísticos
- AymurAI cubre entidades judiciales especializadas
- `opencode` cubre contexto abierto y casos residuales

## Integración mínima sugerida

### Despliegue

Levantar AymurAI como sidecar o servicio aparte:

```bash
docker run -d -p 8899:8899 ghcr.io/aymurai/api:full
```

### Integración en la app actual

Por cada `segment` relevante:

1. llamar a `POST /anonymizer/predict`
2. tomar `labels[start_char, end_char, text, attrs]`
3. convertirlos al esquema actual de `positions`
4. mapear `attrs` a `type`
5. mergear con `regex`
6. mandar al LLM sólo lo faltante o usarlo como capa complementaria

## Recomendación final

Sí vale la pena investigarlo para integración, pero como:

- capa previa especializada de NER judicial
- no como sustituto total del pipeline actual

## Próximos pasos recomendados

1. mapear exactamente `labels.attrs` de AymurAI al esquema de tipos de esta app
2. definir si se integrará por HTTP o mediante servicio local sidecar
3. evaluar un feature flag tipo `USE_AYMURAI=1`
4. integrarlo en `run_detection_pipeline()` sin romper el flujo actual

## Mapeo propuesto `labels.attrs` -> `type`

La API observada de AymurAI devuelve entidades con esta estructura relevante:

- `text`
- `start_char`
- `end_char`
- `attrs.aymurai_label`
- `attrs.aymurai_label_subclass`
- `attrs.aymurai_alt_text`
- `attrs.aymurai_alt_start_char`
- `attrs.aymurai_alt_end_char`

La app actual usa tipos mucho más simples. Para integrarlo sin romper frontend ni export, el mapeo recomendado sería:

| AymurAI `aymurai_label` | `type` interno | Motivo |
|---|---|---|
| `NOMBRE` | `nombre` | Equivalencia directa |
| `PER` | `nombre` | Label real observado en API para personas |
| `GENERO` | `sexo` | Equivalencia directa con el modelo actual |
| `FECHA_DE_NACIMIENTO` | `fecha` | Dato personal directo |
| `FECHA_RESOLUCION` | `fecha` | Fecha judicial relevante |
| `FECHA_DEL_HECHO` | `fecha` | Fecha sensible/relevante |
| `HORA_DE_INICIO` | `fecha` | Mantener categoría simple, ya que no existe `hora` |
| `HORA_DE_CIERRE` | `fecha` | Igual criterio que arriba |
| `LUGAR_DEL_HECHO` | `direccion` | Mejor aproximación al esquema actual |
| `LOC` | `direccion` | Label real observado para ubicaciones |
| `DIRECCION` | `direccion` | Label real observado para direcciones postales |
| `DOMICILIO` | `direccion` | Label real observado (sin tilde) |
| `EDAD` | `edad` | Label real observado para edad |
| `EDAD_AL_MOMENTO_DEL_HECHO` | `edad` | Equivalencia directa |
| `DNI` | `dni_argentino` | Label real observado para documento |
| `N_EXPTE_EJE` | `sensible` | Dato judicial sensible |
| `TIPO_DE_RESOLUCION` | `sensible` | Relevancia judicial/documental |
| `OBJETO_DE_LA_RESOLUCION` | `sensible` | Relevancia judicial/documental |
| `CONDUCTA` | `sensible` | Hecho o conducta penal sensible |
| `CONDUCTA_DESCRIPCION` | `sensible` | Hecho o conducta penal sensible |
| `ART_INFRINGIDO` | `sensible` | Contexto jurídico sensible |
| `DETALLE` | `sensible` | Suele contener texto relevante para anonimización |
| `FRASES_AGRESION` | `sensible` | Lenguaje de violencia/agresión |
| `VIOLENCIA_DE_GENERO` | `sensible` | Equivalencia operativa actual |
| `MODALIDAD_DE_LA_VIOLENCIA` | `sensible` | Equivalencia operativa actual |
| `RELACION_Y_TIPO_ENTRE_ACUSADO/A_Y_DENUNCIANTE` | `sensible` | Relación interpersonal sensible |
| `PERSONA_ACUSADA_NO_DETERMINADA` | `sensible` | Entidad judicial sensible |
| `HIJOS_HIJAS_EN_COMUN` | `sensible` | Información personal/familiar sensible |
| `NACIONALIDAD` | `other` | Dato personal, pero no tiene categoría mejor en el esquema actual |
| `NIVEL_INSTRUCCION` | `other` | Dato personal, no judicial duro |

### Regla de fallback

Si aparece un `aymurai_label` no contemplado:

- `type = "other"`

Esto evita romper el flujo actual y deja visible la entidad en UI/export.

### Uso de spans alternativos

Cuando AymurAI entregue:

- `aymurai_alt_text`
- `aymurai_alt_start_char`
- `aymurai_alt_end_char`

conviene priorizarlos sobre:

- `text`
- `start_char`
- `end_char`

porque AymurAI los usa para normalización/formateo posterior.

Orden recomendado:

1. usar `alt_*` si existen completos
2. si no, usar los spans originales

## Punto exacto de integración en `run_detection_pipeline()`

El lugar correcto es entre:

- `detect_default_pii(segments)`
- y `call_opencode_for_pii()` / `call_direct_api_for_pii()`

### Orden recomendado de pipeline

1. extracción de texto
2. `regex`
3. `AymurAI`
4. `opencode`
5. merge final

### Diseño sugerido dentro de `run_detection_pipeline()`

Pseudoflujo:

```python
plaintext = segments_to_plaintext(segments)

default_keywords, default_positions = detect_default_pii(segments)

aymurai_keywords, aymurai_positions = [], []
if use_aymurai():
    aymurai_keywords, aymurai_positions = call_aymurai_for_segments(segments)

pii_keywords, reasoning_output, queue_notice, ai_status = call_opencode_for_pii(...)
ai_positions = find_word_positions(segments, pii_keywords)

all_positions = merge(default_positions, aymurai_positions, ai_positions)
all_keywords = merge(default_keywords, aymurai_keywords, pii_keywords)
```

### Funciones nuevas sugeridas

#### `call_aymurai_for_segments(segments)`

Responsabilidad:

- iterar segmentos útiles (`paragraph`, `title`, `list`)
- llamar a `POST /anonymizer/predict`
- transformar la respuesta a:
  - `keywords`
  - `positions`

#### `map_aymurai_labels_to_positions(seg_idx, label)`

Responsabilidad:

- tomar un `label`
- decidir si usa `alt_*` o no
- mapear `aymurai_label` a `type`
- generar una `position` compatible con el frontend actual

Salida esperada:

```json
{
  "segment": 12,
  "start": 45,
  "end": 62,
  "word": "Juan Pérez",
  "type": "nombre"
}
```

### Primera integración recomendada

Para minimizar riesgo:

- seguir mandando el texto completo a `opencode`
- usar AymurAI sólo como detector adicional
- mergear al final

Eso evita cambiar demasiada lógica en una primera etapa.

### Segunda etapa (implementada)

Cuando la integración está estable:

- `_get_uncovered_segments()` excluye del LLM segmentos con ≥30% de caracteres cubiertos por `regex + AymurAI`
- el LLM recibe solo segmentos no cubiertos (o con cobertura parcial baja)
- si todos los segmentos están cubiertos, el LLM se omite completamente (`ai_status: "skipped"`)
- esto reduce tokens, latencia y costo sin perder cobertura

## Modo opcional `USE_AYMURAI=1`

Para no romper el flujo actual, la integración debería quedar completamente opt-in.

### Variables sugeridas

Obligatoria principal:

```bash
USE_AYMURAI=0
```

Si se activa:

```bash
USE_AYMURAI=1
AYMURAI_BASE_URL=http://aymurai:8899
AYMURAI_TIMEOUT_SECONDS=20
AYMURAI_MIN_SEGMENT_CHARS=15
```

### Semántica sugerida

- `USE_AYMURAI=0`
  - comportamiento actual intacto
- `USE_AYMURAI=1`
  - activa la llamada a AymurAI antes de opencode

### Función helper sugerida

```python
def use_aymurai():
    return os.environ.get("USE_AYMURAI", "0") == "1"
```

### Comportamiento ante error

Si AymurAI falla:

- log warning
- no romper `/upload`
- continuar con `regex + opencode`

Es decir: AymurAI debe ser una capa opcional degradable.

## Sidecar recomendado

La forma más limpia de integrarlo es como sidecar Docker.

Ejemplo conceptual:

```yaml
services:
  web:
    ...
    environment:
      - USE_AYMURAI=1
      - AYMURAI_BASE_URL=http://aymurai:8899

  aymurai:
    image: ghcr.io/aymurai/api:full
    ports:
      - "8899:8899"
```

Ventajas:

- aislamiento del stack pesado
- despliegue opcional
- sin mezclar dependencias enormes dentro del contenedor principal
- fácil apagarlo sin tocar el resto

## Recomendación de implementación

Implementación recomendada:

- mantener `regex` actual
- agregar AymurAI opcional como detector judicial especializado
- usarlo antes de `opencode`
- seguir usando `opencode` para cobertura abierta/contextual

Orden sugerido:

- `regex`
- `AymurAI`
- `opencode`
- `merge`

## Próxima etapa sugerida

Si se decide avanzar con código:

1. agregar variables `USE_AYMURAI`, `AYMURAI_BASE_URL`, `AYMURAI_TIMEOUT_SECONDS`
2. implementar `call_aymurai_for_segments()`
3. integrar en `run_detection_pipeline()` como capa opcional antes de opencode
4. desplegar AymurAI como sidecar en compose
