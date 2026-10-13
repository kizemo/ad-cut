#!/usr/bin/env python3
"""stage3_match.py - ad-cut v0.4.1 Stage 3: keyword matching.

Reads transcript.json (Stage 2 output) + keywords.json (Stage 1 output),
emits candidates.json: [{start, end, hit_text}]

Algorithm (per plan-restore-skill.md §4.4):
  1. For each segment, scan words. If any keyword is a substring of word,
     record a candidate with [word.start - 2.0, word.end + 2.0] window.
  2. Sort candidates by start, merge any two with gap < 5.0 seconds.

Stage 3 0-hit is STOP-by-design (not an error): if no keywords match,
the source video probably has no sponsor reads. Caller (Stage 4) decides
whether to run LLM judge; the script itself returns exit 0.

Usage:
    python stage3_match.py <transcript.json> <keywords.json> <candidates.json>
                          [--padding 2.0] [--merge-gap 5.0]
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


def match_keywords(
    transcript: dict[str, Any],
    keywords: list[str],
    padding: float = 2.0,
) -> list[dict[str, Any]]:
    """Find word-level keyword hits, applying ±padding seconds."""
    candidates: list[dict[str, Any]] = []
    for seg in transcript.get("segments", []):
        for w in seg.get("words") or []:
            word = w.get("word", "")
            # Find first keyword that is a substring of word; record once
            for kw in keywords:
                if kw and kw in word:
                    candidates.append({
                        "start": max(0.0, float(w["start"]) - padding),
                        "end": float(w["end"]) + padding,
                        "hit_text": word,
                        "matched_keyword": kw,
                    })
                    break
    return candidates


def merge_overlapping(
    candidates: list[dict[str, Any]],
    gap: float = 5.0,
) -> list[dict[str, Any]]:
    """Merge candidates where two consecutive ranges overlap or are within `gap` seconds.
    Keeps the union span; joins hit_texts with "|".
    """
    if not candidates:
        return []

    sorted_cands = sorted(candidates, key=lambda c: c["start"])
    merged: list[dict[str, Any]] = [dict(sorted_cands[0])]

    for c in sorted_cands[1:]:
        last = merged[-1]
        if c["start"] - last["end"] < gap:
            last["end"] = max(last["end"], c["end"])
            last["hit_text"] = f'{last["hit_text"]}|{c["hit_text"]}'
            # Keep first matched_keyword for traceability
        else:
            merged.append(dict(c))

    return merged


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Stage 3 keyword matching (transcript + keywords → candidates)"
    )
    parser.add_argument("transcript", help="transcript.json from Stage 2")
    parser.add_argument("keywords", help="keywords.json from Stage 1")
    parser.add_argument("candidates", help="output candidates.json path")
    parser.add_argument(
        "--padding", type=float, default=2.0,
        help="seconds to add on each side of hit (default 2.0)",
    )
    parser.add_argument(
        "--merge-gap", type=float, default=5.0,
        help="seconds: gap under this is merged (default 5.0)",
    )
    args = parser.parse_args()

    transcript_path = Path(args.transcript)
    keywords_path = Path(args.keywords)
    candidates_path = Path(args.candidates)

    if not transcript_path.exists():
        print(f"ERROR: transcript not found: {transcript_path}", file=sys.stderr)
        return 1

    if not keywords_path.exists():
        print(f"ERROR: keywords not found: {keywords_path}", file=sys.stderr)
        return 1

    try:
        transcript = json.loads(transcript_path.read_text(encoding="utf-8"))
        keywords = json.loads(keywords_path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as e:
        print(f"ERROR: JSON decode failed: {e}", file=sys.stderr)
        return 2

    if not isinstance(keywords, list):
        print(f"ERROR: keywords.json is not a list (got {type(keywords).__name__})", file=sys.stderr)
        return 2

    raw = match_keywords(transcript, keywords, padding=args.padding)
    merged = merge_overlapping(raw, gap=args.merge_gap)

    candidates_path.parent.mkdir(parents=True, exist_ok=True)
    candidates_path.write_text(
        json.dumps(merged, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[stage3] raw={len(raw)} merged={len(merged)} padding={args.padding} "
        f"merge_gap={args.merge_gap} → {candidates_path}",
        file=sys.stderr,
    )

    # 0 hits is STOP-by-design (SKILL.md §"Stage 3 STOP 条件"), NOT an error
    if not merged:
        print("[stage3] 0 candidates → STOP (no sponsor reads detected)", file=sys.stderr)

    return 0


if __name__ == "__main__":
    sys.exit(main())