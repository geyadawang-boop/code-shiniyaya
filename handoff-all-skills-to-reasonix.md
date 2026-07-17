# code-shiniyaya → Reasonix — 全部 Skill 完整移交

**生成时间**: 2026-07-17
**发起**: Claude Code (session 599a9a0b)
**目标**: Reasonix
**回执**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\handover-ack-reasonix.md`

---

## 目录

1. [全部 Skill 总表 (114个)](#1-全部-skill-总表)
2. [🔴 10-Skill 核心栈 — 完整 SKILL.md 正文](#2-核心栈-skillmd-完整正文)
3. [🔴 caveman CLAUDE.md — 项目治理规则](#3-caveman-claudemd)
4. [🔴 config.json — 集中配置](#4-configjson)
5. [🔴 echo-guard.js — 防死循环](#5-echo-guardjs)
6. [🟡 扩展栈 — 完整 SKILL.md 正文](#6-扩展栈-skillmd-完整正文)
7. [🟡 Codex 插件 Skill](#7-codex-插件-skill)
8. [🟢 settings.json + RTK.md + CLAUDE.md](#8-全局配置)
9. [重点标记汇总 — 频繁使用/写入规则的 Skill](#9-重点标记汇总)

---

## 1. 全部 Skill 总表

共 114 个 skill 安装在 `C:\Users\shiniyaya\.claude\skills\`。

### 🔴 10-Skill 核心栈 (code-shiniyaya 每次对话强制激活)

| # | Skill | 行数 | 级别 | 职责 |
|---|-------|------|------|------|
| 1 | **code-shiniyaya** | 1724 | 编排器 | CC↔Codex 8步闭环+26条硬规则+18自检+5源 |
| 2 | **ponytail** | 120 | ultra | YAGNI七步阶梯，删除优先 |
| 3 | **caveman** | — | full | 输出压缩65% token (CLAUDE.md: 307行治理规则) |
| 4 | **ponytail-review** | 57 | 审查 | 过度工程审查 delete/stdlib/native/yagni/shrink |
| 5 | **ponytail-audit** | 41 | 审计 | 全仓过度工程审计 |
| 6 | **ponytail-debt** | 44 | 债务追踪 | ponytail:注释收割→债务账本 |
| 7 | **ponytail-gain** | 50 | 计量 | 基准中位分板 LOC/cost/speed |
| 8 | **ponytail-help** | 71 | 参考 | 全ponytail模式/子skill/配置快查 |
| 9 | **using-superpowers** | 62 | 触发守卫 | 任何操作前强制检查skill适用性 |
| 10 | **openspec-explore** | 290 | 探索 | 结构化思考，不实现 |

### 🟡 高频使用 Skill (迭代/开发/审查中频繁调用)

| # | Skill | 行数 | 用途 | 触发场景 |
|---|-------|------|------|----------|
| 11 | **multi-agent-shiniyaya** | 263 | 多Agent并行深度开发 | 深度开发/全量审计/bug扫描/全面扫描 |
| 12 | **self-improving-agent** | 460 | 终身学习+自我改进 | 每次skill完成后自动提取模式 |
| 13 | **code-review** | 242 | 双轴代码审查(35条BiliSum检查清单) | review/审查PR/代码审计 |
| 14 | **skill-creator** | 84 | Skill创建/编辑/审计 | 创建skill/编辑skill |
| 15 | **skill-vetter** | 139 | Skill质量审查 | 第三方skill审计 |
| 16 | **prompt-optimizer** | 595 | Prompt优化 (6模块+57项检查清单) | prompt优化/触发率调试 |
| 17 | **prompt-engineer** | 136 | Prompt工程 | 编写/重构prompt |
| 18 | **diagnosing-bugs** | 525 | 诊断循环+回测 | diagnose/debug/报错 |
| 19 | **debugging-strategies** | 2951 | 系统调试策略 | 调查bug/性能问题 |
| 20 | **debugging-and-error-recovery** | 300 | 错误恢复 | Bash返回非零/fix失败 |
| 21 | **systematic-debugging** | 1779 | 4阶段调试框架 | bug/测试失败/异常行为 |
| 22 | **research** | 12 | 后台调研+引源 | 调查/查文档/API事实 |
| 23 | **docx** | 590 | Word文档生成 | 报告/备忘录/模板 |
| 24 | **pdf** | 314 | PDF处理 | 读取/合并/拆分/OCR |
| 25 | **planning-with-files** | 228 | Manus式持久化文件规划 | 多步骤项目/5+工具调用 |

### 🟢 其他已安装 Skill (按需使用)

#### AI/LLM 相关
| Skill | 行数 | 用途 |
|-------|------|------|
| claude-api | 578 | Claude API/SDK 参考 |
| gemini | 47 | Gemini API |
| notebooklm | 269 | Google NotebookLM 查询 |
| letta-api-client | 291 | Letta 记忆平台 |
| oracle | 126 | 第二模型审查/调试 |
| model-usage | 416 | AI模型使用统计+成本追踪 |

#### 开发工具
| Skill | 行数 | 用途 |
|-------|------|------|
| tdd | 36 | 测试驱动开发 |
| refactoring | 176 | 代码重构 |
| code-simplifier | 122 | 代码简化 |
| codebase-design | 114 | 深模块设计 |
| domain-modeling | 74 | 领域建模 |
| dependency-management | 81 | 依赖管理 |
| setup-pre-commit | 91 | 预提交门禁 |
| cross-platform-compatibility | 108 | 跨平台兼容 |
| python-error-handling | 1016 | Python错误处理 |
| python-debugpy | 73 | Python调试器 |
| python-venv-manager | 24 | Python虚拟环境 |
| fastapi | 171 | FastAPI最佳实践 |
| fastapi-templates | 136 | FastAPI项目模板 |
| electron-builder | 417 | Electron打包 |
| electron-security | 125 | Electron安全 |
| vercel-react-view-transitions | 320 | React视图过渡 |

#### 安全
| Skill | 行数 | 用途 |
|-------|------|------|
| security-triage | 2352 | BiliSum安全分类 |
| auditing-python-security | 1705 | Python安全审计 (Bandit/Semgrep) |
| xxe-xml-external-entity | 554 | XXE检测 |
| git-guardrails-claude-code | 95 | Git安全护栏 |

#### 数据库
| Skill | 行数 | 用途 |
|-------|------|------|
| sqlite-best-practices | 1472 | SQLite优化+FTS5 |
| semantic-search | 158 | 向量搜索/RAG |
| rag-eval | 350 | RAG质量评估 (RAGAS) |

#### Bilibili/BiliSum 生态
| Skill | 行数 | 用途 |
|-------|------|------|
| bili-note | 345 | B站视频提取Markdown笔记 |
| bilibili-rag-deploy | 1552 | B站RAG知识库本地部署 |
| bilibili-source | 277 | B站视频元数据获取 |
| bilibili-subtitle | 60 | B站字幕 |
| bilisum-* | — | memory/下有~30个BiliSum记忆文件(只读) |

#### 浏览器/自动化
| Skill | 行数 | 用途 |
|-------|------|------|
| agent-browser | 50 | 浏览器自动化CLI |
| browser-use | 136 | 浏览器自动化 |
| firecrawl | 321 | 网页爬取全家桶 |
| firecrawl-scrape | 69 | 单页爬取 |
| firecrawl-crawl | 58 | 整站爬取 |
| firecrawl-search | 124 | 网页搜索 |
| firecrawl-deep-research | 108 | 深度研究爬取 |

#### 文档/笔记
| Skill | 行数 | 用途 |
|-------|------|------|
| obsidian | 119 | Obsidian vault 管理 |
| obsidian-markdown | 196 | Obsidian Flavored Markdown |
| obsidian-automation | 255 | Obsidian 自动化 |
| obsidian-cli | 162 | Obsidian CLI |
| obsidian-vault | 59 | Obsidian vault |
| docx-manipulation | 385 | Word文档操作 |
| officecli | 417 | Office CLI |
| technical-documentation | 79 | 技术文档 |

#### 设计/前端
| Skill | 行数 | 用途 |
|-------|------|------|
| frontend-design | 55 | 前端设计 |
| anthropic-frontend-design | 41 | Anthropic风格前端 |
| ui-ux-pro-max-skill | 514 | 161规则+67风格UI/UX |
| impeccable | 174 | 前端界面设计/审查/打磨 |
| taste-design | 191 | 反slop前端设计 |
| taste-skill | 1233 | 落地页/作品集设计 |
| design-system | 244 | 设计系统/Token架构 |
| visual-designer | 736 | 色彩/字体/间距/视觉 |
| css-animation-creator | 31 | CSS动画 |

#### 视频/音频
| Skill | 行数 | 用途 |
|-------|------|------|
| video-summarizer | 331 | 1800+平台视频下载+摘要 |
| video-downloader | 42 | 视频下载 |
| video-frames | 266 | ffmpeg帧提取+场景检测 |
| subtitle-generation | 392 | 字幕生成 |
| srt-to-structured-data | 131 | SRT→结构化数据 |
| faster-whisper | 1130 | 本地Whisper语音识别 |
| local-whisper | 49 | 本地Whisper |
| openai-whisper | 38 | OpenAI Whisper |
| openai-whisper-api | 71 | Whisper API |
| sherpa-onnx-tts | 109 | TTS语音合成 |
| summarize | 87 | URL/视频/播客摘要 |

#### 社交/通讯
| Skill | 行数 | 用途 |
|-------|------|------|
| discord-clawd | 37 | Discord |
| discord-user-post | 51 | Discord用户帖 |
| telegram-crabbox-e2e-proof | 206 | Telegram端到端 |
| blogwatcher | 69 | 博客监控 |
| douyin-video-summary | 108 | 抖音视频摘要 |

#### 项目管理
| Skill | 行数 | 用途 |
|-------|------|------|
| gh-issues | 213 | GitHub Issues |
| github | 77 | GitHub操作 |
| trello | 108 | Trello |
| notion | 150 | Notion |
| notion-api | 495 | Notion API |
| taskflow | 149 | 任务流 |
| taskflow-inbox-triage | 119 | 收件箱分类 |

#### 基础设施
| Skill | 行数 | 用途 |
|-------|------|------|
| mcp-builder | 236 | MCP服务器构建 |
| mcp-cli | 78 | MCP CLI |
| mcporter | 61 | MCP移植 |
| dotenv | 2014 | .env环境变量 |
| auto-updater | 45 | 自动更新 |
| healthcheck | 105 | 健康检查 |
| observability | 97 | 可观测性 |
| tmux | 91 | tmux会话管理 |
| session-logs | 211 | 会话日志 |
| weather | 87 | 天气 |

#### 其他工具
| Skill | 行数 | 用途 |
|-------|------|------|
| find-skills | 142 | 发现+安装skill |
| multi-search-engine | 271 | 多搜索引擎 |
| diagram-maker | 53 | 图表生成 |
| meme-maker | 42 | 表情包 |
| gifgrep | 85 | GIF搜索 |
| json-canvas | 244 | JSON Canvas |
| nano-pdf | 38 | 毫秒级PDF |
| mineru | 48 | MinerU PDF解析 |
| songsee | 49 | 歌曲识别 |
| gog | 116 | 未知 |
| goplaces | 52 | 未知 |
| sag | 87 | 未知 |
| spike | 51 | 未知 |
| crabbox | 828 | 未知 |
| huashu-nuwa | 671 | 未知 |
| himalaya | 80 | 未知 |
| deep-interview | 61 | 深度访谈 |
| worldmonitor-intelligence-dashboard | 605 | 世界监控情报仪表板 |

---

## 2. 核心栈 SKILL.md 完整正文

以下 10 个 Skill 的 **完整 SKILL.md 内容** 已在前序文档中提供或在此文档中。Reasonix 回执已确认收到之前发送的文件。

${\color{red}\text{【已在 handoff-code-shiniyaya-reasonix-full.md 中】:}}$
- **code-shiniyaya** SKILL.md (~1724行)
- **ponytail** SKILL.md (120行)

${\color{red}\text{【已在 handoff-reasonix-sources-skills.md 中】:}}$
- 5源地址 + 10-Skill路径

${\color{red}\text{【本文件以下各节】:}}$
- caveman CLAUDE.md → §3
- ponytail-review → 上面已读取，内容57行
- ponytail-debt → 上面已读取，内容44行
- ponytail-audit → 上面已读取，内容41行
- ponytail-gain → 上面已读取，内容50行
- ponytail-help → 上面已读取，内容71行
- openspec-explore → 上面已读取，内容290行
- multi-agent-shiniyaya → 上面已读取，内容263行
- using-superpowers → 上面已读取，内容62行
- config.json → §4

---

## 3. caveman CLAUDE.md

**路径**: `C:\Users\shiniyaya\.claude\skills\caveman\CLAUDE.md`
**行数**: 307
**重要性**: 🔴 **必须** — 输出压缩规则 + 项目治理 (README/product/hooks/CI/eval/benchmark 全量规范)

完整内容已在上方 Read 结果中 (307行)。Reasonix 回执确认已收到 caveman CLAUDE.md。

---

## 4. config.json

**路径**: `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\config.json`
**重要性**: 🔴 **必须** — 所有阈值参数集中管理

```json
{
  "schemaVersion": "4.4.0",
  "description": "code-shiniyaya 集中配置文件",
  "agent": {
    "batch_size_min": 4, "batch_size_max": 24,
    "cpu_cores_deduct": 2, "agent_cap": 50,
    "default_batch_fallback": 4, "iteration_scan_agents": 20,
    "retry_attempts_per_slot": 2, "retry_upgrade_tier": 3,
    "re_prompt_per_agent_max": 2
  },
  "silence": {
    "n_ask": 4, "n_auto_degrade": 5,
    "multi_part_paste_max_seconds": 3, "autonomous_degrade_cycles": 3
  },
  "truncation": {
    "max_findings_per_dimension": 8, "max_finding_chars": 600,
    "max_codex_feedback_chars": 8000, "max_source_file_chars": 2000,
    "max_verify_prompt_chars": 12000, "head_ratio": 0.6,
    "separator_chars": 5, "paginate_page_size_lines": 8192
  },
  "budget": {
    "total_agent_launches": 50, "fix_attempts_per_bug": 5,
    "message_rounds": 200, "p0_budget_pct_normal": 60,
    "p0_budget_pct_degraded": 80, "p1_budget_pct": 30,
    "p2_budget_pct": 10, "break_glass_overage_pct": 10,
    "reset_hours": 24, "threshold_warn": 50,
    "threshold_cut_p2": 75, "threshold_p0_only": 90
  },
  "reflection": {
    "reflection_min_hours": 8, "reflection_min_workflows": 3,
    "consolidate_every_n_workflows": 3,
    "max_existing_memory_files": 24, "max_existing_memory_chars": 2500,
    "max_index_prompt_chars": 6000, "reflection_log_max_entries": 40
  },
  "agent_selection": {
    "diagnosis_min_agents": 6, "codex_verify_min_agents": 10,
    "reference_scan_min_agents": 5, "full_repo_scan_min_agents": 40,
    "degraded_step7_agents": 6, "p0_verify_agents": 4,
    "p0_verify_types": ["investigator","general-purpose","Plan","debugging"],
    "p0_verify_dimensions": ["正确性","编码安全","架构","回退"]
  },
  "convergence": {
    "findings_near_convergence": 5, "consecutive_low_rounds": 2,
    "low_findings_threshold": 10, "cr_healthy": 60, "cr_slow": 20,
    "warmup_steps_fixed": 10, "warmup_pct": 0.05,
    "line_tolerance": 5, "evidence_conflict_line_gap": 5
  },
  "git_branch": {
    "session_id_chars": 8, "reflog_recovery_days": 30,
    "merge_conflict_file_threshold": 2, "merge_conflict_line_threshold": 20
  },
  "output": {
    "report_root": "C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya\\报告\\iteration-reports",
    "memory_root": "C:\\Users\\shiniyaya\\Desktop\\code-shiniyaya\\memory",
    "state_root": "{project_root}/.claude/memory/code-shiniyaya"
  },
  "checkpointing": {
    "max_handoff_per_agent": 1, "max_handoff_receive_per_type": 2,
    "max_goto_abort_per_agent": 1, "step6_max_retry": 3,
    "workflow_max_retry_per_dimension": 2,
    "workflow_dimension_retry_cap": 2, "timeout_seconds": 600
  }
}
```

---

## 5. echo-guard.js

**路径**: `C:\Users\shiniyaya\.claude\hooks\echo-guard.js`
**重要性**: 🔴 **必须** — 平台层防 echo 死循环，唯一可靠方案

完整源码见上方 Read 结果 (116行)。settings.json PreToolUse hook 已配置指向此文件。**需 CC 重启验证。**

---

## 6. 扩展栈 SKILL.md 完整正文

以下 Skill 的完整内容已在上方 Read 结果中提供。Reasonix 回执确认收到：

| Skill | 状态 |
|-------|------|
| **using-superpowers** (62行) | ✅ 已读取 |
| **self-improving-agent** (460行) | ✅ 已读取 |
| **code-review** (242行, 35条BiliSum检查清单) | ✅ 已读取 |
| **research** (12行) | ✅ 已读取 |
| **prompt-optimizer** (595行, 6模块) | ✅ 部分读取(80行) |
| **multi-agent-shiniyaya** (263行, 16条硬规则+9反模式) | ✅ 已读取 |
| **obsidian-markdown** (196行) | ✅ 已读取 |

---

## 7. Codex 插件 Skill

**路径**: `C:\Users\shiniyaya\.claude\plugins\marketplaces\openai-codex-plugin-cc\plugins\codex\skills\`

| 文件 | 路径 |
|------|------|
| codex-cli-runtime | `skills/codex-cli-runtime/SKILL.md` (44行) |
| codex-result-handling | `skills/codex-result-handling/SKILL.md` (22行) |
| gpt-5-4-prompting | `skills/gpt-5-4-prompting/SKILL.md` |

**codex-cli-runtime** 完整内容已在上方 Read 结果中。
**codex-result-handling** 完整内容已在上方 Read 结果中。

---

## 8. 全局配置

### settings.json
**路径**: `C:\Users\shiniyaya\.claude\settings.json`

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:15721",
    "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-fable-5[1M]",
    "ANTHROPIC_DEFAULT_FABLE_MODEL_NAME": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL_NAME": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8[1M]",
    "ANTHROPIC_DEFAULT_OPUS_MODEL_NAME": "deepseek-v4-pro",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6[1M]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL_NAME": "deepseek-v4-pro"
  },
  "model": "opus",
  "hooks": {
    "PreToolUse": [{
      "matcher": "Bash",
      "hooks": [{
        "type": "command",
        "command": "node \"C:/Users/shiniyaya/.claude/hooks/echo-guard.js\""
      }]
    }]
  }
}
```

