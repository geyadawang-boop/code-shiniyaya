# autodream -> code-shiniyaya: Durable Memory Pattern Transfer Analysis
# Generated 2026-07-16 | Source: autodream-src v1.0.5 | Target: code-shiniyaya v3.7.0
#
# Dimension: Durable memory — dual-representation (markdown + vector DB),
# checksum-based idempotent writes, state lifecycle with schema versioning.
# ============================================================================

## Finding 1 — P0: No checksum-based idempotent writes on memory files

### Source
  autodream-src/helpers/auto_dream.py:534-541

  Actual code:
    text = file_path.read_text(encoding="utf-8")
    checksum = hashlib.md5(text.encode("utf-8")).hexdigest()
    tracked = file_map.get(file_name, {})
    tracked_ids = normalize_string_list(tracked.get("ids", []))
    if tracked.get("checksum") == checksum and tracked_ids:
        continue  # <--- IDEMPOTENT: skip if unchanged

### Gap
  code-shiniyaya's session JSON files have a checksum field (SKILL.md:141),
  but memory files (high-impact-patterns.md, reference-sources-v2.md,
  reference-sources.md) have NO per-file checksum tracking. Every update
  rewrites the file even when content is byte-identical, causing unnecessary
  file timestamps changes and breaking git-based change detection.

### Fix
  Add to SKILL.md "状态文件" section after the atomic write protocol (after line 165):

```markdown
### 记忆文件幂等写入

记忆文件(high-impact-patterns.md, reference-sources-v2.md等)采用
内容校验和去重——内容未变则跳过写入:

1. 写入前: 读目标文件 → MD5 hash → 与新内容hash对比
2. hash匹配 → 跳过写入(已是最新)
3. hash不匹配 → 执行原子写入(os.replace)
4. 首次写入(文件不存在) → 直接写入

校验和存储于 `memory-checksums.json`:
```json
{
  "schemaVersion": "3.7.0",
  "files": {
    "high-impact-patterns.md": {
      "md5": "a1b2c3d4...",
      "updatedAt": "2026-07-16T..."
    }
  }
}
```
  ```

### Priority: P0
  Prevents unnecessary disk writes and false git-dirty states on every
  memory access. Without this, every code-shiniyaya session that touches
  memory files creates spurious diffs.


## Finding 2 — P0: No state lifecycle with schema versioning on memory state files

### Source
  autodream-src/helpers/auto_dream.py:325-347 (state.json) + :554-561 (vector_state.json)

  Actual code:
    # state.json — schema_version: 2
    save_auto_dream_state(memory_subdir, {
        "schema_version": 2,
        "last_dream_at": datetime.now(timezone.utc).isoformat(),
        "dreams_since_consolidation": dreams_since_consolidation,
        ...
    })

    # vector_state.json — schema_version: 1
    save_autodream_vector_state(memory_subdir, {
        "schema_version": 1,
        "initialized": True,
        "files": file_map,
    })

### Gap
  code-shiniyaya's session JSON has schemaVersion (SKILL.md:135: `"schemaVersion": "3.4.0"`),
  but the memory directory itself has NO state lifecycle file. There is no
  record of:
  - When memory files were last updated
  - Which schema version the memory directory conforms to
  - Which reference sources have been ingested
  - How many patterns have been extracted
  - Whether consolidation is needed

  This means any future migration (e.g., adding a new memory file format,
  changing the frontmatter schema, introducing vector DB integration) has
  no way to detect what needs migration.

### Fix
  Add a new file `memory/state.json` with the following schema, and add
  to SKILL.md "状态文件" section:

