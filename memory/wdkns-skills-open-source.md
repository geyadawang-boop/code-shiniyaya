---
name: wdkns-skills-open-source
description: wdkns/wdkns-skills — Claude Code技能集合。B站/YouTube视频转LaTeX PDF，字幕三级回退+画面关键帧提取+公式代码图表+平台话术过滤+字幕精修清洗。2026-07-16纳入。
metadata:
  type: reference
  source: https://github.com/wdkns/wdkns-skills
  created: 2026-07-16
  status: cloned-analyzed
---

# wdkns-skills (wdkns/wdkns-skills)

- GitHub: https://github.com/wdkns/wdkns-skills
- 技术栈: Claude Code Skills (SKILL.md + agents/*.yaml + scripts/*.py) + LaTeX + yt-dlp + whisper
- 运行方式: Claude Code skill调用，每个skill独立运行

## 包含Skills

### 1. bilibili-render-pdf (B站视频→LaTeX PDF笔记)
- 源文件: skills/bilibili-render-pdf/SKILL.md, agents/openai.yaml
- **字幕三级回退**: CC字幕优先 → Whisper语音转写 → 纯视觉模式(大量B站视频无字幕!)
- **登录获取高清**: 1080P+需cookies, 引导用户用 `yt-dlp --cookies-from-browser chrome`
- **分P视频处理**: 自动检测多P, 询问用户处理哪个Part
- **平台话术过滤**: 排除"一键三连""关注投币""点赞收藏"等非教学内容
- **画面提取**: 从最高可用分辨率提取关键帧, 插入LaTeX作为图表
- **封面使用**: 优先使用原始视频封面作为首页图
- **公式/代码/图表**: 按教学价值提取关键画面、图表、公式和代码片段
- **结构化章节**: 生成带 \section{} / \subsection{} 结构的完整.tex
- **最终交付PDF**: 必须落到可渲染的PDF
- **弹幕处理**: 不用弹幕作教学内容源(噪音太大), 仅用CC字幕或Whisper输出
- **去"字幕味"**: 强调以视频真实教学内容为主, 不只是字幕转写

### 2. subtitle-refine (字幕精修清洗)
- 源文件: skills/subtitle-refine/SKILL.md, scripts/check_clean_srt.py (~250行Python验证脚本)
- **SRT清洗规则引擎**:
  - 语气词检测("嗯啊呃哈欸诶")
  - 口吃/重复检测(AA前缀白名单、"我我"类)
  - 句首句尾赘词过滤
  - 语气停顿补空格
  - 标点符号检测(不允许残留标点)
  - 字幕时长检查(≥400ms最小值)
  - 文本漂移检测(清洗后文字与原文语义一致性 >0.45)
  - 邻位偏移检测(清洗后文字意外漂移到相邻字幕)
  - 允许删除白名单(仅允许删除纯语气词字幕)
- **时间轴验证**: 排序检查, 分割边缘对齐检查, 邻接检查, 全局时间单调检查

### 3. youtube-render-pdf (YouTube视频→LaTeX PDF笔记)
- 源文件: skills/youtube-render-pdf/SKILL.md, agents/openai.yaml
- B站版本的YouTube适配版, 字幕更易获取(YouTube auto-caption)

## LaTeX模板 (templates/tex/)
- 教学笔记LaTeX模板, 含: 封面、目录、多级章节、图表环境、代码块(带行号)、公式块、边注/脚注、参考文献

## 与BiliSum相关度

| wdkns-skills功能 | BiliSum现状 | 可复用性 |
|-----------------|------------|---------|
| 字幕三级回退(CC→Whisper→视觉) | ASR 6s超时无效 | **CRITICAL** — 直接参考回退逻辑 |
| 画面关键帧+图表/公式/代码 | frame_extractor存在但仅用于总结 | **CRITICAL** — 你反复强调的功能! |
| 平台话术过滤"一键三连" | 无 | HIGH — 弹幕/字幕清洗 |
| 字幕精修清洗脚本(250行) | 无 | MEDIUM — 可直接移植Python |
| 原始封面作首页 | 有pic字段存储URL | MEDIUM |
| LaTeX→PDF交付 | 有DOCX导出 | LOW — 需求不同 |
| 以教学内容为主不依赖字幕 | 当前完全依赖字幕 | **CRITICAL** — 核心思路 |
| 分P处理+询问用户 | multi函数未接入 | HIGH |
| Cookie登录1080P | Cookie已存储 | LOW |

## 关联记忆
- [[bilisum-v9.0-bilinote-integration-plan]]
- [[bilinote-open-source]]
- [[bilisum-v8.7-optimization-plan]]
- [[bilisum-all-reference-sources]]
