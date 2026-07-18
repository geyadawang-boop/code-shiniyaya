# code-shiniyaya v4.7.10 — CC ↔ Codex 双向验证编排器

CC 与 OpenAI Codex 之间的标准化双向验证闭环。CC 负责深度诊断（读源码 + 6+ Agent 并行扫描），Codex 负责独立验证（交叉检查 CC 方案），双方都批准后才执行。

```
不是"让 AI 写代码"——是"让两个 AI 系统互相验证对方的工作"
```

**GitHub**: https://github.com/geyadawang-boop/code-shiniyaya

---

## 快速部署

```bash
# 1. 克隆
git clone https://github.com/geyadawang-boop/code-shiniyaya.git
cd code-shiniyaya

# 2. 安装 hooks（3 个防御钩子）
mkdir -p ~/.claude/hooks
cp hooks/echo-guard.js ~/.claude/hooks/echo-guard.js
cp hooks/stop-guard.js ~/.claude/hooks/stop-guard.js
cp hooks/bearings.js ~/.claude/hooks/bearings.js

# 3. 注册 hook 到 settings.json（见 HOOKS-SETUP.md）

# 4. 验证
node references/hooks.test.js
# → 42 passed, 0 failed
```

> 整个 skill = 一个 SKILL.md 文件 + 3 个 hook + 测试验证。零外部依赖，零 API key（Codex 为可选）。

---

## 核心功能

### 1. 三层防御 Hook（平台级，不依赖模型）

| 层 | Hook | 版本 | 功能 |
|----|------|------|------|
| **PreToolUse** | echo-guard.js | v4.3 | Bash 命令实时拦截：无意义 echo、wc -l 循环、8次/turn上限、指纹阶梯 |
| **Stop** | stop-guard.js | v3.5 | Turn 终态审查：纯确认拦截、干净轮停滞、伪发射、签收无 snapshot |
| **SessionStart** | bearings.js | v3.0-r9 | 自动注入上下文：NEXT ACTION、STATE JSON、hook 注册丢失检测 |

**echo-guard 核心能力**：
- 拦截 `echo done/ok/final` → deny 拒绝
- 同 turn 同文件重复 `wc -l` → deny 拒绝
- 非豁免 Bash 8 次/turn 上限 → deny 拒绝
- `find -delete` / `sort -o` / `find -execdir` 破坏性 flag → 捕获
- 文件指纹归一化：`rm a.mp4` / `rm b.mp4` → 同指纹 → 第4次 deny

**stop-guard 核心能力**：
- 纯确认 turn（≥2 确认词 + 零 Write/Edit/Agent）→ block
- 干净轮 <2 未发射 Agent → block
- "第N轮→继"伪发射 → block
- 签收声明无 snapshot → block
- `⚡.../compact` 饱和豁免 / `\bstop\b` 用户中断放过

### 2. 30 条硬规则

| 类别 | 条数 | 关键规则 |
|------|------|---------|
| 门控 | 4 | 双批准门控、CC 不独立改源码、分析自由修改阻断、stop 优先 |
| Agent | 4 | 批次上限 4-16、语法门控、3 层失败重试、无共享文件 |
| Plan-Code Gap | 3 | git diff+grep 双验证、方案锁定、Read 前禁写 |
| 停止线 | 7 | 3次失败崩溃分类、stop 立即停、修复优先、迭代不中断、7方向覆盖 |
| 迭代 | 8 | 输出不阻断、P0 验证规格化、趋势确认、模式自我应用、防卡顿并行、收敛阈值 |
| 交付 | 2 | 报告路径统一、Codex 消息消毒 |
| 质量 | 2 | **规则29** TDD 契约前置 + **规则30** 全站交叉一致性审计 |

### 3. 五层验证管线（L1-L5）

```
L1 静态检测(aislop/agent-lint/hooks.test 42/42)
  → L2 AI初审(6+ Agent 4维度并行)
    → L3 对抗验证(pantheon/MMAR/PAR)
      → L4 清单驱动(28规则↔20自检映射)
        → L5 人工核验(用户+Codex双批准)
```

### 4. 自主迭代模式

触发词：循环迭代/自动更新/自动扫描修复/优化skill

