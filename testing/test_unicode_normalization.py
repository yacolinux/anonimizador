from conftest import anon_app

def test_normalize_text_removes_accent():
    assert anon_app.normalize_text('Pérez') == 'Perez'

def test_normalize_text_removes_multiple_accents():
    assert anon_app.normalize_text('María José') == 'Maria Jose'

def test_normalize_text_lowercase_preserved():
    text = 'Juan Carlos Martínez'
    result = anon_app.normalize_text(text)
    assert result == 'Juan Carlos Martinez'

def test_normalize_text_handles_unicode():
    result = anon_app.normalize_text('áéíóúñüÁÉÍÓÚÑÜ')
    assert result == 'aeiounuAEIOUNU'

def test_normalize_text_empty_string():
    assert anon_app.normalize_text('') == ''

def test_normalize_text_no_accent():
    assert anon_app.normalize_text('Hola mundo') == 'Hola mundo'

def test_normalize_text_dni_with_dots():
    assert anon_app.normalize_text('30.123.456') == '30.123.456'

def test_normalize_text_combination():
    original = 'Dni: 30.123.456 - Nombre: Máría Pérež'
    expected = 'Dni: 30.123.456 - Nombre: Maria Perez'
    assert anon_app.normalize_text(original) == expected

def test_find_word_positions_accent_insensitive():
    segments = [{'type': 'paragraph', 'text': 'El paciente es Pérez'}]
    keywords = [{'word': 'Pérez', 'type': 'nombre'}]
    positions = anon_app.find_word_positions(segments, keywords)
    assert len(positions) == 1
    assert positions[0]['word'] == 'Pérez'

def test_find_word_positions_accent_variant():
    segments = [{'type': 'paragraph', 'text': 'El paciente es Perez'}]
    keywords = [{'word': 'Pérez', 'type': 'nombre'}]
    positions = anon_app.find_word_positions(segments, keywords)
    assert len(positions) == 1
    assert positions[0]['word'] == 'Perez'

def test_find_word_positions_multiple_matches():
    segments = [{'type': 'paragraph', 'text': 'Juan vino con María y Juan se fue'}]
    keywords = [{'word': 'Juan', 'type': 'nombre'}]
    positions = anon_app.find_word_positions(segments, keywords)
    assert len(positions) == 2

def test_find_word_positions_no_match():
    segments = [{'type': 'paragraph', 'text': 'Hola mundo'}]
    keywords = [{'word': 'Pérez', 'type': 'nombre'}]
    positions = anon_app.find_word_positions(segments, keywords)
    assert len(positions) == 0

def test_detect_default_pii_normaliza_match():
    segments = [{'type': 'paragraph', 'text': 'Paciente: María Gómez'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    nombre_kw = [k for k in keywords if k['type'] == 'nombre']
    assert len(nombre_kw) > 0
    assert any('María' in kw['word'] for kw in nombre_kw)

def test_detect_default_pii_direccion_con_acento():
    segments = [{'type': 'paragraph', 'text': 'Dirección: Calle Pellegrini 888'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    direccion_kw = [k for k in keywords if k['type'] == 'direccion']
    assert len(direccion_kw) > 0

def test_normalize_nfkd_combined_chars():
    composed = '\u00e1'  # á as single code point
    decomposed = '\u0061\u0301'  # a + combining acute
    assert anon_app.normalize_text(composed) == 'a'
    assert anon_app.normalize_text(decomposed) == 'a'

def test_normalize_nfkd_identical():
    composed = 'María'
    decomposed = 'Mari\u0301a'
    assert anon_app.normalize_text(composed) == anon_app.normalize_text(decomposed) == 'Maria'