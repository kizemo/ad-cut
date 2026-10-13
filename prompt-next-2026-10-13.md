# ad-cut · next-session prompt (v0.4.0-rebuilt)

承接上一个会话任务:ad-cut skill v0.4.0-rebuilt 重建 + GitHub 仓库建立 + 恢复计划编写已完成。

请按以下必读顺序阅读文档,先掌握项目全貌再动手:

1. `F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-10-13.md` — 现状 + 必读顺序(本文件)
2. `F:\soft\00selfmade\ad-cut\plan-restore-skill.md` — 完整恢复计划(11 个新文件,总工时 ~7h,按 §9 优先级执行)
4. `F:\soft\00selfmade\ad-cut\handoff-ad-cut-skill-2026-08-15.md` — v0.3.0 原版 handoff(Stage 0-7 结构 + 6 个 VERIFY 修复参考)
5. `F:\soft\00selfmade\ad-cut\SKILL.md` — 当前 v0.4.0-rebuilt 实际逻辑
6. https://github.com/kizemo/ad-cut — 远程仓库(本地 `origin` 已配)

**禁读**:`ad-cut/end_1786841068/`(只数据)+ `prompt-next.md`(v0.3.0 旧版)+ `~/.claude/plans/`(已永久丢失)。

**下一步必交付**(per plan §9):从 `scripts/stage1_keywords.sh` 开始,按表序逐个写 11 个新文件,然后 pytest 验证 + 5min/30min/60min e2e 测试 + GitHub 打 `v0.5.0` tag + 同步 `~/.claude/skills/ad-cut/` 从 GitHub clone 覆盖。

**关键避坑**:Stage 6 单 concat interleaved(`[v0][a0]...concat=n=N:v=1:a=1` 不能拆双 filter);Python 必须 3.12(3.14 cython 无 wheel);`claude -p < /dev/null 2>/dev/null`(防 stdin/stderr 污染);HF_ENDPOINT=hf-mirror.com(国内必设);Stage 3 0 命中是 STOP 不是错。

**当前 commit**:`7efeb17`(main 分支,origin 已 push);**未 commit**:plan-restore-skill.md + handoff-ad-cut-skill-2026-10-13.md + 本文件,用户决定后再 commit。