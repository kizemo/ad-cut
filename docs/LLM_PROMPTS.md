# ad-cut Skill · LLM Prompt Templates

**Version**: v0.4.1
**Authoritative source for prompts**: `scripts/stage1_keywords.sh` + `scripts/stage4_judge.sh`
**Test videos used for tuning**: `F:\resourse_study\边界\2026下半年..._2026-08-15.mp4` (no ads, 2h59m lecture)

This document is the canonical reference for the two LLM prompts that drive
the ad-cut pipeline. If you change a prompt in code, update this document too.

---

## Stage 1 · Keyword Expansion

**Script**: `scripts/stage1_keywords.sh`
**Input**: 1-3 user seed keywords (CSV, optional) or defaults `["赞助","冠名","广告"]`
**Output**: `ad-cut/<slug>/keywords.json` (JSON list of ≥10 strings, target 50)
**Validator**: `python -c "assert isinstance(d, list) and len(d) >= 10 ..."` (script-side)

### Prompt (canonical)

```text
扩展以下中文课程视频中的赞助口播关键词到 50 个口语变体,涵盖:
- 本节目由 X 赞助/冠名/独家冠名/特约播出
- 广告时间/稍后回来/广告回来/精彩马上回来
- 由 X 提供/特别鸣谢/本节目由 X 独家赞助
- 本节由 X 支持/本集由 X 冠名

输入种子词:{seed_json}

输出要求:
1. 严格 JSON list[字符串],无 markdown 包裹(无 ```json)
2. 无任何说明文字或前后缀
3. 字符串内不嵌套引号
4. 至少 30 个(理想 50 个),口语化、贴近真实讲座/课程录像口播
6. 排除明显干扰词(如"广告学"、"广告位"等学术/行业词)

示例输入:["supported","sponsored"]
示例输出:["本节目由 X 赞助","感谢 X 冠名播出","广告之后回来","由 X 特别支持","本集由 X 独家冠名","精彩马上回来","稍后继续",...]
```

### Output contract

```json
["本节目由 X 赞助", "感谢 X 冠名播出", "广告之后回来", ...]
```

- **Min**: 10 keywords (script-side validation enforces)
- **Target**: 30-50 keywords
- **Format**: Plain JSON list, no markdown

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| 0 keywords (claude returns nothing) | Network error / API key invalid | Check `ANTHROPIC_BASE_URL`, retry |
| Returns markdown ```json ... ``` | Model didn't follow instructions | Filter via `sed -n '/^\[/,/^\]/p'` (already in script) |
| Returns prose before/after JSON array | Model adds explanation | Filter via `sed -n '/^\[/,/^\]/p'` (handles this) |
| < 10 keywords | Model truncated | Rerun; or manually edit `keywords.json` |
| Academic words like "广告学" | Model interpreted broadly | Add anti-examples in prompt (already in prompt) |

### Tuning notes (v0.4.1 vs lost v0.3.0)

The v0.3.0 prompt is permanently lost. This v0.4.1 version:
- Adds 4 anti-instruction clarifications (items 1-4, 6 in output requirements)
- Specifies target range "30-50" (was "50" in handoff memory)
- Adds 4 example categories (was just 3)
- v0.3.0 may have produced ~80 keywords; v0.4.1 produces 30-50

If Stage 3 false-positive rate is too high on your test video, expand the
seed words with more variants and rerun.

---

## Stage 4 · LLM Re-judgment

**Script**: `scripts/stage4_judge.sh`
**Input**: `ad-cut/<slug>/candidates.json` (read as stdin to `claude -p`)
**Output**: `ad-cut/<slug>/judged.json` (filtered to `is_ad=true` only)

### Prompt (canonical)

```text
判断以下课程视频片段是否为赞助口播(非课程内容)。

判断标准:
- 商业广告 / 品牌冠名 / 课程推销 / 特别鸣谢 → is_ad=true, confidence >= 0.9
- 讲师讲解 / 学生互动 / 答疑 / 学术讨论 → is_ad=false
- 边缘情况(讲师顺口提到品牌,但非赞助口播) → is_ad=false, confidence < 0.6

输入:candidates.json 内容(每段含 start, end, hit_text)
返回:严格 JSON list,无 markdown 包裹,无任何说明文字。
每段返回:{start, end, is_ad, confidence}
is_ad=false 时 confidence 必填(0-1)。

严格要求:
- 严格区分课程内容 vs 商业赞助
- 看到 "本节目由 X 赞助/冠名/鸣谢" 这类典型赞助语 → is_ad=true
- 看到 "爸爸/妈妈/谢谢" 这类普通词 → is_ad=false(假阳性)
- 看到 "广告之后回来" / "稍后继续" → is_ad=true
```

### Output contract

```json
[
  {"start": 184.9, "end": 199.3, "is_ad": true, "confidence": 0.95},
  {"start": 305.1, "end": 318.7, "is_ad": false, "confidence": 0.97},
  ...
]
```

After script-side filter (only `is_ad=true`):

```json
[
  {"start": 184.9, "end": 199.3, "is_ad": true, "confidence": 0.95}
]
```

### Common failure modes

| Symptom | Cause | Fix |
|---|---|---|
| All items `is_ad=false` (no ads kept) | LLM too strict, or true positives missed | Loosen prompt: add "advertising read" examples |
| All items `is_ad=true` (false positives) | LLM too lenient | Add false-positive examples ("爸爸/妈妈" → false) |
| `confidence` missing for `is_ad=false` | Model skipped field | Validator already enforces this; fix prompt |
| Returns prose wrapper | Model adds explanation | Filter via `sed -n '/^\[/,/^\]/p'` |

### Tuning notes

Stage 4 is the **false-positive filter** — its job is to be conservative.
A reasonable error budget:
- **Accept**: Drop 5-10% of true positives (false negative rate) if it removes
  the obvious false positives (e.g., "爸爸妈妈" with "妈妈" substring).
- **Don't accept**: Let obvious sponsor reads ("本节目由 X 冠名") be classified
  as `is_ad=false`.

If Stage 4 is producing 0 items on a video that clearly has sponsor reads,
inspect `candidates.json` to see what Stage 3 caught. Then:
1. Update the prompt to match the failure mode
2. Rerun `bash scripts/stage4_judge.sh`

---

## Pipeline interaction

```
Stage 1 → keywords.json (LLM generates variants)
                ↓
Stage 2 → transcript.json (faster-whisper)
                ↓
Stage 3 → candidates.json (Python: substring match + ±2s)
                ↓
Stage 4 → judged.json (LLM: filter false positives) ← THIS IS WHERE YOU TUNE
                ↓
Stage 5 → dry-run table (Python: merge + format)
                ↓
[user y/n/adjust]
                ↓
Stage 6 → cut mp4 (Python+ffmpeg)
```

If you're tuning for better precision/recall:
1. Inspect **candidates.json** (Stage 3 output) — is it too broad? Too narrow?
2. If too broad → tune Stage 4 prompt
3. If too narrow → tune Stage 1 prompt + rerun Stage 1-4

---

## See also

- `plan-restore-skill.md` §4.2 (Stage 1) + §4.5 (Stage 4) — original spec
- `scripts/stage1_keywords.sh` — canonical Stage 1 implementation
- `scripts/stage4_judge.sh` — canonical Stage 4 implementation
- `docs/VERIFY.md` — verification SOP and test video inventory
- `SKILL.md` — high-level skill flow