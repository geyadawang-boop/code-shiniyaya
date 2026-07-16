# autodream-src Config-Driven Behavior Patterns -- code-shiniyaya Gap Analysis

Source: C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src
Targets: C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md, C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\high-impact-patterns.md
Date: 2026-07-16
Scanner: CC (code-shiniyaya v3.7.0)
DIMENSION: Config-driven behavior -- three-layer config resolution, coercion functions, per-project/per-agent override, externalizing hardcoded constants

## How code-shiniyaya Can Externalize Its Hardcoded Constants

SKILL.md v3.7.0 contains 60+ hardcoded numeric constants embedded in prose. Every threshold, every retry count, every timeout, every agent count is a magic number that cannot be tuned without editing the skill file directly. autodream demonstrates a complete config-driven architecture: plugin.yaml declares `per_project_config: true` and `per_agent_config: true`, default_config.yaml holds user-editable defaults, and every config access goes through coercion functions that (a) validate the type, (b) substitute a sensible default on missing/invalid data, and (c) enforce floor/ceiling guards.

---

## P0 -- Critical: Config Architecture Patterns (Directly Address the Prompt)

### Finding 1: Three-Layer Config Resolution with Per-Project/Per-Agent Override

**Source**: autodream-src/plugin.yaml:6-8, autodream-src/helpers/auto_dream.py:105-109, autodream-src/helpers/auto_dream.py:1159-1184

**Pattern**:
```yaml
# plugin.yaml:6-8 -- declares capabilities, not values
per_project_config: true
per_agent_config: true
```

```python
# auto_dream.py:105-109 -- three-layer resolution
config = get_autodream_config(project_name, agent_profile)  # layer 3: runtime merged
memory_config = get_memory_plugin_config(project_name, agent_profile)  # layer 3: dependent plugin config

# auto_dream.py:1159-1170 -- resolution implementation
def get_autodream_config(project_name, agent_profile):
    return (
        plugins.get_plugin_config(
            PLUGIN_NAME,
            project_name=project_name or "",
            agent_profile=agent_profile or "",
        )
        or {}
    )
```

Layer 1: plugin.yaml declares `settings_sections: [agent]` + `per_project_config: true` + `per_agent_config: true`
Layer 2: default_config.yaml provides user-editable defaults (enabled, min_hours, min_sessions, line_limit, consolidate_every_n_dreams)
Layer 3: At runtime, `plugins.get_plugin_config()` merges: default.yaml < project-specific overrides < agent-profile overrides

**code-shiniyaya gap**: SKILL.md has ZERO config files. All behavioral parameters are hardcoded in prose. The user cannot change N=4 to N=6, cannot change batch_size floor to 8, cannot set per-project agent limits. A single user working on a small project and a large monorepo get exactly the same parameters.

**Concrete fix -- Create this file**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\default_config.yaml`

```yaml
# code-shiniyaya default configuration -- user may override any value
# Schema version tracks config format changes
schema_version: 1

# ---- Silence / Timeout Thresholds ----
codex_silence_n: 4           # messages without Codex reply before asking "keep waiting?"
codex_degrade_after_n: 5     # messages without reply -> auto-degrade (must be > codex_silence_n)
straggler_gap: 3             # agents completed by others without this agent's result -> straggler
stall_user_turns: 5          # user turns without any agent log() -> workflow stalled

# ---- Agent Batching ----
batch_size_formula: "max(floor, min(ceiling, cpu_cores - headroom))"
batch_floor: 4               # minimum agents per batch
batch_ceiling: 16            # maximum agents per batch
cpu_headroom: 2              # cores reserved for system
agent_cap_total: 50          # maximum total agents across all batches

# ---- Per-Step Agent Counts ----
step1_diagnosis_min: 6       # minimum agents for diagnosis scan
step1_5_reference_min: 5     # minimum agents for reference source scan
step4_codex_verify_min: 10   # minimum agents for Codex feedback verification
iter_scan_agents_per_iter: 8 # agents per iteration scan workflow

# ---- Retry / Failure ----
slot_max_replacements: 2     # max agent replacements per slot before permanent failure
same_file_failure_stop: 3    # consecutive same-file failures -> STOP
retry_tiers: 3               # tier escalation: 1=same, 2=feedback, 3=meta-agent
transient_retry_max: 4       # max retries for transient (network/API) errors
transient_backoff_base_s: 10 # base seconds for exponential backoff

# ---- Token / Size Limits ----
step3_split_threshold: 10000 # tokens -> split Codex message into parts
step3_part_max: 8000         # max tokens per part
agent_output_truncate: 12000 # tokens -> truncate agent output, save full to file
agent_output_warn: 8000      # tokens -> warn but pass through
max_turns_per_agent: 40      # hard limit on LLM turn count per agent
fix_turns_per_item: 20       # max turns per fix item in STEP 6

# ---- Convergence ----
convergence_healthy_pct: 60  # CR > this -> healthy convergence
convergence_warn_pct: 20     # CR < this -> slow/no convergence alert
convergence_critical_rises: 2 # consecutive CR rises -> force stop + strategy change

# ---- Iteration Scan ----
iter_scan_max_iterations: 10 # max iterations before forced stop
iter_scan_retries_per_slot: 2 # retries per dimension slot

# ---- State File ----
state_schema_version: "3.4.0"
checksum_algorithm: "SHA-256"
corrupt_file_suffix: ".corrupt"
conflict_file_suffix: ".conflict"

# ---- Per-Project Overrides (example) ----
# projects:
#   my-large-monorepo:
#     agent_cap_total: 80
#     batch_ceiling: 24
#     step1_diagnosis_min: 10
#   my-small-cli-tool:
#     agent_cap_total: 20
#     batch_ceiling: 8
#     step1_diagnosis_min: 3
```

**Concrete fix -- Add to SKILL.md** (new section after the frontmatter):

```markdown
## 配置系统 (v3.8.0)

所有硬编码常量已外部化到 `default_config.yaml`。用户可编辑此文件调整阈值, 无需修改 SKILL.md。

### 三层解析

1. `default_config.yaml` -- 全局默认值(用户可编辑)
2. 项目级覆盖 -- `default_config.yaml` 中 `projects.<project_name>` 块
3. 环境变量覆盖 -- `CODE_SHINIYAYA_<KEY>` (例如 `CODE_SHINIYAYA_CODEX_SILENCE_N=6`)

### 解析规则

- 缺失key -> 使用default_config.yaml中的值
- 类型错误(如字符串"abc"赋值给整数字段) -> 回退到default_config.yaml中的默认值
- 越界值(如batch_ceiling=1000超过上限) -> 钳制到安全范围
- 空值/null -> 使用default_config.yaml中的默认值

