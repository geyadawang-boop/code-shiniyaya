---
name: bilisum-comprehensive-optimization-plan
description: BiliSum v3.0 comprehensive optimization plan covering 120+ bugs, 7 phases, 46 skills, and 6 open-source reference projects
metadata:
  type: project
---

# BiliSum v3.0 全面优化方案

## 项目概述
BiliSum 是一个基于 Electron + FastAPI 的 B站视频总结工具，支持 AI 总结、字幕提取、知识库 RAG 问答、多格式导出。
- 路径: c:\Users\shiniyaya\Desktop\cc\B站总结工具\B站视频总结工具 -cc\
- 分析规模: 42 个 Agent × 10 轮深度分析
- 总 Bug 数: 120+ (P0: 18, P1: 45+, P2: 40+, P3: 15+)
- 已修复: 12 个

## 关键发现
1. summarizer.py:318 `stream:True` + `r.json()` 使 DeepSeek/OpenAI 路径必然崩溃
2. rag_service.py:85-114 构造器死代码 — RAG 完全不可用
3. main.js:306 CDP调试端口9222暴露 (CVSS 9.8)
4. requirements.txt 缺失8个关键包 — 白板Windows无法运行
5. main.py:2268-2366 AI笔记导出8个未定义变量 — 100%崩溃
6. bilibili_client.py 字幕总是取 subs[0] 无语言选择
7. quality.py 196行完全未被集成
8. tools.html 有HTML语法错误(未闭合script标签)
9. browse.html loadDiscover() 缺else分支 → 主界面加载死循环
10. main.py:2208 `.replace('','/')` 空操作 → Obsidian URI完全损坏

## 执行计划
- P0紧急修复 (8h): requirements.txt + stream:True + RAG初始化 + AI笔记导出 + CDP端口 + 安全漏洞
- P1功能修复 (25h): 字幕语言选择 + quality.py集成 + 增强总结 + KB导入 + Obsidian修复
- P2增强 (14h): UI天空鲸鱼主题 + KB分类 + 代码质量 + 死代码清理
- 总计: ~47h

## 关键文件
- backend/main.py (2654行 — 需拆分)
- backend/summarizer.py (AI总结引擎)
- backend/bilibili_client.py (B站API客户端)
- backend/rag_service.py (RAG向量检索)
- backend/database.py (数据存储)
- backend/quality.py (质量评分 — 未集成)
- frontend/ (5个HTML页面)
- main.js (Electron主进程)

**Why:** After 10 rounds of analysis with 42 agents, this represents the most thorough audit of the BiliSum codebase.

**How to apply:** Follow the execution priority order: P0 → P1 → P2. Each phase has specific file:line fix references. Start with requirements.txt completeness check.
