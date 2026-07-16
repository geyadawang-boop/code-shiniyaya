---
name: bilisum-v8.5-delivered
description: BiliSum v8.5 发布完成: 桌面EXE + GitHub v8.5 tag + E盘 + 17项修复 (2026-07-15)
metadata:
  type: project
  priority: highest
  updated: 2026-07-15
  status: delivered
---

# BiliSum v8.5 — 发布完成

## 交付物
| 目标 | 路径 |
|------|------|
| 桌面EXE | `C:\Users\shiniyaya\Desktop\BiliSum8.5-win64.zip` (87MB) |
| E盘 | `E:\即将完成\BiliSum8.5-win64.zip` (MD5 verified) |
| GitHub | `fix-claude-findings` branch, tag `v8.5`, 13 commits since v8.4 |
| 源代码 | `C:\Users\shiniyaya\Desktop\cc\B站总结工具\B站视频总结工具 -cc\` |

## v8.4 → v8.5 变更

### 5 项重大修复
1. **AI 评论** — 双通道: `x/v2/comment/reply?sort=2` (无需WBI/登录, 来自原始 bilibili.js) + `x/v2/reply/wbi/main` cursor 分页 (来自 bili-note)
2. **AI 问答** — 三层回退: UnifiedSearcher (ChromaDB+FTS5 RRF) → db.search_kb() (纯FTS5) → 直接 JSON 文件子串扫描
3. **智能分类** — `classifier.py:37` KB_DIR 统一为 `database.py` 路径 (之前两个文件夹分叉, 所有分类数据丢失)
4. **KB 导入增强** — `api_rag_save` 现在存储 字幕+弹幕精华+热门评论 (不再仅纯字幕)
5. **内嵌 B站** — iframe + `allow-same-origin` 替代页内 fetch/XHR monkey-patching (匹配原始 proxy-route.js 架构, 无 CSP 冲突)

### 2 项小修复
6. **KB 删除同步** — JSON + chunks + FTS5 + ChromaDB + 分类缓存 → 五层清理
7. **DeepSeek URL** — `favorites.html` placeholder 修复: `https://api.deepseek.com/v1` → `https://api.deepseek.com/v1/chat/completions`

## 使用方法
```
1. 解压 BiliSum8.5-win64.zip
2. pip install -r backend/requirements.txt
3. 双击 启动BiliSum.bat
4. 打开 http://127.0.0.1:8000/browse
5. ⚙️ API 设置 → 选 DeepSeek, 填入密钥 → 保存
```

## 后续优化计划
- 内嵌B站 Service Worker (无限滚动代理)
- AI 评论子回复独立抓取 + cursor 全量分页
- 多维度总结增强 (bili-note 写前预算 + 写后评分)
- 第 5 按钮 "完整内容" + DOCX 思维导图嵌入
- 思维导图 PDF 导出
- KB 管理增强 (Obsidian vault 扫描, 外部 URL 导入, 批量 BV 导入)

## 关联记忆
- [[bilisum-v8.5-pending-issues]]
- [[bilisum-v8.5-test-results]]
- [[bilisum-v8.4-session-state]]
- [[bilisum-v8.4-pending-issues]]
