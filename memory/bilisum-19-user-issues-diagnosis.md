---
name: bilisum-19-user-issues-diagnosis
description: 19 项用户反馈问题完整诊断 — 根因 + 文件:行号 + 修复方向 + 状态追踪
metadata:
  type: project
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum 19 项用户问题完整诊断

## P0 崩溃/数据丢失 (6项)

### 1. 弹幕读取报错: get_danmaku() takes 1 positional argument but 2 were given
- 文件: backend\routers\bilibili.py L20
- 根因: 调用 get_danmaku(info.cid, info.duration) 但签名是 get_danmaku(cid: int)
- 状态: ✅ CC已修复

### 2. Obsidian CSRF token missing
- 文件: backend\main.py L217
- 根因: /api/kb/push-obsidian 不在 CSRF_EXEMPT_PATHS
- 状态: ❌ 待Codex修复

### 3. 旧视频无法删除+KB幽灵数据
- 文件: backend\database.py L283-308
- 根因: delete_kb_entry 未清理 kb_chunks_fts + ChromaDB
- 状态: 部分修复 (17a-17d已应用; 17e-17g待修复)

### 4. KB详情页显示错误视频内容
- 文件: frontend\kb.html L154
- 根因: loadKBEntry 调用 /api/kb/search?q=bvid (FTS5模糊匹配) 而非 /api/kb/entry?bvid=bvid (精确查找)
- 状态: ❌ Codex遗漏 (G1)

### 5. KB导入后显示"无内容"
- 文件: frontend\kb.html L166 + database.py search_kb
- 根因: FTS5搜索结果无 content 字段, 前端回退显示 "无内容"
- 状态: 与问题4相同根因

### 6. 总结页导入KB时token missing
- 文件: backend\main.py L217
- 根因: /api/kb/append 不在 CSRF_EXEMPT_PATHS
- 状态: ❌ 与问题2一起修复

## P1 功能问题 (7项)

### 7. 内嵌浏览器仅加载10个视频
- 文件: backend\routers\misc.py + main.js
- 根因: CORS头部无效 + B站XHR被阻止
- 状态: ❌ 待修复

### 8. 内嵌浏览器登录循环
- 文件: main.js cookie存储
- 根因: 加密/明文cookie不同步, 10秒同步延迟
- 状态: ❌ 待修复

### 9. 打开库功能异常
- 文件: main.js + preload.js
- 根因: vault路径双层存储不同步 (后端SQLite DB vs Electron settings.json)
- 状态: ❌ 待修复

### 10. 字幕获取请求超时
- 文件: frontend\js\api.js L73
- 根因: fetchTranscript默认30s超时不够
- 状态: ✅ Codex已修复

### 11. 内嵌页面登录失效
- 根因: 代理页面cookie设置跨域问题
- 状态: ❌ 与问题8一起

### 12. 知识库+下载占据C盘
- 根因: KB_DIR硬编码
- 状态: ❌ 新功能

### 13. Obsidian初始化缺失
- 根因: 无扫描vault .md文件并回导入KB功能
- 状态: ❌ 新功能

## P2 增强 (6项)

### 14. 评论精选不足(30条→40条+UP主优先+子回复)
- 文件: backend\bilibili_client.py + routers\ai.py + frontend\summary.html
- 状态: ❌ Codex遗漏 (G3)

### 15. 思维导图优化(本地CDN+导出+缩放)
- 文件: frontend\summary.html L337-416
- 发现: markmap CDN被CSP阻止 — 思维导图可能从未正常工作
- 状态: ❌ Codex遗漏 (G9)

### 16. DOCX学霸笔记模板
- 文件: backend\docx_exporter.py (265行, 死代码, 从未被调用)
- 状态: ❌ Codex遗漏 (G10)

### 17. AI总结资料不足(多P弹幕未聚合+无UP主标记)
- 文件: backend\summarizer.py + routers\ai.py
- 状态: ❌ Codex遗漏 (G11)

### 18. 视频/音频下载
- 文件: backend\routers\bilibili.py L78-93 (依赖yt-dlp)
- 状态: ❌ 新功能

### 19. 下载路径不可配置
- 文件: frontend\js\api.js L152-159
- 根因: download_dir设置键存在但从未使用
- 状态: ❌ 新功能
