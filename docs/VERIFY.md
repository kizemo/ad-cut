# ad-cut Skill · Verification SOP

**Version**: v0.5.0
**Replaces**: `~/.claude/plans/2026-08-15-ad-cut-e2e-evidence.md` (permanently lost)
**Purpose**: Reproducible verification protocol for end-to-end ad-cut pipelines.

---

## 1. Test environment

### 1.1 Required tools

```bash
# Windows Git Bash
winget install ffmpeg
winget install jqlang.jq    # optional (scripts use awk-based fallback)
```

### 1.2 Python venv (MUST be 3.12 — 3.14 has no cython wheel for faster-whisper)

```bash
py -3.12 -m venv ~/myvenv
~/myvenv/Scripts/pip install faster-whisper
```

### 1.3 Environment variables

```bash
export ADCUT_PYTHON="$HOME/myvenv/Scripts/python.exe"   # Windows Git Bash
export HF_ENDPOINT="https://hf-mirror.com"             # required for China
export HF_HUB_DISABLE_XET=1                            # required for China
```

See `.env.example` for the canonical template.

### 1.4 Test videos

| Label | Path | Duration | Expected behavior |
|---|---|---|---|
| 5 min short (no ads) | `F:\resourse_study\边界\2026下半年..._2026-08-15.mp4` slice 0-5min | 5 min | Stage 3 returns 0 candidates → STOP |
| 30 min mid (false positive) | `F:\resourse_study\边界\2026下半年..._2026-08-15.mp4` slice 30-60min | 30 min | Stage 3 returns 1 candidate ("爸爸妈妈") → Stage 4 filters → STOP |
| 30 min with ads | (need to find a real sponsored video) | 30 min | Stage 3-6 all run; output = input - cuts |
| 60 min long | (need to find) | 60 min | Stage 6 ffmpeg ~10s; full pipeline works |

**Reality check**: As of 2026-10-13, the test videos above are **the same lecture recording** that does NOT have actual sponsor reads. To exercise the full "real ads cut" flow, find:
- 直播带货录像 (live commerce recording)
- 综艺片头 (variety show intro)
- 有商业合作的讲座 (lecture with commercial partnerships)

---

## 2. Unit tests

```bash
cd F:/soft/00selfmade/ad-cut
python -m pytest tests/ -x -v
```

### 2.1 Coverage as of v0.5.0

| File | Tests | Coverage |
|---|---|---|
| `tests/test_transcribe.py` | 6 | argparse, file existence, ImportError, env vars, empty words |
| `tests/test_stage6.py` | 16 | invert cuts, filter_complex schema (VERIFY-FINDING-03), EDL validation, real ffmpeg smoke |

**Total**: 22 tests, all green as of commit `57fc321`.

---

## 3. End-to-end tests

### 3.1 5-min short video (no ads)

```bash
# Slice first 5 min from source video
ffmpeg -y -i "F:\resourse_study\边界\2026下半年..._2026-08-15.mp4" \
    -t 300 -c copy "C:/Temp/adcut-test/5min_no_ads.mp4"

# Run pipeline
bash scripts/run_pipeline.sh --video "C:/Temp/adcut-test/5min_no_ads.mp4"
```

**Expected**:
- Stage 1: writes `keywords.json` (~30-50 keywords)
- Stage 2: writes `transcript.json` (~150 segments)
- Stage 3: returns **0 candidates** → STOP with exit 0
- Stage 4-7: NOT executed

**Expected output**:
```
[stage3] 0 candidates → STOP (no sponsor reads detected)
[run] Stage 3 returned 0 candidates → STOP (no ads detected)
```

### 3.2 30-min mid video (false positive "爸爸妈妈")

```bash
# Slice 30-60 min
ffmpeg -y -ss 1800 -i "F:\resourse_study\边界\2026下半年..._2026-08-15.mp4" \
    -t 1800 -c copy "C:/Temp/adcut-test/30min_false_positive.mp4"

bash scripts/run_pipeline.sh --video "C:/Temp/adcut-test/30min_false_positive.mp4"
```

**Expected**:
- Stage 3: returns 1 candidate at ~XX.X seconds containing "爸爸妈妈"
- Stage 4: LLM judges it as `is_ad=false, confidence>=0.9` → drops it
- Output: STOP with exit 0

