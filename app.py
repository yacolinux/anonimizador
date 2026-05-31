import logging
import os
import re
import json
import uuid
import hmac
import time
import unicodedata
import subprocess
import tempfile
import threading
import shlex
from urllib.request import Request, urlopen
from urllib.error import URLError
from io import BytesIO
from functools import wraps
from flask import session, g
from flask_session import Session
import redis
import pdf2image
import pytesseract

logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s'
)
logger = logging.getLogger('anonimizador')

import pdfplumber
import docx
from docx import Document
from fpdf import FPDF
from flask import (
    Flask, render_template, request, jsonify,
    send_from_directory, send_file
)

app = Flask(__name__)
app.config['UPLOAD_FOLDER'] = '/app/uploads'
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY')
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['SESSION_COOKIE_SECURE'] = os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'

MODEL_NAME = os.environ.get('MODEL_NAME', 'qwen/qwen3-30b-a3b')
ADMIN_USER = os.environ.get('ADMIN_USER', 'adminanon')
ADMIN_PASS = os.environ.get('ADMIN_PASS')
READY_MAX_INFLIGHT = int(os.environ.get('READY_MAX_INFLIGHT', '2'))
UPLOAD_TTL_SECONDS = int(os.environ.get('UPLOAD_TTL_SECONDS', str(900)))
LOGIN_MAX_ATTEMPTS = int(os.environ.get('LOGIN_MAX_ATTEMPTS', '5'))
LOGIN_WINDOW_SECONDS = int(os.environ.get('LOGIN_WINDOW_SECONDS', '300'))
SESSION_BACKEND = os.environ.get('SESSION_BACKEND', 'redis').lower()
REDIS_URL = os.environ.get('REDIS_URL', 'redis://redis:6379/0')
REDIS_CONFIG_KEY = os.environ.get('REDIS_CONFIG_KEY', 'anonimizador:config')
LOCAL_INFERENCE_MAX = int(os.environ.get('LOCAL_INFERENCE_MAX', '3'))
LOCAL_INFERENCE_WAIT_SECONDS = int(os.environ.get('LOCAL_INFERENCE_WAIT_SECONDS', '90'))
LOCAL_INFERENCE_POLL_SECONDS = float(os.environ.get('LOCAL_INFERENCE_POLL_SECONDS', '1.5'))
LOCAL_INFERENCE_SLOT_TTL_SECONDS = int(os.environ.get('LOCAL_INFERENCE_SLOT_TTL_SECONDS', '180'))
MAX_UPLOAD_MB = int(os.environ.get('MAX_UPLOAD_MB', '100'))
OCR_MAX_PAGES = int(os.environ.get('OCR_MAX_PAGES', '50'))
OCR_DPI = int(os.environ.get('OCR_DPI', '200'))
OCR_LANG = os.environ.get('OCR_LANG', 'spa')

ALLOWED_EXTENSIONS = {'pdf', 'docx'}

app.config['MAX_CONTENT_LENGTH'] = MAX_UPLOAD_MB * 1024 * 1024

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

REGEX_PATTERNS_FILE = '/app/regex_patterns.json'

_inflight_lock = threading.Lock()
_inflight_requests = 0
_login_attempts = {}
redis_client = None
redis_available = False
session_ext = Session()


def init_redis_client():
    global redis_client, redis_available
    try:
        client = redis.Redis.from_url(
            REDIS_URL,
            decode_responses=False,
            socket_connect_timeout=2,
            socket_timeout=2,
        )
        client.ping()
        redis_client = client
        redis_available = True
        logger.info('Redis conectado en %s', REDIS_URL)
    except redis.RedisError as e:
        redis_available = False
        redis_client = None
        logger.warning('Redis no disponible (%s). Se usa fallback local.', e)


def configure_session_backend():
    if SESSION_BACKEND == 'redis' and redis_available:
        app.config['SESSION_TYPE'] = 'redis'
        app.config['SESSION_REDIS'] = redis_client
        app.config['SESSION_PERMANENT'] = False
        app.config['SESSION_USE_SIGNER'] = True
        session_ext.init_app(app)
        logger.info('Sesiones configuradas en Redis')
    else:
        logger.info('Sesiones en cookie (backend local)')


def bootstrap_config_in_redis():
    if not redis_available:
        return
    try:
        existing = redis_client.get(REDIS_CONFIG_KEY)
        if existing:
            return
        try:
            with open(REGEX_PATTERNS_FILE, 'r', encoding='utf-8') as f:
                data = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            data = DEFAULT_PATTERNS_DATA
        redis_client.set(REDIS_CONFIG_KEY, json.dumps(data, ensure_ascii=False))
        logger.info('Config inicial cargada en Redis')
    except redis.RedisError:
        logger.warning('No se pudo bootstrapear config en Redis')


def validate_required_env():
    required = []
    if not app.config.get('SECRET_KEY'):
        required.append('FLASK_SECRET_KEY')
    if not ADMIN_PASS:
        required.append('ADMIN_PASS')
    if required:
        raise RuntimeError(
            f"Missing required environment variables: {', '.join(required)}"
        )


def cleanup_old_uploads():
    cutoff = time.time() - UPLOAD_TTL_SECONDS
    upload_dir = app.config['UPLOAD_FOLDER']
    try:
        for name in os.listdir(upload_dir):
            path = os.path.join(upload_dir, name)
            if not os.path.isfile(path):
                continue
            if os.path.getmtime(path) < cutoff:
                os.unlink(path)
    except OSError:
        logger.warning('No se pudo ejecutar limpieza de uploads antiguos')


