#!/usr/bin/env python3
"""check_env.py - ad-cut environment diagnostic.

Reports whether ad-cut's dependencies are installed:
  - ffmpeg (in PATH)
  - ffprobe (in PATH)
  - faster-whisper (importable in the configured Python)
  - faster-whisper model (cached in HF_HOME)

Diagnostic only — does NOT install anything. To install missing
dependencies, run scripts/install_deps.sh.

Usage:
    python check_env.py                 # human-readable table
    python check_env.py --json         # JSON for scripting
    python check_env.py --python X     # check faster-whisper via this interpreter
    python check_env.py --model medium   # check medium model instead of small

Exit codes:
    0  all dependencies present
    1  one or more missing (also returns non-zero in --json mode)
"""
from __future__ import annotations

import argparse
import json as _json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Tuple

# Force UTF-8 stdout on Windows (default is GBK → mojibake with non-ASCII paths)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


# ---------- individual checks ----------

def check_ffmpeg() -> Tuple[bool, str]:
    """Locate ffmpeg binary."""
    p = shutil.which("ffmpeg")
    return (True, p) if p else (False, "ffmpeg not in PATH")


def check_ffprobe() -> Tuple[bool, str]:
    """Locate ffprobe binary."""
    p = shutil.which("ffprobe")
    return (True, p) if p else (False, "ffprobe not in PATH")


def check_whisper(python_exe: str | None = None, timeout: int = 15) -> Tuple[bool, str]:
    """Check if faster-whisper is importable in the given Python."""
    py = python_exe or sys.executable
    try:
        r = subprocess.run(
            [py, "-c", "import faster_whisper; print(faster_whisper.__version__)"],
            capture_output=True, text=True, timeout=timeout,
        )
    except FileNotFoundError:
        return False, f"python not found: {py}"
    except subprocess.TimeoutExpired:
        return False, f"python check timed out: {py}"

    if r.returncode == 0:
        ver = r.stdout.strip() or "unknown"
        return True, f"faster-whisper {ver} in {py}"
    err = (r.stderr or "").strip().splitlines()[0] if r.stderr else "unknown error"
    return False, f"faster-whisper not importable in {py}: {err}"


def _hf_cache_dir() -> Path:
    """Locate HF cache dir (respects HF_HOME env var)."""
    hf_home = os.environ.get("HF_HOME")
    if hf_home:
        return Path(hf_home) / "hub"
    return Path.home() / ".cache" / "huggingface" / "hub"


def check_model_cached(model_name: str = "small") -> Tuple[bool, str]:
    """Check if faster-whisper model is in HF cache.

    Looks at $HF_HOME/hub/models--Systran--faster-whisper-{model_name}/snapshots/*/config.json
    """
    repo_id = f"Systran/faster-whisper-{model_name}"
    cache_base = _hf_cache_dir()
    model_dir = cache_base / f"models--{repo_id.replace('/', '--')}"

    # Method A: huggingface_hub API (most reliable)
    try:
        from huggingface_hub import try_to_load_from_cache  # type: ignore
        p = try_to_load_from_cache(repo_id, "config.json")
        if p:
            return True, f"{p.parent} (HF cache: {repo_id})"
    except ImportError:
        pass  # huggingface_hub not installed; fall back to filesystem check
    except Exception:
        pass

    # Method B: filesystem check (no huggingface_hub needed)
    if model_dir.exists():
        snapshots_dir = model_dir / "snapshots"
        if snapshots_dir.exists():
            for snap in snapshots_dir.iterdir():
                if (snap / "config.json").exists():
                    return True, str(snap)

    return False, f"model '{model_name}' not cached at {cache_base}"


# ---------- report ----------

def collect(python: str | None = None, model: str = "small") -> dict[str, Tuple[bool, str]]:
    return {
        "ffmpeg": check_ffmpeg(),
        "ffprobe": check_ffprobe(),
        "whisper": check_whisper(python),
        "model": check_model_cached(model),
    }


def report(python: str | None = None, model: str = "small") -> int:
    """Print a table; return 0 if all OK, 1 if any missing."""
    results = collect(python, model)
    print(f"ad-cut environment check (model: {model}):")
    width = max(len(name) for name in results)
    all_ok = True
    for name, (ok, msg) in results.items():
        mark = "✓" if ok else "✗"
        print(f"  {mark}  {name:<{width}}  {msg}")
        if not ok:
            all_ok = False
    if all_ok:
        print("\nAll dependencies present.")
    else:
        print("\nMissing components → run scripts/install_deps.sh [--yes]")
    return 0 if all_ok else 1


# ---------- CLI ----------

def main() -> int:
    p = argparse.ArgumentParser(description="ad-cut environment diagnostic")
    p.add_argument("--python", help="Python executable to check (default: sys.executable)")
    p.add_argument("--model", default="small",
                   help="faster-whisper model to check (default: small)")
    p.add_argument("--json", action="store_true",
                   help="emit JSON (one key per check, bool value)")
    args = p.parse_args()

    results = collect(args.python, args.model)
    if args.json:
        # JSON: top-level keys are bool; detailed info goes into _info key
        out = {k: v[0] for k, v in results.items()}
        out["_info"] = {k: v[1] for k, v in results.items()}
        print(_json.dumps(out, indent=2))
        return 0 if all(v[0] for v in results.values()) else 1
    return report(args.python, args.model)


if __name__ == "__main__":
    sys.exit(main())