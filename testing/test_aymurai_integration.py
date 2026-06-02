import json

from conftest import anon_app


def test_map_aymurai_label_to_type_known_values():
    assert anon_app.map_aymurai_label_to_type('NOMBRE') == 'nombre'
    assert anon_app.map_aymurai_label_to_type('GENERO') == 'sexo'
    assert anon_app.map_aymurai_label_to_type('LUGAR_DEL_HECHO') == 'direccion'
    assert anon_app.map_aymurai_label_to_type('DETALLE') == 'sensible'


def test_map_aymurai_label_to_type_unknown_fallback():
    assert anon_app.map_aymurai_label_to_type('ALGO_DESCONOCIDO') == 'other'


def test_extract_aymurai_label_payload_prefers_alt_fields():
    label = {
        'text': '12 de mayo',
        'start_char': 10,
        'end_char': 20,
        'attrs': {
            'aymurai_label': 'FECHA_DEL_HECHO',
            'aymurai_alt_text': '12/05/2024',
            'aymurai_alt_start_char': 12,
            'aymurai_alt_end_char': 22,
        }
    }
    payload = anon_app.extract_aymurai_label_payload(label)
    assert payload['word'] == '12/05/2024'
    assert payload['start'] == 12
    assert payload['end'] == 22
    assert payload['type'] == 'fecha'


def test_call_aymurai_for_segments_disabled_returns_empty(monkeypatch):
    monkeypatch.setattr(anon_app, 'USE_AYMURAI', False)
    keywords, positions = anon_app.call_aymurai_for_segments([
        {'type': 'paragraph', 'text': 'Paciente: Juan Pérez'}
    ])
    assert keywords == []
    assert positions == []


def test_call_aymurai_for_segments_maps_positions(monkeypatch):
    class FakeResponse:
        def __init__(self, payload):
            self.payload = payload

        def read(self):
            return json.dumps(self.payload).encode('utf-8')

        def __enter__(self):
            return self

        def __exit__(self, exc_type, exc, tb):
            return False

    def fake_urlopen(req, timeout=0):
        return FakeResponse({
            'document': 'Paciente: Juan Pérez',
            'labels': [
                {
                    'text': 'Juan Pérez',
                    'start_char': 10,
                    'end_char': 20,
                    'attrs': {
                        'aymurai_label': 'NOMBRE',
                    }
                }
            ]
        })

    monkeypatch.setattr(anon_app, 'USE_AYMURAI', True)
    monkeypatch.setattr(anon_app, 'AYMURAI_BASE_URL', 'http://aymurai:8899')
    monkeypatch.setattr(anon_app, 'urlopen', fake_urlopen)

    keywords, positions = anon_app.call_aymurai_for_segments([
        {'type': 'paragraph', 'text': 'Paciente: Juan Pérez'}
    ])

    assert keywords == [{'word': 'Juan Pérez', 'type': 'nombre'}]
    assert len(positions) == 1
    assert positions[0]['segment'] == 0
    assert positions[0]['word'] == 'Juan Pérez'
    assert positions[0]['type'] == 'nombre'
