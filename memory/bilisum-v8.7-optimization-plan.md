---
name: bilisum-v8.7-optimization-plan
description: v8.7后续优化计划 — AI问答质量(画面信息抓取+KB导入+问答机制, 每功能5Agent对比源文件) + kb_dir路径验证Bug + 人工核验清单模板
metadata:
  type: project
  priority: high
  created: 2026-07-15
---

# BiliSum v8.7 后续优化计划

## 用户实测反馈 (2026-07-15 v8.6核验)

眼罩推荐视频案例: 视频画面标注了5款眼罩型号+音频有提及，
但AI问答回复"源文本中没有列出" — 导入内容缺失画面信息，问答机制不尽人意。

## 优化任务1: AI问答质量三大功能 (用户指定: 每个功能分配5个Agent对比源文件)

### 功能A: 画面信息抓取 (5 Agent对比)
- BiliSum现状: frame_extractor.py/scene_detector.py/thumbnail_generator.py 存在但仅用于AI总结的视觉上下文(ai.py _build_visual_context)，导入KB时完全不用
- 差距: KB导入只存 字幕+弹幕+评论 文本，画面中的商品名/型号/标注文字全部丢失
- 对比源: video-frames skill / VideoChat / vsummary / Bili23-Downloader截图 / bilibili-rag视觉管道
- 方向: 导入时抽关键帧→OCR或VLM识别画面文字→并入KB text

### 功能B: 知识库导入与管理 (5 Agent对比)
- BiliSum现状: api_rag_save存 字幕+弹幕100条+评论40条
- 差距: 无ASR回退接入导入流(无字幕视频只存元数据)、无画面信息、无AI总结结果回存KB
- 对比源: bilibili-rag(content_fetcher+ASR管道) / bili-note(多素材归档+manifest) / knowledge-rag-src / LegalGraphQA
- 方向: 导入管道升级为 字幕→(无字幕时ASR)→弹幕→评论→关键帧文字→AI总结 全量入库

### 功能C: AI问答机制 (5 Agent对比)
- BiliSum现状: _hybrid_search_kb三层回退 + system prompt
- 差距: 检索片段不够或未命中时直接说"没有列出"，不做二次检索/全文回读；Bug 0修复后向量库需重建索引(历史数据是幽灵状态)
- 对比源: bilibili-rag(查询路由+校准) / LegalGraphQA(RunnableParallel并行检索) / rag-eval(RAGAS评测) / semantic-search skill
- 方向: 命中率低时自动回读全文 + 重建向量索引 + RAGAS评测闭环

### 执行方式 (写入: 用户要求逐个功能5 Agent)
- 每功能启动5个Agent: 2个读参考源 + 2个读BiliSum现状 + 1个综合方案
- 共15 Agent, 产出old→new方案后走 用户+Codex双批准 再执行

## 优化任务2: kb_dir路径验证Bug (v8.6核验发现, 待修复)

- 根因: api_settings表 kb_dir='知识库存储路径' (占位文字非路径), _get_kb_dir() isabs检查失败静默回退默认目录
- 后果: 用户设置知识库路径"成功"但导入文件仍进默认目录 (核验3/5失败的原因)
- 修复方案(待审批): settings POST对kb_dir/download_dir做验证 — 必须绝对路径+可写探针(参考Bili23 ensure_directory_accessible directory.py:17-39), 无效则返回明确错误而非静默接受; 前端展示错误
- 附带: 浏览器模式"📁浏览"只能拿文件夹名(安全限制), 需提示用户手动输入完整路径或用Electron

## 人工核验清单模板 (每轮修复后使用)

1. ChromaDB初始化: 启动日志找 "ChromaDB initialized: collection=bilisum_kb, docs=N"
2. 删除确认框: 知识库页+收藏夹页删除按钮 → 应列出6层删除范围
3. 删除清理文件: 删ASR转写过的视频 → data/asr_cache/{bvid}_*.m4a 应消失; downloads/{bvid}/ 应消失
4. 下载路径: 设置下载路径→下载视频→应进 {设置路径}/{bvid}/
5. kb_dir热更新: 改知识库路径(不重启)→导入新视频→新目录应出现{bvid}.json
6. AI问答: 问已导入视频具体内容 → 应召回(向量检索正常)

## v8.6核验结果记录 (2026-07-15)
- 1⚠️ 日志无法查看; AI问答召回质量差(引出优化任务1)
- 2✅ 确认框生效
- 3❌ KB文件未进用户目录(优化任务2根因)
- 4✅ 下载路径生效
- 5❌ kb_dir热更新表面不生效(实际是任务2的验证缺失问题, refresh_kb_dir本身工作正常)

## 关联记忆
- [[bilisum-v8.6-kb-delete-fixes]]
- [[bilisum-v8.5-session-state]]
- [[all-active-rules]]
