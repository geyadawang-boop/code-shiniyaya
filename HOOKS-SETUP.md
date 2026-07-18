# Hook Installation Guide — code-shiniyaya v4.7.10

在新电脑上部署 code-shiniyaya 的三层防御 hook 系统。

## 前置条件

- Claude Code 已安装 (`npm install -g @anthropic-ai/claude-code`)
- Node.js 18+
- 如有现有 CC 配置，先备份 `~/.claude/settings.json`

---

## 安装

### 0. 克隆仓库和检查环境

```bash
# 克隆本仓库
git clone https://github.com/geyadawang-boop/code-shiniyaya.git
cd code-shiniyaya

# 检查 Node.js 版本（需要 18+）
node --version
```

### 1. 复制 hook 文件

```bash
# 从 CLI 克隆仓库后，复制 hooks 到用户级 hooks 目录
mkdir -p ~/.claude/hooks
cp hooks/echo-guard.js ~/.claude/hooks/echo-guard.js
cp hooks/stop-guard.js ~/.claude/hooks/stop-guard.js
cp hooks/bearings.js ~/.claude/hooks/bearings.js
```

> 如果 `~/.claude/hooks/` 已存在同名文件，建议先备份再覆盖：
> `cp ~/.claude/hooks/echo-guard.js ~/.claude/hooks/echo-guard.js.bak`

### 2. 注册 hook 到 settings.json

> **⚠️ 重要**：编辑 `settings.json` 前请**关闭** Claude Code。编辑完成后**重启** CC 使配置生效（CC 不热加载 JSON 变更）。

提供两种方案，根据你的情况选择：

---

#### 方案 A：全新安装（`~/.claude/settings.json` 不存在或为空）

> ⚠️ 注意：此方案会覆盖整个 settings.json。如果你的文件已有其他配置（模型、环境变量、MCP 插件等），请使用下方方案 B 合并插入，不要直接替换。

将以下内容完整写入 `~/.claude/settings.json`（将 `<你的用户名>` 替换为实际用户名）：

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
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/echo-guard.js\"" }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/stop-guard.js\"" }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/bearings.js\"" }
        ]
      }
    ]
  },
  "autoCompactThreshold": 55
}
```

---

#### 方案 B：已有配置（`~/.claude/settings.json` 已有 CC 配置）

先备份：`cp ~/.claude/settings.json ~/.claude/settings.json.bak`

打开 `~/.claude/settings.json`，在文件末尾的 `}` 前面插入以下内容。**注意逗号规则**：原有内容的最后一个键后面**需要加逗号**（如 `"language": "zh-CN"` → `"language": "zh-CN",`）；插入内容中 `"autoCompactThreshold": 55` 是 JSON 对象的最后一个键，后面**不要**加逗号。详见下方逗号规则说明：

```json
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
    "PreToolUse": [
      {
        "matcher": "Bash",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/echo-guard.js\"" }
        ]
      }
    ],
    "Stop": [
      {
        "matcher": "",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/stop-guard.js\"" }
        ]
      }
    ],
    "SessionStart": [
      {
        "matcher": "startup|resume|clear|compact",
        "hooks": [
          { "type": "command", "command": "node \"C:/Users/<你的用户名>/.claude/hooks/bearings.js\"" }
        ]
      }
    ]
  },
  "autoCompactThreshold": 55