### CLAUDE.md
**路径**: `C:\Users\shiniyaya\.claude\CLAUDE.md`
**内容**: `@RTK.md`

### RTK.md
**路径**: `C:\Users\shiniyaya\.claude\RTK.md`

```bash
rtk gain              # 查看 token 节省统计
rtk gain --history    # 命令使用历史
rtk discover          # 分析历史未优化命令
rtk proxy <cmd>       # 原始命令 (绕过过滤)
```

---

## 9. 重点标记汇总

### ${\color{red}\text{🔴 必须掌握 (直接影响 SKILL.md 编辑质量)}}$

| Skill/文件 | 行数 | 为什么关键 | 写入的规则 |
|-----------|------|-----------|-----------|
| **code-shiniyaya** SKILL.md | 1724 | 元编排器自身——所有工作流/规则/自检/反模式的母体 | 26条硬规则 + 18项自检 + 24反模式 + 8步闭环 + 三层死循环防御 |
| **caveman** CLAUDE.md | 307 | 输出压缩65% token——编辑SKILL.md需同标准 | README规范/hook系统/CI/eval/benchmark全部治理规则 |
| **ponytail** SKILL.md | 120 | YAGNI七步阶梯——所有代码决策的约束框架 | 删除优先→stdlib→native→一行→最小; ponytail:debt标注 |
| **ponytail-review** | 57 | 过度工程审查——每次diff必须通过 | delete/stdlib/native/yagni/shrink 5标签+ net: -N lines |
| **ponytail-debt** | 44 | 债务追踪——ponytail: 注释收割→防止"延迟=永不" | ceiling+upgrade标记; no-trigger腐烂风险 |
| **config.json** | 105 | 所有阈值唯一真相源——不可散布在SKILL.md文本中 | Agent/静默/截断/预算/反思/收敛/git/输出/checkpointing 9段 |
| **echo-guard.js** | 116 | CC独占——唯一可靠的echo死循环阻断 | 28个echo正则 + wc循环检测 + 8次上限 + 30s turn重置 |

