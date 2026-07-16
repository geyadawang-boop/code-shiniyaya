---
name: reports-output-to-desktop-folder
description: 新文件/报告必须输出到桌面报告文件夹
metadata: 
  node_type: memory
  type: feedback
  priority: highest
  created: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

所有新生成的文件（报告、DOCX、Markdown、Python脚本、测试文件、临时文件等）必须输出到桌面报告文件夹：
`C:\Users\shiniyaya\Desktop\报告\`

**唯一例外**：用户明确要求 "放到桌面" 的文件（如特定的DOCX总览文件）可以放在桌面。
其他所有AI生成文件一律进报告文件夹。

严禁将任何AI生成的文件直接散落在桌面或其他位置。桌面已有用户个人文件可以保留，但新文件必须进报告文件夹。

此规则无例外。包括但不限于：gen_docx.py、extract_codex.py、__test__*.txt、*~tplv-*.docx、任何DOCX/MD报告、任何Python脚本、任何临时测试文件。

**Why:** 用户桌面已有大量历史报告文件，需要统一管理，避免桌面混乱。用户已多次手动清理桌面AI生成文件。本次用户明确指示"除了我主动要求放到桌面的docx文件，其他都放到报告文件夹里面"。

**How to apply:** 每次Write工具调用时，output_path使用 `C:\Users\shiniyaya\Desktop\报告\<filename>`（除非用户明确说"放到桌面"）。每次Bash生成文件时，目标路径使用 `$USERPROFILE/Desktop/报告/`。
