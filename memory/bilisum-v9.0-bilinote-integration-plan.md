---
name: bilisum-v9.0-bilinote-integration-plan
description: v9.0计划 — 基于bilinote对比分析，增加5大功能：多平台链接页、本地上传+总结、思维导图升级、导出格式扩展、任务历史系统。50 Agent对比验证产出。
metadata:
  type: project
  priority: high
  created: 2026-07-16
  base: bilinote (PrideWood/bilinote) + all prior bug lists
  agent_count: 50 (pending execution)
---

# BiliSum v9.0 — bilinote集成优化计划

## 背景

发现PrideWood/bilinote（Node.js+React, B站/YouTube本地视频笔记工具）与BiliSum高度互补。
通过50 Agent对比验证产出功能缺口和执行方案。

## 功能缺口对比总结 (bilinote vs BiliSum)

| bilinote功能 | BiliSum v8.7 | 缺口 |
|-------------|-------------|------|
| 粘贴链接→自动加载视频+字幕 | ✅ 已有 (导入知识库) | 0 |
| YouTube/多平台链接 | ❌ 仅B站 | **CRITICAL** |
| 本地上传视频→总结 | ❌ 完全缺失 | **CRITICAL** |
| 思维导图(LLM多层级+可折叠/缩放/拖拽/跳转) | ⚠️ 初版无交互 | **HIGH** |
| 导出.txt/.srt | ⚠️ 仅.md | MEDIUM |
| 保存Obsidian vault | ✅ 已有 | 0 |
| 系统依赖检查+一键安装 | ❌ 缺失 | MEDIUM |
| 任务历史(jobs.json+进度追踪) | ⚠️ history表无进度 | MEDIUM |

## 5大功能添加计划

### Feature 1: 多平台视频链接加载 (P0 — 新页面)
- 新建页面 `frontend/multi-platform.html`
- 输入URL→自动识别平台(B站/YouTube/直链)→yt-dlp下载→字幕提取→KB导入
- 复用BiliSum现有的 `api_rag_save` 管道
- 确保下载到用户配置的 `download_dir`
- 参考: bilinote server/server.ts L246-276 (POST /api/jobs/url), video.ts downloadAudioFromOnlineVideo
- 文件: 新增 backend/routers/multi_platform.py, frontend/multi-platform.html

### Feature 2: 本地视频上传+总结 (P0)
- 上传 .mp4/.mov/.mkv/.webm
- ffmpeg提取音频→whisper转写→字幕文本→KB导入→总结
- 复用BiliSum的 asr_service.py (transcribe_video) 和 api_rag_save
- 下载路径: 遵循用户配置的 download_dir/{title}_{hash}/
- 参考: bilinote server/server.ts L197-244 (POST /api/jobs with multer), video.ts extractAudio, transcriber.ts
- 文件: backend/routers/local_video.py, 前端上传UI

### Feature 3: 思维导图升级 (P1)
- LLM独立调用(prompt按时间顺序生成4-6根节点×多层级)
- 前端React/SVG: 节点可折叠、缩放(Ctrl+滚轮)、拖拽
- 节点可点击→跳转视频相应时间戳
- 所有节点可保存为JSON→嵌入DOCX
- 参考: bilinote summarizer.ts 思维导图生成prompt + App.tsx渲染
- 文件: backend/routers/mindmap.py (独立LLM调用), frontend/mindmap.html/js

### Feature 4: 导出格式扩展 (P1)
- 新增 .txt 纯文本字幕导出
- 新增 .srt 时间轴字幕导出
- Markdown笔记导出增强(含思维导图JSON嵌入)
- 现有功能保持: Obsidian vault保存
- 参考: bilinote server/server.ts L361-395
- 文件: backend/routers/export.py (增强现有)

### Feature 5: 任务历史+进度追踪 (P2)
- 按jobId追踪: 排队→下载中→转写中→总结中→完成/失败
- 持久化到uploads/jobs.json
- 前端: 任务列表面板+进度条+取消按钮
- 参考: bilinote server/jobs.ts (完整job状态机), server/server.ts L175-290
- 文件: backend/job_manager.py, frontend/jobs.html

## 执行方式 (50 Agent对比验证)

### Phase 1: 功能对比 (15 Agent)
- 5 Agent: 多平台链接 (bilinote bilibili.ts 603行 vs BiliSum bilibili_client.py → 提取最佳模式)
- 5 Agent: 本地上传+转写 (bilinote video.ts+transcriber.ts vs BiliSum asr_service.py+frame_extractor.py)
- 5 Agent: 思维导图+导出+历史 (bilinote summarizer.ts+jobs.ts vs BiliSum summarizer.py+kb.py)

### Phase 2: 代码移植方案 (15 Agent)
- 5 Agent: yt-dlp下载到指定路径 (bilinote video.ts模式→BiliSum现有bilibili.py改造)
- 5 Agent: 链接识别+多平台路由 (bilinote server.ts URL类型检测→BiliSum新endpoint)
- 5 Agent: 思维导图LLM prompt+前端交互 (bilinote summarizer.ts→BiliSum)

### Phase 3: 集成验证 (10 Agent)
- 5 Agent: 功能互不冲突验证 (新增路由/前端页面/Bug修复共存)
- 5 Agent: 性能+UX评估 (下载路径统一、文件组织、用户流程)

### Phase 4: 最终合成 (10 Agent)
- 5 Agent: 完整old→new代码 (所有5大功能 = ~8个新文件+5个修改)
- 5 Agent: 交叉验证+回退方案 (每个功能独立git branch，互不干扰)

## 回退路径
- 基线: git commit b8b333b (v8.5) 或当前HEAD
- 每功能独立分支: feat/multi-platform, feat/local-video, feat/mindmap-v2, feat/export-formats, feat/job-history
- 单功能回退: `git checkout main -- <file>` 仅影响该功能文件
- 全量回退: `git checkout b8b333b -- .`

## 关联记忆
- [[bilinote-open-source]] — 开源项目详情
- [[bilisum-v8.7-master-bug-list]] — v8.7当前Bug（先修Bug再加功能）
- [[bilisum-v8.5-session-state]] — 历史上下文
- [[all-active-rules]] — 规则
