import os
from pathlib import Path

from streamlit.testing.v1 import AppTest

APP = str(Path(__file__).resolve().parents[1] / "app.py")


def test_app_starts_without_api_key_and_shows_clear_error(monkeypatch):
    monkeypatch.delenv("GEMINI_API_KEY", raising=False)
    monkeypatch.delenv("APP_PASSWORD", raising=False)
    monkeypatch.setattr("dotenv.load_dotenv", lambda *a, **k: False)
    monkeypatch.setattr("config._get", lambda name, default="": os.environ.get(name) or default)  # ignore local secrets.toml
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert any("GEMINI_API_KEY" in e.value for e in at.error)


def test_password_gate(monkeypatch):
    monkeypatch.setenv("APP_PASSWORD", "s3cret")
    monkeypatch.setenv("GEMINI_API_KEY", "dummy")
    at = AppTest.from_file(APP, default_timeout=30).run()
    assert not at.exception
    assert len(at.text_input) == 1  # only the password box is shown
    at.text_input[0].set_value("wrong").run()
    assert any("Wrong password" in e.value for e in at.error)
