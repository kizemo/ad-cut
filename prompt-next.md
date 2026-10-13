# ad-cut skill · next-session prompt

**状态**: ✅ v0.3.0 已 ship,12 个 Task 全完成。

**已装/已交付**:
- `~/.claude/skills/ad-cut/` (SKILL.md 232 行, README.md, bin/transcribe.py)
- `~/.claude/commands/ad-cut.md`
- `~/.claude/plans/2026-08-15-ad-cut-*-notes.md` (RED + REFACTOR + e2e evidence)
- `F:\soft\00selfmade\cut-ad\handoff-ad-cut-skill-2026-08-15.md` (DEPLOY 版)

**已验证(真机)**:
- 5 min + 30 min 测试视频
- 0 命中 → SKILL.md 正确 STOP
- 假阳性 "爸爸妈妈" → Stage 4 LLM 正确拦截
- Stage 6 ffmpeg trim+concat 64s 跑通
- EDL sidecar 可重剪(改 EDL → 重跑 Stage 6 → 精确输出)
- 5 个错误路径全部 ✅

**待办(非阻塞)**:
1. README FAQ 加 Python 3.14 + cython wheel 缺失提示(VERIFY-FINDING-06)
2. 找个真有赞助口播的视频测真"剪广告"流程(目前用户测试视频无广告)

**下一步**:
- 给用户演示 / 让他自己跑一次真视频
- 如果用户报 bug,按 e2e-evidence.md 的 VERIFY-FINDING 表查

**禁止事项**:
- 不要重写 SKILL.md 主体(v0.3.0 已通过 VERIFY)
- 不要把 `claude -p` 改回无 `< /dev/null`(会让 stderr 污染 stdout)
- 不要把 Stage 6 ffmpeg 改回两个独立 concat filter(Media type mismatch bug)