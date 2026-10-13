#!/usr/bin/env bash
# stage1_keywords.sh - ad-cut v0.5.0 Stage 1: LLM keyword expansion
#
# Usage: stage1_keywords.sh <output_json> [user_keywords_csv]
#   output_json: where to write keywords.json (e.g., ad-cut/<slug>/keywords.json)
#   user_keywords_csv: optional, comma-separated seed keywords
#
# Behavior:
#   - Calls `claude -p` with stdin/stderr pollution prevention (VERIFY-FINDING-04)
#   - Filters JSON array from Claude's prose preamble via `sed -n '/^\[/,/^\]/p'`
#   - Validates JSON parseable + >= 10 keywords
#   - Writes UTF-8 keywords.json (JSON list of strings)
#
# Exit codes:
#   0  success
#   1  bad usage
#   2  Claude returned no JSON / JSON invalid / < 10 keywords
#   3  unexpected error

set -euo pipefail

OUTPUT="${1:-}"
USER_KW="${2:-}"

if [ -z "$OUTPUT" ]; then
    cat <<'USAGE' >&2
Usage: stage1_keywords.sh <output_json> [user_keywords_csv]
  output_json     path to write keywords.json
  user_keywords   optional seed keywords (comma-separated, e.g. "赞助,冠名")
USAGE
    exit 1
fi

# Build seed JSON list (default: 3 common Chinese sponsor terms)
if [ -z "$USER_KW" ]; then
    SEED='["赞助","冠名","广告"]'
else
    SEED=$(printf '%s' "$USER_KW" | python -c "
import sys, json
seeds = [w.strip() for w in sys.stdin.read().split(',') if w.strip()]
print(json.dumps(seeds, ensure_ascii=False))
")
fi

# LLM prompt — see docs/LLM_PROMPTS.md for the canonical template
PROMPT="$(cat <<PROMPT_EOF
扩展以下中文课程视频中的赞助口播关键词到 50 个口语变体,涵盖:
- 本节目由 X 赞助/冠名/独家冠名/特约播出
- 广告时间/稍后回来/广告回来/精彩马上回来
- 由 X 提供/特别鸣谢/本节目由 X 独家赞助
- 本节由 X 支持/本集由 X 冠名

输入种子词:${SEED}

输出要求:
1. 严格 JSON list[字符串],无 markdown 包裹(无 \`\`\`json)
2. 无任何说明文字或前后缀
3. 字符串内不嵌套引号
4. 至少 10 个(目标 30-50 个),口语化、贴近真实讲座/课程录像口播
5. 排除明显干扰词(如"广告学"、"广告位"等学术/行业词)

示例输入:["supported","sponsored"]
示例输出:["本节目由 X 赞助","感谢 X 冠名播出","广告之后回来","由 X 特别支持","本集由 X 独家冠名","精彩马上回来","稍后继续",...]
PROMPT_EOF
)"

# Run claude -p with stdin/stderr pollution prevention (VERIFY-FINDING-04)
RAW=$(claude -p "$PROMPT" < /dev/null 2>/dev/null || true)

# Extract JSON array between first [ and last ]
# strip CR first to handle CRLF-terminated JSON
KEYWORDS_JSON=$(printf '%s' "$RAW" | tr -d '\r' | sed -n '/^\[/,/^\]/p')

if [ -z "$KEYWORDS_JSON" ]; then
    echo "ERROR: claude -p returned no JSON array (got $(printf '%s' "$RAW" | wc -c) bytes)" >&2
    echo "---RAW---" >&2
    printf '%s\n' "$RAW" >&2
    echo "---END---" >&2
    exit 2
fi

# Validate JSON + min keyword count
if ! printf '%s' "$KEYWORDS_JSON" | python -c "
import json, sys
data = json.load(sys.stdin)
assert isinstance(data, list), 'not a list'
assert len(data) >= 10, f'only {len(data)} keywords, need >= 10'
for i, k in enumerate(data):
    assert isinstance(k, str), f'keyword[{i}] not string: {k!r}'
    assert k.strip(), f'keyword[{i}] is empty'
" 2>/dev/null; then
    echo "ERROR: keywords JSON invalid or fewer than 10 entries" >&2
    echo "---PARSED---" >&2
    printf '%s\n' "$KEYWORDS_JSON" >&2
    echo "---END---" >&2
    exit 2
fi

mkdir -p "$(dirname "$OUTPUT")"
printf '%s' "$KEYWORDS_JSON" > "$OUTPUT"

COUNT=$(python -c "import json; print(len(json.load(open('$OUTPUT'))))")
echo "[stage1] $COUNT keywords written → $OUTPUT" >&2
exit 0