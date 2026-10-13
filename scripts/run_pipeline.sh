#!/usr/bin/env bash
# run_pipeline.sh - ad-cut v0.5.0 master driver
#
# Orchestrates Stage 0-7. Suitable for batch/CI use; the Claude agent
# (SKILL.md frontmatter) drives the same flow interactively.
#
# Usage:
#   run_pipeline.sh --video <input.mp4> [--yes] [--keywords "k1,k2,k3"] [--output <out.mp4>]
#
# Flags:
#   --video <path>      required: input video (mp4/mkv/mov)
#   --yes               skip Stage 5 STOP gate (CI/batch mode)
#   --keywords <csv>    seed keywords for Stage 1 (otherwise defaults)
#   --output <path>     output mp4 (default: <basename>_no-ads.mp4 in same dir)
#
# Stage 5 STOP gate:
#   - Interactive (no --yes): prompts y/n/adjust
#   - With --yes: auto-proceeds to Stage 6
#
# Exit codes:
#   0  success (no ads, OR ads cut + Stage 6 ran, OR user declined at gate)
#   1  preflight fail / bad usage
#   2  Stage 1-4 hard error
#   5  Stage 6 ffmpeg failed (re-passed through)

set -euo pipefail

# ----- defaults -----
VIDEO=""
OUTPUT=""
YES=0
USER_KW=""
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# ----- usage -----
usage() {
    cat <<'USAGE' >&2
Usage: run_pipeline.sh --video <input.mp4> [--yes] [--keywords "k1,k2"] [--output <out.mp4>]

Examples:
  run_pipeline.sh --video lecture.mp4
  run_pipeline.sh --video lecture.mp4 --keywords "赞助,冠名" --yes
  run_pipeline.sh --video lecture.mp4 --output clean.mp4
USAGE
}

# ----- parse args -----
while [ $# -gt 0 ]; do
    case "$1" in
        --video)    VIDEO="$2"; shift 2 ;;
        --yes)      YES=1; shift ;;
        --keywords) USER_KW="$2"; shift 2 ;;
        --output)   OUTPUT="$2"; shift 2 ;;
        -h|--help)   usage; exit 0 ;;
        *) echo "Unknown arg: $1" >&2; usage; exit 1 ;;
    esac
done

if [ -z "$VIDEO" ]; then
    echo "ERROR: --video is required" >&2
    usage
    exit 1
fi

# ----- derive paths (use Python for portable path/slug handling) -----
read -r VIDEO_ABS BASENAME DIR_NAME SLUG < <(python -c "
import sys, os, hashlib
v = sys.argv[1]
ab = os.path.abspath(v)
base = os.path.splitext(os.path.basename(ab))[0]
d = os.path.dirname(ab)
slug = hashlib.md5(ab.encode('utf-8')).hexdigest()[:12]
# tab-separated for bash read
print(f'{ab}\t{base}\t{d}\t{slug}')
" "$VIDEO")

ARTIFACTS_DIR="$DIR_NAME/ad-cut/$SLUG"
KEYWORDS_JSON="$ARTIFACTS_DIR/keywords.json"
TRANSCRIPT_JSON="$ARTIFACTS_DIR/transcript.json"
CANDIDATES_JSON="$ARTIFACTS_DIR/candidates.json"
JUDGED_JSON="$ARTIFACTS_DIR/judged.json"
DRYRUN_TXT="$ARTIFACTS_DIR/dryrun.txt"

if [ -z "$OUTPUT" ]; then
    OUTPUT_MP4="$DIR_NAME/${BASENAME}_no-ads.mp4"
else
    OUTPUT_MP4="$OUTPUT"
fi
# EDL is ALWAYS derived from input video basename per SKILL.md contract
EDL_PATH="$DIR_NAME/${BASENAME}_no-ads.edl.json"

mkdir -p "$ARTIFACTS_DIR"

echo "[run] video:    $VIDEO_ABS" >&2
echo "[run] slug:     $SLUG" >&2
echo "[run] output:   $OUTPUT_MP4" >&2
echo "[run] edl:      $EDL_PATH" >&2
echo "[run] artifacts: $ARTIFACTS_DIR" >&2
echo "" >&2

# ----- Stage 0: Pre-flight -----
echo "=== Stage 0: Pre-flight ===" >&2
if [ ! -f "$VIDEO_ABS" ]; then
    echo "ERROR: video not found: $VIDEO_ABS" >&2
    exit 1
fi
if [ ! -r "$VIDEO_ABS" ]; then
    echo "ERROR: video not readable: $VIDEO_ABS" >&2
    exit 1
fi
EXT="${VIDEO_ABS##*.}"
case "${EXT,,}" in
    mp4|mkv|mov) ;;
    *) echo "ERROR: unsupported extension: $EXT (need mp4/mkv/mov)" >&2; exit 1 ;;
esac

# Get duration via ffmpeg (avoids ffprobe dependency)
DUR_RAW=$(ffmpeg -i "$VIDEO_ABS" 2>&1 | grep -i '^[[:space:]]*Duration:' | head -1 || true)
if [ -z "$DUR_RAW" ]; then
    echo "ERROR: cannot read video duration (ffmpeg failed)" >&2
    exit 1
fi
echo "[run] $DUR_RAW" >&2
echo "" >&2

# ----- Stage 1: LLM keyword expansion (cached) -----
if [ ! -f "$KEYWORDS_JSON" ]; then
    echo "=== Stage 1: LLM keyword expansion ===" >&2
    if ! bash "$SCRIPT_DIR/stage1_keywords.sh" "$KEYWORDS_JSON" "$USER_KW"; then
        echo "ERROR: Stage 1 failed" >&2
        exit 2
    fi
