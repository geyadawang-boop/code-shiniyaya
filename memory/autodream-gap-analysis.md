# autodream-src Deep Scan Findings -- code-shiniyaya Gap Analysis
# Date: 2026-07-16
# Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src
# Targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
# DIMENSION: Reflection cycle: Learn+Consolidate two-phase reflection, LLM-driven synthesis with structured JSON plans, dual-gate execution
# Key question: How can code-shiniyaya add post-workflow meta-reflection?

## Summary

code-shiniyaya v3.7.0 has a 7-step workflow (diagnose -> plan -> codex -> verify -> gate -> execute -> verify) that culminates in STEP 7 bidirectional verification. After STEP 7 completes, the session JSON is saved and the workflow ends. There is NO post-workflow phase that reflects on what was learned, synthesizes durable memories, or consolidates overlapping knowledge.

AutoDream provides an entire post-workflow reflection infrastructure. It hooks into the Agent Zero process chain (`process_chain_end` extension) and runs as a background task after every session. It operates in two phases: **Learn** (synthesize new memories from recent sessions) and **Consolidation** (periodically merge+prune overlapping memories). Every aspect of this architecture is missing from code-shiniyaya.

Below are ALL patterns autodream implements that code-shiniyaya does NOT have. Each entry follows the required format: (1) exact file:line, (2) gap it fills, (3) concrete fix, (4) priority.

---

## P0: Critical Gaps (post-workflow meta-reflection)

### P0-1: Two-Phase Reflection Cycle (Learn + Consolidate)

**Source**: `helpers/auto_dream.py:97-317` (_run_auto_dream), `helpers/auto_dream.py:264-271` (consolidation gate), `extensions/python/process_chain_end/_60_auto_dream.py:9-36` (hook trigger)

**Pattern**: After every session, a background task runs two phases:
- **Phase 1 (Learn)**: Feed recent sessions + existing memories + vector memories + orphan hints to an LLM. The LLM returns a structured JSON plan with `{summary, changes: [{action: "upsert"|"delete", path, title, description, content, grounding, source_context_ids, ...}]}`. The plan is applied atomically.
- **Phase 2 (Consolidation)**: Every N dreams (configurable via `consolidate_every_n_dreams`, default 3), run a second LLM pass that ONLY merges/consolidates overlapping files and forces deletion of redundant ones. Its prompt explicitly says "Be bold in your pruning. The goal is a lean, non-redundant memory index."

Each phase produces:
- `state.json` with `last_dream_at`, `last_status`, `last_summary`, `dreams_since_consolidation`, memory file count, vector counts
- `.dream-log.md` with a timestamped changelog (newest first, max 40 entries)
- Regenerated `MEMORY.md` index
- Updated vector DB entries (checksum-tracked)

The hook itself (`_60_auto_dream.py:11-36`):
```python
async def execute(self, **kwargs):
    if not self.agent: return
    if self.agent.number != 0: return           # only agent-0 triggers
    if self.agent.context.type == AgentContextType.BACKGROUND: return  # no recursive dreams
    config = plugins.get_plugin_config("AutoDream", self.agent) or {}
    if not config.get("enabled"): return
    persist_chat.save_tmp_chat(self.agent.context)
    schedule_auto_dream(context_id=..., project_name=..., agent_profile=..., memory_subdir=...)
```

**code-shiniyaya gap**: After STEP 7 completes, the workflow ends. Session JSON is saved. No post-hoc reflection occurs. What was learned across the diagnosis, plan, execution, and verification steps is NOT synthesized into durable knowledge. The next time a similar bug appears, the same diagnosis work is repeated from scratch. There is no mechanism to:
- Extract reusable patterns from a completed diagnosis+fix cycle
- Merge overlapping findings across multiple workflow runs
- Prune stale or superseded knowledge
- Generate a summary of what was learned for future reference

**Fix -- Add to SKILL.md** (new section after STEP 7):

