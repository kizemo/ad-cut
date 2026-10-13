#!/usr/bin/env python3
"""stage6_ffmpeg.py - ad-cut v0.5.0 Stage 6: ffmpeg trim+concat.

Reads EDL (list of cut segments), inverts to keep segments on [0, duration],
generates ffmpeg filter_complex with **single interleaved concat**, runs ffmpeg.

**KEY FIX (VERIFY-FINDING-03)**:
  Single concat with interleaved inputs `[v0][a0][v1][a1]...concat=n=N:v=1:a=1[outv][outa]`.
  DO NOT split into `v⊂concat + a⊂concat` — those two parallel filters trigger
  "Media type mismatch" errors. Single concat is stable.

Usage:
    python stage6_ffmpeg.py --video <input.mp4> --edl <edl.json> --output <output.mp4>
                            [--edl-out <edl.json>] [--dry-run]

Exit codes:
    0  success
    1  bad usage / file not found / EDL schema invalid
    2  ffmpeg not in PATH / ffprobe failed
    3  keep segments empty (entire video cut)
    4  ffmpeg run failed
"""
from __future__ import annotations

import argparse
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any


def check_ffmpeg() -> None:
    """Fail fast if ffmpeg is not in PATH."""
    if shutil.which("ffmpeg") is None:
        print("ERROR: ffmpeg not in PATH. Install with: winget install ffmpeg", file=sys.stderr)
        sys.exit(2)


def ffprobe_duration(video: Path) -> float:
    """Return video duration in seconds.

    Tries ffprobe first (canonical); falls back to parsing `ffmpeg -i` output
    when ffprobe is unavailable or its DLLs are not on PATH (common on
    Windows when ffmpeg is installed via winget but ffprobe isn't).
    """
    # Try ffprobe first
    try:
        r = subprocess.run(
            ["ffprobe", "-v", "error", "-show_entries", "format=duration",
             "-of", "csv=p=0", str(video)],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            return float(r.stdout.strip())
    except (FileNotFoundError, subprocess.TimeoutExpired, ValueError):
        pass

    # Fallback: parse ffmpeg -i stderr for Duration: HH:MM:SS.xx
    try:
        r = subprocess.run(
            ["ffmpeg", "-i", str(video)],
            capture_output=True, text=True, timeout=15,
        )
        # ffmpeg -i prints "Duration: HH:MM:SS.xx, start: ..." to stderr
        # Exit code is 1 (because no output specified), that's fine
        for line in (r.stderr or "").splitlines():
            if line.startswith("  Duration:"):
                dur_str = line.split(",")[0].split("Duration:")[1].strip()
                h, m, s = dur_str.split(":")
                return float(h) * 3600 + float(m) * 60 + float(s)
        raise RuntimeError(f"could not parse Duration from ffmpeg -i output: {r.stderr[:500]}")
    except (FileNotFoundError, subprocess.TimeoutExpired) as e:
        raise RuntimeError(f"ffprobe and ffmpeg both failed: {e}")


def load_and_validate_edl(edl_path: Path) -> list[dict[str, Any]]:
    """Load EDL (list of cuts), validate schema, sort by start, merge overlaps.

    Returns: normalized list of {start, end} (overlaps collapsed).
    """
    try:
        data = json.loads(edl_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: EDL JSON decode failed: {e}", file=sys.stderr)
        sys.exit(1)

    if not isinstance(data, list):
        print(f"ERROR: EDL not a list (got {type(data).__name__})", file=sys.stderr)
        sys.exit(1)

    # Validate shape
    for i, item in enumerate(data):
        if not isinstance(item, dict):
            print(f"ERROR: EDL[{i}] not a dict: {item!r}", file=sys.stderr)
            sys.exit(1)
        if "start" not in item or "end" not in item:
            print(f"ERROR: EDL[{i}] missing start/end: {item!r}", file=sys.stderr)
            sys.exit(1)
        if not isinstance(item["start"], (int, float)) or not isinstance(item["end"], (int, float)):
            print(f"ERROR: EDL[{i}] start/end not numeric: {item!r}", file=sys.stderr)
            sys.exit(1)
        if item["end"] <= item["start"]:
            print(f"ERROR: EDL[{i}] end <= start: {item!r}", file=sys.stderr)
            sys.exit(1)

    # Sort by start, merge overlaps (clamp to [0, +∞))
    data = sorted([{"start": float(it["start"]), "end": float(it["end"])} for it in data],
                  key=lambda x: x["start"])
    merged: list[dict[str, Any]] = []
    for it in data:
        if merged and it["start"] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], it["end"])
        else:
            merged.append(dict(it))
    return merged


def invert_cuts_to_keep(
    cuts: list[dict[str, Any]], total: float,
) -> list[tuple[float, float]]:
    """Invert cut list on [0, total] → keep list of (start, end) tuples.

    Handles edge cases:
      - cut at start [0, s]: no keep before it
      - cut at end [e, total]: no keep after it
      - cuts covering entire video: returns []
    """
    keeps: list[tuple[float, float]] = []
    cur = 0.0
    for c in cuts:
        s = max(0.0, min(float(c["start"]), total))
        e = max(0.0, min(float(c["end"]), total))
        if s > cur + 0.001:  # small epsilon
            keeps.append((cur, s))
        cur = max(cur, e)
    if cur + 0.001 < total:
        keeps.append((cur, total))
    return keeps


