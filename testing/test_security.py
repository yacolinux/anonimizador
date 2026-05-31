import os
import json
import tempfile
import time
import uuid
import pytest
from io import BytesIO
from conftest import anon_app, create_synthetic_docx, reset_config_file, cleanup_temp_files

@pytest.fixture
def client():
    anon_app.app.config['TESTING'] = True
    anon_app.app.config['UPLOAD_FOLDER'] = tempfile.mkdtemp()
    with anon_app.app.test_client() as c:
        yield c

@pytest.fixture(autouse=True)
def reset():
    reset_config_file()
    anon_app._login_attempts.clear()
    if anon_app.redis_available:
        try:
            anon_app.redis_client.delete('anonimizador:login:127.0.0.1')
            anon_app.redis_client.delete('anonimizador:login:unknown')
            anon_app.redis_client.delete('anonimizador:login:127.0.0.1')
        except Exception:
            pass

def create_valid_docx_in_upload(client):
    import docx
    d = docx.Document()
    d.add_paragraph('Paciente: Juan Pérez, DNI 30.123.456')
    buf = BytesIO()
    d.save(buf)
    buf.seek(0)
    data = {'file': (buf, 'test.docx')}
    resp = client.post('/upload', data=data, content_type='multipart/form-data')
    body = resp.get_json()
    return body.get('filename'), body.get('keywords', [])

