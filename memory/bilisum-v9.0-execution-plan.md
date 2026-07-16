---
name: bilisum-v9.0-execution-plan
description: v9.0最终执行蓝图 — 整合v8.7 25 Bug + v9.0 bilinote 50Agent验证(5功能+9移植) + wdkns-skills功能 + AI问答优化 → 四大阶15子Phase路线图 (2026-07-16)
metadata:
  type: project
  priority: highest
  created: 2026-07-16
  agentCount: 250+
  status: plan-ready
  base_memories:
    - bilisum-v8.7-master-bug-list (80+ Agent, 25 bugs, 3-layer MVP)
    - bilisum-v9.0-bilinote-integration-plan (50 Agent, 5 features)
    - bilinote-open-source (bilinote cloned /tmp/bilinote)
    - bilisum-v8.7-optimization-plan (AI QA quality + kb_dir fix)
    - all-active-rules (21 rules, 4 blocks)
    - wdkns-skills-open-source (wdkns/wdkns-skills: 字幕三级回退+关键帧+LaTeX)
  git_baseline: b8b333b (current HEAD)
---

# BiliSum v9.0 — 最终执行蓝图 (50 Agent验证完成版)

## ⭐ 用户指定优先级 (2026-07-16)

**优先实现以下两项（来自wdkns-skills），排在其他所有新功能之前：**
1. **画面关键帧抓取** — 关键帧→VLM识别(公式/图表/代码/型号)→写入KB"## 画面内容"+总结prompt注入
2. **平台话术过滤** — "一键三连/关注投币/点赞收藏"等非教学内容从弹幕/评论/字幕中清除

执行顺序调整: Phase 1 Bug修复(F1-F5) → **平台话术过滤(零依赖先做)** → **画面关键帧(需VLM选型)** → 其余v9.0功能

## 执行总览

| 阶段 | 名称 | 工作内容 | 预估 |
|------|------|---------|------|
| **阶段一** Phase 1 | v8.7 Layer 1 (5 fix, ~30行) | numpy安装+delete_video先行+全文扩展+多P+日志 | 2h |
| **阶段一** Phase 2 | v8.7 Layer 2 (4 fix, ~50行) | AI总结复活+ASR后台+delete解耦+localStorage同步 | 4h |
| **阶段二** Phase 3 | 多平台链接导入 | bilinote URL检测+yt-dlp+新API+进度SSE | 4h |
| **阶段二** Phase 4 | 本地上传+总结 | upload端点+ffmpeg+asr+导入管道 | 4h |
| **阶段二** Phase 5 | 思维导图v2 | 独立LLM+交互SVG(折叠/缩放/拖拽/跳转)+导出 | 4h |
| **阶段二** Phase 6 | 导出格式扩展 | .txt+.srt+MD增强(含导图JSON) | 2h |
| **阶段二** Phase 7 | 任务历史+追踪 | jobs.json状态机+前端面板+取消机制 | 3h |
| **阶段三** Phase 8 | AI问答升级(3功能×5Agent) | 画面OCR→导入全量化→问答改进 | 6h |
| **阶段四** Phase 9-10 | 残余清理+全量验证 | Layer 3修复+回退验证 | 5h |
| **总计** | | **25 bugs + 8 features** | **~34h** |

---

## 阶段一: v8.7 Bug修复 (Phases 1-2)

### Phase 1: Layer 1 (5 fix, ~30行, 2h)

来源: [[bilisum-v8.7-master-bug-list]] Layer 1

| Fix | Bug | 文件:行 | 改动 | 状态 |
|-----|-----|---------|------|------|
| F1 | C1: numpy未安装 | requirements.txt | `pip install numpy sentence-transformers` | 待做 |
| F2 | C3: 删除前未删旧向量 | kb.py:188前 + favorites.py:90,291 | `rag.delete_video(bvid)`在`add_video`之前 | 待做 |
| F3 | H5: JSON截断5000 | kb.py:85 | `text[:5000]`→`text[:50000]` | 待做 |
| F4 | H7: 单页字幕 | kb.py:152 + fav:76,266 | `get_full_subtitle`→`get_full_subtitle_multi` | 待做 |
| F5 | H9: danmaku静默 | kb.py:167,176 | `logger.debug`→`logger.warning` | 待做 |

### Phase 2: Layer 2 (4 fix, ~50行, 4h)

