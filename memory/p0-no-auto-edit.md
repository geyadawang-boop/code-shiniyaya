---
name: p0-no-auto-edit
description: [已废弃] 被 p0-dual-approval-before-code-edit 升级取代 — 修改前需用户+Codex双方批准，而非仅用户批准
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  status: superseded
  superseded_by: p0-dual-approval-before-code-edit
  superseded_date: 2026-07-13
  created: 2026-07-12
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# 规则 1：未经批准禁止修改代码

## 规则内容

**任何代码修改前，必须先向用户详细说明改动内容和原因，获得明确批准后才能执行。** 严禁擅自修改任何代码。

## 为什么

PowerShell Set-Content 曾导致大面积 UTF-8 编码损坏。CC 直接修复时多次出现编码转码（UTF-8→UTF-16 LE）、BOM 注入、文件清空等二次损坏。用户需要审核每项修改的风险后再批准执行。

## 具体流程

1. **修改前**: 向用户说明要改哪个文件、改什么内容、为什么需要改、有什么风险
2. **等待批准**: 用户明确说"可以"、"批准"、"执行"等后才动手
3. **修改后**: 立即验证并反馈结果（语法检查、编码检查、功能测试）
4. **例外**: 用户明确说"直接修"、"不用问我"的场合可以跳过审批

## 关联记忆

- [[codex-cross-verification-rule]] — 修改前 Codex 交叉审查
- [[codex-fix-verification-rule]] — 修改后 Codex 独立验证
- [[codex-message-protocol]] — 给 Codex 发信息时的格式要求

**Why:** PowerShell Set-Content 导致 3 轮编码损坏，涉及 main.js、browse.html、bilibili_client.py、summary.html、enhancements.js 等多个文件。每次 CC 静默修改都增加了排查成本。

**How to apply:** 每次代码修改前强制执行。唯一的例外是用户明确说"直接修"。修改后必须立即运行 ast.parse 或对应的语法验证。
