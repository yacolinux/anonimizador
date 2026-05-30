# Anonimizador de Documentos

App web Flask para detectar y anonimizar datos personales en PDF/DOCX. Corre en Docker Compose con OpenCode como backend IA.

## Setup

```bash
cp .env.example .env     # editar OPENAI_API_KEY, OPENAI_BASE_URL, MODEL_NAME, ADMIN_USER, ADMIN_PASS
docker compose up --build  # http://localhost:5000
```

Sin Docker:
```bash
pip install -r requirements.txt
npm install -g opencode-ai@latest
cp .env.example .env
./entrypoint.sh
```

## Variables de entorno (.env)

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | API key del proveedor LLM | `sk-or-v1-...` |
| `OPENAI_BASE_URL` | URL base del proveedor | `https://api.openrouter.ai/v1` |
| `MODEL_NAME` | Modelo a usar (formato provider/modelo) | `opencode/deepseek-v4-flash-free` |
| `FLASK_PORT` | Puerto del servidor | `5000` |
| `ADMIN_USER` | Usuario del panel admin | `adminanon` |
| `ADMIN_PASS` | Contraseña del panel admin | `cambiar-esta-clave` |
| `FLASK_SECRET_KEY` | Secret key para sesiones Flask | `cualquier-string-seguro` |
| `SESSION_COOKIE_SECURE` | Marca cookie de sesión como segura (HTTPS) | `1` |
| `READY_MAX_INFLIGHT` | Umbral de requests concurrentes para marcar busy en `/ready` | `2` |
| `SESSION_BACKEND` | Backend de sesiones (`redis` o `cookie`) | `redis` |
| `REDIS_URL` | URL de Redis compartido (single/HA) | `redis://redis:6379/0` |
| `REDIS_CONFIG_KEY` | Key Redis para config compartida | `anonimizador:config` |
| `UPLOAD_TTL_SECONDS` | Tiempo de retención de uploads con PII (segundos) | `86400` |
| `LOGIN_WINDOW_SECONDS` | Ventana de rate limit login admin (segundos) | `300` |
| `LOGIN_MAX_ATTEMPTS` | Máximo de intentos de login por ventana | `5` |

## API

### Endpoints públicos

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Frontend web |
| `/upload` | POST | Subir PDF/DOCX (multipart `file`). Retorna `{segments, keywords, default_keywords, positions, reasoning}` |
| `/export` | POST | Exportar anonimizado. Body JSON: `{filename, keywords[{word,type}], format:docx\|pdf, replacement}` |
| `/ready` | GET | Health de disponibilidad para HAProxy. Retorna `200` si libre y `503` si busy |

### Endpoints admin (requieren sesión)

