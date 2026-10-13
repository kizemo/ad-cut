---

name: ad-cut
description: 去除讲师课程录像中的赞助口播片段。/ad-cut <video> [--yes]
metadata:
  short-description: 去除课程视频中的赞助口播(LLM 关键词 → faster-whisper 转写 → LLM 二次裁判 → ffmpeg 剪辑)
  version: 0.4.2
  license: see-project
  allowed-tools: Read Write Edit Bash Grep Glob

---

# ad-cut · v0.4.2

> **版本说明**:v0.4.2 在 v0.4.1 基础上修复:① `bin/check_env.py` 检测 ffmpeg / ffprobe / faster-whisper / 模型是否已装;② `scripts/install_deps.sh` 一键安装缺失依赖;③ `bin/transcribe.py` 检测模型已缓存时**跳过下载**(直连 HF)。完整功能同 v0.4.1。

## 何时使用

**合适的场景**:
- 讲座 / 课程录像含有"本节目由 X 赞助"、"广告时间"、"感谢 X 冠名"等明显赞助口播
- 中文(zh)单语种,时长 5 分钟 - 2 小时
- 离线批量处理(非实时流)

**不合适的场景**:
- TV 商业广告(硬切) → 用 Comskip
- 网剧片头片尾 → 帧聚类(P2)
- 多语种混剪 / 实时流
- 文件 < 1 分钟(无剪辑必要)

## 环境需求

| 依赖 | 用途 | 安装 |
|---|---|---|
| ffmpeg / ffprobe | 切片 + 拼接 | `winget install ffmpeg`(Windows) / `apt install ffmpeg`(Linux) |
| Python 3.12 + faster-whisper | ASR 转写 | `py -3.12 -m venv myvenv && myvenv/Scripts/pip install faster-whisper` |
| faster-whisper 模型 | Stage 2 ASR | 自动下载(或 `$HF_HOME/hub` 已有则直接用) |
| awk(原生 Windows 即可) | 关键词匹配 + 时间窗口合并 | (无需安装) |
| claude CLI | Stage 1 关键词扩展 + Stage 4 二次裁判 | (自动检测 `claude` / `claude-haha.cmd`) |

**环境变量**(国内必设):
```bash
export ADCUT_PYTHON="/path/to/venv/Scripts/python.exe"   # faster-whisper 的 Python
export HF_ENDPOINT="https://hf-mirror.com"             # 模型镜像(国内必设)
export HF_HUB_DISABLE_XET=1                            # 关 XET 加速器
```

**一键检测 + 安装**:
```bash
"$ADCUT_PYTHON" bin/check_env.py            # 看哪些缺
bash scripts/install_deps.sh                 # 一键装缺的(--yes 可跳过确认)
bash scripts/install_deps.sh --model medium  # 装 medium 而非 small
```

`bin/check_env.py` 检查 4 项:① `ffmpeg` 在 PATH;② `ffprobe` 在 PATH;③ `faster-whisper` 在 `$ADCUT_PYTHON` 指向的 venv 里可 import;④ 模型 `Systran/faster-whisper-{model}` 已缓存到 `$HF_HOME/hub`(`HF_HOME` 默认 `~/.cache/huggingface`)。

## Output Contract

每跑一次 `/ad-cut <video.mp4>`,产生:

| 产物 | 路径 | 说明 |
|---|---|---|
| `<basename>_no-ads.mp4` | 当前目录 | 剪辑后视频 |
| `<basename>_no-ads.edl.json` | 当前目录 | Edit Decision List,可手动修改后重跑 Stage 6 |
| `ad-cut/<slug>/` | 当前目录 | 中间产物:transcript / keywords / candidates / judged |

`<slug>` = 原文件名的 hash 或短 md5,避免长路径 / 重名冲突。

---

## Stage 0 · Pre-flight Checks

**触发**:任何 /ad-cut 调用第一步。