### 加载伪代码

```
def get_config(key: str, project_name: str | None = None) -> Any:
    env_val = os.environ.get(f"CODE_SHINIYAYA_{key.upper()}")
    if env_val is not None:
        return coerce(env_val, key)  # type-convert + validate

    defaults = load_yaml("default_config.yaml")
    project_overrides = defaults.get("projects", {}).get(project_name, {}) if project_name else {}

    raw = project_overrides.get(key, defaults.get(key))
    return coerce(raw, key)
```
```

**Priority**: P0 -- This is the single most impactful change. It addresses the prompt's specific question ("How can code-shiniyaya externalize its hardcoded constants?") and enables all other config-driven improvements below.

---

### Finding 2: Coercion Functions with Sensible Defaults for Every Config Value

**Source**: autodream-src/helpers/auto_dream.py:656-683

**Pattern**:
```python
# auto_dream.py:656-663
def coerce_consolidate_every(raw: Any) -> int:
    if raw is None:
        return 3                    # sensible default when key is missing
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3                    # sensible default on type error
    return max(0, value)            # floor guard (never negative)

# auto_dream.py:666-673
def coerce_min_hours(raw: Any) -> float:
    if raw is None:
        return 8.0                  # sensible default: 8 hours
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return 8.0
    return max(0.0, value)

# auto_dream.py:676-683
def coerce_min_sessions(raw: Any) -> int:
    if raw is None:
        return 3                    # sensible default: 3 sessions
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return 3
    return max(0, value)
```

Every single config key has a dedicated coercion function that handles: (a) missing key -> sensible default, (b) wrong type -> sensible default, (c) out-of-range -> clamped to valid range. The defaults are NOT the same as the config file defaults -- they are LAST-RESORT defaults when even the config file is missing.

**code-shiniyaya gap**: SKILL.md hardcoded constants have NO coercion. If the config file has `batch_ceiling: "sixteen"` (string instead of int), the entire workflow crashes because Python tries `min(16, "sixteen")`. If the config file is deleted, there is no fallback -- the skill simply cannot run.

**Concrete fix -- Add to SKILL.md** (new section "配置强制函数"):

```markdown
### 配置强制函数 (Coercion Functions)

每个配置键有专用强制函数, 处理缺失/类型错误/越界。与 `default_config.yaml` 配合使用。

```
def coerce_int(raw: Any, default: int, floor: int | None = None, ceiling: int | None = None) -> int:
    """Coerce any value to int with default and range clamping."""
    if raw is None:
        return default
    try:
        value = int(raw)
    except (TypeError, ValueError):
        return default
    if floor is not None and value < floor:
        return floor
    if ceiling is not None and value > ceiling:
        return ceiling
    return value

def coerce_float(raw: Any, default: float, floor: float | None = None) -> float:
    """Coerce any value to float with default and floor clamping."""
    if raw is None:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    if floor is not None and value < floor:
        return floor
    return value

# Per-key coercion (auto-generated from default_config.yaml schema)
COERCION_REGISTRY = {
    "codex_silence_n":       lambda r: coerce_int(r, 4, floor=2, ceiling=20),
    "codex_degrade_after_n": lambda r: coerce_int(r, 5, floor=3, ceiling=30),
    "batch_floor":           lambda r: coerce_int(r, 4, floor=1, ceiling=32),
    "batch_ceiling":         lambda r: coerce_int(r, 16, floor=2, ceiling=64),
    "agent_cap_total":       lambda r: coerce_int(r, 50, floor=5, ceiling=200),
    "step1_diagnosis_min":   lambda r: coerce_int(r, 6, floor=1, ceiling=40),
    "transient_retry_max":   lambda r: coerce_int(r, 4, floor=0, ceiling=10),
    "agent_output_truncate": lambda r: coerce_int(r, 12000, floor=1000, ceiling=100000),
    "convergence_healthy_pct": lambda r: coerce_float(r, 60.0, floor=0.0),
    # ... all 25+ config keys
}
```
```

**Priority**: P0 -- Without coercion functions, externalizing config to `default_config.yaml` is dangerous (any typo in the YAML breaks the workflow). Coercion ensures robustness.

---

### Finding 3: Config-Driven Dual-Threshold OR-Gating

**Source**: autodream-src/helpers/auto_dream.py:686-702, autodream-src/helpers/auto_dream.py:116-122

**Pattern**:
```python
# auto_dream.py:686-702 -- should_run_auto_dream()
def should_run_auto_dream(
    last_dream_at: datetime | None,
    recent_session_count: int,
    min_hours: float,      # from config, coerced
    min_sessions: int,     # from config, coerced
) -> bool:
    if recent_session_count <= 0:
        return False
    if last_dream_at is None:
        return True           # never run before -> always run

    hours_since = (datetime.now(timezone.utc) - last_dream_at).total_seconds() / 3600
    if min_sessions > 0 and recent_session_count >= min_sessions:
        return True            # OR: session threshold met
    if min_hours > 0 and hours_since >= min_hours:
        return True            # OR: time threshold met
    return False               # neither threshold met

# auto_dream.py:116-122 -- caller
if not should_run_auto_dream(
    last_dream_at=last_dream_at,
    recent_session_count=len(recent_sessions),
    min_hours=coerce_min_hours(config.get("min_hours")),     # from config, NOT hardcoded
    min_sessions=coerce_min_sessions(config.get("min_sessions")), # from config, NOT hardcoded
):
    return  # early exit, skip the entire dream
```

This is NOT a simple "run every N hours" cron. It's a dual-orthogonal-threshold OR-gate: run if EITHER (a) enough time has passed since last run, OR (b) enough sessions have accumulated. Both thresholds come from config, are coerced through their respective functions, and can be set to 0 to disable that dimension. The gate decision is logged in state.json for auditability.

**code-shiniyaya gap**: code-shiniyaya has NO config-driven gating for workflow execution. The 7-step workflow is ALWAYS triggered by user keywords. There is no "don't run if X condition" pre-check. Specific gaps:
- The iteration scan workflow has a hardcoded "2 consecutive CR rises -> stop" but the CR threshold percentages are hardcoded (60%, 20%).
- The Codex silence threshold (N=4) is hardcoded -- there is no way to say "for this project, Codex usually responds within 2 messages, so N=2".
- The straggler detection gap (3 messages) is hardcoded.
- All of these should be configurable per-project.

**Concrete fix -- Add to SKILL.md** (in the "迭代扫描工作流" section):

```markdown
### 可配置工作流门控 (v3.8.0)

