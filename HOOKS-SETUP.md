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