```markdown
## STEP 8 -- 工作流后元反思 (v3.8.0)

STEP 7完成后, code-shiniyaya自动运行一次反思, 将本工作流的发现合成为持久知识。

### 触发条件 (双门控)
- 门控A: 距上次反思 ≥ `min_hours` 小时 (默认 8 小时)
- 门控B: 累计完成 ≥ `min_workflows` 个工作流 (默认 3 个)
- 逻辑: A OR B (= 任一满足即触发)。若 `last_reflection_at` 为 None (首次) → 立即触发。
- 若 `min_hours=0` → 仅按工作流计数门控。若 `min_workflows=0` → 仅按时间门控。
- 若工作流异常中断(STEP 6有FAILED_FIXES.md / ABORT触发): 不计入 `min_workflows` 计数; 但仍产生部分反思(仅提取已成功修复的bug的模式)。

### 双阶段结构

#### Phase 1: Learn — 从本工作流提取新记忆

**输入** (注入LLM提示词):
1. 本工作流摘要: STEP 1诊断的bug列表(含根因), STEP 2方案, STEP 4 Codex验证的发现, STEP 6执行结果(成功/失败/阻断), STEP 7验证结果
2. workflow_context_bus 快照(含 diagnosis, plan, codex, execution, meta)
3. 现有持久记忆文件 (最多24个, 每个最多2500字符, 头部60%+尾部40%智能截断)
4. 现有MEMORY.md索引 (最多6000字符)
5. 工作流日志 (workflow-{sessionId}.jsonl, 最多40条事件)

**LLM输出** (结构化JSON, 通过 `DirtyJson.parse_string` 解析):
```json
{
  "summary": "本工作流修复了2个P0空指针bug和1个P1竞态条件。关键模式: src/core.py的初始化顺序问题在3个工作流中重复出现。建议将初始化顺序检查加入pre-commit hook。",
  "changes": [
    {
      "action": "upsert",
      "path": "null-pointer-init-order.md",
      "title": "空指针根因: 初始化顺序问题",
      "description": "src/core.py中字段初始化顺序导致的空指针模式",
      "content": "## 模式\n当src/core.py中的Handler类构造函数在super().__init__()之前初始化logger字段时, 父类构造函数中的setup()回调会触发未初始化的logger空指针。\n\n## 根因\nPython MRO导致父类__init__中调用的方法在子类字段初始化前执行。\n\n## 修复模式\n1. 所有字段初始化移到super().__init__()之后\n2. 在setup()回调中使用hasattr()防御性检查\n\n## 检测方法\ngrep -n 'self\.[a-z_]* = ' src/core.py | sort 然后手动检查是否在super().__init__()之前。\n\n## 来源工作流\n- wf-a1b2c3d4: 2026-07-15, 修复了3处此类问题",
      "grounding": "grounded",
      "source_context_ids": ["a1b2c3d4"],
      "source_first_prompts": ["修复 src/core.py 的空指针异常"],
      "source_memory_ids": ["mem-1"]
    },
    {
      "action": "delete",
      "path": "stale-init-guide.md",
      "reason": "被null-pointer-init-order.md完全覆盖(更具体的模式+可执行检测方法)"
    }
  ]
}
```

**应用规则**:
- `action: "upsert"` + path不存在 → 创建新文件, 写入frontmatter YAML + body markdown
- `action: "upsert"` + path已存在 → 对比内容: 相同则跳过(checksum匹配), 不同则更新
- `action: "delete"` + path存在 → 删除文件, 记录到dream-log
- `action: "delete"` + path不存在 → 忽略(幂等)
- 所有变更完成后: 重新生成MEMORY.md索引

**Memory 文件格式**:
```markdown
---
title: 空指针根因: 初始化顺序问题
description: src/core.py中字段初始化顺序导致的空指针模式
updated_at: 2026-07-16T14:30:00+00:00
memory_scope: code-shiniyaya
grounding: grounded
source_context_ids: ["a1b2c3d4"]
source_first_prompts: ["修复 src/core.py 的空指针异常"]
---

## 模式
...
```

**Frontmatter字段**:
- `title` (必填): 记忆标题
- `description` (必填): 一行描述, 用于MEMORY.md索引
- `updated_at` (自动): ISO 8601 UTC时间戳
- `memory_scope` (自动): 记忆所属范围
- `grounding`: `grounded` (直接来自工作流证据) 或 `inferred` (LLM推断)
- `source_context_ids`: 来源工作流的sessionId列表 (最多8个)
- `source_first_prompts`: 来源工作流的用户首条提示词摘要 (最多8个)
- `source_memory_ids`: 来源记忆ID列表 (最多12个)

#### Phase 2: Consolidate — 周期性合并去重

**触发**: 每 `consolidate_every_n_workflows` 个Learn-only工作流后 (默认3, 可配置0=禁用)

**输入**: 所有现有记忆文件(空出Learn phase的session数据, 只给文件列表)

**LLM系统提示词** (autodream.consolidate.sys.md):
```
# AutoDream Consolidation Role
Your only job is to read pairs or groups of semantically overlapping memory files
and merge them into a single comprehensive file, forcing the deletion of the redundant files.

## Core Rules
- If two or more files cover the same concepts, create a single unified file (upsert).
- You MUST explicitly delete the old, redundant files (action: "delete").
- Be bold in your pruning. The goal is a lean, non-redundant memory index.
- Do not invent new knowledge; only merge and prune what is already there.
```

**输出**: 标准AutoDream计划JSON, `changes` 数组包含 upsert(合并后文件) 和 delete(冗余文件)。

**Consolidation前后对比示例**:
```
前: architecture-decisions.md + arch-decisions-v2.md + architecture-notes.md (3个文件, 相互重叠)
后: architecture-decisions.md (合并后, 包含3个文件的所有非冗余内容) + 删除另外2个
```

### 防并发守卫

使用 `_REFLECTION_RUNNING` set + 线程锁防止同一记忆范围的多次反思并发执行:

```python
_RUNNING_SCOPES: set[str] = set()
_RUNNING_LOCK = threading.Lock()

def schedule_post_workflow_reflection(session_id: str, memory_scope: str) -> bool:
    with _RUNNING_LOCK:
        if memory_scope in _RUNNING_SCOPES:
            return False  # 已有反思运行中
        _RUNNING_SCOPES.add(memory_scope)
    
    task = DeferredTask(thread_name="background")
    task.start_task(_run_reflection, session_id=session_id, memory_scope=memory_scope)
    return True
```

### 反思日志

每次反思产生一条变更记录, 写入 `.reflection-log.md` (最新在前, 最多40条):

```markdown
# Reflection Log
Newest runs first.

