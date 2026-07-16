---
name: bilisum-embedded-bilibili-scroll-reality
description: 内嵌B站无限滚动 — 架构限制，fetch/XHR monkey-patch方向错误，恢复原始版本仅拦截a标签点击
metadata:
  type: project
  updated: 2026-07-15
---

# 内嵌B站无限滚动 — 架构现实

## 结论
fetch/XHR monkey-patching 破坏了B站页面自身的JavaScript初始化，导致页面报错。**该方案已放弃。**

## 为什么原始版本没有这个问题
原始版本只注入了 `<a>` 标签点击拦截和工具栏。它不触碰 `window.fetch` 或 `XMLHttpRequest`。B站页面的JS可以自由初始化，前10个SSR视频渲染正常。无限滚动从来就不是设计目标。

## 为什么 fetch/XHR 拦截不可行
1. **B站 CSP（Content-Security-Policy）** — 页面在加载时设置连接源策略。将 `api.bilibili.com` 的请求重写到 `127.0.0.1:8000` 会触发 CSP 违规。
2. **时序问题** — fetch monkey-patching 必须在 B站自己的 JS 启动**之前**运行，但 B站的 SPA 打包脚本可能先于注入的 `<script>` 标签执行（因为有 `<script defer>` 和并行加载）。
3. **Request 对象问题** — `new Request()` 创建的请求在重写 URL 时会丢失原始头信息（cookie、referer等）。
4. **Service Worker 是唯一正确的方式** — 它可以拦截所有出站网络请求，在 B站 JS 初始化之前生效，并且正确处理 CSP。

## 当前修复
**已移除 fetch/XHR 拦截脚本。** Misc.py 现在恢复到原始的 `<a>` + 工具栏注入模式，与代理路由完全匹配。

## 正确的解决方案（后续）
需要一个 Service Worker (`sw.js`)，注册在 `/bili/proxy` 页面加载时，实际拦截所有到 `*.bilibili.com` 的出站请求，并将它们通过 `/api/bili/proxy-fetch` 代理。这需要：
1. 一个共享的 `sw.js`，作为 `/sw.js` 提供
2. 在注入脚本中注册一个 Service Worker
3. 自定义消息传递，将 B站 cookie 传递给 worker

## 关联记忆
- [[bilisum-v8.5-pending-issues]]
- [[bilisum-v8.4-pending-issues]]
