---
name: bilinote-open-source
description: PrideWood/bilinote — GitHub开源参考。Node.js+React B站/YouTube视频笔记工具。功能：在线链接加载、本地上传、思维导图、导出、历史记录。2026-07-16纳入清单。
metadata:
  type: reference
  source: https://github.com/PrideWood/bilinote
  created: 2026-07-16
  status: cloned-analyzed
---

# bilinote (PrideWood/bilinote)

- GitHub: https://github.com/PrideWood/bilinote
- 技术栈: Node.js 20+ (Express TS) + React + Vite + whisper.cpp + yt-dlp + ffmpeg
- 运行方式: `npm install && npm run dev` (前后端并行启动, 前端 :5173, 后端 :3001)

## 功能清单

| 功能 | 描述 | 关键文件 |
|------|------|---------|
| 在线视频链接加载 | 粘贴B站/YouTube/直链URL → 自动下载字幕 → 总结 | server/server.ts:246 (POST /api/jobs/url) |
| 本地视频上传 | .mp4/.mov/.mkv/.webm 上传 → 提取音频/字幕 → 转写总结 | server/server.ts:197 (POST /api/jobs) |
| 字幕优先+Whisper回退 | 在线先抓字幕；无字幕→下载音频→whisper.cpp转写 | server/transcriber.ts, server/video.ts |
| yt-dlp下载 | --extract-audio + --write-subs + --write-auto-subs | server/video.ts:downloadAudioFromOnlineVideo |
| 音频提取 | ffmpeg抽音频为16kHz单声道wav | server/video.ts:extractAudio, extractAudioFromUrl |
| 知识总结 | LLM生成: 概览、核心结论、知识点树、逻辑脉络、时间轴、术语、复习问题 | server/summarizer.ts (849行) |
| 思维导图 | 单独调用大模型按视频顺序生成多层级导图；节点可折叠/缩放/拖拽/跳转时刻 | server/summarizer.ts |
| 导出 | .txt字幕、.srt字幕、Markdown笔记、保存到Obsidian vault | server/server.ts:361-395 |
| B站API集成 | bvid解析、视频信息、字幕提取 | server/bilibili.ts (603行) |
| 历史记录 | uploads/jobs.json本地存储，含状态/进度 | server/jobs.ts (177行) |
| 系统依赖检查 | ffmpeg/yt-dlp/whisper-cpp检查+一键安装 | server/server.ts:110-130 |
| Whisper模型管理 | 列出可用模型+安装模型 | server/server.ts:133-170 |

## 关键代码模式

### 思维导图生成 (summarizer.ts)
- 独立LLM调用，prompt要求按时间顺序生成4-6个根节点
- 前端React渲染：可折叠/缩放/拖拽，节点可点击跳转视频时刻

### yt-dlp下载到指定路径
```typescript
const outputTemplate = path.join(audioOutputDir, `${jobId}.%(ext)s`);
// --no-playlist --extract-audio --audio-format wav --audio-quality 0
```

### 多平台支持
- server.ts:257 从URL判断bilibili/YouTube/直链 → 不同下载策略
- bilibili.ts:603行完整B站API (视频信息、字幕、多P)

## BiliSum缺失功能

| bilinote功能 | BiliSum现状 |
|-------------|------------|
| 本地上传视频+总结 | ❌ 完全缺失 |
| YouTube/多平台链接 | ❌ 仅B站 |
| 思维导图(LLM多层级+交互) | ⚠️ 有初版但无放缩/拖拽/跳转 |
| 导出.txt/.srt | ⚠️ 仅.md通过Obsidian导出 |
| 保存到Obsidian vault | ✅ 已有 |
| 系统依赖检查+一键安装 | ❌ 缺失 |
| whisper.cpp管理界面 | ❌ 无 (BiliSum用python faster-whisper) |
| 任务历史持久化(jobs.json) | ⚠️ 有history表但无任务进度追踪 |

## 关联记忆
- [[bilisum-all-reference-sources]] — 更新到包含此项目
- [[bilisum-v8.7-master-bug-list]] — 本软件发现的部分bug bilinote已解决
- [[bilisum-v8.7-optimization-plan]]
