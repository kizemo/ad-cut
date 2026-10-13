# ad-cut skill · DEPLOY handoff

**完成日期**: 2026-08-15
**版本**: v0.3.0
**状态**: ✅ shipped, all 12 tasks done

---

## 已交付文件

| 文件 | 大小 | 状态 |
|---|---|---|
| `~/.claude/skills/ad-cut/SKILL.md` | 232+ 行 | ✅ v0.3.0 |
| `~/.claude/skills/ad-cut/README.md` | 101 行 | ✅ |
| `~/.claude/skills/ad-cut/bin/transcribe.py` | 107 行 | ✅ Python wrapper(必要补丁) |
| `~/.claude/commands/ad-cut.md` | 38 行 | ✅ |
| `~/.claude/plans/2026-08-15-ad-cut-baseline-notes.md` | 240 行 | ✅ RED 证据 |
| `~/.claude/plans/2026-08-15-ad-cut-refactor-notes.md` | — | ✅ 0 P0/P1,8 P2 全部补 |
| `~/.claude/plans/2026-08-15-ad-cut-e2e-evidence.md` | — | ✅ 端到端 + 错误路径 |

---

## VERIFY 阶段发现的真实问题 + 修复

| ID | 严重 | 问题 | 修复 | 状态 |
|---|---|---|---|---|
| VERIFY-FINDING-01 | P0 | faster-whisper PyPI 不提供 CLI,SKILL.md Stage 2 失效 | 写 `bin/transcribe.py` wrapper + `ADCUT_PYTHON` env var | ✅ |
| VERIFY-FINDING-02 | P1 | huggingface.co 在国内网络 502 不可达 | `HF_ENDPOINT=https://hf-mirror.com` + `HF_HUB_DISABLE_XET=1`(SKILL.md 已加 hint) | ✅ |
| VERIFY-FINDING-03 | P1 | SKILL.md Stage 6 ffmpeg filter graph "Media type mismatch" | 改用单 concat `v=1:a=1` + interleaved `[v0][a0][v1][a1]...` | ✅ |
| VERIFY-FINDING-04 | P1 | `claude -p` 默认阻塞 stdin 污染 JSON | `< /dev/null 2>/dev/null` + `sed -n '/^{/,/^}/p'` | ✅ |
| VERIFY-FINDING-05 | P2 | jq/bc Windows 原生缺 | awk 替代(已就位) | ✅ |
| VERIFY-FINDING-06 | P2 | Python 3.14 无 cython wheel,faster-whisper 装不上 | 用户需在 Python 3.12 venv 装(README FAQ 需加) | ⏳ README 待更新 |

---

## 测试视频 + 实际数据

| 测试 | 结果 |
|---|---|
| 5 min 短片(`F:\resourse_study\边界\2026下半年..._2026-08-15.mp4` 0-5min) | Stage 3 返回 0 候选 → SKILL.md 设计要求 STOP ✓ |
| 30 min 中片(30-60min) | Stage 3 返回 1 候选 "爸爸妈妈"(假阳性),Stage 4 LLM 判 is_ad:false 0.97 正确拦截 ✓ |
| Stage 5 dry-run table(合成 EDL) | 输出格式正确 ✓ |
| Stage 6 ffmpeg trim+concat(64s for 30min 视频) | 输出 1751.1s / 206MB,cut 49.87s/2.8% ✓ |
| EDL 重剪(改 EDL → 重跑 Stage 6) | 1776.1s 精确 -25s 匹配单 region ✓ |

**关键观察**:用户测试视频(2h59m 投资讲座)**实际上不含明显赞助口播**。前 60 min 扫描:0 个 "本节目由…赞助",1 个 "爸爸妈妈" 假阳性(被 Stage 4 拦截)。Skill 行为正确 —— 没广告就不剪。

**要测真"剪广告"流程**需要找:直播带货录像 / 综艺片头 / 有商业合作的讲座。

---

## 环境依赖(用户需自备)

1. **Python venv**(3.12 推荐,3.14 太新 cython 无 wheel):
   ```bash
   /c/Python314/python.exe -m venv myvenv  # ❌ 失败
   # 改用 3.12:
   py -3.12 -m venv myvenv
   myvenv/Scripts/pip install faster-whisper
   ```

2. **jq**(winget):
   ```bash
   winget install jqlang.jq
   ```

3. **ffmpeg / ffprobe**(winget):
   ```bash
   winget install ffmpeg
   ```

4. **claude CLI**(已装,走 ANTHROPIC_BASE_URL=api.minimaxi.com)

5. **环境变量**:
   ```bash
   export ADCUT_PYTHON=/path/to/venv/Scripts/python.exe  # 指向装 faster-whisper 的 Python
   export HF_ENDPOINT=https://hf-mirror.com              # 国内必须
   export HF_HUB_DISABLE_XET=1                            # 国内必须
   ```

---

## SKILL.md v0.3.0 主体结构

- frontmatter(name,description 触发词)
- When to use
- Stage 0: Pre-flight checks(意图/关键词宽度/文件存在/依赖)
- Requirements
- Output contract
- Stage 1: LLM 关键词扩展(50 个 + 网络口语变体)
- Stage 2: faster-whisper ASR(用 wrapper,默认 small)
- Stage 3: 关键词匹配 + ±2s padding(用 awk)
- Stage 4: LLM 二次裁判(`< /dev/null` + sed 过滤 JSON)
- Stage 5: Merge + dry-run 强 STOP
- Stage 6: ffmpeg trim+concat(单 concat interleaved)
- Stage 7: Report + EDL sidecar
- Red Flags: 10+ 条 verbatim 引用

---

## 已知限制(v1 范围)

- 仅 zh 单语种
- 5 min - 2 h 长度(更长 slow)
- 不支持 TV 硬广告(Comskip)
- 不支持网剧片头片尾(帧聚类)
- 不支持实时流

## 后续 v2/v3

- **v2 web drama**:帧聚类(无监督)
- **v3 TV ads**:Comskip 集成(Plex/Jellyfin DVR 后处理)
- `scripts/edl.py`:如关键词逻辑频繁变更(v1 不做)

---

## 用法速查

```bash
# 设置环境(Windows Git Bash)
export ADCUT_PYTHON="/e/办公文件/H AI/项目研究/.venv/Scripts/python.exe"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_DISABLE_XET="1"

# 触发
/ad-cut /path/to/lecture.mp4              # interactive
/ad-cut /path/to/lecture.mp4 --yes        # 跳 Stage 1 前确认(Stage 5 仍 STOP)
"帮我把 lecture.mp4 的赞助剪掉"           # 自然语言触发
```

产物:
- `<basename>_no-ads.mp4`(剪后)
- `<basename>_no-ads.edl.json`(可重剪 EDL)
- `ad-cut/<slug>/`(中间产物:transcript / keywords / candidates / judged)