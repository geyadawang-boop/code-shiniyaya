---
name: bilisum-remaining-deferred
description: BiliSum 3 remaining deferred tasks post-optimization
metadata:
  type: project
---

## BiliSum 剩余待办项 (2026-07-08)

优化全部完成（73/73 验证通过，74 路由，18 Python 文件编译通过），剩余 3 项推迟：

### 1. main.py 路由去重
- **现状**：main.py 中的旧路由定义与 routers/ 中的新路由定义重复注册（每个路由 2 个副本，共 139 条注册 vs 74 条独立路由）
- **影响**：FastAPI 使用第一个匹配的路由，功能正常，但代码不干净
- **工作量**：约 2 小时，从 main.py 中批量移除已在 routers/ 中定义的路由

### 2. MCP Server 模式
- **现状**：未启动，零代码
- **内容**：实现 MCP (Model Context Protocol) 适配器，让 BiliSum 可作为外部 AI 工具被调用
- **工作量**：约 200 行新代码 + 设计讨论

### 3. E2E 测试（Playwright）
- **现状**：未启动，零代码
- **内容**：搭建 Playwright 测试框架，编写关键用户流程的端到端测试（总结、知识库、RAG 问答）
- **工作量**：独立项目，建议功能稳定后单独进行

**Why:** 全面优化完成后，这 3 项是仅剩的未完成工作。路由去重是代码清理，MCP 是新功能，E2E 测试是质量保障——各有独立的时间节点。

**How to apply:** 用户提及 "之前推迟的那三项" 或 "BiliSum 剩下的工作" 时提醒。
