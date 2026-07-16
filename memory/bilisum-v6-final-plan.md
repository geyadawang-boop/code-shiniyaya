---
name: bilisum-v6-final-plan
description: BiliSum v6.0 全面优化计划 — 18个Agent深度扫描汇总，180+Bug，52个可导入Skill，7条交叉利用链，8个执行阶段
metadata: 
  node_type: memory
  type: project
  originSessionId: c55432b9-b150-4e75-a646-77c692ab1fb0
---

# BiliSum v6.0 全面优化计划

> 生成时间：2026-07-10
> 扫描方法：18个并行Agent（6 Skill读取 + 12 Bug扫描）
> 发现Bug总数：180+（P0:32, P1:58, P2:55, P3:35）
> 可导入Skill：52个（23%）
> 不适用Skill：157个（69.5%）

## TOP 10 P0 致命Bug

1. quality.py预算系统完全失效 — VideoInfo缺少stat字段 → max_tokens ~1823 → 详细总结不详细
2. RAG双重付费 — Anthropic结果被OpenAI结果覆盖
3. thinking参数硬编码发送给所有模型 → DeepSeek/GPT返回400
4. DeterministicEmbedding第3层失效 — MD5哈希产生随机向量
5. RAG三种检索策略不一致
6. pydantic==2.9.0 Python 3.14无法安装 → 白板Windows完全无法运行
7. SESSDATA Cookie通过URL查询字符串明文传输
8. shell.openExternal零验证暴露
9. img标签两个onerror属性
10. KB搜索Enter键TypeError崩溃

## 7条Skill交叉利用链

1. RAG管道：semantic-search+rag-eval+bilibili-rag-deploy+sqlite-best-practices
2. 总结质量：prompt-engineer+claude-api+bili-note+quality.py
3. 内容提取：bilibili-subtitle+faster-whisper+bilibili-source+subtitle-gen
4. 代码质量：fastapi+fastapi-python+fastapi-templates+refactoring+codebase-design+python-error-handling
5. 前端设计：frontend-design+anthropic-frontend-design+design-system+css-animation+impeccable+ui-ux-pro-max
6. 安全：auditing-python-security+electron-security+dotenv+security-triage
7. 测试：fastapi-templates+rag-eval+debugging-strategies+autoreview+code-review

## 8个执行阶段

A: P0致命修复(4-6h) → B: RAG深度优化(3-4h) → C: 总结质量提升(3-4h) → D: KB导入统一(2-3h) → E: 代码质量(4-6h) → F: 安全+测试(3-4h) → G: 功能增强(1-2周) → H: 文档+CI+安装包(1周)

**Why:** 18个Agent深度扫描完成了BiliSum历史上最全面的审计，覆盖了所有28个源文件、226个Skills和6个开源项目。

**How to apply:** 按阶段A→H顺序执行。每阶段完成后运行验证脚本。DOCX完整报告在桌面：BiliSum优化计划v6.0.docx
