---
name: bilisum-p0-bugs
description: 18 P0-level critical bugs found in BiliSum — ALL FIXED as of 2026-07-09 v7.2 Codex+Claude 16-agent sweep
metadata: 
  node_type: memory
  type: project
  updated: 2026-07-09T23:45:00Z
  originSessionId: f2f0e50d-c35d-4ea4-94d4-c2d0e2f3fba5
---

# BiliSum P0 关键 Bug 清单 (18 个) — 全部已修复 ✅

> 最后更新: 2026-07-09 | 修复方法: Codex adversarial review + Claude 16 个修复 Agent + 安全测试套件 (99 项)
> Codex 交叉验证: Codex 独立确认了全部 CRITICAL/HIGH 级问题，与 Claude 发现互相印证

## 崩溃级 (11 个) — 全部已修复 ✅

1. ✅ summarizer.py:318-322 — `stream:True` + `r.json()` → **已修复** — stream:False 显式设置，由 v7.1 Agent A01 修复
2. ✅ rag_service.py:85-114 — `_init_embeddings` 内 return 后死代码 → **已修复** — v7.1 重构，Agent-08 用 n-gram hash + TF-IDF 替换了 broken MD5 embedding
3. ✅ database.py:96 — init_db() close 后未重置 _pool_local.conn → **已修复** — Agent-11 移除了 threading.local() 连接池，每次调用创建新连接
4. ✅ main.py:2362-2366 — api_export_ai_notes 8 个未定义变量 → **已修复** — 路由已迁移至 routers/kb.py，所有变量已正确初始化
5. ✅ summarizer.py:299,305 — thinking block 中 content[0]["text"] → **已修复** — Agent-06 在访问前添加了 type=="text" 过滤，3 处均已修复
6. ✅ main.py:2574 — `time.sleep(2)` 缺少 `import time` → **已修复** — 替换为 asyncio.sleep(2)，路由已迁移至 routers/misc.py
7. ✅ main.py:2208 — `.replace('','/')` 空操作 → **已修复** — 路由已迁移，新实现使用正确的路径连接
8. ✅ bilibili_client.py:71,91,109 — 字幕始终取 subs[0] → **已修复** — _pick_subtitle() 实现分层选择（手动中文 > AI 中文 > 第一个可用）
9. ✅ bilibili_client.py:52-55 — 多 P 视频 cid → **已修复** — Agent-06 为 get_full_subtitle 添加了可选 cid 参数
10. ✅ browse.html:205-209 — loadDiscover() 缺少 else → **已修复** — Agent-05 为两个函数都添加了 else 分支 + 错误处理
11. ✅ main.py:1481 — Cookie GET 传输 → **已修复** — 全部改为 POST + request body

## 安全级 (5 个) — 全部已修复 ✅

12. ✅ main.js:306 — CDP 端口 9222 → **已修复** — 由 BILISUM_DEV=1 环境变量控制 + 绑定 127.0.0.1
13. ✅ main.py:984-988 — /api/settings GET 暴露 API key → **已修复** — 现在返回 mask_key (前8后4，中间打码)
14. ✅ api.js:33-42 — API key GET 参数发送 → **已修复** — API key 现在从后端设置表读取，通过 POST body 发送
15. ✅ main.py:96-102 — CORS allow_origins=["*"] + allow_credentials=True → **已修复** — 改为显式 localhost 源列表
16. ✅ main.py:139-180 — 静态文件路径遍历 → **已修复** — 路由迁移至 routers/static.py，_safe_path() 使用 os.path.basename + normcase

## 依赖级 (2 个) — 全部已修复 ✅

17. ✅ requirements.txt — 缺少 8 个包 → **已修复** — Agent-10 添加 yt-dlp，其余已包含
18. ✅ package-lock.json — 版本不匹配 → **已修复** — 已重新生成 lock 文件

## 本轮发现的额外 P0（Codex + Claude 交叉验证）— 全部已修复 ✅

19. ✅ routers/ai.py:89-93 — summarize_with_claude() TypeError（参数 budget=/visual_warning= 不存在） → **已修复** Agent-02
20. ✅ preload.js:43,59 — 设置键 regex 阻止所有驼峰键名 → **已修复** Agent-01，改用 _allowedSettingKeys.has()
21. ✅ main.js:77-78 — 后端不可达时 Cookie 永久丢失 → **已修复** Agent-03，本地持久化解耦于 HTTP 响应
22. ✅ rag_service.py:23-41 — DeterministicEmbedding (MD5→随机向量) 产生无意义余弦相似度 → **已修复** Agent-08，n-gram hash + TF-IDF
23. ✅ style.css:1676 — [aria-hidden="true"] { display: none !important } 破坏全局无障碍 → **已修复** Agent-05

**Why:** v7.2 是 BiliSum 历史上首次由 Codex 和 Claude 双重验证的全面修复。Codex 对抗性审查独立发现了与 Claude Explore Agent 相同的所有 critical/high 问题（互相印证），Claude 额外发现了 26 个 Codex 未覆盖的问题。全部 32 项修复已直接写入源文件并完成语法验证。

**How to apply:** 本文件是所有 P0 修复的权威记录。后续开发前读取本文件 + bilisum-v7.2-dual-audit-report.md 以确保无修复回退。
