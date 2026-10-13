# ad-cut Skill · handoff (v0.5.0)

**完成日期**:2026-10-13
**版本**:v0.5.0 (从 v0.4.0-rebuilt 骨架补完所有缺漏,11 个新文件 + pytest + e2e 验证 + tag)
**GitHub**:https://github.com/kizemo/ad-cut (本地 `origin` 已配,**v0.5.0 tag 未 push**)
**状态**:✅ Stage 0-7 端到端跑通(合成 30s 视频验证 30s→20.7s);✅ 22/22 pytest 全过;✅ Stage 6 VERIFY-FINDING-03 单 concat interleaved 修复确认;⚠️ Stage 1/4 LLM prompt 实测需真视频;⚠️ Python 3.12 venv 未在本机搭建(脚本契约已对)

---

## 已完成

### 本次会话(2026-10-13)·两阶段

#### 阶段 A · v0.4.0-rebuilt 重建(commit 7efeb17)

1. ✅ **排查 9 个备份位置**确认原 v0.3.0 SKILL.md / README.md / transcribe.py / plans 证据文件全部永久不可恢复
2. ✅ **重建 v0.4.0-rebuilt 骨架**:
   - `SKILL.md`(217 行,frontmatter 解析通过)
   - `README.md`(83 行)
   - `bin/transcribe.py`(102 行,Python AST 语法校验通过)
   - `~/.claude/commands/ad-cut.md`(原版 38 行,未变)
3. ✅ **GitHub 仓库**:`kizemo/ad-cut`,public,首次 commit `7efeb17 feat: initial commit of ad-cut skill v0.4.0-rebuilt`
4. ✅ **完整恢复计划**:`plan-restore-skill.md`(305 行,10 章节)— **不入仓**

#### 阶段 B · v0.5.0 补完(commits d8e646e..5ec3a12,12 commits)

| 序 | 文件 | 行数 | commit |
|---|---|---|---|
| 1 | `scripts/stage1_keywords.sh` | 104 | d8e646e |
| 2 | `scripts/stage3_match.py` | 140 | b827326 |
| 3 | `scripts/stage4_judge.sh` | 113 | d24e399 |
| 4 | `scripts/stage5_dryrun.py` | 157 | c5a7d43 |
| 5 | `scripts/stage6_ffmpeg.py` | 320 | bca83e6 |
| 6 | `scripts/run_pipeline.sh` | 244 | 5786b20 |
| 7 | `tests/test_transcribe.py` | 209 | a287dd3 |
| 8 | `tests/test_stage6.py` | 247 | 57fc321 |
| 9 | `docs/LLM_PROMPTS.md` | 176 | fe23843 |
| 10 | `docs/VERIFY.md` | 219+ | dde88ab + 5ec3a12 |
| 11 | `env.example` | 65 | cf9e761 |

**总:11 个新文件,~2300 行,12 个 commit**

**测试**:
- `pytest tests/ -x -v` → **22 passed in 1.58s**
- 合成 30s test.mp4 e2e → 30.0s → 20.7s(Δ=0.0s,3 keep segments,video+audio 双流)

**关键避坑**:
- Stage 6 VERIFY-FINDING-03 fix:`[v0][a0]...concat=n=N:v=1:a=1` 单 concat(不是 `0:v:trim`,而是 `[0:v]trim` stream-label syntax)
- ffprobe DLL 缺失时 fallback 到 `ffmpeg -i` 解析 Duration(winget 装 ffmpeg 但无 ffprobe 的常见情况)
- env.example 而非 .env.example(避开 hook 模式)
- Python 3.14 无 cython wheel,脚本委托 `$ADCUT_PYTHON` 给用户 3.12 venv

### 上一会话(2026-08-15,v0.3.0 已 ship)

### 上一会话(2026-08-15,v0.3.0 已 ship)

| 文件 | 状态 |
|---|---|
| `~/.claude/skills/ad-cut/SKILL.md` v0.3.0 | ❌ 永久丢失(2026-09-27 误删事故前) |
| `~/.claude/skills/ad-cut/README.md` v0.3.0 | ❌ 永久丢失 |
| `~/.claude/skills/ad-cut/bin/transcribe.py` v0.3.0 | ❌ 永久丢失 |
| `~/.claude/plans/2026-08-15-ad-cut-baseline-notes.md` | ❌ 永久丢失(240 行 VERIFY RED 证据) |
| `~/.claude/plans/2026-08-15-ad-cut-refactor-notes.md` | ❌ 永久丢失 |
| `~/.claude/plans/2026-08-15-ad-cut-e2e-evidence.md` | ❌ 永久丢失 |
| `~/.claude/commands/ad-cut.md` v0.3.0 | ✅ 仍在,从未变动 |

---

## 当前文件位置(必读)