## 2026-07-16 14:30 UTC
- Summary: AutoDream created 2 durable memory files, updated 1, pruned 1. | Consolidation: Merged 3 architecture files into 1.
- Scope: code-shiniyaya
- Phase: Learn + Consolidation
- Inputs: 1 workflow, 0 recent vector memories, 0 related vector memories
- Created: null-pointer-init-order.md, concurrency-safety-checklist.md
- Updated: architecture-decisions.md
- Pruned: stale-init-guide.md
```

### 状态追踪

`reflection-state.json`:
```json
{
  "schema_version": 1,
  "last_reflection_at": "2026-07-16T14:30:00+00:00",
  "last_status": "updated",
  "last_summary": "AutoDream created 2, updated 1, pruned 1",
  "last_workflow_count": 1,
  "memory_file_count": 12,
  "workflows_since_consolidation": 1,
  "last_created_files": ["null-pointer-init-order.md", "concurrency-safety-checklist.md"],
  "last_updated_files": ["architecture-decisions.md"],
  "last_deleted_files": ["stale-init-guide.md"],
  "last_log_path": ".reflection-log.md"
}
```

### 与现有STEP 7的衔接

STEP 7 (双向验证) 完成后:
1. CC写入最终session JSON (含workflow_context_bus完整快照)
2. CC调用 `schedule_post_workflow_reflection(session_id, memory_scope="code-shiniyaya")`
3. 反思在后台线程执行, 不阻塞用户交互
4. 反思结果通过CCD session log通知用户: "AutoDream updated durable memory: created 2, updated 1, pruned 1"
5. 用户可通过读取 `.reflection-log.md` 查看反思历史

### 降级与中断

- 反思LLM调用失败(API error): 静默失败, 不通知用户。下次工作流完成时重试。
- 反思被用户中断: 已写入的memory文件保留(原子写入), 未写入的变更丢失。下次工作流完成时重新生成。
- 磁盘满: 跳过反思, 写入 `reflection-errors.log`, 不阻断工作流完成。
- 所有反思失败均为非阻塞: 即使反思完全失败, STEP 1-7的结果完整保存, 不影响当前工作流。
```

**Where to add**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` -- new section "STEP 8 -- 工作流后元反思" after STEP 7 (after line 299).

---

### P0-2: Dual-Gate Execution Trigger (Time OR Session Count)

**Source**: `helpers/auto_dream.py:686-702` (should_run_auto_dream), `helpers/auto_dream.py:666-683` (coerce_min_hours, coerce_min_sessions), `default_config.yaml:1-6` (configuration)

**Pattern**: The decision to run is gated by TWO independent conditions combined with OR logic:

```python
def should_run_auto_dream(last_dream_at, recent_session_count, min_hours, min_sessions):
    if recent_session_count <= 0:
        return False                           # 无新会话 = 不运行
    if last_dream_at is None:
        return True                            # 首次运行 = 总是触发
    hours_since = (datetime.now(timezone.utc) - last_dream_at).total_seconds() / 3600
    if min_sessions > 0 and recent_session_count >= min_sessions:
        return True                            # 门控A: 累积足够会话数
    if min_hours > 0 and hours_since >= min_hours:
        return True                            # 门控B: 距上次足够时间
    return False
```

Configuration (`default_config.yaml`):
```yaml
enabled: true
min_hours: 2      # float; 0 = 仅用session计数门控
min_sessions: 2   # int; 0 = 仅用时间门控
line_limit: 120
consolidate_every_n_dreams: 2
```

Each parameter has a coercion function with defaults (coerce_min_hours=8.0, coerce_min_sessions=3, coerce_consolidate_every=3) when the config value is None.

**code-shiniyaya gap**: code-shiniyaya has no post-workflow trigger logic whatsoever. If STEP 8 (post-workflow meta-reflection) were added, there would need to be a decision mechanism for when to run it: every workflow? Only after N workflows? Only after H hours? Without this, reflection either runs on every workflow (wasteful for quick successive workflows) or never runs.

**Fix -- Add to SKILL.md** (inside the STEP 8 section above, as the "触发条件" subsection):

```markdown
### 触发条件实现

```python
def should_run_reflection(last_reflection_at, recent_workflow_count, min_hours, min_workflows):
    if recent_workflow_count <= 0:
        return False
    if last_reflection_at is None:
        return True  # 首次总是运行
    hours_since = (now_utc() - last_reflection_at).total_seconds() / 3600
    if min_workflows > 0 and recent_workflow_count >= min_workflows:
        return True
    if min_hours > 0 and hours_since >= min_hours:
        return True
    return False
```

配置参数:
- `reflection_min_hours` (float, 默认 8.0): 距上次反思的最短时间, 0=仅按工作流计数
- `reflection_min_workflows` (int, 默认 3): 触发反思的最少工作流数, 0=仅按时间
- `reflection_consolidate_every_n_workflows` (int, 默认 3): 多少轮Learn后触发一次Consolidation, 0=禁用

恢复逻辑: 每次STEP 7完成后, CC从 `reflection-state.json` 读取 `workflows_since_last_reflection`, 递增, 调用 `should_run_reflection()`。
```

**Where to add**: Inside "STEP 8" section.

---

### P0-3: Checksum-Based Change Detection for Memory Files

**Source**: `helpers/auto_dream.py:533-538` (vector sync), `helpers/auto_dream.py:459-465` (upsert change detection)

**Pattern**: Every memory file and vector document is tracked by checksum. Before processing, the system checks if the content actually changed:

```python
# auto_dream.py:535-538 -- vector sync checksum skip
text = file_path.read_text(encoding="utf-8")
checksum = hashlib.md5(text.encode("utf-8")).hexdigest()
tracked = file_map.get(file_name, {})
if tracked.get("checksum") == checksum and tracked_ids:
    continue  # 未变更, 跳过

# auto_dream.py:459-465 -- upsert identity check
previous = file_path.read_text(encoding="utf-8") if file_path.exists() else None
file_path.write_text(rendered, encoding="utf-8")
if previous is None:
    created_files.append(file_name)
elif previous != rendered:
    updated_files.append(file_name)
```

**code-shiniyaya gap**: code-shiniyaya's session JSON has a `checksum` field for integrity verification (SHA-256 of sorted JSON). But individual items being tracked (memory files, pending items, DAG edges) do not have content-based change detection. The `lastFileHash` field in pending items exists but is only checked at recovery time, not during normal operation. Without checksums, every reflection run would rewrite all memory files even if nothing changed -- wasteful and loses the "noop" fast path.

**Fix -- Add to SKILL.md** (inside STEP 8):

```markdown
### Checksum检测

