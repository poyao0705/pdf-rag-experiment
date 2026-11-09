from typing import Any

import pytest
from pydantic import SecretStr, ValidationError

from core.config import API_ROOT, Settings


def make_settings(**kwargs: Any) -> Settings:
    return Settings(**kwargs)


def test_settings_reject_blank_key_and_resolve_paths_independent_of_cwd(
    tmp_path, monkeypatch
):
    monkeypatch.chdir(tmp_path)
    settings = make_settings(_env_file=None, THESYS_API_KEY="test-key")
    assert isinstance(settings.THESYS_API_KEY, SecretStr)
    assert settings.THESYS_API_KEY.get_secret_value() == "test-key"
    assert "test-key" not in repr(settings)
    assert Settings.model_config.get("env_file") == API_ROOT / ".env"
    expected_path = API_ROOT.parent / "web/src/generated/spec.json"
    assert settings.OPENUI_SPEC_PATH == expected_path
    assert settings.OPENUI_MODEL == "google/gemini-3.6-flash-free"
    assert (
        make_settings(
            _env_file=None, THESYS_API_KEY="test", OPENUI_SPEC_PATH="spec.json"
        ).OPENUI_SPEC_PATH
        == API_ROOT / "spec.json"
    )
    with pytest.raises(ValidationError):
        make_settings(_env_file=None, THESYS_API_KEY="  ")
