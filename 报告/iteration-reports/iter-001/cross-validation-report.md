# Cross-Validation Report — Iteration #1

**Generated**: 2026-07-16
**Source**: 20-Agent deep scan of 4 open-source reference projects
**Target**: code-shiniyaya SKILL.md v3.9.0
**Method**: Cross-validate journal.jsonl agent results against 5 existing memory analyses + SKILL.md v3.9.0 content

---

## 1. Scan Summary

| Source | Agents | Dimensions | Results |
|--------|--------|------------|---------|
| AutoAgent (HKUDS) | 5 | Handoff, Context, Event-DAG, Registry, Retry | 11 patterns |
| autodream | 5 | Memory/State, Reflection, Context, Config, Attribution | 18 patterns |
| autoresearch (Karpathy) | 5 | Git-State, Error-Class, Result-Log, Simplicity, Autonomy | 15 patterns |
| autonomous-coding (Anthropic) | 5 | Init+Loop, ThinkTool, Checklist, Error-Recovery, Safety | 14 patterns |
| **TOTAL** | **20** | **20 dimensions** | **58 raw findings** |

---

## 2. Cross-Validation Methodology

### 2.1 Validation Criteria

1. **Patterns confirmed in >=2 different source projects** = HIGHEST priority (P0)
2. **Single-source unique patterns** = lower priority (P1/P2)
3. **Patterns already in SKILL.md v3.9.0** = SKIP
4. **Patterns already documented in existing memory analyses with applied fixes** = SKIP (reference only)

### 2.2 Cross-Referenced Memory Files

| File | Patterns | Status |
|------|----------|--------|
| `memory/autoagent-gap-analysis.md` | 15 patterns | 4 P0 applied to v3.9.0; 11 P1/P2 documented but not applied |
| `memory/autodream-pattern-transfer.md` | 10 patterns | 0 applied to v3.9.0 (all memory-infra patterns) |
| `memory/autodream-context-patterns.md` | 10 patterns | 2 (MAX_* caps, truncate_for_prompt) applied to v3.9.0 |
| `memory/autoresearch-gap-analysis.md` | 9 patterns | 4 P0 applied to v3.9.0; 5 P1/P2 documented but not applied |
| `memory/autonomous-coding-gap-analysis.md` | 7 patterns | 2 (Init+Loop, Immutable Checklist) applied to v3.9.0; 5 not applied |
| `memory/staged-event-driven-patterns.md` | 11 patterns | Terminal signals + Handoff applied to v3.9.0; GOTO/ABORT not applied |
| `memory/high-impact-patterns.md` | 10 top patterns | Documented as reference; most core concepts present in v3.9.0 |
| `memory/autodream-grounding-attribution-findings.md` | 18 patterns | 0 applied to v3.9.0 (attribution infrastructure) |
| `memory/autoresearch-git-state-machine-findings.md` | 26 patterns | Core git-state applied to v3.9.0; auxiliary patterns not applied |

---

## 3. SKIP: Patterns Already in SKILL.md v3.9.0 (Criteria 3)

These 22 patterns are confirmed present in the current SKILL.md and should NOT be re-applied:

