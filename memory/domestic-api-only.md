---
name: domestic-api-only
description: 项目仅使用国内API，禁止使用国外API
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-12
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# 国内API仅限 + 无需VPN规则

所有后端 API 调用（B站、LLM、字幕、搜索等）必须使用国内可访问的服务端点。**软件不需要使用VPN即可使用。**

**Why:** 项目面向国内用户，B站 API 在国内网络环境，LLM 使用国内厂商（DeepSeek等）。使用国外 API 会导致连接超时、不可用。用户不应被要求开启VPN才能使用软件。

**How to apply:**
1. LLM API URL 默认指向国内服务商（如 DeepSeek、通义千问等）
2. B站 API 全部走 `api.bilibili.com`（国内CDN）
3. 不使用需要代理的国外端点
4. 超时配置针对国内网络环境优化（国内到 B站 CDN 通常 <3s）
5. **严格禁止**: 任何国外端点（如 api.openai.com, api.anthropic.com, Google APIs 等）不应作为默认或唯一选项
6. 如使用国外端点，必须(a)用户明确配置了代理 且(b)作为可选备选 且(c)默认仍使用国内端点
