"""Demo backend: runs `claude -p` as a subprocess, so it uses the Claude plan instead of API billing.

Safety (SPEC core rule 10), on every call:
- `--tools ""`: the input is untrusted, and a Claude Code session normally has file and shell tools that an
  injected instruction could try to use.
- `--no-session-persistence`: nothing is saved to disk.
- The input goes in through stdin, never the command line.
- A timeout (CLAUDE_CODE_TIMEOUT, default 120 seconds). Any failure raises BackendError.
"""
from __future__ import annotations

import json
import subprocess

from . import BackendError


class ClaudeCodeBackend:
    name = "claude-code"

    def __init__(self, model=None, timeout=120.0):
        self.model = model  # optional: with none, the CLI uses its own default model
        self.timeout = timeout

    def generate(self, system, user_text, schema=None, image=None):
        if image is not None:
            # Whether and how the CLI accepts images is decided by scripts/image_test.py. Until a method
            # is confirmed there, an image is refused here rather than guessed at.
            raise BackendError("claude-code backend: image input is not supported; use IMAGE_MODE=tesseract")

        cmd = ["claude", "-p", system, "--output-format", "json", "--tools", "", "--no-session-persistence"]
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        if self.model:
            cmd += ["--model", self.model]

        try:
            proc = subprocess.run(cmd, input=user_text, capture_output=True, text=True,
                                  encoding="utf-8", timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise BackendError(f"claude timed out after {self.timeout}s") from e
        except FileNotFoundError as e:
            raise BackendError("claude CLI not found on PATH") from e
        except OSError as e:
            raise BackendError(f"could not run claude: {e}") from e
        if proc.returncode != 0:
            raise BackendError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:200]}")

        try:
            envelope = json.loads(proc.stdout)
            result = envelope["result"]
        except (json.JSONDecodeError, KeyError, TypeError) as e:
            raise BackendError(f"unreadable claude output: {proc.stdout[:100]!r}") from e
        if envelope.get("is_error") or not isinstance(result, str):
            raise BackendError(f"claude reported an error: {str(result)[:200]}")

        if schema is not None:
            # With --json-schema the CLI returns the object in `structured_output` and reports stop_reason
            # "tool_use" (it delivers the answer through an internal tool call).
            structured = envelope.get("structured_output")
            if isinstance(structured, dict):
                return json.dumps(structured)
            # No structured_output: hand back the text exactly as it is. The pipeline's validation will
            # reject it, and the retry-once rule applies. Nothing is repaired here (SPEC core rule 3).
            return result

        if (envelope.get("stop_reason") or "end_turn") != "end_turn":
            raise BackendError(f"stopped early: {envelope.get('stop_reason')}")
        return result
