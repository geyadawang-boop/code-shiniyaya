# code-shiniyaya v4.2.5 最终状态

**Date**: 2026-07-16
**Final Version**: v4.2.5 (889 lines)
**Total Iterations**: 25 (iter#1 iter#20 → v4.1.3, iter#21-#25 → v4.2.0-v4.2.5)
**Source Files Read**: ~62 across 4 projects

## SKILL.md v4.2.5 规模

| 组件 | v4.0.7 (iter#20) | v4.2.5 (iter#25) | 增长 |
|------|-----------------|-----------------|------|
| 硬规则 | 24 | 25 | +1 (Fast-fail+预热排除) |
| 反模式 | 21 | 23 | +2 (预热期计入预算, 隐式步骤依赖) |
| 自检 | 16 | 16 | — |
| 总行数 | ~831 | 889 | +58 |

## v4.2.0→v4.2.5 新增内容总汇

### 规则
- **规则25**: Fast-fail内联守卫+预热排除 (autoresearch train.py)

### 反模式
- **反模式22**: 预热期计入预算/统计 (train.py)
- **反模式23**: 隐式步骤依赖 (AutoAgent workflow_former.py)

### 终端信号协议
- GOTO/ABORT类型化 (AutoAgent flow/dynamic.py ReturnBehavior枚举)
- 工具调用完成信号 case_resolved/case_not_resolved (tool_editor.py)
- 声明式事件依赖 listen_group三模式 (workflow_former.py)
- 编译验证管线 XML→Python→编译→run (edit_workflow.py+edit_agents.py)

### 截断/输出
- truncate_with_file_fallback 溢出保存完整文件 (tool_utils.py)
- paginate_large_output 分页模式 (terminal_tools.py)
- 结果标记模式 start/end marker (edit_agents.py)

### 防护机制
- 重连恢复 容器已存在→跳过创建 (docker_env.py)
- 重试感知关闭 stop_if_should_exit (tenacity_stop.py)
- 信号驱动分段睡眠 sleep_if_should_continue (shutdown_listener.py)
- 流水线恢复编辑 反馈注入+阶段独立MAX_RETRY (metachain_meta_workflow.py)
- 分块批量写入 batch_size=200 (rag_tools.py)

### 工作流
- STEP 8 Phase 2: MD5校验和变更检测+孤儿检测+双门控触发 (auto_dream.py)

### 输出规范化
- Shell脚本代理模式 复杂命令→临时脚本→chmod+x→执行 (edit_agents.py)
- 速率限制处理 API剩余<10→sleep最多5秒 (github_client.py)
- print_stream灰暗日志 [grey42]标记 (util.py)

## 4源完整读取清单

### AutoAgent (~45 files read)
已读: core.py, main.py, types.py, constant.py, flow/core.py, flow/types.py, flow/dynamic.py, flow/broker.py, flow/utils.py, fn_call_converter.py, registry.py, logger.py, tools/inner.py, tools/tool_utils.py, tools/terminal_tools.py, tools/code_search.py, tools/rag_tools.py, tools/web_tools.py, tools/github_client.py, tools/github_ops.py, tools/md_obs.py, tools/rag_code.py, tools/meta/edit_agents.py, tools/meta/edit_tools.py, tools/meta/edit_workflow.py, tools/meta/tool_retriever.py, tools/meta/search_tools.py, agents/meta_agent/agent_creator.py, agents/meta_agent/agent_editor.py, agents/meta_agent/agent_former.py, agents/meta_agent/tool_editor.py, agents/meta_agent/workflow_creator.py, agents/meta_agent/workflow_former.py, memory/rag_memory.py, memory/code_memory.py, memory/tool_memory.py, environment/docker_env.py, environment/browser_env.py, environment/utils.py, environment/tenacity_stop.py, environment/shutdown_listener.py, cli_utils/metachain_meta_agent.py, cli_utils/metachain_meta_workflow.py, io_utils.py, util.py, cli.py, server.py

### autodream (~10 files read)
已读: helpers/auto_dream.py (全量1411行), plugin.yaml, default_config.yaml, prompts/autodream.sys.md, prompts/autodream.msg.md, prompts/autodream.consolidate.sys.md, prompts/autodream.consolidate.msg.md, extensions/python/process_chain_end/_60_auto_dream.py, webui/config.html, README.md

### autoresearch (5 files — 全部)
已读: program.md, train.py (全量631行), prepare.py (全量390行), analysis.ipynb, README.md

### autonomous-coding (2 source files — 全部)
已读: agent.py (全量), progress.py (全量), CLAUDE.md, README.md

## 未读残余 (低优先级，已穷尽核心模式)

AutoAgent: tools/dummy_tool.py, tools/file_surfer_tool.py, tools/github_ops.py, memory/paper_memory.py, memory/codetree_memory.py, memory/utils.py, memory/code_tree/code_parser.py, environment/local_env.py, environment/browser_cookies.py, environment/cookies_data.py, environment/markdown_browser/* (4 files), environment/mdconvert.py, environment/tcp_server.py, evaluation/* (6 files), agents/system_agent/* (3 files), agents/dummy_agent.py, agents/github_agent.py, repl/repl.py, loop_utils/font_page.py, process_tool_docs.py, docs/*

autodream: 全部核心已读
autoresearch: 全部已读
autonomous-coding: 全部已读 (只有2个源文件)