```

> **逗号规则**：JSON 对象的最后一个键后面**不**加逗号，前面的键后面**必须**加逗号。
> 如果你的 `settings.json` 在插入前已有内容（比如 `model`、`env` 等），那么插入内容中 `"autoCompactThreshold": 55` 就不能加逗号（它是最后一个键）。
> 举例：如果原有文件结束于 `"language": "zh-CN"`（无逗号），插入后变成 `"language": "zh-CN",`（加逗号），后面接新内容。

---

#### 路径对照表（三平台）

将上方模板中 `C:/Users/<你的用户名>/` 替换为对应路径。**不要用记事本编辑**——记事本默认保存 UTF-16，Node.js 无法解析。请用 VS Code 或 Notepad++：

| 操作系统 | hook 文件路径示例 |
|---------|----------------|
| **Windows**（Git Bash） | `C:/Users/<你的用户名>/.claude/hooks/echo-guard.js` |
| **macOS** | `/Users/<你的用户名>/.claude/hooks/echo-guard.js` |
| **Linux** | `/home/<你的用户名>/.claude/hooks/echo-guard.js` |

> 三个 hook 文件（echo-guard.js、stop-guard.js、bearings.js）都要改，把文件名替换为对应的名字即可。以上 bash 命令请在 Git Bash 中执行，Windows 自带的 cmd.exe 不识别 `mkdir -p` 和 `~`。

---

### 3. 验证安装

```bash
# 在仓库根目录运行
node references/hooks.test.js
# 预期输出: 42 passed, 0 failed
```

> **如果测试失败**，请检查：
> 1. hook 文件是否在 `~/.claude/hooks/` 目录中（`ls ~/.claude/hooks/`）
> 2. `~/.claude/settings.json` 中的路径是否与实际文件位置一致
> 3. 路径中的用户名是否已替换
> 4. JSON 格式是否正确（可用 `node -e "JSON.parse(require('fs').readFileSync('$HOME/.claude/settings.json','utf8'))"` 验证）

### 4. 确认 hook 生效

启动 Claude Code，检查以下几点：
- 启动时应看到 `[BEARINGS]` 或 `NEXT ACTION:` 开头的自动上下文注入
- 尝试 `echo done` → 应被 echo-guard 拦截
- 尝试仅输出"done"/"ok" 无工具调用 → 应被 stop-guard 拦截

### 验证 hook 是否真的被注册（不只看测试）

```bash
# 检查 settings.json 中是否有 hook 配置
grep -c "echo-guard\|stop-guard\|bearings" ~/.claude/settings.json
# 应返回 ≥3（三个 hook 文件各匹配一次）
```

---

## 5. 故障排查

### 5.1 hooks.test.js 测试失败

执行 `node references/hooks.test.js` 如果未通过，常见原因如下：

**路径错误**：运行 `ls ~/.claude/hooks/` 确认三个 hook 文件（echo-guard.js、stop-guard.js、bearings.js）都存在。如果文件缺失，重新执行安装步骤 1。

**文件缺失**：检查是否已从仓库复制。确认当前在 `code-shiniyaya` 目录下，然后重新执行：

```bash
cp hooks/echo-guard.js ~/.claude/hooks/echo-guard.js
cp hooks/stop-guard.js ~/.claude/hooks/stop-guard.js
cp hooks/bearings.js ~/.claude/hooks/bearings.js
```

**Node.js 版本不兼容**：运行 `node --version`，确认版本 >= 18。如果版本过低，从 [nodejs.org](https://nodejs.org) 下载最新 LTS 版本。

**settings.json 中路径不一致**：打开 `~/.claude/settings.json`，对比 `command` 字段中的路径与实际 `~/.claude/hooks/` 目录中的文件名。注意斜杠方向（Windows 使用 `/` 而非 `\`）和用户名是否正确。

### 5.2 settings.json JSON 解析错误

修改 `settings.json` 后若 CC 启动报 JSON 解析错误，可用以下命令快速验证 JSON 格式：

```bash
node -e "JSON.parse(require('fs').readFileSync(require('path').join(process.env.HOME,'.claude','settings.json'),'utf8')); console.log('OK')"
```

如果输出 `OK` 则表示 JSON 格式正确；如果抛出异常，错误信息会指示具体位置（行号 + 列号）。

**常见 JSON 格式错误**：
- **多余的逗号**：JSON 不允许最后一个键后面有逗号。例如 `"autoCompactThreshold": 55,` 应改为 `"autoCompactThreshold": 55`（去掉末尾逗号）。
- **缺少逗号**：非最后一个键后面缺少逗号会导致解析失败。
- **花括号不匹配**：检查 `{}` 是否成对，尤其是手动编辑插入内容后容易漏掉闭合花括号。
- **引号问题**：所有键和字符串值必须使用**双引号**，单引号不被 JSON 标准接受。
- **转义问题**：路径中的反斜杠 `\` 必须写为 `\\`，但使用 `/` 更简洁且不需要转义。

### 5.3 Hook 已注册但不生效

当 `settings.json` 配置正确、JSON 解析通过，但 CC 启动时未见 hook 行为，按以下顺序排查：

**CC 版本是否支持 hooks**：Hooks 功能需要 Claude Code >= 0.1.20。运行以下命令检查版本：

```bash
npx @anthropic-ai/claude-code --version
```

如果版本过低，运行 `npm update -g @anthropic-ai/claude-code` 升级。

**settings.json 是否保存成功**：确认修改已写入磁盘：

```bash
cat ~/.claude/settings.json | grep -c "hooks"
```

若返回 0，说明文件未保存或 hooks 块未写入。

**CC 是否已重启**：编辑 `settings.json` 后必须**完全关闭并重新启动** Claude Code。CC 不会热加载 `settings.json` 的变更。

**hook 文件是否可执行**：确认 Node.js 可以执行 hook 文件：

```bash
node ~/.claude/hooks/echo-guard.js
```

应输出 `[]` 或类似 JSON 响应。如果报错，检查文件是否有语法错误。

### 5.4 中文编码问题

Windows 系统上最常见的错误来源之一。

**记事本陷阱**：Windows 自带记事本保存文件时默认使用 **UTF-16 LE (UCS-2 LE)** 编码。Node.js 的 `JSON.parse()` 只支持 **UTF-8**，导致即使 JSON 格式完全正确也会解析失败。

**症状**：
- `settings.json` 在记事本中打开显示正常
- Node 验证命令报 `JSON.parse` 错误
- 但在 VS Code 右下角会显示编码为 `UTF-16 LE` 而非 `UTF-8`

**解决方案**：
1. 使用 **VS Code** 或 **Notepad++** 编辑 `settings.json`，不要用记事本
2. 在 VS Code 中打开文件后，检查右下角编码指示器是否为 `UTF-8`
3. 如果不是，点击编码选择 "Save with Encoding" -> "UTF-8"
4. 或者在 VS Code 中按 `Ctrl+Shift+P`，输入 `Change File Encoding`，选择 `UTF-8`

**验证编码是否正确**：

```bash
node -e "const fs=require('fs'),buf=fs.readFileSync(require('path').join(process.env.HOME,'.claude','settings.json')); console.log('BOM:',buf[0].toString(16),buf[1].toString(16)); if(buf[0]===0xFF&&buf[1]===0xFE)console.log('DETECTED: UTF-16 LE — 请使用 VS Code 另存为 UTF-8'); else if(buf[0]===0xEF&&buf[1]===0xBB)console.log('UTF-8 with BOM (一般可正常解析)'); else console.log('OK: 编码看起来正确')"
```

---

## 卸载

```bash
rm ~/.claude/hooks/echo-guard.js
rm ~/.claude/hooks/stop-guard.js
rm ~/.claude/hooks/bearings.js
# 并从 settings.json 中移除 hooks 块
```

---

## 架构图

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

## 未来规划

### 6.1 跨平台原生路径简化

当前所有 hook 配置中的路径使用硬编码绝对路径（如 `C:/Users/<用户名>/.claude/hooks/echo-guard.js`），在新电脑部署时需要手动替换用户名，容易出错。

**计划方案**：利用 Claude Code 的环境变量机制，使 hook 路径支持 `$HOME` 或 `%USERPROFILE%` 环境变量引用。例如：

```json
{ "type": "command", "command": "node \"$HOME/.claude/hooks/echo-guard.js\"" }
```

目前 CC 的 settings.json 是否支持环境变量展开取决于版本，未来将提供兼容性矩阵，并为每个主流操作系统各提供一套免修改的默认配置。

### 6.2 一键安装脚本

为降低部署门槛，计划提供跨平台一键安装脚本：

- **Windows**: `install-hooks.bat` — 自动检测用户目录、复制 hook 文件、备份旧 settings.json、合并 hooks 配置、验证安装。
- **macOS / Linux**: `install-hooks.sh` — 同上，使用 POSIX shell 实现，兼容 bash / zsh。
- **Node.js 通用版**: `install-hooks.js` — 一个 Node 脚本跨平台运行，无需区分操作系统。

脚本将包含以下能力：
- 自动检测现有 `settings.json` 并安全合并（不覆盖已有配置）
- 交互式确认是否覆盖已有 hook 文件
- 安装完成后自动运行 `hooks.test.js` 验证
- 失败时给出明确的错误信息和修复指引

### 6.3 开源社区贡献指南

本项目欢迎社区贡献。如果你有兴趣参与，请遵循以下规范：

**报告问题 (Issues)**：
- 使用 GitHub Issues 提交 bug 报告或功能请求
- 标题格式：`[hooks] 简要描述` 或 `[docs] 简要描述`
- 描述中注明操作系统、CC 版本、Node.js 版本
- 附上相关错误输出或日志

**提交代码 (Pull Requests)**：
1. Fork 本仓库并创建特性分支：`git checkout -b feat/hooks-xxx`
2. 确保通过所有测试：`node references/hooks.test.js`
3. 为新增功能编写对应的测试用例（在 `references/hooks.test.js` 中添加）
4. 提交 PR 时注明变更类型：`feat` / `fix` / `docs` / `chore`
5. 等待 review，根据反馈修改

**代码风格**：
- Hook 脚本使用 ES2021+ 语法，Node.js 原生模块（不引入 npm 依赖）
- 使用 `'use strict'` 严格模式
- 所有错误使用英文抛出，便于日志聚合
- 关键逻辑添加中文注释，便于维护者理解

**行为准则**：
- 保持友好和建设性的沟通
- 关注代码质量而非数量
- 尊重项目现有的架构设计和命名约定
