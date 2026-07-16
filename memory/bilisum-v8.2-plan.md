---
name: bilisum-v8-2-plan
description: BiliSum v8.2 完整计划 — 动态总结长度 + 分类页面优化 + 4项Bug修复 + UP主内容提取
metadata: 
  node_type: memory
  type: plan
  priority: highest
  created: 2026-07-13
  status: pending-codex-approval
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum v8.2 完整计划

## 需求汇总

### 用户要求1: 动态总结长度
总结长度由多维度综合决定:
- 信息密度 (字幕中有效信息占比)
- 知识价值度 (教学/科普 vs 娱乐/闲聊)
- 理解难度 (术语密度/专业程度)
- 视频时长
- 字幕字数
- 画面丰富度 (远期，需OCR)
- 在当前基础上适当加长

### 用户要求2: 全部内容发给AI
- 字幕全文发给AI (不裁切)
- 弹幕全部发给AI (不裁切)
- 评论区全部内容发给AI (不裁切)
- UP主发的评论+弹幕单独摘出，独立一节"UP主观点"

### 用户要求3: 评论价值筛选
- 不只传数量，要传有价值的评论
- 已有 relevance_score (ai.py L555-561) 按关键词匹配
- AI分析评论端点已有精选逻辑

### 用户要求4: 分类页面来源区分
- 分类整理根据收藏夹和知识库两个来源
- 加按钮区分: 只看知识库 / 只看收藏夹 / 全部

### Bug修复 (4项)
1. 弹幕橙色背景+UP主标记不生效 (前端重复计频)
2. AI评论"无可读取的评论" (Cookie缺失)
3. 思维导图 Markmap.create传参错误 (div vs svg)
4. 分类页面垃圾标签 (stop_chars不足 + author误入tag + blacklist不完整)

## 实现方案

### Phase A: Bug修复 (立即，零风险)

A1. summary.html L594-604 — 弹幕前端改为解析后端前缀标签
A2. bilibili_client.py + ai.py — get_all_comments Cookie检查 + 友好错误提示
A3. summary.html L371-389 — Markmap.create传入SVG元素而非div
A4. classifier.py L380-406 + L340-344 + L686 — stop_chars补全 + blacklist扩充 + 移除author tag

### Phase B: 分类页面来源区分

B1. categories.html — 新增来源切换按钮栏:
  <button onclick="switchSource('kb')">知识库</button>
  <button onclick="switchSource('favorites')">收藏夹</button>
  <button onclick="switchSource('all')">全部</button>

B2. kb.py — browse端点新增 source 参数 (kb/favorites/all)
B3. database.py — get_kb_list_filtered 支持来源筛选
B4. favorites.py — 收藏夹视频列表端点，返回与kb相同格式

### Phase C: 动态总结长度

C1. quality.py — 新增3个分析函数:
  compute_information_density(subtitle_text) -> float
  compute_knowledge_value(video_type, subtitle_text, tags) -> float
  compute_difficulty_level(subtitle_text) -> float

C2. quality.py compute_note_budget — 新参数参与base_target_min计算:
  + information_density * subtitle_chars * 0.01
  + knowledge_value * duration_minutes * 10
  + difficulty * duration_minutes * 5
  + min(danmaku_count, 500) * 0.8
  提高base_target_min下限从1200→1800，上限从45000→65000

C3. summarizer.py — max_tokens范围从[1823,32000]→[2400,64000]

### Phase D: UP主内容 + 全文传递

D1. prompt_engine.py build_video_context() — 新增参数:
  - up_comments: list[str] UP主评论
  - up_danmaku: list[str] UP主弹幕
  - 新增段落 "UP主观点" 独立列出

D2. routers/ai.py api_summarize — 提取UP主评论+弹幕:
  up_name = info.owner_name
  up_comments = [c for c in comments if c.user == up_name]
  up_danmaku = [d for d in danmaku if d.startswith("[UP主]")]

D3. 字幕/弹幕/评论全文传递:
  prompt_engine.py 移除字幕裁切 (目前_text_sample[:2000]→全文)
  弹幕全文传入 (目前可能被截断)
  评论全文传入

## 修改文件 (9个)

1. frontend/summary.html — A1(弹幕) + A3(思维导图)
2. backend/bilibili_client.py — A2(Cookie日志)
3. backend/routers/ai.py — A2(友好错误) + D2(UP主提取)
4. backend/classifier.py — A4(垃圾标签)
5. frontend/categories.html — B1(来源按钮)
6. backend/routers/kb.py — B2(来源参数)
7. backend/database.py — B3(来源筛选)
8. backend/quality.py — C1+C2(动态token)
9. backend/prompt_engine.py — D1+D3(UP主+全文)

## 关联
- [[dynamic-summary-length]]
- [[bilisum-v8.1-compression-state]]
