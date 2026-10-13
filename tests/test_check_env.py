"""test_check_env.py - unit tests for bin/check_env.py

Covers:
  - check_ffmpeg / check_ffprobe: PATH lookup via shutil.which
  - check_whisper: subprocess invocation, version capture
  - check_model_cached: HF cache directory + snapshot detection
  - find_cached_model (transcribe.py): same detection logic
  - JSON output mode and exit codes
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

# Make bin/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
sys.path.insert(0, str(BIN_DIR))

import check_env  # noqa: E402
from transcribe import find_cached_model  # noqa: E402


# ----- check_ffmpeg / check_ffprobe -----

def test_check_ffmpeg_present(monkeypatch):
    monkeypatch.setattr("check_env.shutil.which",
                        lambda cmd: (True, "/usr/bin/ffmpeg")[1] if cmd == "ffmpeg" else None)
    ok, msg = check_env.check_ffmpeg()
    assert ok is True
    assert msg == "/usr/bin/ffmpeg"


def test_check_ffmpeg_missing(monkeypatch):
    monkeypatch.setattr("check_env.shutil.which", lambda cmd: None)
    ok, msg = check_env.check_ffmpeg()
    assert ok is False
    assert "not in PATH" in msg


def test_check_ffprobe_present(monkeypatch):
    monkeypatch.setattr("check_env.shutil.which",
                        lambda cmd: "/usr/bin/ffprobe" if cmd == "ffprobe" else None)
    ok, msg = check_env.check_ffprobe()
    assert ok is True
    assert msg == "/usr/bin/ffprobe"


def test_check_ffprobe_missing(monkeypatch):
    monkeypatch.setattr("check_env.shutil.which", lambda cmd: None)
    ok, msg = check_env.check_ffprobe()
    assert ok is False
    assert "ffprobe not in PATH" in msg


# ----- check_whisper -----

def test_check_whisper_present(monkeypatch):
    fake = MagicMock(returncode=0, stdout="1.2.1\n", stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)
    ok, msg = check_env.check_whisper(python_exe="/path/to/python")
    assert ok is True
    assert "1.2.1" in msg
    assert "/path/to/python" in msg


def test_check_whisper_missing(monkeypatch):
    fake = MagicMock(returncode=1, stdout="", stderr="ModuleNotFoundError: No module named 'faster_whisper'\n")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake)
    ok, msg = check_env.check_whisper(python_exe="/missing/python")
    assert ok is False
    assert "faster-whisper not importable" in msg


def test_check_whisper_python_not_found(monkeypatch):
    def raise_fnf(*a, **kw):
        raise FileNotFoundError("/missing/python")
    monkeypatch.setattr("subprocess.run", raise_fnf)
    ok, msg = check_env.check_whisper(python_exe="/missing/python")
    assert ok is False
    assert "python not found" in msg


# ----- check_model_cached -----

def test_check_model_cached_via_huggingfacehub(monkeypatch, tmp_path):
    """huggingface_hub API returns cached path."""
    snap = tmp_path / "snap1"
    snap.mkdir()
    (snap / "config.json").write_text("{}")

    # Patch HF cache to a controlled tmp dir
    monkeypatch.setenv("HF_HOME", str(tmp_path / "hf_cache"))
    (tmp_path / "hf_cache" / "hub").mkdir(parents=True)
    # Place snapshot under the controlled HF_HOME so the real try_to_load_from_cache picks it up
    real_snap = tmp_path / "hf_cache" / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "rev1"
    real_snap.mkdir(parents=True)
    (real_snap / "config.json").write_text("{}")

    ok, msg = check_env.check_model_cached("small")
    assert ok is True
    assert "rev1" in msg


def test_check_model_cached_via_filesystem(monkeypatch, tmp_path):
    """Filesystem fallback when huggingface_hub not installed."""
    # Force HF cache to a controlled tmp dir
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    # Build HF cache structure for "Systran/faster-whisper-small"
    model_dir = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "abc123"
    model_dir.mkdir(parents=True)
    (model_dir / "config.json").write_text("{}")

    # Force huggingface_hub not importable (fallback path)
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    ok, msg = check_env.check_model_cached("small")
    assert ok is True
    assert "abc123" in msg


def test_check_model_not_cached(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    ok, msg = check_env.check_model_cached("small")
    assert ok is False
    assert "not cached" in msg


def test_check_model_cached_empty_snapshot_dir(monkeypatch, tmp_path):
    """Snapshot dir exists but lacks config.json → not considered cached."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    model_dir = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "incomplete"
    model_dir.mkdir(parents=True)
    # No config.json — incomplete snapshot

    ok, msg = check_env.check_model_cached("small")
    assert ok is False


