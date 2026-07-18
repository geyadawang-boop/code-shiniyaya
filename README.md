# code-shiniyaya v4.7.10 — CC ↔ Codex 双向验证编排器

> **不是"让 AI 写代码"——是"让两个 AI 系统互相验证对方的工作"**

code-shiniyaya 是一个运行在 Claude Code (CC) 平台上的元编排系统。它不直接修改源代码，而是建立 CC 与 OpenAI Codex 之间的标准化双向验证闭环：CC 负责深度诊断（读源码 + 6+ Agent 并行扫描），Codex 负责独立验证（交叉检查 CC 方案），双方都批准后才执行。在此基础上，系统配备了三层防御 Hook（平台级、不依赖模型）、30 条硬规则、五层验证管线、自主迭代模式和上下文防饱和机制。

**GitHub**: https://github.com/geyadawang-boop/code-shiniyaya

---

## 目录

- [1. 项目简介](#1-项目简介)
- [2. 快速部署](#2-快速部署)
- [3. 三层防御 Hook 详解](#3-三层防御-hook-详解)
- [4. 30 条硬规则](#4-30-条硬规则)
- [5. 五层验证管线](#5-五层验证管线)
- [6. 自主迭代模式](#6-自主迭代模式)
- [7. 上下文防饱和与一字恢复](#7-上下文防饱和与一字恢复)
- [8. 触发词表](#8-触发词表)
- [9. 外部加速 Skill](#9-外部加速-skill)
- [10. 防御栈版本表](#10-防御栈版本表)
- [11. 仓库结构](#11-仓库结构)

---

## 1. 项目简介

### 核心理念

code-shiniyaya 的哲学根基是一个清醒的认知：**Claude Code 是请求-响应模型，不是自主 Agent**。CC 不能给自己发消息、不能自主启动新 turn、压缩后不能自动续跑。任何声称"AI 可以自主压缩+自动继续"的说法都是伪功能。

基于这个认知，code-shiniyaya 只做三件事：

1. **诊断** — 多源多 Agent 并行扫描，找出问题
2. **编排** — 在 CC ↔ Codex 之间传递验证消息，双方批准后才执行
3. **防御** — 三层 Hook 在平台级拦截破坏性操作和死循环

整个项目 = 一个 SKILL.md 主技能定义文件 + 3 个防御 Hook + 测试验证套件。零外部依赖，零 API Key（Codex 为可选）。

### 系统架构

```
用户输入（触发词匹配）
    │
    ▼
┌─────────────────────────────────────────────────────┐
│  code-shiniyaya 9 步闭环 (STEP 0-8)                   │
│                                                       │
│  STEP 0 → 环境检测                                    │
│  STEP 1 → 预扫描 (aislop + agent-lint + hooks.test)   │
│  STEP 2 → 深度诊断 (6+ Agent 并行)                    │
│  STEP 3 → 方案生成 + Codex 可复制文本                 │
│  STEP 4 → Codex 双向验证                              │
│  STEP 5 → 双批准门控（用户 + Codex）                  │
│  STEP 6 → 执行（含变更前 L1-L3 强制门控）              │
│  STEP 7 → 双向验证（L3 对抗验证）                      │
│  STEP 8 → 元反思 + 知识合并                           │
└─────────────────────────────────────────────────────┘
    │
    ▼
三层防御 Hook（平台级，不依赖模型）
┌─────────────────────────────────────────────────────┐
│  SessionStart: bearings.js v3.0-r9                   │
│  PreToolUse:   echo-guard.js v4.3                    │
│  Stop:         stop-guard.js v3.5                    │
└─────────────────────────────────────────────────────┘
```

### 与外部 Skill 的关系

code-shiniyaya 自身开发/迭代必须在以下 10 个 Skill 全部激活的状态下进行：

| #  | Skill             | 级别  | 职责                                           |
|----|-------------------|-------|------------------------------------------------|
| 1  | code-shiniyaya    | 编排器 | 9 步闭环 + 30 条硬规则 + 20 项自检 + Hook 基础设施   |
| 2  | ponytail          | ultra | YAGNI 极端主义：删除优先，永不新增无必要代码         |
| 3  | caveman           | full  | 输出压缩，但安全警告/不可逆操作恢复完整语言           |
| 4  | ponytail-review   | 审查   | 过度工程审查：delete/stdlib/native/yagni          |
| 5  | ponytail-audit    | 审计   | 全仓过度工程审计                                   |
| 6  | ponytail-debt     | 债务追踪 | ponytail 注释收割→债务账本                        |
| 7  | ponytail-gain     | 计量   | 基准中位分板：LOC/成本/速度                        |
| 8  | ponytail-help     | 参考   | 全 ponytail 模式快查卡片                           |
| 9  | using-superpowers | 触发守卫 | 操作前检查 skill 是否适用，强制调用                  |
| 10 | openspec-explore  | 探索   | 思考不实现，质疑假设，不 rush                       |

优先级链：`code-shiniyaya > ponytail > using-superpowers > caveman > ponytail-review/audit/debt/gain/help > openspec-explore`

冲突裁决：安全/正确性 > 极简。信任边界验证、数据丢失保护、安全措施、无障碍、校准真实硬件、任何明确要求——这 6 项永不简化。

---

## 2. 快速部署

### 前置条件

- Claude Code 已安装（`npm install -g @anthropic-ai/claude-code`）
- Node.js 18+
- (可选) OpenAI Codex CLI + codex-plugin-cc

### 安装步骤

```bash
# 1. 克隆仓库
git clone https://github.com/geyadawang-boop/code-shiniyaya.git
cd code-shiniyaya

# 2. 创建 hooks 目录并复制 3 个防御钩子
mkdir -p ~/.claude/hooks
cp hooks/echo-guard.js ~/.claude/hooks/echo-guard.js
cp hooks/stop-guard.js ~/.claude/hooks/stop-guard.js
cp hooks/bearings.js ~/.claude/hooks/bearings.js

# 3. 注册 hooks 到 settings.json（编辑或创建 ~/.claude/settings.json）
```

### settings.json 配置

编辑 `~/.claude/settings.json`，加入以下内容（将 `<你的用户名>` 替换为实际用户名）：

```json
{
  "permissions": {
    "deny": [
      "Bash(rm:*)",
      "Bash(chmod -R:*)",
      "Bash(chmod --recursive:*)",
      "Bash(git push --force:*)",
      "Bash(git push -f:*)"
    ]
  },
  "hooks": {
    "PreToolUse": {
      "Bash": [
        {
          "matcher": ".",
          "command": "node",
          "args": ["C:/Users/<你的用户名>/.claude/hooks/echo-guard.js"]
        }
      ]
    },
    "Stop": [
      {
        "matcher": ".",
        "command": "node",
        "args": ["C:/Users/<你的用户名>/.claude/hooks/stop-guard.js"]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "command": "node",
        "args": ["C:/Users/<你的用户名>/.claude/hooks/bearings.js"]
      }
    ]
  },
  "autoCompactThreshold": 55
}
```

> **Windows 注意**：路径使用 `/` 或 `\\`，不要使用单反斜杠 `\`。`permissions.deny` 是 hooks 的互补层——即使 hooks 被其他插件覆盖，deny 仍在。autoCompactThreshold:55 是上下文防饱和的关键参数。

### 验证安装

```bash
# 在仓库根目录运行回归测试
node references/hooks.test.js
# 预期输出: 42 passed, 0 failed
```

### 验证 Hook 生效

启动 Claude Code，检查以下几点：
- SessionStart Hook 输出应看到 `[BEARINGS]` 或 `NEXT ACTION:` 开头的信息
- 尝试 `echo done` → 被 echo-guard 拦截
- 尝试纯确认输出（无工具调用） → 被 stop-guard 拦截

### Codex 插件安装（可选）

```bash
# 安装 codex-plugin-cc
# 在 Claude Code 中执行:
/plugin marketplace add openai/codex-plugin-cc
/plugin install codex@openai-codex
/reload-plugins
/codex:setup
```

插件提供 `/codex:review`（只读审查）、`/codex:adversarial-review`（对抗审查）、`/codex:rescue`（任务委派）等命令。

### 卸载

```bash
rm ~/.claude/hooks/echo-guard.js
rm ~/.claude/hooks/stop-guard.js
rm ~/.claude/hooks/bearings.js
# 并从 settings.json 移除 hooks 块
```

---

## 3. 三层防御 Hook 详解

整个防御系统的核心哲学：**L2 平台阻断 > L3 一字恢复 > L1 文本规则**。文本规则（规则 26/自检）在模型陷入验证强迫吸引子时会失效，平台级 Hook 不依赖模型认知——它们才是真正的最后防线。

```
                    ┌─────────────────────┐
                    │  Claude Code 会话     │
                    └──────┬──────────────┘
                           │
              ┌────────────┼────────────┐
              ▼            ▼            ▼
       SessionStart     PreToolUse      Stop
       bearings.js     echo-guard.js  stop-guard.js
       v3.0-r9         v4.3          v3.5
              │            │            │
              ▼            ▼            ▼
       NEXT ACTION     Bash 命令       Turn 终态
       STATE JSON     拦截/豁免      对抗审查
       HookWarn 检测   指纹阶梯       4道保护门
```

---

### 3.1 echo-guard.js v4.3 — PreToolUse Bash 钩子

在每次 Bash 命令执行前触发，拦截破坏性/无意义的命令。包含 6 层功能：

#### 第 1 层：无意义 echo 拦截

拦截输出无实质内容的 echo 命令。以下 echo 会被拒绝：

- `echo done` / `echo ok` / `echo final` / `echo complete`
- `echo 1` / `echo 2` / `echo 3`（无意义的数字确认）
- `echo ""` / 空 echo / 纯空格 echo
- 6 词以内的纯确认性 echo（如 `echo "all good"`）

deny 响应示例：
```
❌ echo-guard: 无意义echo——"echo done"。请执行有产出操作而非确认输出。
```

#### 第 2 层：wc -l 循环拦截

同 turn 内对同一文件的 `wc -l` 命令：
- 第 1 次：放行（记录文件指纹）
- 第 2 次：拦截（"wc -l 同文件第 2 次——行数已知"）

防止模型因验证强迫反复检查同一文件的行数。

#### 第 3 层：8 次非只读 Bash/turn 上限

每个 turn 内非豁免 Bash 命令最多 8 次。豁免列表（不计入上限）：

| 分类 | 命令 |
|------|------|
| 无条件豁免（只读） | `grep`, `rg`, `cat`, `head`, `tail`, `wc`, `uniq`, `stat` |
| 条件豁免（先放行再检查 flag） | `find`, `sort`, `diff` |

条件豁免的命令如果带破坏性 flag，则从豁免转入拦截检查。

#### 第 4 层：破坏性 flag 检测

对 `find` 和 `sort` 命令，检查是否携带破坏性 flag：

**find 破坏性 flag**（Set DESTRUCTIVE_FLAGS）：
- `-delete` — 直接删除文件
- `-exec` — 执行任意命令
- `-execdir` — 在文件所在目录执行命令
- `-fprint` / `-fprint0` / `-fls` — 写入文件
- `-ok` / `-okdir` — 带确认的执行（仍可造成破坏）
- `--output` — 输出重定向

**sort 破坏性 flag**：
- `-o` / `-O` — 输出到文件（可能原地覆盖）
- `--output=FILE` — equals 形式等同于 `-o`

**command-context-aware**（v4.1 关键特性）：
- `find . -name "*.txt" -o -name "*.md"` 中的 `-o` = 逻辑 OR，**非破坏性**——放行
- `sort file.txt -o sorted.txt` 中的 `-o` = 输出文件，**破坏性**——拦截
- 同一标志在不同上下文中含义不同，Hook 根据命令类型区分对待

#### 第 5 层：指纹阶梯

**文件指纹归一化**（v4.2）：将具体文件参数替换为类型占位符，实现跨文件识别。

```
rm a.mp4   → 指纹: rm <FILE>
rm b.mp4   → 指纹: rm <FILE>  ← 同一指纹
rm -rf dir → 指纹: rm <FLAG> <FILE>
```

指纹阶梯升级路径：
| 同一指纹出现次数 | 响应 |
|------------------|------|
| 第 1 次 | 放行 |
| 第 2 次 | systemMessage（系统消息警告） |
| 第 3 次 | ask（询问用户确认） |
| ≥ 第 4 次 | deny（拒绝）+ 换策略指令 |

指纹存储 cross-turn，15 分钟 TTL 过期，仅小写命令词归一化——参数大小写不归一化。

#### 第 6 层：统一 deny 输出

所有阻断路径统一使用 `deny()/ask()` 辅助函数输出 `hookSpecificOutput.permissionDecision`。PreToolUse handler 需要此格式才能实际拒绝执行。输出示例：

```json
{
  "hookSpecificOutput": {
    "permissionDecision": "deny",
    "reason": "echo-guard: 无意义echo——'echo done'。请执行有产出操作。"
  }
}
```

#### echo-guard 典型拦截场景

```
用户：echo "done"
   → 拦截: 无意义echo

用户：echo "final complete"
   → 拦截: 无意义echo（≥2 确认词）

用户：wc -l file.txt
   → 放行（第1次）
用户：wc -l file.txt
   → 拦截: 同文件wc -l第2次

用户：find . -name "*.tmp" -delete
   → 拦截: 破坏性flag（-delete）

用户：sort file.txt -o sorted.txt
   → 拦截: sort破坏性flag（-o）

用户：rm a.mp4（第4次重复类操作）
   → 拦截: 指纹阶梯≥4 → deny
```

---

### 3.2 stop-guard.js v3.5 — Stop 钩子

在每次 turn 结束时触发，分析 transcript 末 400 行，识别 4 种需要阻止的模式。v3.5 是 Stop 防御的权威版本，包含了对抗审查阶段多项真实 bug 修复。

#### 第 1 道门：pure-confirmation（纯确认拦截）

**触发条件**：最后一次 assistant turn 包含 ≥2 个确认词（done/ok/final/complete/verified/confirmed/finished/success）**且** 该 turn 没有调用任何 Write、Edit、Agent 工具。

**为什么需要**：模型陷入验证强迫时，会不停输出"done""ok""completed"等等确认词，不执行任何实质性操作。这些 turn 消耗上下文窗口但不产生价值。

**Block 响应**：注入"写 snapshot + 输出 ⚡ 进度行后停止"指令，强制跳转到有产出的操作。

**v3.5 关键修复**：
- **tool_result break**（跨 turn 污染修复）：前一 turn 的 Agent/Write 输出可能泄漏到当前 turn 的 text 块中，导致确认词误判。v3.5 解析 assistant message 时跳过 `tool_use` 和 `tool_result` 块的文本，只审查纯 text 内容。
- **CONFIRM 仅匹配 text 块**：`done`/`ok` 等膨化词若出现在 tool_use 输出中（如 Agent 输出的日志包含 "done"），不再误触发纯确认拦截。

#### 第 2 道门：stall（停滞检测）

**触发条件**：干净轮计数器 < 2 **且** 当前 turn 没有发射任何 Agent（无 Workflow/Agent/Task 工具调用）。

**为什么需要**：迭代模式中，如果干净轮不足 2 轮但模型没有启动新扫描，说明迭代停滞了。需要强制启动扫描。

**Block 响应**：注入"启动下一轮扫描 Agent 并继续迭代"指令。

#### 第 3 道门：pre-launch（预发射审计）

**触发条件**（v3.4 引入）：turn 中包含"第 N 轮→继"或类似预发射声明，但实际没有调用 Workflow/Agent/Task 工具。

**为什么需要**：迭代审计（r4 真实案例）中发现预发射声明伪造——模型写了"第 9 轮在飞"但未实际调用 Agent。进度行必须是对已实际发射 Agent 的声明，不是发射的替代品。

**处理方式**：每 turn 最多 block 1 次。block 后模型修正行为（实际发射 Agent）。

**v3.5 修复**：tool_result 跨 turn 污染也会导致 pre-launch 误判——Agent 输出中的"第 N 轮"文本流入当前 turn。修复后 pre-launch 解析同样只检查 text 块。

#### 第 4 道门：clean-exit（干净退出检测）

**触发条件**：收敛声明（"干净轮 2/2""## 签收单""最终签收单"）**但** 同一 turn 没有写入 snapshot。

**为什么需要**：收敛声明的核心要求是同 turn 落盘 snapshot + goal-reached 文件。只有文字声明不保存状态 = 虚假收敛。

**验证通过条件**：同 turn 写入了 `memory/goal-reached-{版本}.md`（含 P0=0 字段 + final commit）+ 最终 snapshot（含哨兵行）。

#### 其他特性

- **饱和豁免**：如果 turn 输出包含 `⚡.../compact` 模式，跳过所有门控（饱和优先线）。
- **用户中断放过**：用户消息包含 `\bstop\b` 词边界时跳过干预（v3.5 移除了过宽的裸"报告"匹配）。
- **stop_hook_active 护身符**：每 stop 事件最多 1 次干预，防止 Hook 自循环。

---

### 3.3 bearings.js v3.0-r9 — SessionStart 钩子

在每次会话启动（startup/resume/clear/compact）时触发，自动注入环境上下文。v3.0-r9 是 42 测试全绿的稳定版本。

#### NEXT ACTION 注入

自动在系统上下文中注入当前应执行的动作：

```
NEXT ACTION: {动作}
```

动作取值来自 snapshot 的 `nextAction` 字段：
- `await` — 有在飞 Agent 或未处理的预发射结果，先等待
- `scan` — 启动新一轮扫描（干净轮 < 2 且无 pending 项）
- `fix` — 从 pending 项继续修复
- `verify` — 进入最终验证（干净轮 ≥ 2）

#### STATE JSON 注入

注入当前状态的 JSON 摘要，包含：
- 当前版本号
- 干净轮计数
- pending 修复项数
- 饱和状态
- hook 注册状态
- 迭代任务规格（如果有）

STATE JSON 使用双格式容错正则，支持 `"干净轮计数: i/2"` 和 `"clean_rounds: i/2"` 两种字面格式。

#### HookWarn 4 种形态

当检测到 hook 注册丢失或不完整时，bearings.js 注入警告。警告有 4 种形态：

| 形态 | 触发条件 | 输出格式 |
|------|---------|---------|
| HOOK_INFO | 完全注册 | `[BEARINGS/NEXT] echo-guard v4.3+stop-guard v3.5+bearings v3.0-r9 全挂载` |
| HOOK_WARN_PRE | PreToolUse 缺失 | `[BEARINGS] ⚠️ echo-guard未注册: PreToolUse.Bash` |
| HOOK_WARN_STOP | Stop 缺失 | `[BEARINGS] ⚠️ stop-guard未注册: Stop` |
| HOOK_WARN_MISSING | SessionStart 缺失 | `[BEARINGS] ⚠️ bearings未注册: SessionStart` |

#### cwd 过滤

bearings.js 仅在以下工作目录激活：
- `code-shiniyaya`（主项目）
- `bilisum` 或 `bilibili-summary`（BiliSum 项目）

非相关项目不注入，避免干扰其他对话。

#### 标准化启动检查清单

"继"触发恢复时，bearings.js 自动注入以下检查结果（消除手动 7 步检查的信息收集成本）：
1. `pwd` — 确认工作目录
2. `ls memory/snapshot-*.md` — 列出快照
3. `git log --oneline -5` — 当前 HEAD
4. `git status --short` — 工作区状态
5. `cat CHANGELOG.md | head -30` — 最近变更
6. `ls memory/ | wc -l` — 记忆文件数

版本交叉比对（snapshot 版本号 vs git HEAD）仍需模型在"继"时执行。

#### Hook 基础设施规则（9 条生命周期模式）

所有 code-shiniyaya 的 Hook 遵循 ponytail hooks/ 的 9 条生命周期模式：

1. **沉默失败契约** — 所有写操作必须 try/catch，错误静默吞掉，Hook 绝对不能冻结会话
2. **UTF-8 BOM 剥离** — JSON.parse 前 `.replace(/^﻿/, '')`（Windows 编辑器 BOM）
3. **stdin 超时守卫** — Windows PowerShell 管道可能吞掉 stdin，1 秒 setTimeout 回退
4. **一次性哨兵文件** — 配置提示前检查哨兵文件，存在则跳过
5. **Shell 安全路径 allowlist** — `isShellSafe()` 校验字符白名单
6. **多级配置解析** — env var > config file > hardcoded default
7. **平台感知配置目录** — Windows 用 `%APPDATA%`，POSIX 用 `~/.config/`
8. **停用检测（全消息匹配）** — 停用短语仅当构成整条消息时识别
9. **子 Agent 规则集注入** — SubagentStart hook 将规则集注入子 Agent

---

## 4. 30 条硬规则

规则分为 7 个类别，每类有明确的目的和边界。

### 4.1 门控规则（规则 1-4）

| 规则 | 名称 | 概要 |
|------|------|------|
| **1** | 双批准门控 | 用户 + Codex 双方批准才能执行。Codex 批准需每项 file:line 证据。CC 必须独立验证每项批准。Codex 不可用时降级为用户单批准可执行。 |
| **2** | CC 不独立修改源码 | 无例外。记忆/规则/review/报告/迭代自修复除外。迭代自修复仅限语法错误/导入缺失/配置修正/反模式更新。P0 逻辑变更仍需用户批准。 |
| **3** | 分析自由，修改阻断 | 诊断/方案/报告 = 无门控；触及 Edit/Write 到源码 → 阻断。 |
| **4** | 逐项反馈 | 每项 → 反馈 → 确认 → 继续。禁止批量。迭代模式下暂停此规则，P0/P1 自动执行。P0 安全敏感修复仍需用户中断确认。 |

### 4.2 Agent 规则（规则 5-8）

| 规则 | 名称 | 概要 |
|------|------|------|
| **5** | 批次控制 | batch_size = max(4, min(16, cpu_cores-2))。总 Agent 上限 50。迭代扫描 20 Agent 分 2 批。 |
| **6** | 语法门控 | 批次间验证（ast.parse/tsc/eslint）→ 前进 → 失败回滚。 |
| **7** | 失败替换与 3 层重试升级 | 第 1 次：原始类型；第 2 次：原始类型 + 注入失败原因；第 3 次：升级到 general-purpose。3 次全失败 → PERMANENTLY_FAILED。 |
| **8** | 无共享文件 | 单 Agent = 串行安全。多 Agent = CC 自保（共享文件检测 + 串行排队）。 |

**规则 7 三层重试升级表：**

| 尝试 | Agent 类型 | 权限 | 提示词注入 |
|------|-----------|------|-----------|
| 1 | 原始类型（如 investigator） | 标准 | 无 |
| 2 | 原始类型 | 标准 | 注入上次失败原因作为反馈 |
| 3 | general-purpose（升级） | 全部文件读取 + 全部 Skill | "原 Agent 2 次尝试失败。失败原因: {reason}。请使用不同方法解决。" |

### 4.3 Plan-Code Gap 规则（规则 9-11）

| 规则 | 名称 | 概要 |
|------|------|------|
| **9** | 代码 ≠ 方案 | `git diff --stat` + `grep -n` 双验证。不一致 → 回滚 + 报告。 |
| **10** | 方案锁定 | 偏离 = (a)未列出文件 OR (b)函数/类范围外 OR (c)机制改变。偏离 → 新方案 + 重双批准。 |
| **11** | 盲写禁止 | Write/Edit 前必须 Read。 |

### 4.4 停止线规则（规则 12-19）

| 规则 | 名称 | 概要 |
|------|------|------|
| **12** | 3 次同文件失败 + 崩溃分类 | Type A（琐碎错误）= 自动修复，不消耗配额。Type B（根本性错误）= 消耗配额，3 次后终止。 |
| **13** | 中断优先 | stop/中断/CTRL+C → 立即停，等下条消息。完成项保留，未开始项待恢复。 |
| **14** | 写成功即完成 | Write/Edit 成功 = 已写入。不 Read 验证正确性。仅执行原子写入协议的 checksum 验证 Read。 |
| **15** | 迭代不中断 | 迭代模式下持续执行不停顿。优先于规则 1、4、9、10。不覆盖规则 2 和安全护栏。 |
| **16** | 双轨修复 | 每次迭代必须同时推进：(a) SKILL.md 内容优化, (b) 迭代流程本身优化。两轨不可偏废。 |
| **17** | 7 大优化方向 | 持续性/保真性/有意义性/稳定性/5源深度利用/自我迭代/报告规范。不得只优化其中 1-2 个方向。 |
| **18** | 用户中断处理 | "停"/"stop"/"报告"= 唯一合法停止信号。普通消息不中断迭代。 |
| **19** | 工作流输出不阻断 | 思考过程（thinking）≠ 用户可见输出。只有最终文本响应才算用户可见。 |

### 4.5 迭代规则（规则 20-25）

| 规则 | 名称 | 概要 |
|------|------|------|
| **20** | P0 验证规格化 | 非降级模式 = 2 Agent（investigator + general-purpose）。降级模式 = 4 Agent。必须指定类型和维度。 |
| **21** | 趋势确认 | 单次非零不表示未达标。对比上一轮看趋势。只有连续 2 轮不变且 P0>0 才触发检查。 |
| **22** | 自动化模式自我应用 | 从 5 源提取的模式必须实际应用，不能只文档化。每轮至少集成 1 个。 |
| **23** | 防卡顿并行启动 | 所有 Agent 在单一 planar 并行块中启动（Promise.all），不使用 phase 门控。 |
| **24** | 收敛阈值自调整 | 发现数 < 5 且连续 2 轮 < 10 且无 P0 → 触发 50 Agent 最终验证。干净轮 ≥ 2 才宣布收敛。 |
| **25** | Fast-fail 内联守卫 | 关键指标内联检查，不委托 Agent。异常值立即 abort。前 N 步为预热期，不计入统计。 |

**规则 24 干净轮计数器详解：**

干净轮 = 本轮扫描返回 0 P0 + 0 P1 **且本轮未应用任何修复**。修复轮永不计为干净轮——修复本身可能引入新 bug（v4.7.8 两次实证）。计数器 < 2 时，强制启动下一轮扫描。前置条件：hooks.test.js 全绿 + agent-lint 分数不降 + 扫描维度与上轮重叠 < 80%。

**Turn-end 统一决策树（turn-end 的权威决策逻辑）：**

1. pending 非空 → 继续修复
2. 否则干净轮 < 2 → 启动下一轮扫描
3. 否则未跑最终验证 → 启动 50 Agent 最终验证
4. 50 Agent 确认 P0=0 → 写 goal-reached 文件 → 输出签收单 → 写最终 snapshot → 停止
5. 2/3 不可执行（三硬门全阻断）→ 写 snapshot → 输出对应状态进度行 → 停止

### 4.6 交付规则（规则 27-28）

| 规则 | 名称 | 概要 |
|------|------|------|
| **27** | 报告路径统一 | 所有报告 → `报告/iteration-reports/iter-{N}/`。可通过 `CODE_SHINIYAYA_REPORT_DIR` 覆盖根路径。 |
| **28** | Codex 消息可复制 | 纯文本，`=` 分隔，无 Markdown 表格。用 `-->` 不用 `→`。6 步消毒流水线：Bidi→NFKC→零宽→Null→C0/C1→围栏转义。 |

### 4.7 质量门控规则（规则 29-30）

#### 规则 29 — 契约前置 + 验证驱动（TDD 模式落地）

每个 P0/P1 修复必须配验证用例：
- hooks 域 → hooks.test.js 回归用例
- SKILL.md/规则域 → 独立验证脚本

执行顺序：Before-any-edit（Read 目标文件）→ After-edit-before-done（运行验证命令）→ 修复未通过验证 = 未完成。

**核心原则**：No fix without a checkable invariant。Fix 的 done 状态由验证命令 exit code=0 定义，不是 Write 工具调用返回。Clean 轮前置条件中的 hooks.test.js 全绿 = 此规则的聚合关。

#### 规则 30 — 修复后全站交叉一致性审计

任何修复改变共享值（版本号/计数/hook 名称/路径/阈值）后，必须执行跨文件一致性审计——否则该修复视为未完成。

**审计三步**：
1. **确定权威源** — 哪个文件的值是正确的（如 echo-guard.js L2 的 `v4.1` 是代码权威源）
2. **Grep 全站引用** — `grep -rn "echo-guard v[0-9]" .` 搜索所有出现
3. **差异 → 批量修正** — 每个非权威引用对齐权威源或标注"故意不同 + 原因"

审计范围包括当前值 + 相近模式（如数字序列 30→33→35→38 全站必须一致）。修复后 commit message 列出所有被修改的引用行号。

**为什么需要规则 30**：实证表明 echo-guard v3.4→v4.1 跨越 8 轮才收敛——因为每次修复只改发现点、不查其余引用。跨文件引用不一致是 SKILL.md 生态的最高频 bug 类型。

---

## 5. 五层验证管线

每变更（修复/新增/重构）在进入 STEP 5 用户批准前，必须通过 L1-L3；L4 为 CC 内化清单（非外部工具）；L5 = STEP 5 门控（已有）。管线执行顺序：

```
变更完成 → L1 → L2 → L3 → L4 → L5(STEP 5) → STEP 6 执行
                                                    │
                         任一层失败 ← ← ← ← ← ← ← ← ┘
                                                    ▼
                                              回 STEP 2 重方案
```

### L1 静态检测（机器零 LLM 成本）

**触发时机**：每轮修复后、commit 前、干净轮计数器计入前。

**检查方法**：
- `npx aislop .` — 50+ 反模式规则，亚秒级，按严重度注入 Agent prompt。不可用 → 跳过。
- `npx agent-lint score SKILL.md` — Skill 元质量分数。较上轮下降 → LINT_REGRESS。不可用 → 跳过。
- `node hooks.test.js` — 42 用例全绿（当前 v4.7.10=42）。

**失败动作**：
- aislop 新增 HIGH/CRITICAL → 本轮修复标 BLOCKED，回 STEP 2
- agent-lint 分数下降 → 回滚评估，修复标 LINT_REGRESS
- hooks.test 任一 FAIL → 禁止进入干净轮计数

### L2 AI 初审（6+ Agent 并行 + diff 审查）

**触发时机**：L1 通过后、STEP 4（Codex 审查）前。

**4 维度并行**：

| 维度 | Agent 数 | 类型 | 焦点 |
|------|---------|------|------|
| 正确性 | 2 | investigator + general-purpose | 代码逻辑、行号对齐 |
| 编码安全 | 2 | investigator + general-purpose | 注入/越权/泄露 |
| 规则合规 | 1 | Plan | 30 条硬规则逐条对照 |
| 过度工程 | 1 | ponytail-review | diff 审查 — delete/stdlib/native/yagni |

**失败动作**：任一 P0 维度 FAIL → 整体不通过 → 退回 STEP 2。仅 P1/P2 split → 多数 Agent 通过 → 整体通过（附注 split 维度）。

### L3 对抗验证（pantheon + PAR/MMAR）

**触发时机**：L2 通过后、STEP 7 双向验证。

**4 条路由**：

| 路由 | 条件 | 机制 |
|------|------|------|
| pantheon-fix | 复杂 P0 + DAG 空 + 用户 opt-in | 多候选修复 + 隔离 worktree + 回归门控 + 对抗验证 |
| MMAR 降级 | Codex 不可用 + MMAR 可用 | 跨模型对抗审查，产出视同 Codex 粘贴回复 |
| PAR | 可用时 | 独立批评者 Agent 主动攻击提议，循环至收敛 |
| pantheon-gap | P0 修复后 + 可用 | 扫描同根因变体 bug，写入 VARIANTS 报告 |

**失败动作**：pantheon-fix 回归门控失败 → 回滚 worktree。MMAR 不可用 → 降级 CC 6+ Agent 自我验证。对抗验证发现新 P0 → 追加 pending，本轮干净轮清零。

### L4 清单驱动（28 规则 ↔ 20 自检映射）

**触发时机**：L3 通过后、STEP 5 用户批准前。CC 内化执行，零外部工具依赖。

**4 周期映射**：

| 周期 | 对应自检 | 检查内容 |
|------|---------|---------|
| 安全性（Q1-Q7） | #7（时间预算）+ #17（防卡死） | 安全护栏 6 项；脚本安全性 |
| 完整性（Q8-Q14） | #5#6#8#9#10#12#14 | 工作流完整性；7 方向覆盖；模式实际应用 |
| 正确性（Q15-Q21） | #13（产出物）+ #16（报告路径） | 方案-代码一致性；修复有效性；去重 |
| 幻觉（Q22-Q28） | #2（不等待）+ #18（同 turn 部分） | 无伪发射；收敛条件真实满足 |

**失败动作**：任一周期的 ≥ 2 项自检未通过 → 该修复轮不计干净轮。未通过项写入 snapshot 的 L4-gaps 字段。

### L5 人工核验（用户批准门控）

**触发时机**：L1-L4 全部通过后。

**检查方法**：STEP 5 双批准门控。用户审查 L1-L4 通过证据 → 批准执行。Codex 双向验证为人工核验提供第二意见。

**失败动作**：用户拒绝或 Codex 拒绝 → 回 STEP 2 重方案。Codex 不可用 → 降级模式（用户单批准可执行）。

### 管线硬性约束

- **L1 为干净轮前置条件**：三个条件缺一不可
- **L1-L3 为 L4 输入**：跳过前置层的清单核对 = 形式主义
- **L5 不可跳过**：P0 安全敏感修复仍需用户中断确认
- **外部 skill 不可用的回退**：所有回退不阻塞管线，仅降低对应层置信度

---

## 6. 自主迭代模式

自主迭代是当用户消息匹配 H 类触发词时进入的深度自动化模式，用于对 SKILL.md 进行持续优化直到收敛。

### 触发词

`循环迭代` / `自动更新` / `自动迭代` / `自主执行` / `不中断` / `持续修复` / `自动扫描修复` / `优化skill` / `根据源文件优化`

### 工作流

#### 1. 计划生成

1. 分析需求 → 识别任务目标、范围边界、成功标准
2. 生成迭代计划 → 写入 `报告/iteration-plans/plan-{ts}.md`
   - 任务分解（阶段 × 步骤）
   - 每步的验证标准
   - 停止条件（零 bug / 用户显式停 / 预算耗尽）
   - 预计 Agent 数量和工作流轮次
3. 呈现计划供审阅 → 提示"审阅后回复'批准执行'或提出修改"
4. (可选) 对迭代计划跑 grilling 压力测试

#### 2. 自主执行

一旦用户批准（或下条消息为非否决/非修改内容的任意回复 → 视为批准）：

**(A) 发射 → (B) snapshot + git commit → (C) 输出进度行**

这三个步骤必须严格按照 A→B→C 顺序执行，缺一不可。禁止 AB 倒序（先 commit 后发射→"已完成"认知闭合），禁止 AC 跳 B（伪发射——stop-guard v3.5 pre-launch 门将 block）。

**预发射三硬门**（启动前必须过的三关）：
1. **饱和检查** — 上下文 ≥ 55%？→ 走饱和优先线（保存 snapshot + 输出 `/compact + 继`）
2. **预算检查** — 剩余 Agent 发射配额 < 20？→ 不启动，走预算耗尽路径
3. **在飞检查** — 有在飞 Agent 或未处理结果？→ 不重复发射，先处理现有结果

#### 3. 进度行格式

正常轮：`第N轮[dim]: X→Y→继`（X=发现数，Y=修复数，dim=维度名）
干净轮：`第N轮[规模]: 干净轮i/2→继`（i=当前计数，规模=扫描 Agent 数）
失败轮：`第N轮[FAIL]: Agent全部PERMANENTLY_FAILED→停`

### 干净轮计数器

**核心逻辑**：干净轮 = 本轮扫描返回 0 P0 + 0 P1 **且本轮未应用任何修复**。修复轮永不计为干净轮。

```
计数器=0 → 有修复 → 清零 → 重新扫描
       → 扫描无发现 → 干净轮1/2 → 再扫一次
       → 无发现 → 干净轮2/2 → 收敛达成
```

**前置条件**：
- hooks.test.js 全绿
- agent-lint 分数不降
- 扫描维度与上轮重叠 < 80%

### 签收单模板（强制，stop-guard 收敛检测锚点）

```
## 签收单

发现总数: {N}
修复总数: {M}
当前零bug确认: ✅ P0=0（最终50 Agent终验确认）
final commit: {commit_hash}
```

同 turn 必须写 `memory/goal-reached-{版本}.md`（含版本/日期/50 Agent 结果 P0=0/发现总数/修复总数/final commit）+ 最终 snapshot（含哨兵行）。

### 收敛条件

1. 干净轮 ≥ 2
2. 最终 50 Agent 终验 P0=0
3. 签收单已输出

---

## 7. 上下文防饱和与一字恢复

### 根因分析

死循环（echo done/ok/wc -l × N）不是规则设计缺陷——是 LLM 在上下文窗口接近饱和时进入**验证强迫吸引子状态**的结果。文本规则（规则 26/自检）只能事后阻断已发生的循环，不能防止模型进入吸引子。

唯一有效的事前预防 = **避免上下文饱和**。

### 自动压缩阈值

```
autoCompactThreshold: 55
```

| 估算占用 | 动作 |
|---------|------|
| < 55% | 正常执行 |
| 55-70% | 保存 snapshot + git commit（不push）→ 输出"⚡ 55% — /compact + 继" → 终止 turn |
| 70-90% | 禁用扫描发射；保存 snapshot + git commit；输出"⚡ 70% — /compact + 继" |
| > 90% | 仅保存 snapshot + git commit，输出"⚠️ >90% /compact 继"，不启动任何 Agent |

阈值估算基于 `versionVector × ~12%`（每轮 20 Agent ≈ 10-15% 上下文消耗）。Write 密集型会话准确，Read 密集型可能低估 30-50%。

### 55% 饱和触发流程

```
1. 保存 memory/snapshot-{ts}.md
   字段：版本号/todo/关键数据/nextAction/干净轮计数
   原子写入（tmp+rename）+ 末尾哨兵行
   <!-- SNAPSHOT-COMPLETE {ts} -->

2. CHANGELOG 追加一行

3. git add + commit（不push）
   若干净轮<2且预发射未完成→禁止commit（防认知闭合）

4. 输出: "⚡ 55% — /compact + 继"

5. 不echo done/ok/final，不Read刚写的文件，不启动新Agent
```

### 快照保留策略

- **max_snapshots**: 20（默认，可在 `memory/config.json` 配置）
- **retention_days**: 7 天（按 mtime 清理）
- 保存新快照后若总数 > max_snapshots → 删除最旧的非 goal-reached 版快照
- 快照恢复时先验证哨兵行，缺失 = 截断快照 → 进入第二道防线

### 恢复触发词表

| 触发词 | 恢复方式 |
|--------|---------|
| `继` | 读最新 snapshot → 恢复执行（一字恢复专有触发词） |
| `继续执行` / `继续迭代` / `继续优化` | snapshot 恢复 |
| `继续修复` | session JSON 恢复，不存在则 snapshot 恢复 |
| `resume` / `go on` / `pick up` | 先尝试 session JSON，不存在则 snapshot |
| `继续`（裸词） | 不触发恢复，提示用户明确意图 |
| `继续等` / `继续等待` | 保持静默等待，不触发恢复路由 |

### 恢复决策树（4 分支）

"继"触发恢复后，根据 snapshot 的 nextAction 字段决策：

```
① nextAction=await OR 有在飞Agent/未处理的预发射结果
   → 不重复启动新轮
   → 处理已返回结果（journal/task-notification）

② (nextAction=scan OR 干净轮<2) AND 无pending项
   → 立即启动下一轮扫描Agent（同turn，过三硬门）

③ nextAction=fix OR pending非空
   → 从首个pending项继续修复

④ nextAction=verify OR 干净轮≥2
   → 确认收敛（50 Agent终验）
   → P0=0 → 写goal-reached + 输出签收单
```

### 饱和度检测信号（启发式）

1. **历史工具调用密度** — 最后 20 条消息中工具调用占比 > 70%
2. **重复模式出现** — 同一工具 + 同一参数在最近 10 次中出现 ≥ 2 次
3. **输出长度衰减** — 最后 5 条消息平均长度 < 前 5 条的 50%
4. **确认词密度** — 最近 10 条中 done/ok/final 出现 ≥ 3 次且无实质 Write/Edit
5. **上下文膨胀** — 最近 turn 中引用的不同文件/代码块 > 20 个

---

## 8. 触发词表

9 类共 60+ 短语。匹配到触发词后必须调用此 Skill：先诊断 → 写方案 → 可复制文本 → 等 Codex → 验证 → 双批准 → 执行。

### A 类 — 发送（8 个）

```
告诉codex, 发给codex, 让codex分析, 让Codex确认,
把结果告诉codex, 把方案告诉codex让他分析,
请完全遵守规则现在先告诉codex, codex帮我看下
```

### B 类 — 验证 + 审查（17 个）

```
双重检验, 双向验证, codex交叉验证, 对敲代码,
交叉验证codex, 用codex验证, codex核验, codex把关,
codex review, codex复审, 让codex审一下, 给Codex过一遍,
codex也跑一遍, 让codex看看, codex双重检查,
codex交叉审计, codex协同审查
```

### C 类 — 协作/对照（8 个）

```
帮我和codex对一下, 发给Codex审核, codex协同,
cc和codex一起修, cc和codex, 两边对照,
双向审核, 联合审查
```

### D 类 — 门控（5 个）

```
双批准, 双重批准, 双方确认后执行, codex审批, 发给codex审批
```

### E 类 — 方案/扫描（7 个）

```
多方案对比, 源文件交叉验证, deep diagnosis,
cross-verify with codex, 启动方案验证,
方案审批, 修复方案审批
```

### F 类 — AI 通用（3 个）

```
发给AI审查, 让AI也看看, 交叉检查
```

### G 类 — 全量（3 个）

```
全量扫描, full scan, codex全量
```

### H 类 — 自主迭代（9 个）

```
循环迭代, 自动更新, 自动迭代, 自主执行,
不中断, 持续修复, 自动扫描修复,
优化skill, 根据源文件优化
```

### I 类 — Agent 错误反馈（4 个）

```
agent错误, agent失败, 静默无反馈, agent报错
```

### 假阳性门控

`"双重检查"`、`"交叉审计"`、`"协同审查"` — 仅在有 `"codex"` 前缀的版本（如 `"codex双重检查"`）触发 skill 时弹出确认。无前缀的裸短语不匹配任何触发类别。

---

## 9. 外部加速 Skill

### 8 个挂点

非 10-skill 栈成员，不强制激活，卸载零影响。定位同 codex-plugin：仅替代执行/传输/验证的机械层，门控与验证深度不降，规则 1 双批准语义永不被替代。

| 挂点位置 | Skill | 用途 | 不可用回退 |
|---------|-------|------|-----------|
| STEP 1 预扫 | aislop | 50+ 反模式规则确定性检测，零 LLM 成本 | 跳过 |
| STEP 1.4 | fp-check (推断加严) | 假阳性消除 | 原路径 |
| STEP 4 | fp-check | FP 消除 | 原路径 |
| STEP 6 路由 | pantheon-fix | 复杂 P0 多候选修复 + 对抗验证 | 原路径 |
| STEP 6.0 合并前 | differential-review | 差异审查 | 原路径 |
| STEP 7 降级 | MMAR | 跨模型对抗审查 | CC 6+ Agent 自我验证 |
| STEP 7 后 | variant-analysis | 规则漂移检测 | 跳过 |
| H 类迭代 | grilling + designing-workflow-skills + agent-lint | 压力测试 + 质量轴检 + 元质量分 | 跳过/原路径 |

### 6 个已安装 Skill 利用状态

| Skill | 利用状态 | 适用场景与说明 |
|-------|---------|---------------|
| **diagramming-code** | ✅ 已集成 | 生成 SKILL.md 结构可视化（五层验证管线流程图、30 条硬规则依赖关系图） |
| **variant-analysis** | ⏳ 待试用 | SKILL.md 历史版本规则漂移检测——对比版本间的硬规则/自检/管线变更 |
| **graph-evolution** | ⏳ 待试用 | code-shiniyaya git 仓库结构 diff——追踪引用的外部文件随版本的结构演变 |
| **agentic-actions-auditor** | ⏳ 待试用 | 审计 SKILL.md 中定义的 Agent 动作权限边界与实际 hook 配置的一致性 |
| **trailmark** | ❌ 不适用 | 仅限代码仓库（Python/JS/TS 等源码）的调用图构建，不适用于 Markdown 编排文件 |
| **semgrep** | ❌ 不适用 | 仅限 Python/JS 源码的模式匹配和漏洞扫描，不适用 Markdown 规则文件 |

---

## 10. 防御栈版本表

| 组件 | 版本 | 状态 | 说明 |
|------|------|------|------|
| echo-guard.js | v4.3 | ✅ 42 测试全绿 | PreToolUse Bash 钩子，6 层防御 |
| stop-guard.js | v3.5 | ✅ 42 测试全绿 | Stop 钩子，4 道门（含 v3.5 跨 turn 污染修复） |
| bearings.js | v3.0-r9 | ✅ 42 测试全绿 | SessionStart 钩子，NEXT ACTION + STATE JSON + HookWarn |
| hooks.test.js | 42/42 | ✅ 全绿 | 回归测试套件，历史：30 → 33 → 35 → 38 → 42 |
| 硬规则 | 30 条 | ✅ 含规则 29+30 | 门控/Agent/Gap/停止线/迭代/交付/质量门控 |
| autoCompactThreshold | 55 | ✅ 平台级 | settings.json 自动压缩阈值，模型 55% 保存 + 平台 55% 压缩 |
| 干净轮计数器 | 2/2 | ✅ 已收敛 | 修复轮永不计为干净轮，≥2 才宣布收敛 |
| 五层验证管线 | L1-L5 | ✅ v4.7.10 落地 | L1 静态 → L2 AI 初审 → L3 对抗 → L4 清单 → L5 人工 |

### Hook 版本演进

```
echo-guard:  v3.0 → v3.2 → v3.3 → v3.4 → v3.5 → v3.6 → v4.0 → v4.1 → v4.2 → v4.3
stop-guard:  v2 → v3.0 → v3.2 → v3.3 → v3.4 → v3.5
bearings:    v1 → v2 → v3.0-r8 → v3.0-r9
hooks.test:  30 → 33 → 35 → 37 → 38 → 42
```

### 迭代战绩（r1-r19）

| 轮次范围 | 类型 | 关键变更 |
|---------|------|---------|
| r1-r4 | 转移包落地 | 五层管线 + 规则 29 + headroom + aislop/lint/ponytail + token 审计 |
| r5-r8 | Hook 强化 | echo-guard v3.5→v4.1 token-array, stop-guard v3.3→v3.4 |
| r9-r12 | 稳定性修复 | autoCompact 恢复 + 规则 30 + 版本全站同步 |
| r13-r16 | 对抗审计 | stop-guard v3.5 跨 turn 污染修复 + echo-guard v4.2/v4.3 + 42→全站 |
| r17-r19 | 终验修复 | 50A 2 P0 + 16 P1 全部修复 + L-line 13 处 + CHANGELOG 补全 |

---

## 11. 仓库结构

```
code-shiniyaya/
│
├── SKILL.md                          ← 主技能定义（9步闭环+30规则+五层管线+20自检）
│                                         ~1658行，117K字符
│
├── README.md                         ← 本文件（中文完整文档）
├── CHANGELOG.md                      ← 轮次级变更历史（r1-r19）
├── HOOKS-SETUP.md                    ← 新电脑部署指南（英文）
├── COMPLETE.md                       ← 完成状态报告
│
├── .claude/
│   └── settings.json                 ← 项目级配置（permissions.deny 硬规则子集）
│
├── hooks/                            ← 3 个防御 Hook（复制到 ~/.claude/hooks/ 使用）
│   ├── echo-guard.js                 ← PreToolUse Bash 钩子 v4.3
│   ├── stop-guard.js                 ← Stop 钩子 v3.5
│   └── bearings.js                   ← SessionStart 钩子 v3.0-r9
│
├── references/                       ← 测试 + 验证 + 参考
│   ├── hooks.test.js                 ← 42 用例回归测试（防御栈的规范证明）
│   ├── adversarial-55.js             ← 50 Agent 终验对抗测试
│   ├── SKILL.md                      ← 参考skill定义
│   ├── e2e-3story-test.js            ← 端到端三故事测试
│   ├── journal-parser.py             ← 日志解析器
│   ├── scan-state.schema.json        ← 扫描状态 JSON Schema
│   ├── resume-protocol.md            ← 恢复协议文档
│   ├── resume-workflow.md            ← 恢复工作流文档
│   ├── progress-tracking.md          ← 进度跟踪文档
│   ├── anti-hang-v2.md               ← 防挂起策略 v2
│   ├── time-escalation.md            ← 时间升级路径
│   ├── headroom-usage.md             ← headroom 使用指南
│   └── ...
│
├── memory/                           ← 持久记忆（快照/审计/基线/配置）
│   ├── goal-reached-v4.7.10.md       ← v4.7.10 收敛证明（P0=0, 干净轮2/2）
│   ├── snapshot-{ts}.md              ← 状态快照（max 20, min 7天保留）
│   ├── config.json                   ← 集中配置常量
│   ├── iteration-task.md             ← 迭代任务定义（活文档，地面真相）
│   ├── meta-iteration-quality.md     ← 元迭代质量追踪
│   ├── applied-patterns.md           ← 已应用自动化模式台账
│   ├── optimization-plan.md          ← 优化计划
│   ├── agent-lint-results.txt        ← agent-lint 基线分数
│   ├── aislop-results.json           ← aislop 扫描结果
│   ├── manual-verification-checklist.md  ← 人工核验清单
│   ├── symbol-impact-analysis-and-change-mapping.md  ← 符号影响分析
│   ├── autoagent-*-patterns.md       ← Agent 模式提取（5源深度扫描产出）
│   ├── autodream-*-findings.md       ← AutoDream 分析产出
│   ├── autoresearch-*-findings.md    ← AutoResearch 分析产出
│   ├── autonomous-coding-*-findings.md ← AutonomousCoding 分析产出
│   ├── bilisum-*.md                  ← BiliSum 项目分析历史
│   ├── p0-*.md                       ← P0 规则专项证明
│   ├── codex-*.md                    ← Codex 验证记录
│   ├── session-state-*.md            ← 会话状态记录
│   ├── session-summary-*.md          ← 会话总结
│   ├── 4-source-complete.md          ← 4源扫描完成报告
│   ├── high-impact-patterns.md       ← 高影响模式记录
│   └── ...
│
├── 报告/                              ← 迭代报告
│   └── iteration-reports/
│       └── iter-{N}/                 ← 每轮迭代报告
│
├── references/ponytail-*-SKILL.md    ← Ponytail 系列 Skill 参考定义
│
├── autoagent-src/                    ← AutoAgent 源文件（5源之一）
├── autodream-src/                    ← AutoDream 源文件（5源之一）
├── autoresearch-src/                 ← AutoResearch 源文件（5源之一）
├── autonomous-coding-src/            ← AutonomousCoding 源文件（5源之一）
├── ponytail-src/                     ← Ponytail 源文件（5源之一）
│
├── handoff-all-skills-to-reasonix.md ← Reasonix 交接文档
├── handover-to-reasonix.md           ← Reasonix 交接
├── handover-ack-reasonix.md          ← Reasonix 确认回执
│
├── done                              ← 标记文件
└── test_guard_bug.js                 ← 守卫测试
```

### 5 个源文件仓库

code-shiniyaya 的持续优化基于 5 个开源参考项目的深度扫描和模式提取。每个源提供了独特的自我迭代能力蓝本：

| 源 | 目录 | 核心价值 |
|----|------|---------|
| AutoAgent | `autoagent-src/` | 事件驱动自动化：GOTO/ABORT 控制流、listen_group 依赖声明、3层重试+元Agent升级 |
| AutoDream | `autodream-src/` | 记忆驱动反思：Learn+Consolidate 双阶段、checksum 幂等写入、向量记忆同步 |
| AutoResearch | `autoresearch-src/` | 自主连续性：NEVER STOP 指令、Git 状态机、固定预算、崩溃自分类 |
| AutonomousCoding | `autonomous-coding-src/` | 两阶段执行：Init+Loop 阶段、不可变检查清单、三层安全模型 |
| Ponytail | `ponytail-src/` | 极简自验证：selftest 门控、judge 裁判、debt 账本、7步阶梯 |

每轮迭代必须从至少 2 个源中提取"如何自动化自身"的模式并写入 SKILL.md。

---

## 许可证

MIT

---

> **最后更新**: 2026-07-19 | **版本**: v4.7.10-r19 | **收敛证明**: P0=0, 干净轮 2/2, hooks.test 42/42