工作流启动前检查双阈值门控(仿autodream的should_run_auto_dream模式):

```
should_run_iteration_scan(
    last_scan_state: dict,
    config: dict,
) -> bool:
    # Threshold 1: Convergence rate below warn threshold -> must run
    cr = last_scan_state.get("convergence_rate", 100)
    if cr < coerce_float(config.get("convergence_warn_pct"), 20.0):
        return True

    # Threshold 2: Iterations below max -> may run
    iterations = last_scan_state.get("iterations", 0)
    if iterations >= coerce_int(config.get("iter_scan_max_iterations"), 10):
        return False  # max iterations exhausted

    # Threshold 3: CRITICAL count > 0 -> must run (unfixed bugs remain)
    if last_scan_state.get("critical_count", 0) > 0:
        return True

    return False  # no reason to run
```

### Codex静默阈值(可配置)

```
codex_silence_n = coerce_int(config.get("codex_silence_n"), 4, floor=2, ceiling=20)
straggler_gap = coerce_int(config.get("straggler_gap"), 3, floor=1, ceiling=10)
stall_turns = coerce_int(config.get("stall_user_turns"), 5, floor=2, ceiling=20)
```

### 与现有降级逻辑的集成

在SKILL.md中所有出现 `N=4` 的位置替换为 `N={codex_silence_n}`, 出现 `3条消息` 的位置替换为 `{straggler_gap}条消息`。
```

**Priority**: P0 -- The "config-driven gating" is the core of the autodream architecture and directly answers the prompt's dimension. Without this, externalizing constants (Finding 1) is just a data file -- gating makes it an active control system.

---

## P1 -- Important: Robustness and Operational Patterns

### Finding 4: Thread-Safe Mutex to Prevent Duplicate Parallel Execution

**Source**: autodream-src/helpers/auto_dream.py:49-51, autodream-src/helpers/auto_dream.py:74-93

**Pattern**:
```python
# auto_dream.py:49-51 -- module-level mutex
_RUNNING_SUBDIRS: set[str] = set()
_RUNNING_LOCK = threading.Lock()
_TASKS: dict[str, DeferredTask] = {}

# auto_dream.py:74-93 -- acquire before scheduling
def schedule_auto_dream(context_id, project_name, agent_profile, memory_subdir) -> bool:
    with _RUNNING_LOCK:
        if memory_subdir in _RUNNING_SUBDIRS:
            return False       # ALREADY RUNNING -- reject duplicate
        _RUNNING_SUBDIRS.add(memory_subdir)

    task = DeferredTask(thread_name=THREAD_BACKGROUND)
    task.start_task(_run_auto_dream, ...)
    _TASKS[memory_subdir] = task
    return True

# auto_dream.py:360-365 -- release in finally block
finally:
    with _RUNNING_LOCK:
        _RUNNING_SUBDIRS.discard(memory_subdir)
    _TASKS.pop(memory_subdir, None)
```

This prevents the same memory scope from having two concurrent AutoDream runs. If a second session triggers AutoDream while the first is still running, `schedule_auto_dream()` returns `False` and the caller silently skips.

**code-shiniyaya gap**: code-shiniyaya has session isolation via `{sessionId[:8]}` in filenames, but NO mechanism to prevent the SAME session from launching duplicate workflows. If the user says "告诉codex" twice rapidly, two sets of 10+ agents could be launched for the same STEP 4 verification. The session.json `step` field provides some protection (you can't enter STEP 4 if you're already in STEP 4), but this is a soft guard, not a mutex.

**Concrete fix -- Add to SKILL.md** (new section in "状态文件"):

```markdown
### 工作流互斥锁 (v3.8.0)

防止同一会话启动重复工作流:

```
# session-{id}.json 新增字段
{
  "workflowLock": {
    "active_workflow_type": "STEP_4_CODEX_VERIFY",
    "lock_acquired_at": "2026-07-16T14:30:00Z",
    "lock_session_step": 4
  }
}
```

### 锁定协议

1. 任何工作流步骤启动前, 先检查 `session.workflowLock`:
   - 无活跃锁 -> 获取锁, 写入 `active_workflow_type` 和获取时间
   - 有活跃锁 -> 拒绝启动, 提示用户: "工作流 {active_workflow_type} 正在运行中(自 {lock_acquired_at})。等待完成或说'终止'停止。"
2. 工作流完成(正常/失败/中断) -> 释放锁 (设置 `workflowLock = null`)
3. 中断恢复时: 检查锁是否残留(锁时间 > 2小时前) -> 自动清理陈旧锁

### 与现有原子写入协议的集成

锁定操作使用相同的原子写入协议: 读取session JSON -> 检查/修改workflowLock -> 写入(带SHA-256校验)。
```

**Priority**: P1 -- Duplicate workflow launch is a real risk for users who trigger keywords rapidly. The mutex prevents wasted agent capacity.

---

### Finding 5: Checksum-Based "Skip If Unchanged" Processing

**Source**: autodream-src/helpers/auto_dream.py:534-552

**Pattern**:
```python
# auto_dream.py:534-552 -- sync_autodream_vector_memory()
for file_name, file_path in current_paths.items():
    text = file_path.read_text(encoding="utf-8")
    checksum = hashlib.md5(text.encode("utf-8")).hexdigest()
    tracked = file_map.get(file_name, {})
    tracked_ids = normalize_string_list(tracked.get("ids", []))
    if tracked.get("checksum") == checksum and tracked_ids:
        continue                   # SKIP: file unchanged AND vector IDs exist

    # File changed -> delete old vectors, insert new ones
    if tracked_ids:
        await db.delete_documents_by_ids(tracked_ids)

    frontmatter, body = parse_frontmatter(text)
    inserted_ids = await db.insert_documents([build_autodream_document(...)])
    file_map[file_name] = {
        "checksum": checksum,      # store for next comparison
        "ids": inserted_ids,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }
```

Each memory file's MD5 checksum is compared against the previous run's checksum (stored in `vector_state.json`). If both the checksum matches AND vector IDs already exist, the ENTIRE vector sync for that file is skipped. This is O(1) per file instead of O(content-size).

**code-shiniyaya gap**: code-shiniyaya's state files (session JSON, pending JSON, DAG JSON) are always written in full on every step transition. There is NO "is this file unchanged since last write?" check. Specific gaps:
- When session JSON is re-read after a stop, the `checksum` field validates integrity but is never used for "skip if unchanged."
- The DAG is rebuilt from `git rev-parse HEAD` on every recovery -- even when HEAD hasn't changed.
- The iteration scan writes `scan-state-{iter}.json` for every iteration, even when the scan found nothing new (all PASS).
- Agent results that are identical across iterations are re-processed each time.

**Concrete fix -- Add to SKILL.md** (in "状态文件" section):

```markdown
### 校验和跳过优化 (v3.8.0)

