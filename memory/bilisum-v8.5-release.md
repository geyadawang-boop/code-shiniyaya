---
name: bilisum-v8.5-release
description: BiliSum v8.5 — GitHub + E盘 + 桌面EXE 全部就绪 (2026-07-15)
metadata:
  type: project
  updated: 2026-07-15
  status: released
---

# BiliSum v8.5 — 发布完成

## 交付物
- **桌面EXE**: `C:\Users\shiniyaya\Desktop\BiliSum8.5-win64.zip` (94MB)
- **GitHub**: branch `fix-claude-findings`, tag `v8.5`, 10 commits v8.4→v8.5
- **E盘**: `E:\即将完成\bilisum8.5\`

## 使用方法 (便携版)
1. 解压 `BiliSum8.5-win64.zip`
2. 确保 Python 3.9+ + pip依赖已安装 (backend/requirements.txt)
3. 双击 `启动BiliSum.bat` — 自动启动后端 + Electron 窗口

## 修复清单
1. AI评论 — `x/v2/comment/reply?sort=2` 主通道 (无需WBI/登录) + `reply/wbi/main` 回退
2. AI问答 — ChromaDB → FTS5 → JSON 三层回退
3. 智能分类 — KB_DIR 统一 (classifier 与 database 路径一致)
4. KB导入 — 字幕 + 弹幕 + 评论完整导入
5. 内嵌B站 — iframe + allow-same-origin (无fetch monkey-patching)
6. KB删除同步 — JSON + chunks + FTS5 + ChromaDB + 分类缓存 五层清理
7. DeepSeek URL — favorites.html placeholder 修复

## 关联记忆
- [[bilisum-v8.5-pending-issues]]
- [[bilisum-v8.5-test-results]]
- [[bilisum-v8.4-session-state]]
