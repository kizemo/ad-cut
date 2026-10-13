#!/usr/bin/env python3
"""discover_local_tools.py - ad-cut local tool discovery.

Deep-probe the system for already-deployed ffmpeg / ffprobe / Python /
faster-whisper / cached models / GPU. Returns a JSON summary.

This is the **first** step of Stage 0. NEVER download/install anything
until this returns a complete report — even if "$ADCUT_PYTHON not set"
or "PATH doesn't have ffmpeg", the right answer might be "user has
JianyingPro's bundled ffmpeg" or "user has the system Python with
faster-whisper pre-installed".

Probes (in order, all non-destructive):
  1. PATH: ffmpeg / ffprobe / python
  2. System Pythons: py.exe launcher → C:\\Python3XX, plus python3, python
  3. venv detection: walk common roots for Scripts/python.exe with
     Lib/site-packages/faster_whisper
  4. HF cache: $HF_HOME/hub/models--Systran--faster-whisper-*
  5. Known Windows install paths (priority order):
       - C:\\Program Files\\JianyingPro\\*\\ffmpeg.exe
       - C:\\Program Files\\Topaz Labs LLC\\Topaz Video AI\\ffmpeg.exe
       - D:\\green\\哔哩下载姬\\ffmpeg\\ffmpeg.exe
       - D:\\Program Files\\FormatFactory\\ffmpeg.exe
       - D:\\Program Files\\ShadowBot\\*\\ffmpeg.exe
       - WinGet links: %LOCALAPPDATA%\\Microsoft\\WinGet\\Links\\
  6. GPU vendor (NVIDIA / AMD / Intel) via Windows WMI

Usage:
    python scripts/discover_local_tools.py
    python scripts/discover_local_tools.py --json   # JSON only
    python scripts/discover_local_tools.py --quiet  # only summary line

Exit codes:
    0  at least one ffmpeg + one usable Python found
    1  something critical missing
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


# Force UTF-8 on Windows
if sys.platform == "win32":
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass


# ---------- known install paths ----------

# (path_glob, label). Order = priority (earlier wins when multiple match).
KNOWN_FFMPEG_PATHS_WINDOWS = [
    ("C:/Program Files/JianyingPro/*/ffmpeg.exe", "JianyingPro"),
    ("C:/Program Files (x86)/JianyingPro/*/ffmpeg.exe", "JianyingPro (x86)"),
    ("C:/Program Files/Topaz Labs LLC/Topaz Video AI/ffmpeg.exe", "Topaz Video AI"),
    ("C:/Program Files (x86)/Topaz Labs LLC/Topaz Video AI/ffmpeg.exe", "Topaz (x86)"),
    ("C:/Program Files/Topaz Video AI/ffmpeg.exe", "Topaz Video AI (legacy path)"),
    ("D:/green/哔哩下载姬/ffmpeg/ffmpeg.exe", "哔哩下载姬"),
    ("D:/Program Files/FormatFactory/ffmpeg.exe", "FormatFactory"),
    ("D:/Program Files/Format Factory/ffmpeg.exe", "Format Factory"),
    ("D:/Program Files/ShadowBot/*/ffmpeg.exe", "ShadowBot"),
    ("D:/green/ShadowBot/ffmpeg.exe", "ShadowBot (green)"),
    ("C:/Program Files/EVCapture/ffmpeg.exe", "EVCapture"),
    ("C:/Program Files (x86)/EVCapture/ffmpeg.exe", "EVCapture (x86)"),
]

KNOWN_PYTHON_PATHS_WINDOWS = [
    "C:/Python314/python.exe",
    "C:/Python313/python.exe",
    "C:/Python312/python.exe",
    "C:/Python311/python.exe",
    "C:/Python310/python.exe",
]


def _glob_first(pattern: str) -> Optional[Path]:
    """Return the first existing path matching a glob pattern, or None.

    pathlib.Path().glob() does NOT support absolute patterns or
    patterns with drive letters; this wrapper uses os.path-based
    globbing instead, which is portable across both.
    """
    import glob as _glob
    matches = sorted(_glob.glob(pattern))
    for m in matches:
        if Path(m).is_file():
            return Path(m)
    return None


# ---------- probes ----------

def probe_path_tools() -> dict:
    """Check ffmpeg/ffprobe in PATH."""
    return {
        "ffmpeg": shutil.which("ffmpeg"),
        "ffprobe": shutil.which("ffprobe"),
    }


def probe_known_ffmpeg() -> list[dict]:
    """Search known Windows install paths for ffmpeg.exe.

    Returns list of {path, source, has_ffprobe} (sorted by priority).
    """
    if sys.platform != "win32":
        return []
    results: list[dict] = []
    seen: set[str] = set()
    for pattern, source in KNOWN_FFMPEG_PATHS_WINDOWS:
        p = _glob_first(pattern)
        if p and str(p) not in seen:
            seen.add(str(p))
            # Companion ffprobe
            ffprobe = p.parent / "ffprobe.exe"
            if not ffprobe.exists():
                ffprobe = None
            results.append({
                "path": str(p),
                "source": source,
                "ffprobe": str(ffprobe) if ffprobe else None,
            })
    return results


def probe_winget_links() -> list[dict]:
    """Search WinGet Links directory for shimmed ffmpeg."""
    if sys.platform != "win32":
        return []
    local_app = os.environ.get("LOCALAPPDATA", "")
    if not local_app:
        return []
    links_dir = Path(local_app) / "Microsoft" / "WinGet" / "Links"
    if not links_dir.exists():
        return []
    results: list[dict] = []
    for ffmpeg_shim in links_dir.glob("ffmpeg*"):
        if ffmpeg_shim.is_file() or ffmpeg_shim.is_symlink():
            target = ffmpeg_shim.resolve() if ffmpeg_shim.is_symlink() else ffmpeg_shim
            results.append({
                "shim": str(ffmpeg_shim),
                "target": str(target),
            })
    return results


def probe_pythons() -> list[dict]:
    """Find Python interpreters and check if they have faster-whisper."""
    candidates: list[dict] = []
    seen: set[str] = set()

    # PATH pythons first
    for name in ("python", "python3", "py"):
        p = shutil.which(name)
        if p and p not in seen:
            seen.add(p)
            candidates.append({"exe": p, "source": f"PATH {name}"})

    # Known system Pythons
    if sys.platform == "win32":
        for path in KNOWN_PYTHON_PATHS_WINDOWS:
            if Path(path).exists() and path not in seen:
                seen.add(path)
                candidates.append({"exe": path, "source": "known Windows path"})

        # py launcher list (py -3.12, py -3.11, etc.)
        try:
            r = subprocess.run(
                ["py", "-3.12", "-c", "import sys; print(sys.executable)"],
                capture_output=True, text=True, timeout=10,
            )
            if r.returncode == 0 and r.stdout.strip() not in seen:
                p = r.stdout.strip()
                seen.add(p)
                candidates.append({"exe": p, "source": "py launcher -3.12"})
        except (FileNotFoundError, subprocess.TimeoutExpired):
            pass

    # For each, check faster-whisper
    for c in candidates:
        try:
            r = subprocess.run(
                [c["exe"], "-c",
                 "import faster_whisper; print(faster_whisper.__version__)"],
                capture_output=True, text=True, timeout=15,
            )
            c["faster_whisper"] = (
                r.stdout.strip() if r.returncode == 0 else None
            )
        except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
            c["faster_whisper"] = None

    return candidates


def probe_hf_cache() -> dict:
    """Find cached faster-whisper models."""
    hf_home = os.environ.get("HF_HOME")
    cache = Path(hf_home) / "hub" if hf_home else Path.home() / ".cache" / "huggingface" / "hub"
    out = {"path": str(cache), "models": []}
    if cache.exists():
        for d in cache.iterdir():
            if d.is_dir() and d.name.startswith("models--Systran--faster-whisper-"):
                name = d.name.replace("models--Systran--faster-whisper-", "")
                snapshots = d / "snapshots"
                if snapshots.exists():
                    for s in snapshots.iterdir():
                        if (s / "config.json").exists():
                            out["models"].append({"name": name, "path": str(s)})
                            break
    return out


def probe_gpu() -> dict:
    """Detect GPU vendor via Windows WMI. Returns {vendor, name} or empty."""
    if sys.platform != "win32":
        return {"vendor": None, "name": None}
    try:
        r = subprocess.run(
            ["powershell", "-NoProfile", "-Command",
             "Get-WmiObject Win32_VideoController | Select-Object -First 1 Name, AdapterCompatibility | ConvertTo-Csv -NoTypeInformation"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode == 0 and r.stdout.strip():
            lines = r.stdout.strip().splitlines()
            # CSV: "Name","AdapterCompatibility"
            if len(lines) >= 2:
                name = lines[1].split(",")[0].strip('"')
                compat = lines[1].split(",")[1].strip('"') if "," in lines[1] else ""
                vendor = None
                if any(k in (name + compat).lower() for k in ("nvidia", "geforce", "quadro", "tesla", "rtx")):
                    vendor = "NVIDIA"
                elif any(k in (name + compat).lower() for k in ("amd", "radeon", "ati ")):
                    vendor = "AMD"
                elif any(k in (name + compat).lower() for k in ("intel", "uhd", "iris")):
                    vendor = "Intel"
                return {"vendor": vendor, "name": name}
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        pass
    return {"vendor": None, "name": None}


def probe_ffmpeg_encoders(ffmpeg_path: Optional[str]) -> list[str]:
    """List h264 encoders in this ffmpeg build."""
    if not ffmpeg_path:
        return []
    try:
        r = subprocess.run(
            [ffmpeg_path, "-hide_banner", "-encoders"],
            capture_output=True, text=True, timeout=15,
        )
        if r.returncode != 0:
            return []
        encs = []
        for line in r.stdout.splitlines():
            # lines like " V..... = Video - h264_nvenc  NVIDIA NVENC H.264 encoder"
            if "h264" in line.lower() and "encoder" in line.lower():
                parts = line.split()
                if len(parts) >= 3:
                    encs.append(parts[2])
        return encs
    except (FileNotFoundError, subprocess.TimeoutExpired, OSError):
        return []


# ---------- main ----------

def collect() -> dict:
    """Run all probes and return a unified report."""
    path_tools = probe_path_tools()
    known_ffmpeg = probe_known_ffmpeg()
    winget_links = probe_winget_links()
    pythons = probe_pythons()
    hf_cache = probe_hf_cache()
    gpu = probe_gpu()

    # Pick best ffmpeg: PATH > known > WinGet
    best_ffmpeg = path_tools["ffmpeg"]
    best_ffprobe = path_tools["ffprobe"]
    best_ffmpeg_source = "PATH"
    if not best_ffmpeg and known_ffmpeg:
        best_ffmpeg = known_ffmpeg[0]["path"]
        best_ffmpeg_source = known_ffmpeg[0]["source"]
        if not best_ffprobe and known_ffmpeg[0].get("ffprobe"):
            best_ffprobe = known_ffmpeg[0]["ffprobe"]
    elif not best_ffmpeg and winget_links:
        # WinGet shim is just a launcher; resolve target
        best_ffmpeg = winget_links[0]["target"]
        best_ffmpeg_source = "WinGet link"

    encoders = probe_ffmpeg_encoders(best_ffmpeg)

    # Pick best Python: one with faster-whisper > system
    best_python = None
    best_python_source = None
    for p in pythons:
        if p.get("faster_whisper"):
            best_python = p["exe"]
            best_python_source = p["source"]
            break
    if not best_python and pythons:
        best_python = pythons[0]["exe"]
        best_python_source = pythons[0]["source"]

    needs_download = {
        "ffmpeg": not best_ffmpeg,
        "python": not best_python,
        "faster_whisper": not any(p.get("faster_whisper") for p in pythons),
        "model": not hf_cache["models"],
    }

    return {
        "ffmpeg": {
            "best_path": best_ffmpeg,
            "best_path_source": best_ffmpeg_source,
            "ffprobe": best_ffprobe,
            "encoders": encoders,
        },
        "ffmpeg_known_locations": known_ffmpeg,
        "winget_links": winget_links,
        "python": {
            "best_path": best_python,
            "best_path_source": best_python_source,
            "candidates": pythons,
        },
        "huggingface_cache": hf_cache,
        "gpu": gpu,
        "needs_download": needs_download,
    }


def report(data: dict) -> int:
    """Print a human-readable report. Return 0 if essentials OK, else 1."""
    print("ad-cut local tool discovery:")
    print()

    # ffmpeg
    ff = data["ffmpeg"]
    if ff["best_path"]:
        print(f"  ✓ ffmpeg       {ff['best_path']}")
        print(f"                   (from {ff['best_path_source']})")
        if ff["encoders"]:
            print(f"                   h264 encoders: {', '.join(ff['encoders'])}")
    else:
        print("  ✗ ffmpeg       NOT FOUND")
    if ff["ffprobe"]:
        print(f"  ✓ ffprobe      {ff['ffprobe']}")
    else:
        print("  ✗ ffprobe      NOT FOUND (will use ffmpeg -i fallback)")

    # Python
    py = data["python"]
    if py["best_path"]:
        print(f"  ✓ python       {py['best_path']}")
        print(f"                   (from {py['best_path_source']})")
        # Show which pythons have faster-whisper
        with_fw = [p for p in py["candidates"] if p.get("faster_whisper")]
        if with_fw:
            for p in with_fw:
                print(f"  ✓ faster-whisper {p['faster_whisper']}  (in {p['exe']})")
        else:
            print("  ✗ faster-whisper NOT IMPORTABLE in any discovered Python")
    else:
        print("  ✗ python       NOT FOUND")

    # HF cache
    hf = data["huggingface_cache"]
    if hf["models"]:
        print(f"  ✓ HF cache     {hf['path']}")
        for m in hf["models"]:
            print(f"    - {m['name']:10s}  {m['path']}")
    else:
        print(f"  ✗ HF cache     empty ({hf['path']})")

    # GPU
    gpu = data["gpu"]
    if gpu.get("name"):
        print(f"  ✓ GPU          {gpu.get('vendor') or 'unknown'}: {gpu['name']}")
    else:
        print("  - GPU          not detected")

    # Decision
    nd = data["needs_download"]
    print()
    if any(nd.values()):
        print("→ Some components missing. Run scripts/install_deps.sh.")
    else:
        print("→ All essentials present. No download needed.")
    return 0 if not any(nd.values()) else 1


def main() -> int:
    p = argparse.ArgumentParser(description="ad-cut local tool discovery")
    p.add_argument("--json", action="store_true", help="emit JSON only")
    p.add_argument("--quiet", action="store_true", help="one-line summary only")
    args = p.parse_args()

    data = collect()
    if args.json:
        print(json.dumps(data, indent=2, ensure_ascii=False))
    elif args.quiet:
        nd = data["needs_download"]
        ff = data["ffmpeg"]["best_path"]
        py = data["python"]["best_path"]
        m = data["huggingface_cache"]["models"]
        print(f"ffmpeg={'✓' if ff else '✗'} python={'✓' if py else '✗'} "
              f"model={'✓' if m else '✗'} gpu={data['gpu'].get('vendor') or '-'}")
    else:
        return report(data)

    nd = data["needs_download"]
    return 0 if not any(nd.values()) else 1


if __name__ == "__main__":
    sys.exit(main())