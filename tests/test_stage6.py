"""test_stage6.py - tests for scripts/stage6_ffmpeg.py

Covers:
  - invert_cuts_to_keep: basic, at-start, at-end, full-coverage, overlaps
  - build_filter_complex: verifies **single interleaved concat** (VERIFY-FINDING-03)
  - load_and_validate_edl: schema validation + sort + merge
  - End-to-end smoke: real ffmpeg run on synthetic 30s video, cut [10,12] → 28s

Run: python -m pytest tests/test_stage6.py -x -v
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

# Make scripts/ importable
REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPTS_DIR = REPO_ROOT / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

from stage6_ffmpeg import (  # noqa: E402
    build_filter_complex,
    invert_cuts_to_keep,
    load_and_validate_edl,
)


# ----- unit tests for invert_cuts_to_keep -----

def test_invert_basic_middle_cut():
    """Cut in the middle of video → keeps before and after."""
    cuts = [{"start": 10.0, "end": 12.0}]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == [(0.0, 10.0), (12.0, 30.0)]


def test_invert_cut_at_start():
    """Cut at start of video → no keep before, keep rest."""
    cuts = [{"start": 0.0, "end": 5.0}]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == [(5.0, 30.0)]


def test_invert_cut_at_end():
    """Cut at end of video → keep start, no keep after."""
    cuts = [{"start": 25.0, "end": 30.0}]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == [(0.0, 25.0)]


def test_invert_full_coverage():
    """Cut covering entire video → no keep segments."""
    cuts = [{"start": 0.0, "end": 30.0}]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == []


def test_invert_multiple_cuts():
    """Multiple cuts → alternating keep segments."""
    cuts = [
        {"start": 5.0, "end": 7.0},
        {"start": 15.0, "end": 18.0},
        {"start": 25.0, "end": 27.0},
    ]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == [
        (0.0, 5.0),
        (7.0, 15.0),
        (18.0, 25.0),
        (27.0, 30.0),
    ]


def test_invert_overlapping_cuts_merged_at_input():
    """Overlapping cuts at input layer should be merged by load_and_validate_edl
    before invert; this test verifies the simple case via direct call."""
    # If cuts are pre-merged (as expected after load_and_validate_edl), this works.
    cuts = [{"start": 10.0, "end": 18.0}]  # pre-merged from [10,15] + [15,18]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    assert keeps == [(0.0, 10.0), (18.0, 30.0)]


def test_invert_clamp_cuts_to_video_bounds():
    """Cuts exceeding video bounds should be clamped."""
    cuts = [{"start": -5.0, "end": 5.0}, {"start": 25.0, "end": 35.0}]
    keeps = invert_cuts_to_keep(cuts, total=30.0)
    # [-5, 5] clamped to [0, 5] → no keep before
    # [25, 35] clamped to [25, 30] → no keep after
    assert keeps == [(5.0, 25.0)]


# ----- unit tests for build_filter_complex -----

def test_filter_complex_single_interleaved_concat():
    """VERIFY-FINDING-03 fix: must use single concat with interleaved inputs.

    Splits into v⊂concat + a⊂concat would trigger Media type mismatch.
    """
    keeps = [(0.0, 10.0), (12.0, 30.0)]
    fc = build_filter_complex(keeps)

    # Should contain exactly ONE concat (not split)
    assert fc.count("concat=") == 1, f"expected 1 concat, got {fc.count('concat='): fc}"

    # Should have interleaved [v0][a0][v1][a1] inputs
    assert "[v0][a0][v1][a1]" in fc, f"interleaved inputs not found: {fc}"

    # Concat params must include v=1:a=1
    assert "concat=n=2:v=1:a=1" in fc

    # Output labels [outv][outa]
    assert "[outv][outa]" in fc

    # Each keep segment has trim + setpts + label
    assert "[0:v]trim=start=0.0:end=10.0" in fc
    assert "[0:a]atrim=start=0.0:end=10.0" in fc
    assert "[0:v]trim=start=12.0:end=30.0" in fc


def test_filter_complex_single_segment():
    """Single keep segment (n=1) is also valid."""
    fc = build_filter_complex([(0.0, 30.0)])
    assert "[v0][a0]concat=n=1:v=1:a=1[outv][outa]" in fc


def test_filter_complex_three_segments():
    """Three keep segments → six trim filters + 1 concat with n=3."""
    keeps = [(0.0, 5.0), (7.0, 15.0), (18.0, 30.0)]
    fc = build_filter_complex(keeps)
    assert "[v0][a0][v1][a1][v2][a2]concat=n=3:v=1:a=1[outv][outa]" in fc


# ----- unit tests for load_and_validate_edl -----

def test_load_edl_validates_schema_missing_keys(tmp_path):
    """EDL with item missing 'end' should exit 1."""
    edl = tmp_path / "bad.json"
    edl.write_text(json.dumps([{"start": 10.0}]), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_and_validate_edl(edl)
    assert e.value.code == 1


def test_load_edl_validates_end_lt_start(tmp_path):
    """EDL with end <= start should exit 1."""
    edl = tmp_path / "bad.json"
    edl.write_text(json.dumps([{"start": 10.0, "end": 5.0}]), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_and_validate_edl(edl)
    assert e.value.code == 1


def test_load_edl_validates_non_list(tmp_path):
    """EDL that's not a list should exit 1."""
    edl = tmp_path / "bad.json"
    edl.write_text(json.dumps({"start": 10.0, "end": 12.0}), encoding="utf-8")
    with pytest.raises(SystemExit) as e:
        load_and_validate_edl(edl)
    assert e.value.code == 1