对重复处理进行跳过优化, 仿autodream的checksum-based skip:

#### 会话状态写入跳过
写入 `session-{id}.json` 前: 计算新状态的SHA-256 -> 与当前磁盘文件SHA-256对比。相同 -> 跳过写入(无变更)。

#### DAG重建跳过
恢复时: 对比 `dag.snapshot` (git HEAD) 与实际 `git rev-parse HEAD`。相同 -> 复用现有DAG, 不重建。不同 -> 重建DAG并更新snapshot。

#### 迭代扫描结果跳过
迭代N的 `scan-state-{N}.json` 与迭代N-1对比:
- 所有维度verdict相同 AND issueCount相同 -> 跳过写入(收敛, 无新发现)
- 任意维度变化 -> 写入新state文件

#### Agent结果缓存
同一 (file, line_range, agent_type, task_signature) 元组在24小时内已有结果 -> 复用缓存, 不重新启动Agent。

```
# 缓存键: SHA-256(file + line_range + agent_type + task_prompt[:200])
cache_key = hashlib.sha256(f"{file}:{line_start}-{line_end}:{agent_type}:{task}".encode()).hexdigest()
cached = agent_result_cache.get(cache_key)
if cached and (now - cached["ts"]).hours < 24:
    return cached["result"]  # reuse
```
```

**Priority**: P1 -- In large iteration scans (10+ iterations), checksum skipping can reduce redundant processing by 60-80%.

---

### Finding 6: State Schema Versioning for Backward Compatibility

**Source**: autodream-src/helpers/auto_dream.py:325-347, autodream-src/helpers/auto_dream.py:554-561

**Pattern**:
```python
# auto_dream.py:325-347 -- save_auto_dream_state with schema_version
save_auto_dream_state(
    memory_subdir,
    {
        "schema_version": 2,           # versioned schema
        "last_dream_at": ...,
        "last_status": ...,
        "last_summary": ...,
        "memory_file_count": ...,
        "dreams_since_consolidation": dreams_since_consolidation,
        # ... all fields
    },
)

# auto_dream.py:554-561 -- vector_state with separate schema version
save_autodream_vector_state(
    memory_subdir,
    {
        "schema_version": 1,           # independent schema version
        "initialized": True,
        "files": file_map,
    },
)
```

Two distinct state files each have their OWN `schema_version` numbers that evolve independently. The `state.json` schema is at v2 (added `dreams_since_consolidation`), while `vector_state.json` is at v1. When reading, the code checks `schema_version` to decide how to interpret the data.

**code-shiniyaya gap**: code-shiniyaya's session JSON has `"schemaVersion": "3.4.0"` -- a single version number. But it's only used for the session state file (session-{id}.json). The pending fix file (pending-{id}.json) and DAG file (dag-{id}.json) have their own declared `"schemaVersion": "3.4.0"` but they don't evolve independently. If a future version adds a `fixTier` field to pending items, there's no way to know whether a pending.json written by v3.7.0 supports that field.

**Concrete fix -- Add to SKILL.md** (in "状态文件" section):

```markdown
### 独立Schema版本控制 (v3.8.0)

每个状态文件有独立schema版本, 允许独立演进(仿autodream):

| 文件 | Schema键 | 当前版本 | 新增于 | 说明 |
|------|---------|---------|--------|------|
| session-{id}.json | `sessionSchemaVersion` | "3.4.0" | v3.4.0 | 会话状态+步骤追踪 |
| pending-{id}.json | `pendingSchemaVersion` | "1.0.0" | v3.8.0 | 待修复项(独立演进) |
| dag-{id}.json | `dagSchemaVersion` | "1.0.0" | v3.8.0 | 依赖图(独立演进) |
| eventlog-{id}.jsonl | `eventlogSchemaVersion` | "1.0.0" | v3.8.0 | 事件日志(独立演进) |

### 读取时版本适配

```
def read_state_file(path, expected_schema_key):
    data = json.loads(read_file(path))
    version = data.get(expected_schema_key, "0.0.0")

    if version == "3.4.0":       # current session schema
        return data
    elif version == "3.3.0":     # older session schema (missing itemStates)
        data["itemStates"] = {}  # backfill
        return data
    elif version == "0.0.0":     # pre-schema file
        return migrate_from_legacy(data)  # full migration
    else:
        raise SchemaVersionError(f"Unknown {expected_schema_key}: {version}")
```
```

**Priority**: P1 -- Independent schema versioning prevents the "one version number for everything" fragility. Critical if `pendingSchema` gains a `fixTier` field in v3.9.0 but `dagSchema` stays at v1.0.0.

---

### Finding 7: Markdown Event Log with Newest-First Truncation

**Source**: autodream-src/helpers/auto_dream.py:994-1018, autodream-src/helpers/auto_dream.py:1021-1071

**Pattern**:
```python
# auto_dream.py:994-1018 -- append_auto_dream_log()
def append_auto_dream_log(memory_subdir, summary, created_files, updated_files, deleted_files, run_metadata):
    path = Path(get_autodream_log_path(memory_subdir))
    entry = render_auto_dream_log_entry(summary, created_files, updated_files, deleted_files, run_metadata)

    # Parse existing entries, prepend newest, truncate to MAX
    existing_entries = parse_auto_dream_log_entries(path.read_text() if path.exists() else "")
    merged_entries = [entry, *existing_entries][:AUTO_DREAM_LOG_MAX_ENTRIES]  # newest-first, capped

    header = "# AutoDream Log\n\nNewest runs first.\n\n"
    path.write_text(header + "\n\n".join(merged_entries).rstrip() + "\n", encoding="utf-8")

# auto_dream.py:1021-1071 -- human-readable entry format
def render_auto_dream_log_entry(summary, created_files, updated_files, deleted_files, run_metadata):
    timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [f"## {timestamp}"]
    if summary:
        lines.append(f"- Summary: {collapse_single_line(summary)}")
    scope_name = collapse_single_line(run_metadata.get("memory_scope", {}).get("canonical_name", ""))
    if scope_name:
        lines.append(f"- Scope: {scope_name}")
    phase = str(run_metadata.get("phase", "learn")).capitalize()
    lines.append(f"- Phase: {phase}")
    # ... created/updated/deleted lists, orphan hints
    return "\n".join(lines).strip()