else
    echo "Stage 1: skip (cached $KEYWORDS_JSON)" >&2
fi
echo "" >&2

# ----- Stage 2: faster-whisper ASR (cached) -----
if [ ! -f "$TRANSCRIPT_JSON" ]; then
    echo "=== Stage 2: faster-whisper ASR ===" >&2
    PY="${ADCUT_PYTHON:-python}"
    if [ -z "${ADCUT_PYTHON:-}" ]; then
        echo "WARN: ADCUT_PYTHON not set, falling back to 'python' (likely 3.14)" >&2
    fi
    if ! "$PY" "$PROJECT_DIR/bin/transcribe.py" "$VIDEO_ABS" "$TRANSCRIPT_JSON"; then
        echo "ERROR: Stage 2 failed (check ADCUT_PYTHON / HF_ENDPOINT)" >&2
        exit 2
    fi
else
    echo "Stage 2: skip (cached $TRANSCRIPT_JSON)" >&2
fi
echo "" >&2

# ----- Stage 3: keyword match -----
echo "=== Stage 3: keyword match ===" >&2
if ! python "$SCRIPT_DIR/stage3_match.py" "$TRANSCRIPT_JSON" "$KEYWORDS_JSON" "$CANDIDATES_JSON"; then
    echo "ERROR: Stage 3 failed" >&2
    exit 2
fi
CAND_COUNT=$(python -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$CANDIDATES_JSON")
if [ "$CAND_COUNT" = "0" ]; then
    echo "" >&2
    echo "[run] Stage 3 returned 0 candidates → STOP (no ads detected)" >&2
    exit 0
fi
echo "[run] $CAND_COUNT candidates" >&2
echo "" >&2

# ----- Stage 4: LLM re-judge -----
echo "=== Stage 4: LLM re-judge ===" >&2
if ! bash "$SCRIPT_DIR/stage4_judge.sh" "$CANDIDATES_JSON" "$JUDGED_JSON"; then
    echo "ERROR: Stage 4 failed" >&2
    exit 2
fi
JUDGE_COUNT=$(python -c "import json,sys; print(len(json.load(open(sys.argv[1]))))" "$JUDGED_JSON")
if [ "$JUDGE_COUNT" = "0" ]; then
    echo "" >&2
    echo "[run] Stage 4 kept 0 → STOP (no ads confirmed)" >&2
    exit 0
fi
echo "[run] $JUDGE_COUNT ads confirmed" >&2
echo "" >&2

# ----- Stage 5: dry-run -----
echo "=== Stage 5: dry-run ===" >&2
if ! python "$SCRIPT_DIR/stage5_dryrun.py" "$JUDGED_JSON" "$DRYRUN_TXT" --transcript "$TRANSCRIPT_JSON"; then
    echo "ERROR: Stage 5 failed" >&2
    exit 2
fi
echo "" >&2

# ----- STOP gate -----
if [ "$YES" = "0" ]; then
    echo "[run] Review the dry-run table above." >&2
    if [ -t 0 ]; then
        # interactive terminal
        read -r -p "[run] Run Stage 6 (ffmpeg cut)? [y/n/adjust] " REPLY
    else
        # non-interactive (no TTY) without --yes → safe STOP
        echo "[run] no TTY and no --yes → STOP (run again with --yes for non-interactive)" >&2
        exit 0
    fi
    case "${REPLY:-n}" in
        y|Y|yes|YES) ;;
        n|N|no|NO) echo "[run] user declined, exit 0" >&2; exit 0 ;;
        adjust|a)
            echo "[run] Edit EDL: $JUDGED_JSON, then press Enter to continue." >&2
            read -r _
            ;;
        *) echo "[run] unrecognized reply, defaulting to n → STOP" >&2; exit 0 ;;
    esac
fi

# ----- Stage 6: ffmpeg cut -----
echo "=== Stage 6: ffmpeg ===" >&2
if ! python "$SCRIPT_DIR/stage6_ffmpeg.py" \
        --video "$VIDEO_ABS" \
        --edl "$JUDGED_JSON" \
        --output "$OUTPUT_MP4" \
        --edl-out "$EDL_PATH"; then
    RC=$?
    echo "ERROR: Stage 6 failed (exit $RC)" >&2
    exit $RC
fi
echo "" >&2

# ----- Stage 7: Report -----
echo "=== Stage 7: Report ===" >&2
IN_DUR=$(ffmpeg -i "$VIDEO_ABS" 2>&1 | grep -i '^[[:space:]]*Duration:' | head -1 | sed -E 's/.*Duration:[[:space:]]+([0-9:.]+).*/\1/')
OUT_DUR=$(ffmpeg -i "$OUTPUT_MP4" 2>&1 | grep -i '^[[:space:]]*Duration:' | head -1 | sed -E 's/.*Duration:[[:space:]]+([0-9:.]+).*/\1/')

echo "" >&2
echo "✅ 完成: $IN_DUR → $OUT_DUR"
KEPT_COUNT=$(python -c "import json,sys; data=json.load(open(sys.argv[1])); print(len(data))" "$JUDGED_JSON")
echo "保留: $KEPT_COUNT 段剪广告 confirmed"
echo "EDL: $EDL_PATH"
echo "中间产物: $ARTIFACTS_DIR"
echo "输出视频: $OUTPUT_MP4"

exit 0