---
name: six-skill-stack
description: 10-skill强制激活栈用于code-shiniyaya开发 — 6个ponytail子插件+caveman+using-superpowers+openspec-explore+code-shiniyaya自身
metadata:
  type: project
---

code-shiniyaya v4.6.7开发必须同时激活10个skill:

| # | Skill | 级别 |
|---|-------|------|
| 1 | code-shiniyaya | 编排器 |
| 2 | ponytail | ultra |
| 3 | caveman | full |
| 4 | ponytail-review | 审查 |
| 5 | ponytail-audit | 审计 |
| 6 | ponytail-debt | 债务追踪 |
| 7 | ponytail-gain | 计量 |
| 8 | ponytail-help | 参考 |
| 9 | using-superpowers | 触发守卫 |
| 10 | openspec-explore | 探索 |

**Why:** ponytail子skill审核/审计/债务/计量机制是code-shiniyaya自迭代质量保证的必须组成部分。caveman压缩输出, using-superpowers防止遗漏触发, openspec-explore提供结构化探索。

**How to apply:** 每次对话开始确认全部激活。缺失skill→从C:\Users\shiniyaya\Desktop\code-shiniyaya\ponytail-src\skills\读取并安装到C:\Users\shiniyaya\.claude\skills\。配置参考ponytail-help。

优先级链: code-shiniyaya > ponytail > using-superpowers > caveman > ponytail-review/audit/debt/gain/help > openspec-explore

冲突裁决: 安全/正确性 > 极简。信任边界永不简化。

相关: [[code-shiniyaya-skill-optimization]] [[ponytail-source]]
