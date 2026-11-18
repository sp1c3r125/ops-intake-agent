"""The only file that reads environment variables.

Everything else gets a Config object. Tests build a Config directly or pass a dict to `load()`.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from datetime import date

BACKENDS = ("api", "claude-code")
IMAGE_MODES = ("vision", "tesseract")

# Default IMAGE_MODE per backend (SPEC "Backends and images").
# api: base64 image blocks, supported by the API.
# claude-code: scripts/image_test.py showed the CLI reads a base64 image sent as a stream-json message on
# stdin with tools off (method A: --input-format stream-json --output-format stream-json --verbose), so it
# also defaults to vision. Tesseract stays available with IMAGE_MODE=tesseract but is not needed.
DEFAULT_IMAGE_MODE = {"api": "vision", "claude-code": "vision"}

DEFAULT_DEMO_TODAY = "2026-11-20"
DEFAULT_TIMEOUT = 120.0


class ConfigError(Exception):
    """A required setting is missing or invalid. The message says what to set."""


@dataclass(frozen=True)
class Config:
    backend: str = "api"
    model: str | None = None
    api_key: str | None = None
    image_mode: str = "vision"
    timeout: float = DEFAULT_TIMEOUT
    demo_today: date = date.fromisoformat(DEFAULT_DEMO_TODAY)


def load(env=None) -> Config:
    """Build a Config from the environment (or from a dict, for tests). Raises ConfigError."""
    env = os.environ if env is None else env

    backend = env.get("BACKEND", "api")
    if backend not in BACKENDS:
        raise ConfigError(f'BACKEND must be "api" or "claude-code", not {backend!r}.')

    model = env.get("ANTHROPIC_MODEL") or None
    api_key = env.get("ANTHROPIC_API_KEY") or None
    if backend == "api":
        if not model:
            raise ConfigError("Set ANTHROPIC_MODEL to the model id you want to use (there is no default).")
        if not api_key:
            raise ConfigError("Set ANTHROPIC_API_KEY for BACKEND=api.")
    # claude-code: ANTHROPIC_MODEL is optional; with none set the CLI uses its own default model.

    image_mode = env.get("IMAGE_MODE") or DEFAULT_IMAGE_MODE[backend]
    if image_mode not in IMAGE_MODES:
        raise ConfigError(f'IMAGE_MODE must be "vision" or "tesseract", not {image_mode!r}.')

    raw_timeout = env.get("CLAUDE_CODE_TIMEOUT", str(DEFAULT_TIMEOUT))
    try:
        timeout = float(raw_timeout)
    except ValueError:
        raise ConfigError(f"CLAUDE_CODE_TIMEOUT must be a number of seconds, not {raw_timeout!r}.") from None
    if timeout <= 0:
        raise ConfigError("CLAUDE_CODE_TIMEOUT must be greater than 0.")

    raw_date = env.get("DEMO_TODAY", DEFAULT_DEMO_TODAY)
    try:
        demo_today = date.fromisoformat(raw_date)
    except ValueError:
        raise ConfigError(f"DEMO_TODAY must be YYYY-MM-DD, not {raw_date!r}.") from None

    return Config(backend, model, api_key, image_mode, timeout, demo_today)
