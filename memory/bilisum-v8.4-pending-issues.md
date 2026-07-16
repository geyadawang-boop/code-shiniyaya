---
name: bilisum-v8.4-pending-issues
description: BiliSum v8.4 — 全部待办: 人工核验反馈+待修复Bug+参考源功能优化+用户新需求 (2026-07-15)
metadata:
  type: project
  priority: highest
  updated: 2026-07-15
  status: active
---

# BiliSum v8.4 — 完整待办清单

## 一、人工核验结果（5项 → 3通过 / 1半通过 / 1失败）

| # | 操作 | 结果 | 状态 |
|---|------|------|------|
| 1 | 重启后端 + Electron | 无报错启动 | ✅ 通过 |
| 2 | 4个总结按钮 | 功能正常，无object错误 | ✅ 通过 |
| 3 | 思维导图渲染+导出 | 渲染成功，SVG/Obsidian导出成功 | ✅ 通过 |
| 4 | 内嵌B站首页 | 仍只能加载10个视频，后续无限加载中 | ❌ 失败 |
| 5 | DOCX学霸笔记 | 导出成功 | ⚠️ 半通过(见用户新需求) |

## 二、用户新需求（本轮反馈 2026-07-15）

### A. 6维度详细总结确认
- 6维度(information_density/knowledge_value/difficulty_factor/visual_richness/new_concept_count/danmaku_count)已在 quality.py compute_note_budget() 和 ai.py:151-167 集成
- 当前仅影响 max_tokens 动态缩放，prompt中未显式展示维度结果
- **加入后续优化：** 在详细总结prompt中显式展示6维度分析结果

### B. 思维导图导出PDF ⭐NEW
- 当前：SVG导出 + Obsidian导出
- 新增：PDF导出选项
- 来源：frontend summary.html 已有 exportMindmapSVG()，需加 exportMindmapPDF()

### C. 内嵌B站首页无限滚动 ⭐ 接之前
- 根因：B站XHR/fetch直接发往api.bilibili.com，cookie域不匹配+WBI签名缺失
- 修复方向：注入Service Worker拦截 → 后端proxy-fetch端点

### D. 第5个按钮"完整内容" ⭐NEW ⭐ 重要
- 来源参考：bili-note archive_bili_materials.py 的全量导出模式
- 功能：在summary.html新增第5个模式chip
- 展示内容：
  - AI完整总结
  - 字幕文字稿(带时间戳)
  - 思维导图内嵌插图
  - 热门评论(高赞排序)
  - 弹幕精华(高出现频率)
  - 标签/元数据
- 交互：先在上方展示生成内容，下方有一个"📥 导出完整笔记(.docx)"按钮
- DOCX优化（基于源文件参考）：
  - 整体色调/字体/排版美观度提升 ← BOC content.js 笔记样式
  - 思维导图SVG/PNG插图嵌入 ← 自研
  - 评论区高赞+UP主评论专属区块 ← MediaCrawler 评论模式
  - 弹幕精华词云/高频列表 ← Bili23-Downloader 弹幕分析
  - 章节感知目录(已有)+彩色章节标签
  - 封面页美化(渐变背景+视频封面图)
  - 页眉页脚(BiliSum logo + 页码)

## 三、待修复Bug（3项）

| # | 问题 | 根因推测 | 下一步 |
|---|------|---------|--------|
| 1 | AI评论报"无可读取的评论" | B站API需要特定header/Cookie | 重启后端看终端日志 |
| 2 | AI问答读不到已导入内容 | ChromaDB向量索引可能不同步 | 检查ChromaDB集合是否为空 |
| 3 | 内嵌B站首页无限滚动失效 | XHR/fetch直接发api.bilibili.com+cookie域不匹配+WBI签名缺失 | Service Worker + proxy-fetch端点 |

## 四、参考源功能优化（27项，含用户新需求）

### P1 — 高优先级（8项）

| # | 功能 | 来源参考 | 目标文件 | 状态 |
|---|------|---------|---------|------|
| 1 | 评论全量抓取(不限40条) | MediaCrawler detail cursor分页 | backend/bilibili_client.py | 待实现 |
| 2 | organize_video_content 多分块AI笔记合成 | bilibili-rag markdown_export.py:55-113 | backend/summarizer.py | 待实现 |
| 3 | RAGAS自动评测(5指标+基准答案+CSV) | LegalGraphQA evaluate.py:75-176 | scripts/eval_rag.py | 待实现 |
| 4 | TokenBucket速率限制接入audio下载 | Bili23-Downloader Downloader.py:33-41 | backend/rate_limiter.py | 待接入 |
| 5 | Service Worker拦截fetch/XHR代理B站API | 自研(修复内嵌B站无限滚动) | frontend/sw.js + backend misc.py | 待实现 |
| 6 | proxy-fetch端点+WBI签名注入 | 自研 | backend/routers/misc.py | 待实现 |
| 7 | 6维度显式展示在详细总结prompt | 自研(用户反馈) | backend/summarizer.py build_prompt() | 待实现 |
| 8 | 思维导图PDF导出 | 自研(用户反馈) | frontend/summary.html | 待实现 |

