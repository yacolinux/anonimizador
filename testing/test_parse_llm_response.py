import json
from conftest import anon_app

def test_parse_empty_output():
    result = anon_app.parse_pii_from_output('')
    assert result == []

def test_parse_none_output():
    result = anon_app.parse_pii_from_output(None)
    assert result == []

def test_parse_only_whitespace():
    result = anon_app.parse_pii_from_output('   \n   ')
    assert result == []

def test_parse_fenced_json_block():
    output = 'Algun texto previo\n```json\n[{"word": "Juan Pérez", "type": "nombre"}]\n```\nTexto posterior'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'Juan Pérez'
    assert result[0]['type'] == 'nombre'

def test_parse_fenced_json_no_lang():
    output = '```\n[{"word": "30.123.456", "type": "dni"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == '30.123.456'

def test_parse_inline_json():
    output = 'Los datos son [{"word": "test@email.com", "type": "email"}] y eso es todo'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'test@email.com'

def test_parse_multiple_items():
    output = '```json\n[\n  {"word": "Juan Pérez", "type": "nombre"},\n  {"word": "30.123.456", "type": "dni"},\n  {"word": "Calle Falsa 123", "type": "direccion"}\n]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 3

def test_parse_ignores_missing_word_key():
    output = '```json\n[{"word": "Juan", "type": "nombre"}, {"notword": "xxxx", "type": "otro"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'Juan'

def test_parse_ignores_empty_word():
    output = '```json\n[{"word": "", "type": "nombre"}, {"word": "Juan", "type": "nombre"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'Juan'

def test_parse_non_json_output_returns_empty():
    output = 'No se detectaron datos personales en este documento.'
    result = anon_app.parse_pii_from_output(output)
    assert result == []

def test_parse_with_ansi_escape_codes():
    output = '\x1b[32m```json\x1b[0m\n\x1b[0m[{"word": "Juan", "type": "nombre"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1

def test_parse_pair_notation():
    output = 'Datos: {"word": "Juan Pérez", "type": "nombre"} and {"word": "30.123.456", "type": "dni"}'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 2

def test_parse_pair_notation_single_quotes():
    output = "Datos: {'word': 'Juan Pérez', 'type': 'nombre'}"
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1

def test_parse_table_format():
    output = '| Palabra | Tipo |\n|---|---|\n| Juan Pérez | nombre |\n| 30.123.456 | dni |'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 2

def test_parse_table_ignores_header():
    output = '| palabra | tipo |\n|---|---|\n| Juan Pérez | nombre |'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1

def test_parse_table_with_backticks():
    output = '| `Juan Pérez` | `nombre` |\n|---|---|'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1

def test_parse_malformed_json_does_not_crash():
    output = '```json\n[{word: "incompleto"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert isinstance(result, list)

def test_parse_fallback_to_bracket_extraction():
    output = 'Texto [{"word": "Juan", "type": "nombre"}] final'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1

def test_parse_extra_spaces_in_word():
    output = '```json\n[{"word": "  Juan Pérez  ", "type": "nombre"}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'Juan Pérez'

def test_parse_prioritizes_fenced_over_inline():
    output = '```json\n[{"word": "correcto", "type": "tipo"}]\n```\n[{"word": "incorrecto", "type": "tipo"}]'
    result = anon_app.parse_pii_from_output(output)
    assert len(result) == 1
    assert result[0]['word'] == 'correcto'

def test_parse_not_a_list_returns_empty():
    output = '```json\n{"nombre": "Juan", "edad": 30}\n```'
    result = anon_app.parse_pii_from_output(output)
    assert result == []

def test_parse_empty_list():
    output = '```json\n[]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert result == []

def test_parse_type_fallback_to_other():
    output = '```json\n[{"word": "Juan", "type": ""}]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert result[0]['type'] == 'other'


def test_parse_normalizes_common_alias_types():
    output = '```json\n[\n  {"word": "Claudio Perez", "type": "persona"},\n  {"word": "Av. Siempre Viva 742", "type": "domicilio"},\n  {"word": "usuario@test.com", "type": "mail"}\n]\n```'
    result = anon_app.parse_pii_from_output(output)
    assert result[0]['type'] == 'nombre'
    assert result[1]['type'] == 'direccion'
    assert result[2]['type'] == 'email'


def test_clean_opencode_inference_output_removes_migration_noise():
    raw = (
        'Performing one time database migration, may take a few minutes...\n'
        'sqlite-migration:done\n'
        'Database migration complete.\n'
        '[0m\n'
        '> build · deepseek-v4-flash-free\n'
        '[{"word": "Juan Perez", "type": "persona"}]\n'
    )
    cleaned = anon_app.clean_opencode_inference_output(raw)
    assert 'sqlite-migration' not in cleaned
    assert 'Database migration complete' not in cleaned
    assert '> build' not in cleaned
    assert 'Juan Perez' in cleaned
