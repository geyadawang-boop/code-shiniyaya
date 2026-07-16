# CODE-SHINIYAYA v4.2.0 — 4源深度利用迭代

**Date**: 2026-07-16
**Previous**: v4.1.3 (iter#20 zero-confirmed)
**Current**: v4.2.0

## v4.2.0 Changes (from unscanned source files)

### AutoAgent files read (first time):
- `flow/dynamic.py` — GOTO/ABORT类型化返回值(ReturnBehavior枚举, 19行) → 规则22更新, 终端信号协议v4.2.0类型化
- `fn_call_converter.py` — interleave_user_into_messages(L837-848) → 确认现有interleave实现正确; FN_CALL→NON_FN_CALL双向转换 → 工具格式适配参考
- `registry.py` — Registry单例+FunctionInfo自动提取(args/docstring/body/file_path) → config集中化参考; MAX_OUTPUT_LENGTH=12000 → 输入上限对齐
- `flow/broker.py` — BaseBroker抽象(append+callback_after_run_done) → 消息路由抽象参考
- `tools/tool_utils.py` — 输出溢出→保存完整文件+返回截断+告知路径 → 规则22已应用, 输入上限增强
- `flow/utils.py` — function_or_method_to_repr(MD5哈希唯一标识函数) → Agent函数注册参考
- `memory/code_memory.py` — CodeMemory(向量化代码库+CodeReranker重排序) → 代码搜索模式参考
- `agents/meta_agent/agent_creator.py` — AI创建Agent的Agent → 自修改系统参考
- `agents/meta_agent/agent_editor.py` — AI编辑Agent的Agent → 自修改系统参考

### autodream files read (first time):
- `auto_dream.py` (full 1411 lines) — Learn+Consolidate完整实现: 双门控触发(min_hours OR min_sessions)、MD5校验和变更检测(L535-539)、孤儿检测(L846-918, token重叠分数)、DirtyJson容错解析(L246) → STEP 8增强
- `default_config.yaml` — 5个配置项(enabled/min_hours=2/min_sessions=2/line_limit=120/consolidate_every_n_dreams=2) → config外部化参考
- `prompts/autodream.consolidate.sys.md` — Consolidate系统提示词(Facts→.md, Rules→.promptinclude.md分类) → STEP 8 Phase 2实现参考
- `extensions/python/process_chain_end/_60_auto_dream.py` — 扩展钩子(agent0检查/非后台/保存临时聊天→触发dream) → 生命周期钩子参考

### autoresearch files read (first time):
- `train.py` (full 631 lines) — Fast-fail内联守卫(L570-572: `if loss>100: exit(1)`)、前10步预热排除(L578: `if step>10`才计入)、EMA去偏(L583)、固定时间预算进度驱动 → 规则25(新增)
- `prepare.py` (full 390 lines) — 5次重试+指数退避+临时文件+原子rename下载(L60-88)、best-fit packing数据加载器(L276-337) → 原子写入协议增强

### autonomous-coding files read (first time):
- `agent.py` (full) — clean exit/auto-continue/warmup → 确认现有Init+Loop实现覆盖
- `CLAUDE.md` (full) → 确认现有模式提取完整

## Key additions to SKILL.md v4.2.0
1. **规则25** — Fast-fail内联守卫+预热排除 (train.py L570-572 + L578)
2. **反模式22** — 预热期计入预算/统计 (train.py step>10守卫)
3. **终端信号协议v4.2.0类型化** — GOTO/ABORT用ReturnBehavior枚举替代文本解析 (dynamic.py)
4. **截断增强** — truncate_with_file_fallback溢出保存完整文件 (tool_utils.py)
5. **STEP 8增强** — MD5校验和变更检测+孤儿检测+双门控触发 (auto_dream.py)
6. **原子写入协议** — temp+rename模式引用 (prepare.py L75)

## Remaining unscanned (lower priority)
- AutoAgent: agents/meta_agent/workflow_creator.py, workflow_former.py, workflow_form_complie.py, agent_former.py, form_complie.py, tool_editor.py
- AutoAgent: memory/paper_memory.py, memory/codetree_memory.py, memory/tool_memory.py
- AutoAgent: environment/ files (docker_env.py, browser_env.py, etc.)
- AutoAgent: evaluation/ files
- autodream: prompts/autodream.consolidate.msg.md
- autoresearch: analysis.ipynb (full)
