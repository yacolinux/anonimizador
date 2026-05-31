from conftest import anon_app

def test_replace_simple_word():
    result = anon_app.replace_normalized('Hola Juan', 'Juan', '[REDACTADO]')
    assert result == 'Hola [REDACTADO]'

def test_replace_accented_word():
    result = anon_app.replace_normalized('El paciente es Pérez', 'Pérez', '[REDACTADO]')
    assert result == 'El paciente es [REDACTADO]'

def test_replace_accent_variant_search():
    result = anon_app.replace_normalized('El paciente es Perez', 'Pérez', '[REDACTADO]')
    assert result == 'El paciente es [REDACTADO]'

def test_replace_multiple_occurrences():
    result = anon_app.replace_normalized('Juan vino con Juan y Juan se fue', 'Juan', '[REDACTADO]')
    assert result == '[REDACTADO] vino con [REDACTADO] y [REDACTADO] se fue'

def test_replace_no_match():
    text = 'Hola mundo'
    result = anon_app.replace_normalized(text, 'Pérez', '[REDACTADO]')
    assert result == text

def test_replace_empty_text():
    result = anon_app.replace_normalized('', 'Juan', '[REDACTADO]')
    assert result == ''

def test_replace_empty_keyword():
    result = anon_app.replace_normalized('Hola', '', '[REDACTADO]')
    assert result == 'Hola'

def test_replace_with_empty_replacement():
    result = anon_app.replace_normalized('Hola Juan', 'Juan', '')
    assert result == 'Hola '

def test_replace_numbers():
    result = anon_app.replace_normalized('DNI 30.123.456', '30.123.456', '[REDACTADO]')
    assert result == 'DNI [REDACTADO]'

def test_replace_direccion():
    text = 'Vive en Calle San Martín 1234'
    result = anon_app.replace_normalized(text, 'Calle San Martín 1234', '[REDACTADO]')
    assert result == 'Vive en [REDACTADO]'

def test_replace_spanish_accent_in_word():
    result = anon_app.replace_normalized('Dirección: Pellegrini', 'Pellegrini', '[REDACTADO]')
    assert result == 'Dirección: [REDACTADO]'

def test_replace_partial_word_not_replaced():
    result = anon_app.replace_normalized('Juanito vino', 'Juan', '[REDACTADO]')
    assert result == '[REDACTADO]ito vino'

def test_replace_positional_correctness():
    text = 'Hola Juan, tu DNI es 30.123.456'
    result = anon_app.replace_normalized(text, 'Juan', '[REDACTADO]')
    assert result == 'Hola [REDACTADO], tu DNI es 30.123.456'

def test_replace_longer_replacement():
    text = 'Hola Juan'
    result = anon_app.replace_normalized(text, 'Juan', '[ANONIMIZADO]')
    assert result == 'Hola [ANONIMIZADO]'

def test_replace_shorter_replacement():
    text = 'Hola Juan Carlos'
    result = anon_app.replace_normalized(text, 'Juan Carlos', 'XXX')
    assert result == 'Hola XXX'

def test_replace_multiple_different_keywords():
    text = 'Paciente: Juan Pérez, DNI 30.123.456'
    result = anon_app.replace_normalized(text, 'Juan Pérez', '[REDACTADO]')
    result = anon_app.replace_normalized(result, '30.123.456', '[REDACTADO]')
    assert '[REDACTADO]' in result
    assert 'Juan Pérez' not in result
    assert '30.123.456' not in result

def test_replace_dni_con_puntos():
    text = 'DNI: 30.123.456 - CUIL: 20-30123456-7'
    result = anon_app.replace_normalized(text, '30.123.456', '[REDACTADO]')
    result = anon_app.replace_normalized(result, '20-30123456-7', '[REDACTADO]')
    assert '[REDACTADO]' in result
    assert '30.123.456' not in result
    assert '20-30123456-7' not in result

def test_replace_solapa_con_acento():
    text = 'María José'
    result = anon_app.replace_normalized(text, 'María José', '[REDACTADO]')
    assert result == '[REDACTADO]'

def test_replace_previene_loop_infinito():
    text = 'XXXX'
    result = anon_app.replace_normalized(text, 'XX', 'X')
    assert result == 'XX'

def test_replace_case_insensitive():
    text = 'Hola JUAN'
    result = anon_app.replace_normalized(text, 'Juan', '[REDACTADO]')
    assert result == 'Hola [REDACTADO]'