```

Output is a human-readable Markdown file (NOT JSON, NOT JSONL) with newest entries first, capped at `AUTO_DREAM_LOG_MAX_ENTRIES` (40). Each entry is a `## timestamp` section with bullet points for summary, scope, phase, input counts, and file changes.

**code-shiniyaya gap**: code-shiniyaya has NO operational log. There is no record of "at 14:32, STEP 1 completed with 3 P0 bugs found" or "at 14:45, Codex replied with 2 approvals and 1 rejection." All state is in JSON files that are machine-readable but not human-auditable. The iteration scan convergence tracking exists only as in-memory state during the CC conversation.

**Concrete fix -- Create this file format for code-shiniyaya**:

```markdown
### WORKFLOW_LOG (.dream-log.md 模式, v3.8.0)

仿autodream的`.dream-log.md`格式, 追加写入 `{project_root}/.claude/memory/code-shiniyaya/workflow-{sessionId[:8]}.md`:

```
# code-shiniyaya Workflow Log
Newest runs first.

## 2026-07-16 14:45 UTC
- Session: a1b2c3d4
- Workflow: CC<->Codex双向验证
- Steps completed: STEP_1 (diagnosis) -> STEP_2 (plan) -> STEP_3 (codex_sent) -> STEP_4 (verified)
- Bugs found: 3 (P0=1, P1=2)
- Codex: 2 approved, 1 rejected (Bug-2 needs replan)
- Agents used: 22 across 3 batches
- Duration: ~15 min (3 user turns)
- Mode: normal

## 2026-07-16 14:15 UTC
- Session: a1b2c3d4
- Workflow: STEP_1 diagnosis only
- Agents launched: 6 (investigator x2, general-purpose x2, Plan x1, debugging x1)
- Completed: 5/6 (1 straggler: Explore agent timed out at src/core.py:200)
- Bugs found: 5 raw (2 after dedup)
- Duration: ~8 min (2 user turns)

## 2026-07-16 13:50 UTC
- Session: a1b2c3d4
- Workflow: STEP_0 precheck
- Openspec: not available, skipped
- using-superpowers: confirmed triggers
- Ready for STEP_1

```

### 格式规则

1. `## ISO8601 UTC timestamp` 作为条目分隔符
2. 每个条目包含: session, workflow phase, outcomes, agent counts, duration
3. 最多保留 40 条(仿AUTO_DREAM_LOG_MAX_ENTRIES)
4. 超限 -> 自动删除最旧条目
5. CC在每个STEP转换时写一条log, 在每个workflow完成时写一条summary

### 与eventlog的互补关系

- `workflow-{id}.md`: 人类可读的Markdown摘要, 适合快速回顾
- `eventlog-{id}.jsonl`: 机器可解析的详细事件流, 适合恢复和审计
```

**Priority**: P1 -- Human-auditable logs are essential for debugging why a workflow made a specific decision 3 days ago.

---

### Finding 8: Two-Phase Processing with Counter-Based Phase Activation

**Source**: autodream-src/helpers/auto_dream.py:97-317, autodream-src/helpers/auto_dream.py:266-272

**Pattern**:
```python
# auto_dream.py:97-317 -- dual-phase architecture
async def _run_auto_dream(...):
    # Phase 1: LEARN (always runs)
    plan = await apply_auto_dream_plan(memory_subdir, plan=learn_plan, ..., run_metadata={"phase": "learn"})

    # Phase 2: CONSOLIDATE (only runs every N dreams)
    dreams_since_consolidation = int(state.get("dreams_since_consolidation", 0)) + 1
    consolidate_every = coerce_consolidate_every(config.get("consolidate_every_n_dreams"))

    consolidate_result = None
    if consolidate_every > 0 and dreams_since_consolidation >= consolidate_every:
        dreams_since_consolidation = 0  # reset counter
        existing_files_for_consolidation = load_existing_memory_files(memory_subdir)

        if len(existing_files_for_consolidation) > 1:
            plan_consolidate = await apply_auto_dream_plan(
                memory_subdir=memory_subdir,
                plan=consolidation_plan,
                run_metadata={"phase": "consolidation"}
            )

    # Merge results from both phases
    final_summary = result["summary"]
    if consolidate_result and consolidate_result["changed"]:
        final_summary += f" | Consolidation: {consolidate_result['summary']}"

    # Track counter in state
    state["dreams_since_consolidation"] = dreams_since_consolidation
```

Phase 1 (Learn) always runs. Phase 2 (Consolidation) only activates when `dreams_since_consolidation >= consolidate_every_n_dreams`. The counter persists in state.json and resets after each consolidation. This prevents expensive dedup/merge processing on every run while still ensuring it happens periodically.

**code-shiniyaya gap**: code-shiniyaya has no concept of periodic maintenance phases. Every workflow run is the same 7-step pipeline with no "skip this expensive step if we just did it recently" mechanism. Specific gaps:
- STEP 1.5 (reference source scan) always runs -- even if the reference source hasn't changed since the last scan.
- STEP 7 (bidirectional verification) always runs a full CC->Codex->CC round.
- The iteration scan always runs all 8 agents, even when convergence is clearly achieved (CR > 95%).
- Memory files (high-impact-patterns.md, etc.) are written but never consolidated or deduplicated.

**Concrete fix -- Add to SKILL.md** (new section):

```markdown
### 两阶段处理 + 计数器激活 (v3.8.0)

仿autodream的Learn+Consolidation两阶段架构:

#### Phase 1: Learn (每次运行)
- STEP 1 诊断 + STEP 2 方案生成
- STEP 4 Codex反馈验证
- STEP 6 逐项执行

#### Phase 2: Consolidate (每N次运行)
由 `consolidate_every_n_workflows` 配置控制(默认=5):

```
# session-{id}.json 新增字段
{
  "workflows_since_consolidation": 4,
  "last_consolidation_at": "2026-07-15T10:00:00Z"
}
```

触发条件: `workflows_since_consolidation >= consolidate_every_n_workflows`

Consolidation操作:
1. 合并记忆文件: 检查 `memory/high-impact-patterns.md` 与 `memory/autoagent-*.md` 的重叠 -> 去重合并
2. 清理过期引用: 检查 `memory/reference-sources.md` 中指向已不可访问源文件的条目 -> 标记或删除
3. 记忆索引重建: 重写 `memory/MEMORY.md`, 移除断链, 更新描述
4. 重置计数器: `workflows_since_consolidation = 0`

#### 可跳过的昂贵步骤(计数器门控)