class TestFileUploadSecurity:

    def test_upload_exe_rejected(self, client):
        data = {'file': (BytesIO(b'fake exe content'), 'malware.exe')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400
        body = resp.get_json()
        assert 'error' in body

    def test_upload_txt_rejected(self, client):
        data = {'file': (BytesIO(b'text file'), 'documento.txt')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_zip_rejected(self, client):
        data = {'file': (BytesIO(b'zip content'), 'doc.zip')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_no_filename(self, client):
        data = {'file': (BytesIO(b'something'), '')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_no_file_key(self, client):
        resp = client.post('/upload', data={})
        assert resp.status_code == 400
        assert 'No file provided' in resp.get_json().get('error', '')

    def test_upload_filename_with_path_traversal(self, client):
        data = {'file': (BytesIO(b'%PDF-1.4 fake'), '../../../etc/passwd.pdf')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_filename_with_null_byte(self, client):
        data = {'file': (BytesIO(b'%PDF-1.4 fake'), 'doc.pdf\x00.exe')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

    def test_upload_filename_double_extension(self, client):
        data = {'file': (BytesIO(b'fake content'), 'doc.pdf.exe')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        assert resp.status_code == 400

class TestPathTraversal:

    def test_is_path_inside_uploads_outside(self):
        assert anon_app.is_path_inside_uploads('/etc/passwd') is False
        assert anon_app.is_path_inside_uploads('/tmp/evil.pdf') is False

    def test_is_path_inside_uploads_traversal_dotdot(self):
        upload_dir = anon_app.app.config['UPLOAD_FOLDER']
        path = os.path.join(upload_dir, '..', 'etc', 'passwd')
        assert anon_app.is_path_inside_uploads(path) is False

    def test_is_path_inside_uploads_symlink_in_path(self):
        upload_dir = anon_app.app.config['UPLOAD_FOLDER']
        path = os.path.join(upload_dir, 'subdir', '..', '..', 'etc', 'passwd')
        assert anon_app.is_path_inside_uploads(path) is False

    def test_is_path_inside_uploads_valid(self):
        upload_dir = anon_app.app.config['UPLOAD_FOLDER']
        path = os.path.join(upload_dir, 'valid-file.pdf')
        assert anon_app.is_path_inside_uploads(path) is True

    def test_is_valid_upload_filename_rejects_traversal(self):
        assert anon_app.is_valid_upload_filename('../file.docx') is False
        assert anon_app.is_valid_upload_filename('../../file.pdf') is False

class TestExportSecurity:

    def test_export_no_filename(self, client):
        resp = client.post('/export', json={'format': 'docx', 'keywords': []})
        assert resp.status_code == 400
        assert 'No filename' in resp.get_json().get('error', '')

    def test_export_invalid_filename(self, client):
        resp = client.post('/export', json={
            'filename': '../../../etc/passwd',
            'keywords': [],
            'format': 'docx',
        })
        assert resp.status_code == 400
        assert 'Invalid filename' in resp.get_json().get('error', '')

    def test_export_nonexistent_file(self, client):
        uid = str(uuid.uuid4())
        resp = client.post('/export', json={
            'filename': f'{uid}.pdf',
            'keywords': [],
            'format': 'docx',
        })
        assert resp.status_code == 404

    def test_export_empty_body(self, client):
        resp = client.post('/export', json={})
        assert resp.status_code == 400

    def test_export_to_docx_works_with_valid_file(self, client):
        filename, keywords = create_valid_docx_in_upload(client)
        kw_entries = [{'word': p.get('word', ''), 'type': p.get('type', 'other')}
                      for p in keywords[:2]]
        resp = client.post('/export', json={
            'filename': filename,
            'keywords': kw_entries,
            'format': 'docx',
            'replacement': '[REDACTADO]',
        })
        assert resp.status_code == 200

    def test_export_unexpected_format(self, client):
        filename, _ = create_valid_docx_in_upload(client)
        resp = client.post('/export', json={
            'filename': filename,
            'keywords': [],
            'format': 'html',
        })
        assert resp.status_code == 400

    def test_export_pdf_to_docx_rejected(self, client):
        from fpdf import FPDF
        pdf = FPDF()
        pdf.add_page()
        pdf.set_font('Helvetica', '', 11)
        pdf.multi_cell(0, 6, 'Paciente: Juan Pérez, DNI 30.123.456')
        pdf_buf = BytesIO()
        pdf.output(pdf_buf)
        pdf_buf.seek(0)
        data = {'file': (pdf_buf, 'test.pdf')}
        resp = client.post('/upload', data=data, content_type='multipart/form-data')
        body = resp.get_json()
        filename = body.get('filename')
        resp = client.post('/export', json={
            'filename': filename,
            'keywords': [],
            'format': 'docx',
        })
        assert resp.status_code == 400
        body = resp.get_json()
        assert body and 'No se puede exportar PDF a DOCX' in body.get('error', '')

class TestAdminRateLimit:

    def test_login_rate_limit_blocks_after_max(self, client):
        for _ in range(5):
            client.post('/admin/login', json={
                'user': 'admin', 'password': 'wrongpass'
            })
        resp = client.post('/admin/login', json={
            'user': 'admin', 'password': 'wrongpass'
        })
        assert resp.status_code == 429
        assert 'Too many attempts' in resp.get_json().get('error', '')

    def test_admin_login_ok(self, client):
        resp = client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        assert resp.status_code == 200
        body = resp.get_json()
        assert body.get('ok') is True

    def test_admin_logout_clears_session(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.get('/admin/status')
        assert resp.get_json()['logged_in'] is True
        client.post('/admin/logout')
        resp = client.get('/admin/status')
        assert resp.get_json()['logged_in'] is False

    def test_unauthenticated_admin_endpoints_blocked(self, client):
        resp = client.get('/admin/config')
        assert resp.status_code == 401
        resp = client.post('/admin/config', json={})
        assert resp.status_code == 401

class TestCookieAndHeaders:

    def test_session_cookie_httponly_on_login(self, client):
        resp = client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        cookie_headers = resp.headers.getlist('Set-Cookie')
        has_httponly = any('HttpOnly' in c for c in cookie_headers)
        assert has_httponly

    def test_session_cookie_samesite_lax(self, client):
        resp = client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        cookie_headers = resp.headers.getlist('Set-Cookie')
        has_samesite = any('SameSite=Lax' in c for c in cookie_headers)
        assert has_samesite

class TestUploadsEndpoint:

    def test_uploads_endpoint_requires_auth(self, client):
        resp = client.get('/uploads/550e8400-e29b-41d4-a716-446655440000.pdf')
        assert resp.status_code == 401

    def test_uploads_endpoint_with_auth_invalid_uuid(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.get('/uploads/../../../etc/passwd')
        assert resp.status_code in (400, 404)

    def test_uploads_endpoint_with_auth_nonexistent(self, client):
        import uuid
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        uid = str(uuid.uuid4())
        resp = client.get(f'/uploads/{uid}.pdf')
        assert resp.status_code == 404

class TestAdminConfigValidation:

    def test_save_invalid_regex_pattern(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.post('/admin/config', json={
            'patterns': [{'pattern': '[invalid', 'type': 'test'}],
            'prompt': 'test',
        })
        assert resp.status_code == 400
        assert 'regex inválido' in resp.get_json().get('error', '').lower()

    def test_save_pattern_too_long(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.post('/admin/config', json={
            'patterns': [{'pattern': 'a' * 301, 'type': 'test'}],
            'prompt': 'test',
        })
        assert resp.status_code == 400

    def test_save_missing_pattern_fields(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.post('/admin/config', json={
            'patterns': [{'pattern': '\\d+'}],
            'prompt': 'test',
        })
        assert resp.status_code == 400

    def test_save_invalid_model_url(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.post('/admin/config', json={
            'patterns': [],
            'prompt': 'test',
            'model_url': 'not-a-url',
        })
        assert resp.status_code == 400

    def test_save_valid_config(self, client):
        client.post('/admin/login', json={
            'user': 'admin', 'password': 'testpass'
        })
        resp = client.post('/admin/config', json={
            'patterns': [{'pattern': '\\d+', 'type': 'num'}],
            'prompt': 'test prompt',
            'model_url': 'https://api.example.com/v1',
        })
        assert resp.status_code == 200

    def test_admin_config_requires_auth(self, client):
        resp = client.post('/admin/config', json={
            'patterns': [{'pattern': '\\d+', 'type': 'num'}],
            'prompt': 'test',
        })
        assert resp.status_code == 401

class TestReanalyzeSecurity:

    def test_reanalyze_invalid_filename(self, client):
        resp = client.post('/reanalyze-ai', json={
            'filename': '../../../etc/passwd'
        })
        assert resp.status_code == 400
        assert 'Invalid filename' in resp.get_json().get('error', '')

    def test_reanalyze_nonexistent_file(self, client):
        resp = client.post('/reanalyze-ai', json={
            'filename': '550e8400-e29b-41d4-a716-446655440000.pdf'
        })
        assert resp.status_code == 404

class TestReadyEndpoint:

    def test_ready_endpoint_returns_json(self, client):
        resp = client.get('/ready')
        assert resp.status_code == 200
        body = resp.get_json()
        assert 'ready' in body
        assert 'busy' in body
        assert 'inflight' in body