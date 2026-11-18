from datetime import date

import pytest

from engine import config
from engine.config import ConfigError, load


def test_api_needs_model_and_key():
    with pytest.raises(ConfigError, match="ANTHROPIC_MODEL"):
        load({"ANTHROPIC_API_KEY": "k"})
    with pytest.raises(ConfigError, match="ANTHROPIC_API_KEY"):
        load({"ANTHROPIC_MODEL": "m"})
    cfg = load({"ANTHROPIC_MODEL": "m", "ANTHROPIC_API_KEY": "k"})
    assert (cfg.backend, cfg.model, cfg.image_mode) == ("api", "m", "vision")


def test_claude_code_needs_nothing_and_model_is_optional():
    cfg = load({"BACKEND": "claude-code"})
    assert cfg.backend == "claude-code" and cfg.model is None and cfg.api_key is None
    assert cfg.image_mode == config.DEFAULT_IMAGE_MODE["claude-code"]
    assert load({"BACKEND": "claude-code", "ANTHROPIC_MODEL": "m"}).model == "m"


def test_defaults_for_timeout_and_demo_date():
    cfg = load({"BACKEND": "claude-code"})
    assert cfg.timeout == 120.0
    assert cfg.demo_today == date(2026, 11, 20)
    cfg = load({"BACKEND": "claude-code", "CLAUDE_CODE_TIMEOUT": "30", "DEMO_TODAY": "2027-01-05"})
    assert cfg.timeout == 30.0 and cfg.demo_today == date(2027, 1, 5)


def test_image_mode_override():
    assert load({"BACKEND": "claude-code", "IMAGE_MODE": "vision"}).image_mode == "vision"


@pytest.mark.parametrize("env", [
    {"BACKEND": "nope"},
    {"BACKEND": "claude-code", "IMAGE_MODE": "x"},
    {"BACKEND": "claude-code", "CLAUDE_CODE_TIMEOUT": "abc"},
    {"BACKEND": "claude-code", "CLAUDE_CODE_TIMEOUT": "0"},
    {"BACKEND": "claude-code", "DEMO_TODAY": "20/11/2026"},
])
def test_bad_settings_raise(env):
    with pytest.raises(ConfigError):
        load(env)
