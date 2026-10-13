#!/usr/bin/env python3
"""stage6_ffmpeg.py - ad-cut v0.4.1 Stage 6: ffmpeg trim+concat.

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
from typing import Any, Optional


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
    # Preserve extra fields (confidence, hit_text, etc.) for EDL sidecar traceability;
    # when merging overlaps, keep the FIRST item's extras.
    normalized = []
    for it in data:
        item = {"start": float(it["start"]), "end": float(it["end"])}
        for k, v in it.items():
            if k not in ("start", "end"):
                item[k] = v
        normalized.append(item)
    normalized.sort(key=lambda x: x["start"])

    merged: list[dict[str, Any]] = []
    for it in normalized:
        if merged and it["start"] < merged[-1]["end"]:
            merged[-1]["end"] = max(merged[-1]["end"], it["end"])
            # Keep first item's extras; do NOT overwrite with second item's extras
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


# ---------- mode selection (P0-3 from OPTIMIZATION-PLAN) ----------

def ffprobe_stream_info(ffmpeg_path: str, video: Path) -> dict:
    """Probe codec / bitrate / framerate for mode selection.

    Returns dict with keys: codec, bitrate_kbps, fps, has_audio. Missing
    fields are None. Pure parser — never fails, returns partial info.
    """
    info = {"codec": None, "bitrate_kbps": None, "fps": None, "has_audio": None}
    try:
        r = subprocess.run(
            [ffmpeg_path, "-i", str(video)],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        stderr = r.stderr or ""
        for line in stderr.splitlines():
            if line.strip().startswith("Duration:"):
                # Duration: 00:00:30.00, start: ..., bitrate: 188 kb/s
                if "bitrate:" in line:
                    try:
                        br_str = line.split("bitrate:")[1].split()[0]
                        info["bitrate_kbps"] = float(br_str)
                    except (ValueError, IndexError):
                        pass
            elif "Stream #0:0" in line and "Video:" in line:
                # "Stream #0:0(...): Video: h264 (High) ..., yuv420p, 320x240, 188 kb/s, 30 fps"
                if "h264" in line.lower():
                    info["codec"] = "h264"
                elif "hevc" in line.lower() or "h265" in line.lower():
                    info["codec"] = "hevc"
                if "fps" in line:
                    try:
                        # "30 fps" or "29.97 fps"
                        for tok in line.split(","):
                            if "fps" in tok:
                                fps_str = tok.strip().split()[0]
                                info["fps"] = float(fps_str)
                                break
                    except (ValueError, IndexError):
                        pass
            elif "Stream #0:1" in line and "Audio:" in line:
                info["has_audio"] = True
        # No audio stream at all?
        if info["has_audio"] is None and not any("Audio:" in l for l in stderr.splitlines()):
            info["has_audio"] = False
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return info


def list_encoders(ffmpeg_path: str) -> list[str]:
    """List h264 encoders in this ffmpeg build."""
    try:
        r = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, encoding="utf-8", errors="replace",
            timeout=15,
        )
        encs = []
        for line in r.stdout.splitlines():
            if "h264" in line.lower() and "encoder" in line.lower():
                parts = line.split()
                if len(parts) >= 3:
                    encs.append(parts[2])
        return encs
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


def pick_mode(
    stream_info: dict,
    encoders: list[str],
    force_reencode: bool = False,
) -> tuple[str, Optional[str]]:
    """Decide which mode to use for the cut.

    Returns:
      (mode, encoder) where mode ∈ {"copy", "reencode", "reencode_gpu"}
      encoder is None for copy / software, or the GPU encoder name.

    Decision logic:
      - force_reencode=True → pick best available re-encode path
      - source is h264 + bitrate < 2000 kbps → "copy" (already well-compressed)
      - encoders include libx264 → "reencode" (software)
      - GPU encoder available → "reencode_gpu"
      - else → "copy" (last resort: no re-encode possible)
    """
    if not force_reencode:
        if stream_info.get("codec") == "h264" and (stream_info.get("bitrate_kbps") or 0) < 2000:
            return ("copy", None)

    if "libx264" in encoders:
        return ("reencode", "libx264")
    # GPU priority order: NVIDIA > AMD > Intel > MediaFoundation > QSV
    for enc in ("h264_nvenc", "h264_amf", "h264_qsv", "h264_mf"):
        if enc in encoders:
            return ("reencode_gpu", enc)
    return ("copy", None)


def build_concat_demuxer_cmd(
    video: Path, keeps: list[tuple[float, float]], output: Path,
) -> tuple[list[str], str]:
    """Build ffmpeg concat demuxer command (stream copy, no re-encode).

    Returns (cmd, demuxer_filelist_content).
    The demuxer file is created in temp and cleaned up by caller.

    Format:
        ffmpeg -y -f concat -safe 0 -i list.txt -c copy output.mp4

    Each list.txt line: "file 'X'\ninpoint S\noutpoint E"
    """
    import tempfile
    fd, list_path = tempfile.mkstemp(suffix=".txt", prefix="adcut_concat_")
    import os
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            for s, e in keeps:
                f.write(f"file {video.as_posix()!r}\n")
                f.write(f"inpoint {s}\n")
                f.write(f"outpoint {e}\n")
    except Exception:
        os.unlink(list_path)
        raise

    cmd = [
        "ffmpeg", "-y",
        "-f", "concat", "-safe", "0",
        "-i", list_path,
        "-c", "copy",
        str(output),
    ]
    return cmd, list_path


def build_reencode_cmd(
    video: Path, keeps: list[tuple[float, float]], output: Path,
    encoder: str = "libx264",
) -> list[str]:
    """Build ffmpeg re-encode command (filter graph, GPU or software)."""
    filter_complex = build_filter_complex(keeps)
    cmd = [
        "ffmpeg", "-y", "-i", str(video),
        "-filter_complex", filter_complex,
        "-map", "[outv]", "-map", "[outa]",
        "-c:v", encoder, "-c:a", "aac",
        str(output),
    ]
    # GPU encoders need extra flags to avoid producing empty output
    if encoder in ("h264_nvenc", "h264_amf", "h264_qsv", "h264_mf"):
        # Insert -preset for nvenc, -rc for amf, etc. — keep it minimal
        pass
    return cmd


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 6 ffmpeg trim+concat (auto copy / reencode mode)",
    )
    parser.add_argument("--video", required=True, help="input video path")
    parser.add_argument("--edl", required=True, help="EDL JSON (list of cut segments)")
    parser.add_argument("--output", required=True, help="output mp4 path")
    parser.add_argument("--edl-out", help="write normalized (post-merge) EDL to this path")
    parser.add_argument(
        "--reencode", action="store_true",
        help="force re-encode (skip stream-copy auto-detection)",
    )
    parser.add_argument(
        "--encoder", default=None,
        help="explicit encoder (libx264, h264_nvenc, h264_amf, h264_qsv, h264_mf)",
    )
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
        r = subprocess.run(cmd, capture_output=True, text=True, encoding="utf-8", errors="replace")
        if r.returncode != 0:
            print(f"ERROR: ffmpeg failed (exit {r.returncode}):", file=sys.stderr)
            print(r.stderr[-1500:], file=sys.stderr)
            return 4
        print(f"[stage6] done (stream copy): {output}", file=sys.stderr)
        return 0

    # Mode selection (P0-3): auto pick copy / reencode / reencode_gpu
    ffmpeg_path = shutil.which("ffmpeg")
    stream_info = ffprobe_stream_info(ffmpeg_path, video)
    encoders = list_encoders(ffmpeg_path)
    mode, encoder = pick_mode(stream_info, encoders, force_reencode=args.reencode)
    if args.encoder:
        mode = "reencode"
        encoder = args.encoder
    print(
        f"[stage6] mode decision: source={stream_info} "
        f"→ mode={mode} encoder={encoder or '(stream-copy)'}",
        file=sys.stderr,
    )

    if mode == "copy":
        # Stream copy via concat demuxer (no re-encode, preserves fps/codec/bitrate)
        cmd, demuxer_path = build_concat_demuxer_cmd(video, keeps, output)
        if args.dry_run:
            print(f"[stage6] {len(keeps)} keep segments, mode=copy (concat demuxer)")
            print(f"[stage6] demuxer file: {demuxer_path}")
            print("--- demuxer content ---")
            print(Path(demuxer_path).read_text(encoding="utf-8"))
            print("--- end ---")
            print("[stage6] ffmpeg command:")
            print(" ".join(repr(c) for c in cmd))
            return 0
        try:
            r = subprocess.run(
                cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
            )
            if r.returncode != 0:
                print(f"ERROR: ffmpeg copy failed (exit {r.returncode}):", file=sys.stderr)
                print(r.stderr[-1500:], file=sys.stderr)
                return 4
        finally:
            try:
                Path(demuxer_path).unlink()
            except OSError:
                pass
    else:
        # Re-encode via filter graph (single interleaved concat)
        cmd = build_reencode_cmd(video, keeps, output, encoder=encoder or "libx264")
        if args.dry_run:
            print(f"[stage6] {len(keeps)} keep segments, mode={mode} encoder={encoder}")
            filter_complex = build_filter_complex(keeps)
            print("[stage6] filter_complex:")
            print(filter_complex)
            print("\n[stage6] ffmpeg command:")
            print(" ".join(repr(c) for c in cmd))
            return 0
        r = subprocess.run(
            cmd, capture_output=True, text=True, encoding="utf-8", errors="replace",
        )
        if r.returncode != 0:
            print(f"ERROR: ffmpeg {mode} failed (exit {r.returncode}):", file=sys.stderr)
            # Dump full + tail for diagnostics
            print("--- ffmpeg stderr (full) ---", file=sys.stderr)
            print(r.stderr or "(empty)", file=sys.stderr)
            if r.stdout:
                print("--- ffmpeg stdout ---", file=sys.stderr)
                print(r.stdout, file=sys.stderr)
            print("--- ffmpeg stderr (last 500 chars) ---", file=sys.stderr)
            print((r.stderr or "")[-500:], file=sys.stderr)
            print("--- end ---", file=sys.stderr)
            return 4

    # Verify output duration + size sanity
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
        # Sanity check: stream-copy should not significantly bloat file size
        in_size = video.stat().st_size
        out_size = output.stat().st_size
        if in_size > 0 and out_size > in_size * 1.5 and mode == "copy":
            print(
                f"WARN: stream-copy output is {out_size / in_size:.1f}x larger than input "
                f"(unexpected; this usually means codec differs between cuts)",
                file=sys.stderr,
            )
    except Exception as e:
        print(f"WARN: could not probe output duration: {e}", file=sys.stderr)
        print(f"[stage6] done: {output}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())