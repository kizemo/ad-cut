#!/usr/bin/env bash
# stage4_judge.sh - ad-cut v0.5.0 Stage 4: LLM re-judgment
#
# Usage: stage4_judge.sh <candidates.json> <judged.json>
#   candidates.json: input from Stage 3
#   judged.json:    output (filtered to is_ad=true)
#
# Behavior:
#   - Reads candidates.json as stdin to `claude -p` (VERIFY-FINDING-04: stderr → /dev/null)
#   - Filters JSON array from Claude prose preamble
#   - Validates JSON schema: list[{start, end, is_ad, confidence}]
#   - Filters: keep only is_ad=true (the candidates judged as actual sponsor reads)
#   - 0 kept = STOP-by-design (Stage 5/6 not invoked)
#
# Exit codes:
#   0  success (even if 0 ads confirmed)
#   1  bad usage / file not found
#   2  claude returned no JSON / JSON invalid

set -euo pipefail

CANDIDATES="${1:-}"
JUDGED="${2:-}"

if [ -z "$CANDIDATES" ] || [ -z "$JUDGED" ]; then
    cat <<'USAGE' >&2
Usage: stage4_judge.sh <candidates.json> <judged.json>
  candidates.json  input from Stage 3
  judged.json      output path (only is_ad=true items kept)
USAGE
    exit 1
fi

if [ ! -f "$CANDIDATES" ]; then
    echo "ERROR: candidates not found: $CANDIDATES" >&2
    exit 1
fi

PROMPT="$(cat <<PROMPT_EOF
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
PROMPT_EOF
)"

# Run with stdin redirected to candidates.json + stderr suppressed
RAW=$(claude -p "$PROMPT" < "$CANDIDATES" 2>/dev/null || true)

# Extract JSON array; strip CR first (CRLF safety)
JUDGED_RAW=$(printf '%s' "$RAW" | tr -d '\r' | sed -n '/^\[/,/^\]/p')

if [ -z "$JUDGED_RAW" ]; then
    echo "ERROR: claude -p returned no JSON array (got $(printf '%s' "$RAW" | wc -c) bytes)" >&2
    echo "---RAW---" >&2
    printf '%s\n' "$RAW" >&2
    echo "---END---" >&2
    exit 2
fi

# Validate JSON shape
if ! printf '%s' "$JUDGED_RAW" | python -c "
import json, sys
data = json.load(sys.stdin)
assert isinstance(data, list), f'not a list, got {type(data).__name__}'
for i, item in enumerate(data):
    assert isinstance(item, dict), f'item[{i}] not dict: {item!r}'
    for k in ('start', 'end', 'is_ad', 'confidence'):
        assert k in item, f'item[{i}] missing key {k!r}'
    assert isinstance(item['is_ad'], bool), f'item[{i}].is_ad not bool: {item[\"is_ad\"]!r}'
    assert isinstance(item['confidence'], (int, float)), \
        f'item[{i}].confidence not numeric: {item[\"confidence\"]!r}'
    assert 0.0 <= item['confidence'] <= 1.0, \
        f'item[{i}].confidence out of [0,1]: {item[\"confidence\"]!r}'
" 2>/dev/null; then
    echo "ERROR: judged JSON schema invalid" >&2
    echo "---PARSED---" >&2
    printf '%s\n' "$JUDGED_RAW" >&2
    echo "---END---" >&2
    exit 2
fi

# Filter: keep only is_ad=true
FILTERED=$(printf '%s' "$JUDGED_RAW" | python -c "
import json, sys
data = json.load(sys.stdin)
kept = [item for item in data if item.get('is_ad') is True]
print(json.dumps(kept, ensure_ascii=False))
")

mkdir -p "$(dirname "$JUDGED")"
printf '%s' "$FILTERED" > "$JUDGED"

TOTAL=$(printf '%s' "$JUDGED_RAW" | python -c "import json,sys; print(len(json.load(sys.stdin)))")
KEPT=$(printf '%s' "$FILTERED" | python -c "import json,sys; print(len(json.load(sys.stdin)))")
echo "[stage4] judged=$TOTAL kept_is_ad=$KEPT → $JUDGED" >&2

if [ "$KEPT" = "0" ]; then
    echo "[stage4] 0 ads confirmed → STOP (Stage 5/6 not called)" >&2
fi

exit 0