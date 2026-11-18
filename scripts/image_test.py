"""Can the `claude -p` CLI read an image with tools switched off?  Run this yourself, in a normal terminal.

    python scripts/image_test.py

Do NOT run it from inside a Claude Code session: a nested `claude -p` can block or hang.

It makes a small PNG that shows "TOTAL 12.50", then tries each method below. For every method it prints the
command (the image bytes are never printed; they go in through stdin), the exit code, and the answer.
It also reports whether Tesseract is installed.

Methods (all with --tools "" and --no-session-persistence, same as the real backend):
  A  --input-format stream-json, --output-format stream-json (--verbose): a base64 image content block
  B  --input-format stream-json, --output-format json:                    the same input, plain envelope
The result tells us which IMAGE_MODE each backend should default to (SPEC "Backends and images").
"""
import base64
import io
import json
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

TIMEOUT = 120
SCHEMA = {"type": "object", "properties": {"total": {"type": "number"}}, "required": ["total"],
          "additionalProperties": False}
PROMPT = ('Read the image. Reply with JSON only. "total" is the TOTAL amount shown in the image, '
          "as a number.")
EXPECTED = 12.5


def make_png():
    img = Image.new("RGB", (360, 120), "white")
    draw = ImageDraw.Draw(img)
    try:
        font = ImageFont.truetype("consola.ttf", 40)  # Windows monospace
    except OSError:
        font = ImageFont.load_default(size=40)
    draw.text((20, 36), "TOTAL 12.50", fill="black", font=font)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def stream_input(png):
    msg = {"type": "user", "message": {"role": "user", "content": [
        {"type": "image", "source": {"type": "base64", "media_type": "image/png",
                                     "data": base64.b64encode(png).decode("ascii")}},
        {"type": "text", "text": "Read the image and give the total."}]}}
    return json.dumps(msg) + "\n"


def parse_answer(stdout):
    """Pull the answer out of either a single JSON envelope or a stream-json line stream."""
    envelopes = []
    for line in stdout.splitlines():
        line = line.strip()
        if line.startswith("{"):
            try:
                envelopes.append(json.loads(line))
            except json.JSONDecodeError:
                pass
    final = next((e for e in reversed(envelopes) if e.get("type") == "result" or "result" in e), None)
    if final is None:
        return None, "no result object found in output"
    if isinstance(final.get("structured_output"), dict):
        return final["structured_output"], None
    return final.get("result"), final.get("subtype") or ("is_error" if final.get("is_error") else None)


def try_method(label, extra_args, png):
    cmd = ["claude", "-p", PROMPT, "--tools", "", "--no-session-persistence",
           "--input-format", "stream-json", "--json-schema", json.dumps(SCHEMA)] + extra_args
    print(f"\n=== Method {label} ===")
    print("command:", " ".join(repr(c) if " " in c or c == "" else c for c in cmd))
    print("stdin:   one stream-json user message with a base64 PNG block (bytes not shown)")
    try:
        proc = subprocess.run(cmd, input=stream_input(png), capture_output=True, text=True,
                              encoding="utf-8", timeout=TIMEOUT)
    except subprocess.TimeoutExpired:
        print(f"exit code: none (timed out after {TIMEOUT}s)")
        return False
    except FileNotFoundError:
        print("exit code: none (claude CLI not found on PATH)")
        return False
    print("exit code:", proc.returncode)
    if proc.returncode != 0:
        print("stderr:", proc.stderr.strip()[:500])
        print("stdout:", proc.stdout.strip()[:500])
        return False
    answer, note = parse_answer(proc.stdout)
    print("answer:", json.dumps(answer) if not isinstance(answer, str) else answer[:500])
    if note:
        print("note:", note)
    if isinstance(answer, str):
        try:
            answer = json.loads(answer)
        except json.JSONDecodeError:
            pass
    ok = isinstance(answer, dict) and answer.get("total") == EXPECTED
    print("RESULT:", f"WORKS (read total {EXPECTED})" if ok else "did not return the expected total")
    return ok


def check_tesseract():
    print("\n=== Tesseract ===")
    try:
        proc = subprocess.run(["tesseract", "--version"], capture_output=True, text=True, timeout=15)
        first = (proc.stdout or proc.stderr).strip().splitlines()
        print("tesseract --version: exit", proc.returncode, "|", first[0] if first else "(no output)")
        return proc.returncode == 0
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        print("tesseract --version: not available:", type(e).__name__)
        return False


def main():
    png = make_png()
    results = {
        "A (stream-json in and out)": try_method("A", ["--output-format", "stream-json", "--verbose"], png),
        "B (stream-json in, json out)": try_method("B", ["--output-format", "json"], png),
    }
    tess = check_tesseract()
    print("\n=== Summary ===")
    for name, ok in results.items():
        print(f"CLI image method {name}: {'WORKS' if ok else 'no'}")
    print("Tesseract:", "installed" if tess else "missing")
    if not any(results.values()) and not tess:
        print("No CLI image method works and Tesseract is missing: install Tesseract for the CLI backend.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
