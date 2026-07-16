---
name: bilisum-160agent-results
description: 160 Agent四大Workflow产出汇总 (2026-07-16) — 已应用: content_filter+frame_text_service+多模态client; 待批准: 三级字幕回退+教学优先prompt。含全部设计要点。
metadata:
  type: project
  priority: highest
  created: 2026-07-16
  agentCount: 160
  status: 2-applied-2-pending-approval
---

# 160 Agent 产出汇总 (4 Workflow × 40)

## 已应用+验证的代码 (AST+import全通过)

### 1. content_filter.py ⭐用户优先项2 (平台话术过滤)
- 新文件, 纯stdlib (re+collections)
- 三级分类: NOISE(打卡/前排/一键三连/引流→丢弃) | REACTION(哈哈哈/666/233→折叠"x500"计数) | CONTENT(去重保留)
- normalize_text: 重复字符压缩(哈哈哈哈哈→哈哈哈), 233333→233归并
- 已接入 kb.py api_rag_save (弹幕+评论双路)
- 冒烟测试通过: 保留对象属性(.user/.likes/.content), list进list出

### 2. frame_text_service.py ⭐用户优先项1 (画面关键帧)
- 新文件 ~630行, 10阶段管线
- 视频获取: 调用方→frames_cache→yt-dlp(720p+cookies)
- 帧提取: FrameExtractor关键帧+场景变化; stdlib字节直方图去重(阈值0.985)
- 自适应帧数: ≤5min:8 / ≤15min:12 / ≤30min:16 / ≤60min:20 / max:24
- VLM: qwen-vl-plus (dashscope, 国产✅) + OpenAI兼容回退, Semaphore(3)
- 中文prompt: 提取全部可见文字(字幕/PPT/白板/代码/图表标签)+一句话场景
- 输出: [MM:SS]文字块 → to_prompt_block()渲染"## 视频画面时间轴"
- manifest缓存(重导入不重复VLM) + 删除钩子自注册 + 永不raise(gaps降级)
- API key: db设置dashscope_api_key → DASHSCOPE_API_KEY env
- 环境变量: BILISUM_VL_MODEL / BILISUM_VL_FALLBACK_URL/MODEL

### 3. unified_llm_client.py 多模态扩展
- 图片输入: data URI / raw base64 / URL / 本地路径 全支持
- dashscope compatible-mode路由为openai格式
- 新SECTION 3.5多模态消息构造器

### 4. kb.py api_rag_save元数据修复
- save_kb_entry现在传全量: desc/duration/pubdate/tags/tname/stat/owner_mid

## 待批准应用的设计 (完整old→new diff已产出)

### 5. 三级字幕回退 ✅ 已应用 (2026-07-16, 用户+Codex双批准)
- models.py: SubtitleData.source + parts_total/parts_ok字段
- bilibili_client.py: 死代码_try_channel5删除; Tier1官方并行→Tier2 ASR(900s/2h上限/信号量)→Tier3纯视觉
- asr_service.py: VIDEO_CACHE_DIR + download_video_for_frames + cleanup_video_cache
- kb.py: 多P检测分支(parts>1用get_full_subtitle_multi) + partsTotal/partsOk响应
- 前端: summary.html + multi-platform.html "已导入 N/N 页" toast
- Agent修正设计bug: extract_frame_text位置参数→关键字参数(签名不匹配)
- 运行时开关: BILISUM_ASR_FALLBACK=0 / BILISUM_VISUAL_FALLBACK=0 可独立禁用
- 验证: AST x4 + import main + SubtitleData默认值 + _asr_text_to_body时间戳解析 ✅

### 6. 教学优先总结prompt ✅ 已应用 (2026-07-16, 用户+Codex双批准)
- summarizer.py: _TEACHING_SYSTEM_PROMPT(1144字符)插入_TRUST_BOUNDARY后
- detailed模板: 7维Markdown+隐藏CoT+## 总结与延伸
- structured模板: 7维JSON+旧字段兼容+audience_view+insufficient_content
- 附加: _parse_model_json修复链(fence/尾逗号/截断) + _normalize_structured_summary + structured_data附加
- 安全层零改动(git diff验证)
- 验证: AST + import + 冒烟(brief/keypoints/mindmap不变, f-string brace正确) ✅

## 统计
- 160 Agent, ~7.5M subagent tokens, ~2900次工具调用
- 4个Workflow全部40/40无错误完成

## 下一步 (待用户+Codex双批准)
1. 应用三级字幕回退diff (models.py+bilibili_client.py+asr_service.py)
2. 应用教学优先prompt diff (summarizer.py)
3. frame_text_service接线到api_rag_save ("## 画面内容"section)
4. 人工核验清单生成 (规则22)

## 关联记忆
- [[bilisum-v9.0-execution-plan]] — 用户优先级已标注
- [[bilisum-v8.7-master-bug-list]]
- [[manual-verification-checklist]]
