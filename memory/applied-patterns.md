# 已应用自动化模式台账 (规则22, v4.7.7从SKILL.md移出)

每轮迭代至少应用1个提取模式到工作流。本文件为累积台账。

## 工作流层
- Terminal信号 + 3层重试 + 崩溃分类 + Init+Loop + 无阶段门控并行启动
- ThinkTool推理空间 (v4.0.1, autonomous-coding agents/tools/think.py)
- ThinkTool审计轨迹 (v4.0.1, ThinkTool汇总生成审计轨迹概念)
- 原子文件写入 (prepare.py temp+rename模式 v4.2.0)
- Fast-fail内联守卫 (train.py NaN/loss检测 v4.2.0)
- 输出溢出保存到文件 (tool_utils.py截断+文件路径模式 v4.2.0)
- 终端输出分页 (terminal_tools.py viewport page状态模式 v4.2.2, 适配版)
- 重连恢复 (docker_env.py 容器已存在→跳过创建 v4.2.2)
- 重试感知关闭 (tenacity_stop.py should_exit v4.2.3)
- 分段睡眠 (shutdown_listener.py sleep_if_should_continue v4.2.3)
- 流水线恢复编辑 (metachain_meta_workflow.py feedback注入 v4.2.3)
- 分块批量写入 (rag_tools.py chunk_size=200 v4.2.3)

## 协议层
- GOTO/ABORT终端信号 + 完成信号工具调用(case_resolved) + 声明式事件依赖(listen+outputs)

## STEP 8 Learn+Consolidate (v4.5.2)
- MD5校验和变更检测 + 孤儿检测(token_overlap评分) + 双门控反思触发

## v4.7.6-v4.7.7 (Reasonix + 5 Agent迭代)
- 墙钟时间盒 (autoresearch TIME_BUDGET, 规范级)
- GET BEARINGS启动检查清单 (autonomous-coding coding_prompt.md, 7步)
- caveman auto-clarity安全解压 (ponytail)
- selftest双层门控 (ponytail complete.py:90-102)
- 基线优先 (autoresearch program.md:39)
- Agent输出重定向+grep (autoresearch program.md:99-101)
- echo-guard.js v2.0 stdin hook (ponytail hooks 9模式: 沉默失败+BOM剥离+stdin超时守卫)
- snapshot原子写入+哨兵行 (autoresearch prepare.py temp+rename + 自研SNAPSHOT-COMPLETE)
