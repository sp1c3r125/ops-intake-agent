"""Demo backend: runs `claude -p` as a subprocess, so it uses the Claude plan instead of API billing.

Safety (SPEC core rule 10), on every call:
- `--tools ""`: the input is untrusted, and a Claude Code session normally has file and shell tools that an
  injected instruction could try to use.
- `--no-session-persistence`: nothing is saved to disk.
- The input goes in through stdin, never the command line.
- A timeout (CLAUDE_CODE_TIMEOUT, default 120 seconds). Any failure raises BackendError.

Images: scripts/image_test.py showed that the CLI reads a base64 image block sent as a stream-json user
message on stdin (`--input-format stream-json`, which requires `--output-format stream-json --verbose`).
Text-only calls keep the plain `--output-format json` path.
"""
from __future__ import annotations

import base64
import json
import subprocess

from . import BackendError


def _image_message(user_text, image):
    data, mime = image
    return json.dumps({"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": mime,
                                     "data": base64.b64encode(data).decode("ascii")}},
        {"type": "text", "text": user_text}]}}) + "\n"


def _result_object(stdout, streaming):
    """The final result object: the whole stdout (json format) or the last `result` line (stream-json)."""
    try:
        if not streaming:
            return json.loads(stdout)
        for line in reversed(stdout.splitlines()):
            line = line.strip()
            if line.startswith("{"):
                obj = json.loads(line)
                if isinstance(obj, dict) and obj.get("type") == "result":
                    return obj
    except json.JSONDecodeError:
        pass
    raise BackendError(f"unreadable claude output: {stdout[:100]!r}")


class ClaudeCodeBackend:
    name = "claude-code"

    def __init__(self, model=None, timeout=120.0):
        self.model = model  # optional: with none, the CLI uses its own default model
        self.timeout = timeout

    def generate(self, system, user_text, schema=None, image=None):
        streaming = image is not None
        cmd = ["claude", "-p", system, "--tools", "", "--no-session-persistence"]
        if streaming:
            cmd += ["--input-format", "stream-json", "--output-format", "stream-json", "--verbose"]
            stdin = _image_message(user_text, image)
        else:
            cmd += ["--output-format", "json"]
            stdin = user_text
        if schema is not None:
            cmd += ["--json-schema", json.dumps(schema)]
        if self.model:
            cmd += ["--model", self.model]

        try:
            proc = subprocess.run(cmd, input=stdin, capture_output=True, text=True,
                                  encoding="utf-8", timeout=self.timeout)
        except subprocess.TimeoutExpired as e:
            raise BackendError(f"claude timed out after {self.timeout}s") from e
        except FileNotFoundError as e:
            raise BackendError("claude CLI not found on PATH") from e
        except OSError as e:
            raise BackendError(f"could not run claude: {e}") from e
        if proc.returncode != 0:
            raise BackendError(f"claude exited {proc.returncode}: {proc.stderr.strip()[:200]}")

        envelope = _result_object(proc.stdout, streaming)
        result = envelope.get("result") if isinstance(envelope, dict) else None
        if not isinstance(envelope, dict) or "result" not in envelope:
            raise BackendError(f"unreadable claude output: {proc.stdout[:100]!r}")
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
