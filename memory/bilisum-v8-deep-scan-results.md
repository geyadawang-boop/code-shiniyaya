---
name: bilisum-v8-deep-scan-results
description: 14 Agent深入交叉扫描汇总 — BiliSum vs 10参考源，57 .py + 12前端，发现60+P0、100+P1、50+P2
metadata:
  type: project
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum v8.0 深入交叉扫描结果

## 扫描范围
- BiliSum: 57 .py (28,177行) + 12前端 + 3 Electron
- 参考源: 10个
- Agent: 14个维度交叉对比

## P0致命发现 (必须立即修复)

### 前端+API
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 1 | DELETE /api/kb/delete缺CSRF豁免 → 删除功能403 | main.py L217 |
| 2 | Obsidian导出发送空bvids → 按钮永远导出0文件 | favorites.html L766 |
| 3 | 同步进度轮询字段完全不匹配 → 进度条永不显示 | favorites.html L469-473 vs favorites.py L14-44 |
| 4 | categories.html完全独立 → 无API key/无设置入口 | categories.html |
| 5 | 18个前端API调用无api.js封装 → 缺CSRF token | 多个HTML文件 |

### LLM/AI安全
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 6 | prompt_engine.py 8个字段零消毒 | prompt_engine.py L1065-1112 |
| 7 | classifier.py f-string裸注入 | classifier.py L288-293 |
| 8 | KB RAG问答 + chat/stream 无中文输出指令 | routers/kb.py L251, L311 |
| 9 | SYSTEM_PROMPT 无中文输出约束 | prompt_engine.py L964 |

### 数据库/存储
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 10 | 删除操作零ChromaDB清理 → 向量孤岛 | database.py L283-308 |
| 11 | 删除操作零kb_index_meta清理 | semantic_search.py L1184 |
| 12 | 所有数据库函数同步阻塞事件循环 | database.py L18-40 |
| 13 | 4个函数重复全量KB文件扫描(N+1) | database.py L522/601/644/684 |

### 字幕/弹幕
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 14 | 多P视频所有分P获取相同字幕(cid未传) | routers/bilibili.py L111 |
| 15 | ASR yt-dlp零Cookie → 受限视频100%失败 | asr_service.py L62-64 |
| 16 | all_channels_failed从未设为True | bilibili_client.py L281-297 |

### B站客户端
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 17 | resolve_b23_url损坏 → Location头永不可用 | bilibili_client.py L541 |
| 18 | 核心API(视频信息/评论/弹幕)零重试 | bilibili_client.py L76/308/414 |

### RAG
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 19 | RetrievalPipeline/CrossEncoder/AttentionReorder死代码 | semantic_search.py L1236-1413 |
| 20 | FTS5后备返回snippet但kb.py读content → 后备时RAG崩溃 | database.py L347 vs kb.py L245 |

### 测试/CI
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 21 | CI所有测试失败被|| true吞掉 → CI零门禁作用 | ci.yml L27/29/57 |
| 22 | test_security.py发现真实bug: camelCase IPC键被正则拒绝 | test_security.py L429-443 |
| 23 | 25个Python模块零测试 | 多个 |

### 依赖
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 24 | tiktoken未在requirements.txt → 导入崩溃 | requirements.txt |
| 25 | python-docx未在requirements.txt → 导入崩溃 | requirements.txt |

### 性能
| # | 问题 | 文件:行号 |
|---|------|-----------|
| 26 | rag_service.py time.sleep()阻塞事件循环 | rag_service.py L158 |
| 27 | Jina/Cohere重排序器同步httpx.Client | semantic_search.py L594/663 |

## P1高优先级 (应尽快修复)

### API层
- POST /api/asr/transcribe, DELETE /api/history, 8个分类/Obsidian端点缺CSRF豁免
- CSRF中间件startswith匹配过宽

### 前端
- favorites.html 9条英文toast消息
- browse.html renderErrorState被本地实现覆盖(使用'!!'残留文本)

### 字幕/弹幕
- WBI密钥空时静默降级为无签名
- 无字幕结果缓存
- Ch1-Ch3 API调用零重试
- 弹幕duration=0时仅1段
- language硬编码zh

### 收藏夹/Obsidian
- N+1查询未修复
- 零断点续传/进度持久化
- push-obsidian REST API路径不可达(无API key)

### B站客户端
- 4处收藏夹API缺WBI签名
- UA字符串3处不一致
- move_favorite_resources创建临时客户端

### RAG
- 5种检索结果格式不一致
- 无集合管理API
- "lost in the middle"无缓解

### 性能
- search_kb回退线性扫描O(N)
- _kb_index缓存无上限
- _df字典无限增长
- LLM回退链max_retries=1

## P2增强

### 导出/工具
- DOCX两路径重叠
- tools.html缺多搜索/DOCX/ZIP/分类的UI
- 7种dynamic-archify格式不适用

### 跨平台
- start.bat仅Windows
- Obsidian路径假定macOS
- langchain-community/sentence-transformers/whisper/Pillow/torch未列

### 安全
- 3处except:pass吞异常(DNS/分类/Obsidian)
- cancellation.py死代码
- classifier.py使用print()而非logger

### 测试
- diagnose_db.py变量名bug(corpus_count未定义)
- RAG eval触发路径引用不存在文件

## 关联记忆
- [[bilisum-v8-full-scan-report]]
- [[bilisum-v8-session-state]]
- [[bilisum-19-user-issues-diagnosis]]
- [[codex-bilisum-v8-verification-results]]
- [[p0-triple-skill-workflow]]