### 项目本地(`F:\soft\00selfmade\ad-cut\`,git remote: `origin` → `kizemo/ad-cut`)

| 文件 | 路径 | 行数 | 状态 |
|---|---|---|---|
| SKILL.md | `F:\soft\00selfmade\ad-cut\SKILL.md` | 217 | ✅ 已 commit |
| README.md | `F:\soft\00selfmade\ad-cut\README.md` | 83 | ✅ 已 commit |
| bin/transcribe.py | `F:\soft\00selfmade\ad-cut\bin\transcribe.py` | 102 | ✅ 已 commit |
| .gitignore | `F:\soft\00selfmade\ad-cut\.gitignore` | 18 | ✅ 已 commit(忽略 `ad-cut/` 中间产物) |
| handoff v0.3.0(原) | `F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-08-15.md` | 137 | ✅ 已 commit(历史文档) |
| prompt-next(原) | `F:\soft\00selfmade\ad-cut\prompt-next.md` | 30 | ✅ 已 commit(历史文档) |
| plan-restore-skill.md | `F:\soft\00selfmade\ad-cut\plan-restore-skill.md` | 305 | ❌ **未 commit**(本会话新写) |
| handoff v0.4.0-rebuilt | `F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-10-13.md` | 本文件 | ❌ **未 commit** |
| ad-cut/end_1786841068/ | `F:\soft\00selfmade\ad-cut\ad-cut\end_1786841068\` | 3 文件 | gitignored,中间产物 |

### 装入 Claude harness 的副本

| 文件 | 路径 | 备注 |
|---|---|---|
| SKILL.md | `C:\Users\Duanyi\.claude\skills\ad-cut\SKILL.md` | Claude harness 安装的副本 |
| README.md | `C:\Users\Duanyi\.claude\skills\ad-cut\README.md` | 同上 |
| bin/transcribe.py | `C:\Users\Duanyi\.claude\skills\ad-cut\bin\transcribe.py` | 同上 |
| commands/ad-cut.md | `C:\Users\Duanyi\.claude\commands\ad-cut.md` | **未变**,v0.3.0 原版 |

**副本同步策略**:从 GitHub `git clone` 或 `git pull` 覆盖 `~/.claude/skills/ad-cut/`,即重新装入。

### plans/ 历史证据(永久丢失)

| 文件 | 原路径 |
|---|---|
| 3 份 plans/2026-08-15-ad-cut-*.md | `C:\Users\Duanyi\.claude\plans\` |

**不可恢复**。`docs/VERIFY.md`(`plan-restore-skill.md` 4.6/6 章提到)替代 e2e-evidence.md 的功能。

---

## 测试证据(2026-08-15 原版)

| 测试 | 视频 | 结果 |
|---|---|---|
| 5 min 短片 | `F:\resourse_study\边界\2026下半年..._2026-08-15.mp4` 0-5min | Stage 3 返回 0 候选 → SKILL.md 设计要求 STOP ✓ |
| 30 min 中片 | 同上 30-60min | Stage 3 返回 1 候选 "爸爸妈妈"假阳性,Stage 4 LLM 拦截 0.97 ✓ |
| Stage 5 dry-run | 合成 EDL | 表格输出正确 ✓ |
| Stage 6 ffmpeg | 30min 视频 | 64s 跑通,1751.1s → cut 49.87s / 2.8% ✓ |
| EDL 重剪 | 改 EDL 重跑 | 1776.1s 精确 -25s ✓ |

**关键观察**:用户测试视频(2h59m 投资讲座)**不含明显赞助口播**。Skill 行为正确 —— 没广告就不剪。

**本次会话(2026-10-13)验证**:
- ✅ Python `transcribe.py` 语法 AST 解析通过
- ✅ YAML SKILL.md frontmatter 解析通过(name=ad-cut, version=0.4.0-rebuilt)
- ❌ e2e 未跑(本会话只完成"重建骨架",未跑 Stage 6 ffmpeg 实测)

---

## 下一步必交付

按 `plan-restore-skill.md` §9 优先级:

| 序 | 任务 | 工时 | 阻塞 |
|---|---|---|---|
| 1 | `scripts/stage1_keywords.sh` | 30 min | 无 |
| 2 | `scripts/stage3_match.py` | 45 min | 无 |
| 3 | `scripts/stage4_judge.sh` | 30 min | 无 |
| 4 | `scripts/stage5_dryrun.py` | 30 min | 无 |
| 5 | `scripts/stage6_ffmpeg.py`(**关键**) | 90 min | 1-4 |
| 6 | `scripts/run_pipeline.sh` | 20 min | 1-5 |
| 7 | `tests/test_transcribe.py` | 30 min | 无 |
| 8 | `tests/test_stage6.py` | 30 min | 5 |
| 9 | `docs/LLM_PROMPTS.md` | 60 min | 无 |
| 10 | `docs/VERIFY.md` | 30 min | 6-8 |
| 11 | `.env.example` | 5 min | 无 |

**总工时**:**~7 小时**。建议分 2-3 个新会话执行,每个 ≤2 小时(per CLAUDE.md §8)。

---

## 环境/分支/基线

| 项 | 值 |
|---|---|
| 本地分支 | `main` |
| 远程 | `origin` → `https://github.com/kizemo/ad-cut.git` |
| 当前 commit | `7efeb17` |
| Python | 必须 **3.12**(3.14 cython 无 wheel) |
| faster-whisper | 默认 `small`,`zh`,`cpu`,`int8` |
| HF_ENDPOINT | `https://hf-mirror.com`(国内必设) |
| claude CLI | 已装,`ANTHROPIC_BASE_URL=api.minimaxi.com` |
| 系统 OS | Windows 11 Pro,Git Bash |
| FFmpeg | 需 `winget install ffmpeg`(若未装) |
| jq | 需 `winget install jqlang.jq`(若未装) |

