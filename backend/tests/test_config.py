import os

from app.config import AiSettings, OcrSettings, load_dotenv


def test_dotenv_windows_paths_comments_and_precedence(tmp_path, monkeypatch):
    env = tmp_path / ".env"
    env.write_text(
        "# comment\n"
        "PADDLE_MODEL_DIR=C:\\Models\\paddle_models\n"
        "PADDLE_DEVICE=cpu\n"
        'POPPLER_PATH="C:\\poppler\\Library\\bin"\n'
        "OCR_LANGUAGES=eng+deu+fra+spa\n"
        "AI_PROVIDER=ollama\n"
        "OLLAMA_MODEL=qwen2.5-coder:1.5b-fast\n",
        encoding="utf-8-sig",
    )
    for k in ("PADDLE_MODEL_DIR", "PADDLE_DEVICE", "POPPLER_PATH", "OCR_LANGUAGES", "OLLAMA_MODEL"):
        monkeypatch.delenv(k, raising=False)
    monkeypatch.setenv("AI_PROVIDER", "none")  # a real environment variable must win over .env
    assert load_dotenv(env) == env
    o = OcrSettings.from_env()
    assert o.model_dir == "C:\\Models\\paddle_models"
    assert o.device == "cpu"
    assert o.poppler_path == "C:\\poppler\\Library\\bin"
    assert o.languages == ("eng", "deu", "fra", "spa")
    assert AiSettings.from_env().provider == "none"
    assert AiSettings.from_env().ollama_model == "qwen2.5-coder:1.5b-fast"
    for k in ("PADDLE_MODEL_DIR", "PADDLE_DEVICE", "POPPLER_PATH", "OCR_LANGUAGES", "OLLAMA_MODEL"):
        os.environ.pop(k, None)


def test_ai_groq_environment_and_secret_repr(monkeypatch):
    monkeypatch.setenv("AI_PROVIDER", "groq")
    monkeypatch.setenv("GROQ_API_KEY", "gsk_test")
    monkeypatch.setenv("GROQ_BASE_URL", "https://example.test/v1")
    monkeypatch.setenv("GROQ_MODEL", "openai/gpt-oss-120b")
    s = AiSettings.from_env()
    assert s.provider == "groq"
    assert s.groq_api_key == "gsk_test"
    assert s.groq_base_url == "https://example.test/v1"
    assert s.groq_model == "openai/gpt-oss-120b"
    assert "gsk_test" not in repr(s)


def test_dotenv_missing_file_is_fine(tmp_path):
    assert load_dotenv(tmp_path / "nope.env") is None