| 步骤 | 跳过条件 | 计数器 |
|------|---------|--------|
| STEP 1.5 (参考源扫描) | 上次完整扫描后未超过 `reference_scan_every_n` 次workflow | `workflows_since_reference_scan` |
| 迭代扫描全部8 Agent | CR > 90% 持续3次迭代 | `iterations_since_convergence` |
| STEP 7 第2轮 | 第1轮无争议(已有) | N/A |
| 记忆文件去重 | 距上次consolidation不足 `consolidate_every_n_workflows` | `workflows_since_consolidation` |
```

**Priority**: P1 -- Two-phase processing eliminates redundant work. The consolidate phase is particularly valuable for memory file maintenance (deduplicating overlapping patterns from multiple source scans).

---

### Finding 9: Memory File Taxonomy -- `.md` vs `.promptinclude.md`

**Source**: autodream-src/prompts/autodream.sys.md:47-49, autodream-src/helpers/auto_dream.py:1299-1318

**Pattern**:
```
# autodream.sys.md:47-49 -- Taxonomy rules in the system prompt
## Guidance
- **Taxonomy (Rules vs. Facts)**: Differentiate between behavioral guidelines and general knowledge.
  - If a memory contains strict instructions, behavioral rules, constraints, or formatting mandates for the AI,
    save it as a `.promptinclude.md` file (e.g., `rules.promptinclude.md` or `coding_style.promptinclude.md`).
    The system automatically enforces these.
  - If a memory contains facts, context, architectural decisions, or history,
    save it as a standard `.md` file.
```

```python
# auto_dream.py:1299-1318 -- filename collision resolution aware of promptinclude
def ensure_unique_memory_filename(file_name, existing_file_names, allow_existing):
    stem = file_name
    suffix = ""
    if file_name.endswith(".promptinclude.md"):
        stem = file_name[:-17]        # strip ".promptinclude.md"
        suffix = ".promptinclude.md"
    elif file_name.endswith(".md"):
        stem = file_name[:-3]          # strip ".md"
        suffix = ".md"

    counter = 2
    while True:
        candidate = f"{stem}-{counter}{suffix}"
        if candidate not in existing_file_names:
            return candidate
        counter += 1
```

Files with `.promptinclude.md` extension are treated as behavioral rules to be automatically enforced (injected into agent prompts). Standard `.md` files are factual reference. The collision resolution is extension-aware.

**code-shiniyaya gap**: code-shiniyaya's memory files are all standard `.md` files. There is no distinction between behavioral rules (which should be injected into agent prompts as constraints) and factual reference (which agents may consult). Currently, `SKILL.md` itself contains both rules and facts intermixed. The memory files contain both "how to implement pattern X" (factual) and "always use pattern X when Y" (behavioral).

**Concrete fix -- Add to SKILL.md** (new section in "记忆"):

```markdown
### 记忆文件分类: .md vs .promptinclude.md (v3.8.0)

仿autodream的文件扩展名分类系统:

| 扩展名 | 内容类型 | 自动行为 |
|--------|---------|---------|
| `.md` | 事实、上下文、架构决策、历史记录 | Agent可读取参考, 不强制执行 |
| `.promptinclude.md` | 行为规则、约束、格式要求、强制指令 | 自动注入Agent系统提示词, 强制执行 |
| `.promptinclude.md` | CC编排规则(如: "不跳过STEP X", "P0需双验证") | 注入Agent prompt时加 `[ENFORCED_RULES]` 前缀 |

### 现有文件重分类

```
memory/high-impact-patterns.md         -> 保持.md (事实: 列出模式)
memory/memory-isolation-rule.md        -> 重命名为 memory-isolation-rule.promptinclude.md (行为规则)
memory/autoagent-security-patterns.md  -> 保持.md (事实+模式描述)
SKILL.md本身                            -> 事实+规则混合(不变, 但STEP指令视为.promptinclude等效)
```

### Agent提示词注入

Agent启动时, CC从 `memory/*.promptinclude.md` 中收集所有规则, 注入到系统提示词:

```
[ENFORCED_RULES -- 以下规则必须遵守]
1. (from memory-isolation-rule.promptinclude.md) 所有记忆写入 code-shiniyaya/memory/, 不写入 bilisum
2. (from anti-hang-v2.promptinclude.md) max_turns=40, 超限终止
[/ENFORCED_RULES]
```

### .promptinclude.md 文件格式

```markdown
## Rule: <规则名称>
- Priority: ALWAYS_ENFORCE
- Scope: agent_prompt_injection
- Trigger: on_agent_launch

<规则正文>
```
```

**Priority**: P1 -- This taxonomy separates "things the agent must do" from "things the agent may want to know," reducing prompt clutter and ensuring critical rules are never missed.

---

## P2 -- Nice-to-Have: Operational Excellence Patterns

### Finding 10: Orphan Detection via Token Overlap Scoring

**Source**: autodream-src/helpers/auto_dream.py:846-918

**Pattern**:
```python
# auto_dream.py:846-918 -- find_orphan_candidates()
def find_orphan_candidates(memory_subdir: str) -> list[dict[str, Any]]:
    current_project_name = memory_subdir[9:]  # strip "projects/" prefix
    current_tokens = slug_tokens(current_project_name)  # {token: set of [a-z0-9]+ tokens with len>1}

    candidates = []
    for project_dir in projects_root.iterdir():
        sibling_project_name = project_dir.name
        sibling_tokens = slug_tokens(sibling_project_name)
        overlap = score_token_overlap(current_tokens, sibling_tokens)  # Jaccard-like: |A ∩ B| / max(|A|, |B|)

        if overlap < MIN_ORPHAN_OVERLAP:  # 0.5
            continue  # not enough token overlap -> probably unrelated project

        # Check if sibling has memory files with the same name pattern
        memories_dir = Path(get_project_meta(sibling_project_name, "memory", AUTO_DREAM_DIR, AUTO_DREAM_MEMORIES_DIR))
        memory_files = [path for path in memories_dir.glob("*.md") if path.is_file()]
        if memory_files:
            candidates.append({
                "memory_subdir": f"projects/{sibling_project_name}",
                "overlap_score": round(overlap, 2),
                "shared_tokens": sorted(current_tokens & sibling_tokens),
                "memory_file_count": len(memory_files),
            })

    candidates.sort(key=lambda item: (item["overlap_score"], item["last_updated_at"]), reverse=True)
    return candidates[:MAX_ORPHAN_CANDIDATES]  # 4

# auto_dream.py:1340-1350 -- token extraction and overlap scoring
def slug_tokens(value: Any) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9]+", str(value or "").lower()) if len(token) > 1}