| # | Pattern | SKILL.md v3.9.0 Location | Cross-Validated By |
|---|---------|--------------------------|---------------------|
| SKIP-1 | workflow_context shared state bus | Lines 432-466 | AutoAgent + autonomous-coding |
| SKIP-2 | Agent HANDOFF protocol | Lines 389-401 | AutoAgent + autonomous-coding |
| SKIP-3 | TERMINAL signal protocol (RESOLVED/UNRESOLVED/PARTIAL) | Lines 413-430 | AutoAgent + autoresearch |
| SKIP-4 | STEP 4 MAX_* input caps (5 constants) | Lines 467-489 | autodream + AutoAgent |
| SKIP-5 | truncate_for_prompt (60/40 head-tail) | Lines 487-494 | autodream + AutoAgent |
| SKIP-6 | Git state machine STEP 6.0 | Lines 326-355 | autoresearch + autonomous-coding |
| SKIP-7 | fix-log TSV (fix-log-{sessionId}.tsv) | Lines 339-346 | autoresearch + autonomous-coding |
| SKIP-8 | Type A (trivial) / Type B (fundamental) crash classification | Lines 88-94 | autoresearch + autonomous-coding |
| SKIP-9 | Rule 15 iteration continuity (never stop mid-iteration) | Lines 98-107 | autoresearch + autonomous-coding |
| SKIP-10 | Iteration self-checks 1-11 | Lines 101-120 | (internal evolution) |
| SKIP-11 | Init+Loop two-phase iteration model | Lines 585-591 | autonomous-coding + AutoAgent |
| SKIP-12 | scan-plan immutable checklist (verified flag only) | Lines 593-594 | autonomous-coding + autodream |
| SKIP-13 | Session JSON SHA-256 checksum + atomic write | Lines 156-165 | autodream + autonomous-coding |
| SKIP-14 | CTX_UPDATE security whitelist | Lines 456-465 | AutoAgent + autodream |
| SKIP-15 | 3-tier retry escalation table | Lines 70-79 | AutoAgent + autoresearch |
| SKIP-16 | Agent handoff quotas (1/agent, 2/target/batch) | Lines 403-405 | AutoAgent |
| SKIP-17 | WORKFLOW_LOG via workflow_context + journal.jsonl | Lines 432-466 | AutoAgent + autodream |
| SKIP-18 | Iteration convergence tracking (CR formula) | Line 612 | autoresearch |
| SKIP-19 | Dual-threshold OR-gating (N=4/N=5 silent) | Lines 36, 63-64 | autodream + autonomous-coding |
| SKIP-20 | Byzantine Codex defense (fake file:line detection) | Lines 313-314 | (internal evolution) |
| SKIP-21 | Agent output header (AGENT: {id}:{type}:{ts}) | Lines 439-456 | AutoAgent |
| SKIP-22 | STEP 3 sanitization pipeline (5-stage) | Lines 291-297 | (internal evolution) |

---

## 4. HIGHEST PRIORITY (P0): Patterns Confirmed in >=2 Sources, NOT in SKILL.md v3.9.0

### P0-1: Post-Workflow Meta-Reflection (STEP 8: Learn + Consolidate)

**Confirmed by**: autodream (two-phase Learn+Consolidate dream loop, `auto_dream.py:97-317`) + autonomous-coding (Init creates checklist, Loop executes with fresh context, `agent.py:97-207`)

**Gap**: After STEP 7 completes, the workflow ends. No post-hoc reflection synthesizes what was learned into durable knowledge. The next time a similar bug appears, the same diagnosis work repeats from scratch.

**Fix text for SKILL.md** (new section after STEP 7):

```markdown
## STEP 8 -- 工作流后元反思 (v4.0.0)

STEP 7完成后, 自动运行反思, 将本工作流的发现合成为持久知识。

### 触发条件 (双门控, OR逻辑)
- 门控A: 距上次反思 >= `reflection_min_hours` 小时 (默认 8)
- 门控B: 累计完成 >= `reflection_min_workflows` 个工作流 (默认 3)
- 首次运行 (last_reflection_at is None): 立即触发

### Phase 1: Learn — 从本工作流提取新记忆

**输入** (注入LLM): workflow_context_bus 快照 (diagnosis + plan + codex + execution + meta), 现有记忆文件 (最多24个, 每个≤2500字符, 60/40截断), MEMORY.md 索引 (≤6000字符)

**LLM输出** (JSON, DirtyJson容错解析):
```json
{
  "summary": "本工作流修复了2个P0空指针和1个P1竞态条件...",
  "changes": [
    {"action": "upsert", "path": "null-pointer-init-order.md", "title": "...", "description": "...", "content": "...", "grounding": "grounded", "source_context_ids": ["a1b2c3d4"], "source_first_prompts": ["..."], "source_memory_ids": ["..."]},
    {"action": "delete", "path": "stale-guide.md", "reason": "被新文件完全覆盖"}
  ]
}
```

### Phase 2: Consolidate — 周期性合并去重

**触发**: 每 `consolidate_every_n_workflows` 个 Learn-only 反思后 (默认 3, 0=禁用)
**输入**: 所有现有记忆文件 (不包含session数据, 仅文件列表)
**LLM**: "只合并语义重叠的文件, 强制删除冗余文件。仅合并和修剪已有内容, 不创造新知识。"

### 反思日志 (.reflection-log.md)
每次反思追加一条记录 (最新在前, 最多40条): timestamp, summary, scope, phase, inputs, created/updated/pruned 列表

### 并发防护
`_REFLECTION_SCOPES` set + 线程锁: 同范围同时最多一个反思运行。排队槽位: 1。
```

