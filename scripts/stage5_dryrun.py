#!/usr/bin/env python3
"""stage5_dryrun.py - ad-cut v0.5.0 Stage 5: merge + dry-run + STOP gate.

Reads judged.json (Stage 4), merges adjacent cuts, prints a human-readable
table of segments to stdout, writes the same table to dryrun.txt.

**STOP gate**: this script NEVER invokes Stage 6. The caller (typically
the SKILL.md orchestrator or run_pipeline.sh in interactive mode) reads
the user's reply (`y`/`n`/`adjust`) and decides whether to proceed.

Usage:
    python stage5_dryrun.py <judged.json> <dryrun.txt> [--transcript <t.json>] [--merge-gap 5.0]

Exit codes:
    0  dry-run table printed + dryrun.txt written
    1  bad usage / missing file
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def merge_adjacent(
    items: list[dict[str, Any]],
    gap: float = 5.0,
) -> list[dict[str, Any]]:
    """Merge judged items where two consecutive ranges overlap or are within `gap` seconds.

    Keeps union span; joins hit_texts with "|".
    """
    if not items:
        return []
    sorted_items = sorted(items, key=lambda x: x["start"])
    merged: list[dict[str, Any]] = [dict(sorted_items[0])]
    for it in sorted_items[1:]:
        last = merged[-1]
        if it["start"] - last["end"] < gap:
            last["end"] = max(last["end"], it["end"])
            last["hit_text"] = f'{last["hit_text"]}|{it["hit_text"]}'
        else:
            merged.append(dict(it))
    return merged


def fmt_time(seconds: float | None) -> str:
    """Format seconds as MM:SS or H:MM:SS, or '--:--' if None."""
    if seconds is None:
        return "--:--"
    s = int(seconds)
    h, rem = divmod(s, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"


def build_table(
    merged: list[dict[str, Any]],
    total_duration: float | None,
) -> tuple[str, float]:
    """Build the dry-run table string; return (text, total_cut_seconds)."""
    lines: list[str] = []
    total_cut = 0.0
    for i, seg in enumerate(merged, 1):
        dur = seg["end"] - seg["start"]
        total_cut += dur
        hit = seg.get("hit_text", "")
        if len(hit) > 50:
            hit = hit[:47] + "..."
        lines.append(
            f"[{i:>3}] {seg['start']:>7.1f} - {seg['end']:>7.1f}  "
            f"({dur:>5.1f}s)  hit: {hit!r}"
        )

    sep = "-" * 60
    lines.append(sep)

    total_str = fmt_time(total_duration)
    if total_duration:
        pct = 100.0 * total_cut / total_duration
        expected_out = total_duration - total_cut
        lines.append(f"总剪切: {total_cut:.1f}s / {total_str} ({pct:.2f}%)")
        lines.append(
            f"预计输出: {fmt_time(expected_out)} "
            f"(与原视频时长 -{total_cut:.1f}s)"
        )
    else:
        lines.append(f"总剪切: {total_cut:.1f}s")
        lines.append("预计输出: (视频时长未知;transcript 未提供)")

    return "\n".join(lines), total_cut


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 5 merge + dry-run + STOP gate",
    )
    parser.add_argument("judged", help="judged.json from Stage 4")
    parser.add_argument("dryrun_out", help="output dryrun.txt path")
    parser.add_argument(
        "--transcript",
        help="optional transcript.json (for total video duration)",
    )
    parser.add_argument(
        "--merge-gap", type=float, default=5.0,
        help="seconds: gap under this is merged (default 5.0)",
    )
    args = parser.parse_args()

    judged_path = Path(args.judged)
    dryrun_path = Path(args.dryrun_out)

    if not judged_path.exists():
        print(f"ERROR: judged not found: {judged_path}", file=sys.stderr)
        return 1

    try:
        judged = json.loads(judged_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: judged.json JSON decode failed: {e}", file=sys.stderr)
        return 2

    if not isinstance(judged, list):
        print(f"ERROR: judged.json not a list (got {type(judged).__name__})", file=sys.stderr)
        return 2

    # Pull total video duration if available
    total_duration: float | None = None
    if args.transcript and Path(args.transcript).exists():
        try:
            tx = json.loads(Path(args.transcript).read_text(encoding="utf-8"))
            total_duration = float(tx.get("duration", 0))
        except (json.JSONDecodeError, ValueError):
            pass

    merged = merge_adjacent(judged, gap=args.merge_gap)
    table, total_cut = build_table(merged, total_duration)

    # Print table to stdout
    print(table)
    # Status to stderr
    print(f"\n[ad-cut] {len(merged)} cut segments, {total_cut:.1f}s total", file=sys.stderr)
    print("[ad-cut] DRY-RUN gate: reply y → Stage 6, n → skip, adjust → edit EDL", file=sys.stderr)

    # Write dryrun.txt
    dryrun_path.parent.mkdir(parents=True, exist_ok=True)
    dryrun_path.write_text(table + "\n", encoding="utf-8")

    return 0


if __name__ == "__main__":
    sys.exit(main())