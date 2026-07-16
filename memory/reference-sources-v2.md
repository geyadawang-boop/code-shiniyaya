---
name: code-shiniyaya-reference-sources-v2
description: 4 new open-source reference projects (AutoAgent, autodream, autoresearch, autonomous-coding) added 2026-07-16 — 65 total patterns extracted across all sources
metadata:
  type: reference
  priority: highest
---

# code-shiniyaya — 开源参考源 v2

## 本次新增（2026-07-16）

| 项目 | 星数 | 核心贡献 | 总模式数 |
|------|------|---------|------|
| **AutoAgent** (HKUDS) | 9,468 | 事件驱动DAG引擎, Triage Hub-and-Spoke, 3-Tier重试升级 | 19 |
| **autodream** | 19 | LLM驱动合成, 双重代表记忆, 两阶段反思循环, grounding归因 | 19 |
| **autoresearch** (Karpathy) | 91,221 | Git-based状态机, 表格结果日志, 崩溃分类法, 固定预算 | 13 |
| **autonomous-coding** (Anthropic) | 17,248 | 两Agent编排, 不可变检查清单, ThinkTool, 轨迹记录 | 14 |

## 来源路径

- `C:\Users\shiniyaya\Desktop\code-shiniyaya\autoagent-src\`
- `C:\Users\shiniyaya\Desktop\code-shiniyaya\autodream-src\`
- `C:\Users\shiniyaya\Desktop\code-shiniyaya\autoresearch-src\`
- `C:\Users\shiniyaya\Desktop\code-shiniyaya\autonomous-coding-src\`

## Top-10 最高影响模式（跨源交叉验证）

多个源独立印证了相同模式：

| 模式 | 已验证来源 | P0影响 |
|------|------|------|
| **Agent编排 = Hub-and-Spoke** | AutoAgent + autonomous-coding | 两Agent模型（init+loop），transfer-back完成信号 |
| **Git作为状态机** | autoresearch + autonomous-coding | 提交=状态单元，保留/丢弃通过git reset |
| **不可变检查清单（仅翻转verified标志）** | autonomous-coding + autodream | 创建后永不修改——仅变更状态 |
| **崩溃分类法（琐碎 vs 根本性）** | autoresearch + autonomous-coding | 琐碎错误自动重试，根本性错误跳过 |
| **双重代表记忆（markdown + 向量）** | autodream + AutoAgent | Markdown是真实来源，向量是索引 |
| **LLM驱动的合成** | autodream + AutoAgent | 结构化JSON计划由LLM生成，非硬编码 |
| **事件驱动DAG + listen_group** | AutoAgent (独有) | 声明式步骤编排，自动并行扇出 |
| **两阶段反思（Learn + Consolidate）** | autodream (独有) | STEP 7后的元反思通道 |
| **固定预算作为趋同代理** | autoresearch (独有) | 每次扫描相同预算→直接可比较 |
| **轨迹记录用于调试** | autonomous-coding (独有) | JSONL每轮记录+提取的图片，时间戳目录 |

## 已弃用/已剪裁文件

防卡顿 v2.0 中以下文件已被 v2.1 替代：
- `time-escalation.md` — CronCreate-based，CC无计时器导致无法使用
- `progress-experience-design.md` — 假设CC可轮询，无法使用
- `progress-tracking.md` WIP部分 — 被anti-hang-v2.md中的内联log()模式替代

## 关联记忆

- [[bilisum-all-reference-sources]]
- [[bilisum-reference-import-registry]]
- [[bilisum-open-source-references]]
- [[code-shiniyaya-skill-state]]
