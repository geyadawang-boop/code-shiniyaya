# BiliSum — 私人仓库指南

仓库URL: https://github.com/geyadawang-boop/BiliSum-
分支: main (最新) / latest (快照) / v9.0 (标签)

## Clone & Setup

git clone https://github.com/geyadawang-boop/BiliSum-.git
cd BiliSum-
git tag -l        # 查看所有标签

## 结构

backend/  — Python后端源码 (67 .py)
frontend/ — 前端页面+CSS+JS (17文件)
memory/   — 全部活跃记忆 (120 .md)
references/ — 技能定义+参考文档

## 回退命令

git checkout c488dc6    # 回退到记忆同步点(含全部计划但无源码)
git checkout 680efd8     # 回退到v4.6.8基线
git checkout v9.0        # 当前最新v9.0快照
git checkout <commit> -- <file>  # 恢复单个文件

## 提交历史

42cd70f 记忆同步记录
dada15a v9.0 完整源码
c488dc6 v9.0 完整记忆+规则+skill+报告
70fc3ec 合并
680efd8 v4.6.8 基线
