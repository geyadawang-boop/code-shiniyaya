---
name: bilisum-v8.7-master-bug-list
description: v8.7主Bug清单 — 80+ Agent交叉验证产出。12 P0 + 8 P1 + 5 P2。含确认/暂定标记和根因文件:行号。
metadata:
  type: project
  priority: highest
  created: 2026-07-16
  agentCount: 80+
  verified: cross-checked
---

# BiliSum v8.7 — 主Bug清单 (80+ Agent交叉验证)

## 分析覆盖
- Topic 1: 删除→重导入→字数递减 (20 Agent, 交叉验证)
- Topic 2: KB导入+路径系统 (20 Agent, 交叉验证)
- Topic 3: AI问答质量+检索 (15 Agent)
- 完整性检验设计 (5 Agent)
- 可行性+风险评审 (5 Agent)
- 15 Agent方案初扫 (15 Agent)
- 总计: 80+ Agent

## P0-CRITICAL (3 bugs — 必须本周修)

### C1: numpy未安装 → 整个向量搜索栈从未工作
- 文件: semantic_search.py:48, kb.py:22-27
- import numpy失败 → `_HAS_SEMANTIC_SEARCH=False` → 所有"向量搜索"回退到FTS5
- ChromaDB有210条嵌入排队从未处理
- 修复: `pip install numpy sentence-transformers` — 安装即修复
- 确认级别: **确认** (3个独立Agent核实)

