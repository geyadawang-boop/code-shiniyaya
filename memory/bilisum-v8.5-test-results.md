---
name: bilisum-v8.5-test-results
description: BiliSum v8.5 — 2026-07-15 核验结果: 评论✅知识库✅分类✅ 内嵌❌ deepseek还需改
metadata:
  type: project
  updated: 2026-07-15
  status: partial-pass
---

# BiliSum v8.5 — 本轮核验结果

## 核验结果

| # | 测试项 | 结果 | 备注 |
|---|--------|------|------|
| 1 | AI评论分析 | ✅ 通过 | 双通道回退生效，读取成功。细节优化→后续 |
| 2 | AI问答读取知识库 | ✅ 通过 | 三层回退链生效，KB_DIR统一 |
| 3 | 收藏夹分类 | ✅ 通过 | KB_DIR统一修复生效 |
| 4 | 内嵌B站滚动 | ❌ 失败 | 显示"登录信息获取失败"等报错 |

## 待修复

### 立即修复
1. **内嵌B站 proxy-fetch**: fetch/XHR拦截脚本有bug，需调试
2. **DeepSeek API 地址**: 多处前端默认placeholder写`api.anthropic.com`，选deepseek模型时自动切`api.deepseek.com/v1/chat/completions` — 需检查是否真是`https://api.deepseek.com`
3. **KB 删除同步**: 删除KB条目时确保 chunks/ + ChromaDB + FTS5 + JSON 全部清理（当前已有但需验证完整性）
4. **KB 导入内容增强**: `api_rag_save` 已改为导入字幕+弹幕+评论，不再仅纯字幕

### 后续优化
- AI评论细节（子回复抓取、情感分析精度）
- 评论全量抓取（cursor分页替代单页）
- 多维度总结增强（bili-note预算+评分）
- DOCX思维导图嵌入
- 第5按钮"完整内容"
- 思维导图PDF导出

## 关联记忆
- [[bilisum-v8.4-session-state]]
- [[bilisum-v8.4-pending-issues]]