**Actual from v0.3.0 handoff**:
- Stage 3 returned 1 candidate, Stage 4 dropped with confidence 0.97 → STOP

### 3.3 30-min video with REAL ads

**Prereq**: Find a video with actual "本节目由 X 赞助" reads.

```bash
bash scripts/run_pipeline.sh --video path/to/real_ads_30min.mp4 --yes
```

**Expected**:
- Stage 3: returns N candidates (N≥1)
- Stage 4: keeps some/all as `is_ad=true`
- Stage 5: prints table with cuts
- Stage 6 (auto with --yes): cuts video, writes `<basename>_no-ads.mp4`
- Stage 7: prints final report

### 3.4 60-min long video

```bash
bash scripts/run_pipeline.sh --video path/to/60min.mp4 --yes
```

**Expected**:
- Stage 6 ffmpeg runs in ~10-30s (2-5% of input duration)
- Output duration = input - total cuts (±1s tolerance)

---

## 4. Error path tests

| Scenario | How to trigger | Expected |
|---|---|---|
| Input file not found | `bash run_pipeline.sh --video /tmp/nope.mp4` | Stage 0: "video not found", exit 1 |
| Wrong extension | `bash run_pipeline.sh --video doc.txt` | Stage 0: "unsupported extension", exit 1 |
| `ADCUT_PYTHON` unset | unset ADCUT_PYTHON; run | Stage 2: "WARN: falling back to python", but continues |
| faster-whisper not in venv | point `ADCUT_PYTHON` to non-faster Python | Stage 2: transcribe.py exits 2; pipeline exits 2 |
| Stage 3 returns 0 | use a 5-min no-ads video | Stage 3 STOP message, exit 0 |
| Stage 4 returns 0 | use a video where all candidates are false positives | Stage 4 STOP message, exit 0 |
| Stage 5 user says n | run without --yes, type `n` at prompt | Pipeline exits 0, no ffmpeg call |
| User edits EDL badly | run with --yes, corrupt `judged.json` | Stage 6: schema validation error, exit 1 |
| ffmpeg fails | corrupt input video mid-stream | Stage 6: ffmpeg returns non-zero, exit 4 |
| Entire video cut | EDL = `[{start: 0, end: 99999}]` | Stage 6: "keep segments empty", exit 3 |

All these have corresponding test paths in `tests/test_stage6.py` or are
explicit exits in `scripts/run_pipeline.sh`.

---

## 5. Verification artifacts

After a successful run, you should have:

```
<video_dir>/
├── <basename>_no-ads.mp4        # final cut video (Stage 6)
├── <basename>_no-ads.edl.json   # effective EDL (Stage 6 edl-out)
└── ad-cut/<slug>/
    ├── keywords.json            # Stage 1 output
    ├── transcript.json          # Stage 2 output (large)
    ├── candidates.json          # Stage 3 output
    ├── judged.json              # Stage 4 output
    └── dryrun.txt               # Stage 5 table
```

`<slug>` = `md5(video_absolute_path)[:12]` (12-char hex prefix).

---

## 6. Performance benchmarks

From v0.3.0 handoff (2026-08-15, baseline):
- 5 min video, ASR small: ~30s
- 30 min video, ASR small: ~3min
- 30 min Stage 6 ffmpeg cut: 64s
- 60 min video, ASR small: ~6min (estimated)
- 60 min Stage 6 ffmpeg cut: ~2min (estimated)

faster-whisper `small` model on CPU is the bottleneck. Use `medium` or
`large-v3` for higher accuracy at 3-5x cost.

---

## 7. Verification evidence template

When you run a verification, append a row here:

```
| YYYY-MM-DD | video path | duration | result | notes |
|---|---|---|---|---|
| 2026-10-13 | test.mp4 (synthetic) | 30s | Stage 6 cut 10-12 → 28s | automated test |
```

For real-video verifications, include:
- ffmpeg output before/after durations
- Stage 3 candidate count
- Stage 4 kept count
- Stage 5 dryrun table
- Final report from Stage 7

---

## 8. See also

- `plan-restore-skill.md` §6 (verification plan source)
- `handoff-ad-cut-skill-2026-08-15.md` (v0.3.0 baseline, 5 tests passed)
- `tests/` — automated tests
- `scripts/run_pipeline.sh` — batch/CI driver
- `SKILL.md` — Claude skill frontmatter (interactive driver)