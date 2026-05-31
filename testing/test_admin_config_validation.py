import json
import os
import tempfile
from conftest import anon_app, DEFAULT_PATTERNS_DATA, REGEX_PATTERNS_FILE, reset_config_file

def setup_function():
    reset_config_file()

def teardown_function():
    reset_config_file()

def test_save_and_load_regex_config():
    patterns = [{"pattern": "\\b\\d{7,8}\\b", "type": "dni_test"}]
    prompt = "Test prompt {text}"
    anon_app.save_regex_config(patterns, prompt)
    config = anon_app.load_regex_config()
    assert config['patterns'] == patterns
    assert config['prompt'] == prompt

def test_load_default_config_when_file_missing():
    backup = REGEX_PATTERNS_FILE + '.bak'
    try:
        os.rename(REGEX_PATTERNS_FILE, backup)
        config = anon_app.load_regex_config()
        assert 'patterns' in config
        assert 'prompt' in config
    finally:
        if os.path.exists(backup):
            os.rename(backup, REGEX_PATTERNS_FILE)

def test_save_config_with_model_info():
    patterns = [{"pattern": "\\d+", "type": "numero"}]
    prompt = "Analiza {text}"
    anon_app.save_regex_config(
        patterns,
        prompt,
        model_url="http://localhost:11434/v1",
        model_name="llama3",
        api_key="sk-test-123",
    )
    config = anon_app.load_regex_config()
    assert config['model_url'] == "http://localhost:11434/v1"
    assert config['model_name'] == "llama3"
    assert config['api_key'] == "sk-test-123"

def test_save_config_without_model_info():
    patterns = DEFAULT_PATTERNS_DATA['patterns']
    prompt = DEFAULT_PATTERNS_DATA['prompt']
    anon_app.save_regex_config(patterns, prompt)
    config = anon_app.load_regex_config()
    config = anon_app.load_regex_config()
    assert 'model_url' not in config
    assert 'model_name' not in config

def test_get_pii_patterns_from_config():
    patterns = [{"pattern": "\\b\\d{3}\\b", "type": "tres_digitos"}]
    prompt = "test"
    anon_app.save_regex_config(patterns, prompt)
    result = anon_app.get_pii_patterns()
    assert len(result) == 1
    assert result[0][1] == 'tres_digitos'

def test_get_opencode_prompt():
    patterns = []
    prompt = "Custom prompt: {text}"
    anon_app.save_regex_config(patterns, prompt)
    loaded = anon_app.get_opencode_prompt()
    assert loaded == prompt

def test_get_opencode_prompt_default_fallback():
    backup = REGEX_PATTERNS_FILE + '.bak'
    try:
        os.rename(REGEX_PATTERNS_FILE, backup)
        loaded = anon_app.get_opencode_prompt()
        assert '{text}' in loaded
    finally:
        if os.path.exists(backup):
            os.rename(backup, REGEX_PATTERNS_FILE)

def test_save_multiple_patterns():
    patterns = [
        {"pattern": "\\b\\d+\\b", "type": "numeros"},
        {"pattern": "\\b[a-z]+@[a-z]+\\.[a-z]+\\b", "type": "email"},
        {"pattern": "\\b[A-Z][a-z]+\\s+[A-Z][a-z]+\\b", "type": "nombre"},
    ]
    anon_app.save_regex_config(patterns, "test")
    config = anon_app.load_regex_config()
    assert len(config['patterns']) == 3

def test_save_empty_patterns():
    anon_app.save_regex_config([], "test empty")
    config = anon_app.load_regex_config()
    assert config['patterns'] == []

def test_save_config_preserves_file_json():
    patterns = [{"pattern": "\\d+", "type": "num"}]
    prompt = "test"
    anon_app.save_regex_config(patterns, prompt)
    with open(REGEX_PATTERNS_FILE, 'r', encoding='utf-8') as f:
        data = json.load(f)
    assert data['patterns'] == patterns
    assert data['prompt'] == prompt

def test_get_model_config_defaults():
    config = anon_app.get_model_config()
    assert 'model_url' in config
    assert 'model_name' in config
    assert 'api_key' in config

def test_get_current_model():
    model = anon_app.get_current_model()
    assert isinstance(model, str)
    assert len(model) > 0

def test_is_local_model_provider_remote():
    os.environ['OPENAI_BASE_URL'] = 'https://api.openrouter.ai/v1'
    from conftest import anon_app as app2
    result = app2.is_local_model_provider()
    assert result is False

def test_is_local_model_provider_localhost():
    os.environ['OPENAI_BASE_URL'] = 'http://localhost:11434/v1'
    from conftest import anon_app as app2
    result = app2.is_local_model_provider()
    assert result is True