Memory文件写入前:
1. 计算新内容 SHA-256
2. 读现有文件(若存在) → 计算 SHA-256
3. 若相同 → 跳过, 不记为updated
4. 若不同/不存在 → 写入, 标记为 created/updated

反思完成后:
- 若 `created_files` + `updated_files` + `deleted_files` 全部为空 → status = "noop", 不写入dream-log(避免日志膨胀)
- 若有变更 → status = "updated", 写入dream-log + 更新MEMORY.md索引
```

**Where to add**: Inside "STEP 8" section.

---

### P0-4: Auto-Index Regeneration (MEMORY.md from Frontmatter)

**Source**: `helpers/auto_dream.py:921-944` (render_memory_index), `helpers/auto_dream.py:467-471` (write after plan apply)

**Pattern**: After every dream, the index file is regenerated from scratch by reading all memory file frontmatter:

```python
def render_memory_index(memory_files, line_limit):
    lines = ["# Memory Index", ""]
    if not memory_files:
        lines.append("No durable memories indexed yet.")
        return "\n".join(lines) + "\n"
    max_entries = max(1, line_limit - 3)
    visible_entries = memory_files[:max_entries]
    hidden_entries = len(memory_files) - len(visible_entries)
    for item in visible_entries:
        title = collapse_single_line(item.title)
        description = collapse_single_line(item.description) or "Durable memory"
        lines.append(f"- [{title}](memories/{item.file_name}): {description}")
    if hidden_entries > 0:
        lines.append(f"- Additional memories hidden to respect the line limit: {hidden_entries}")
    return "\n".join(lines) + "\n"

# Called after plan application:
memory_files = load_existing_memory_files(memory_subdir)
memory_index = render_memory_index(memory_files, line_limit=line_limit)
Path(get_autodream_index_path(memory_subdir)).write_text(memory_index, encoding="utf-8")
```

The index is sorted by `updated_at DESC, title ASC`. Files beyond `line_limit` are hidden with a count note.

**code-shiniyaya gap**: code-shiniyaya's `memory/MEMORY.md` is manually maintained. When new memory files are added (e.g., gap analyses, pattern files), someone must manually edit MEMORY.md to add a link entry. This is fragile -- new files easily get orphaned (present on disk but not linked from the index). AutoDream's pattern guarantees index-file consistency: the index is always a correct function of the files on disk.

**Fix -- Add to SKILL.md**:

```markdown
### MEMORY.md自动生成

每次反思完成后, 自动重建 `memory/MEMORY.md`:

算法:
```
files = glob("memory/*.md") - exclude("MEMORY.md", "cleanup-*.md")
sorted_files = sort(files, key=(updated_at DESC, title ASC))
index = "# code-shiniyaya Memory Index\n\n"
for f in sorted_files[:line_limit]:
    meta = parse_frontmatter(f)
    index += f"- [{meta.title}](memory/{f.name}): {meta.description}\n"
if len(sorted_files) > line_limit:
    index += f"- Additional memories hidden: {len(sorted_files) - line_limit}\n"
write("memory/MEMORY.md", index)
```

手动添加的记忆条目(在MEMORY.md中的孤立链接)会在下次自动重建时丢失。因此所有记忆文件的元数据必须在frontmatter中维护, 而非在MEMORY.md中手写。

此模式等同于autodream的 `render_memory_index()` (auto_dream.py:921-944)。
```

**Where to add**: Inside "STEP 8" section or as a standalone note in the "记忆" section.

---

## P1: Important Gaps

### P1-1: .promptinclude.md Taxonomy (Rules vs. Facts)

**Source**: `prompts/autodream.sys.md:47-50`, `helpers/auto_dream.py:1306-1309` (ensure_unique_memory_filename handles `.promptinclude.md` suffix)

**Pattern**: Memory files have a two-tier taxonomy based on file extension:
- `.md` -- Facts, architecture, context, decisions, history. Informational. Not enforced.
- `.promptinclude.md` -- Rules, constraints, behavioral guidelines, formatting mandates. **Automatically enforced** by the system -- these files are injected into every future agent's prompt.

```markdown
# autodream.sys.md:47-50
- **Taxonomy (Rules vs. Facts)**: Differentiate between behavioral guidelines and general knowledge.
  - If a memory contains strict instructions, behavioral rules, constraints, or formatting 
    mandates for the AI, save it as a `.promptinclude.md` file. The system automatically enforces these.
  - If a memory contains facts, context, architectural decisions, or history, save it as a 
    standard `.md` file.
```

**code-shiniyaya gap**: All memory files are plain `.md` with no behavioral vs. factual distinction. When the SKILL.md specifies hard rules (e.g., "双批准门控"), these are exclusively in SKILL.md itself. Memories about patterns discovered across workflows have no mechanism to enforce themselves on future agent runs. For example, if STEP 8 reflection discovers that "Explore agent hangs >10% of the time on cross-file references," this should become a behavioral constraint (never use Explore for xref) that gets injected into agent prompts. Currently, anti-hang-v2.md contains this rule but has no auto-enforcement.

**Fix -- Add to SKILL.md**:

```markdown
### Memory 文件分类 (v3.8.0)

| 扩展名 | 用途 | 注入行为 |
|--------|------|---------|
| `.md` | 事实/架构/上下文/决策/历史 | 仅在相关时供Agent参考(语义检索触发) |
| `.promptinclude.md` | 规则/约束/行为指南/格式要求 | **每次Agent调用时自动追加到系统提示词末尾** |

**分类规则** (Agent创建memory时):
- 包含强制性行为规则 → 必须用 `.promptinclude.md`
- 包含事实/上下文 → 用 `.md`
- 不确定 → 默认 `.md`, LLM可在后续Consolidation中将事实升级为规则(改变扩展名)