**检查清单**:
1. **意图验证**:用户说"剪广告 / 去赞助 / 切掉冠名"?是 → 继续;否(单/双字通用词如"广告")→ STOP 问用户
2. **环境检测**(调 `bin/check_env.py`):ffmpeg / ffprobe / faster-whisper / 模型是否就绪。任一缺失 → 提示运行 `bash scripts/install_deps.sh`(不自动装,要用户明确触发)
3. **文件存在**:`<video>` 路径可读,大小 > 1 MB?
4. **格式**:扩展名是 mp4 / mkv / mov 之一?
5. **时长**:先试 `ffprobe -v error -show_entries format=duration -of csv=p=0 <video>`;**失败时 fallback 到 `ffmpeg -i <video> 2>&1 | grep Duration`**(winget 装 ffmpeg 但 ffprobe 缺 DLL 的常见情况)。1min - 3h 之间?
6. **claude CLI**:`command -v claude` 或 `claude-haha.cmd`,任一可用即通过(脚本自动 fallback)
7. **环境变量**:`$ADCUT_PYTHON` 指向装了 faster-whisper 的 Python?未设 → STOP,提示具体修复命令

**Stage 2 转写前的模型缓存复用**(v0.4.2+):`bin/transcribe.py` 先在 `$HF_HOME/hub` 找模型 snapshot。命中 → 用本地路径 + `local_files_only=True`,**绝不发起网络请求**;未命中 → 走默认路径,自动用 `$HF_ENDPOINT` 镜像下载(国内必须设)。

## Stage 1 · LLM 关键词扩展

**目的**:从用户给的 1-3 个核心词扩展到 30-50 个口语变体。

**做法**:
```bash
KEYWORDS=$(claude -p "扩展以下[zh]课程视频赞助口播的关键词到 50 个口语变体,涵盖:'本节目由 X 赞助/冠名/广告时间/由 X 提供/特别感谢 X'. 输出纯 JSON list,无 markdown." < /dev/null 2>/dev/null | sed -n '/^\[/,/^\]/p')
```

**注意**:
- `< /dev/null` 防 stdin 污染
- `2>/dev/null` 抑制 stderr
- `sed -n '/^\[/,/^\]/p'` 只取 JSON 数组(去掉 Claude 的开场白)

**写入**: `ad-cut/<slug>/keywords.json`

**STOP 条件**:扩展后少于 10 个有效关键词 → STOP 问用户补充。

## Stage 2 · faster-whisper ASR 转写

**调用**:`bin/transcribe.py`(wrapper,绕过 faster-whisper 无 CLI 的问题):

```bash
"$ADCUT_PYTHON" bin/transcribe.py <video> ad-cut/<slug>/transcript.json
```

**模型缓存复用**(v0.4.2+):`transcribe.py` 启动时会先在 `$HF_HOME/hub/models--Systran--faster-whisper-{model}/snapshots/` 找已下载的模型:
- **命中** → 用本地路径 + `local_files_only=True`,**0 网络请求**(适合离线 / 模型已下载场景)
- **未命中** → 走 faster-whisper 默认下载流程,**自动用 `$HF_ENDPOINT` 镜像**(国内必设 `https://hf-mirror.com`)

**参数**(默认):
- model: `small`(可换 medium/large-v3,但 small 适合中文课程)
- language: `zh`
- word_timestamps: `True`(为 Stage 3 关键词 ±2s 匹配准备)

**输出**:`transcript.json` 含 segments[{start, end, text, words[{start, end, word}]}]

**STOP 条件**:转写失败 → 检查 `ADCUT_PYTHON` / `HF_ENDPOINT`

## Stage 3 · 关键词匹配 + ±2s padding

**算法**:
1. 对每个 segment,逐 word 检查是否含 keywords 任一词
2. 命中 → 记录 `[word_start - 2, word_end + 2]` 窗口
3. 用 awk 合并重叠窗口(unix 风格:`awk` 排序 + 区间合并)

**典型 awk 一行**:
```bash
awk 'BEGIN{OFS="\t"} {if($1<=curr_end) curr_end=$2>curr_end?$2:curr_end; else{if(curr_end)print curr_start,curr_end; curr_start=$1; curr_end=$2}} END{if(curr_end)print curr_start,curr_end}' candidates.tsv | sort -k1n
```

**输出**:`ad-cut/<slug>/candidates.json`(`[{start, end, hit_text}]`)

**STOP 条件**:0 命中 → **SKILL.md 设计要求 STOP**(没广告就不剪,不要强行截几段)