def build_filter_complex(keeps: list[tuple[float, float]]) -> str:
    """Build ffmpeg filter_complex string with **single interleaved concat**.

    Pattern per keep segment (filter_complex syntax: stream label in [brackets]):
      [0:v]trim=start=S:end=E,setpts=PTS-STARTPTS[v_i]
      [0:a]atrim=start=S:end=E,asetpts=PTS-STARTPTS[a_i]

    Concat (single, NOT split into v⊂ + a⊂):
      [v0][a0][v1][a1]...[vN-1][aN-1]concat=n=N:v=1:a=1[outv][outa]
    """
    parts: list[str] = []
    for i, (s, e) in enumerate(keeps):
        parts.append(f"[0:v]trim=start={s}:end={e},setpts=PTS-STARTPTS[v{i}]")
        parts.append(f"[0:a]atrim=start={s}:end={e},asetpts=PTS-STARTPTS[a{i}]")

    inputs = "".join(f"[v{i}][a{i}]" for i in range(len(keeps)))
    n = len(keeps)
    parts.append(f"{inputs}concat=n={n}:v=1:a=1[outv][outa]")
    return ";".join(parts)


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 6 ffmpeg trim+concat (single interleaved concat)",
    )
    parser.add_argument("--video", required=True, help="input video path")
    parser.add_argument("--edl", required=True, help="EDL JSON (list of cut segments)")
    parser.add_argument("--output", required=True, help="output mp4 path")
    parser.add_argument("--edl-out", help="write normalized (post-merge) EDL to this path")
    parser.add_argument(
        "--dry-run", action="store_true",
        help="print filter graph + ffmpeg cmd without running",
    )
    args = parser.parse_args()

    check_ffmpeg()

    video = Path(args.video)
    edl_path = Path(args.edl)
    output = Path(args.output)

    if not video.exists():
        print(f"ERROR: video not found: {video}", file=sys.stderr)
        return 1
    if not edl_path.exists():
        print(f"ERROR: EDL not found: {edl_path}", file=sys.stderr)
        return 1

    cuts = load_and_validate_edl(edl_path)

    try:
        total = ffprobe_duration(video)
    except (RuntimeError, ValueError) as e:
        print(f"ERROR: {e}", file=sys.stderr)
        return 2

    keeps = invert_cuts_to_keep(cuts, total)

    # Write normalized EDL if requested (post-merge cuts, sorted)
    if args.edl_out:
        edl_out = Path(args.edl_out)
        edl_out.parent.mkdir(parents=True, exist_ok=True)
        edl_out.write_text(
            json.dumps(cuts, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    # Edge case: no keep segments (entire video cut)
    if not keeps:
        print(
            "[stage6] ERROR: keep segments empty (entire video would be cut). "
            "Cannot produce output.",
            file=sys.stderr,
        )
        return 3

    # Edge case: no cuts → stream copy (no filter)
    if not cuts:
        cmd = ["ffmpeg", "-y", "-i", str(video), "-c", "copy", str(output)]
        if args.dry_run:
            print("[stage6] (0 cuts → stream copy)")
            print(" ".join(repr(c) for c in cmd))
            return 0
        print(f"[stage6] 0 cuts → stream copy → {output}", file=sys.stderr)
        r = subprocess.run(cmd, capture_output=True, text=True)
        if r.returncode != 0:
            print(f"ERROR: ffmpeg failed (exit {r.returncode}):", file=sys.stderr)
            print(r.stderr[-1500:], file=sys.stderr)
            return 4
        print(f"[stage6] done (stream copy): {output}", file=sys.stderr)
        return 0

    # Build filter graph + run ffmpeg
    filter_complex = build_filter_complex(keeps)
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", "libx264", "-c:a", "aac",
        str(output),
    ]

    if args.dry_run:
        print(f"[stage6] {len(keeps)} keep segments from {len(cuts)} cuts")
        print("[stage6] filter_complex:")
        print(filter_complex)
        print("\n[stage6] ffmpeg command:")
        print(" ".join(repr(c) for c in cmd))
        return 0

    print(
        f"[stage6] running ffmpeg: {len(keeps)} keep segments, "
        f"expected output ≈ {sum(e - s for s, e in keeps):.1f}s",
        file=sys.stderr,
    )
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(f"ERROR: ffmpeg failed (exit {r.returncode}):", file=sys.stderr)
        # Show last 1500 chars of stderr (most useful)
        print(r.stderr[-1500:], file=sys.stderr)
        return 4

    # Verify output duration
    try:
        out_dur = ffprobe_duration(output)
        expected = sum(e - s for s, e in keeps)
        print(
            f"[stage6] done: input {total:.1f}s → output {out_dur:.1f}s "
            f"(expected ≈ {expected:.1f}s, Δ={out_dur - expected:+.1f}s)",
            file=sys.stderr,
        )
        if abs(out_dur - expected) > 1.0:
            print(
                f"WARN: output duration differs from expected by "
                f"{out_dur - expected:+.1f}s",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"WARN: could not probe output duration: {e}", file=sys.stderr)
        print(f"[stage6] done: {output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())