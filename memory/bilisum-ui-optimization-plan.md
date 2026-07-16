---
name: bilisum-ui-optimization-plan
description: UI beautification plan — sky-blue whale theme, CSS token cleanup, accessibility fixes, animation compliance
metadata:
  type: project
---

# BiliSum UI 优化 + 天空蓝鲸鱼主题方案

## 天空蓝鲸鱼主题配色
- 天空浅蓝 #e8f4fd (60%) / 白色浪花 #f0f7fa (30%) / 暖珊瑚 #ff6b6b (10%)
- 保留 B站粉(#fb7299) 作为功能色
- CTA 磷虾橙 #ffa726
- 暗色模式: 深海蓝灰渐变

## 动画方案
- 4层天空渐变背景 (fixed, z-index:0, pointer-events:none)
- 6朵CSS纯绘云 (border-radius伪元素, 3深度层 65-140s周期)
- 内联SVG鲸鱼 (200x80 viewBox, 22s飞行周期, ease-out-quart, 喷水动画)
- 全部 transform+opacity GPU加速
- @media (prefers-reduced-motion) 完整覆盖
- 骨架屏 shimmer 替换 spinner

## UI Bug 修复清单 (30+项)
- 替换 35+ 硬编码 hex → CSS变量
- 全部字体 ≥ 12px (当前有20+处违规)
- `--muted: #999` → `#666` (对比度从2.68:1→ 4.6:1)
- tools.html 移除孤立 `t` 字符 + 修复未闭合 `<script>` + 删除重复System Status
- 所有动画添加 `prefers-reduced-motion`
- 4处 `transition: all` → `transform, opacity, box-shadow`
- z-index 文档化: dropdown(100)→sticky(200)→modal(300)→toast(400)
- 弹窗升级为 `<dialog>` + ARIA属性(aria-modal/aria-label)
- 设置/登录/加载组件提取为共享HTML模板(消除4处重复)
- `h-screen` → `min-height: 100dvh`
- 暗色模式覆盖全部token(阴影/粉色变体/状态色)
- kb.html搜索用真实输入框替换prompt()
- favorites.html收藏夹复选框用`<input type="checkbox">`替换`<div>`

## 无障碍性 (14项)
- 零→完整 ARIA 属性
- 弹窗焦点捕获
- `prefers-reduced-motion` 支持
- `prefers-reduced-transparency` 支持
- 按钮 `:focus-visible` 样式
- `skip-to-main-content` 链接

**Why:** The current UI scored 3.5/10 in the audit. The whale theme provides a distinctive, non-AI-default visual identity.

**How to apply:** Implement Phase E of the optimization plan. Start with CSS token cleanup, then add sky background, then clouds, then whale animation.