def is_valid_upload_filename(filename):
    return bool(re.fullmatch(r'[0-9a-fA-F-]{36}\.(pdf|docx)', filename or ''))


def is_path_inside_uploads(path):
    upload_root = os.path.realpath(app.config['UPLOAD_FOLDER'])
    target = os.path.realpath(path)
    return target.startswith(upload_root + os.sep)


def _prune_login_attempts(now):
    stale = [ip for ip, ts in _login_attempts.items() if now - ts[-1] > LOGIN_WINDOW_SECONDS]
    for ip in stale:
        _login_attempts.pop(ip, None)


def is_login_rate_limited(ip):
    if redis_available:
        key = f'anonimizador:login:{ip}'
        try:
            count = redis_client.get(key)
            return int(count or 0) >= LOGIN_MAX_ATTEMPTS
        except redis.RedisError:
            pass
    now = time.time()
    _prune_login_attempts(now)
    attempts = _login_attempts.get(ip, [])
    attempts = [t for t in attempts if now - t <= LOGIN_WINDOW_SECONDS]
    _login_attempts[ip] = attempts
    return len(attempts) >= LOGIN_MAX_ATTEMPTS


def register_login_failure(ip):
    if redis_available:
        key = f'anonimizador:login:{ip}'
        try:
            pipe = redis_client.pipeline()
            pipe.incr(key)
            pipe.expire(key, LOGIN_WINDOW_SECONDS)
            pipe.execute()
            return
        except redis.RedisError:
            pass
    now = time.time()
    attempts = _login_attempts.get(ip, [])
    attempts.append(now)
    _login_attempts[ip] = attempts


validate_required_env()
init_redis_client()
configure_session_backend()
bootstrap_config_in_redis()


def _cleanup_loop():
    while True:
        time.sleep(60)
        try:
            cleanup_old_uploads()
        except Exception:
            logger.warning('Error en limpieza periódica de uploads')


cleanup_thread = threading.Thread(target=_cleanup_loop, daemon=True, name='cleanup-loop')
cleanup_thread.start()


def _inc_inflight():
    global _inflight_requests
    with _inflight_lock:
        _inflight_requests += 1
        return _inflight_requests


def _dec_inflight():
    global _inflight_requests
    with _inflight_lock:
        _inflight_requests = max(0, _inflight_requests - 1)
        return _inflight_requests


def _current_inflight():
    with _inflight_lock:
        return _inflight_requests


@app.before_request
def track_request_start():
    if request.path == '/ready':
        g._counted_inflight = False
        return
    g._counted_inflight = True
    _inc_inflight()


@app.after_request
def track_request_end(response):
    if getattr(g, '_counted_inflight', False):
        _dec_inflight()
        g._counted_inflight = False
    return response


@app.teardown_request
def track_request_teardown(_exc):
    if getattr(g, '_counted_inflight', False):
        _dec_inflight()
        g._counted_inflight = False

DEFAULT_PATTERNS_DATA = {
    "patterns": [
        {"pattern": r"\b\d{1,2}\.?\d{3}\.?\d{3}\b", "type": "dni_argentino"},
        {"pattern": r"\b\d{7,8}\b", "type": "dni_argentino"},
        {"pattern": r"(?:calle|av\.|avenida|domicilio|direcci[oó]n|pasaje|b[oó]u?le?vard|ruta|camino)\s+[a-záéíóúñ\s]+\d+", "type": "direccion"},
        {"pattern": r"\d+\s*(?:años|anios|años de edad)", "type": "edad"},
        {"pattern": r"\b(?:masculino|femenino|var[oó]n|mujer|hombre|femenina|masculina)\b", "type": "sexo"},
        {"pattern": r"(?:paciente|nombre|apellido|señor|señora|sr[a]?\.?)\s*:?\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+", "type": "nombre"},
        {"pattern": r"\b(?:[\w.-]+@[\w.-]+\.\w{2,})\b", "type": "email"},
        {"pattern": r"\b(?:abus\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:viol\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:fallec\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:homicid\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:femicid\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:lesion\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:amenaz\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:agred\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:imput\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:conden\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:deten\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:testig\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:denunci\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:perici\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:forens\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:cadav\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:autops\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:necrops\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:identif\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:document\w*)\b", "type": "sensible"},
        {"pattern": r"\b(?:expedient\w*)\b", "type": "sensible"},
    ],
    "prompt": (
        "Analiza este documento y determina TODAS las palabras o conjuntos de palabras "
        "que son datos personales o información judicial/jurídica importante.\n\n"
        "Busca ESPECÍFICAMENTE:\n"
        "- Nombres y apellidos completos de personas\n"
        "- DNI, CUIT, CUIL, pasaporte, cualquier número de identificación\n"
        "- Domicilios o direcciones postales completas\n"
        "- Edades (números seguidos de 'años')\n"
        "- Sexo o género de la persona\n"
        "- Teléfonos, celulares, emails\n"
        "- Cuentas bancarias, CBUs, números de tarjeta\n"
        "- Montos de dinero: cifras en números Y TAMBIÉN cifras escritas en palabras\n"
        "  (ej: 'cuarenta y cuatro millones de pesos', 'dos mil quinientos dólares')\n"
        "- Cualquier cifra o valor descrito en palabras o números que sea relevante\n"
        "- Fechas de nacimiento, fechas importantes\n"
        "- Nombres de empresas, juzgados, organismos\n"
        "- Números de expediente, causas judiciales\n\n"
        "IMPORTANTE: al final de tu respuesta, incluí un bloque JSON con el "
        "siguiente formato, y SOLO ese bloque JSON al final:\n\n"
        '```json\n'
        '[{"word": "el texto exacto como aparece", "type": "categoria"}, ...]\n'
        '```\n\n'
        "TEXT:\n\"\"\"\n{text}\n\"\"\""
    )
}


