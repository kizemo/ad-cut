#!/usr/bin/env bash
# install_deps.sh - ad-cut dependency installer
#
# Detects what's missing via bin/check_env.py, then installs each component:
#   1. ffmpeg via winget (Windows) / apt (Linux) / brew (Mac)
#   2. faster-whisper via pip (in $ADCUT_PYTHON venv if set, else `python`)
#   3. faster-whisper model download via Python (honors HF_ENDPOINT for China)
#
# Each step prompts for confirmation unless --yes is passed.
# Re-runnable: each step is no-op if already installed.
#
# Usage:
#   install_deps.sh                # interactive, prompts per install
#   install_deps.sh --yes           # auto-confirm all installs (CI mode)
#   install_deps.sh --model medium # install medium instead of small
#
# Exit codes:
#   0  all installs succeeded (or already present)
#   1  some installs failed

set -euo pipefail

YES=0
MODEL="${ADCUT_WHISPER_MODEL:-small}"

for arg in "$@"; do
    case "$arg" in
        --yes|-y) YES=1 ;;
        --model)  shift; MODEL="${1:-small}" ;;
        --model=*) MODEL="${arg#--model=}" ;;
        --help|-h)
            cat <<'USAGE' >&2
Usage: install_deps.sh [--yes] [--model MODEL]
  --yes       auto-confirm all install prompts
  --model     faster-whisper model name (default: small)
USAGE
            exit 0
            ;;
        *) echo "WARN: unknown arg: $arg (continuing)" >&2 ;;
    esac
done

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Pick Python interpreter
PY="${ADCUT_PYTHON:-python}"

# Confirmation helper
confirm() {
    if [ "$YES" = "1" ]; then return 0; fi
    local msg="$1"
    read -r -p "$msg [y/N] " REPLY
    case "${REPLY:-n}" in
        y|Y|yes|YES) return 0 ;;
        *) return 1 ;;
    esac
}

# Header
echo "==> ad-cut dependency installer (model: $MODEL, python: $PY)"
echo ""

# ----- 1. ffmpeg -----
echo "==> [1/3] ffmpeg"
if command -v ffmpeg >/dev/null 2>&1; then
    echo "  ✓ already installed: $(command -v ffmpeg)"
else
    if confirm "  install ffmpeg?"; then
        if command -v winget >/dev/null 2>&1; then
            echo "  → winget install Gyan.FFmpeg"
            winget install --id=Gyan.FFmpeg -e --accept-package-agreements --accept-source-agreements \
                || echo "  WARN: winget install returned non-zero (you may need admin or to retry)"
        elif command -v choco >/dev/null 2>&1; then
            echo "  → choco install ffmpeg"
            choco install ffmpeg -y || echo "  WARN: choco install failed"
        elif command -v apt-get >/dev/null 2>&1; then
            echo "  → sudo apt-get install -y ffmpeg"
            sudo apt-get install -y ffmpeg || echo "  WARN: apt-get failed (check sudo)"
        elif command -v brew >/dev/null 2>&1; then
            echo "  → brew install ffmpeg"
            brew install ffmpeg || echo "  WARN: brew install failed"
        else
            echo "  ERROR: no package manager found (winget/choco/apt/brew)" >&2
            echo "  install ffmpeg from https://ffmpeg.org/ffmpeg.html manually" >&2
            exit 1
        fi
    else
        echo "  ⊘ skipped"
    fi
fi
echo ""

# ----- 2. faster-whisper -----
echo "==> [2/3] faster-whisper (in $PY)"
if "$PY" -c "import faster_whisper" 2>/dev/null; then
    VER=$("$PY" -c "import faster_whisper; print(faster_whisper.__version__)" 2>/dev/null || echo "?")
    echo "  ✓ already installed: faster-whisper $VER"
else
    if confirm "  install faster-whisper via pip?"; then
        "$PY" -m pip install --upgrade faster-whisper \
            || { echo "  ERROR: pip install failed" >&2; exit 1; }
        echo "  ✓ installed"
    else
        echo "  ⊘ skipped"
    fi
fi
echo ""

# ----- 3. model -----
echo "==> [3/3] faster-whisper model '$MODEL'"
# Set HF_ENDPOINT if not set (China-friendly default; works internationally too)
if [ -z "${HF_ENDPOINT:-}" ]; then
    export HF_ENDPOINT="https://hf-mirror.com"
    echo "  (i) HF_ENDPOINT unset → defaulting to $HF_ENDPOINT for this run"
fi

# Check if already cached
if "$PY" "$PROJECT_DIR/bin/check_env.py" --python "$PY" --model "$MODEL" --json 2>/dev/null \
        | python -c "import json,sys; sys.exit(0 if json.load(sys.stdin).get('model') else 1)"; then
    echo "  ✓ model '$MODEL' already cached (no download needed)"
else
    if confirm "  download model '$MODEL' (~${MODEL_BYTES:-500M} via $HF_ENDPOINT)?"; then
        "$PY" -c "
from faster_whisper import WhisperModel
import os
m = os.environ.get('ADCUT_WHISPER_DEVICE', 'cpu')
ct = os.environ.get('ADCUT_WHISPER_COMPUTE', 'int8')
print(f'  Downloading model $MODEL ({m}/{ct}) via {os.environ.get(\"HF_ENDPOINT\", \"huggingface.co\")}')
m = WhisperModel('$MODEL', device=m, compute_type=ct)
print('  ✓ downloaded successfully')
" || { echo "  ERROR: download failed" >&2; exit 1; }
    else
        echo "  ⊘ skipped"
    fi
fi
echo ""

# ----- Summary -----
echo "==> Summary"
"$PY" "$PROJECT_DIR/bin/check_env.py" --python "$PY" --model "$MODEL" || true
echo ""
echo "Tip: ensure HF_ENDPOINT=https://hf-mirror.com is set in your shell"
echo "     (e.g. add to ~/.bashrc: export HF_ENDPOINT=https://hf-mirror.com)"