**注入规则**:
- 所有 `.promptinclude.md` 文件在Agent启动时串接为一个 `[ENFORCED_RULES]` 块追加到系统提示词
- 注入顺序: 按 `title` 字母序排序, 保证确定性
- 最大注入长度: 4000字符 (超出部分截断, 警告日志)
- `.md` 文件不自动注入 -- 仅通过语义检索(如有向量DB)或显式引用访问

**示例**:
- `anti-hang-v2.promptinclude.md`: "禁止对跨文件引用使用Explore Agent(挂起率>10%)"
- `null-pointer-init-order.md`: "src/core.py初始化顺序模式" (事实, 不强制)
```

**Where to add**: Inside "STEP 8" section and update the "记忆" section.

---

### P1-2: Dream Log with Rotation

**Source**: `helpers/auto_dream.py:994-1018` (append_auto_dream_log), `helpers/auto_dream.py:1021-1071` (render_auto_dream_log_entry), `helpers/auto_dream.py:1074-1096` (parse_auto_dream_log_entries)

**Pattern**: Each dream run appends a structured entry to `.dream-log.md`. The log has a max entry count (40); old entries are rotated out. Each entry contains: timestamp, summary, scope, phase, input counts, created/updated/deleted file lists, orphan hints.

```python
def append_auto_dream_log(memory_subdir, summary, created_files, updated_files, deleted_files, run_metadata):
    entry = render_auto_dream_log_entry(summary, created_files, updated_files, deleted_files, run_metadata)
    existing_entries = parse_auto_dream_log_entries(path.read_text() if path.exists() else "")
    merged_entries = [entry, *existing_entries][:AUTO_DREAM_LOG_MAX_ENTRIES]  # 40 max
    path.write_text(header + "\n\n".join(merged_entries).rstrip() + "\n")
```

The log format:
```
## 2026-07-16 14:30 UTC
- Summary: AutoDream created 2 durable memory files, updated 1, pruned 1
- Scope: code-shiniyaya (code-shiniyaya)
- Phase: Learn
- Inputs: 3 sessions, 5 recent vector memories, 2 related vector memories
- Created: null-pointer-init-order.md, concurrency-safety-checklist.md
- Updated: architecture-decisions.md
- Pruned: stale-init-guide.md
- Rename / orphan hints: bilisum (7 files)
```

**code-shiniyaya gap**: No changelog of memory evolution. When memory files change, there's no record of who changed what, when, or why. Debugging "why does this memory say X when it used to say Y" is impossible without git history (and memory files may not be in git).

**Fix -- Add to SKILL.md**:

```markdown
### Reflection Log (.reflection-log.md)

路径: `memory/.reflection-log.md`

每次反思后追加一条记录(最新在前, 最多40条):

```markdown
# Reflection Log
Newest runs first.

## 2026-07-16 14:30 UTC
- Summary: 从1个工作流提取2条新记忆, 合并3条架构记忆为1条。
- Scope: code-shiniyaya
- Phase: Learn + Consolidation
- Inputs: 1 workflow, 0 recent vector memories, 0 related vector memories
- Created: null-pointer-init-order.md, concurrency-safety-checklist.md
- Updated: architecture-decisions.md
- Pruned: stale-init-guide.md, arch-notes-v2.md
```

条目格式:
- `## YYYY-MM-DD HH:MM UTC` -- 反思时间戳
- `Summary` -- 一句话摘要(取自LLM输出的 `summary` 字段)
- `Scope` -- 记忆范围
- `Phase` -- Learn / Consolidation / Learn+Consolidation
- `Inputs` -- 输入数据计数
- `Created` / `Updated` / `Pruned` -- 文件变更列表
- `Rename / orphan hints` -- 可能的重复项目记忆文件夹

条目解析: 按 `## ` 分隔符解析(同autodream的parse逻辑), 头40条保留。
```

**Where to add**: Inside "STEP 8" section.

---

### P1-3: Orphan Candidate Detection (Cross-Project Dedup)

**Source**: `helpers/auto_dream.py:846-918` (find_orphan_candidates)

**Pattern**: When a project is renamed or split, the old project's memory folder becomes an "orphan." AutoDream detects this by comparing token overlaps between sibling project names:

```python
def find_orphan_candidates(memory_subdir):
    current_project_name = memory_subdir[9:]  # strip "projects/"
    current_tokens = slug_tokens(current_project_name)  # split into lowercase alphanumeric tokens

    for sibling_project_dir in projects_root.iterdir():
        sibling_project_name = sibling_project_dir.name
        sibling_tokens = slug_tokens(sibling_project_name)
        overlap = len(current_tokens & sibling_tokens) / max(len(current_tokens), len(sibling_tokens))
        if overlap < MIN_ORPHAN_OVERLAP:  # 0.5
            continue
        # Found potential orphan: names share >= 50% token overlap
        candidates.append({"memory_subdir": sibling, "overlap_score": overlap, "shared_tokens": [...], ...})

    return candidates[:MAX_ORPHAN_CANDIDATES]  # 4
```

**code-shiniyaya gap**: code-shiniyaya has one memory scope (`code-shiniyaya/memory/`). There's no concept of cross-project memory dedup. However, the pattern is directly applicable: if code-shiniyaya's memory files accidentally overlap with bilisum's memory files (both in the user's desktop ecosystem), there should be detection and hints. More broadly, the token-overlap algorithm is a general technique for detecting near-duplicate directories.

**Fix -- Add to SKILL.md** (inside STEP 8, Consolidation phase):

```markdown
### 孤立候选检测 (Consolidation阶段)

在Consolidation阶段, 检测可能重复的记忆文件:

算法:
```
1. 对每对记忆文件 (f1, f2):
   a. 提取标题token: re.findall(r"[a-z0-9]+", title.lower()), 过滤长度≤1的token
   b. overlap = len(tokens1 & tokens2) / max(len(tokens1), len(tokens2))
   c. if overlap >= 0.5: 标记为潜在重复对
2. 按overlap降序排列, 取前4个候选
3. 在Consolidation LLM提示词中呈现这些候选对: "以下记忆文件标题高度重叠, 请检查是否需要合并: ..."
```

跨项目检测 (扩展):
```
当前项目: code-shiniyaya
检测范围: C:\Users\shiniyaya\Desktop\ 下的所有子目录
检测方法: 对每个子目录, 检查是否有同名memory/目录, 计算token重叠
若重叠≥50%: 提示用户 "发现可能的重复记忆目录: bilisum/memory/ 与 code-shiniyaya/memory/ 共享{overlap*100}%的token, 是否需要交叉引用?"
```

注意: 跨项目检测是软提示(hints), 不自动操作。需要用户确认后才进行跨项目合并。
```

**Where to add**: Inside "STEP 8" section.

---

### P1-4: Session Transcript Summarization via Utility Model

**Source**: `helpers/auto_dream.py:142-149`

**Pattern**: Before feeding session transcripts to the dream LLM, long transcripts are summarized by a smaller/cheaper utility model:

```python
system_sum = agent.read_prompt("fw.topic_summary.sys.md")
for session in recent_sessions:
    if len(session.transcript) > MAX_SESSION_CHARS:  # 4000 chars
        msg_sum = agent.read_prompt("fw.topic_summary.msg.md", content=session.transcript)
        summary = await agent.call_utility_model(system=system_sum, message=msg_sum)
        if summary:
            session.transcript = summary.strip()
```

The utility model produces a condensed version that captures the key topics and decisions without the full conversation detail. Each session is then capped at `MAX_SESSION_CHARS` (4000).

**code-shiniyaya gap**: STEP 8 reflection would need to feed the full workflow transcript to the reflection LLM. But a 7-step workflow can involve 10+ agents, each producing hundreds of lines of output. The full transcript could be 50K+ characters. Without summarization, the reflection LLM would receive truncated input (via head-tail truncation, see P2-1) and miss important context.

**Fix -- Add to SKILL.md** (inside STEP 8):

```markdown
### 工作流摘要压缩

反思前, 对每个工作流的完整记录进行摘要压缩:

```
for workflow in recent_workflows:
    if len(workflow.full_transcript) > 4000:
        summary_prompt = "请将以下工作流记录压缩为关键事件摘要(保留bug、修复、决策、失败原因):\n\n{transcript}"
        summary = call_utility_model(summary_prompt)
        workflow.transcript = summary[:4000]  # 保留前4000字符
```

摘要格式(用于反思LLM):
```
[工作流 a1b2c3d4] 2026-07-15
用户请求: 修复 src/core.py:42 空指针异常
诊断: investigator发现3处初始化顺序问题(P0), Plan发现1处架构异味(P1)
方案: Phase A修复3处初始化顺序(移至super().__init__()之后)
Codex: 批准Phase A, 要求对架构异味做进一步分析
执行: 3处修复成功, 架构异味标记为P2待后续处理
验证: CC 6 Agent验证通过, 回归测试无退化
```

最多保留8个工作流, 每个压缩后≤4000字符。
```

**Where to add**: Inside "STEP 8" section.

---

### P1-5: `dreams_since_consolidation` Counter with State Persistence

**Source**: `helpers/auto_dream.py:266-271`, `helpers/auto_dream.py:345`

**Pattern**: A persistent counter tracks how many Learn-only dream runs have occurred since the last Consolidation run. When it reaches the threshold (`consolidate_every_n_dreams`), Consolidation triggers and the counter resets to 0. The counter survives restarts (stored in `state.json`):

```python
# auto_dream.py:266-267
dreams_since_consolidation = int(state.get("dreams_since_consolidation", 0)) + 1
consolidate_every = coerce_consolidate_every(config.get("consolidate_every_n_dreams"))

# auto_dream.py:270-271
if consolidate_every > 0 and dreams_since_consolidation >= consolidate_every:
    dreams_since_consolidation = 0  # reset
    # ... run consolidation ...

# auto_dream.py:345 -- saved to state.json
"dreams_since_consolidation": dreams_since_consolidation,
```

**code-shiniyaya gap**: Without this counter, there's no way to know whether the current reflection should include Consolidation. The counter must be persisted across sessions (in `reflection-state.json`).

**Fix -- Add to SKILL.md** (inside STEP 8):

```markdown
### consolidation计数器

`reflection-state.json` 中的 `workflows_since_consolidation` 字段:
- 每次Learn-only反思后递增1
- 达到 `reflection_consolidate_every_n_workflows` 阈值时触发Consolidation并重置为0
- 若Consolidation返回空changes(无需合并): 仍然重置计数器(防止每次都触发无效Consolidation)
- 若 `reflection_consolidate_every_n_workflows = 0`: 永不触发Consolidation, 计数器不递增
```

**Where to add**: Inside "STEP 8" section.

---

## P2: Nice-to-Have Improvements

### P2-1: Smart Head-Tail Truncation (not simple cutoff)

**Source**: `helpers/auto_dream.py:1246-1252` (truncate_for_prompt)

**Pattern**: Instead of simply cutting at `max_chars`, the truncation preserves 60% from the head and 40% from the tail, with a separator line:

```python
def truncate_for_prompt(text, max_chars):
    text = str(text or "").strip()
    if len(text) <= max_chars:
        return text
    head = int(max_chars * 0.6)
    tail = max_chars - head - 9  # 9 = len("\n...\n")
    return text[:head].rstrip() + "\n...\n" + text[-tail:].lstrip()
