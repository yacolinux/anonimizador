# 🕵️ Anonimizador de Documentos

Aplicación web para detectar y anonimizar datos personales en documentos PDF y DOCX. Combina detección por reglas (regex configurables) con análisis por IA vía **OpenCode** para identificar información sensible como nombres, DNI, direcciones, montos de dinero, palabras jurídicas y más, y luego exporta el documento anonimizado o copia el texto al portapapeles.

![Flask](https://img.shields.io/badge/Flask-3.1-blue) ![Python](https://img.shields.io/badge/Python-3.11-green) ![Docker](https://img.shields.io/badge/Docker-Compose-2496ED) ![License](https://img.shields.io/badge/license-MIT-lightgrey)

![Documento Simulado](screenshots/documento-simulado.jpeg)
*Documento Simulado*

---

## ✨ Características

- **Carga drag & drop** de archivos PDF y DOCX (máx 50 MB)
- **Detección en dos capas**:
  - **Regex configurable**: 29 patrones editables desde el panel admin — DNI argentino, direcciones, edad, sexo, nombres, emails, y palabras sensibles (`abus*`, `viol*`, `homicid*`, `femicid*`, `forens*`, `expedient*`, etc.)
  - **IA**: vía **OpenCode** con prompts personalizables, usando cualquier modelo LLM compatible OpenAI
- **Interfaz interactiva**:
  - Documento renderizado con palabras PII resaltadas en **amarillo**
  - Click para agregar/quitar palabras de la lista de anonimización
  - Checkbox "Marcar todas" para togglear todas las ocurrencias de una palabra
  - Agregar palabras manualmente desde el panel lateral
  - **Copiar Texto Anonimizado** al portapapeles (ideal para chatbots)
  - **Ver Razonamiento** de la IA en modal
  - Tema oscuro/claro con persistencia en localStorage
- **Exportación** del documento anonimizado en:
  - **DOCX** (reemplaza palabras manteniendo formato original)
  - **PDF** (genera nuevo documento con tipografía DejaVu)
  - *Nota*: PDFs originales solo pueden exportarse a PDF (python-docx no abre PDFs)
- **Panel de Administración** (acceso discreto ⚙ esquina inferior izquierda):
  - Login con credenciales configurables en `.env`
  - **Prompt**: editar el prompt que se envía a la IA
  - **Patrones Regex**: editar los patrones de detección en formato JSON
  - **Elegir Modelo**: configurar API endpoint URL y nombre del modelo (soporta modelos locales como Ollama)
- **Normalización Unicode**: maneja acentos correctamente (Pérez ↔ Perez)
- **Corre en Docker Compose** con un solo comando

---

## 🚀 Instalación y uso

### Requisitos

- Docker y Docker Compose v2
- Una API key de un proveedor LLM ([OpenRouter](https://openrouter.ai), [Together AI](https://together.ai), etc.)

### Pasos

```bash
# 1. Clonar el repositorio
git clone https://github.com/tu-usuario/anonimizador.git
cd anonimizador

# 2. Configurar variables de entorno
cp .env.example .env
# Editar .env con tu API key, modelo deseado y credenciales admin

# 3. Iniciar
docker compose up --build
```

La aplicación estará disponible en `http://localhost:5000`.

### Variables de entorno

| Variable | Descripción | Ejemplo |
|---|---|---|
| `OPENAI_API_KEY` | API key del proveedor LLM | `sk-or-v1-...` |
| `OPENAI_BASE_URL` | URL base del proveedor | `https://api.openrouter.ai/v1` |
| `MODEL_NAME` | Modelo a usar (formato provider/modelo) | `opencode/deepseek-v4-flash-free` |
| `FLASK_PORT` | Puerto del servidor | `5000` |
| `ADMIN_USER` | Usuario del panel admin | `adminanon` |
| `ADMIN_PASS` | Contraseña del panel admin | `IJGNF678` |
| `FLASK_SECRET_KEY` | Secret key para sesiones Flask | `cualquier-string-seguro` |

### Sin Docker

```bash
pip install -r requirements.txt
npm install -g opencode-ai@latest
cp .env.example .env
./entrypoint.sh
```

---

## 🧠 Arquitectura

```
anonimizador/
├── app.py                  # Backend Flask (API endpoints, detección PII, export, admin)
├── entrypoint.sh           # Configura opencode auth.json al iniciar
├── regex_patterns.json     # Patrones regex + prompt + config modelo (editable desde admin)
├── templates/
│   └── index.html          # Frontend HTML (SPA)
├── static/
│   ├── style.css           # CSS con tema oscuro/claro + admin panel
│   └── app.js              # Lógica frontend: upload, PII toggle, export, copy, admin
├── docker-compose.yml      # Orquestación Docker
├── Dockerfile              # python:3.11-slim + Node.js 22 + opencode-ai
├── requirements.txt        # Dependencias Python
├── .env                    # Configuración sensible
└── .env.example            # Plantilla de configuración
```

### Flujo de procesamiento

1. **Upload** → se extrae el texto del PDF/DOCX preservando títulos, párrafos y listas
2. **Detección regex** → patrones desde `regex_patterns.json` buscan DNI, direcciones, edad, sexo, nombres, emails, palabras sensibles
3. **Detección IA** → el texto se envía a **OpenCode** (`opencode run --model ...`) que analiza y devuelve palabras PII adicionales con categorías
4. **Combinación** → se fusionan posiciones sin duplicados y se devuelven al frontend
5. **Interacción** → el usuario revisa, agrega o quita palabras, puede copiar el texto anonimizado
6. **Exportación** → se reemplazan las palabras seleccionadas con `[REDACTADO]` y se descarga el documento

### API REST

| Endpoint | Método | Descripción |
|---|---|---|
| `/` | GET | Frontend web |
| `/upload` | POST | Subir PDF/DOCX (multipart `file`) |
| `/export` | POST | Exportar documento anonimizado (JSON body) |
| `/admin/login` | POST | Login panel admin |
| `/admin/logout` | POST | Logout panel admin |
| `/admin/status` | GET | Estado de sesión admin |
| `/admin/config` | GET | Obtener config (patrones, prompt, modelo) |
| `/admin/config` | POST | Guardar config |

#### `/upload` response

```json
{
  "filename": "uuid.docx",
  "segments": [
    {"type": "title", "text": "Informe"},
    {"type": "paragraph", "text": "Paciente: Juan Pérez, DNI 30.123.456"}
  ],
  "keywords": [
    {"word": "Juan Pérez", "type": "nombre"}
  ],
  "default_keywords": [
    {"word": "30.123.456", "type": "dni_argentino"}
  ],
  "positions": [
    {"segment": 1, "start": 12, "end": 22, "word": "Juan Pérez", "type": "nombre"}
  ],
  "reasoning": "Output completo de la IA..."
}
```

#### `/export` request

```json
{
  "filename": "uuid.docx",
  "keywords": [
    {"word": "Juan Pérez", "type": "nombre"},
    {"word": "30.123.456", "type": "dni_argentino"}
  ],
  "format": "docx",
  "replacement": "[REDACTADO]"
}
```

---

## 🔍 Detección regex (configurable)

Patrones por defecto en `regex_patterns.json` (editables desde el panel admin):

| Tipo | Patrón | Ejemplo |
|---|---|---|
| DNI argentino | `\b\d{1,2}\.?\d{3}\.?\d{3}\b` | `30.123.456` |
| DNI sin puntos | `\b\d{7,8}\b` | `30123456` |
| Dirección | `(?:calle\|av\.|avenida\|domicilio...) + texto + número` | `Av. Siempre Viva 742` |
| Edad | `\d+\s*(?:años\|anios\|años de edad)` | `45 años` |
| Sexo | `\b(?:masculino\|femenino\|varón\|mujer...)\b` | `Masculino` |
| Nombre | `(?:paciente\|nombre\|Sr.\|Sra....) + nombre + apellido` | `Paciente: Carlos Martínez` |
| Email | `\b[\w.-]+@[\w.-]+\.\w{2,}\b` | `juan@mail.com` |
| Sensibles | `abus\w*`, `viol\w*`, `fallec\w*`, `homicid\w*`, `femicid\w*`, `lesion\w*`, `amenaz\w*`, `agred\w*`, `imput\w*`, `conden\w*`, `deten\w*`, `testig\w*`, `denunci\w*`, `perici\w*`, `forens\w*`, `cadav\w*`, `autops\w*`, `necrops\w*`, `identif\w*`, `domicil\w*`, `document\w*`, `expedient\w*` | `abuso`, `homicidio`, `forense` |

---

## ⚙️ Panel de Administración

Acceso: botón ⚙ en la esquina inferior izquierda.

### Credenciales

Configurables en `.env`:
- `ADMIN_USER=adminanon`
- `ADMIN_PASS=IJGNF678`

### Tabs

1. **Prompt**: Editor del prompt que se envía a la IA. Usa `{text}` como placeholder para el texto del documento.
2. **Patrones Regex**: Editor JSON de los patrones de detección. Formato: `[{"pattern": "regex", "type": "categoria"}, ...]`
3. **Elegir Modelo**: Configurar el modelo LLM:
   - **API Endpoint URL**: URL base del proveedor (ej: `https://api.openrouter.ai/v1` o `http://localhost:11434/v1` para Ollama)
   - **Nombre del modelo**: Formato `provider/modelo` (ej: `opencode/deepseek-v4-flash-free`)

Los cambios se aplican inmediatamente al siguiente documento cargado.

---

## 🧪 Pruebas rápidas

```bash
# Crear documento de prueba
docker exec -i anonimizador-web-1 python3 -c "
from docx import Document
d = Document()
d.add_heading('Historia Clínica', level=1)
d.add_paragraph('Paciente: Juan Pérez, DNI 30.123.456')
d.add_paragraph('Dirección: Av. Corrientes 1234, CABA')
d.save('/tmp/test.docx')
"
docker cp anonimizador-web-1:/tmp/test.docx /tmp/test.docx

# Probar subida
curl -s -F "file=@/tmp/test.docx" http://localhost:5000/upload | python3 -m json.tool

# Probar exportación
curl -s -F "file=@/tmp/test.docx" http://localhost:5000/upload > /tmp/r.json
python3 -c "
import json
r = json.load(open('/tmp/r.json'))
kw = [{'word': p['word'], 'type': p['type']} for p in r['positions']]
print(json.dumps({'filename': r['filename'], 'keywords': kw, 'format': 'docx'}))
" | curl -s -X POST -H 'Content-Type: application/json' -d @- http://localhost:5000/export -o /tmp/anon.docx

# Probar panel admin
curl -s -c /tmp/cookies.txt -X POST -H 'Content-Type: application/json' \
  -d '{"user":"adminanon","password":"IJGNF678"}' http://localhost:5000/admin/login
curl -s -b /tmp/cookies.txt http://localhost:5000/admin/config | python3 -m json.tool
```

---

## 🛠️ Tecnologías

| Tecnología | Uso |
|---|---|
| **Python 3.11** | Backend |
| **Flask 3.1** | Framework web |
| **Gunicorn** | Servidor WSGI (2 workers, timeout 180s) |
| **pdfplumber** | Extracción de texto de PDFs |
| **python-docx** | Extracción y generación de DOCX |
| **fpdf2** | Generación de PDFs |
| **OpenCode** | Agente IA para detección de PII vía CLI |
| **Node.js 22** | Runtime para OpenCode |
| **Docker Compose** | Orquestación de servicios |
| **JavaScript vanilla** | Frontend SPA interactivo |

---

## 📄 Licencia

MIT
