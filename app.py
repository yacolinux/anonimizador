import logging
import os
import re
import json
import uuid
import unicodedata
import subprocess
import tempfile
import threading
from io import BytesIO
from functools import wraps
from flask import session, g

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
app.config['SECRET_KEY'] = os.environ.get('FLASK_SECRET_KEY', 'dev-secret-key-change-in-prod')

MODEL_NAME = os.environ.get('MODEL_NAME', 'qwen/qwen3-30b-a3b')
ADMIN_USER = os.environ.get('ADMIN_USER', 'adminanon')
ADMIN_PASS = os.environ.get('ADMIN_PASS', 'IJGNF678')
READY_MAX_INFLIGHT = int(os.environ.get('READY_MAX_INFLIGHT', '2'))

ALLOWED_EXTENSIONS = {'pdf', 'docx'}

os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

REGEX_PATTERNS_FILE = '/app/regex_patterns.json'
MODEL_CONFIG_FILE = '/app/model_config.json'

_inflight_lock = threading.Lock()
_inflight_requests = 0


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


def save_regex_config(patterns, prompt, model_url=None, model_name=None):
    data = {"patterns": patterns, "prompt": prompt}
    if model_url is not None:
        data["model_url"] = model_url
    if model_name is not None:
        data["model_name"] = model_name
    with open(REGEX_PATTERNS_FILE, 'w', encoding='utf-8') as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
    logger.info('Config regex guardada (%d patrones)', len(patterns))


def get_model_config():
    config = load_regex_config()
    return {
        'model_url': config.get('model_url', os.environ.get('OPENAI_BASE_URL', '')),
        'model_name': config.get('model_name', os.environ.get('MODEL_NAME', ''))
    }


def get_current_model():
    cfg = get_model_config()
    return cfg['model_name'] or MODEL_NAME


def get_current_base_url():
    cfg = get_model_config()
    return cfg['model_url'] or os.environ.get('OPENAI_BASE_URL', '')


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS


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
    return segments


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
        return extract_text_docx(filepath)
    return []


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


def call_opencode_for_pii(text):
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

    try:
        logger.info('Ejecutando opencode run --model opencode/%s', model_id)
        result = subprocess.run(
            [
                'opencode', 'run', short_msg,
                '--model', f'opencode/{model_id}',
                '--dangerously-skip-permissions',
                '--file', tmp_path,
            ],
            capture_output=True,
            text=True,
            timeout=120,
            env={**os.environ, 'HOME': os.environ.get('HOME', '/root')}
        )

        full_output = (result.stdout or '') + '\n' + (result.stderr or '')
        full_output = full_output.strip()
        logger.info('Respuesta opencode: %d chars', len(full_output))

        parsed = parse_pii_from_output(full_output)
        if parsed:
            logger.info('PII detectadas por IA: %d keywords', len(parsed))
            return parsed, full_output

        logger.warning('No se pudo parsear JSON del output de opencode. Preview: %s', full_output[:220])
        return [], full_output
    except subprocess.TimeoutExpired:
        logger.error('Timeout al ejecutar opencode (120s)')
        return [], 'Error: Timeout al ejecutar opencode'
    except (json.JSONDecodeError, subprocess.CalledProcessError) as e:
        logger.error('Error ejecutando opencode: %s', e)
        return [], f'Error: {str(e)}'
    finally:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass


def normalize_text(text):
    nfkd = unicodedata.normalize('NFKD', text)
    return ''.join(c for c in nfkd if not unicodedata.combining(c))


DEFAULT_PII_PATTERNS = [
    (r'\b\d{1,2}\.?\d{3}\.?\d{3}\b', 'dni_argentino'),
    (r'\b\d{1,2}\.\d{3}\.\d{3}\b', 'dni_argentino'),
    (r'\b\d{7,8}\b', 'dni_argentino'),
    (r'(?:calle|av\.|avenida|domicilio|direcci[oó]n|pasaje|b[oó]u?le?vard|ruta|camino)\s+[a-záéíóúñ\s]+\d+', 'direccion'),
    (r'\d+\s*(?:años|anios|años de edad)', 'edad'),
    (r'\b(?:masculino|femenino|var[oó]n|mujer|hombre|femenina|masculina)\b', 'sexo'),
    (r'(?:paciente|nombre|apellido|señor|señora|sr[a]?\.?)\s*:?\s*[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñ]+)+', 'nombre'),
]


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

    segments = extract_text(filepath)
    if not segments:
        return jsonify({'error': 'Could not extract text from this document'}), 400
    logger.info('Texto extraído: %d segmentos', len(segments))

    plaintext = segments_to_plaintext(segments)
    logger.info('Texto plano: %d chars', len(plaintext))

    pii_keywords, reasoning_output = call_opencode_for_pii(plaintext)
    logger.info('IA devolvió %d keywords', len(pii_keywords))

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
    logger.info('--- Upload completado ---')

    return jsonify({
        'filename': filename,
        'segments': segments,
        'keywords': pii_keywords,
        'default_keywords': default_keywords,
        'positions': merged_positions,
        'reasoning': reasoning_output
    })


@app.route('/uploads/<filename>')
def uploaded_file(filename):
    return send_from_directory(app.config['UPLOAD_FOLDER'], filename)


@app.route('/export', methods=['POST'])
def export():
    logger.info('--- Export solicitado ---')
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400

    filename = data.get('filename')
    keywords = data.get('keywords', [])
    output_format = data.get('format', 'docx')
    replacement = data.get('replacement', '[REDACTADO]')

    if not filename:
        return jsonify({'error': 'No filename provided'}), 400

    filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
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
        return send_file(
            buf,
            mimetype='application/vnd.openxmlformats-officedocument'
                      '.wordprocessingml.document',
            as_attachment=True,
            download_name=f'anonimizado_{filename.replace(".pdf", ".docx")}'
        )
    elif output_format == 'pdf':
        segments = extract_text(filepath)
        buf = anonymize_pdf(segments, kw_entries, replacement,
                           f'Anonimizado - {filename}')
        logger.info('Export PDF completado')
        return send_file(
            buf,
            mimetype='application/pdf',
            as_attachment=True,
            download_name=f'anonimizado_{filename.replace(".docx", ".pdf")}'
        )

    return jsonify({'error': 'Unsupported format. Use docx or pdf'}), 400


def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('admin_logged_in'):
            return jsonify({'error': 'Unauthorized'}), 401
        return f(*args, **kwargs)
    return decorated


@app.route('/admin/login', methods=['POST'])
def admin_login():
    data = request.get_json()
    if not data:
        return jsonify({'error': 'No data provided'}), 400
    user = data.get('user', '')
    password = data.get('password', '')
    if user == ADMIN_USER and password == ADMIN_PASS:
        session['admin_logged_in'] = True
        logger.info('Admin login exitoso')
        return jsonify({'ok': True})
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
        'model_name': config.get('model_name', os.environ.get('MODEL_NAME', ''))
    })


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
    try:
        save_regex_config(patterns, prompt, model_url, model_name)
        return jsonify({'ok': True})
    except Exception as e:
        logger.error('Error guardando config: %s', e)
        return jsonify({'error': str(e)}), 500


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000, debug=True)