def load_regex_config():
    if redis_available:
        try:
            raw = redis_client.get(REDIS_CONFIG_KEY)
            if raw:
                if isinstance(raw, bytes):
                    raw = raw.decode('utf-8')
                data = json.loads(raw)
                logger.info('Config regex cargada desde Redis')
                return data
        except (redis.RedisError, json.JSONDecodeError):
            logger.warning('No se pudo leer config desde Redis, usando fallback')
    try:
        with open(REGEX_PATTERNS_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        logger.info('Config regex cargada desde archivo')
        return data
    except (FileNotFoundError, json.JSONDecodeError):
        logger.info('Usando config regex por defecto')
        return DEFAULT_PATTERNS_DATA


def get_pii_patterns():
    config = load_regex_config()
    return [(p['pattern'], p['type']) for p in config.get('patterns', [])]


def get_opencode_prompt():
    config = load_regex_config()
    return config.get('prompt', DEFAULT_PATTERNS_DATA['prompt'])


def save_regex_config(
    patterns,
    prompt,
    model_url=None,
    model_name=None,
    opencode_command=None,
    api_key=None,
):
    data = {"patterns": patterns, "prompt": prompt}
    if model_url is not None:
        data["model_url"] = model_url
    if model_name is not None:
        data["model_name"] = model_name
    if opencode_command is not None:
        data["opencode_command"] = opencode_command
    elif "opencode_command" in load_regex_config():
        data["opencode_command"] = load_regex_config().get("opencode_command")
    if api_key is not None:
        data["api_key"] = api_key
    elif "api_key" in load_regex_config():
        data["api_key"] = load_regex_config().get("api_key")
    if redis_available:
        try:
            redis_client.set(REDIS_CONFIG_KEY, json.dumps(data, ensure_ascii=False))
            logger.info('Config regex guardada en Redis (%d patrones)', len(patterns))
        except redis.RedisError:
            logger.warning('No se pudo guardar config en Redis, guardando solo en archivo')
    with open(REGEX_PATTERNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info('Config regex guardada (%d patrones)', len(patterns))


def get_model_config():
    config = load_regex_config()
    return {
        'model_url': config.get('model_url', os.environ.get('OPENAI_BASE_URL', '')),
        'model_name': config.get('model_name', os.environ.get('MODEL_NAME', '')),
        'opencode_command': config.get(
            'opencode_command',
            'opencode run "{message}" --model opencode/{model} --dangerously-skip-permissions --file {file}'
        ),
        'api_key': config.get('api_key', os.environ.get('OPENAI_API_KEY', '')),
    }


def get_opencode_command_template():
    cfg = get_model_config()
    return cfg['opencode_command']


def get_current_model():
    cfg = get_model_config()
    return cfg['model_name'] or MODEL_NAME


def get_current_base_url():
    cfg = get_model_config()
    return cfg['model_url'] or os.environ.get('OPENAI_BASE_URL', '')


def get_current_api_key():
    cfg = get_model_config()
    return cfg['api_key'] or os.environ.get('OPENAI_API_KEY', '')


def is_local_model_provider():
    model_url = (get_current_base_url() or '').strip().lower()
    if not model_url:
        return False
    local_hosts = (
        'localhost',
        '127.0.0.1',
        '0.0.0.0',
        'host.docker.internal',
        'ollama',
    )
    return any(host in model_url for host in local_hosts)


def local_provider_healthcheck_url():
    base = (get_current_base_url() or '').strip()
    if not base:
        return None
    if '/api/' in base:
        return base.rstrip('/')
    return base.rstrip('/') + '/api/tags'


def is_local_provider_available():
    if not is_local_model_provider():
        return True
    target = local_provider_healthcheck_url()
    if not target:
        return False
    try:
        req = Request(target, method='GET')
        with urlopen(req, timeout=3) as resp:
            return resp.status == 200
    except (URLError, TimeoutError, ValueError):
        return False


def acquire_local_inference_slot(wait_seconds=None):
    if not redis_available or not is_local_model_provider() or LOCAL_INFERENCE_MAX <= 0:
        return None, None

    token = str(uuid.uuid4())
    wait_limit = LOCAL_INFERENCE_WAIT_SECONDS if wait_seconds is None else wait_seconds
    deadline = time.time() + max(0, wait_limit)
    slot_prefix = 'anonimizador:local_inference:slot'

    while time.time() <= deadline:
        for slot_num in range(1, LOCAL_INFERENCE_MAX + 1):
            slot_key = f'{slot_prefix}:{slot_num}'
            try:
                ok = redis_client.set(
                    slot_key,
                    token,
                    nx=True,
                    ex=max(30, LOCAL_INFERENCE_SLOT_TTL_SECONDS),
                )
            except redis.RedisError:
                logger.warning('Redis error tomando slot de inferencia local')
                return None, None
            if ok:
                return slot_key, token
        time.sleep(max(0.2, LOCAL_INFERENCE_POLL_SECONDS))

    return None, token


def release_local_inference_slot(slot_key, token):
    if not redis_available or not slot_key or not token:
        return
    try:
        val = redis_client.get(slot_key)
        if val and val.decode('utf-8') == token:
            redis_client.delete(slot_key)
    except redis.RedisError:
        logger.warning('Redis error liberando slot de inferencia local')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


def extract_text_ocr(filepath):
    segments = []
    try:
        logger.info('Convirtiendo PDF a imagenes para OCR (dpi=%d, lang=%s)', OCR_DPI, OCR_LANG)
        images = pdf2image.convert_from_path(filepath, dpi=OCR_DPI)
        for i, image in enumerate(images):
            if i >= OCR_MAX_PAGES:
                logger.warning('Limite de paginas OCR alcanzado (%d)', OCR_MAX_PAGES)
                break
            text = pytesseract.image_to_string(image, lang=OCR_LANG)
            if text.strip():
                segments.append({'type': 'paragraph', 'text': text.strip()})
    except Exception as e:
        logger.error('Error en OCR: %s', e)
    return segments


def extract_text_pdf(filepath):
    segments = []
    try:
        with pdfplumber.open(filepath) as pdf:
            for page in pdf.pages:
                try:
                    lines = page.extract_text_lines() or []
                    for block in lines:
                        raw = block.get('text', '').strip()
                        if not raw:
                            continue
                        x0 = block.get('x0', 0)
                        top = block.get('top', 0)
                        is_short = len(raw) < 90
                        high_on_page = isinstance(top, (int, float)) and top < 60
                        indented = isinstance(x0, (int, float)) and (x0 > 50)
                        if is_short and (high_on_page or indented):
                            seg_type = 'title'
                        else:
                            seg_type = 'paragraph'
                        segments.append({'type': seg_type, 'text': raw})
                except Exception:
                    raw = page.extract_text() or ''
                    for line in raw.split('\n'):
                        line = line.strip()
                        if line:
                            segments.append({'type': 'paragraph', 'text': line})
    except Exception:
        pass
    if not segments:
        try:
            with pdfplumber.open(filepath) as pdf:
                for page in pdf.pages:
                    raw = page.extract_text() or ''
                    for line in raw.split('\n'):
                        line = line.strip()
                        if line:
                            segments.append({'type': 'paragraph', 'text': line})
        except Exception:
            pass
    
    total_text_len = sum(len(s['text']) for s in segments)
    if total_text_len < 100:
        logger.info('PDF con poco texto extraible (%d chars). Iniciando fallback OCR.', total_text_len)
        ocr_segments = extract_text_ocr(filepath)
        if ocr_segments:
            return ocr_segments, True
    return segments, False


def extract_text_docx(filepath):
    doc = docx.Document(filepath)
    segments = []
    for para in doc.paragraphs:
        text = para.text.strip()
        if not text:
            continue
        style_name = para.style.name.lower() if para.style else ''
        if 'heading' in style_name or 'title' in style_name:
            seg_type = 'title'
        elif 'list' in style_name:
            seg_type = 'list'
        else:
            seg_type = 'paragraph'
        segments.append({'type': seg_type, 'text': text})
    for table in doc.tables:
        for row in table.rows:
            row_texts = []
            for cell in row.cells:
                cell_text = ' '.join(p.text.strip() for p in cell.paragraphs if p.text.strip())
                if cell_text:
                    row_texts.append(cell_text)
            if row_texts:
                segments.append({'type': 'paragraph', 'text': ' | '.join(row_texts)})
    return segments


def extract_text(filepath):
    ext = filepath.rsplit('.', 1)[1].lower()
    if ext == 'pdf':
        return extract_text_pdf(filepath)
    elif ext == 'docx':
        return extract_text_docx(filepath), False
    return [], False


def segments_to_plaintext(segments):
    return '\n\n'.join(s['text'] for s in segments)


def get_model_id():
    model_name = get_current_model()
    parts = model_name.replace('\\', '/').split('/')
    return parts[-1] if len(parts) > 1 else parts[0]


def parse_pii_from_output(raw_output):
    text = re.sub(r'\x1b\[[0-9;]*m', '', raw_output or '').strip()

    candidates = []
    fenced = re.search(r'```(?:json)?\s*(\[.*?\])\s*```', text, re.DOTALL)
    if fenced:
        candidates.append(fenced.group(1))

    inline_array = re.search(r'(\[\s*\{.*\}\s*\])', text, re.DOTALL)
    if inline_array:
        candidates.append(inline_array.group(1))

    first_bracket = text.find('[')
    last_bracket = text.rfind(']')
    if first_bracket != -1 and last_bracket != -1 and last_bracket > first_bracket:
        candidates.append(text[first_bracket:last_bracket + 1])

    for candidate in candidates:
        try:
            parsed = json.loads(candidate)
            if isinstance(parsed, list):
                cleaned = []
                for item in parsed:
                    if isinstance(item, dict) and 'word' in item and 'type' in item:
                        word = str(item.get('word', '')).strip()
                        ptype = str(item.get('type', 'other')).strip() or 'other'
                        if word:
                            cleaned.append({'word': word, 'type': ptype})
                if cleaned:
                    return cleaned
        except json.JSONDecodeError:
            continue

    pair_matches = re.findall(
        r'\{\s*["\']word["\']\s*:\s*["\']([^"\']+)["\']\s*,\s*["\']type["\']\s*:\s*["\']([^"\']+)["\']\s*\}',
        text,
        re.IGNORECASE,
    )
    if pair_matches:
        return [{'word': w.strip(), 'type': t.strip() or 'other'} for w, t in pair_matches if w.strip()]

    table_lines = [ln.strip() for ln in text.splitlines() if '|' in ln]
    extracted = []
    for ln in table_lines:
        if ln.startswith('|---'):
            continue
        cols = [c.strip(' `') for c in ln.split('|') if c.strip()]
        if len(cols) >= 2 and cols[0].lower() not in ('palabra', 'word'):
            extracted.append({'word': cols[0], 'type': cols[1] or 'other'})
    if extracted:
        return extracted

    return []


def call_opencode_for_pii(text, wait_seconds=None):
    model_id = get_model_id()
    prompt_template = get_opencode_prompt()
    prompt = prompt_template.replace('{text}', text)

    combined_input = (
        "INSTRUCCIONES:\n" + prompt + "\n\n"
        "NO HAGAS PREGUNTAS. NO SUGIERAS ACCIONES. Solo devolvé el JSON con "
        "los datos detectados. No escribas nada más que el JSON."
    )

    logger.info('Enviando texto a opencode (%d chars)', len(text))

    with tempfile.NamedTemporaryFile(
        mode='w', suffix='.txt', delete=False, dir='/app/uploads'
    ) as f:
        f.write(combined_input)
        tmp_path = f.name

    short_msg = 'Analiza el archivo adjunto y seguí las instrucciones'
    command_template = (get_opencode_command_template() or '').strip()
    if not command_template:
        command_template = 'opencode run "{message}" --model opencode/{model} --dangerously-skip-permissions --file {file}'
    command_filled = (
        command_template
        .replace('{message}', short_msg)
        .replace('{model}', model_id)
        .replace('{file}', tmp_path)
    )
    queue_notice = None
    slot_key = None
    slot_token = None

    if is_local_model_provider() and not is_local_provider_available():
        queue_notice = 'Proveedor local no disponible en este momento.'
        logger.warning(queue_notice)
        return [], queue_notice, queue_notice, 'unavailable'

    if is_local_model_provider() and redis_available and LOCAL_INFERENCE_MAX > 0:
        logger.info(
            'Proveedor local detectado. Intentando tomar slot de inferencia (max=%d)',
            LOCAL_INFERENCE_MAX,
        )
        started_wait = time.time()
        slot_key, slot_token = acquire_local_inference_slot(wait_seconds=wait_seconds)
        waited = int(time.time() - started_wait)
        if not slot_key:
            queue_notice = (
                'Proveedor local ocupado. No se obtuvo slot de inferencia dentro del tiempo de espera.'
            )
            logger.warning(queue_notice)
            return [], queue_notice, queue_notice, 'busy'
        if waited > 0:
            queue_notice = f'Inferencia local en cola: espera aproximada {waited}s antes de procesar.'
            logger.info(queue_notice)

    try:
        logger.info('Ejecutando comando opencode personalizado')
        cmd_args = shlex.split(command_filled)
        run_env = {**os.environ, 'HOME': os.environ.get('HOME', '/root')}
        selected_api_key = (get_current_api_key() or '').strip()
        if selected_api_key:
            run_env['OPENAI_API_KEY'] = selected_api_key
        result = subprocess.run(
            cmd_args,
            capture_output=True,
            text=True,
            timeout=120,
            env=run_env,
        )

        full_output = (result.stdout or '') + '\n' + (result.stderr or '')
        full_output = full_output.strip()
        logger.info('Respuesta opencode: %d chars', len(full_output))

        parsed = parse_pii_from_output(full_output)
        if parsed:
            logger.info('PII detectadas por IA: %d keywords', len(parsed))
            return parsed, full_output, queue_notice, 'ok'

        logger.warning('No se pudo parsear JSON del output de opencode. Preview: %s', full_output[:220])
        return [], full_output, queue_notice, 'ok'
    except subprocess.TimeoutExpired:
        logger.error('Timeout al ejecutar opencode (120s)')
        return [], 'Error: Timeout al ejecutar opencode', queue_notice, 'timeout'
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        logger.error('Error ejecutando opencode: %s', e)
        return [], f'Error: {str(e)}', queue_notice, 'error'
    finally:
        release_local_inference_slot(slot_key, slot_token)
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def run_detection_pipeline(segments, wait_seconds=None):
    plaintext = segments_to_plaintext(segments)
    logger.info('Texto plano: %d chars', len(plaintext))

    pii_keywords, reasoning_output, queue_notice, ai_status = call_opencode_for_pii(
        plaintext,
        wait_seconds=wait_seconds,
    )
    logger.info('IA devolvió %d keywords (status=%s)', len(pii_keywords), ai_status)

    default_keywords, default_positions = detect_default_pii(segments)
    logger.info('Regex detectó %d keywords / %d posiciones', len(default_keywords), len(default_positions))

    ai_positions = find_word_positions(segments, pii_keywords)
    logger.info('Posiciones IA: %d', len(ai_positions))

    seen_ranges = set()
    merged_positions = []
    for pos in default_positions + ai_positions:
        key = (pos['segment'], pos['start'], pos['end'], pos['word'])
        if key not in seen_ranges:
            seen_ranges.add(key)
            merged_positions.append(pos)

    merged_positions.sort(key=lambda p: (p['segment'], p['start']))
    logger.info('Total posiciones fusionadas: %d', len(merged_positions))

    return {
        'keywords': pii_keywords,
        'default_keywords': default_keywords,
        'positions': merged_positions,
        'reasoning': reasoning_output,
        'queue_notice': queue_notice,
        'ai_status': ai_status,
        'analysis_mode': 'full' if ai_status == 'ok' else 'regex_only',
        'ai_positions': ai_positions,
    }


def normalize_text(text):
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


def detect_default_pii(segments):
    default_keywords_set = {}
    positions = []
    patterns = get_pii_patterns()

    for seg_idx, seg in enumerate(segments):
        text = seg['text']
        lower_text = text.lower()

        for pattern, ptype in patterns:
            for match in re.finditer(pattern, text, re.IGNORECASE):
                word = match.group()
                normalized = normalize_text(word).lower()
                key = f'{normalized}|{ptype}'
                if key not in default_keywords_set:
                    default_keywords_set[key] = {'word': word, 'type': ptype}
                positions.append({
                    'segment': seg_idx,
                    'start': match.start(),
                    'end': match.end(),
                    'word': word,
                    'type': ptype
                })

    return list(default_keywords_set.values()), positions


def find_word_positions(segments, keywords):
    positions = []
    for seg_idx, seg in enumerate(segments):
        text = seg['text']
        norm_text = normalize_text(text).lower()
        for kw in keywords:
            norm_kw = normalize_text(kw['word']).lower()
            start = 0
            while True:
                idx = norm_text.find(norm_kw, start)
                if idx == -1:
                    break
                word_match = text[idx:idx + len(kw['word'])]
                positions.append({
                    'segment': seg_idx,
                    'start': idx,
                    'end': idx + len(kw['word']),
                    'word': word_match,
                    'type': kw.get('type', 'other')
                })
                start = idx + 1
    return positions


def replace_normalized(text, kw_word, replacement):
    norm_text = normalize_text(text).lower()
    norm_kw = normalize_text(kw_word).lower()
    if not norm_kw:
        return text
    start = 0
    while True:
        idx = norm_text.find(norm_kw, start)
        if idx == -1:
            break
        orig_text = text[idx:idx + len(kw_word)]
        accented = unicodedata.normalize('NFKD', orig_text)
        has_combining = any(unicodedata.combining(c) for c in accented)
        match_len = len(accented) if has_combining else len(kw_word)
        text = text[:idx] + replacement + text[idx + match_len:]
        norm_text = normalize_text(text).lower()
        start = idx + len(replacement)
    return text


def anonymize_docx(filepath, keywords, replacement='[REDACTADO]'):
    doc = Document(filepath)

    def replace_text(text):
        out = text
        for kw in keywords:
            if normalize_text(kw['word']).lower() in normalize_text(out).lower():
                out = replace_normalized(out, kw['word'], replacement)
        return out

    def keep_run_style(paragraph):
        if paragraph.runs:
            src = paragraph.runs[0]
            return {
                'name': src.font.name,
                'size': src.font.size,
                'bold': src.font.bold,
                'italic': src.font.italic,
                'underline': src.font.underline,
                'color': src.font.color.rgb,
            }
        return None

    def apply_run_style(run, style):
        if not style:
            return
        run.font.name = style['name']
        run.font.size = style['size']
        run.font.bold = style['bold']
        run.font.italic = style['italic']
        run.font.underline = style['underline']
        run.font.color.rgb = style['color']

    def anonymize_paragraphs(paragraphs):
        for para in paragraphs:
            original = para.text
            if not original:
                continue
            anonymized = replace_text(original)
            if anonymized == original:
                continue
            style = keep_run_style(para)
            para.text = anonymized
            if para.runs:
                apply_run_style(para.runs[0], style)

    anonymize_paragraphs(doc.paragraphs)
    for table in doc.tables:
        for row in table.rows:
            for cell in row.cells:
                anonymize_paragraphs(cell.paragraphs)

    buf = BytesIO()
    doc.save(buf)
    buf.seek(0)
    return buf


def get_pdf_fonts():
    import glob
    candidates = glob.glob('/usr/share/fonts/truetype/dejavu/DejaVuSans*.ttf')
    regular = None
    bold = None
    for f in sorted(candidates):
        basename = f.split('/')[-1]
        if basename == 'DejaVuSans.ttf':
            regular = f
        elif basename == 'DejaVuSans-Bold.ttf':
            bold = f
    return regular, bold, None


def anonymize_pdf(segments, keywords, replacement='[REDACTADO]', title='Documento Anonimizado'):
    pdf = FPDF(format='A4')
    pdf.set_auto_page_break(auto=True, margin=18)
    pdf.set_margins(18, 18, 18)
    pdf.add_page()

    regular_font, bold_font, _ = get_pdf_fonts()
    has_dejavu = regular_font is not None

    if has_dejavu:
        pdf.add_font('DejaVuSans', '', regular_font, uni=True)
        pdf.add_font('DejaVuSans', 'B', bold_font, uni=True)

    if has_dejavu:
        pdf.set_font('DejaVuSans', 'B', 15)
    else:
        pdf.set_font('Helvetica', 'B', 15)
    pdf.multi_cell(0, 8, title)
    pdf.ln(2)

    for seg in segments:
        text = seg['text']
        for kw in keywords:
            if normalize_text(kw['word']).lower() in normalize_text(text).lower():
                text = replace_normalized(text, kw['word'], replacement)

        if has_dejavu:
            if seg['type'] == 'title':
                pdf.set_font('DejaVuSans', 'B', 13)
            elif seg['type'] == 'list':
                pdf.set_font('DejaVuSans', '', 11)
            else:
                pdf.set_font('DejaVuSans', '', 11)
        else:
            if seg['type'] == 'title':
                pdf.set_font('Helvetica', 'B', 13)
            elif seg['type'] == 'list':
                pdf.set_font('Helvetica', '', 11)
            else:
                pdf.set_font('Helvetica', '', 11)

        if seg['type'] == 'list':
            text = f'- {text}'

        line_h = 6.6 if seg['type'] == 'paragraph' else 7.2
        pdf.multi_cell(0, line_h, text)
        if seg['type'] == 'title':
            pdf.ln(2.5)
        else:
            pdf.ln(1.4)

    buf = BytesIO()
    pdf.output(buf)
    buf.seek(0)
    return buf


@app.route('/')
def index():
    return render_template('index.html')


@app.route('/ready', methods=['GET'])
def ready():
    inflight = _current_inflight()
    busy = inflight >= READY_MAX_INFLIGHT
    payload = {
        'ready': not busy,
        'busy': busy,
        'inflight': inflight,
        'max_inflight': READY_MAX_INFLIGHT,
    }
    return (jsonify(payload), 200) if not busy else (jsonify(payload), 503)


@app.route('/upload', methods=['POST'])
def upload():
    logger.info('--- Nuevo upload ---')
    cleanup_old_uploads()
    if 'file' not in request.files:
        return jsonify({'error': 'No file provided'}), 400
    file = request.files['file']
    if not file.filename or not allowed_file(file.filename):
        return jsonify({'error': 'Invalid file type. Only PDF and DOCX allowed'}), 400

    ext = file.filename.rsplit('.', 1)[1].lower()
    uid = str(uuid.uuid4())
    filename = f'{uid}.{ext}'
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    file.save(filepath)
    logger.info('Archivo guardado: %s (%s)', filename, ext)

    segments, used_ocr = extract_text(filepath)
    if not segments:
        return jsonify({'error': 'Could not extract text from this document'}), 400
    logger.info('Texto extraído: %d segmentos', len(segments))

    result = run_detection_pipeline(segments)
    logger.info('--- Upload completado ---')

    return jsonify({
        'filename': filename,
        'segments': segments,
        'keywords': result['keywords'],
        'default_keywords': result['default_keywords'],
        'positions': result['positions'],
        'reasoning': result['reasoning'],
        'queue_notice': result['queue_notice'],
        'ai_status': result['ai_status'],
        'analysis_mode': result['analysis_mode'],
        'used_ocr': used_ocr,
    })


@app.route('/reanalyze-ai', methods=['POST'])
def reanalyze_ai():
    cleanup_old_uploads()
    data = request.get_json() or {}
    filename = data.get('filename', '')
    if not is_valid_upload_filename(filename):
        return jsonify({'error': 'Invalid filename'}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not is_path_inside_uploads(filepath) or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    segments, used_ocr = extract_text(filepath)
    if not segments:
        return jsonify({'error': 'Could not extract text from this document'}), 400

    result = run_detection_pipeline(segments, wait_seconds=0)
    status_code = 202 if result['ai_status'] in ('busy', 'unavailable') else 200
    return jsonify({
        'filename': filename,
        'keywords': result['keywords'],
        'default_keywords': result['default_keywords'],
        'positions': result['positions'],
        'ai_positions': result['ai_positions'],
        'reasoning': result['reasoning'],
        'queue_notice': result['queue_notice'],
        'ai_status': result['ai_status'],
        'analysis_mode': result['analysis_mode'],
        'used_ocr': used_ocr,
    }), status_code


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/uploads/<filename>')
@admin_required
def uploaded_file(filename):
    if not is_valid_upload_filename(filename):
        return jsonify({'error': 'Invalid filename'}), 400
    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not is_path_inside_uploads(filepath) or not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/export', methods=['POST'])
def export():
    logger.info('--- Export solicitado ---')
    cleanup_old_uploads()
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    filename = data.get('filename')
    keywords = data.get('keywords', [])
    output_format = data.get('format', 'docx')
    replacement = data.get('replacement', '[REDACTADO]')

    if not filename:
        return jsonify({'error': 'No filename provided'}), 400

    if not is_valid_upload_filename(filename):
        return jsonify({'error': 'Invalid filename'}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
    if not is_path_inside_uploads(filepath):
        return jsonify({'error': 'Invalid path'}), 400
    if not os.path.exists(filepath):
        return jsonify({'error': 'File not found'}), 404

    ext = filename.rsplit('.', 1)[1].lower()

    if ext == 'pdf' and output_format == 'docx':
        return jsonify({'error': 'No se puede exportar PDF a DOCX. Usá formato PDF.'}), 400

    kw_entries = [{'word': kw['word'], 'type': kw.get('type', 'other')}
                  for kw in keywords]
    logger.info('Exportando %s con %d keywords a reemplazar (formato: %s)', filename, len(kw_entries), output_format)

    if output_format == 'docx':
        buf = anonymize_docx(filepath, kw_entries, replacement)
        logger.info('Export DOCX completado')
        try:
            os.unlink(filepath)
        except OSError:
            pass
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument'
                      '.wordprocessingml.document',
            as_attachment=True,
            download_name=f'anonimizado_{filename.replace(".pdf", ".docx")}'
        )
    elif output_format == 'pdf':
        segments, _ = extract_text(filepath)
        buf = anonymize_pdf(segments, kw_entries, replacement,
                           f'Anonimizado - {filename}')
        logger.info('Export PDF completado')
        try:
            os.unlink(filepath)
        except OSError:
            pass
        return send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'anonimizado_{filename.replace(".docx", ".pdf")}'
        )

    return jsonify({'error': 'Unsupported format. Use docx or pdf'}), 400


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    ip = request.headers.get('X-Forwarded-For', request.remote_addr or 'unknown').split(',')[0].strip()
    if is_login_rate_limited(ip):
        return jsonify({'error': 'Too many attempts. Try again later.'}), 429
    user = data.get('user', '')
    password = data.get('password', '')
    if hmac.compare_digest(str(user), str(ADMIN_USER)) and hmac.compare_digest(str(password), str(ADMIN_PASS)):
        session['admin_logged_in'] = True
        if redis_available:
            try:
                redis_client.delete(f'anonimizador:login:{ip}')
            except redis.RedisError:
                pass
        logger.info('Admin login exitoso')
        return jsonify({'ok': True})
    register_login_failure(ip)
    logger.warning('Intento de login admin fallido')
    return jsonify({'error': 'Credenciales inválidas'}), 401


@app.route('/admin/logout', methods=['POST'])
def admin_logout():
    session.pop('admin_logged_in', None)
    session.modified = True
    return jsonify({'ok': True})


@app.route('/admin/status', methods=['GET'])
def admin_status():
    return jsonify({'logged_in': session.get('admin_logged_in', False)})


@app.route('/admin/config', methods=['GET'])
@admin_required
def admin_get_config():
    config = load_regex_config()
    return jsonify({
        'patterns': config.get('patterns', []),
        'prompt': config.get('prompt', ''),
        'model_url': config.get('model_url', os.environ.get('OPENAI_BASE_URL', '')),
        'model_name': config.get('model_name', os.environ.get('MODEL_NAME', '')),
        'api_key': config.get('api_key', os.environ.get('OPENAI_API_KEY', '')),
        'opencode_command': config.get(
            'opencode_command',
            'opencode run "{message}" --model opencode/{model} --dangerously-skip-permissions --file {file}'
        ),
    })


def validate_config_patterns(patterns):
    if not isinstance(patterns, list):
        return 'patterns debe ser una lista'
    for i, p in enumerate(patterns):
        if not isinstance(p, dict):
            return f'patrón {i}: debe ser un objeto JSON'
        if 'pattern' not in p or 'type' not in p:
            return f'patrón {i}: requiere campos "pattern" y "type"'
        if not isinstance(p['pattern'], str) or not isinstance(p['type'], str):
            return f'patrón {i}: "pattern" y "type" deben ser strings'
        if len(p['pattern']) > 300:
            return f'patrón {i}: regex demasiado largo (máx 300 chars)'
        try:
            re.compile(p['pattern'])
        except re.error as e:
            return f'patrón {i}: regex inválido — {e}'
    return None


def validate_config_prompt(prompt):
    if not isinstance(prompt, str):
        return 'prompt debe ser un string'
    if len(prompt) > 10000:
        return 'prompt demasiado largo (máx 10000 chars)'
    return None


def validate_config_model_url(model_url):
    if model_url is None:
        return None
    if not isinstance(model_url, str):
        return 'model_url debe ser un string'
    if len(model_url) > 500:
        return 'model_url demasiado largo (máx 500 chars)'
    if model_url.strip():
        try:
            from urllib.parse import urlparse
            parsed = urlparse(model_url)
            if parsed.scheme not in ('http', 'https'):
                return 'model_url debe usar http o https'
            if not parsed.netloc:
                return 'model_url debe incluir un host válido'
        except Exception:
            return 'model_url no es una URL válida'
    return None


def validate_opencode_command(opencode_command):
    if opencode_command is None:
        return None
    if not isinstance(opencode_command, str):
        return 'opencode_command debe ser un string'
    if len(opencode_command) > 1000:
        return 'opencode_command demasiado largo (máx 1000 chars)'
    text = opencode_command.strip()
    if not text:
        return None
    if '{file}' not in text:
        return 'opencode_command debe incluir placeholder {file}'
    return None


def validate_config_api_key(api_key):
    if api_key is None:
        return None
    if not isinstance(api_key, str):
        return 'api_key debe ser un string'
    if len(api_key) > 500:
        return 'api_key demasiado larga (máx 500 chars)'
    return None


@app.route('/admin/config', methods=['POST'])
@admin_required
def admin_save_config():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    patterns = data.get('patterns', [])
    prompt = data.get('prompt', '')
    model_url = data.get('model_url')
    model_name = data.get('model_name')
    api_key = data.get('api_key')
    opencode_command = data.get('opencode_command')

    err = validate_config_patterns(patterns)
    if err:
        return jsonify({'error': err}), 400
    err = validate_config_prompt(prompt)
    if err:
        return jsonify({'error': err}), 400
    err = validate_config_model_url(model_url)
    if err:
        return jsonify({'error': err}), 400
    err = validate_opencode_command(opencode_command)
    if err:
        return jsonify({'error': err}), 400
    err = validate_config_api_key(api_key)
    if err:
        return jsonify({'error': err}), 400

    try:
        save_regex_config(patterns, prompt, model_url, model_name, opencode_command, api_key)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error('Error guardando config: %s', e)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=False)
