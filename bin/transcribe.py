#!/usr/bin/env python3
# transcribe.py - ad-cut v0.4.2 ASR wrapper
#
# Wraps faster-whisper for Stage 2 of the ad-cut skill.
# faster-whisper PyPI does NOT provide a CLI, so this wrapper exists.
#
# Smart caching: if the requested model is already in $HF_HOME/hub, use the
# local snapshot path directly (local_files_only=True) so faster-whisper does
# NOT re-download / re-verify. If not cached, falls back to default download
# (uses HF_ENDPOINT=https://hf-mirror.com for China users).
#
# Usage:
#     python transcribe.py <video_path> <output_json>

import json
import os
import sys
from pathlib import Path
from typing import Optional


# Force UTF-8 stdout on Windows (default GBK → mojibake on non-ASCII paths)
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


def find_cached_model(model_name: str) -> Optional[str]:
    """Locate a faster-whisper model snapshot on the filesystem.

    Returns the absolute path to the snapshot dir if found, else None.
    Tries (a) huggingface_hub.try_to_load_from_cache, then (b) direct
    filesystem probe under $HF_HOME/hub or ~/.cache/huggingface/hub.
    """
    repo_id = f"Systran/faster-whisper-{model_name}"

    # (a) huggingface_hub API
    try:
        from huggingface_hub import try_to_load_from_cache  # type: ignore
        p = try_to_load_from_cache(repo_id, "config.json")
        if p:
            return str(Path(p).parent)
    except ImportError:
        pass
    except Exception:
        pass

    # (b) filesystem probe
    hf_home = os.environ.get("HF_HOME")
    cache_base = (Path(hf_home) / "hub") if hf_home else (Path.home() / ".cache" / "huggingface" / "hub")
    model_dir = cache_base / f"models--{repo_id.replace('/', '--')}"
    if model_dir.exists():
        snapshots_dir = model_dir / "snapshots"
        if snapshots_dir.exists():
            for snap in snapshots_dir.iterdir():
                if (snap / "config.json").exists():
                    return str(snap)
    return None


def main() -> None:
    if len(sys.argv) != 3:
        print(
            "Usage: python transcribe.py <video_path> <output_json>",
            file=sys.stderr,
        )
        sys.exit(1)

    video = Path(sys.argv[1])
    output = Path(sys.argv[2])

    if not video.exists():
        print(f"ERROR: video not found: {video}", file=sys.stderr)
        sys.exit(1)

    output.parent.mkdir(parents=True, exist_ok=True)

    try:
        from faster_whisper import WhisperModel
    except ImportError:
        print(
            "ERROR: faster-whisper not installed.\n"
            "  pip install faster-whisper   (in your venv)\n"
            f"  current Python: {sys.executable}",
            file=sys.stderr,
        )
        sys.exit(2)

    model_name = os.environ.get("ADCUT_WHISPER_MODEL", "small")
    language = os.environ.get("ADCUT_WHISPER_LANG", "zh")
    device = os.environ.get("ADCUT_WHISPER_DEVICE", "cpu")
    compute_type = os.environ.get("ADCUT_WHISPER_COMPUTE", "int8")

    # Smart path: use cached snapshot if available → skip download entirely
    cached = find_cached_model(model_name)
    if cached:
        print(
            f"[transcribe] {video.name} -> {output.name}\n"
            f"  model={model_name} (cached: {cached}) lang={language} "
            f"device={device} compute_type={compute_type}",
            file=sys.stderr,
        )
        # local_files_only=True forces no network check at all
        model = WhisperModel(cached, device=device, compute_type=compute_type,
                             local_files_only=True)
    else:
        # Not cached — fall through to faster-whisper's default behavior.
        # HF_ENDPOINT (if set, e.g. https://hf-mirror.com) is honored automatically
        # by huggingface_hub, so China users get the mirror without explicit code.
        hf_endpoint = os.environ.get("HF_ENDPOINT", "")
        if not hf_endpoint:
            print(
                "WARN: HF_ENDPOINT not set — huggingface.co may be slow/blocked in China.\n"
                "      Set HF_ENDPOINT=https://hf-mirror.com for the mirror.\n"
                "      Run scripts/install_deps.sh to set up environment.",
                file=sys.stderr,
            )
        print(
            f"[transcribe] {video.name} -> {output.name}\n"
            f"  model={model_name} (NOT cached; will download via "
            f"{hf_endpoint or 'huggingface.co'}) lang={language} "
            f"device={device} compute_type={compute_type}",
            file=sys.stderr,
        )
        model = WhisperModel(model_name, device=device, compute_type=compute_type)

    segments_iter, info = model.transcribe(
        str(video),
        language=language,
        word_timestamps=True,
        vad_filter=True,
        beam_size=5,
    )

    segments = []
    for seg in segments_iter:
        segments.append({
            "start": float(seg.start),
            "end": float(seg.end),
            "text": seg.text.strip(),
            "words": [
                {
                    "start": float(w.start),
                    "end": float(w.end),
                    "word": w.word,
                }
                for w in (seg.words or [])
            ],
        })

    payload = {
        "video": str(video.resolve()),
        "duration": float(info.duration),
        "language": info.language,
        "model": model_name,
        "segments": segments,
    }

    output.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(
        f"[transcribe] done: {len(segments)} segments, "
        f"{info.duration:.1f}s total",
        file=sys.stderr,
    )


if __name__ == "__main__":
    main()