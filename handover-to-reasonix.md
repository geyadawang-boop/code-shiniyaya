# code-shiniyaya v4.7.5 交接文档

**生成时间**: 2026-07-17
**生成会话**: 599a9a0b-b50c-408a-8971-13091a6783bd
**目标接收方**: Reasonix

---

## 1. 项目概览

| 项目 | 说明 |
|------|------|
| **名称** | code-shiniyaya — CC↔Codex 双向验证元编排 Skill |
| **版本** | v4.7.5 |
| **本地根目录** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\` |
| **核心文件** | `SKILL.md` (~1724行) |
| **GitHub** | https://github.com/geyadawang-boop/code-shiniyaya.git |
| **Git分支** | HEAD (main) |
| **最近提交** | `008451a` — v4.7.5 fix: 饱和度信号诚实标注+turn终止诚实标注+自检标注NON-VIABLE |
| **对话工作目录** | `D:\.claude` |
| **记忆目录** | `C:\Users\shiniyaya\.claude\projects\D--\memory\` |

## 2. 核心文件索引

### 主文件

| 文件 | 绝对路径 | 说明 |
|------|----------|------|
| **SKILL.md** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\SKILL.md` | 主Skill定义，~1724行，26条硬规则+18项自检+24反模式 |
| **CHANGELOG.md** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\CHANGELOG.md` | 版本演化记录 (v4.7.0 → v4.7.5) |
| **config.json** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\config.json` | 集中配置 (Agent/静默/截断/预算/反思参数) |
| **snapshot** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\snapshot-20260717T013659.md` | 会话快照 (可能过时) |
| **.gitignore** | `C:\Users\shiniyaya\Desktop\code-shiniyaya\.gitignore` | 含 `*-src/` 排除源码归档 |

### 记忆文件 (124个 .md)

`C:\Users\shiniyaya\Desktop\code-shiniyaya\memory\` 下关键文件:

| 文件 | 说明 |
|------|------|
| `reference-sources-v2.md` | 4个新增开源参考源 (AutoAgent/autodream/autoresearch/autonomous-coding) |
| `reference-sources.md` | 全部41个参考源清单 |
| `all-active-rules.md` | BiliSum全部活跃规则一览(22条) |
| `iteration-task.md` | 迭代任务规格+未扫描文件列表 |
| `optimization-plan.md` | 优化计划 (7大方向) |
| `meta-iteration-quality.md` | 元迭代质量评分 |
| `memory-isolation-rule.md` | 记忆隔离规则 |
| `code-shiniyaya-skill-optimization.md` | Skill优化记录 |

## 3. 全局配置 (Claude Code settings)

**文件**: `C:\Users\shiniyaya\.claude\settings.json`

```json
{
  "env": {
    "ANTHROPIC_AUTH_TOKEN": "PROXY_MANAGED",
    "ANTHROPIC_BASE_URL": "http://127.0.0.1:15721",
    "ANTHROPIC_DEFAULT_OPUS_MODEL": "claude-opus-4-8[1M]",
    "ANTHROPIC_DEFAULT_SONNET_MODEL": "claude-sonnet-4-6[1M]",
    "ANTHROPIC_DEFAULT_FABLE_MODEL": "claude-fable-5[1M]",
    "ANTHROPIC_DEFAULT_HAIKU_MODEL": "claude-haiku-4-5"
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

**关键信息**:
- API代理地址: `http://127.0.0.1:15721`
- 后端模型名: `deepseek-v4-pro` (所有4个Claude模型共用此实际模型)
- 默认模型: opus
- PreToolUse Bash hook: **echo-guard.js** (v1.0, 刚安装，需重启CC生效)

## 4. 5个开源参考源 (read-only，仅提取模式)

| # | 项目 | 源路径 | 星数 | 核心价值 | 已提取模式 |
|---|------|--------|------|----------|-----------|
| 1 | **AutoAgent** (HKUDS) | `autoagent-src/` | 9,468 | 事件驱动DAG引擎, Hub-and-Spoke, 3-Tier重试 | 19 |
| 2 | **autodream** | `autodream-src/` | 19 | LLM合成, 双重记忆, 两阶段反思, grounding归因 | 19 |
| 3 | **autoresearch** (Karpathy) | `autoresearch-src/` | 91,221 | Git状态机, 崩溃分类, 固定预算, TSV日志 | 13 |
| 4 | **autonomous-coding** (Anthropic) | `autonomous-coding-src/` | 17,248 | Init+Loop, 不可变清单, ThinkTool, 轨迹记录 | 14 |
| 5 | **ponytail** | `C:\Users\shiniyaya\.claude\skills\ponytail\` | — | YAGNI七步阶梯, ponytail:debt标注, 三重强度 | 17 |

**总计**: 82个已提取模式，已集成到SKILL.md的功能约~45项，其余待CC平台能力升级。

## 5. 10-Skill协同开发栈 (每次对话强制激活)

```
优先级链: code-shiniyaya(编排) > ponytail(极简) > using-superpowers(触发)
  > caveman(输出) > ponytail-review/audit/debt/gain/help(审查层)
  > openspec-explore(探索)
```

| # | Skill | 级别 | 职责 |
|---|-------|------|------|
| 1 | code-shiniyaya | 编排器 | 8步闭环+26条硬规则+18项自检+5源+ponytail七步阶梯+Hook基础设施 |
| 2 | ponytail | ultra | YAGNI极端主义: 删除优先→七步阶梯→ponytail:debt标注 |
| 3 | caveman | full | 输出压缩: 丢弃冠词/填充词/客套话 |
| 4 | ponytail-review | 审查 | 过度工程审查: delete/stdlib/native/yagni/shrink标签 |
| 5 | ponytail-audit | 审计 | 全仓过度工程审计 |
| 6 | ponytail-debt | 债务追踪 | ponytail: 注释收割→债务账本 |
| 7 | ponytail-gain | 计量 | 基准中位分板: LOC/net/token/cost |
| 8 | ponytail-help | 参考 | 全ponytail模式/子skill/配置快查 |
| 9 | using-superpowers | 触发守卫 | 任何操作前检查skill适用性 |
| 10 | openspec-explore | 探索 | 思考不实现, 可视化, 质疑假设 |

## 6. SKILL.md 核心架构

### 8步工作流 (STEP 0-7)

```
STEP 0: 冷启动 — 三Skill前置 + 环境检测 (python环境能力检测)
STEP 1: 诊断 — 6+ Agent并行 (5类型: investigator/general-purpose/Plan/debugging/Explore)
STEP 2: 方案生成 — ponytail七步阶梯检查→生成方案→Codex审查
STEP 3: 发送Codex — 纯文本格式, 消毒流水线 (Bidi→NFKC→零宽→Null→C0/C1)
STEP 4: Codex验证 — /codex:review + /codex:adversarial-review (10+ Agent)
STEP 5: 双批准门控 — 用户+Codex双重批准, 降级模式用户单批准
STEP 6: 执行修复 — Git分支隔离, 预算管理, 独立并行修复
STEP 7: 双向验证 — CC验证Codex修复 + Codex验证CC修复, 1轮终止除非有争议
STEP 8: Learn+Consolidate — MD5变更检测, 孤儿记忆检测, 反思触发
```

### 26条硬规则 (关键摘录)

- **规则1**: 双批准门控 — 用户+Codex都批准才能执行
- **规则15**: 禁止无产出用户可见消息 — CC不可输出分析/汇报文本到用户
- **规则20**: P0验证规格 — 非降级2 Agent / 降级4 Agent
- **规则26**: 无意义输出循环阻断 — Read/Grep/Bash/wc/确认词/Wr↔Rd循环阻断 (HARD)
- **规则27**: 报告路径权威定义
- **规则28**: Codex消息可复制 — 纯文本, `=`分隔, 无Markdown表格

### 18项自检 + 24反模式

自检覆盖: 工作流通知处理、不等待、不静默、工作流存活、循环持续、有意义迭代、任务保真、时间预算、元迭代完整性、稳定性积累、任务规格锁定、Agent卡住处理、4源深度利用、产出物写入、自我迭代提取、源文件旋转、报告路径、可运行边界、框架兼容、多Agent规格。
反模式覆盖: 单源诊断、单Agent、5-文案、无方案执行、盲信Codex（#1-#6最致命）。

### 关键防御机制

```
死循环三层防御:
  L1: 规则26 (事后阻断 - 同turn内文件/pattern/确认词循环检测)
  L2: PreToolUse echo-guard.js (平台止损 - echo空值阻断 + >8 Bash/turn上限)
  L3: 一字恢复 (事后恢复 - 55%饱和度→保存snapshot→/compact→用户"继"恢复)

上下文感知防饱和:
  55%阈值: 保存snapshot+git commit → "⚡ 55% — /compact + 继"
  一字恢复流程: ls snapshot-*.md → 读CHANGELOG → 4 Agent精简扫描 → 续取任务
```

## 7. 已安装工具/插件

| 工具 | 说明 | 安装位置 |
|------|------|----------|
| **RTK** (Rust Token Killer) | Token优化CLI代理 (60-90%节省) | `which rtk` 验证 |
| **codex-plugin-cc** | OpenAI Codex双向通信插件 | `C:\Users\shiniyaya\.claude\plugins\marketplaces\openai-codex-plugin-cc\` |
| **caveman** | 输出压缩模式 + SessionStart hook | `C:\Users\shiniyaya\.claude\skills\caveman\` |
| **echo-guard.js** | PreToolUse Bash hook (v1.0) | `C:\Users\shiniyaya\.claude\hooks\echo-guard.js` |

**Codex插件可用命令**:
- `/codex:review` — 只读审查uncommitted变更
- `/codex:adversarial-review` — 对抗性审查
- `/codex:rescue` — 委派bug修复给Codex子Agent
- `/codex:transfer` — CC会话转持久Codex线程
- `/codex:setup` — 初始化设置
- `/codex:status` — 查看状态
- `/codex:cancel` — 取消运行中任务

**echo-guard.js 拦截规则**:
1. 空/占位 echo: `echo ""`, `echo "done"`, `echo "ok"`, `echo "1"`, `echo "2"`, `echo final/complete/verified/confirmed` + 纯数字
2. wc -l 同文件两次同一turn → 阻断
3. >8次Bash调用/turn → 阻断
4. 30s空闲 = 新turn，计数器归零

## 8. Gateway端口与API

| 配置项 | 值 |
|--------|-----|
| **API代理** | `http://127.0.0.1:15721` |
| **认证** | PROXY_MANAGED (由代理处理) |
| **后端实际模型** | `deepseek-v4-pro` |
| **Git代理** | `127.0.0.1:7897` |
| **模型映射** | Claude Opus/Sonnet/Fable/Haiku → 全部路由到 deepseek-v4-pro |

## 9. 当前会话状态

- **CLAUDE.md** (全局): `@RTK.md`
- **CAVEMAN MODE**: full (ACTIVE)
- **PONYTAIL MODE**: ultra (ACTIVE)
- **Ultracode**: ON
- **会话ID**: `599a9a0b-b50c-408a-8971-13091a6783bd`
- **Git状态**: clean (所有修复已提交)
- **最近提交(10条)**:
  ```
  008451a v4.7.5 fix: 饱和度信号+turn终止诚实标注+自检NON-VIABLE+恢复ls snapshot+自检#1(d)
  db98734 v4.7.5: 主任务栏同步工作机制 — Agent并行时CC做有产出的事，杜绝echo循环
  0befdc7 v4.7.5 opt: ponytail:debt footer updated — 行号→§锚点
  23cdfa7 v4.7.5 opt: 机制可行性矩阵 行号→§锚点 + 反映v4.7.5降级状态
  30a6ed2 v4.7.5 opt: remove duplicate 每次执行 line from STEP 6.1
  a6f8093 v4.7.5 opt: L3 Bash shell注入防御
  8c58ae9 v4.7.5 opt: 自检#13/#16/规则27去重合并 → 规则27为报告路径权威定义
  000f3b1 v4.7.5 fix: final 2 P1 — 预算90%→完全耗尽 + 自检#18(c)(d)标注跨turn不可行
  b8c68fd v4.7.5 fix: 4 P1 resolved — 规则15+自检#1-4+自检#11降级为turn感知
  e4ad326 v4.7.5 fix: remove phantom 5-minute auto-approval timer (CC has no daemon)
  ```

## 10. 已知未完成事项

| # | 事项 | 优先级 | 状态 |
|---|------|--------|------|
| 1 | **echo-guard.js 需重启CC验证** | HIGH | Hook已安装到settings.json，文件已写入，但CC未重启→未实际生效 |
| 2 | **echo循环持续发生** | CRITICAL | 根因=LLM验证强迫吸引子，文本规则无法完全阻断。echo-guard.js从平台层阻断，需验证 |
| 3 | **snapshot过时** | MEDIUM | 最新快照仍是v4.7.3状态，未反映v4.7.5多次提交 |
| 4 | **5个后台Agent未完成** | LOW | 上次会话遗留: 终确认: P2债务全部清零 + 交叉验证6/7/8/10。可通过SendMessage恢复 |
| 5 | **PreToolUse hook旧残留** | LOW | `/tmp/.cc_bash_*.json` 旧计数器文件(391/164次)不再使用但未清理 |
| 6 | **入口路由表触发词数量** | LOW | metadata说"7 categories"，实际定义9类(A-I)，不一致 |
| 7 | **STEP 7终止未定义post-dispute** | LOW | 争议后无明确过渡→可能无限循环 |
| 8 | **STEP 4 plugin模式验证路径不明确** | LOW | plugin模式是否走10+ Agent验证管道未说明 |

## 11. 关键注意事项 (给Reasonix)

### CC架构根本限制
- **请求-响应模型**: Claude不能跨turn自主执行，不能给自己发消息，无守护进程
- **无事件循环**: 不能主动轮询Agent状态，不能后台自主等待
- **无token计数API**: 上下文饱和度只能启发式估算 (versionVector × 12%)
- **/compact是终端命令**: AI不能通过工具调用触发压缩，必须用户手动执行

### 防echo循环的根本逻辑
文本规则（规则26/自检#18/主任务栏工作）在此问题上不可靠——模型进入验证强迫吸引子时，执行检查的认知能力已被循环劫持。**唯一有效措施是平台层阻断**（echo-guard.js在Bash调用前拦截）。不要试图通过SKILL.md文本规则来彻底解决这个问题。

### 恢复机制
用户只需输入一个字 **"继"** 即可触发完整恢复流程：读最新snapshot → 读CHANGELOG → 4 Agent完整性扫描 → 从上次中断点续取任务。不要忘记这个触发词。

### Git操作
- Push可能因网络(代理127.0.0.1:7897)失败→snapshot本地保存即安全，push非必须
- origin = `https://github.com/geyadawang-boop/code-shiniyaya.git` (不是BiliSum!)
- 每次修改前确认 `git remote -v`

## 12. 快速恢复步骤

```
1. 重启 Claude Code (使echo-guard.js生效)
2. 确认环境: git remote -v → 应指向 code-shiniyaya
3. 输入"继" → 触发一字恢复 → 自动从snapshot续取
4. 检查 CHANGELOG.md 了解上次进度
5. 如需继续优化: "根据源文件优化skill" 触发H类自主迭代
```

---

**文档结束** | 如需任何字段的详细内容，查阅对应的源文件路径即可。
