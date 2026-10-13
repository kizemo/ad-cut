"""test_transcribe.py - unit tests for bin/transcribe.py

Covers:
  - argparse: missing args, wrong number of args → exit 1
  - video not found → exit 1
  - faster-whisper ImportError → exit 2
  - happy path: mock WhisperModel, verify output JSON schema
  - env var overrides (ADCUT_WHISPER_MODEL / LANG)

Run: python -m pytest tests/test_transcribe.py -x -v
"""
from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock

import pytest

# Make bin/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
BIN_DIR = REPO_ROOT / "bin"
sys.path.insert(0, str(BIN_DIR))


# ----- fixtures -----

class _FakeWord:
    def __init__(self, start: float, end: float, word: str):
        self.start = start
        self.end = end
        self.word = word


class _FakeSegment:
    def __init__(self, start: float, end: float, text: str, words):
        self.start = start
        self.end = end
        self.text = text
        self.words = words


class _FakeInfo:
    def __init__(self, duration: float = 60.0, language: str = "zh"):
        self.duration = duration
        self.language = language


def _install_fake_faster_whisper(monkeypatch, segments, info):
    """Install a fake faster_whisper module into sys.modules."""
    fake_model_instance = MagicMock()
    fake_model_instance.transcribe = lambda *a, **kw: (iter(segments), info)

    fake_faster_whisper = MagicMock()
    fake_faster_whisper.WhisperModel = lambda *a, **kw: fake_model_instance

    monkeypatch.setitem(sys.modules, "faster_whisper", fake_faster_whisper)


# ----- tests -----

def test_no_args_exits_1(capsys, monkeypatch):
    """transcribe.py with no args: print usage to stderr + exit 1."""
    monkeypatch.setattr(sys, "argv", ["transcribe.py"])
    # Need to re-import to get fresh sys.argv behavior (the module-level import is
    # already cached; main() reads sys.argv at runtime, so this works)
    from transcribe import main
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    captured = capsys.readouterr()
    assert "Usage" in captured.err


def test_video_not_found_exits_1(capsys, monkeypatch, tmp_path):
    """transcribe.py with non-existent video: exit 1."""
    fake_video = tmp_path / "nonexistent.mp4"
    fake_output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(fake_video), str(fake_output)])

    from transcribe import main
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 1
    captured = capsys.readouterr()
    assert "not found" in captured.err


def test_faster_whisper_not_installed_exits_2(capsys, monkeypatch, tmp_path):
    """When faster_whisper raises ImportError: exit 2."""
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(fake_video), str(fake_output)])

    # Ensure not in sys.modules
    monkeypatch.delitem(sys.modules, "faster_whisper", raising=False)

    # Patch builtins.__import__ to raise on faster_whisper
    import builtins
    real_import = builtins.__import__

    def mock_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "faster_whisper" or name.startswith("faster_whisper."):
            raise ImportError("mocked: faster-whisper not installed")
        return real_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", mock_import)

    from transcribe import main
    with pytest.raises(SystemExit) as e:
        main()
    assert e.value.code == 2
    captured = capsys.readouterr()
    assert "faster-whisper" in captured.err
    assert "pip install" in captured.err


def test_happy_path_default_args(capsys, monkeypatch, tmp_path):
    """Happy path with default model=small, lang=zh, device=cpu, compute=int8."""
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(fake_video), str(fake_output)])

    # Strip env vars so we test defaults
    for var in ("ADCUT_WHISPER_MODEL", "ADCUT_WHISPER_LANG", "ADCUT_WHISPER_DEVICE", "ADCUT_WHISPER_COMPUTE"):
        monkeypatch.delenv(var, raising=False)

    fake_segments = [
        _FakeSegment(0.0, 5.0, "大家好", [_FakeWord(0.0, 1.0, "大"), _FakeWord(1.0, 2.0, "家")]),
        _FakeSegment(5.0, 10.0, "今天讲", [_FakeWord(5.0, 6.0, "今"), _FakeWord(6.0, 7.0, "天")]),
    ]
    fake_info = _FakeInfo(duration=10.0, language="zh")
    _install_fake_faster_whisper(monkeypatch, fake_segments, fake_info)

    from transcribe import main
    main()  # should exit 0, no exception

    # Verify output JSON
    assert fake_output.exists()
    data = json.loads(fake_output.read_text(encoding="utf-8"))
    assert data["video"] == str(fake_video.resolve())
    assert data["duration"] == 10.0
    assert data["language"] == "zh"
    assert data["model"] == "small"
    assert len(data["segments"]) == 2

    seg0 = data["segments"][0]
    assert seg0["start"] == 0.0
    assert seg0["end"] == 5.0
    assert seg0["text"] == "大家好"
    assert len(seg0["words"]) == 2
    assert seg0["words"][0]["word"] == "大"
    assert seg0["words"][1]["word"] == "家"

    seg1 = data["segments"][1]
    assert seg1["text"] == "今天讲"


def test_env_var_overrides(capsys, monkeypatch, tmp_path):
    """ADCUT_WHISPER_MODEL and LANG env vars are honored."""
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(fake_video), str(fake_output)])

    monkeypatch.setenv("ADCUT_WHISPER_MODEL", "large-v3")
    monkeypatch.setenv("ADCUT_WHISPER_LANG", "en")

    fake_segments = []
    fake_info = _FakeInfo(duration=0.0, language="en")
    _install_fake_faster_whisper(monkeypatch, fake_segments, fake_info)

    from transcribe import main
    main()

    data = json.loads(fake_output.read_text(encoding="utf-8"))
    assert data["model"] == "large-v3"
    assert data["language"] == "en"


def test_empty_words_segment(capsys, monkeypatch, tmp_path):
    """Segments with no words (None) are handled gracefully."""
    fake_video = tmp_path / "fake.mp4"
    fake_video.write_bytes(b"\x00" * 1024)
    fake_output = tmp_path / "out.json"
    monkeypatch.setattr(sys, "argv", ["transcribe.py", str(fake_video), str(fake_output)])

    for var in ("ADCUT_WHISPER_MODEL", "ADCUT_WHISPER_LANG", "ADCUT_WHISPER_DEVICE", "ADCUT_WHISPER_COMPUTE"):
        monkeypatch.delenv(var, raising=False)

    # Segment with words=None
    fake_segments = [
        _FakeSegment(0.0, 5.0, "大家好", [_FakeWord(0.0, 1.0, "大")]),
        _FakeSegment(5.0, 10.0, "今天讲", None),
    ]
    fake_info = _FakeInfo(duration=10.0, language="zh")
    _install_fake_faster_whisper(monkeypatch, fake_segments, fake_info)

    from transcribe import main
    main()

    data = json.loads(fake_output.read_text(encoding="utf-8"))
    assert len(data["segments"]) == 2
    assert data["segments"][0]["words"] == [{"start": 0.0, "end": 1.0, "word": "大"}]
    # Segment 1 with words=None becomes empty list
    assert data["segments"][1]["words"] == []