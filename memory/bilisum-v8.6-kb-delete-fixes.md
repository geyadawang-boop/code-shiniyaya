---
name: bilisum-v8.6-kb-delete-fixes
description: v8.6 KB删除6Bug修复记录 — Bug 0-4已修(Phase A+B)，Phase C待做。回退基线commit b8b333b。含每项old→new回退路径。
metadata:
  type: project
  priority: highest
  created: 2026-07-15
  status: phase-a-b-done
---

# BiliSum v8.6 — KB删除孤儿文件 6 Bug 修复

## 回退基线

- Git基线: commit `b8b333b` (v8.5最后一个commit，本轮修改前)
- 一键全回退: `git checkout b8b333b -- backend/database.py backend/main.py backend/rag_service.py backend/routers/bilibili.py backend/routers/kb.py`
- 修改涉及5个文件，无其他文件受影响

## 6 Bug状态

| Bug | 状态 | 文件 |
|-----|------|------|
| 0 ChromaDB async静默失败 | ✅已修+双验证 | rag_service.py |
| 1 ASR缓存不清理 | ✅已修 | database.py |
| 2 下载mkdtemp泄漏 | ✅已修 | bilibili.py |
| 3 download_dir死代码 | ✅已修(核心) | bilibili.py |
| 4 KB_DIR冻结 | ✅已修 | database.py+kb.py+main.py |
| 5 前端确认框不完整 | ⏳Phase C待做 | kb.html+favorites.html |

## 逐项回退路径 (old→new可逆)

### Bug 0: rag_service.py
- L127: `def _init_chroma_with_retry` ← 回退为 `async def _init_chroma_with_retry`
- L158: `time.sleep(delay)` ← 回退为 `await asyncio.sleep(delay)`
- 单独回退: `git checkout b8b333b -- backend/rag_service.py`
- ⚠️ 回退后果: ChromaDB回到永不初始化状态(coroutine bug复活)

### Bug 1: database.py delete_kb_entry
- 新增块: "Clean ASR audio cache files" try/except (ChromaDB清理块后)
- 回退: 删除该try块(9行)
- 独立性: 失败仅warning，不影响其他删除层

### Bug 2+3: bilibili.py api_download_video
- old: `outdir = tempfile.mkdtemp()`
- new: `download_root = db.get_setting("download_dir") or {project}/downloads; outdir = download_root/{bvid}/`
- 回退: `git checkout b8b333b -- backend/routers/bilibili.py`
- 同时database.py delete_kb_entry新增"Clean downloaded video files"块(shutil.rmtree(download_dir/{bvid}))

### Bug 4: 三个文件
- database.py: 新增 refresh_kb_dir() 函数(L33-55左右) — 回退=删除函数
- kb.py settings POST: kb_dir变更时调用db.refresh_kb_dir() — 回退=删除4行if块
- kb.py L104: 死常量KB_DIR已移除(grep证实无使用) — 回退=恢复原行
- main.py L379: `kb_dir = db.KB_DIR` ← 回退为 `os.path.join(os.path.dirname(BASE_DIR), "knowledge_base")`

## 验证记录

- Phase A: ast.parse x3 + import main + vector_store type = Chroma (非coroutine) — Codex逐行确认3/3
- Phase B: ast.parse x3 + import main + refresh_kb_dir()运行成功 + classifier.KB_DIR synced True — 已发Codex待验证

## Phase C 待做

- C1: kb.html deleteKB/deleteSelectedKB + favorites.html deleteImportedVideo 确认框列出删除范围
  (参考bilibili-rag SourcesPanel.tsx:450-494 范围明示模式)
- C2可选: delete复用get_rag_service()单例(勿每次新建RAGService) + SQLite/Chroma自愈对账清历史幽灵向量
  (参考bilibili-rag knowledge.py:698-712)

## 参考源43模式索引

5-Agent扫描结果在workflow journal:
`C:\Users\shiniyaya\.claude\projects\D---claude\59f32053-c26f-4181-bc28-8729dd850a6d\subagents\workflows\wf_e10502fd-0eb\journal.jsonl`
关键: Bili23 safe_remove/ensure_directory_accessible/快照语义, bilibili-rag同步Chroma构造/引用计数删除/自愈校准, bili-note按bvid目录/copy_if_exists迁移

## 关联记忆
- [[bilisum-v8.5-session-state]]
- [[bilisum-v8.5-pending-issues]]
- [[all-active-rules]]