```

**code-shiniyaya gap**: code-shiniyaya has no explicit truncation strategy. When content exceeds limits, the behavior is undefined. This pattern ensures that both the beginning (context/background) AND the end (conclusions/findings) of a document are preserved, which is almost always more useful than just the first N chars.

**Fix -- Add to SKILL.md** (generic utility pattern):

```markdown
### 智能截断 (head-tail)

当内容超过限制时, 使用60%头部+40%尾部策略:

```
truncate_for_prompt(text, max_chars):
    if len(text) <= max_chars: return text
    head_chars = int(max_chars * 0.6)
    tail_chars = max_chars - head_chars - len("\n...\n")
    return text[:head_chars].rstrip() + "\n...\n" + text[-tail_chars:].lstrip()
```

适用场景:
- 记忆文件内容超过 `MAX_EXISTING_MEMORY_CHARS` (2500)时
- 工作流记录超过 `MAX_SESSION_CHARS` (4000)时
- MEMORY.md索引超过 `MAX_INDEX_PROMPT_CHARS` (6000)时
- Agent输出超过token限制时

优于简单截断: 保留开头(上下文)和结尾(结论), 牺牲中间的冗余细节。
```

**Where to add**: Generic utility section in SKILL.md or anti-hang-v2.md.

---

### P2-2: Concurrency Guard with Set[scope] + Thread Lock

**Source**: `helpers/auto_dream.py:49-51, 79-93` (schedule_auto_dream)

**Pattern**: A `_RUNNING_SUBDIRS: set[str]` guarded by `threading.Lock()` prevents multiple concurrent dream runs for the same memory scope:

```python
_RUNNING_SUBDIRS: set[str] = set()
_RUNNING_LOCK = threading.Lock()

def schedule_auto_dream(context_id, project_name, agent_profile, memory_subdir):
    with _RUNNING_LOCK:
        if memory_subdir in _RUNNING_SUBDIRS:
            return False         # 已有反思在此范围运行
        _RUNNING_SUBDIRS.add(memory_subdir)
    # ... launch task ...
    # finally block: _RUNNING_SUBDIRS.discard(memory_subdir)
```

**code-shiniyaya gap**: If two CC sessions complete at roughly the same time, both could trigger post-workflow reflection simultaneously. Without a concurrency guard, both would write to the same memory files, causing corruption. This is the same class of problem as Scenario 2 (3 concurrent CC sessions -> file corruption) that was already analyzed in session JSON design.

**Fix -- Add to SKILL.md** (inside STEP 8):

```markdown
### 并发防护

反思写入通过以下机制防止并发文件损坏:

1. `_REFLECTION_LOCK`: 进程级互斥锁, 确保单次反思原子执行
2. `_REFLECTION_SCOPES`: set[str], 追踪正在运行反思的记忆范围
3. 若同范围的反思已在运行 → 新请求排队(最多1个排队槽位), 不重复运行
4. 反思任务使用独立线程, 不阻塞CC主会话
5. 内存文件写入使用 `os.replace(tmp, target)` 原子写入协议(同session JSON)
```

**Where to add**: Inside "STEP 8" section.

---

### P2-3: Single-Line Collapse for Frontmatter Safety

**Source**: `helpers/auto_dream.py:1379-1384` (collapse_single_line, collapse_whitespace)

**Pattern**: Before writing any value into YAML frontmatter, it's collapsed to a single line:

```python
def collapse_single_line(value):
    return collapse_whitespace(value).replace("\n", " ")

def collapse_whitespace(value):
    return " ".join(str(value or "").split())
```

This prevents multi-line values from breaking YAML frontmatter parsing (YAML frontmatter must be single-line for string scalars unless using block scalars).

**code-shiniyaya gap**: If STEP 8 memory file frontmatter includes `source_first_prompts` (the user's original bug report, which may contain newlines), the YAML parser would break. This pattern is a defensive measure.

**Fix -- Add to SKILL.md** (memory file format):

```markdown
### Frontmatter安全规则

所有写入YAML frontmatter的字符串值必须先 `collapse_single_line()`:
- 将所有连续空白字符压缩为单个空格
- 将换行符替换为空格
- 去除首尾空白

受影响字段: title, description, grounding, canonical_scope_name, project_title
列表字段(source_context_ids, source_first_prompts, source_memory_ids): 每个数组元素单独collapse
```

---

### P2-4: Utility Model for Background Tasks (Non-blocking LLM Calls)

**Source**: `helpers/auto_dream.py:140-149, 241-245`

**Pattern**: All dream LLM calls use `agent.call_utility_model()` with `background=True`. This uses a smaller/cheaper model for background tasks. The utility model is separate from the main agent's model, ensuring that reflection doesn't consume the user's primary model quota or context window.

```python
response = await agent.call_utility_model(
    system=system,
    message=message,
    background=True,
)
```

**code-shiniyaya gap**: If STEP 8 reflection uses the same model as the main workflow, it could consume significant token budget. A separate utility model (or at minimum, a flag indicating "this is a background, non-interactive task -- use the cheapest available model") would reduce costs.

**Fix -- Add to SKILL.md**:

```markdown
### 反思模型选择

反思LLM调用使用独立模型配置(非主工作流模型):
- 优先: 便宜模型 (如 gpt-4o-mini, claude-haiku)
- 回退: 主工作流模型
- 背景模式: 不阻塞用户交互
- Token预算: 每次反思最多 16000 input tokens + 4000 output tokens
```

---

### P2-5: DEFAULT_LOG Auto-Initialization on First Import

**Source**: `autoagent/logger.py:166-172` (from the logger pattern referenced in autoagent-src)

**Pattern**: The logger auto-initializes on module import if `DEFAULT_LOG` is True:

```python
if DEFAULT_LOG:
    log_dir = Path(f'logs/res_{datetime.now().strftime("%Y%m%d_%H%M%S")}')
    log_dir.mkdir(parents=True, exist_ok=True)
    LoggerManager.set_logger(MetaChainLogger(log_path=str(log_dir / "agent.log")))
