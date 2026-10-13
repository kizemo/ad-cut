#!/usr/bin/env python3
# transcribe.py - ad-cut v0.4.1 ASR wrapper
#
# Wraps faster-whisper for Stage 2 of the ad-cut skill.
# faster-whisper PyPI does NOT provide a CLI, so this wrapper exists.
#
# Usage:
#     python transcribe.py <video_path> <output_json>

import json
import os
import sys
from pathlib import Path


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

    print(
        f"[transcribe] {video.name} -> {output.name}\n"
        f"  model={model_name} lang={language} "
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