**Priority**: P0 | **Effort**: High | **Files**: SKILL.md (new STEP 8 section)

---

### P0-2: Grounding/Attribution Tracking Per Finding

**Confirmed by**: autodream (grounded vs inferred, source_context_ids, source_first_prompts, `auto_dream.py:425-448`) + AutoAgent (sender tag in messages, agent source tracking, `core.py:323,437,621`)

**Gap**: Agent findings in STEP 1/4 carry only severity (P0/P1/P2) with no provenance declaration. Cannot distinguish direct observation from agent hallucination. Merged findings lose source agent identity.

**Fix text for SKILL.md** (add to STEP 1 dedup section):

```markdown
### Agent Finding Provenance (STEP 1.4, P0强制)

每个 finding MUST 包含:

```json
{
  "severity": "P0",
  "file": "src/auth.py",
  "line": 42,
  "description": "Null pointer dereference in authenticate()",
  "grounding": "grounded",
  "evidence": "Line 42: user = get_user(); Line 43: user.name — user may be None",
  "inference_chain": null,
  "source_agent_ids": ["a1b2c3d4"],
  "source_agent_types": ["investigator"]
}
```

**grounding 取值**:
- `grounded`: 直接从源文件/日志/测试输出中观察到。必须含 `evidence` 字段 (精确引文或行号)
- `inferred`: 从模式/启发式推断, 无直接观察。必须含 `inference_chain` (推理路径)
- `partial`: 部分证据存在但关键假设未验证。同时含 `evidence` + `inference_chain`

**合并时 grounding 继承**: 任一 agent 含 grounded → 合并后 = grounded (含所有 agent evidence 并集); 全部 inferred → 合并后 = inferred

**grounding=null**: 拒绝该 agent 输出, 要求重新提交

**STEP 4 Codex 验证**: Codex "Bug X已修复" 含 grounding=grounded → 检查证据引用真实文件/行号; Codex 含 grounding=inferred 或不含 grounding → 该项 Gate FAIL (Byzantine Codex defense)
```

**Priority**: P0 | **Effort**: Medium | **Files**: SKILL.md (STEP 1.4, STEP 4)

---

### P0-3: Three-Layer Safety/Sandbox Model

**Confirmed by**: autonomous-coding (Layer 1 sandbox + Layer 2 permissions + Layer 3 bash hooks, `client.py:50-85`, `security.py:15-41`) + AutoAgent (sandbox enable, `autoAllowBashIfSandboxed`)

**Gap**: SKILL.md's `permissions` metadata (`file-read: true, shell: true`) is declarative, not enforced. No bash command allowlist, no compound command parsing defense, no OS-level filesystem sandboxing, no per-command extra validation for sensitive operations.

**Fix text for SKILL.md** (new section in Agent Orchestration):