def test_load_edl_sorts_and_merges_overlaps(tmp_path):
    """EDL with out-of-order + overlapping cuts gets sorted and merged."""
    edl = tmp_path / "edl.json"
    edl.write_text(
        json.dumps([
            {"start": 15.0, "end": 18.0},
            {"start": 5.0, "end": 8.0},
            {"start": 6.0, "end": 12.0},  # overlaps with [5,8]
        ]),
        encoding="utf-8",
    )
    result = load_and_validate_edl(edl)
    # After sort: [(5,8), (6,12), (15,18)]
    # After merge: [(5,12), (15,18)]
    assert result == [{"start": 5.0, "end": 12.0}, {"start": 15.0, "end": 18.0}]


def test_load_edl_empty_list(tmp_path):
    """Empty EDL returns empty list (no error)."""
    edl = tmp_path / "empty.json"
    edl.write_text("[]", encoding="utf-8")
    assert load_and_validate_edl(edl) == []


def test_load_edl_preserves_extra_fields(tmp_path):
    """EDL items may carry confidence / hit_text; loader must preserve them for traceability."""
    edl = tmp_path / "rich.json"
    edl.write_text(json.dumps([
        {"start": 10.0, "end": 12.0, "is_ad": True, "confidence": 0.95, "hit_text": "赞助"},
        {"start": 20.0, "end": 22.0, "is_ad": False, "confidence": 0.85, "hit_text": "爸爸妈妈"},
    ]), encoding="utf-8")
    result = load_and_validate_edl(edl)
    assert len(result) == 2
    assert result[0]["confidence"] == 0.95
    assert result[0]["hit_text"] == "赞助"
    assert result[0]["is_ad"] is True
    assert result[1]["confidence"] == 0.85
    assert result[1]["is_ad"] is False


def test_load_edl_merge_keeps_first_item_extras(tmp_path):
    """When merging overlaps, keep FIRST item's extra fields (not last)."""
    edl = tmp_path / "merge_extras.json"
    edl.write_text(json.dumps([
        {"start": 10.0, "end": 15.0, "is_ad": True, "confidence": 0.92, "hit_text": "first"},
        {"start": 13.0, "end": 18.0, "is_ad": True, "confidence": 0.99, "hit_text": "second"},
    ]), encoding="utf-8")
    result = load_and_validate_edl(edl)
    # After merge: [{start:10, end:18, ...first_extras}]
    assert len(result) == 1
    assert result[0]["start"] == 10.0
    assert result[0]["end"] == 18.0
    assert result[0]["hit_text"] == "first", "merge must keep FIRST item's extras"
    assert result[0]["confidence"] == 0.92


# ----- end-to-end smoke test (real ffmpeg) -----

@pytest.mark.skipif(shutil.which("ffmpeg") is None, reason="ffmpeg not in PATH")
def test_ffmpeg_smoke_30s_single_cut(tmp_path):
    """Generate 30s synthetic video → run stage6 → verify 28s output.

    This is the smoke test that proves the single-interleaved-concat actually
    produces a valid MP4 with both audio and video streams.
    """
    # Skip if ffprobe not loadable (we use ffmpeg -i fallback, so this should be fine)
    video = tmp_path / "test.mp4"
    cmd_gen = [
        "ffmpeg", "-y", "-f", "lavfi",
        "-i", "testsrc=duration=30:size=320x240:rate=10",
        "-f", "lavfi",
        "-i", "sine=frequency=440:duration=30",
        "-c:v", "libx264", "-c:a", "aac", "-shortest",
        str(video),
    ]
    r = subprocess.run(cmd_gen, capture_output=True, text=True)
    assert r.returncode == 0, f"test video gen failed: {r.stderr[-500:]}"
    assert video.exists()

    edl = tmp_path / "edl.json"
    edl.write_text(json.dumps([{"start": 10.0, "end": 12.0}]), encoding="utf-8")

    output = tmp_path / "out.mp4"

    # Run stage6_ffmpeg.py via subprocess (test the CLI, not just functions)
    cmd_run = [
        sys.executable, str(SCRIPTS_DIR / "stage6_ffmpeg.py"),
        "--video", str(video),
        "--edl", str(edl),
        "--output", str(output),
    ]
    r = subprocess.run(cmd_run, capture_output=True, text=True)
    assert r.returncode == 0, f"stage6 failed: {r.stderr[-1000:]}"
    assert output.exists()

    # Verify output duration via ffmpeg -i (avoids ffprobe dependency)
    r = subprocess.run(
        ["ffmpeg", "-i", str(output)],
        capture_output=True, text=True,
    )
    # ffmpeg -i exits 1 (no output spec), but stderr contains "Duration:"
    dur_line = next((l for l in r.stderr.splitlines() if "Duration:" in l), None)
    assert dur_line is not None, f"no Duration line in: {r.stderr[:500]}"
    # Format: "Duration: HH:MM:SS.xx, ..."
    dur_str = dur_line.split("Duration:")[1].split(",")[0].strip()
    h, m, s = dur_str.split(":")
    dur_seconds = float(h) * 3600 + float(m) * 60 + float(s)
    # 30s - 2s cut = 28s ±0.5s tolerance
    assert 27.5 <= dur_seconds <= 28.5, f"expected ~28s, got {dur_seconds:.2f}s"

    # Verify both audio and video streams exist (parse stderr for Stream lines)
    assert "Stream #0:0: Video" in r.stderr or "Video:" in r.stderr, "no video stream"
    assert "Audio:" in r.stderr, "no audio stream"