# Hook Installation Guide — code-shiniyaya v4.7.10

在新电脑上部署 code-shiniyaya 的三层防御 hook 系统。

## 前置条件

- Claude Code 已安装 (`npm install -g @anthropic-ai/claude-code`)
- Node.js 18+

---

## 安装

### 1. 复制 hook 文件

```bash
# 从 CLI 克隆仓库后，复制 hooks 到用户级 hooks 目录
mkdir -p ~/.claude/hooks
cp hooks/echo-guard.js ~/.claude/hooks/echo-guard.js
cp hooks/stop-guard.js ~/.claude/hooks/stop-guard.js
cp hooks/bearings.js ~/.claude/hooks/bearings.js
```

### 2. 注册 hook 到 settings.json

编辑 `~/.claude/settings.json`（若无则创建），添加如下内容：

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

> **注意**: 将 `<你的用户名>` 替换为实际用户名。Windows 路径用 `\\` 或 `/`。

### 3. 验证

```bash
# 在仓库根目录运行
node references/hooks.test.js
# 预期输出: 42 passed, 0 failed
```

### 4. 确认 hooks 生效

启动 Claude Code，检查 SessionStart hook 输出：
- 应看到 `[BEARINGS]` 或 `NEXT ACTION:` 开头的自动上下文注入
- 尝试 `echo done` → 应被 echo-guard 拦截
- 尝试无工具调用的纯确认输出 → 应被 stop-guard 拦截

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
