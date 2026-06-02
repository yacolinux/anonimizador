from conftest import anon_app

def test_get_pii_patterns_returns_list():
    patterns = anon_app.get_pii_patterns()
    assert isinstance(patterns, list)
    assert len(patterns) > 0
    for pattern, ptype in patterns:
        assert isinstance(pattern, str)
        assert isinstance(ptype, str)

def test_detect_default_pii_dni():
    segments = [{'type': 'paragraph', 'text': 'DNI 30.123.456 del paciente'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    assert any('30.123.456' in kw['word'] for kw in keywords)
    assert len(positions) > 0

def test_detect_default_pii_dni_simple():
    segments = [{'type': 'paragraph', 'text': 'Documento 30123456'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    assert any('30123456' in kw['word'] for kw in keywords)

def test_detect_default_pii_direccion():
    segments = [{'type': 'paragraph', 'text': 'Domicilio: Av. Corrientes 2567, CABA'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    direccion_kw = [k for k in keywords if k['type'] == 'direccion']
    assert len(direccion_kw) > 0

def test_detect_default_pii_edad():
    segments = [{'type': 'paragraph', 'text': 'Tiene 42 años de edad'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    edad_kw = [k for k in keywords if k['type'] == 'edad']
    assert len(edad_kw) > 0

def test_detect_default_pii_sexo():
    segments = [{'type': 'paragraph', 'text': 'Sexo: Femenino'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sexo_kw = [k for k in keywords if k['type'] == 'sexo']
    assert len(sexo_kw) > 0

def test_detect_default_pii_nombre():
    segments = [{'type': 'paragraph', 'text': 'Paciente: María Eugenia López'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    nombre_kw = [k for k in keywords if k['type'] == 'nombre']
    assert len(nombre_kw) > 0

def test_detect_default_pii_email():
    segments = [{'type': 'paragraph', 'text': 'Contacto: test@example.com'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    email_kw = [k for k in keywords if k['type'] == 'email']
    assert len(email_kw) > 0

def test_detect_default_pii_sin_coincidencias():
    segments = [{'type': 'paragraph', 'text': 'Este texto no tiene datos personales evidentes.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    assert len(keywords) == 0
    assert len(positions) == 0

def test_detect_default_pii_multiple_segmentos():
    segments = [
        {'type': 'title', 'text': 'Informe Médico'},
        {'type': 'paragraph', 'text': 'Paciente: Pedro García, DNI 40.123.456'},
        {'type': 'paragraph', 'text': 'Edad: 28 años, Sexo: Masculino'},
    ]
    keywords, positions = anon_app.detect_default_pii(segments)
    assert len(keywords) >= 4
    assert len(positions) >= 4

def test_detect_default_pii_positions_correctas():
    text = 'Paciente: Juan Pérez, DNI 30.123.456'
    segments = [{'type': 'paragraph', 'text': text}]
    keywords, positions = anon_app.detect_default_pii(segments)
    for pos in positions:
        assert pos['segment'] == 0
        assert pos['start'] >= 0
        assert pos['end'] > pos['start']
        assert text[pos['start']:pos['end']] == pos['word']

def test_detect_default_pii_sensible_words():
    segments = [
        {'type': 'paragraph', 'text': 'Hubo un abuso sexual contra la víctima.'},
        {'type': 'paragraph', 'text': 'Se investiga el homicidio.'},
        {'type': 'paragraph', 'text': 'La denuncia fue por violencia de género.'},
    ]
    keywords, positions = anon_app.detect_default_pii(segments)
    types = {k['type'] for k in keywords}
    assert 'sensible' in types
    assert any('abus' in kw['word'].lower() for kw in keywords)
    assert any('homicid' in kw['word'].lower() for kw in keywords)
    assert any('viol' in kw['word'].lower() for kw in keywords)

def test_detect_default_pii_direccion_calle():
    segments = [{'type': 'paragraph', 'text': 'Calle Rivadavia 1500, piso 3'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    direccion_kw = [k for k in keywords if k['type'] == 'direccion']
    assert len(direccion_kw) > 0

def test_detect_default_pii_cuil_pattern():
    segments = [{'type': 'paragraph', 'text': 'CUIL 20-30123456-7'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    assert len(keywords) >= 1

def test_detect_default_pii_sin_falsos_positivos():
    segments = [{'type': 'paragraph', 'text': 'El artículo 123 del código penal establece...'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    for kw in keywords:
        assert kw['type'] != 'dni_argentino'

def test_detect_default_pii_denuncia():
    segments = [{'type': 'paragraph', 'text': 'La denunciante manifestó haber sido víctima de amenazas.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sensible_kw = [k for k in keywords if k['type'] == 'sensible']
    assert any('denunci' in kw['word'].lower() for kw in sensible_kw)

def test_detect_default_pii_forense():
    segments = [{'type': 'paragraph', 'text': 'La pericia forense determinó lesiones graves.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sensible_kw = [k for k in keywords if k['type'] == 'sensible']
    assert any('forens' in kw['word'].lower() for kw in sensible_kw)

def test_detect_default_pii_imputado():
    segments = [{'type': 'paragraph', 'text': 'El imputado fue notificado de la condena.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sensible_kw = [k for k in keywords if k['type'] == 'sensible']
    assert any('imput' in kw['word'].lower() for kw in sensible_kw)
    assert any('conden' in kw['word'].lower() for kw in sensible_kw)

def test_detect_default_pii_fallecimiento():
    segments = [{'type': 'paragraph', 'text': 'Se constató el fallecimiento por autopsia.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sensible_kw = [k for k in keywords if k['type'] == 'sensible']
    assert any('fallec' in kw['word'].lower() for kw in sensible_kw)
    assert any('autops' in kw['word'].lower() for kw in sensible_kw)

def test_detect_default_pii_expediente():
    segments = [{'type': 'paragraph', 'text': 'El documento fue cargado al expediente digital.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    sensible_kw = [k for k in keywords if k['type'] == 'sensible']
    assert any('expedient' in kw['word'].lower() for kw in sensible_kw)


def test_detect_default_pii_juez_con_nombre():
    segments = [{'type': 'paragraph', 'text': 'Juez Claudio Pérez intervino en la audiencia.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    nombre_kw = [k for k in keywords if k['type'] == 'nombre']
    assert any('Juez Claudio Pérez' in kw['word'] for kw in nombre_kw)


def test_detect_default_pii_fiscalia():
    segments = [{'type': 'paragraph', 'text': 'La Fiscalía Federal N° 3 presentó el dictamen.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    fiscalia_kw = [k for k in keywords if k['type'] == 'fiscalia']
    assert len(fiscalia_kw) > 0


def test_detect_default_pii_ufi():
    segments = [{'type': 'paragraph', 'text': 'Interviene la UFI N° 7.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    fiscalia_kw = [k for k in keywords if k['type'] == 'fiscalia']
    assert any('UFI' in kw['word'] for kw in fiscalia_kw)


def test_detect_default_pii_matricula_tomo_folio():
    segments = [{'type': 'paragraph', 'text': 'Abogada T. 54 F. 233 patrocina a la actora.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    matricula_kw = [k for k in keywords if k['type'] == 'matricula_prof']
    assert len(matricula_kw) > 0


def test_detect_default_pii_generic_phone():
    segments = [{'type': 'paragraph', 'text': 'Contacto urgente: +54 11 4567-8901'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    telefono_kw = [k for k in keywords if k['type'] == 'telefono']
    assert len(telefono_kw) > 0


def test_detect_default_pii_generic_date():
    segments = [{'type': 'paragraph', 'text': 'La audiencia será el 15/03/2024.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    fecha_kw = [k for k in keywords if k['type'] == 'fecha']
    assert len(fecha_kw) > 0


def test_detect_default_pii_cpacf_tomo_folio():
    segments = [{'type': 'paragraph', 'text': 'Matrícula CPACF T. 54 F. 233 vigente.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    matricula_kw = [k for k in keywords if k['type'] == 'matricula_prof']
    assert len(matricula_kw) > 0


def test_detect_default_pii_expediente_formatted():
    segments = [{'type': 'paragraph', 'text': 'Expediente EXP-2024-55432 en trámite.'}]
    keywords, positions = anon_app.detect_default_pii(segments)
    expediente_kw = [k for k in keywords if k['type'] == 'expediente_judicial']
    assert len(expediente_kw) > 0