| Fix | Bug | 参考源 | 改动 |
|-----|-----|--------|------|
| F6 | H1: generate_summary死代码 | bilinote summarizer.ts(849行) | 导入后调用LLM总结+存KB JSON |
| F7 | H2: ASR 6s超时 | bilinote transcriber.ts(255行) | 后台任务+轮询替代6s wait_for |
| F8 | H3+H4: delete异常 | bilibili-rag(引用计数删除) | os.remove包try+JSON缺失也清理其他层 |
| F9 | H8: localStorage不同步 | Obsidian Clipper(持久化模式) | 页面加载调 `GET /api/settings` 合并 |

---

## 阶段二: v9.0 新功能 (Phases 3-7)

来源: [[bilisum-v9.0-bilinote-integration-plan]] + 50 Agent验证

### 50 Agent参考源码移植目录

| 移植 | 参考源→BiliSum | 代码位置 |
|------|----------------|---------|
| T1: yt-dlp下载 | bilinote video.ts→bilibili.py | downloadAudioFromOnlineVideo输出模板 |
| T2: 字幕回退链 | bilinote bilibili.ts:subtitle fallback | CC→AI→页面刮取→yt-dlp→Whisper |
| T3: LLM总结prompt | bilinote summarizer.ts→summarizer.py | 7维度结构化JSON |
| T4: 转写管道 | bilinote transcriber.ts→asr_service.py | whisper-cli集成+缓存 |
| T5: 任务状态机 | bilinote jobs.ts→job_manager.py | 6状态+进度+取消 |
| T6: 文件注册表 | Bili23 file.py→database.py | safe_remove+按manifest清理 |
| T7: 依赖检查 | bilinote server.ts→main.py | GET /api/system/dependencies |
| T8: 多平台识别 | bilinote server.ts:URL regex→import_url.py | B站/YouTube/直链路由 |
| T9: 导出格式 | bilinote server.ts export→export.py | .txt+.srt+Markdown |

### Phase 3: Feature 1 — 多平台视频链接 (P0)

- 新文件: backend/routers/import_url.py (平台检测+URL导入)
- 修改: multi-platform.html (已有, 传SSE进度)
- 复用: api_rag_save管道 + yt-dlp wrapper
- 关键: 下载到配置的download_dir/{平台}_{id}/

### Phase 4: Feature 2 — 本地视频上传 (P0)

- 新端点: POST /api/local-video/upload (ffmpeg抽音频→asr转写→KB导入→总结)
- 支持: .mp4 .mov .mkv .webm
- 复用: asr_service.transcribe_video

### Phase 5: Feature 3 — 思维导图v2 (P1)

- 独立LLM prompt: 按视频时序4-6根节点多层级
- 纯JS SVG渲染: 折叠+缩放+拖拽+点击跳转时刻
- 导出: PNG + JSON嵌入DOCX

### Phase 6: Feature 4 — 导出扩展 (P1)

- .txt纯字幕 + .srt时间轴 + Markdown(含导图JSON) + Obsidian保持

### Phase 7: Feature 5 — 任务历史 (P2)

- jobs.json持久化: QUEUED→DOWNLOADING→TRANSCRIBING→SUMMARIZING→COMPLETED/FAILED
- 前端: 任务面板+进度条+取消按钮(复用已有AbortController设计)

---

## 阶段三: AI问答优化 (Phase 8)

来源: [[bilisum-v8.7-optimization-plan]]
- 功能A: 画面信息抓取 (关键帧→OCR/VLM→KB文本) — 参考wdkns-skills(提取图表/公式/代码)
- 功能B: KB导入管道统一化 (字幕→ASR→弹幕→评论→关键帧→AI总结全量入库)
- 功能C: 问答机制 (全文回退+否认重试+RAGAS评测+向量重建)

---

## 阶段四: 清理+验证 (Phases 9-10)

- F10: 导入完整性检验 (content_manifest + 前端结构化toast)
- F11: OCR/VLM画面文字 (opt-in, VLM API key)
- F12: 向量全量重建按钮 (Post-Bug0遗留)
- 回退: git基线b8b333b, 每Phase独立分支

---

## 关联记忆
- [[bilisum-v8.7-master-bug-list]] — Bug详情
- [[bilisum-v8.7-session-state]] — 会话状态
- [[bilisum-v9.0-bilinote-integration-plan]] — bilinote集成细节
- [[manual-verification-checklist]] — 当前8项待核验
