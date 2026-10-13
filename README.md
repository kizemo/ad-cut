# ad-cut Skill · v0.4.0-rebuilt

去除讲师课程录像中的赞助口播片段。**自动识别 + 二次裁判 + 精确剪辑**。

> ⚠️ **v0.4.0-rebuilt 是 2026-10-13 从 handoff 文档反向重建的版本**,**不是** 2026-08-15 ship 的 v0.3.0 原版。Stage 1/4 LLM prompt 和 Stage 6 ffmpeg filter graph 完整命令为重建版本。Stage 0/3/5/7 结构性逻辑忠实于 handoff。

## 用法

```bash
# 设置环境(Windows Git Bash)
export ADCUT_PYTHON="/path/to/venv/Scripts/python.exe"   # faster-whisper 所在的 Python
export HF_ENDPOINT="https://hf-mirror.com"              # 国内必设
export HF_HUB_DISABLE_XET=1

# 触发
/ad-cut /path/to/lecture.mp4              # interactive
/ad-cut /path/to/lecture.mp4 --yes        # 跳 Stage 0 前的确认(Stage 5 仍 STOP)
"帮我把 lecture.mp4 的赞助剪掉"           # 自然语言触发
```

## 产物

| 产物 | 说明 |
|---|---|
| `<basename>_no-ads.mp4` | 剪后视频 |
| `<basename>_no-ads.edl.json` | Edit Decision List(可手动修改后重跑 Stage 6) |
| `ad-cut/<slug>/keywords.json` | Stage 1 扩展关键词 |
| `ad-cut/<slug>/transcript.json` | Stage 2 ASR 转写 |
| `ad-cut/<slug>/candidates.json` | Stage 3 关键词命中 |
| `ad-cut/<slug>/judged.json` | Stage 4 LLM 二次裁判 |

## 安装

### 1. 系统依赖

```bash
winget install ffmpeg        # ffmpeg + ffprobe
winget install jqlang.jq     # jq(可选,SKILL.md 默认用 awk)
```

### 3. Python venv(⚠️ 必须 3.12,3.14 装不上 faster-whisper)

```bash
# Windows
py -3.12 -m venv myvenv
myvenv/Scripts/pip install faster-whisper
```

**Python 3.14 警告**:faster-whisper 依赖 cython,3.14 当前无 cython wheel。请用 Python 3.12。

### 2. 环境变量

写入 `~/.bashrc`(Git Bash)或 PowerShell profile:

```bash
export ADCUT_PYTHON="/c/Users/<yourname>/myvenv/Scripts/python.exe"
export HF_ENDPOINT="https://hf-mirror.com"
export HF_HUB_DISABLE_XET=1
```

## 验证

详见 `F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-08-15.md`(v0.3.0 原版的 e2e 证据)。

## FAQ

**Q: 重建版与原版 v0.3.0 有什么不同?**
A: Stage 0/3/5/7 结构同原版;Stage 1/4 LLM prompt 措辞可能微调;Stage 6 ffmpeg filter graph 完整命令由"两个独立 concat"改为"单 concat interleaved"(per handoff VERIFY-FINDING-03 fix)。

**Q: Stage 3 0 命中就 STOP,合理吗?**
A: 合理。课程录像本身可能没有广告,强行截几段会让视频逻辑断裂。STOP 提示用户"未检测到广告"。

**Q: Stage 5 dry-run gate 能否跳过?**
A: 不能。`--yes` 标志只跳过 Stage 0 前的"是否开始"确认。Stage 5 dry-run 是不可绕过的强 STOP,让用户最后 review EDL。

**Q: 改了 EDL 想重剪?**
A: 修改 `<basename>_no-ads.edl.json`,然后**只跑 Stage 6**(不需要重跑 Stage 1-5)。

**Q: 多语种 / TV 硬广告 / 网剧片头片尾?**
A: 不在 v0.4 范围。TV 硬广告用 Comskip;网剧片头片尾用帧聚类(详见 SKILL.md "v2/v3 Roadmap")。

## License

See project handoff for original v0.3.0 license.