```markdown
### 记忆目录状态 (`memory/state.json`)

记忆目录自身的生命周期状态追踪:

```json
{
  "schemaVersion": "3.7.0",
  "createdAt": "2026-07-16T...",
  "lastUpdateAt": "2026-07-16T...",
  "lastConsolidationAt": null,
  "referenceSourcesIngested": [
    {"name": "autodream-src", "version": "1.0.5", "patternsExtracted": 19, "ingestedAt": "2026-07-16T..."},
    {"name": "AutoAgent", "version": "latest", "patternsExtracted": 19, "ingestedAt": "2026-07-16T..."}
  ],
  "memoryFileCount": 5,
  "totalPatterns": 65,
  "consolidationDue": false,
  "checksum": ""
}
```

迁移检测:
- 启动时读 state.json → 对比 schemaVersion 与 SKILL.md 版本
- 不匹配 → 运行迁移函数(如 v3.7.0 → v3.8.0 需新增字段)
- 迁移后更新 schemaVersion + checksum
```
  ```

### Priority: P0
  Without this, memory directory format evolution is impossible to manage
  safely. Adding a new field to memory files becomes a manual chore
  instead of an automated migration.


## Finding 3 — P0: No memory consolidation / dedup mechanism

### Source
  autodream-src/helpers/auto_dream.py:264-315 (consolidation phase)
  autodream-src/prompts/autodream.consolidate.sys.md:1-14 (consolidation prompt)
  autodream-src/prompts/autodream.consolidate.msg.md:1-13 (consolidation message)

  Actual code:
    # Phase 2: Consolidate / Clean
    dreams_since_consolidation = int(state.get("dreams_since_consolidation", 0)) + 1
    consolidate_every = coerce_consolidate_every(config.get("consolidate_every_n_dreams"))

    if consolidate_every > 0 and dreams_since_consolidation >= consolidate_every:
        dreams_since_consolidation = 0
        existing_files_for_consolidation = load_existing_memory_files(memory_subdir)
        if len(existing_files_for_consolidation) > 1:
            # Run consolidation prompt → merge overlapping → delete redundant

### Gap
  code-shiniyaya has 5 memory files accumulating patterns from multiple
  reference source ingestion sessions. As more sources are scanned, patterns
  will overlap, duplicate, or drift. There is NO mechanism to:
  - Detect overlapping patterns across memory files
  - Merge redundant patterns into unified descriptions
  - Prune stale/superseded patterns
  - Track which patterns are "active" vs "historical"

  The high-impact-patterns.md already shows this problem: pattern #5
  "双重代表记忆" appears in both high-impact-patterns.md AND
  reference-sources-v2.md with different descriptions.

### Fix
  Add to SKILL.md a new section after the existing "记忆" section (after line 327):

```markdown
### 记忆合并 (每 N 次参考源摄入后)

防止记忆文件碎片化和模式漂移的定期去重合并机制。

**触发**: `consolidationDue === true` 在 `memory/state.json` 中
(每次新参考源摄入后 +1, 达到 `consolidateEveryNIngests` 时触发,
默认 N=3, 对标 autodream `consolidate_every_n_dreams`)

**流程**:
1. 加载所有现有记忆文件→提取每个模式的 key+description
2. 对每个 key 组(跨文件同模式):
   a. 合并描述: 最长 + 最完整 → 保留
   b. 合并 source:line 引用: 去重并集
   c. 合并已验证来源: 跨源并集
3. 生成合并计划: {"merge": [{into, from[], reason}], "delete": [stale_files]}
4. 用户确认(只读计划, 不自动执行) → 逐文件执行
5. 更新 memory/state.json 的 lastConsolidationAt + consolidationDue=false

**合并规则**:
- 同名 key(小写+去空格) → 视为同一模式, 合并
- 不同 key 但共享 ≥2 个源引用 → 视为重叠, 提示用户裁决
- 仅单个源引用且 ≥30 天未更新 → 标 STALE, 提示用户保留/删除
```
  ```