| Endpoint | Método | Descripción |
|---|---|---|
| `/admin/login` | POST | Login admin. Body: `{user, password}` |
| `/admin/logout` | POST | Cerrar sesión admin |
| `/admin/status` | GET | Estado de sesión. Retorna `{logged_in: bool}` |
| `/admin/config` | GET | Obtener configuración actual. Retorna `{patterns, prompt, model_url, model_name}` |
| `/admin/config` | POST | Guardar configuración. Body: `{patterns[], prompt, model_url, model_name}` |

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
├── docker-compose.yml      # Orquestación Docker
├── docker-compose.ha.yml   # Pool HA: 5 instancias activas + 5 opcionales
├── haproxy.cfg             # Config base de HAProxy (public + sticky admin)
├── HAPROXY.md              # Guía de balanceo
├── OPERACION-HA.md         # Runbook single + HA
├── Dockerfile              # python:3.11-slim + Node.js 22 + opencode-ai
├── requirements.txt        # Dependencias Python
└── .env                    # Configuración sensible
```

### Componentes backend (`app.py`)

- **Flask app** con gunicorn (2 workers, timeout 180s)
- **Redis opcional/compartido** para sesiones admin, rate limit y config distribuida
- **Endpoint `/ready`** para balanceo: reporta estado de ocupación por requests en vuelo (`inflight`)
- **Extracción de texto**: `pdfplumber` para PDF, `python-docx` para DOCX
- **Detección PII por regex**: `detect_default_pii()` lee patrones desde `regex_patterns.json`
- **Detección PII por IA**: `call_opencode_for_pii()` ejecuta `opencode run` como subprocess (timeout 120s)
- **Normalización Unicode**: `normalize_text()` usa NFKD + elimina combining marks
- **Export DOCX**: modifica `runs` del documento original, marca en rojo bold
- **Export PDF**: usa `fpdf2` con DejaVuSans, fallback a Helvetica
- **Panel admin**: sesiones Flask con `admin_required` decorator

### Frontend (`index.html` + `style.css` + `app.js`)

- **SPA vanilla JS** sin frameworks
- **Tema oscuro por defecto** con toggle a claro (persistido en localStorage)
- **Panel documento**: texto con palabras PII resaltadas en amarillo (clickeables para toggle)
- **Panel lateral**: lista de PII agrupadas, checkbox "marcar todas", agregar palabras manualmente
- **Botón "Copiar Texto Anonimizado"**: copia el texto con reemplazos al portapapeles
- **Botón "Ver Razonamiento"**: modal con output completo de la IA
- **Panel admin**: botón discreto ⚙ en esquina inferior izquierda, login → tabs (Prompt, Patrones Regex, Elegir Modelo)

## Detección de PII

Dos capas combinadas en `/upload`:

1. **Regex configurable** (`detect_default_pii`): lee patrones desde `regex_patterns.json`. Incluye:
   - DNI argentino (`XX.XXX.XXX`, `XXXXXXXX`)
   - Direcciones (`calle`, `av.`, `domicilio` + texto + número)
   - Edad (`XX años`)
   - Sexo (`Masculino`, `Femenino`, etc.)
   - Nombres con prefijo (`Paciente:`, `Sr.`, etc.)
   - Emails
   - Palabras sensibles (`abus*`, `viol*`, `homicid*`, `femicid*`, `forens*`, `expedient*`, etc.)

2. **IA via opencode** (`call_opencode_for_pii`): ejecuta `opencode run --model opencode/{modelo} --file texto.txt --dangerously-skip-permissions`. El prompt es configurable desde el panel admin. Pide JSON array `[{word, type}]`.

Posiciones combinadas (sin duplicados) ordenadas por segmento.

## Configuración de modelo

El modelo se configura en `.env` (`MODEL_NAME`) y puede sobrescribirse desde el panel admin (tab "Elegir Modelo"). La configuración se guarda en `regex_patterns.json` con campos `model_url` y `model_name`.

- **Formato**: `provider/modelo` (ej: `opencode/deepseek-v4-flash-free`)
- **Provider `opencode`**: usa la API key configurada en `auth.json` (generado por `entrypoint.sh` desde `OPENAI_API_KEY`)
- **Modelos locales**: se puede configurar cualquier endpoint compatible OpenAI cambiando `model_url` (ej: `http://localhost:11434/v1` para Ollama)

## Particularidades

- **Normalización Unicode**: `normalize_text()` usa NFKD + elimina combining marks. Crucial para acentos (Pérez vs Perez). Afecta `find_word_positions`, `anonymize_docx`, `anonymize_pdf`.
- **Texto de reemplazo default**: `[REDACTADO]` (configurable en el frontend)
- **Export PDF → DOCX**: no permitido (python-docx no puede abrir PDFs). El frontend deshabilita la opción DOCX y muestra un mensaje explicativo.
- **Timeout subprocess**: 120s para opencode (gunicorn timeout 180s)
- **Subida máxima**: 50MB
- **Auth opencode**: `entrypoint.sh` escribe `~/.local/share/opencode/auth.json` si `OPENAI_API_KEY` está definida
- **HA / balanceo**: endpoint `/ready` + `READY_MAX_INFLIGHT` para que HAProxy enrute sólo a instancias libres
- **Sticky admin**: mantener afinidad `/admin/*` en HAProxy

## HA (5 a 10 instancias)

- `docker-compose.ha.yml` trae `web1..web5` activas por default (`5001..5005`)
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