```

**code-shiniyaya gap**: STEP 8 reflection log (`.reflection-log.md`) needs to be created on first use. The auto-initialization pattern ensures the directory and file exist before any write attempt.

**Fix**: The reflection state initialization should be part of the STEP 8 "first run" path: if `reflection-state.json` doesn't exist, create it with default values and run reflection immediately (the `last_reflection_at is None -> True` path from the dual-gate trigger).

---

## Summary: All Patterns by Priority

| # | Priority | Pattern | Source file:line | Fix target |
|---|----------|---------|-----------------|------------|
| 1 | P0 | Two-phase reflection (Learn + Consolidate) | auto_dream.py:97-317 | SKILL.md: new STEP 8 |
| 2 | P0 | Dual-gate execution trigger (time OR sessions) | auto_dream.py:686-702 | SKILL.md: STEP 8 trigger |
| 3 | P0 | Checksum-based change detection | auto_dream.py:533-538, 459-465 | SKILL.md: STEP 8 checksum |
| 4 | P0 | Auto-index regeneration from frontmatter | auto_dream.py:921-944 | SKILL.md: STEP 8 MEMORY.md |
| 5 | P1 | .promptinclude.md taxonomy (rules vs. facts) | autodream.sys.md:47-50 | SKILL.md: memory taxonomy |
| 6 | P1 | Dream log with rotation (max 40 entries) | auto_dream.py:994-1018 | SKILL.md: .reflection-log.md |
| 7 | P1 | Orphan candidate detection (token overlap) | auto_dream.py:846-918 | SKILL.md: STEP 8 consolidate |
| 8 | P1 | Session transcript summarization | auto_dream.py:142-149 | SKILL.md: workflow compression |
| 9 | P1 | dreams_since_consolidation counter | auto_dream.py:266-271, 345 | SKILL.md: consolidation counter |
| 10 | P2 | Smart head-tail truncation (60%/40%) | auto_dream.py:1246-1252 | SKILL.md: utility pattern |
| 11 | P2 | Concurrency guard (set + lock) | auto_dream.py:49-51, 79-93 | SKILL.md: STEP 8 concurrency |
| 12 | P2 | Single-line collapse for frontmatter | auto_dream.py:1379-1384 | SKILL.md: frontmatter rules |
| 13 | P2 | Utility model for background tasks | auto_dream.py:241-245 | SKILL.md: reflection model |
| 14 | P2 | Auto-initialization on first import | logger.py:166-172 (conceptual) | STEP 8 first-run path |

## Patterns Already Partially Covered in high-impact-patterns.md

The existing high-impact-patterns.md #7 ("两阶段反思循环") covers the Learn+Consolidate concept at a high level (2 lines) but has ZERO implementation detail. This scan provides:
- Exact file:line references for every component
- Concrete JSON plan format
- Configuration parameters with defaults
- Concurrency guard implementation
- Log rotation implementation
- Frontmatter schema
- Index regeneration algorithm

The existing coverage is a pointer, not a specification. This scan provides the specification.

## Relationship to Previous Gap Analyses

- `autoagent-gap-analysis.md`: Covers 15 patterns from autoagent-src (context bus, handoff, terminal signals, DAG engine, etc.). No overlap with autodream reflection patterns.
- `autoagent-security-patterns.md`: Covers 8 patterns (max_turns, CancelledError, retry escalation, etc.). No overlap.
- `staged-event-driven-patterns.md`: Covers 11 patterns (terminal signals, handoff, first-completed dispatch, GOTO/ABORT, etc.). No overlap.

The autodream patterns are **complementary**: they add the post-workflow layer that none of the previous scans addressed. Together, the patterns form a complete lifecycle:
1. Pre-workflow: STEP 0 (using-superpowers + openspec-explore)
2. During-workflow: STEPS 1-7 (diagnosis -> execution -> verification)
3. Post-workflow: STEP 8 (meta-reflection: Learn + Consolidation)

## Concrete Changes to SKILL.md

The most impactful change is one new section after STEP 7:

### New: "STEP 8 -- 工作流后元反思 (v3.8.0)"

This section should contain all P0 and P1 patterns integrated into a coherent workflow step:

1. Trigger conditions (dual-gate from P0-2)
2. Phase 1: Learn (from P0-1)
   - Input assembly
   - LLM prompt format
   - JSON plan structure
   - Memory file format with frontmatter
   - Application rules
3. Phase 2: Consolidation (from P0-1, P1-3)
   - Trigger counter (from P1-5)
   - Orphan detection (from P1-3)
   - Merge LLM prompt
4. Checksum detection (from P0-3)
5. INDEX regeneration (from P0-4)
6. Reflection log (from P1-2)
7. Concurrency guard (from P2-2)
8. Error/degradation handling

### Update: memory/high-impact-patterns.md

Update pattern #7 ("两阶段反思循环") with:
- Concrete file:line references
- Implementation detail summary
- Link to this gap analysis for full specification

### Update: "记忆" section in SKILL.md

Add `.promptinclude.md` taxonomy (from P1-1), auto-index generation note.

---

## Files to Write/Update

| File | Action | Content |
|------|--------|---------|
| `memory/autodream-gap-analysis.md` | **WRITE THIS FILE** | This entire analysis |
| `memory/high-impact-patterns.md` | Update pattern #7 | Add concrete autodream file:line refs, link to this analysis |
| `SKILL.md` | Add section after line 299 | "STEP 8 -- 工作流后元反思" (full specification) |