### P1.5 — 第5按钮"完整内容"（5项）⭐NEW

| # | 功能 | 来源参考 | 目标 |
|---|------|---------|------|
| 9 | 第5个mode chip "📦 完整内容" (前端) | bili-note全量导出模式 | frontend/summary.html |
| 10 | 完整内容生成API端点 | 自研 | backend/routers/ai.py api_full_content() |
| 11 | DOCX导出重构：封面美化+渐变背景+视频封面图 | BOC content.js样式 | backend/docx_exporter.py |
| 12 | DOCX思维导图插图嵌入(SVG→PNG) | 自研 | backend/docx_exporter.py |
| 13 | DOCX评论区+弹幕精华区块 | MediaCrawler+Bili23-Downloader | backend/docx_exporter.py |

### P2 — YAML引擎增强（4项）← BOC content.js

| # | 功能 | 来源 | 目标 |
|---|------|------|------|
| 14 | YAML前端字段UI自定义(字段开关/类型编辑) | content.js:4760-4775 | frontend settings |
| 15 | 5类型格式化 | content.js:4906-4943 | backend/yaml_frontmatter.py |
| 16 | 模板变量resolveFrontmatterTemplateValue | content.js:4884-4893 | backend/yaml_frontmatter.py |
| 17 | 日期-标题文件名 | content.js:5163-5183 | backend/routers/kb.py |

### P2 — 字幕/导出增强（2项）← Bili23-Downloader

| # | 功能 | 来源 | 目标 |
|---|------|------|------|
| 18 | 多格式字幕导出(SRT/LRC/TXT/ASS) | SubtitlesParser.py:13-133 | backend/routers/export.py |
| 19 | 版本迁移check_need_patch | config.py:444-462 | bootstrap.py |

### P2 — KB/检索增强（4项）

| # | 功能 | 来源参考 | 目标 |
|---|------|---------|------|
| 20 | 并行检索RunnableParallel(替代串行) | LegalGraphQA qa_chain_refactored.py:302-309 | backend/rag_service.py |
| 21 | 三向差异检测(新增/修改/删除) | LegalGraphQA kb_manager.py:108-110 | backend/routers/favorites.py |
| 22 | Chunk级UPSERT(替代JSON覆盖) | transcript_db.py:59-79 | backend/database.py |
| 23 | 搜索自动触发build_index | knowledge-rag knowledge_api.py:99-125 | backend/routers/kb.py |

### P2 — 知识管理增强（2项）← karpathy-llm-wiki-vault

| # | 功能 | 来源 | 目标 |
|---|------|------|------|
| 24 | wiki/index.md + wiki/log.md 结构化索引 | karpathy wiki目录 | backend/routers/kb.py |
| 25 | 双向链接[[page]]强制+知识冲突追踪 | karpathy wiki | Obsidian导出模块 |

### P3 — 新功能（5项）

| # | 功能 | 来源参考 | 目标 |
|---|------|---------|------|
| 26 | 本地视频文件导入(mp4→ASR→KB) | vsummary Whisper | 新功能 |
| 27 | Obsidian vault扫描+回导入KB | BOC vault集成 | backend/routers/kb.py |
| 28 | 外部URL导入→抓取→KB | ClawHub knowledge-rag | 新功能 |
| 29 | 批量BV号队列导入 | bilibili-rag knowledge.py | backend/routers/favorites.py |
| 30 | B站AI摘要get_video_summary | bilibili-rag bilibili.py:343 | backend/bilibili_client.py |

### P3 — awesome-selfhosted 外部参考（4项）

| # | 功能 | 参考项目 |
|---|------|---------|
| 31 | AI第二大脑/RAG agent | Khoj |
| 32 | 内置RAG/MCP兼容 | AnythingLLM |
| 33 | 即时模糊搜索(MeiliSearch) | MeiliSearch |
| 34 | 媒体整理+搜索 | Tube Archivist |

## 五、历史遗留（11项）

| ID | 问题 | 文件 |
|----|------|------|
| H02 | Obsidian CSRF token | main.py |
| H04/H05 | KB详情页显示错误/无内容 | kb.html |
| H08 | 内嵌浏览器登录循环 | main.js |
| H09 | vault路径不同步 | main.js |
| H14 | 评论增强(时间戳定位) | summary.html |
| H15 | 思维导图本地CDN | summary.html |
| H16 | DOCX模板自定义 | docx_exporter.py |
| H17 | AI总结增强(UP主风格) | summarizer.py |
| D01 | main.py路由去重 | main.py |
| D02 | MCP Server模式 | 新功能 |
| D03 | E2E测试(Playwright) | 新功能 |

## 关联记忆
- [[bilisum-v8.4-session-state]]
- [[bilisum-all-reference-sources]]
- [[bilisum-reference-import-registry]]
- [[reference-source-function-mapping]]
- [[bilisum-19-user-issues-diagnosis]]
- [[bilisum-remaining-deferred]]