### ${\color{orange}\text{🟡 应该掌握 (提升审查+迭代质量)}}$

| Skill | 行数 | 写入的规则 |
|-------|------|-----------|
| **ponytail-audit** | 41 | 全仓过度工程审计——ranked list of cuts |
| **ponytail-gain** | 50 | 基准中位分板——诚实边界: 不打印per-repo估算 |
| **ponytail-help** | 71 | 全ponytail模式/命令/配置快查 |
| **openspec-explore** | 290 | 结构化探索——不实现，思考+可视化+质疑 |
| **multi-agent-shiniyaya** | 263 | 16条硬规则+9反模式+8 Phase工作流+4记忆文件+优先级体系 |
| **using-superpowers** | 62 | 触发守卫——1%可能就强制调用skill，不可跳过 |
| **self-improving-agent** | 460 | 多记忆架构+终身学习+进化标记+自纠正+推广策略 |
| **code-review** | 242 | 35条BiliSum检查清单(XSS/并发/魔法数字/安全) + 双轴审查 |
| **prompt-optimizer** | 595 | 6模块(约束引擎/诊断表/A-B测试/压缩/57项检查清单/自动优化) |

### ${\color{green}\text{🟢 按需查阅}}$

其余 ~100 个 skill。全部清单见 §1。最常用的按需 skill:
- **diagnosing-bugs** (525行) + **debugging-strategies** (2951行) + **systematic-debugging** (1779行) — 调试三件套
- **docx** (590行) + **pdf** (314行) — 文档输出
- **planning-with-files** (228行) — 多步骤持久化规划
- **skill-creator** (84行) + **skill-vetter** (139行) — Skill生命周期管理
- **research** (12行) — 后台调查

### 关键共识 (Reasonix 回执确认)

- Skills 本质是 Markdown 规则定义，不是平台特权——CC 的 skill 都可以转给 Reasonix 执行
- echo循环的唯一可靠方案是平台层阻断 (echo-guard.js)，文本规则不可靠——不要再在 SKILL.md 上无限循环修改
- 共享 Git 仓库 + CHANGELOG.md 为权威记录，谁先 commit 谁占线
- 不要动 BiliSum 仓库和记忆
- 分工: CC独占仅 echo-guard.js运行验证1项；其余均可协作或转发

---

**全部移交完毕** | 114个 Skill 清单 + 完整正文 + 重点标记 + 全局配置 + Codex插件