工作流：
1. 分析需求 → 写迭代计划
2. **(A) 发射 Workflow/Agent** → **(B) snapshot + git commit** → **(C) 输出进度行**
3. 同 turn 预发射：Agent 飞后不等"继"直接启动下一轮
4. **干净轮计数器**：仅 0 P0+P1 且无修复的轮才算干净，≥2 轮才宣布收敛
5. 收敛 → 50 Agent 终验 → P0=0 → 签收单（强制模板）

### 5. 上下文防饱和 + 一字恢复

- **autoCompactThreshold: 55**：上下文 ≥55% 平台自动 /compact
- **模型侧互补**：55% 时写 snapshot + git commit + 输出 `⚡.../compact + 继`
- **恢复**：用户"继" → 读最新 snapshot → nextAction 决策（await/scan/fix/verify）
- **快照保留**：max 20，min 7 天，原子写入 + 哨兵行

### 6. 外部看门狗全栈

```
L1 文本规则(规则26) ── 同turn自查，吸引子状态失效
  ↓
L2 平台阻断 ── echo-guard v4.3 + stop-guard v3.5
  ↓
L2.5 permissions.deny ── settings.json 声明式拒绝
  ↓
L3 一字恢复 ── snapshot + git + 用户"继"
```

### 7. 触发词（60+ 短语 / 9 类）

| 类 | 示例 |
|----|------|
| 发送 | "告诉codex"、"让codex分析" |
| 验证 | "双重检验"、"codex review"、"交叉验证" |
| 协作 | "两边对照"、"cc和codex一起修" |
| 门控 | "双批准"、"codex审批" |
| 方案 | "多方案对比"、"deep diagnosis" |
| 全量 | "full scan"、"全量扫描" |
| 自主迭代 | "自动迭代"、"优化skill"、"自动扫描修复" |

### 8. 6 个已安装 Skill 利用

| Skill | 利用状态 | 用途 |
|-------|---------|------|
| diagramming-code | ✅ 已集成 | SKILL.md 结构可视化 |
| variant-analysis | ⏳ 待试用 | 规则漂移检测 |
| graph-evolution | ⏳ 待试用 | 仓库结构 diff |
| agentic-actions-auditor | ⏳ 待试用 | 权限边界审计 |
| trailmark | ❌ 不适用 | 仅代码仓库 |
| semgrep | ❌ 不适用 | 仅源码匹配 |

---

## 防御栈版本

| 组件 | 版本 | 状态 |
|------|------|------|
| echo-guard | v4.3 | ✅ 42 测试 |
| stop-guard | v3.5 | ✅ 42 测试 |
| bearings | v3.0-r9 | ✅ 42 测试 |
| hooks.test | 42/42 | ✅ 全绿 |
| 硬规则 | 30 条 | ✅ 含规则29+30 |
| autoCompactThreshold | 55 | ✅ 平台级 |
| 干净轮 | 2/2 | ✅ 已收敛 |

---

## 仓库结构

```
code-shiniyaya/
├── SKILL.md              ← 主技能定义（9步闭环+30规则+管线）
├── README.md             ← 本文件
├── CHANGELOG.md          ← 轮次级变更历史（r1-r19）
├── HOOKS-SETUP.md        ← 新电脑部署指南
├── .claude/
│   └── settings.json     ← 项目级配置（permissions.deny）
├── hooks/                ← 3个防御hook（复制到 ~/.claude/hooks/ 使用）
│   ├── echo-guard.js     ← PreToolUse Bash钩子 v4.3
│   ├── stop-guard.js     ← Stop钩子 v3.5
│   └── bearings.js       ← SessionStart钩子 v3.0-r9
├── references/           ← 测试+验证+参考
│   ├── hooks.test.js     ← 42用例回归测试
│   ├── adversarial-55.js ← 50A终验对抗测试
│   └── ...
├── memory/               ← 持久记忆（快照/审计/基线）
│   ├── goal-reached-v4.7.10.md  ← 收敛证明
│   ├── snapshot-*.md     ← 状态快照
│   └── ...
└── 报告/                 ← 迭代报告
    └── iteration-reports/
```

---

## 许可证

MIT
