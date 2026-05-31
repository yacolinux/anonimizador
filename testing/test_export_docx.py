import os
import tempfile
from conftest import anon_app

def test_anonymize_docx_replaces_keywords():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('Paciente: Juan Pérez, DNI 30.123.456')
        doc.save(tmp.name)
        keywords = [
            {'word': 'Juan Pérez', 'type': 'nombre'},
            {'word': '30.123.456', 'type': 'dni'},
        ]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        result_doc = docx.Document(buf)
        text = ' '.join(p.text for p in result_doc.paragraphs)
        assert 'Juan Pérez' not in text
        assert '30.123.456' not in text
        assert '[REDACTADO]' in text
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_preserves_non_pii():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('Informe médico general.')
        doc.add_paragraph('El paciente se encuentra en buen estado.')
        doc.save(tmp.name)
        keywords = [{'word': 'Juan Pérez', 'type': 'nombre'}]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        result_doc = docx.Document(buf)
        texts = [p.text for p in result_doc.paragraphs]
        assert any('Informe médico general' in t for t in texts)
        assert any('buen estado' in t for t in texts)
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_empty_keywords():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        original = 'Texto de prueba sin datos sensibles.'
        doc.add_paragraph(original)
        doc.save(tmp.name)
        buf = anon_app.anonymize_docx(tmp.name, [], '[REDACTADO]')
        result_doc = docx.Document(buf)
        assert original in ' '.join(p.text for p in result_doc.paragraphs)
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_multiple_paragraphs():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('Paciente: Pedro Gómez')
        doc.add_paragraph('DNI: 40.123.456')
        doc.add_paragraph('Diagnóstico: nada relevante.')
        doc.save(tmp.name)
        keywords = [
            {'word': 'Pedro Gómez', 'type': 'nombre'},
            {'word': '40.123.456', 'type': 'dni'},
        ]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        result_doc = docx.Document(buf)
        full = ' '.join(p.text for p in result_doc.paragraphs)
        assert '[REDACTADO]' in full
        assert 'Pedro Gómez' not in full
        assert 'nada relevante' in full
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_table_cells():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        table = doc.add_table(rows=2, cols=2)
        table.cell(0, 0).text = 'Nombre'
        table.cell(0, 1).text = 'DNI'
        table.cell(1, 0).text = 'Juan Pérez'
        table.cell(1, 1).text = '30.123.456'
        doc.save(tmp.name)
        keywords = [
            {'word': 'Juan Pérez', 'type': 'nombre'},
            {'word': '30.123.456', 'type': 'dni'},
        ]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        result_doc = docx.Document(buf)
        full = ' '.join(p.text for p in result_doc.paragraphs)
        for table in result_doc.tables:
            for row in table.rows:
                for cell in row.cells:
                    full += ' ' + cell.text
        assert 'Juan Pérez' not in full
        assert '30.123.456' not in full
        assert full.count('[REDACTADO]') >= 2
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_replacement_string():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('Paciente: Juan Pérez')
        doc.save(tmp.name)
        keywords = [{'word': 'Juan Pérez', 'type': 'nombre'}]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[ANONIMO]')
        result_doc = docx.Document(buf)
        text = ' '.join(p.text for p in result_doc.paragraphs)
        assert '[ANONIMO]' in text
        assert '[REDACTADO]' not in text
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_accented_keyword():
    import docx
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('El perito es José Martínez')
        doc.save(tmp.name)
        keywords = [{'word': 'José Martínez', 'type': 'nombre'}]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        result_doc = docx.Document(buf)
        text = ' '.join(p.text for p in result_doc.paragraphs)
        assert 'José Martínez' not in text
        assert '[REDACTADO]' in text
    finally:
        os.unlink(tmp.name)

def test_anonymize_docx_output_is_bytesio():
    import docx
    from io import BytesIO
    tmp = tempfile.NamedTemporaryFile(suffix='.docx', delete=False)
    tmp.close()
    try:
        doc = docx.Document()
        doc.add_paragraph('Paciente: Juan Pérez')
        doc.save(tmp.name)
        keywords = [{'word': 'Juan Pérez', 'type': 'nombre'}]
        buf = anon_app.anonymize_docx(tmp.name, keywords, '[REDACTADO]')
        assert isinstance(buf, BytesIO)
        assert len(buf.getvalue()) > 0
    finally:
        os.unlink(tmp.name)