---
name: mindmap-working-params
description: BiliSum 思维导图渲染成功参数记录 — MutationObserver异步等待+autoloader+fallback链
metadata:
  type: reference
  created: 2026-07-15
  priority: highest
---

# BiliSum 思维导图渲染成功参数

## 关键参数 (已验证可正常显示)
- CDN: `https://cdn.jsdelivr.net/npm/markmap-autoloader@0.17.0/dist/index.js` (IIFE单文件)
- 加载方式: 动态`<script>`标签注入,非ESM import
- 渲染方式: 创建`<div class="markmap">`DOM元素, autoloader自动发现+渲染
- 异步等待: MutationObserver轮询200ms×30次(6s),检测容器内`<svg>`元素出现+宽度>0
- 手动重试: 30次轮询后若仍未渲染,调用`window.markmap.autoLoader.renderAll()`,再等3s
- 最终回退: 15s后仍无SVG→`_fallbackToText()`文本大纲
- CSP: `script-src https://cdn.jsdelivr.net` (main.js L660) + proxy页面`default-src * 'unsafe-inline'`

## 失败过的方案 (勿再用)
- ❌ ESM `import {Transformer} from "..."` → CSP `unsafe-inline`不覆盖module scripts
- ❌ `markmap-lib@0.17.0/dist/browser/index.js` → HTTP 404 (正确路径是.mjs)
- ❌ `markmap-view@0.17.0/dist/browser/index.js` → IIFE格式,无ESM export
- ❌ `autoLoader.renderAll()` 在`script.onload`中立即调用 → 依赖项未加载完成
- ❌ `markmap-autoloader` → 空格/URL格式错误

## 文件位置
- 前端: `frontend/summary.html` renderMindmap() L364-420
- CSP: `main.js` L660 script-src
- 后端mindmap prompt: `backend/summarizer.py` mindmap模式 L304-337
