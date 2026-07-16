---
name: bilisum-v8.5-pending-issues
description: BiliSum v8.5 待办: 内嵌B站 proxy-fetch调试 + DeepSeek URL + KB删除同步 + KB导入增强 + 后续优化
metadata:
  type: project
  priority: highest
  updated: 2026-07-15
  status: active
---

# BiliSum v8.5 — 本轮核验与修复 (2026-07-15)

## 核验结果

| # | 测试项 | 结果 |
|---|--------|------|
| 1 | AI评论分析 | ✅ 通过 |
| 2 | AI问答读取知识库 | ✅ 通过 |
| 3 | 收藏夹自动分类 | ✅ 通过 |
| 4 | 内嵌B站滚动加载 | ❌ 仍报错 |

## 已完成修复

### A. KB导入内容增强 ✅
`routers/kb.py:111-132` — `api_rag_save` 现在导入: 字幕 + 弹幕精华 + 热门评论，不再仅纯字幕。

### B. 内嵌B站 proxy-fetch 第二次修复 ✅
`routers/misc.py:142-166` — 注入脚本修复:
- 修复重复 `</script>` 标签导致 JS 语法错误
- 修复 `new Request()` 在拦截场景下不可用
- fetch拦截仅处理GET请求
- XMLHttpRequest拦截使用`_origOpen.call`代替`apply`

### C. DeepSeek API 地址
`constants.py:45` — 当前 `DEFAULT_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"`
`common.js:387` — 选deepseek模型时自动填 `https://api.deepseek.com/v1/chat/completions`

实际测试: `https://api.deepseek.com/v1` 返回401(需要key)，确认此URL可到达。

## 待测试

重启后端 + Electron，测试内嵌B站首页滚动加载。

## 后续优化计划

1. AI评论细节优化 (子回复独立抓取, 情感分析精度, cursor全量分页)
2. 多维度总结增强 (bili-note 写前预算+写后评分+证据索引)
3. 第5按钮"完整内容" + DOCX嵌入思维导图
4. 思维导图PDF导出
5. KB删除完整性验证 (JSON+chunks+FTS5+ChromaDB四层清理)
6. 内嵌B站 Service Worker 方案 (作为fetch/XHR拦截的长期替代)

## 关联记忆
- [[bilisum-v8.4-session-state]]
- [[bilisum-v8.5-test-results]]
- [[bilisum-v8.4-pending-issues]]