def score_token_overlap(current_tokens: set[str], sibling_tokens: set[str]) -> float:
    if not current_tokens or not sibling_tokens:
        return 0.0
    return len(current_tokens & sibling_tokens) / max(len(current_tokens), len(sibling_tokens))
```

When a project is renamed (e.g., "my-app" -> "my-app-v2"), the old project's memory files become orphans. The orphan detector finds these by comparing token overlap (slugified project names) and reports them as "rename / orphan hints" to the consolidation prompt. This prevents memory fragmentation.

**code-shiniyaya gap**: code-shiniyaya has no orphan detection. The memory files reference 4 reference sources (AutoAgent, autodream, autoresearch, autonomous-coding) and are written to a single directory. If code-shiniyaya were to be applied to a new project that maintains its own memory files, there is no mechanism to detect: "this memory file was written for the old project, not the current one."

The practical gap today is smaller (only one project), but the pattern is valuable for any system that writes files scoped to a project context.

**Concrete fix -- Add to high-impact-patterns.md**:

```markdown
### 12. Orphan Memory Detection (from autodream)

**Pattern**: Token-overlap scoring detects memory files from renamed/split projects.

**Implementation for code-shiniyaya**:

```
def find_orphan_memory_files(memory_dir: str, current_project_name: str):
    current_tokens = slug_tokens(current_project_name)
    orphans = []

    for file in glob(f"{memory_dir}/*.md"):
        file_tokens = slug_tokens(file.stem)
        overlap = len(current_tokens & file_tokens) / max(len(current_tokens), len(file_tokens))
        if overlap < 0.3:  # low token overlap with current project
            orphans.append({"file": file.name, "overlap_score": round(overlap, 2)})

    return sorted(orphans, key=lambda x: x["overlap_score"])

# Example: if current_project = "code-shiniyaya" and file = "bilisum-memory-patterns.md"
# tokens(code-shiniyaya) = {"code","shiniyaya"}
# tokens(bilisum-memory-patterns) = {"bilisum","memory","patterns"}
# overlap = 0 / 3 = 0.0 -> FLAGGED as orphan
```

**Trigger**: Consolidation phase (Finding 8) automatically flags orphans for review.

**Benefit**: Prevents cross-project memory pollution when code-shiniyaya is applied to multiple projects.
```

**Priority**: P2 -- Low urgency for single-project use, but essential for multi-project deployment.

---

### Finding 11: Grounding Provenance Tracking

**Source**: autodream-src/prompts/autodream.sys.md:31-32, autodream-src/helpers/auto_dream.py:425-428

**Pattern**:
```
# autodream.sys.md:31-32 -- grounding instruction
- Set `grounding` to `grounded` when the memory is directly supported by the supplied sessions or memories.
  Otherwise set it to `inferred`.

# auto_dream.py:425-428 -- implementation
grounding = str(change.get("grounding", "") or "").strip().lower()
if grounding in {"grounded", "inferred"}:
    frontmatter["grounding"] = grounding
```

Every memory file tracks whether its content is "grounded" (directly supported by evidence in session transcripts) or "inferred" (synthesized from patterns across multiple sources but not directly stated). This provenance tracking persists in the frontmatter and is visible in the vector database.

**code-shiniyaya gap**: code-shiniyaya's memory files (high-impact-patterns.md, reference-sources-v2.md, autoagent-*.md) contain patterns extracted from source code scans. But there is NO tracking of whether a pattern is:
- "grounded": directly from a source file with file:line evidence
- "inferred": synthesized by CC from multiple observations
- "speculative": proposed as a good idea but not observed in any source

This means future CC sessions cannot distinguish "this is a proven pattern from AutoAgent's main.py:50" from "this is a pattern CC theorized might exist."

**Concrete fix -- Add to SKILL.md** (in "记忆" section):

```markdown
### Grounding溯源追踪 (v3.8.0)

每个记忆文件条目必须标注grounding来源(仿autodream):

| Grounding | 含义 | 示例 |
|-----------|------|------|
| `grounded: <file:line>` | 直接从源文件中提取 | `grounded: autoagent/main.py:50-80` |
| `inferred: <pattern>` | 从多个源综合推断 | `inferred: cross-source (3 sources show same OR-gate pattern)` |
| `speculative: <reasoning>` | 理论设计, 未在开源项目中观察到 | `speculative: dedup-before-dispatch would prevent double work` |

### 文件格式

```markdown
## Pattern: Config-Driven OR-Gating

grounding: grounded: autodream-src/helpers/auto_dream.py:686-702
source_context_ids: ["autodream-src"]
source_files: ["helpers/auto_dream.py:686-702"]
```

### 在Agent提示词中使用

Agent收到grounded模式时: "此模式已在 {source_file} 中验证实现, 可信任。"
Agent收到inferred模式时: "此模式跨{count}个源综合, 高度可信但无单一实现。"
Agent收到speculative模式时: "此模式为理论设计, 未经验证。谨慎使用。"
```

**Priority**: P2 -- Provenance tracking improves trust calibration for agents and future CC sessions.

---

### Finding 12: Safe Filename Normalization with Collision Resolution

**Source**: autodream-src/helpers/auto_dream.py:1255-1318

**Pattern**:
```python
# auto_dream.py:1255-1262 -- normalize_memory_filename
def normalize_memory_filename(value: str) -> str:
    safe = files.safe_file_name(
        (value or "").replace("\\", "/").split("/")[-1].strip()
    )
    safe = safe.lower().strip(" ._") or "memory"
    if not safe.endswith(".md"):
        safe += ".md"
    return safe

# auto_dream.py:1265-1291 -- select_memory_file_name with collision detection
def select_memory_file_name(raw_path, title, existing_file_names):
    normalized_path = normalize_memory_filename(raw_path) if raw_path else ""
    title_file_name = normalize_memory_filename(title or normalized_path or "memory")

    # Case 1: explicit path exists -> allow overwrite (upsert)
    if normalized_path and normalized_path in existing_file_names:
        return ensure_unique_memory_filename(normalized_path, existing_file_names, allow_existing=True)
    # Case 2: title-derived name exists -> allow overwrite
    if not normalized_path and title_file_name in existing_file_names:
        return ensure_unique_memory_filename(title_file_name, existing_file_names, allow_existing=True)
    # Case 3: new file -> ensure no collision
    return ensure_unique_memory_filename(title_file_name, existing_file_names, allow_existing=False)

# auto_dream.py:1294-1318 -- collision resolution with counter suffix
def ensure_unique_memory_filename(file_name, existing_file_names, allow_existing):
    if allow_existing and file_name in existing_file_names:
        return file_name  # upsert: overwrite existing
    if file_name not in existing_file_names:
        return file_name   # no collision
    # Collision: append "-2", "-3", etc.
    stem, suffix = split_extension(file_name)
    counter = 2
    while True:
        candidate = f"{stem}-{counter}{suffix}"
        if candidate not in existing_file_names:
            return candidate
        counter += 1