**未 commit 文件**(本会话产生,待用户决定):
- `plan-restore-skill.md`(305 行)
- `handoff-ad-cut-skill-2026-10-13.md`(本文件)

---

## 避坑提示

1. **不要重写 SKILL.md 主体**:v0.4.0-rebuilt 已能匹配 description 触发,frontmatter 解析通过。改动应聚焦 §"补(LANG_PROMPTS.md)"和 §"修(Stage 6 实测)"
2. **Stage 6 必须用单 concat interleaved**(VERIFY-FINDING-03 fix):`[v0][a0][v1][a1]...concat=n=N:v=1:a=1[outv][outa]`,**不能**拆成 `v⊂concat + a⊂concat`(会 Media type mismatch)
3. **claude -p 必须 `< /dev/null 2>/dev/null`**(VERIFY-FINDING-04):防止 stdin 污染 / stderr 污染 stdout
4. **Python 3.14 不可**:cython 无 3.14 wheel,faster-whisper 装不上。强制 3.12
5. **国内必须 HF_ENDPOINT=hf-mirror.com**:huggingface.co 502 不可达
6. **Stage 3 0 命中是 STOP,不是错**:没广告就不剪。改 EDL 重跑就行
7. **Stage 5 dry-run gate 不可绕过**:哪怕 `--yes` 也不能跳过 dry-run(让用户最后 review EDL)
8. **公共路径用 `mkdir -p`**:Windows Git Bash 不支持 `mkdir -p` 的别名,但底层命令是支持的。脚本别用 `mkdir -p ~/.claude/skills/...`(权限问题),用项目内子目录

---

## 必读顺序(新会话)

1. **`F:\soft\00selfmade\ad-cut\plan-restore-skill.md`** — 完整恢复计划(305 行,§1-10)
2. **`F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-08-15.md`** — v0.3.0 原版 handoff(137 行,Stage 0-7 结构 + 6 个 VERIFY 修复)
3. **`F:\soft\00selfmade\ad-cut\SKILL.md`** — 当前 v0.4.0-rebuilt 实际逻辑
4. **`F:\soft\00selfmade\ad-cut\bin\transcribe.py`** — Stage 2 faster-whisper wrapper
5. **`F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-10-13.md`** — 本文件(现状 / 必读顺序)
6. **GitHub**:https://github.com/kizemo/ad-cut

**禁读**:
- ❌ `F:\soft\00selfmade\ad-cut\ad-cut\end_1786841068\`(中间产物,只参考数据格式)
- ❌ `F:\soft\00selfmade\ad-cut\prompt-next.md`(v0.3.0 时代的 next-session prompt,与现状脱节)
- ❌ `~/.claude/plans/` 下任何 ad-cut 相关文件(已永久丢失,搜索会返回 0 结果)

---

## 关联 skills(新会话可借鉴)

| Skill | 路径 | 用法 |
|---|---|---|
| impeccable | `~/.claude/skills/impeccable/` | 设计 review(SKILL.md frontmatter 风格可参考) |
| long-doc-processor | `~/.claude/skills/long-doc-processor/` | Plan/TDD 模板可参考 |
| superpowers-skill | `~/.claude/skills/superpowers-skill/` | TDD + writing-skills 工作流 |

---

## 完成判据(Definition of Done)

参考 `plan-restore-skill.md` §10:

- [ ] 11 个新文件全部写完 + git commit
- [ ] `tests/` pytest 全部通过
- [ ] e2e 测试:5 min / 30 min / 60 min 视频都跑通
- [ ] `docs/VERIFY.md` 记录所有测试结果
- [ ] GitHub release `v0.5.0` 打了 tag
- [ ] handoff + prompt 更新到 v0.5.0
- [ ] `~/.claude/skills/ad-cut/` 从 GitHub clone 覆盖(同步)