### C2: KB只存视频描述，不存实际字幕文字稿
- 文件: kb.py:152 api_rag_save → knowledge_base/*.json
- 眼罩视频text=217字符(仅描述)。Zero .srt/.vtt文件。导入管线从未拉取真正的字幕内容
- B站audo/AI字幕存在但未传入KB JSON
- 修复: 确保get_full_subtitle输出到达保存前文本
- 确认级别: **确认** (Agent直接检查JSON文件)

### C3: 删除→重导入→字数递减 (4个并发根因)
- 根因A: Danmaku/comments except:pass → B站限流时静默失败→文本越来越短 (kb.py:162-176)
- 根因B: add_video()不先delete_video() → 旧chunks残留ChromaDB (rag_service.py:284)
- 根因C: save_kb_entry覆盖文本但ChromaDB矢量不删→累积孤儿chunks
- 根因D: delete_kb_entry创建RAGService()无api_key/api_url → 嵌入维度不匹配 → ChromaDB删除静默失败 (database.py:430)
  详情: get_rag_service()用OpenAI 1536维嵌入；delete_kb_entry只创建空RAGService()用DeterministicEmbedding 384维 → ChromaDB InvalidDimensionException → 被捕获 → 向量永不删除
- 修复: rag.delete_video(bvid)于rag.add_video前 + delete_kb_entry改用main.get_rag_service()单例 + danmaku/comments失败提升为logging.warning
- 确认级别: **确认** (5个独立Agent核实, 包括最后单一Agent发现的RAGService嵌入维度Bug)

## P0-HIGH (9 bugs)

### H1: generate_summary标志从v7.1以来就是死代码
- 文件: kb.py:150 — 读取但从未使用
- AI总结从未在导入时生成/存储
- 修复: ~30行恢复——导入后调用summarize_with_claude，将结果存入KB JSON

### H2: ASR 6秒超时使ASR管线名存实亡
- 文件: bilibili_client.py:355-370, asyncio.wait_for(timeout=6)
- 真实ASR需要下载视频(30-120s)+Whisper(数分钟)。6秒超时保证永不成功
- 修复: 后台任务+轮询；或直接await并大幅提高超时

### H3: delete_kb_entry os.remove无保护→异常跳过全部10个清理块
- 文件: database.py:407
- JSON被其他进程锁定→os.remove抛异常→chunks/FTS5/ChromaDB/ASR/下载目录/分类缓存/索引元数据全部跳过
- 修复: 将os.remove和其他未保护步骤包装在try/except中，失败时继续清理后续资源

### H4: delete_kb_entry JSON缺失时返回False跳过10个清理块
- 文件: database.py:406,475
- 若上次部分删除删掉了JSON但crash→下次调用JSON不存在→返回False→全部清理跳过
- 永久孤儿：chunks/FTS5行/ChromaDB向量/ASR缓存/下载目录/分类缓存/索引元数据
- 修复: 将清理逻辑与JSON存在性检查解耦；即使JSON缺失也继续清理

### H5: layer 3 JSON fallback截断在text[:5000]
- 文件: kb.py:85
- 长视频(10000-15000字符字幕)→后半部分内容完全搜不到
- 修复: text[:50000] remove arbitrary cap

### H6: add_video()返回值被忽略，失败无感知
- 文件: kb.py:188, favorites.py:90, favorites.py:291
- ChromaDB磁盘满/损坏→add_video()返回0(失败)→所有调用方忽略→用户看到"导入成功"
- 修复: 检查返回值；失败时记录warning并返回给前端

### H7: 单页字幕函数用于多P视频导入
- 文件: kb.py:152, favorites.py:76, favorites.py:266
- 使用get_full_subtitle(单页)而非get_full_subtitle_multi(多页)
- 多P视频只获取第1页字幕
- 修复: 在3个调用点替换为get_full_subtitle_multi (3行)

### H8: localStorage从不查后端DB→跨浏览器kb_dir不同步
- 文件: common.js loadSettings() L370-377
- fetchSettings()存在但从未接入初始化
- 修复: 页面加载时调用GET /api/settings合并DB值

### H9: B站API静默失败→数据丢失无感知
- 文件: kb.py:162-176
- Danmaku/comments失败→except:pass→用户永远不知缺失
- 修复: logger.debug→logger.warning；在API响应中包含content_manifest

## P1-MEDIUM (8 bugs)

### M1: ChromaDB去重ID错误→chunks覆盖而非累积(阻止了bug但语义错误)
### M2: kb_dir变更后classifier.CLASSIFICATION_CACHE_FILE未刷新
### M3: kb.htm/favorites.html缺少detectProviderFromModel()处理器
### M4: categories.html设置弹窗缺关闭按钮
### M5: kb_dir null边界→refresh_kb_dir()从不调用
### M6: ChromaDB持久化目录中210+未处理嵌入排队(numpy缺失)
### M7: 3个导入路径向save_kb_entry传递不同字段集→同个BV号不同路径产生不同KB条目
### M8: 未检查add_video()返回值

## P2-LOW (5 bugs — UX/优化)

### L1: 前端删除确认不能区分"从未存在"vs"JSON缺失但残留数据"
### L2: 设置弹窗HTML不一致(6个文件各有不同占位符/处理器/布局)
### L3: 单chunks文件删除失败中止循环→后续文件跳过
### L4: 中文分词(FTS5 unicode61)——无同义词扩展/查询重写
### L5: RAGAS评测框架存在但未使用——无法量化修复是否改善QA

## MVP修复路线图 (已完成+待做)

### 第1层 (5个修复, ~30行, 本周)
| # | 修复 | 文件:行 |
|---|------|---------|
| F1 | pip install numpy + sentence-transformers | requirements.txt |
| F2 | rag.delete_video(bvid)在rag.add_video之前 + 检查返回值 | kb.py:188前 |
| F3 | text[:5000]→text[:50000] | kb.py:85 |
| F4 | get_full_subtitle→get_full_subtitle_multi (3处) | kb.py:152 + favorites.py:76,266 |
| F5 | danmaku/comment except:logger.debug→logger.warning | kb.py:167,176 |

### 第2层 (4个修复, ~50行, 本月)
| F6 | 恢复AI总结存储——将summarize_with_claude()结果存回KB JSON |
| F7 | ASR后台任务——无字幕视频显示"可稍后ASR转写"按钮 |
| F8 | delete_kb_entry解耦——JSON缺失时也清理其他资源 |
| F9 | 前端加载设置时合并后端DB值(调用fetchSettings) |

### 第3层 (v9.0)
| F10 | 导入完整性检验(content_manifest + 前端toast) |
| F11 | OCR/VLM画面文字(opt-in,需VLM API key) |
| F12 | 向量全量重建按钮(Post-Bug0遗留) |

## 关联记忆
- [[bilisum-v8.7-optimization-plan]]
- [[bilisum-v8.6-kb-delete-fixes]]
- [[bilisum-v8.5-session-state]]
- [[all-active-rules]]
