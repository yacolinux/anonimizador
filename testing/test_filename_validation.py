from conftest import anon_app
import uuid

def test_valid_upload_filename_uuid_docx():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(f'{uid}.docx') is True

def test_valid_upload_filename_uuid_pdf():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(f'{uid}.pdf') is True

def test_valid_upload_filename_uppercase_uuid():
    uid = str(uuid.uuid4()).upper()
    assert anon_app.is_valid_upload_filename(f'{uid}.pdf') is True

def test_invalid_upload_filename_empty():
    assert anon_app.is_valid_upload_filename('') is False

def test_invalid_upload_filename_none():
    assert anon_app.is_valid_upload_filename(None) is False

def test_invalid_upload_filename_no_ext():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(uid) is False

def test_invalid_upload_filename_wrong_ext():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(f'{uid}.exe') is False
    assert anon_app.is_valid_upload_filename(f'{uid}.txt') is False
    assert anon_app.is_valid_upload_filename(f'{uid}.zip') is False

def test_invalid_upload_filename_path_traversal():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(f'../{uid}.docx') is False
    assert anon_app.is_valid_upload_filename(f'/etc/{uid}.pdf') is False

def test_invalid_upload_filename_double_ext():
    uid = str(uuid.uuid4())
    assert anon_app.is_valid_upload_filename(f'{uid}.pdf.docx') is False

def test_invalid_upload_filename_symlinks():
    assert anon_app.is_valid_upload_filename('../../../etc/passwd') is False

def test_invalid_upload_filename_short():
    assert anon_app.is_valid_upload_filename('a.pdf') is False

def test_allowed_file_valid():
    assert anon_app.allowed_file('documento.pdf') is True
    assert anon_app.allowed_file('documento.docx') is True
    assert anon_app.allowed_file('doc.PDF') is True
    assert anon_app.allowed_file('doc.DOCX') is True

def test_allowed_file_invalid():
    assert anon_app.allowed_file('doc.exe') is False
    assert anon_app.allowed_file('doc.txt') is False
    assert anon_app.allowed_file('doc.zip') is False
    assert anon_app.allowed_file('doc.pdf.exe') is False

def test_allowed_file_no_extension():
    assert anon_app.allowed_file('documento') is False

def test_allowed_file_empty():
    assert anon_app.allowed_file('') is False

def test_is_path_inside_uploads_valid():
    upload_dir = anon_app.app.config['UPLOAD_FOLDER']
    valid_path = f'{upload_dir}/somefile.pdf'
    assert anon_app.is_path_inside_uploads(valid_path) is True

def test_is_path_inside_uploads_traversal():
    assert anon_app.is_path_inside_uploads('/etc/passwd') is False

def test_is_path_inside_uploads_outside():
    assert anon_app.is_path_inside_uploads('/tmp/malicious.pdf') is False