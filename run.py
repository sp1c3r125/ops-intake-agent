"""Run one pack or all of them:  python run.py --pack <name>   |   python run.py --all

Before any run it prints how many Claude calls the run will make. It never sends anything.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from engine import config, inputs, outputs, pipeline
from engine.backends.api import ApiBackend
from engine.backends.claude_code import ClaudeCodeBackend

ROOT = Path(__file__).resolve().parent


def make_backend(cfg):
    if cfg.backend == "api":
        return ApiBackend(cfg.model, api_key=cfg.api_key)
    return ClaudeCodeBackend(model=cfg.model, timeout=cfg.timeout)


def discover(packs_dir):
    """Pack folders: any folder with a pack.py, except those starting with _ or ."""
    return [p.name for p in sorted(Path(packs_dir).iterdir())
            if p.is_dir() and not p.name.startswith(("_", ".")) and (p / "pack.py").exists()]


def main(argv=None, *, cfg=None, backend=None, packs_dir=None, out_root=None):
    parser = argparse.ArgumentParser(description="ops-intake-agent: extract, check, route. Never sends.")
    group = parser.add_mutually_exclusive_group(required=True)
    group.add_argument("--pack", help="run one pack, by folder name")
    group.add_argument("--all", action="store_true", help="run every pack and write outputs/index.html")
    args = parser.parse_args(argv)

    packs_dir = Path(packs_dir or ROOT / "packs")
    out_root = Path(out_root or ROOT / "outputs")
    try:
        cfg = cfg or config.load()
    except config.ConfigError as e:
        print(f"Config error: {e}", file=sys.stderr)
        return 2

    available = discover(packs_dir)
    names = available if args.all else [args.pack]
    if not names:
        print(f"No packs found in {packs_dir}.", file=sys.stderr)
        return 2
    if args.pack and args.pack not in available:
        print(f"Unknown pack {args.pack!r}. Available: {', '.join(available) or 'none'}", file=sys.stderr)
        return 2

    try:
        packs = [pipeline.load_pack(packs_dir / n) for n in names]
        loaded = [(p, inputs.load_items(p.input_kind, p.dir, p.input_glob, cfg.image_mode)) for p in packs]
    except (pipeline.PackError, ValueError) as e:
        print(f"Pack error: {e}", file=sys.stderr)
        return 2

    # Always say what the run will cost before it starts.
    print(f"Claude calls for this run (backend: {cfg.backend}, image mode: {cfg.image_mode}):")
    total_extract = total_draft = 0
    for p, items in loaded:
        extract, draft = pipeline.count_calls(p, items)
        total_extract, total_draft = total_extract + extract, total_draft + draft
        print(f"  {p.name}: {extract} extract calls" + (f", up to {draft} draft calls" if draft else ""))
    print(f"  total: {total_extract} extract calls"
          + (f" and up to {total_draft} draft calls" if total_draft else "")
          + f". A retry can add up to {total_extract} more extract calls.")

    backend = backend or make_backend(cfg)
    summaries = []
    for p, items in loaded:
        print(f"Running {p.name} ({len(items)} items)...")
        s = pipeline.run_pack(p, items, backend, cfg, out_root)
        summaries.append(s)
        top = ", ".join(f"{k} ({v})" for k, v in outputs.top_reasons(s)) or "none"
        print(f"  {s['name']}: {s['total']} items, {s['auto']} auto, {s['human']} need a person, "
              f"{s['skip']} skipped. Top reasons: {top}")
        print(f"  dashboard: {Path(out_root) / s['name'] / 'dashboard.html'}")
    if args.all:
        print(f"Index: {outputs.write_index(out_root, summaries)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