```markdown
## Agent Safety — Three-Layer Defense (v4.0.0)

### Layer 1 — Sandbox (OS-Level)
- 所有子 Agent 启用 sandbox 模式 (如平台支持)
- Sandbox 防止文件系统逃逸, 即使 shell 权限被授予
- `autoAllowBashIfSandboxed: true`

### Layer 2 — Permissions (Filesystem)
- 文件操作限制在项目目录: `Read(./**), Write(./**), Edit(./**)`
- 绝不授予自主 Agent `Read(/**)` 或 `Write(/**)`
- Bash 仅在 Layer 3 hooks 有效时授予

### Layer 3 — Security Hooks (Bash Allowlist)

**最低允许命令集**:
```
ls, cat, head, tail, wc, grep  (文件检查)
cp, mkdir                        (文件操作, sandbox+permissions内安全)
pwd                              (导航)
npm, node, npx, python, pip, uv  (开发工具)
git                              (版本控制)
ps, lsof, sleep                  (进程管理, 需额外验证)
```

**敏感命令额外验证**:
- `rm`: 完全禁止 (Agent 不应删除文件; 用 git 清理)
- `pkill`/`kill`: 仅允许杀 dev 相关进程 (node, npm, vite, next, python)
- `chmod`: 仅允许 `+x` (脚本执行权限), 禁止递归

**复合命令防御**: 解析 `&&`, `||`, `;` 命令链, **每段独立验证**。任一段不通过 → 整条命令阻断。解析失败 (畸形命令) → 阻断 (fail-safe)。

**实现模板**: 参考 `autonomous-coding-src/autonomous-coding/security.py` — `extract_commands()`, `split_command_segments()`, `bash_security_hook()`
```

**Priority**: P0 | **Effort**: Medium | **Files**: SKILL.md (new section)

---

### P0-4: Fixed Budget Enforcement Per Severity Tier

**Confirmed by**: autoresearch (TIME_BUDGET=300 on prepare.py, 10-min timeout kill on program.md:108) + autonomous-coding (max_iterations bound on agent.py:149-153)

**Gap**: SKILL.md has agent-cap=50 (resource limit, not a budget). No per-severity allocation, no consumption tracking, no threshold-based actions. A P2 cosmetic fix consuming 8 agent launches is treated identically to a P0 crash fix using 1 launch.

**Fix text for SKILL.md** (add to 状态文件 section):

```markdown
### 修复预算 (`budget-{sessionId[:8]}.json`) (v4.0.0)

```json
{
  "total": {"agent_launches": 50, "fix_attempts_per_bug": 5, "message_rounds": 200},
  "consumed": {"agent_launches": 12, "fix_attempts": {"B1": 2, "B2": 1}},
  "by_severity": {
    "P0": {"budget_pct": 60, "consumed": 8},
    "P1": {"budget_pct": 30, "consumed": 4},
    "P2": {"budget_pct": 10, "consumed": 0}
  }
}
```

| 消耗率 | 动作 |
|--------|------|
| <50% | 正常 |
| 50-75% | 日志警告, P2 降级 |
| 75-90% | 停止新 P2, P1 限制 1 次尝试 |
| >90% | 仅 P0, 所有修复升级到 Tier 2 |

降级模式: P0 预算从 60% 增加到 80% (CC 自我验证更昂贵)。预算消耗 >90% 且 Codex 不可用: BREAK_GLASS 允许超支 10%, 仅 P0。
```

**Priority**: P0 | **Effort**: Medium | **Files**: SKILL.md (状态文件 section)

---

### P0-5: First-Completed Dispatch (Streaming Step Transition)

**Confirmed by**: AutoAgent (flow/core.py:153-175 — `asyncio.FIRST_COMPLETED`, process results as each task finishes) + autonomous-coding (Init triggers Loop without waiting for all agents)

**Gap**: SKILL.md's STEP 1 launches 6+ agents, waits for ALL to complete before dedup/STEP 2. STEP 4 launches 10+ agents, waits for ALL before STEP 5. Critical path gated by slowest agent (P50=116s, max=600s). No incremental processing.

**Fix text for SKILL.md** (add to 迭代扫描工作流 section):

```markdown
### First-Completed Dispatch (Streaming Step Transition) (v4.0.0)

**代替**: Launch N agents → wait ALL → process → next step
**使用**: Launch N agents → process each as it completes → trigger downstream incrementally

**STEP 1 实现**:
1. Launch 6+ agents 并行
2. 每个 agent 返回时 (log() event):
   a. 即时提取 findings
   b. 对已收到 findings 去重 (同一 file:line±3)
   c. 若发现 P0 crash → 立即开始 STEP 2 方案生成 (不等剩余 agents)
3. 所有 agents 返回且无新 P0 → 等待落后检测 (3-message gap, anti-hang-v2.md)

**STEP 4 实现**:
1. Launch 10+ agents 跨 7 维度
2. 每个维度首个 agent 返回 → 标记该维度 "已覆盖"
3. 任一个维度证伪 Codex 声明 → 立即标记 "Codex Gate FAIL"
4. 不等待剩余维度 — Byzantine Codex defense 在首次证伪时触发

**收益**: 6-agent batch P50=116s 时, 首次完成分发允许 orchestrator 在 ~120s 开始 STEP 2, 而非 ~600s, 关键路径延迟降低 5 倍。
```

**Priority**: P0 | **Effort**: Medium | **Files**: SKILL.md (迭代扫描工作流 section)

---

## 5. HIGH PRIORITY (P1): Single-Source Unique Patterns

### P1-1: Trajectory Recording JSONL Format

**Source**: autonomous-coding (trajectory.py:20-61, loop.py:372-501)
**Gap**: No standardized per-turn conversation recording. journal.jsonl captures only agent results (`type: "result"`), not full user+assistant+tools transcript.

**Fix**: Add `runs/{iso-ts}-{sessionId[:8]}/transcript.jsonl` specification — one JSON object per turn with `role` + `content`, `meta.json` with model/task/timing, `system_prompt.md` copy.

**Priority**: P1 | **Effort**: Medium | **Files**: SKILL.md (Agent编排 section)

---

### P1-2: Orphan Candidate Detection (Token Overlap)

**Source**: autodream (find_orphan_candidates, auto_dream.py:846-918) — cross-project memory leakage detection via Jaccard-like token overlap scoring, threshold 0.5
**Confirmed by**: autonomous-coding (cross-session fingerprinting concept)

**Fix**: Add token-overlap detection in Consolidation phase: `score = |tokens1 ∩ tokens2| / max(|tokens1|, |tokens2|)`, threshold ≥0.5 flags potential-duplicate pair. Present top-4 candidates to Consolidation LLM.

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (STEP 8 Consolidation)

---

### P1-3: Memory File Checksum Idempotent Writes

**Source**: autodream (auto_dream.py:534-541 — MD5 checksum skip; auto_dream.py:459-465 — previous != rendered detection)
**Confirmed by**: SKILL.md's own session JSON SHA-256 protocol (same concept, different target)

**Fix**: Extend atomic write + checksum protocol from session JSON to all memory/*.md files. Write前: MD5 hash → 对比 memory-checksums.json → hash匹配 → 跳过写入 (已最新). hash不匹配 → os.replace 原子写入.

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (记忆 section), memory-checksums.json

---

### P1-4: Standardized Memory File Frontmatter Schema

**Source**: autodream (auto_dream.py:418-448 — comprehensive YAML frontmatter: title, description, updated_at, memory_scope, grounding, source_context_ids, source_first_prompts, source_memory_ids, canonical_scope_name, project_title)

**Fix**: All memory/*.md files MUST include: `title`, `description`, `updated_at` (ISO 8601 UTC, auto-updated), `memory_scope`, `grounding` (grounded|inferred|mixed), `source_sessions`, `pattern_count`, `schema_version`. Auto-populate `updated_at` on each write.

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (记忆 section), all memory/*.md files

---

### P1-5: Memory Taxonomy — Rules (.promptinclude.md) vs Facts (.md) vs History (.history.md)

**Source**: autodream (autodream.sys.md:47-49 — `.promptinclude.md` for behavioral rules/constraints auto-enforced; `.md` for facts/context)

**Fix**: Three-tier extension-based taxonomy:
- `.promptinclude.md`: Hard rules, constraints, behavioral guidelines → auto-injected into every agent system prompt
- `.md`: Facts, patterns, architecture, context → semantic retrieval only
- `.history.md`: Change records, audit trails → debug-only access

Migration: `memory-isolation-rule.md` → `.rules.md`, `high-impact-patterns.md` → `.patterns.md`, `cleanup-verification.md` → `.history.md`

**Priority**: P1 | **Effort**: Medium | **Files**: SKILL.md (记忆 section), all memory/*.md

---

### P1-6: Auto-Index Regeneration (MEMORY.md from Frontmatter)

**Source**: autodream (render_memory_index, auto_dream.py:921-944 — index regenerated from file frontmatter after every dream run, sorted by updated_at DESC, line_limit capped)

**Fix**: After every memory file write, auto-rebuild `memory/MEMORY.md`: glob `memory/*.md` → parse frontmatter → sort by updated_at DESC, title ASC → render `- [title](file): description` list → cap at 120 lines → append hidden count if truncated.

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (记忆 section)

---

### P1-7: Memory Scope Isolation Between Projects

**Source**: autodream (resolve_memory_subdir, auto_dream.py:1187-1191 — `projects/{project_name}` scoping, project_memory_isolation config)

**Fix**: Add `memory_scope` field to all memory files. Directory structure: `memory/scopes/_global/` (cross-project, meta-orchestration) + `memory/scopes/{project_slug}/` (per-project). Write to wrong scope → log warning, don't block.

**Priority**: P1 | **Effort**: Medium | **Files**: SKILL.md (记忆 section)

---

### P1-8: GOTO/ABORT Dynamic Flow Control

**Source**: AutoAgent (flow/dynamic.py:9-18 — ReturnBehavior.GOTO jumps to target event group, ReturnBehavior.ABORT terminates entire DAG)

**Fix**: Extend TERMINAL protocol:
- `TERMINAL: GOTO STEP_{N} | {reason}` — Agent signals downstream steps unnecessary, orchestrator skips to target step
- `TERMINAL: ABORT | {reason}` — Agent detects unfixable condition, orchestrator stops all agents, writes ABORT_LOG.md

Safeguards: GOTO forward-only (target_step > current_step). ABORT requires user confirm (unless P0 security issue).

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (TERMINAL protocol extension)

---

### P1-9: ThinkTool Reasoning Space Pattern

**Source**: autonomous-coding (think.py:1-32 — zero-side-effect reasoning tool, structured thought parameter, prevents impulsive tool calls)

**Fix**: Add prompt-level Think pattern (CC agents cannot define custom tools): `[THINK]\nGoal: ...\nExpected: ...\nRisk: ...\nSuccess: ...\n[/THINK]` block mandatory before any tool call. Persists in conversation history, survives context truncation.

**Priority**: P1 | **Effort**: Low | **Files**: SKILL.md (Agent prompt template)

---

### P1-10: Prompt Structure Constraint Enforcement Template

**Source**: autonomous-coding (coding_prompt.md — 10-step structure with severity labels MANDATORY/CRITICAL/CAREFULLY!, NEVER rules, DO/DON'T blocks, forced orientation step, pre-work verification gate, clean exit protocol)

**Fix**: Standardized agent prompt template:
1. Role declaration (identity + key constraint)
2. STEP 1: GET YOUR BEARINGS (MANDATORY) — forced disk reads
3. STEP 2: VERIFY EXISTING WORK (CRITICAL!) — pre-work regression gate
4. STEP 3: CHOOSE ONE TASK — single-task focus
5. STEP 4: IMPLEMENT + VERIFY — evidence-gated
6. STEP 5: UPDATE CHECKLIST (CAREFULLY!) — restricted mutation
7. STEP 6: COMMIT + UPDATE PROGRESS
8. STEP 7: END SESSION CLEANLY — explicit pre-termination checklist

**Priority**: P1 | **Effort**: Medium | **Files**: SKILL.md (Agent编排 section)

---

### P1-11: Fresh-Session Error Recovery Model

**Source**: autonomous-coding (agent.py:169-181 — each iteration gets fresh ClaudeSDKClient, error status → retry with fresh session, 3s fixed delay)
**Gap identified**: No recoverable/unrecoverable error classification, no exponential backoff, no empty-response detection. All exceptions funneled into identical `"error"` status.

**Fix**: Add fresh-session-per-iteration model: create new client per loop iteration → prevents accumulated context corruption. Recovery state = disk (checklist.json + progress.txt + git log), not memory. No complex JSON state file parsing needed for simple recovery.

Also add: empty-response detection (response_text="" → nudge "Your response was empty. Please provide output." + retry, max 2 consecutive).

**Priority**: P1 | **Effort**: Medium | **Files**: anti-hang-v2.md (new section)

---

### P1-12: Bash Command Allowlist with Compound Command Parsing

**Source**: autonomous-coding (security.py:15-41, 297-359 — ALLOWED_COMMANDS set, COMMANDS_NEEDING_EXTRA_VALIDATION set, compound command splitting on `&&`/`||`/`;`)

**Fix**: See P0-3 (Three-Layer Safety Model) — this is the implementation detail for Layer 3 of that model.

**Priority**: P1 | **Effort**: Low (reference implementation exists) | **Files**: SKILL.md (Layer 3 of P0-3)

---

## 6. LOWER PRIORITY (P2): Single-Source Patterns

| # | Pattern | Source | Fix Summary |
|---|---------|--------|-------------|
| P2-1 | Background-task async memory writes | autodream (DeferredTask, auto_dream.py:74-94) | Queue memory writes to `.queued/` dir, background agent applies, main flow continues |
| P2-2 | Reflection log with rotation | autodream (append_auto_dream_log, auto_dream.py:994-1018) | `.reflection-log.md` — newest-first, max 40 entries, auto-rotate |
| P2-3 | Consolidation counter | autodream (dreams_since_consolidation, auto_dream.py:266-271) | `workflows_since_consolidation` in reflection-state.json, triggers at N=3 |
| P2-4 | Session transcript pre-summarization | autodream (utility model summarization, auto_dream.py:142-149) | Summarize workflow transcripts >4000 chars via utility model before feeding to reflection LLM |
| P2-5 | Token-aware sliding-window context truncation | autonomous-coding (history_util.py:69-111) | When >80% context: remove oldest message pairs, inject "[Earlier history truncated.]" |
| P2-6 | Empty-response detection | autonomous-coding (loop.py:431-446) | Detect agent returning "" → nudge "please continue" + retry, max 2 consecutive |
| P2-7 | Redirect-all anti-flood | autoresearch (program.md:99) | Route agent stdout/stderr to `.log` file, grep extract only needed metrics |
| P2-8 | Output redirection + grep extraction | autoresearch (program.md:99-100) | `> run.log 2>&1` then `grep` for metrics — context never flooded with raw logs |
| P2-9 | Single-file edit constraint | autoresearch (program.md:26-27) | Single fix modifies max 1 file (unless DAG-declared cross-file dependency) |
| P2-10 | Simplicity criterion as decision gate | autoresearch (program.md:37) | "Small improvement adding complexity = reject. Simplification with equal/better result = keep." |
| P2-11 | Config-driven coercion functions | autodream (coerce_min_hours, coerce_min_sessions) | Type-safe config parsing with defaults for all runtime parameters |
| P2-12 | Index-content separation pattern | autodream (MEMORY.md vs memory files) | Findings INDEX.md (max 80 lines, metadata only) + per-finding content files in dimension subdirs |
| P2-13 | Memory state lifecycle | autodream (state.json + vector_state.json schema versioning) | `memory/state.json` tracking: schemaVersion, lastUpdateAt, referenceSourcesIngested, consolidationDue |
| P2-14 | Cross-project memory orphan detection | autodream (find_orphan_candidates, auto_dream.py:846-918) | Token overlap ≥0.5 across sibling project memory dirs → hint user |

---

## 7. FINAL_PRIORITY_LIST — Implementation Order

### Phase 1: P0 (multi-source confirmed, apply immediately)

| ID | Pattern | SKILL.md Section | Exact Lines to Add |
|----|---------|-----------------|---------------------|
| FIX-01 | Post-workflow meta-reflection (STEP 8: Learn+Consolidate) | After STEP 7 (after line 384) | Full STEP 8 section (~200 lines) |
| FIX-02 | Grounding/attribution per finding | STEP 1.4 dedup merge section | `grounding` field spec + merge rules (~50 lines) |
| FIX-03 | Three-layer safety/sandbox model | After Agent编排 table | New "Agent Safety" section (~80 lines) |
| FIX-04 | Fixed budget enforcement per severity | After 状态文件 section | budget-{sessionId}.json spec + threshold actions (~60 lines) |
| FIX-05 | First-completed dispatch (streaming) | 迭代扫描工作流 section | Streaming dispatch logic for STEP 1 + STEP 4 (~70 lines) |

### Phase 2: P1 (single-source high impact, apply in next iteration)

| ID | Pattern | Target |
|----|---------|--------|
| FIX-06 | Trajectory recording JSONL format | SKILL.md Agent编排 section |
| FIX-07 | Orphan candidate detection (token overlap) | SKILL.md STEP 8 Consolidation |
| FIX-08 | Memory file checksum idempotent writes | SKILL.md 记忆 section |
| FIX-09 | Standardized memory frontmatter schema | SKILL.md 记忆 section + all memory/*.md |
| FIX-10 | Memory taxonomy (.promptinclude.md vs .md) | SKILL.md 记忆 section |
| FIX-11 | Auto-index regeneration (MEMORY.md) | SKILL.md 记忆 section |
| FIX-12 | Memory scope isolation | SKILL.md 记忆 section |
| FIX-13 | GOTO/ABORT flow control | SKILL.md TERMINAL protocol |
| FIX-14 | ThinkTool reasoning pattern | SKILL.md Agent prompt template |
| FIX-15 | Prompt structure constraint template | SKILL.md Agent编排 section |
| FIX-16 | Fresh-session error recovery | anti-hang-v2.md |

### Phase 3: P2 (single-source, lower urgency)

| ID | Pattern | Target |
|----|---------|--------|
| FIX-17 | Background async memory writes | SKILL.md 记忆 section |
| FIX-18 | Reflection log with rotation | SKILL.md STEP 8 |
| FIX-19 | Consolidation counter | SKILL.md STEP 8 |
| FIX-20 | Session transcript pre-summarization | SKILL.md STEP 8 |
| FIX-21 | Token-aware context truncation | anti-hang-v2.md |
| FIX-22 | Empty-response detection | anti-hang-v2.md |
| FIX-23 | Redirect-all anti-flood | SKILL.md Agent编排 |
| FIX-24 | Output redirection + grep extraction | SKILL.md Agent编排 |
| FIX-25 | Single-file edit constraint | SKILL.md STEP 6 |
| FIX-26 | Simplicity criterion | SKILL.md Agent编排 |
| FIX-27 | Config coercion functions | SKILL.md 配置 section |

---

## 8. Cross-Reference Verification Matrix

| New Pattern | autoagent-gap-analysis | autodream-pattern-transfer | autodream-context-patterns | autoresearch-gap-analysis | autonomous-coding-gap-analysis | staged-event-driven | autodream-grounding |
|-------------|----------------------|---------------------------|---------------------------|--------------------------|-------------------------------|---------------------|---------------------|
| FIX-01 (STEP 8) | - | Finding 1,2,3 | Pattern 6,8 | - | - | - | P0-1, P0-2 |
| FIX-02 (Grounding) | P1-4 (sender tag) | Finding 4 | - | - | - | - | Finding 1,2,3,4 |
| FIX-03 (Safety) | - | - | - | - | Dimension 6 (P0) | - | - |
| FIX-04 (Budget) | - | - | - | P1 (TIME_BUDGET) | - | - | - |
| FIX-05 (Streaming) | P0-4 (DAG engine) | - | - | - | Dimension 1 (Init+Loop) | Finding 3 | - |
| FIX-06 (Trajectory) | - | - | - | P0 (results.tsv) | Dimension 4 | - | - |
| FIX-07 (Orphan) | - | Finding 10 | Pattern 9 | - | - | - | P1-3 |
| FIX-08 (Checksum) | - | Finding 1 | Pattern 5 | - | - | - | P0-3 |
| FIX-09 (Frontmatter) | - | Finding 5 | - | - | - | - | P1-4 |
| FIX-10 (Taxonomy) | - | Finding 9 | - | - | - | - | P1-1 |
| FIX-11 (Auto-Index) | - | - | Pattern 3 | - | - | - | P0-4 |
| FIX-12 (Scope) | - | Finding 6 | - | - | - | - | - |
| FIX-13 (GOTO) | P0-4 (flow control) | - | - | - | - | Finding 7 | - |
| FIX-14 (ThinkTool) | - | - | - | - | Dimension 3 | - | - |
| FIX-15 (Prompt) | - | - | - | - | Dimension 7 | - | - |
| FIX-16 (FreshSession) | - | - | - | - | Dimension 5 | - | - |

---

## 9. Statistics

| Metric | Count |
|--------|-------|
| Total raw agent findings | 58 |
| Patterns already in SKILL.md v3.9.0 (SKIPPED) | 22 |
| Patterns in existing memory analyses (documented, not applied) | 31 |
| **NEW unimplemented patterns to apply** | **27** |
| P0 (multi-source confirmed) | 5 |
| P1 (single-source high impact) | 11 |
| P2 (single-source lower urgency) | 11 |
| Multi-source confirmed (>=2 sources) | 12 |
| Single-source unique | 15 |

---

## 10. Memory Files Requiring Updates

After applying fixes, these memory files need synchronization:

| File | Action |
|------|--------|
| `memory/high-impact-patterns.md` | Add grounding/attribution fields to all patterns (FIX-02); update pattern #7 with STEP 8 details |
| `memory/autodream-pattern-transfer.md` | Mark Findings 1-5 as "applied to v4.0.0" after FIX-08/09/10 applied |
| `memory/autodream-context-patterns.md` | Mark Pattern 3 (index-content separation) as "applied to v4.0.0" after FIX-12 |
| `memory/autoresearch-gap-analysis.md` | Mark P1 budget enforcement as "applied to v4.0.0" after FIX-04 |
| `memory/autonomous-coding-gap-analysis.md` | Mark Dimensions 3,4,5,6,7 as "applied to v4.0.0" after Phase 2 |
| `memory/staged-event-driven-patterns.md` | Mark Finding 7 (GOTO/ABORT) as "applied to v4.0.0" after FIX-13 |
| `memory/MEMORY.md` | Auto-regenerated after FIX-11 |
| `memory/state.json` | NEW FILE — created after FIX-01 (STEP 8 first run) |
| `memory/.reflection-log.md` | NEW FILE — created after first reflection run |
| `memory/memory-checksums.json` | NEW FILE — created after FIX-08 |
| `memory/iteration-task.md` | Update "当前状态" to reflect v4.0.0 target |
