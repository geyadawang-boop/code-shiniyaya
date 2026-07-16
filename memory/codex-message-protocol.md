# 给 Codex 发信息时的规则

## 触发条件
用户说 "发给 codex"、"需要告诉 codex"、"发给 Codex" 等时触发

## 规则
1. 提供**完整可复制文本**，用户可以直接 Ctrl+C / Ctrl+V 转发
2. 文本包含以下要素：
   - 源文件读取路径（桌面 DOCX + review/ MD）
   - 源码根目录
   - 详细任务要求（按 Parts A-I 组织）
   - 执行阶段（Phase A/B/C/D）
   - 每个任务的风险评估和具体修复代码
   - 要求 Codex 启动自己的子 Agent 独立分析
   - 要求 Codex 合并方案后反馈 CC 最终确认
3. 文本中不包含 markdown 表格（plain text 更易复制）
4. 关键规则必须醒目标注：
   - 严禁 PowerShell Set-Content
   - 必须使用 Python open(encoding="utf-8")
   - 每步验证 ast.parse + import backend.main
   - 不得使用 bash 管道重定向写 .js 文件
5. 要求 Codex 启动至少 6 个不同维度、不同类型的子 Agent 独立分析，不追求秒回，追求深度和准确性
6. Codex 需合并方案后反馈 CC 最终确认

## 格式示例
```
Codex，

[内容...]

读取清单：
  桌面 DOCX: C:\Users\...\xxx.docx
  Review MD: C:\Users\...\review\xxx.md
  源码根目录: C:\Users\...\cc\...\

执行流程: [5步]
Part A-I: [9个领域摘要]
Phase A/B/C/D: [优先级表]
关键规则: [标注]
```