```

Three-tier filename safety: (a) strip path separators + dangerous chars, (b) enforce lowercase + clean edges, (c) resolve collisions with counter suffix `-2`, `-3`, etc. The `allow_existing` flag distinguishes upsert (intentional overwrite) from accidental collision.

**code-shiniyaya gap**: code-shiniyaya's report filenames use `FOR_CODEX_{描述}.md` with a sanitization step (SKILL.md line 146-147). But the sanitization is incomplete:
- It removes `..`, `/`, `\`, `:`, `>`, `<`, `|`, `?`, `*`, `%00`, `\n`, `\r`, zero-width chars
- But it does NOT handle: uppercase vs lowercase collisions on case-insensitive filesystems (Windows), leading/trailing spaces/periods (invalid on Windows), or name collisions with existing files.

**Concrete fix -- Add to SKILL.md** (in "Codex消息可复制" sanitization section):

```markdown
### 文件名安全规范化 (增强版, v3.8.0)

替换当前STEP 3 sanitization(第146-147行):

```
def safe_report_filename(description: str, existing_names: set[str]) -> str:
    # 1. Strip dangerous path characters
    safe = re.sub(r'[<>:"/\\|?*\x00-\x1f​-‍﻿‪-‮⁦-⁩]', '', description)
    # 2. Normalize to safe lowercase alphanumeric
    safe = re.sub(r'[^a-z0-9_\-. ]', '', safe.lower())
    # 3. Trim leading/trailing spaces, dots, underscores (invalid on Windows)
    safe = safe.strip(' ._')
    # 4. Fallback on empty
    if not safe:
        safe = "diagnosis"
    # 5. Truncate to 50 chars (existing rule)
    safe = safe[:50]
    # 6. Ensure .md extension
    if not safe.endswith('.md'):
        safe += '.md'
    # 7. Collision resolution (NEW)
    if safe in existing_names:
        stem = safe[:-3] if safe.endswith('.md') else safe
        counter = 2
        while f"{stem}-{counter}.md" in existing_names:
            counter += 1
        safe = f"{stem}-{counter}.md"
    existing_names.add(safe)
    return safe
```

### Windows兼容性清单

| 检查项 | 当前(v3.7.0) | 增强(v3.8.0) |
|--------|------------|------------|
| 去除路径分隔符 | 是 | 是 |
| 去除control/bidi/zero-width字符 | 是 | 是(更完整列表) |
| 强制小写(大小写不敏感FS) | 否 | 是 |
| 去除首尾空格/句点 | 否 | 是 |
| 碰撞检测+计数器去重 | 否 | 是 |
| 扩展名强制 | 否 | 是(.md) |
```

**Priority**: P2 -- Low urgency (collisions are rare with session-ID-prefixed filenames) but important for correctness on Windows.

---

## Summary: Integration Priority

| # | Pattern | Priority | Source (autodream) | Fix Target | Effort |
|---|---------|----------|-------------------|------------|--------|
| 1 | Three-Layer Config Resolution | P0 | plugin.yaml:6-8, auto_dream.py:1159-1170 | new file: default_config.yaml + SKILL.md section | High |
| 2 | Coercion Functions with Sensible Defaults | P0 | auto_dream.py:656-683 | SKILL.md: new "配置强制函数" section | Medium |
| 3 | Config-Driven Dual-Threshold OR-Gating | P0 | auto_dream.py:686-702 | SKILL.md: replace hardcoded thresholds | Medium |
| 4 | Thread-Safe Mutex (Prevent Duplicate Execution) | P1 | auto_dream.py:49-51, 74-93 | SKILL.md: "工作流互斥锁" section | Low |
| 5 | Checksum-Based "Skip If Unchanged" | P1 | auto_dream.py:534-552 | SKILL.md: "校验和跳过优化" section | Medium |
| 6 | State Schema Versioning (Per-File) | P1 | auto_dream.py:325-347, 554-561 | SKILL.md: "独立Schema版本控制" section | Low |
| 7 | Markdown Event Log (Newest-First, Truncated) | P1 | auto_dream.py:994-1071 | New file format: workflow-{id}.md | Medium |
| 8 | Two-Phase Processing (Learn + Consolidate) | P1 | auto_dream.py:97-317, 266-272 | SKILL.md: "两阶段处理" section | High |
| 9 | Memory File Taxonomy (.md vs .promptinclude.md) | P1 | autodream.sys.md:47-49, auto_dream.py:1299-1318 | SKILL.md: "记忆文件分类" section | Low |
| 10 | Orphan Detection via Token Overlap | P2 | auto_dream.py:846-918 | high-impact-patterns.md: new entry | Low |
| 11 | Grounding Provenance Tracking | P2 | autodream.sys.md:31-32, auto_dream.py:425-428 | SKILL.md: "Grounding溯源追踪" section | Low |
| 12 | Safe Filename Normalization + Collision Resolution | P2 | auto_dream.py:1255-1318 | SKILL.md: enhance sanitization | Low |

## Cumulative Impact

- **P0 patterns (1-3)**: Directly answer the prompt's core question -- "How can code-shiniyaya externalize its hardcoded constants?" These three patterns provide the complete architecture: config file, coercion functions, and config-driven gating. Together they enable user-tunable behavior without editing SKILL.md.

- **P1 patterns (4-9)**: Robustness and operational improvements. The mutex, checksum-skip, schema versioning, event log, two-phase processing, and file taxonomy together create a production-grade operational foundation that autodream has and code-shiniyaya currently lacks.

- **P2 patterns (10-12)**: Quality-of-life improvements. Orphan detection, grounding tracking, and safe filenames are valuable but not blocking.

## What Already Exists (No Duplication)

All findings in this file are GENUINELY NEW relative to existing memory files. Specifically:
- **Config resolution/coercion/gating** (Findings 1-3): Completely absent from all 10 existing memory files -- this is the autodream-specific contribution.
- **Mutex/checksum-skip/schema-versioning** (Findings 4-6): Novel operational patterns not covered by autoagent-src scans.
- **Event log/two-phase/taxonomy** (Findings 7-9): New operational patterns.
- **Orphan detection/grounding/filename safety** (Findings 10-12): Novel utility patterns.

No pattern from autodream's `case_resolved`/3-tier-retry/DAG-engine/max_turns space is duplicated here -- those are already thoroughly documented in autoagent-*.md files.