### Priority: P0
  Memory rot is already happening (pattern #5 duplicated across files).
  Without consolidation, each new reference source ingestion adds patterns
  that overlap with existing ones, degrading signal-to-noise ratio.


## Finding 4 — P1: No grounding/attribution tracking per-pattern

### Source
  autodream-src/helpers/auto_dream.py:419-448 (frontmatter with grounding)
  autodream-src/helpers/auto_dream.py:1105-1140 (build_autodream_document metadata)

  Actual code:
    grounding = str(change.get("grounding", "") or "").strip().lower()
    if grounding in {"grounded", "inferred"}:
        frontmatter["grounding"] = grounding
    source_context_ids = normalize_string_list(change.get("source_context_ids", []))
    if source_context_ids:
        frontmatter["source_context_ids"] = source_context_ids
    source_first_prompts = normalize_string_list(change.get("source_first_prompts", []))
    if source_first_prompts:
        frontmatter["source_first_prompts"] = source_first_prompts[:8]
    source_memory_ids = normalize_string_list(change.get("source_memory_ids", []))
    if source_memory_ids:
        frontmatter["source_memory_ids"] = source_memory_ids[:12]

### Gap
  code-shiniyaya's high-impact-patterns.md says "跨源交叉验证: 10个模式被≥2个源独立印证"
  but this is a single human-authored claim — there is NO per-pattern tracking of:
  - Whether a pattern is "grounded" (directly observed in source code) vs "inferred"
  - Which specific file:line pairs support the claim
  - Which source sessions produced the pattern

  Compare pattern #5 in high-impact-patterns.md:
    "双重代表记忆 (autodream + AutoAgent)"
  vs autodream's approach:
    grounding: "grounded"
    source_context_ids: ["ctx_abc123", "ctx_def456"]
    source_first_prompts: ["deep scan autodream memory system", "extract durable memory patterns"]

### Fix
  Add grounding fields to high-impact-patterns.md's pattern format and update
  SKILL.md "记忆" section:

```markdown
### 模式归因追踪

每个记忆模式 MUST 包含以下溯源字段:

```markdown
### N. 模式名称

- **grounding**: grounded | inferred
  (grounded = 直接从源文件 file:line 提取; inferred = 从多个源推断但无直接代码证据)
- **source_files**: 直接支持的源文件列表
  - autodream-src/helpers/auto_dream.py:534-541
- **source_sessions**: 产生此模式的扫描会话 ID
  - sid:a1b2c3d4 (2026-07-16)
- **cross_validated_by**: 独立验证此模式的其他源
  - AutoAgent: flow/core.py:93-151 (事件驱动DAG — 不同机制但相同"双重代表"概念)
- **confidence**: high | medium | low
  (high = 自有代码直接实现 + ≥2 源交叉验证; medium = 1源验证; low = 仅推断)
```

归因缺失的模式 → 标 UNGROUNDED → 下次扫描时优先验证。
```

### Priority: P1
  Without grounding, future sessions cannot distinguish between patterns
  that are truly battle-tested (observed in multiple working codebases)
  vs patterns that were inferred but never verified. This leads to
  integration of unverified patterns that may not work in practice.


## Finding 5 — P1: No memory file frontmatter with provenance

### Source
  autodream-src/helpers/auto_dream.py:419-448 (comprehensive frontmatter)
  
  Fields in autodream memory frontmatter:
    title, description, updated_at, memory_scope, grounding,
    source_context_ids, source_first_prompts, source_memory_ids,
    canonical_scope_name, project_title

### Gap
  code-shiniyaya memory files have minimal frontmatter:
  ```yaml
  ---
  name: code-shiniyaya-reference-sources-v2
  description: ...
  metadata:
    type: reference
    priority: highest
  ---
  ```
  Missing: updated_at (per-file timestamp), grounding, source_context_ids,
  source_first_prompts (which scan sessions produced this), memory_scope.

  This means you cannot answer: "When was this memory file last changed
  and what triggered that change?"

### Fix
  Standardize memory file frontmatter in SKILL.md "记忆" section:

```markdown
### 记忆文件标准前置元数据

所有 `memory/*.md` 文件 MUST 包含:

```yaml
---
title: "..."
description: "..."
updated_at: "2026-07-16T14:30:00Z"  # ISO 8601 UTC
memory_scope: "code-shiniyaya"
canonical_name: "reference-sources-v2"
grounding: grounded                   # grounded | inferred | mixed
source_sessions: ["sid:a1b2c3d4"]    # 产生此文件的扫描会话
pattern_count: 65                     # 此文件含有的模式数
cross_validated_count: 10             # 被≥2源验证的模式数
schema_version: "3.7.0"
---
```

`updated_at` 由写入工具自动更新——人工编辑时手动更新。
```

### Priority: P1
  Standardized provenance enables automated staleness detection and
  consolidation-eligibility checks. Without it, every memory operation
  is manual and error-prone.


## Finding 6 — P1: No memory scope isolation between projects

### Source
  autodream-src/helpers/auto_dream.py:1187-1191 (resolve_memory_subdir)
  autodream-src/helpers/auto_dream.py:813-843 (describe_memory_scope)

  Actual code:
    def resolve_memory_subdir(project_name, agent_profile):
        config = get_memory_plugin_config(project_name, agent_profile)
        if project_name and config.get("project_memory_isolation", True):
            return f"projects/{project_name}"
        return config.get("agent_memory_subdir", "") or "default"

### Gap
  code-shiniyaya's SKILL.md:326-327 states:
    "此Skill对应的所有记忆和修改只能写入本目录, 不得写入 ~/.claude/projects/c--/memory/"
  
  This is a MANUAL rule enforced by human discipline, not a system-enforced
  isolation. If code-shiniyaya is used in multiple projects (it claims to
  be a meta-orchestrator), there is no mechanism to:
  - Scope memories per project (e.g., bilisum patterns vs other-project patterns)
  - Detect cross-project memory leakage
  - Isolate reference source ingestion per project

### Fix
  Add to SKILL.md "记忆" section:

```markdown
### 记忆作用域隔离

记忆文件按 `memory_scope` 隔离——对标 autodream 的 `memory_subdir`:

```
{project_root}/.claude/memory/code-shiniyaya/
  ├── state.json                    # 全局状态
  ├── scopes/
  │   ├── _global/                  # 跨项目共享(元编排模式、验证流程等)
  │   │   ├── high-impact-patterns.md
  │   │   └── reference-sources-v2.md
  │   └── {project_slug}/           # 项目特定记忆
  │       ├── patterns.md
  │       └── reference-sources.md
  └── memory-checksums.json
```

当前(单项目): 所有文件在 `_global/` 下。多项目时: 项目特定模式→对应 `{project_slug}/` 目录。

记忆写入时 MUST 指定 `memory_scope`——写入错误 scope → 日志警告 + 不阻断。
```
  ```

### Priority: P1
  Prevents future cross-contamination when code-shiniyaya is used across
  multiple codebases. The current manual rule is fragile and will fail
  under multi-project usage.


## Finding 7 — P1: No background-task memory sync (all synchronous)

### Source
  autodream-src/helpers/auto_dream.py:74-94 (schedule_auto_dream)
  autodream-src/helpers/auto_dream.py:85-93 (DeferredTask + THREAD_BACKGROUND)

  Actual code:
    task = DeferredTask(thread_name=THREAD_BACKGROUND)
    task.start_task(
        _run_auto_dream,
        context_id=context_id,
        project_name=project_name,
        agent_profile=agent_profile,
        memory_subdir=memory_subdir,
    )
    _TASKS[memory_subdir] = task

### Gap
  code-shiniyaya's memory operations (writing patterns, updating reference
  sources) are all inline/synchronous — they block the main CC conversation
  flow. autodream runs memory synthesis as a background task so the agent
  can continue interacting while memory is being consolidated.

  For code-shiniyaya: when 5+ Agent parallel scans complete and results
  need to be written to memory files, this currently blocks the conversation.
  If memory sync takes 30s, the user waits.

### Fix
  Add to SKILL.md "记忆" section:

```markdown
### 异步记忆写入

记忆文件写入(尤其是多文件批量更新)应异步执行:

1. 收集所有待写入变更→写入临时 `.queued/` 目录
2. 触发后台 Agent: "将 queued 变更应用到 memory/ 文件"
3. 主流程继续, 不等记忆写入完成
4. 后台 Agent 完成后 → log() 通知:"记忆已更新: {summary}"
5. 失败 → log() 错误, 保留 `.queued/` 供检查

对标 autodream 的 `DeferredTask(thread_name=THREAD_BACKGROUND)`:
- CC 无线程——用后台 Agent 替代
- Agent 超时=300s, 同规则7失败替换
```
  ```

### Priority: P1
  Prevents memory writes from blocking the main conversation flow during
  batch reference-source ingestion (STEP 1.5 where 5+ agents complete
  simultaneously).


## Finding 8 — P2: No dream log / per-operation audit trail for memory changes

### Source
  autodream-src/helpers/auto_dream.py:994-1018 (append_auto_dream_log)
  autodream-src/helpers/auto_dream.py:1021-1071 (render_auto_dream_log_entry)

  Actual code:
    def append_auto_dream_log(memory_subdir, summary, created_files, updated_files,
                              deleted_files, run_metadata):
        entry = render_auto_dream_log_entry(...)
        existing_entries = parse_auto_dream_log_entries(...)
        merged_entries = [entry, *existing_entries][:AUTO_DREAM_LOG_MAX_ENTRIES]
        header = "# AutoDream Log\n\nNewest runs first.\n\n"
        path.write_text(header + "\n\n".join(merged_entries).rstrip() + "\n", ...)

### Gap
  code-shiniyaya has no per-memory-operation audit trail. When a pattern
  is added/modified/deleted in high-impact-patterns.md, there is no record of:
  - When it happened
  - Which session triggered it
  - What exactly changed (created/updated/deleted)
  - What the scope/phase was

  CHANGELOG.md tracks SKILL.md changes, not memory file changes.

### Fix
  Add to SKILL.md "记忆" section:

```markdown
### 记忆变更日志 (`memory/.changelog.md`)

每次记忆写入操作 MUST 追加一条变更记录(最新在前, 最多保留40条):

```markdown
## 2026-07-16 14:30 UTC
- Summary: 从 autodream-src 提取19个模式, 写入 reference-sources-v2.md
- Scope: _global
- Phase: reference-ingestion
- Created: reference-sources-v2.md
- Updated: high-impact-patterns.md (cross-validated patterns #5, #7, #8 updated)
- Session: sid:a1b2c3d4
- Inputs: 1 source repo, 19 patterns extracted
```

格式对标 autodream `.dream-log.md`——markdown headings, 最新在前, 硬上限40条。
```
  ```

### Priority: P2
  Audit trail for debugging "when did this pattern get added and why?"
  Without it, memory file evolution is opaque.


## Finding 9 — P2: No taxonomy differentiation (rules vs facts vs patterns)

### Source
  autodream-src/prompts/autodream.sys.md:47-49 (taxonomy rule)
  autodream-src/prompts/autodream.consolidate.sys.md:11 (taxonomy enforcement)

  Actual text:
    - **Taxonomy (Rules vs. Facts)**: Differentiate between behavioral
      guidelines and general knowledge.
      - If a memory contains strict instructions, behavioral rules, constraints,
        or formatting mandates for the AI, save it as a `.promptinclude.md` file.
      - If a memory contains facts, context, architectural decisions, or history,
        save it as a standard `.md` file.

### Gap
  code-shiniyaya memory files are all `.md` with no differentiation between:
  - **Rules/Constraints** (e.g., "P0双验证 MUST be enforced")
  - **Facts/Patterns** (e.g., "autodream uses checksum-based idempotent writes")
  - **History/Context** (e.g., "2026-07-16: cleaned up bilisum memory leakage")

  All three types are mixed in the same files, making it impossible to
  automatically separate "rules that MUST be followed" from "interesting
  observations" from "historical record."

### Fix
  Add to SKILL.md "记忆" section:

```markdown
### 记忆分类法(Rules vs Patterns vs History)

对标 autodream 的 `.promptinclude.md`(规则) vs `.md`(事实) 分类:

| 类型 | 文件后缀 | 内容 | 自动加载 |
|------|---------|------|---------|
| **规则** | `.rules.md` | 硬约束、执行流程、门控条件 | 每次对话 MUST 加载 |
| **模式** | `.patterns.md` | 可集成模式、参考源提取 | 按需加载(STEP 1.5) |
| **历史** | `.history.md` | 变更记录、审计追踪 | 仅调试时加载 |

当前迁移:
- `high-impact-patterns.md` → `high-impact-patterns.patterns.md`
- `memory-isolation-rule.md` → `memory-isolation.rules.md`
- `cleanup-verification.md` → `cleanup-verification.history.md`
- `.changelog.md` → 新增
```
  ```

### Priority: P2
  Classification enables selective loading — rules are always loaded;
  patterns are loaded only during reference ingestion; history is loaded
  only during debugging. Saves context window on every session.


## Finding 10 — P2: No orphan candidate detection for stale/renamed memory files

### Source
  autodream-src/helpers/auto_dream.py:846-918 (find_orphan_candidates)

  Actual code:
    def find_orphan_candidates(memory_subdir: str) -> list[dict[str, Any]]:
        # For project-scoped memory: detect sibling projects with
        # overlapping token names that may be leftovers from a rename.
        sibling_tokens = slug_tokens(sibling_project_name)
        overlap = score_token_overlap(current_tokens, sibling_tokens)
        if overlap < MIN_ORPHAN_OVERLAP:  # 0.5
            continue

### Gap
  code-shiniyaya's memory directory has 5 files. If a file is renamed
  (e.g., `anti-hang-v2.md` → `anti-hang-v2.1.md`), the old file lingers
  with no detection. If a future scan produces overlapping patterns with
  an existing file under a different name, the duplication goes undetected.

### Fix
  Add to SKILL.md "记忆合并" subsection:

```markdown
### 孤立文件检测

每次参考源摄入后, 运行孤立检测:
1. 对比所有 memory/*.md 文件的 title/description token overlap
2. overlap ≥ 0.5 (Jaccard) → 标为 potential-duplicate
3. 生成报告: "以下文件可能重叠: [A] ↔ [B] (overlap: 0.72), 建议合并"
4. 用户确认 → 手动合并或忽略

对标 autodream `score_token_overlap()` + `slug_tokens()` 实现:
```python
def slug_tokens(text: str) -> set[str]:
    return {t for t in re.findall(r"[a-z0-9]+", text.lower()) if len(t) > 1}

def score_overlap(a: set[str], b: set[str]) -> float:
    if not a or not b: return 0.0
    return len(a & b) / max(len(a), len(b))
```
```
  ```

### Priority: P2
  Prevents silent duplication as memory files grow. Currently 5 files
  is manageable manually; at 20+ files this becomes essential.


## Summary: Integration Priority Matrix

| # | Pattern | P | Effort | Impact | Target Files |
|---|---------|---|--------|--------|-------------|
| 1 | 幂等写入(checksum) | P0 | Low | 防止虚假 git diff | SKILL.md, memory-checksums.json |
| 2 | 状态生命周期(schema versioning) | P0 | Low | 安全格式迁移 | SKILL.md, memory/state.json |
| 3 | 记忆合并(dedup) | P0 | Med | 防止模式漂移 | SKILL.md, high-impact-patterns.md |
| 4 | 归因追踪(grounding) | P1 | Med | 可信度分级 | SKILL.md, high-impact-patterns.md |
| 5 | 标准前置元数据 | P1 | Low | 自动化过期检测 | SKILL.md, all memory/*.md |
| 6 | 作用域隔离 | P1 | Med | 多项目安全 | SKILL.md |
| 7 | 异步记忆写入 | P1 | Low | 防阻塞 | SKILL.md |
| 8 | 变更日志(.changelog.md) | P2 | Low | 审计追踪 | SKILL.md, memory/.changelog.md |
| 9 | 记忆分类法(rules/patterns/history) | P2 | Med | 按需加载 | SKILL.md |
| 10 | 孤立文件检测 | P2 | Low | 防重复 | SKILL.md |

## Key Insight: The "N+1" Anti-Pattern

code-shiniyaya already has the CORRECT atomic write protocol for session
JSON files (SKILL.md:156-165: tmp file → flush → fsync → os.replace).
But this protocol is ONLY applied to 3 session-scoped JSON files
(session-*.json, pending-*.json, dag-*.json).

The autodream lesson is: durable memory files need the SAME rigor as
state files. Every memory file write should be:
  checksum → idempotent? → skip : (tmp → flush → fsync → os.replace)

The fact that memory files are Markdown (not JSON) doesn't change the
need for atomic writes — it's the SAME filesystem, SAME failure modes.
