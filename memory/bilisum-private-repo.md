---
name: bilisum-private-repo
description: 私人仓库同步记录 — https://github.com/geyadawang-boop/BiliSum- (v9.0完整源码+记忆+规则+参考)
metadata:
  type: reference
  created: 2026-07-16
  repo: https://github.com/geyadawang-boop/BiliSum-
  status: synced
---

# 私人仓库同步记录

- 仓库: https://github.com/geyadawang-boop/BiliSum-
- 分支: main
- 最后推送: 2026-07-16 (2次commit)

## Commit历史

| Commit | 内容 |
|--------|------|
| `dada15a` | v9.0 完整源码: backend 67.py + frontend 17文件 + preload/main.js + 根配置 |
| `c488dc6` | v9.0 完整记忆: 22条规则 + 120记忆文件 + 6 ponytail skill + DOCX |

## 仓库结构

| 目录 | 内容 | 大小 |
|------|------|------|
| backend/ | 后端源码 (147文件, 67 Python) | 5.4MB |
| frontend/ | 前端页面+CSS+JS (17文件) | 492KB |
| memory/ | 全部活跃记忆 (120 Markdown) | 1.5MB |
| references/ | 技能定义+参考文档 (13文件) | 188KB |
| 根目录 | .gitignore, requirements.txt, package.json, preload.js, main.js, 启动脚本 | — |

## 回退方法

```bash
git clone https://github.com/geyadawang-boop/BiliSum-.git
cd BiliSum-
# 回退到记忆同步点(不含源码):
git checkout c488dc6
# 回退单个文件到记忆同步点:
git checkout c488dc6 -- memory/
# 回退到源码之前的commit:
git checkout c488dc6~1
```

总计250个跟踪文件，7.6MB。

## 关联记忆
- [[bilisum-v9.0-execution-plan]]
- [[bilisum-v8.7-session-state]]