## Stage 4 · LLM 二次裁判

**目的**:Stage 3 关键词匹配有假阳性(如"爸爸妈妈"含"妈妈"假广告词),LLM 二次过滤。

```bash
JUDGED=$(claude -p "判断以下课程视频片段是否为赞助口播...返回 JSON: [{start, end, is_ad, confidence}]. is_ad=false 时 confidence 必填(0-1). 严格区分课程内容 vs 商业赞助." < candidates.json 2>/dev/null | sed -n '/^\[/,/^\]/p')
```

**写入**:`ad-cut/<slug>/judged.json`

**保留**:is_ad=true 的 candidate 进入 Stage 5;false 直接丢弃。

## Stage 5 · Merge + Dry-run + **强 STOP**

**算法**:
1. 合并相邻 judged 候选(< 5s 间隔视为一段)
2. 计算总剪切时长 = sum(end - start)

**输出 dry-run table**:
```
[1] 184.9 - 199.3  (14.4s)  hit: "你都可以联系我们的课程顾问"
[2] 305.1 - 318.7  (13.6s)  hit: "感谢 XX 冠名播出"
---
总剪切: 28.0s / 30:00 (1.55%)
预计输出: 29:32 (与原视频时长 -28s)
```

**🚨 强 STOP**:打印后**不调用 Stage 6**。等用户回复:
- `y` → 进入 Stage 6
- `n` → 退出,不剪切
- `adjust` → 用户改 EDL → 重跑

`--yes` 标志:可跳过 Stage 0 前的"是否开始"确认,但**不**禁用 Stage 5 dry-run gate。

## Stage 6 · ffmpeg trim + concat

**算法**(单 concat filter,interleaved `[v0][a0][v1][a1]...`):

```bash
# 1. trim 每个 keep 段
# 2. 单 concat:v=1:a=1,n=keep_segments
#   (注意:不能拆成 v⊆i + a⊆i 双 filter,会触发 Media type mismatch)
```

**命令模板**(per-judged EDL):
```bash
ffmpeg -y -i input.mp4 \
  -filter_complex "0:trim=START1:END1,setpts=PTS-STARTPTS[v0]; \
                  0:atrim=START1:END1,asetpts=PTS-STARTPTS[a0]; \
                  ...[v{a1}_a{N-1}][concat]interleave=n={2N}:v=1:a=1[outv][outa]" \
  -map "[outv]" -map "[outa]" \
  output.mp4
```

**写入**:`<basename>_no-ads.mp4` + `<basename>_no-ads.edl.json`

## Stage 7 · Report

输出:
```
✅ 完成: 30:00 → 29:32 (-28s)
保留: 28 段 / 总 30:00 (98.4%)
剪切: 2 段 / 总 28s (1.6%)
EDL: <basename>_no-ads.edl.json  (可手动调整后重跑 Stage 6)
中产物: ad-cut/<slug>/
```

---

## Red Flags

⚠️ **以下情况必须 STOP,不要继续**:

1. 文件不存在 / 不可读
2. 时长 < 1min 或 > 3h
3. Stage 3 0 命中 → 不剪,告诉用户"未检测到广告"
4. Stage 4 全部 false → 同上
5. Stage 5 dry-run 后**永远等用户回复**(哪怕 --yes)
6. `ADCUT_PYTHON` 未设 / faster-whisper 未装 → 报环境问题,不强行用系统 Python
7. 命中片段占视频 > 30% → 警告"广告过多,可能是误判,建议先 review EDL"
9. 用户改 EDL 后重跑 Stage 6 → 必须先校验 EDL JSON 格式,坏格式不要 ffmpeg

## 已知限制(v0.4.1)

- **仅 zh 单语种**(英文版 P2)
- **5min - 2h**(更长 slow,P2 优化)
- **不支持 TV 硬广告 / 网剧片头**(用 Comskip / 帧聚类)
- **不支持实时流**

## v2/v3 Roadmap(非 v0.4 范围)

- **v2 网剧片头片尾**:帧聚类(无监督)
- **v3 TV ads**:Comskip 集成(Plex/Jellyfin DVR 后处理)
- **scripts/edl.py**:EDL 重剪独立工具