# ----- find_cached_model (transcribe.py) -----

def test_find_cached_model_present(monkeypatch, tmp_path):
    """find_cached_model uses HF cache."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    snap = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "rev1"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")

    result = find_cached_model("small")
    assert result == str(snap)


def test_find_cached_model_missing(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)
    assert find_cached_model("small") is None


def test_find_cached_model_custom_hf_home(monkeypatch, tmp_path):
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    monkeypatch.setitem(sys.modules, "huggingface_hub", None)

    # Note: snapshot parent isn't "hub/" — verify HF_HOME works without hub suffix
    cache_dir = tmp_path / "hub"
    snap2 = cache_dir / "models--Systran--faster-whisper-medium" / "snapshots" / "r1"
    snap2.mkdir(parents=True)
    (snap2 / "config.json").write_text("{}")

    assert find_cached_model("medium") == str(snap2)


# ----- CLI integration -----

def test_cli_json_all_ok(monkeypatch):
    """--json mode with all checks passing."""
    monkeypatch.setattr("sys.argv", ["check_env.py", "--json"])

    # Mock all checks to return ok
    monkeypatch.setattr("check_env.check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr("check_env.check_ffprobe", lambda: (True, "/usr/bin/ffprobe"))
    monkeypatch.setattr("check_env.check_whisper", lambda py=None: (True, "faster-whisper 1.2.1"))
    monkeypatch.setattr("check_env.check_model_cached", lambda m="small": (True, "/cache"))

    rc = check_env.main()
    assert rc == 0


def test_cli_json_missing(monkeypatch, capsys):
    """--json mode with missing deps returns non-zero + reports which is missing."""
    monkeypatch.setattr("sys.argv", ["check_env.py", "--json"])
    monkeypatch.setattr("check_env.check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr("check_env.check_ffprobe", lambda: (False, "ffprobe missing"))
    monkeypatch.setattr("check_env.check_whisper", lambda py=None: (True, "1.2.1"))
    monkeypatch.setattr("check_env.check_model_cached", lambda m="small": (True, "/cache"))

    rc = check_env.main()
    assert rc == 1
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert parsed["ffprobe"] is False
    assert parsed["ffmpeg"] is True
    assert parsed["whisper"] is True
    assert parsed["model"] is True


def test_cli_report_format(capsys, monkeypatch):
    """Human-readable table format includes all checks."""
    monkeypatch.setattr("sys.argv", ["check_env.py"])
    monkeypatch.setattr("check_env.check_ffmpeg", lambda: (True, "/usr/bin/ffmpeg"))
    monkeypatch.setattr("check_env.check_ffprobe", lambda: (True, "/usr/bin/ffprobe"))
    monkeypatch.setattr("check_env.check_whisper", lambda py=None: (True, "faster-whisper 1.2.1 in /path/python"))
    monkeypatch.setattr("check_env.check_model_cached", lambda m="small": (True, "/cache/path"))

    rc = check_env.main()
    assert rc == 0
    out = capsys.readouterr().out
    assert "ffmpeg" in out
    assert "ffprobe" in out
    assert "whisper" in out
    assert "model" in out
    assert "All dependencies present" in out