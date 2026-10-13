#!/usr/bin/env python3
"""keyword_buckets.py - flatten scripts/keyword_buckets.json to a flat list.

The buckets file groups keywords by speaker role + content type, so
Stage 1 / Stage 4 can use the categorization for weighting. Stage 3
just needs a flat list — this script does that flattening.

Usage:
    python keyword_buckets.py            # flat JSON list to stdout
    python keyword_buckets.py --include format_sponsor cta_engagement
    python keyword_buckets.py --exclude speaker_transition
    python keyword_buckets.py --seed     # only 5 from each bucket (for prompt seed)

Exit codes:
    0  ok
    1  keyword_buckets.json not found
    2  bucket name not in valid list
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


BUCKETS_PATH = Path(__file__).parent / "keyword_buckets.json"


def load_buckets(path: Path = BUCKETS_PATH) -> dict:
    if not path.exists():
        print(f"ERROR: {path} not found", file=sys.stderr)
        sys.exit(1)
    return json.loads(path.read_text(encoding="utf-8"))


def flatten(buckets: dict, include: list[str] | None = None,
            exclude: list[str] | None = None, seed: bool = False) -> list[str]:
    """Flatten buckets to a list of strings, preserving insertion order, deduped."""
    out: list[str] = []
    seen: set[str] = set()
    bk = buckets.get("buckets", {})
    for name, data in bk.items():
        if include and name not in include:
            continue
        if exclude and name in exclude:
            continue
        kws = data.get("keywords", [])
        if seed:
            kws = kws[:5]
        for kw in kws:
            if kw and kw not in seen:
                seen.add(kw)
                out.append(kw)
    return out


def main() -> int:
    p = argparse.ArgumentParser(description="Flatten keyword_buckets.json to a list")
    p.add_argument("--include", nargs="*", help="only these bucket names")
    p.add_argument("--exclude", nargs="*", help="drop these bucket names")
    p.add_argument("--seed", action="store_true",
                   help="only first 5 keywords per bucket (use as prompt seed)")
    args = p.parse_args()

    buckets = load_buckets()
    valid_names = list(buckets.get("buckets", {}).keys())
    for name in (args.include or []) + (args.exclude or []):
        if name not in valid_names:
            print(f"ERROR: unknown bucket '{name}'. Valid: {valid_names}", file=sys.stderr)
            sys.exit(2)
    result = flatten(buckets, include=args.include, exclude=args.exclude, seed=args.seed)
    print(json.dumps(result, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main())