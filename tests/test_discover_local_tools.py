"""test_discover_local_tools.py - unit tests for scripts/discover_local_tools.py

Covers:
  - _glob_first: glob with absolute paths and drive letters (pathlib doesn't support)
  - probe_path_tools: shutil.which mocking
  - probe_known_ffmpeg: Windows path discovery
  - probe_pythons: each python's faster-whisper status
  - probe_hf_cache: $HF_HOME respects
  - probe_gpu: graceful failure
  - collect: integration
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import discover_local_tools as dlt  # noqa: E402


# ----- _glob_first -----

def test_glob_first_finds_file(tmp_path):
    target = tmp_path / "ffmpeg.exe"
    target.write_text("dummy")
    pattern = str(tmp_path / "ffmpeg.exe").replace("\\", "/")
    assert dlt._glob_first(pattern) == target


def test_glob_first_with_glob_wildcard(tmp_path):
    (tmp_path / "JianyingPro").mkdir()
    (tmp_path / "JianyingPro" / "10.9.0.14199").mkdir()
    target = tmp_path / "JianyingPro" / "10.9.0.14199" / "ffmpeg.exe"
    target.write_text("dummy")
    pattern = str(tmp_path).replace("\\", "/") + "/JianyingPro/*/ffmpeg.exe"
    result = dlt._glob_first(pattern)
    assert result == target


def test_glob_first_no_match(tmp_path):
    pattern = str(tmp_path / "nope.exe").replace("\\", "/")
    assert dlt._glob_first(pattern) is None


# ----- probe_path_tools -----

def test_probe_path_tools_both(monkeypatch):
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: f"/usr/bin/{cmd}" if cmd in ("ffmpeg", "ffprobe") else None)
    result = dlt.probe_path_tools()
    assert result == {"ffmpeg": "/usr/bin/ffmpeg", "ffprobe": "/usr/bin/ffprobe"}


def test_probe_path_tools_missing(monkeypatch):
    monkeypatch.setattr("discover_local_tools.shutil.which", lambda cmd: None)
    result = dlt.probe_path_tools()
    assert result == {"ffmpeg": None, "ffprobe": None}


# ----- probe_pythons -----

def test_probe_pythons_finds_faster_whisper(monkeypatch):
    """Mock shutil.which + subprocess.run for python check."""
    # Only "python" in PATH
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: "/usr/bin/python" if cmd == "python" else None)

    fake_run = MagicMock(returncode=0, stdout="1.2.1", stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_run)

    # Skip py launcher
    result = dlt.probe_pythons()
    assert len(result) >= 1
    has_fw = [p for p in result if p.get("faster_whisper") == "1.2.1"]
    assert has_fw, f"expected at least one python with faster-whisper: {result}"


def test_probe_pythons_no_faster_whisper(monkeypatch):
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: "/usr/bin/python" if cmd == "python" else None)
    fake_run = MagicMock(returncode=1, stdout="", stderr="ModuleNotFoundError")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_run)
    result = dlt.probe_pythons()
    assert all(p.get("faster_whisper") is None for p in result)


# ----- probe_hf_cache -----

def test_probe_hf_cache_no_env(monkeypatch, tmp_path):
    """Without HF_HOME, defaults to ~/.cache/huggingface/hub."""
    monkeypatch.delenv("HF_HOME", raising=False)
    monkeypatch.setattr("pathlib.Path.home", lambda: tmp_path)
    result = dlt.probe_hf_cache()
    assert result["path"] == str(tmp_path / ".cache" / "huggingface" / "hub")
    assert result["models"] == []


def test_probe_hf_cache_with_env(monkeypatch, tmp_path):
    """HF_HOME env var is respected."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    result = dlt.probe_hf_cache()
    assert result["path"] == str(tmp_path / "hub")
    assert result["models"] == []


def test_probe_hf_cache_finds_models(monkeypatch, tmp_path):
    """Discovers Systran/faster-whisper-* model snapshots."""
    monkeypatch.setenv("HF_HOME", str(tmp_path))
    snap = tmp_path / "hub" / "models--Systran--faster-whisper-small" / "snapshots" / "rev1"
    snap.mkdir(parents=True)
    (snap / "config.json").write_text("{}")
    result = dlt.probe_hf_cache()
    assert len(result["models"]) == 1
    assert result["models"][0]["name"] == "small"


# ----- probe_gpu graceful failure -----

def test_probe_gpu_no_powershell(monkeypatch):
    """If powershell missing, returns empty without raising."""
    def raise_fnf(*a, **kw):
        raise FileNotFoundError("powershell")
    monkeypatch.setattr("subprocess.run", raise_fnf)
    result = dlt.probe_gpu()
    assert result == {"vendor": None, "name": None}


# ----- collect integration -----

def test_collect_returns_complete_dict(monkeypatch, tmp_path):
    """End-to-end: all probes return sensible data; structure is consistent."""
    # Mock everything to known good state
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: f"/usr/bin/{cmd}" if cmd in ("ffmpeg", "ffprobe", "python") else None)
    fake_run = MagicMock(returncode=0, stdout="1.2.1", stderr="")
    monkeypatch.setattr("subprocess.run", lambda *a, **kw: fake_run)

    # Empty HF cache
    monkeypatch.setenv("HF_HOME", str(tmp_path))

    result = dlt.collect()
    assert "ffmpeg" in result
    # ffprobe is nested inside ffmpeg dict
    assert "ffprobe" in result["ffmpeg"]
    assert "python" in result
    assert "huggingface_cache" in result
    assert "gpu" in result
    assert "needs_download" in result
    assert result["needs_download"]["model"] is True  # empty cache


# ----- CLI smoke -----

def test_cli_quiet_mode(monkeypatch, capsys):
    """--quiet emits a single summary line."""
    monkeypatch.setattr("sys.argv", ["dlt.py", "--quiet"])
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: f"/usr/bin/{cmd}" if cmd in ("ffmpeg", "ffprobe", "python") else None)
    monkeypatch.setattr("subprocess.run", MagicMock(returncode=0, stdout="1.2.1", stderr=""))
    monkeypatch.setenv("HF_HOME", "/tmp/nonexistent_hf_test_dir")

    rc = dlt.main()
    out = capsys.readouterr().out
    assert "ffmpeg=" in out
    assert "python=" in out
    assert "model=" in out


def test_cli_json_mode(monkeypatch, capsys):
    """--json emits parseable JSON."""
    monkeypatch.setattr("sys.argv", ["dlt.py", "--json"])
    monkeypatch.setattr("discover_local_tools.shutil.which",
                        lambda cmd: "/usr/bin/ffmpeg" if cmd == "ffmpeg" else None)
    monkeypatch.setattr("subprocess.run", MagicMock(returncode=0, stdout="1.2.1", stderr=""))
    monkeypatch.setenv("HF_HOME", "/tmp/nonexistent")

    rc = dlt.main()
    out = capsys.readouterr().out
    parsed = json.loads(out)
    assert "ffmpeg" in parsed
    assert "needs_download" in parsed