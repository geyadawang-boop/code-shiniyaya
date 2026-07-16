"""
BiliSum Prompt Engine v2.0 - 深度学习版
基于 prompt-engineer skill 方法论,整合 CoT + Few-Shot + JSON Schema + 抗幻觉护栏

作者: prompt-engineer agent
日期: 2026-07-09

Bug 修复清单 (summarizer.py:52-96 → 全部重写):
  B1: 4模式 prompt 过于简单,无角色建模/输出约束
  B2: 零 CoT 引导,模型直接输出无推理过程
  B3: 零 Few-Shot 示例,无输出质量参考
  B4: 无 JSON Schema 结构化输出约束,原始文本难解析
  B5: 无抗幻觉护栏,允许模型编造视频中不存在的内容
  B6: 缺少 study-note 和 qa 模式
  B7: Anthropic API 未使用 system parameter (summarizer.py:136)
  B8: summarize_segments prompt 同样简陋 (summarizer.py:210)
"""

import json
import re
from typing import Optional, Literal
from dataclasses import dataclass, field
from models import VideoInfo, SubtitleData, CommentEntry


# ============================================================================
# Section 0: JSON Schema Definitions - 结构化输出约束
# ============================================================================

OUTPUT_SCHEMAS = {
    "brief": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["brief"]},
            "title": {"type": "string", "description": "视频标题"},
            "one_liner": {
                "type": "string",
                "description": "一句话总结视频核心内容",
                "maxLength": 150
            },
            "key_points": {
                "type": "array",
                "description": "2-3条关键信息",
                "items": {"type": "string"},
                "minItems": 2,
                "maxItems": 3
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {
                "type": "string",
                "enum": ["high", "medium", "low"],
                "description": "high=有完整字幕; medium=部分字幕; low=无字幕仅推测"
            },
            "citations": {
                "type": "array",
                "description": "每条关键信息的数据来源标注",
                "items": {
                    "type": "object",
                    "properties": {
                        "point_index": {"type": "integer"},
                        "source": {
                            "type": "string",
                            "enum": ["subtitle", "description", "danmaku", "comment", "tags", "ocr", "inferred"]
                        },
                        "quote": {"type": "string", "description": "引用原文片段"}
                    },
                    "required": ["point_index", "source"]
                }
            },
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "one_liner", "key_points", "has_subtitle", "confidence"]
    },

    "detailed": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["detailed"]},
            "title": {"type": "string"},
            "overview": {"type": "string", "description": "视频主题概述(一句话)", "maxLength": 200},
            "key_points": {
                "type": "array",
                "description": "关键内容要点(3-5条)",
                "items": {
                    "type": "object",
                    "properties": {
                        "heading": {"type": "string", "description": "要点标题"},
                        "detail": {"type": "string", "description": "详细说明"},
                        "timestamp": {"type": "string", "description": "大致时间段,如 03:15-05:20"},
                        "source": {"type": "string", "enum": ["subtitle", "description", "danmaku", "comment", "tags", "ocr", "inferred"]},
                        "quote": {"type": "string", "description": "引用原文"}
                    },
                    "required": ["heading", "detail", "source"]
                },
                "minItems": 3,
                "maxItems": 5
            },
            "ocr_text_summary": {
                "type": "string",
                "description": "画面文字总结(如有)",
                "nullable": True
            },
            "audience_reactions": {
                "type": "object",
                "properties": {
                    "summary": {"type": "string"},
                    "hot_comments": {
                        "type": "array",
                        "items": {"type": "string"},
                        "maxItems": 5
                    }
                },
                "nullable": True
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "citations": {"type": "array", "items": {"type": "object"}},
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "overview", "key_points", "has_subtitle", "confidence"]
    },

    "keypoints": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["keypoints"]},
            "title": {"type": "string"},
            "key_points": {
                "type": "array",
                "description": "5-10个关键要点",
                "items": {
                    "type": "object",
                    "properties": {
                        "index": {"type": "integer"},
                        "point": {"type": "string", "description": "要点内容"},
                        "timestamp": {"type": "string", "description": "大致时间段"},
                        "source": {"type": "string", "enum": ["subtitle", "description", "danmaku", "comment", "tags", "ocr", "inferred"]},
                        "importance": {"type": "string", "enum": ["critical", "high", "medium"]}
                    },
                    "required": ["index", "point", "source"]
                },
                "minItems": 5,
                "maxItems": 10
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "key_points", "has_subtitle", "confidence"]
    },

    "mindmap": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["mindmap"]},
            "title": {"type": "string"},
            "central_topic": {"type": "string", "description": "中心主题"},
            "branches": {
                "type": "array",
                "description": "一级分支",
                "items": {
                    "type": "object",
                    "properties": {
                        "topic": {"type": "string", "description": "分支主题"},
                        "children": {
                            "type": "array",
                            "description": "二级分支",
                            "items": {
                                "type": "object",
                                "properties": {
                                    "topic": {"type": "string"},
                                    "children": {
                                        "type": "array",
                                        "items": {
                                            "type": "object",
                                            "properties": {
                                                "topic": {"type": "string"},
                                                "note": {"type": "string", "description": "补充说明"}
                                            }
                                        }
                                    }
                                }
                            }
                        }
                    },
                    "required": ["topic"]
                },
                "minItems": 2,
                "maxItems": 7
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "central_topic", "branches", "has_subtitle", "confidence"]
    },

    "study-note": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["study-note"]},
            "title": {"type": "string"},
            "learning_objectives": {
                "type": "array",
                "description": "学习目标",
                "items": {"type": "string"},
                "minItems": 1,
                "maxItems": 5
            },
            "key_concepts": {
                "type": "array",
                "description": "核心概念",
                "items": {
                    "type": "object",
                    "properties": {
                        "term": {"type": "string", "description": "概念/术语"},
                        "definition": {"type": "string", "description": "定义/解释"},
                        "examples": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "举例说明"
                        },
                        "source": {"type": "string", "enum": ["subtitle", "description", "danmaku", "comment", "tags", "ocr", "inferred"]}
                    },
                    "required": ["term", "definition", "source"]
                },
                "minItems": 1
            },
            "structured_notes": {
                "type": "array",
                "description": "结构化笔记(按主题分段)",
                "items": {
                    "type": "object",
                    "properties": {
                        "section_title": {"type": "string"},
                        "content": {"type": "string"},
                        "timestamp": {"type": "string"}
                    }
                }
            },
            "summary": {"type": "string", "description": "学习总结"},
            "review_questions": {
                "type": "array",
                "description": "复习问题",
                "items": {"type": "string"},
                "maxItems": 5
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "citations": {"type": "array", "items": {"type": "object"}},
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "learning_objectives", "key_concepts", "structured_notes", "has_subtitle", "confidence"]
    },

    "qa": {
        "type": "object",
        "properties": {
            "mode": {"type": "string", "enum": ["qa"]},
            "title": {"type": "string"},
            "questions_and_answers": {
                "type": "array",
                "description": "问答对列表",
                "items": {
                    "type": "object",
                    "properties": {
                        "id": {"type": "integer"},
                        "question": {"type": "string"},
                        "answer": {"type": "string"},
                        "answer_source": {
                            "type": "string",
                            "enum": ["explicit", "inferred", "speculative"],
                            "description": "explicit=字幕直接回答; inferred=从上下文推断; speculative=推测"
                        },
                        "timestamp": {"type": "string"},
                        "source_quote": {"type": "string", "description": "答案来源引用"},
                        "difficulty": {"type": "string", "enum": ["basic", "intermediate", "advanced"]}
                    },
                    "required": ["id", "question", "answer", "answer_source"]
                },
                "minItems": 3,
                "maxItems": 10
            },
            "has_subtitle": {"type": "boolean"},
            "confidence": {"type": "string", "enum": ["high", "medium", "low"]},
            "generated_at": {"type": "string", "format": "date-time"}
        },
        "required": ["mode", "title", "questions_and_answers", "has_subtitle", "confidence"]
    }
}


# ============================================================================
# Section 1: Anti-Hallucination Guardrails (抗幻觉护栏)
# ============================================================================

ANTI_HALLUCINATION_GUARDRAILS = """
## 严格护栏 (Mandatory Guardrails)

### 1. 信息来源约束 (Source-Grounding)
- **绝对禁止**编造视频中没有出现的信息、人物、事件或数据
- 每一条关键信息的输出必须能在提供的视频信息源(字幕/简介/弹幕/评论/标签/OCR)中找到对应依据
- 如果某类信息源为空或不可用,必须在对应字段标注 `source: "inferred"` 并说明推断依据

### 2. 事实核查提示 (Fact-Checking Protocol)
在输出任何结论前,请执行以下自检:
- [ ] 这条信息是否直接来自提供的字幕文本?
- [ ] 如果不是字幕中的,是否来自简介/标签/OCR?
- [ ] 如果纯粹是从标题推测的,是否标注了 \"根据标题推测\"?
- [ ] 我是否添加了任何我\"知道\"但视频中没有提到的内容?

### 3. 来源引用机制 (Source Citation)
每条 output 必须包含以下元数据之一:
- `source: "subtitle"` + 引用字幕原文片段
- `source: "description"` + 引用简介片段
- `source: "ocr"` + 引用画面文字片段
- `source: "danmaku"` + 引用弹幕片段
- `source: "comment"` + 引用评论片段
- `source: "tags"` + 引用标签
- `source: "inferred"` + 说明推断逻辑(如\"基于标题中的XXX关键词推断\")

### 4. 置信度声明
- `confidence: "high"` = 有完整字幕,信息直接来自字幕
- `confidence: "medium"` = 有部分字幕或依赖多种信息源交叉验证
- `confidence: "low"` = 无字幕,主要依赖标题/简介/标签推测

### 5. 不确定性表达
- 当在无字幕情况下推测时,必须使用\"可能\"、\"推测\"、\"基于标签推断\"等语言
- 禁止使用确定语气的陈述句描述推测内容
"""


# ============================================================================
# Section 2: CoT (Chain-of-Thought) 引导模板
# ============================================================================

COT_TEMPLATES = {
    "brief": """## 思考步骤 (Step-by-Step Reasoning)
在生成最终输出前,请按以下步骤思考:

**Step 1 - 信息盘点**: 列出所有可用的信息源类型及其状态(有/无/部分)
- 字幕: [有/无/部分] {subtitle_length}字符
- 简介: [有/无] {desc_length}字符
- 弹幕: [有/无] {danmaku_count}条
- 评论: [有/无] {comment_count}条
- 标签: [有/无] {tags_length}字符
- 画面文字(OCR): [有/无] {ocr_length}字符

**Step 2 - 核心主题识别**: 从标题和已识别信息中提取视频核心主题
- 标题关键词: [提取]
- 核心主题: [一句话概括]

**Step 3 - 关键信息提取**: 从最重要的信息源中提取2-3条最关键信息
- 信息1: [从哪来? 引用原文]
- 信息2: [从哪来? 引用原文]
- 信息3: [从哪来? 引用原文]

**Step 4 - 置信度评估**: 基于信息完整度,评估本次总结的可信度
- 信息完整度: [高/中/低]
- 是否依赖推测: [是/否]

**Step 5 - 输出生成**: 基于以上分析,生成结构化JSON输出""",

    "detailed": """## 思考步骤 (Step-by-Step Reasoning)

**Step 1 - 信息源全景分析**:
逐项列出每个信息源的状态和内容密度:
| 信息源 | 状态 | 字符数/条数 | 信息密度评估 |
|--------|------|------------|-------------|
| 字幕 | [有/无] | N | [高/中/低] |
| 简介 | [有/无] | N | [高/中/低] |
| ... | | | |

**Step 2 - 内容结构化拆解**:
将视频内容按逻辑拆解为3-5个主题块,每个块标注:
- 时间范围(如有时间戳)
- 主题关键词
- 是否为核心内容

**Step 3 - 深层信息提取**:
对每个主题块进行深层提取:
- 说了什么(what)
- 为什么这样说(why)
- 关键论据/证据
- 与其他块的关联

**Step 4 - 观众反馈分析** (如有评论/弹幕):
- 提取高频观点/情绪
- 识别有价值的补充信息
- 标注争议点(如有)

**Step 5 - 置信度与护栏自检**:
- 逐条检查输出是否仅来自提供的信息源
- 标注每条信息的来源和引用
- 确认无编造内容

**Step 6 - 生成结构化JSON输出**""",

    "keypoints": """## 思考步骤 (Step-by-Step Reasoning)

**Step 1 - 时间线梳理**:
如果字幕有时间戳,构建视频内容时间线:
- 开头(0-20%): [主题/内容]
- 中段(20-80%): [核心展开]
- 结尾(80-100%): [总结/升华]

**Step 2 - 信息密度分析**:
识别信息密度最高的段落,优先从中提取要点

**Step 3 - 要点分级**:
对每个提取的要点标注重要程度:
- critical: 视频核心论点,无此点则失去意义
- high: 主要支撑论点
- medium: 补充信息

**Step 4 - 去重与合并**:
- 合并语义重复的要点
- 确保每个要点独立且有价值

**Step 5 - 时间戳绑定** (如可用):
为每个要点标注大致时间位置

**Step 6 - 输出生成**: 按重要度排序,生成JSON""",

    "mindmap": """## 思考步骤 (Step-by-Step Reasoning)

**Step 1 - 中心主题提炼**:
从标题和内容核心中提取中心主题(一句话)

**Step 2 - 一级分支识别**:
将视频内容的逻辑结构拆解为2-7个一级分支:
- 按时间顺序拆分(如:引言->方法->结果->讨论->结论)
- 或按主题拆分(如:背景->原理->应用->局限->展望)

**Step 3 - 二级/三级细化**:
对每个一级分支进行2-3层细化,保持:
- 每个节点一个独立概念
- 同级节点互斥且完备(MECE原则)

**Step 4 - 关联标注**:
标注跨分支的逻辑关联(如有)

**Step 5 - 输出生成**: 生成JSON树形结构""",

    "study-note": """## 思考步骤 (Step-by-Step Reasoning)

**Step 1 - 学习目标设定**:
从视频内容中反推UP主希望观众学到什么,列出1-5个学习目标

**Step 2 - 核心概念提取**:
从字幕中识别关键术语、概念、定义:
- 识别首次出现的新术语
- 提取定义性语句
- 匹配举例说明

**Step 3 - 结构化笔记编排**:
按教学逻辑重组内容:
- 引言/背景 -> 核心知识点1 -> 核心知识点2 -> ... -> 总结/回顾

**Step 4 - 复习问题设计**:
基于核心概念生成3-5个自测问题
- 确保问题能直接从视频内容中找到答案
- 不编造视频中未回答的问题

**Step 5 - 输出生成**: 生成JSON学习笔记""",

    "qa": """## 思考步骤 (Step-by-Step Reasoning)

**Step 1 - 隐式问题提取**:
从视频内容中提取\"视频试图回答的问题\":
- 标题中的疑问
- 内容中讨论的核心问题
- 弹幕/评论中观众关心的问题

**Step 2 - 答案定位**:
对每个问题,在信息源中定位答案:
- 字幕原文
- 简介关键句
- 弹幕补充

**Step 3 - 答案可信度分级**:
- explicit: 字幕/简介中直接给出明确答案
- inferred: 从多处信息综合推断
- speculative: 基于碎片信息推测(需标注不确定性)

**Step 4 - 难度标注**:
- basic: 视频直接陈述的事实
- intermediate: 需要综合多个信息源理解
- advanced: 需要推断或背景知识

**Step 5 - 输出生成**: 生成JSON问答对"""
}


# ============================================================================
# Section 3: Few-Shot 示例 (双语文)
# ============================================================================

FEW_SHOT_EXAMPLES = {
    "brief": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有字幕 - 科技类视频
假设标题为"量子计算入门:从零理解量子比特",有完整字幕

```json
{
  "mode": "brief",
  "title": "量子计算入门:从零理解量子比特",
  "one_liner": "本视频用通俗语言解释了量子比特(qubit)的核心概念及其与传统比特的区别,适合量子计算零基础观众入门。",
  "key_points": [
    "传统比特只能是0或1,而量子比特可以同时处于0和1的叠加态",
    "量子纠缠使得多个量子比特之间形成非局域关联,这是量子计算并行性的基础",
    "当前量子计算的主要挑战是退相干问题,即量子态极易受环境干扰而坍缩"
  ],
  "has_subtitle": true,
  "confidence": "high",
  "citations": [
    {"point_index": 1, "source": "subtitle", "quote": "传统比特就像一盏灯,要么开要么关;量子比特则像一个可以同时开和关的球"},
    {"point_index": 2, "source": "subtitle", "quote": "量子纠缠是量子计算最神奇的地方,两个纠缠的量子比特无论相隔多远都能瞬时关联"},
    {"point_index": 3, "source": "subtitle", "quote": "退相干是目前量子计算最大的敌人"}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```

### 示例 2: 无字幕 - 基于简介/标签推测
假设标题为"【Vlog】一个人在东京的周末",无字幕,有标签"日本旅行,东京,一人旅,vlog"

```json
{
  "mode": "brief",
  "title": "【Vlog】一个人在东京的周末",
  "one_liner": "根据标题和标签推测,这是一个记录独自在东京度过周末的日常Vlog,可能包含逛街、美食和城市景观等内容。",
  "key_points": [
    "根据标签推测,视频展示了东京的周末生活场景",
    "标签'一人旅'表明这是独自旅行的记录,可能包含独自用餐、逛街等内容",
    "标签'vlog'表明采用第一人称日常记录风格"
  ],
  "has_subtitle": false,
  "confidence": "low",
  "citations": [
    {"point_index": 1, "source": "inferred", "quote": "基于标签'日本旅行,东京'推断"},
    {"point_index": 2, "source": "inferred", "quote": "基于标签'一人旅'推断"},
    {"point_index": 3, "source": "inferred", "quote": "基于标签'vlog'推断"}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```
""",
        "en": """
## Output Examples (Few-Shot)

### Example 1: With subtitles - Tech video
Title: "Quantum Computing 101: Understanding Qubits"

```json
{
  "mode": "brief",
  "title": "Quantum Computing 101: Understanding Qubits",
  "one_liner": "This video explains the core concept of qubits and how they differ from classical bits in an accessible way for beginners.",
  "key_points": [
    "Classical bits are binary (0 or 1), while qubits can exist in superposition of both states simultaneously",
    "Quantum entanglement enables non-local correlations between multiple qubits, forming the basis of quantum parallelism",
    "The primary challenge in quantum computing today is decoherence — quantum states are extremely fragile and easily collapse"
  ],
  "has_subtitle": true,
  "confidence": "high",
  "citations": [
    {"point_index": 1, "source": "subtitle", "quote": "A classical bit is like a light switch — on or off; a qubit is like a sphere that can be in any state on its surface"},
    {"point_index": 2, "source": "subtitle", "quote": "Entanglement is the most fascinating aspect of quantum computing"},
    {"point_index": 3, "source": "subtitle", "quote": "Decoherence is currently the biggest enemy of quantum computing"}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    },

    "detailed": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有完整字幕 - 科普类视频
标题"为什么猫咪总是把东西推下桌子? | 猫行为学"

```json
{
  "mode": "detailed",
  "title": "为什么猫咪总是把东西推下桌子? | 猫行为学",
  "overview": "本视频从猫行为学角度解释了猫咪推东西下桌子的四大原因:捕猎本能、注意力寻求、探索行为和领地标记。",
  "key_points": [
    {
      "heading": "原因一: 捕猎本能的延续",
      "detail": "猫咪用爪子拨动小物件是在模拟捕猎行为。在野外,猫会用前爪试探猎物的反应。家猫虽然没有捕猎需求,但这种本能行为被保留了下来。桌上的小物件(如笔、瓶盖)的大小和移动方式恰好触发了这种本能。",
      "timestamp": "01:20-03:45",
      "source": "subtitle",
      "quote": "当猫咪用爪子拨动桌上的小物件时,它的大脑里激活的是捕猎回路——它在测试这个'猎物'是否还活着。"
    },
    {
      "heading": "原因二: 注意力寻求行为",
      "detail": "猫咪很快学会了一个因果关系:推东西=人类反应。无论是呵斥还是追赶,对猫来说都是一种'互动',从而强化了这个行为。",
      "timestamp": "04:00-05:30",
      "source": "subtitle",
      "quote": "对猫咪来说,负面关注也是关注。如果你每次它推东西都看它一眼,它就学会了:推东西=主人看我。"
    },
    {
      "heading": "原因三: 触觉探索",
      "detail": "猫的爪垫有丰富的神经末梢,通过触碰物体来获取纹理、温度、重量等信息,这是它们的探索方式。",
      "timestamp": "05:45-07:10",
      "source": "subtitle",
      "quote": "猫咪爪垫上的触觉感受器比人类指尖还要密集,推东西是它们在'用手感知世界'。"
    },
    {
      "heading": "原因四: 领地标记",
      "detail": "猫的爪垫间有气味腺,推蹭物体时会留下气味标记,宣告领地。",
      "timestamp": "07:20-08:30",
      "source": "subtitle",
      "quote": "猫咪爪垫之间分布着气味腺,所以每次它推、拍、蹭一个物体,其实都在说'这是我的'。"
    },
    {
      "heading": "如何纠正这个行为",
      "detail": "UP主建议了三招:增加互动玩具、定时玩耍消耗精力、以及为贵重物品设置物理障碍。最重要的是不要用惩罚的方式。",
      "timestamp": "08:45-11:00",
      "source": "subtitle",
      "quote": "如果你想减少猫咪推东西的行为,最好的方法不是惩罚,而是满足它的狩猎和探索需求。"
    }
  ],
  "ocr_text_summary": "画面中出现关键数据:猫咪每天平均拨动物体行为的次数为8-15次,其中早晨(6-9am)和傍晚(5-8pm)为高峰期。",
  "audience_reactions": {
    "summary": "观众普遍认同UP主的解释,许多猫主人分享了自家猫咪的搞笑行为。热评集中在'原来我家猫不是在故意气我'的恍然大悟。",
    "hot_comments": [
      "原来我家主子不是故意气我!是我错怪它了!",
      "试了UP主说的增加互动玩具,真的有效!三天推东西次数明显减少了",
      "我家猫推的都是我的眼镜,已经换了三副了..."
    ]
  },
  "has_subtitle": true,
  "confidence": "high",
  "citations": [
    {"point_index": 1, "source": "subtitle", "quote": "当猫咪用爪子拨动桌上的小物件时..."},
    {"point_index": 2, "source": "subtitle", "quote": "对猫咪来说,负面关注也是关注..."},
    {"point_index": 3, "source": "subtitle", "quote": "猫咪爪垫上的触觉感受器..."},
    {"point_index": 4, "source": "subtitle", "quote": "猫咪爪垫之间分布着气味腺..."},
    {"point_index": 5, "source": "subtitle", "quote": "如果你想减少猫咪推东西的行为..."}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```

### 示例 2: 部分字幕 - 游戏实况
标题"【原神】4.0枫丹主线全剧情实况 #12",有部分字幕+弹幕+评论

```json
{
  "mode": "detailed",
  "title": "【原神】4.0枫丹主线全剧情实况 #12",
  "overview": "根据字幕、弹幕和评论推测,这是原神枫丹主线剧情的第12期实况,主要内容可能是林尼的魔术审判法庭戏。",
  "key_points": [
    {
      "heading": "剧情推进: 法庭审判高潮",
      "detail": "根据弹幕高频词'林尼''审判''魔术'推测,本段内容围绕枫丹法庭对林尼的审判展开,涉及魔术手法作为关键证据的辩论环节。弹幕中大量出现'反转''燃起来了'表明有高潮情节。",
      "timestamp": "推测 00:00-15:00",
      "source": "inferred",
      "quote": "基于弹幕'林尼这个魔术反转绝了'和'法庭戏做得真好'等评论推断"
    },
    {
      "heading": "UP主反应与互动",
      "detail": "根据字幕片段和评论,UP主在关键剧情处有大量情绪反应,包括对剧情反转的惊讶和角色对话的吐槽。",
      "timestamp": "推测 05:00-12:00",
      "source": "subtitle",
      "quote": "字幕片段: '不是吧!!!这也太离谱了!!!' '我真的没想到是这样的'"
    },
    {
      "heading": "观众讨论热点",
      "detail": "评论区集中讨论了剧情伏笔和后续发展预测,部分观众指出了之前剧情的伏笔回收。",
      "timestamp": "N/A",
      "source": "comment",
      "quote": "热评:'其实在第8期就有暗示...''枫丹主线的水准真的太高了'"
    }
  ],
  "ocr_text_summary": null,
  "audience_reactions": {
    "summary": "观众对法庭剧情的反转反应热烈,大量讨论剧情伏笔和角色塑造。弹幕密度在关键反转处达到峰值。",
    "hot_comments": [
      "枫丹主线真的是目前最好的主线",
      "林尼这个角色塑造得太好了",
      "第12期开始剧情直接起飞"
    ]
  },
  "has_subtitle": true,
  "confidence": "medium",
  "citations": [
    {"point_index": 1, "source": "inferred", "quote": "综合弹幕和评论关键词推断"},
    {"point_index": 2, "source": "subtitle", "quote": "字幕片段直接引用"},
    {"point_index": 3, "source": "comment", "quote": "评论区直接引用"}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    },

    "keypoints": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有字幕 - 教程类视频
标题"【Python教程】10分钟学会Pandas数据分析"

```json
{
  "mode": "keypoints",
  "title": "【Python教程】10分钟学会Pandas数据分析",
  "key_points": [
    {"index": 1, "point": "安装: pip install pandas 即可安装最新版Pandas库", "timestamp": "00:30", "source": "subtitle", "importance": "high"},
    {"index": 2, "point": "DataFrame是Pandas的核心数据结构,可以理解为一个类似Excel表格的二维数据表", "timestamp": "01:15", "source": "subtitle", "importance": "critical"},
    {"index": 3, "point": "读取CSV用 pd.read_csv('文件名'),读取Excel用 pd.read_excel('文件名')", "timestamp": "02:30", "source": "subtitle", "importance": "high"},
    {"index": 4, "point": "df.head() 查看前5行; df.info() 查看数据类型和缺失情况; df.describe() 查看统计摘要", "timestamp": "04:00", "source": "subtitle", "importance": "high"},
    {"index": 5, "point": "数据筛选: df[df['列名'] > 值] 按条件过滤; df.loc[] 按标签索引; df.iloc[] 按位置索引", "timestamp": "05:45", "source": "subtitle", "importance": "critical"},
    {"index": 6, "point": "缺失值处理: df.dropna() 删除缺失行; df.fillna(值) 填充缺失值", "timestamp": "07:20", "source": "subtitle", "importance": "medium"},
    {"index": 7, "point": "分组聚合: df.groupby('列名').mean() 按某列分组后求均值", "timestamp": "08:40", "source": "subtitle", "importance": "medium"}
  ],
  "has_subtitle": true,
  "confidence": "high",
  "generated_at": "2026-07-09T12:00:00Z"
}
```

### 示例 2: 无字幕 - 基于标签/简介推测
标题"2024年度最佳手机推荐(旗舰篇)",无字幕,有简介和标签

```json
{
  "mode": "keypoints",
  "title": "2024年度最佳手机推荐(旗舰篇)",
  "key_points": [
    {"index": 1, "point": "根据简介推测,视频可能涉及多个品牌的旗舰手机对比评测", "timestamp": "N/A", "source": "inferred", "importance": "high"},
    {"index": 2, "point": "标签包含'iPhone 16 Pro'、'华为Mate 70'、'小米15 Pro',推测涉及这三款机型", "timestamp": "N/A", "source": "tags", "importance": "high"},
    {"index": 3, "point": "标签'影像旗舰''性能旗舰'表明可能从影像和性能两个维度分别推荐", "timestamp": "N/A", "source": "tags", "importance": "medium"},
    {"index": 4, "point": "简介提到'预算区间从4000到10000元',推测覆盖中高端到顶配价位", "timestamp": "N/A", "source": "description", "importance": "medium"},
    {"index": 5, "point": "根据标题'年度最佳',推测为年度总结性质的内容,可能包括年度最佳XX奖项", "timestamp": "N/A", "source": "inferred", "importance": "medium"}
  ],
  "has_subtitle": false,
  "confidence": "low",
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    },

    "mindmap": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有字幕 - 知识科普
标题"人体免疫系统是如何工作的?"

```json
{
  "mode": "mindmap",
  "title": "人体免疫系统是如何工作的?",
  "central_topic": "人体免疫系统工作原理",
  "branches": [
    {
      "topic": "第一道防线: 物理和化学屏障",
      "children": [
        {"topic": "皮肤", "children": [{"topic": "角质层物理阻隔", "note": "最外层防线"}]},
        {"topic": "黏膜", "children": [{"topic": "呼吸道纤毛排除异物", "note": "咳嗽和打喷嚏的机制"}]},
        {"topic": "化学防御", "children": [{"topic": "胃酸杀菌", "note": "pH 1.5-3.5"}, {"topic": "溶菌酶", "note": "存在于眼泪和唾液中"}]}
      ]
    },
    {
      "topic": "第二道防线: 先天免疫",
      "children": [
        {"topic": "巨噬细胞", "children": [{"topic": "吞噬病原体", "note": "非特异性识别"}]},
        {"topic": "自然杀伤细胞(NK细胞)", "children": [{"topic": "消灭被病毒感染的细胞", "note": "不需要预先识别"}]},
        {"topic": "炎症反应", "children": [{"topic": "组胺释放", "note": "血管扩张,白细胞聚集"}]},
        {"topic": "补体系统", "children": [{"topic": "标记病原体", "note": "帮助吞噬细胞识别"}, {"topic": "直接裂解细菌", "note": "膜攻击复合物"}]}
      ]
    },
    {
      "topic": "第三道防线: 适应性免疫",
      "children": [
        {"topic": "T细胞", "children": [
          {"topic": "辅助T细胞(CD4+)", "note": "激活B细胞和其他免疫细胞"},
          {"topic": "杀伤T细胞(CD8+)", "note": "直接杀死被感染细胞"}
        ]},
        {"topic": "B细胞", "children": [
          {"topic": "产生抗体", "note": "特异性结合抗原"},
          {"topic": "记忆B细胞", "note": "长期免疫记忆,疫苗的原理"}
        ]}
      ]
    },
    {
      "topic": "免疫失调相关疾病",
      "children": [
        {"topic": "过敏", "children": [{"topic": "IgE过度反应", "note": "对无害物质产生免疫反应"}]},
        {"topic": "自身免疫病", "children": [{"topic": "免疫系统攻击自身组织", "note": "如类风湿性关节炎、1型糖尿病"}]},
        {"topic": "免疫缺陷", "children": [{"topic": "HIV/AIDS", "note": "破坏CD4+T细胞"}]}
      ]
    }
  ],
  "has_subtitle": true,
  "confidence": "high",
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    },

    "study-note": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有字幕 - 教学类视频
标题"【高中生物】光合作用全过程详解 | 光反应与暗反应"

```json
{
  "mode": "study-note",
  "title": "【高中生物】光合作用全过程详解 | 光反应与暗反应",
  "learning_objectives": [
    "理解光合作用的两个阶段:光反应和暗反应(卡尔文循环)",
    "掌握光反应中水的光解和ATP、NADPH的生成过程",
    "掌握暗反应中CO2的固定和C3的还原过程",
    "能写出光合作用的总反应方程式并解释各物质来源"
  ],
  "key_concepts": [
    {
      "term": "光反应",
      "definition": "在类囊体薄膜上进行,需要光,将光能转化为ATP和NADPH中的化学能,同时水分解产生氧气。",
      "examples": ["光合色素吸收光能", "水的光解: 2H₂O → 4H⁺ + 4e⁻ + O₂↑"],
      "source": "subtitle"
    },
    {
      "term": "暗反应(卡尔文循环)",
      "definition": "在叶绿体基质中进行,不需要光,利用光反应产生的ATP和NADPH将CO₂还原为糖类(C₃→C₆)。",
      "examples": ["CO₂固定: CO₂ + C₅ → 2C₃", "C₃还原: 利用ATP和NADPH"],
      "source": "subtitle"
    },
    {
      "term": "光合作用总反应式",
      "definition": "6CO₂ + 12H₂O →(光能,叶绿体)→ C₆H₁₂O₆ + 6O₂ + 6H₂O",
      "examples": ["注意: 产生的O₂全部来自H₂O,不是CO₂"],
      "source": "subtitle"
    }
  ],
  "structured_notes": [
    {
      "section_title": "一、光合作用概述",
      "content": "光合作用是绿色植物利用光能,将CO₂和H₂O转化为有机物并释放O₂的过程。场所是叶绿体。分为光反应和暗反应两个阶段。",
      "timestamp": "00:00-02:30"
    },
    {
      "section_title": "二、光反应阶段(详细)",
      "content": "场所:类囊体薄膜。条件:需要光、色素、酶。过程:1)光能吸收:色素分子吸收光能;2)水的光解:2H₂O→4H⁺+4e⁻+O₂↑;3)电子传递:电子沿传递链传递,推动H⁺跨膜运输;4)ATP合成:H⁺通过ATP合酶回流,驱动ATP合成(光合磷酸化);5)NADPH生成:NADP⁺+2e⁻+H⁺→NADPH。产物:ATP、NADPH、O₂。",
      "timestamp": "02:30-08:00"
    },
    {
      "section_title": "三、暗反应阶段(卡尔文循环)",
      "content": "场所:叶绿体基质。条件:不需要光,需要多种酶。过程:1)CO₂固定:CO₂+C₅(核酮糖-1,5-二磷酸)→2C₃(3-磷酸甘油酸),由RuBisCO酶催化;2)C₃还原:利用光反应产生的ATP和NADPH将C₃还原为G3P(三碳糖磷酸);3)C₅再生:部分G3P经过一系列反应再生成C₅,保证循环继续。净产物:每固定3分子CO₂,净生成1分子G3P(用于合成葡萄糖等有机物)。",
      "timestamp": "08:00-14:30"
    },
    {
      "section_title": "四、光反应与暗反应的比较",
      "content": "光反应:需要光,场所类囊体薄膜,水光解放氧,产生ATP和NADPH。暗反应:不需要光(但需要光反应产物),场所叶绿体基质,CO₂固定和还原,消耗ATP和NADPH,产生糖类。两者关系:光反应为暗反应提供ATP和NADPH;暗反应为光反应提供ADP、Pi和NADP⁺。",
      "timestamp": "14:30-17:00"
    }
  ],
  "summary": "光合作用是高中生物的核心考点。关键理解:1)光反应和暗反应的区别与联系;2)产生的O₂全部来自水的光解;3)ATP和NADPH是连接两个阶段的纽带。",
  "review_questions": [
    "光合作用产生的氧气来自哪种反应物?",
    "光反应和暗反应分别在叶绿体的什么部位进行?",
    "如果停止光照,暗反应还能继续进行吗?为什么?",
    "写出光合作用的总反应方程式。",
    "RuBisCO酶在光合作用中催化什么反应?"
  ],
  "has_subtitle": true,
  "confidence": "high",
  "citations": [
    {"point_index": 1, "source": "subtitle", "quote": "光合作用分为光反应和暗反应两个阶段"},
    {"point_index": 2, "source": "subtitle", "quote": "光反应在类囊体薄膜上进行"}
  ],
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    },

    "qa": {
        "zh": """
## 输出示例 (Few-Shot Examples)

### 示例 1: 有字幕 - 科普问答
标题"黑洞的5个常见问题,一次讲清楚"

```json
{
  "mode": "qa",
  "title": "黑洞的5个常见问题,一次讲清楚",
  "questions_and_answers": [
    {
      "id": 1,
      "question": "黑洞是什么?",
      "answer": "黑洞是时空中的一个区域,其引力极其强大,以至于没有任何东西(包括光)能从中逃脱。黑洞通常由大质量恒星在生命末期引力坍缩形成。黑洞的边界称为'事件视界',一旦越过这个边界就再也无法返回。",
      "answer_source": "explicit",
      "timestamp": "00:45-03:20",
      "source_quote": "黑洞是宇宙中最极端的天体,它的引力大到连光都逃不出来。你可以把事件视界想象成一个单向门——东西可以进去,但永远出不来。",
      "difficulty": "basic"
    },
    {
      "id": 2,
      "question": "如果掉进黑洞会发生什么?",
      "answer": "从外部观察者角度看,掉入者似乎在事件视界处永远冻结(时间膨胀效应)。从掉入者自身角度看,会经历'意大利面条化'(spaghettification)——头部和脚部受到的引力差(潮汐力)会将身体拉成细长条,最终在奇点处被摧毁。黑洞质量越小,潮汐力越强,意大利面条化越早发生。",
      "answer_source": "explicit",
      "timestamp": "03:30-07:00",
      "source_quote": "你掉进黑洞的时候不会'消失'——从外面看你会永远停在黑洞边缘。但你自己可不好受,你会被拉成一根意大利面,这叫spaghettification。",
      "difficulty": "intermediate"
    },
    {
      "id": 3,
      "question": "黑洞会蒸发吗?",
      "answer": "会的。根据霍金辐射理论,黑洞不是完全'黑'的——由于量子效应,黑洞会缓慢地辐射能量并逐渐蒸发。但这个过程非常缓慢:一个太阳质量的黑洞完全蒸发需要约10^67年,远比当前宇宙年龄(约138亿年)长。",
      "answer_source": "explicit",
      "timestamp": "07:15-09:30",
      "source_quote": "霍金发现黑洞其实会'蒸发',通过一种叫霍金辐射的量子效应。不过别担心,一个太阳那么大的黑洞蒸发完需要10的67次方年。",
      "difficulty": "intermediate"
    },
    {
      "id": 4,
      "question": "银河系中心有黑洞吗?",
      "answer": "有。银河系中心有一个超大质量黑洞,名为'Sagittarius A*'(人马座A*),质量约为太阳的400万倍。2022年,事件视界望远镜(EHT)发布了它的第一张照片。",
      "answer_source": "explicit",
      "timestamp": "09:45-11:30",
      "source_quote": "我们银河系正中心就有一个超大质量黑洞,叫Sagittarius A*,简称Sgr A*。2022年科学家第一次拍到了它的照片。",
      "difficulty": "basic"
    },
    {
      "id": 5,
      "question": "黑洞内部有什么?",
      "answer": "根据现有物理理论(广义相对论),黑洞中心存在一个'奇点'——密度无限大、体积无限小的点,我们已知的物理定律在奇点处失效。要真正理解黑洞内部,需要一套能将广义相对论和量子力学统一起来的量子引力理论,目前这仍是物理学最大的未解难题之一。",
      "answer_source": "explicit",
      "timestamp": "11:45-14:00",
      "source_quote": "黑洞最中心叫奇点,在那里所有物理定律都失效了。要理解黑洞内部,我们需要一个现在还存在的理论——量子引力。",
      "difficulty": "advanced"
    }
  ],
  "has_subtitle": true,
  "confidence": "high",
  "generated_at": "2026-07-09T12:00:00Z"
}
```
"""
    }
}


# ============================================================================
# Section 4: System Prompt - 角色与行为规范
# ============================================================================

SYSTEM_PROMPT = """<identity>
你是 BiliSum-AI,一个专业的B站(Bilibili)视频内容总结与分析助手。
你拥有以下核心能力:
1. 从视频字幕中提取结构化信息
2. 综合字幕、弹幕、评论、标签等多源数据进行交叉验证
3. 对无字幕视频进行基于元数据的合理推测
4. 生成多种格式的总结输出(简要/详细/要点/思维导图/学习笔记/问答)

你的核心原则是: 准确、可靠、来源可溯。宁可标注不确定性,也绝不编造内容。
</identity>

<capabilities>
你可以:
- 从字幕文本中提取关键信息和结构化要点
- 将弹幕和评论作为辅助信息源,补充观众视角
- 在无字幕时基于标题、简介、标签进行合理推测(但必须标注)
- 输出严格符合 JSON Schema 的结构化数据

你不可以:
- 编造视频中没有出现的任何人名、事件、数据或结论
- 将你的先验知识(训练数据中的知识)当作视频内容输出
- 在没有信息源的情况下给出确定性的陈述
- 对视频内容进行主观评价或价值判断(除非是总结观众评论的观点)
</capabilities>

<anti_hallucination_rules>
## 核心反幻觉规则 (MUST FOLLOW)
1. 输出的每一个事实陈述,都必须能在输入中找到对应的原文支持
2. 在每条输出中标注 `source` 字段,指明信息来源类型
3. 如果必须进行推测,使用 `source: "inferred"` 并说明推断逻辑
4. 置信度标注规则:
   - confidence: "high" → 有完整字幕,信息直接可验证
   - confidence: "medium" → 有部分字幕或依赖多源交叉验证
   - confidence: "low" → 无字幕,主要依赖元数据推测
5. 使用"可能"、"推测"、"根据XX推断"等语言描述不确定内容
6. 在回答前进行三步自检:
   (a) 这条信息是否直接来自提供的材料?
   (b) 如果不是,推断的依据是什么?
   (c) 是否已用适当的方式标注了不确定性?

<forbidden_patterns>
绝对禁止以下输出模式:
- ❌ "这个视频讲解了[某个概念]..." (如果字幕中从未出现该概念)
- ❌ "UP主认为..." (如果字幕没有第一人称表达)
- ❌ "视频中提到了A、B、C..." (如果A不在任何信息源中)
- ❌ 使用确定语气描述推测内容
- ❌ 编造具体数据/日期/人名
</forbidden_patterns>
</anti_hallucination_rules>

<output_format>
你必须严格输出一个合法的JSON对象,符合指定的JSON Schema。
不要输出任何JSON之外的文本(包括解释、前缀、后缀)。
不要使用markdown代码块包裹JSON(除非示例中明确要求)。
所有输出必须使用中文。All output must be in Chinese.
</output_format>"""


# ============================================================================
# Section 5: 主 Prompt 构建器
# ============================================================================

@dataclass
class PromptContext:
    """Prompt 构建上下文"""
    info: VideoInfo
    subtitle: SubtitleData
    comments: list
    mode: str = "detailed"
    ocr_text: str = ""
    danmaku: list = None
    language: str = "zh"  # zh or en
    max_subtitle_length: int = 12000
    max_ocr_length: int = 5000
    max_danmaku_count: int = 50
    max_comment_count: int = 15

    def __post_init__(self):
        if self.danmaku is None:
            self.danmaku = []


class PromptEngine:
    """
    BiliSum Prompt Engine v2.0
    整合 prompt-engineer skill 的全部最佳实践:
    - 6种输出模式 (brief/detailed/keypoints/mindmap/study-note/qa)
    - Chain-of-Thought 引导
    - Few-Shot 双语示例
    - JSON Schema 结构化输出约束
    - 抗幻觉护栏 + 来源引用
    - System Prompt 分离 (针对 Anthropic API)
    """

    SUPPORTED_MODES = ["brief", "detailed", "keypoints", "mindmap", "study-note", "qa"]

    def __init__(self, language: str = "zh"):
        self.language = language

    # ------------------------------------------------------------------
    # 5.1 视频信息组装
    # ------------------------------------------------------------------
    def build_video_context(self, ctx: PromptContext) -> str:
        """组装视频信息上下文,使用XML标签分隔不同信息源"""
        from summarizer import _sanitize_llm_field
        parts = []

        # 标题 (最高优先级信息)
        if ctx.info.title:
            parts.append(f'<title>{_sanitize_llm_field(ctx.info.title, "title")}</title>')

        # 简介
        if ctx.info.desc and len(ctx.info.desc) > 20:
            desc = _sanitize_llm_field(ctx.info.desc[:2000], "description")
            parts.append(f'<description>{desc}</description>')

        # 字幕 (核心信息源)
        if ctx.subtitle.text:
            st = ctx.subtitle.text
            if len(st) > ctx.max_subtitle_length:
                st = st[:ctx.max_subtitle_length] + "\n...[字幕过长,已截断]..."
            parts.append(f'<subtitle>\n{_sanitize_llm_field(st, "subtitle")}\n</subtitle>')

        # 画面文字 OCR
        if ctx.ocr_text and len(ctx.ocr_text) > 5:
            ocr = _sanitize_llm_field(ctx.ocr_text[:ctx.max_ocr_length], "ocr_text")
            parts.append(f'<ocr_text>{ocr}</ocr_text>')

        # 弹幕
        if ctx.danmaku and len(ctx.danmaku) > 0:
            danmaku_sample = ctx.danmaku[:ctx.max_danmaku_count]
            dm_text = _sanitize_llm_field(" | ".join(danmaku_sample), "danmaku")
            parts.append(f'<danmaku count="{len(ctx.danmaku)}" shown="{len(danmaku_sample)}">{dm_text}</danmaku>')

        # 标签
        if ctx.subtitle.tags:
            parts.append(f'<tags>{_sanitize_llm_field(ctx.subtitle.tags[:2000], "tags")}</tags>')

        # 视频描述(来自 subtitle.desc,当 text 为空时的备选)
        if ctx.subtitle.desc and len(ctx.subtitle.desc) > 10 and not ctx.subtitle.text:
            parts.append(f'<video_description>{_sanitize_llm_field(ctx.subtitle.desc[:2000], "description")}</video_description>')

        # 评论
        if ctx.comments and len(ctx.comments) > 0:
            comment_entries = ctx.comments[:ctx.max_comment_count]
            comments_str = "\n".join([
                f"  [{_sanitize_llm_field(c.user, 'username')}] (likes:{c.likes}): {_sanitize_llm_field(c.content, 'comment')}"
                for c in comment_entries
            ])
            parts.append(f'<comments count="{len(ctx.comments)}" shown="{len(comment_entries)}">\n{comments_str}\n</comments>')

        return "\n\n".join(parts)

    # ------------------------------------------------------------------
    # 5.2 信息源状态摘要 (供 CoT 使用)
    # ------------------------------------------------------------------
    def build_source_status(self, ctx: PromptContext) -> dict:
        """构建信息源状态摘要"""
        return {
            "subtitle_length": len(ctx.subtitle.text) if ctx.subtitle.text else 0,
            "desc_length": len(ctx.info.desc) if ctx.info.desc else 0,
            "danmaku_count": len(ctx.danmaku) if ctx.danmaku else 0,
            "comment_count": len(ctx.comments) if ctx.comments else 0,
            "tags_length": len(ctx.subtitle.tags) if ctx.subtitle.tags else 0,
            "ocr_length": len(ctx.ocr_text) if ctx.ocr_text else 0
        }

    # ------------------------------------------------------------------
    # 5.3 CoT 模板填充
    # ------------------------------------------------------------------
    def fill_cot_template(self, mode: str, ctx: PromptContext) -> str:
        """填充 CoT 模板中的变量"""
        if mode not in COT_TEMPLATES:
            return ""

        template = COT_TEMPLATES[mode]
        status = self.build_source_status(ctx)

        return template.format(
            subtitle_length=status["subtitle_length"],
            desc_length=status["desc_length"],
            danmaku_count=status["danmaku_count"],
            comment_count=status["comment_count"],
            tags_length=status["tags_length"],
            ocr_length=status["ocr_length"]
        )

    # ------------------------------------------------------------------
    # 5.4 语言选择器 (Few-Shot 示例)
    # ------------------------------------------------------------------
    def get_few_shot_examples(self, mode: str) -> str:
        """获取指定模式和语言的 few-shot 示例"""
        if mode not in FEW_SHOT_EXAMPLES:
            return ""

        examples = FEW_SHOT_EXAMPLES[mode]
        if self.language in examples:
            return examples[self.language]
        # fallback to Chinese
        return examples.get("zh", "")

    # ------------------------------------------------------------------
    # 5.5 JSON Schema 输出约束文本
    # ------------------------------------------------------------------
    def get_schema_instruction(self, mode: str) -> str:
        """生成 JSON Schema 输出约束指令"""
        if mode not in OUTPUT_SCHEMAS:
            mode = "detailed"

        schema = OUTPUT_SCHEMAS[mode]
        schema_json = json.dumps(schema, indent=2, ensure_ascii=False)

        return f"""## 输出格式约束 (JSON Schema)
你必须严格按照以下 JSON Schema 输出,不要添加任何额外字段:

```json
{schema_json}
```

重要提醒:
- 只输出 JSON 对象,不要有任何前缀/后缀文本
- 所有 required 字段必须存在
- `source` 字段必须从允许的枚举值中选择
- `confidence` 必须是 "high"、"medium" 或 "low"
- 如果某信息源不可用,对应的引用字段可以为 null 或空数组"""

    # ------------------------------------------------------------------
    # 5.6 主 Prompt 构建 (完整版)
    # ------------------------------------------------------------------
    def build_full_prompt(self, ctx: PromptContext) -> dict:
        """
        构建完整的 prompt (system + user message)
        返回 {"system": str, "user": str} 以便分别传给 Anthropic 和 OpenAI API
        """
        mode = ctx.mode if ctx.mode in self.SUPPORTED_MODES else "detailed"

        video_context = self.build_video_context(ctx)
        cot_guide = self.fill_cot_template(mode, ctx)
        few_shot = self.get_few_shot_examples(mode)
        schema_instruction = self.get_schema_instruction(mode)

        # 构建 user message
        user_message_parts = []

        # 1. 任务说明 (含模式描述)
        user_message_parts.append(self._get_mode_task_description(mode))

        # 2. 视频信息
        user_message_parts.append(f"## 视频信息\n\n<video_data>\n{video_context}\n</video_data>")

        # 3. CoT 引导
        if cot_guide:
            user_message_parts.append(cot_guide)

        # 4. 抗幻觉护栏 (内联提醒)
        user_message_parts.append(ANTI_HALLUCINATION_GUARDRAILS)

        # 5. JSON Schema 约束
        user_message_parts.append(schema_instruction)

        # 6. Few-Shot 示例
        if few_shot:
            user_message_parts.append(few_shot)

        # 7. 最终指令
        user_message_parts.append(f"""## 最终指令

现在,请对以上视频信息执行 {mode} 模式的总结。

请先按照上面的思考步骤(Step-by-Step)进行分析,然后在分析完成后输出最终的JSON结果。

再次强调:
- 只输出 JSON,不要有任何其他文字
- 严格遵守 JSON Schema
- 每条事实必须有来源标注
- 不确定的内容必须标明推测
- 所有内容请用中文输出

请开始。""")

        user_message = "\n\n".join(user_message_parts)

        return {
            "system": SYSTEM_PROMPT,
            "user": user_message
        }

    # ------------------------------------------------------------------
    # 5.7 各模式任务描述
    # ------------------------------------------------------------------
    def _get_mode_task_description(self, mode: str) -> str:
        descriptions = {
            "brief": """## 任务: 简要总结 (Brief Summary)

请对以下B站视频内容进行简要总结,输出格式为严格的结构化JSON。

**输出要求:**
- 一句话概括视频核心内容(不超过150字)
- 提取2-3条最关键的信息
- 标注信息来源和置信度
- 如果缺少字幕,基于可用信息推测并标明""",

            "detailed": """## 任务: 详细总结 (Detailed Summary)

请对以下B站视频内容进行详细的结构化总结,输出格式为严格的结构化JSON。

**输出要求:**
- 视频主题概述(一句话)
- 3-5个关键要点,每个要点包含:标题、详细说明、时间戳(如可用)、信息来源、原文引用
- 画面文字总结(如有OCR数据)
- 观众观点总结(如有评论/弹幕数据)
- 标注信息来源和置信度""",

            "keypoints": """## 任务: 关键要点提取 (Key Points Extraction)

请从以下B站视频内容中提取关键要点,输出格式为严格的结构化JSON。

**输出要求:**
- 提取5-10个关键要点
- 每个要点标注:序号、内容、时间戳(如可用)、信息来源、重要程度(critical/high/medium)
- 按重要程度排序
- 如果有时间戳信息,尽量标注""",

            "mindmap": """## 任务: 思维导图大纲 (Mind Map Outline)

请为以下B站视频内容生成一个结构化的思维导图大纲,输出格式为严格的JSON树形结构。

**输出要求:**
- 确定中心主题(一句话)
- 拆解为2-7个一级分支(按逻辑或时间顺序)
- 每个一级分支展开2-3级子分支
- 同级分支遵循MECE原则(互斥且完备)
- 叶子节点可包含补充说明(notes)""",

            "study-note": """## 任务: 学习笔记 (Study Notes)

请将以下B站视频内容转化为结构化的学习笔记,输出格式为严格的JSON。

**输出要求:**
- 列出1-5个学习目标(从视频内容反推UP主想教什么)
- 提取核心概念(术语+定义+举例+来源)
- 按教学逻辑编排结构化笔记(分段+时间戳)
- 提供学习总结
- 生成3-5个自测复习问题(答案必须能在视频中找到)
- 基于Bloom分类法标注认知层次""",

            "qa": """## 任务: 问答对生成 (Q&A Generation)

请从以下B站视频中提取并生成问答对,输出格式为严格的JSON。

**输出要求:**
- 提取3-10个问答对
- 问题来源:标题中的疑问、内容核心问题、弹幕/评论中的高频问题
- 答案必须在信息源中有依据
- 标注答案来源类型:explicit(直接回答)/inferred(推断)/speculative(推测)
- 标注难度:basic/intermediate/advanced
- 提供答案的原文引用""",
        }

        return descriptions.get(mode, descriptions["detailed"])

    # ------------------------------------------------------------------
    # 5.8 Token 估算 (使用 tiktoken 近似)
    # ------------------------------------------------------------------
    def estimate_tokens(self, text: str, model_family: str = "claude") -> int:
        """
        估算文本的 token 数。
        Claude 使用约 1 token ≈ 3.5 中文字符 或 4 英文字符的粗略估计。
        精确计算需要 tiktoken,此处使用近似算法快速估计。
        """
        # 粗略估算:中文约 1.5 char/token, 英文约 4 char/token
        # 使用混合策略: 统计中文字符数和英文字符数
        chinese_chars = len(re.findall(r'[一-鿿　-〿＀-￯]', text))
        other_chars = len(text) - chinese_chars

        # 中文约 0.6-0.7 token/char, 英文约 0.25 token/char
        estimated = int(chinese_chars * 0.65 + other_chars * 0.25)
        return estimated

    # ------------------------------------------------------------------
    # 5.9 Prompt 版本信息
    # ------------------------------------------------------------------
    def get_prompt_metadata(self, ctx: PromptContext) -> dict:
        """获取 prompt 构建的元数据(用于日志/调试/版本追踪)"""
        full_prompt = self.build_full_prompt(ctx)
        system_tokens = self.estimate_tokens(full_prompt["system"])
        user_tokens = self.estimate_tokens(full_prompt["user"])

        return {
            "version": "2.0.0",
            "mode": ctx.mode,
            "language": self.language,
            "system_tokens_estimated": system_tokens,
            "user_tokens_estimated": user_tokens,
            "total_tokens_estimated": system_tokens + user_tokens,
            "has_subtitle": bool(ctx.subtitle.text),
            "has_ocr": bool(ctx.ocr_text and len(ctx.ocr_text) > 5),
            "has_danmaku": bool(ctx.danmaku),
            "has_comments": bool(ctx.comments),
            "features": [
                "cot_guided",
                "few_shot_examples",
                "json_schema_constrained",
                "anti_hallucination_guardrails",
                "source_citation",
                "confidence_scoring",
                "dual_language_examples"
            ]
        }


# ============================================================================
# Section 6: 兼容层 - 无缝替换旧的 build_prompt()
# ============================================================================

def build_prompt_v2(
    info: VideoInfo,
    subtitle: SubtitleData,
    comments: list,
    mode: str = "detailed",
    ocr_text: str = "",
    danmaku: list = None,
    language: str = "zh"
) -> dict:
    """
    v2.0 build_prompt - 返回 {"system": str, "user": str}
    完全替代 summarizer.py:10-98 的旧 build_prompt()

    使用方式:
        engine = PromptEngine(language="zh")
        ctx = PromptContext(info, subtitle, comments, mode, ocr_text, danmaku or [])
        prompt_dict = engine.build_full_prompt(ctx)
        # prompt_dict["system"] -> 传给 Anthropic 的 system parameter
        # prompt_dict["user"] -> 传给 messages[0]["content"]
    """
    engine = PromptEngine(language=language)
    ctx = PromptContext(
        info=info,
        subtitle=subtitle,
        comments=comments,
        mode=mode,
        ocr_text=ocr_text,
        danmaku=danmaku or []
    )
    return engine.build_full_prompt(ctx)


def build_prompt_legacy(
    info: VideoInfo,
    subtitle: SubtitleData,
    comments: list,
    mode: str = "detailed",
    ocr_text: str = "",
    danmaku: list = None
) -> str:
    """
    v2.0 兼容旧格式 - 返回拼接后的纯文本 prompt (向后兼容)
    当 API 不支持分离 system/user 时使用
    """
    prompt_dict = build_prompt_v2(info, subtitle, comments, mode, ocr_text, danmaku)
    return f"{prompt_dict['system']}\n\n---\n\n{prompt_dict['user']}"


# ============================================================================
# Section 7: 输出解析与验证
# ============================================================================

def parse_and_validate_output(raw_output: str, mode: str) -> dict:
    """
    解析 LLM 原始输出为结构化数据,并进行 Schema 验证

    Args:
        raw_output: LLM 返回的原始文本
        mode: 模式名称

    Returns:
        {"valid": bool, "data": dict|None, "error": str|None, "raw": str}
    """
    result = {"valid": False, "data": None, "error": None, "raw": raw_output}

    # Step 1: 尝试从输出中提取 JSON
    json_str = raw_output.strip()

    # 尝试移除 markdown 代码块包裹
    md_match = re.search(r'```(?:json)?\s*\n?(.*?)\n?```', raw_output, re.DOTALL)
    if md_match:
        json_str = md_match.group(1).strip()

    # Step 2: 尝试解析 JSON
    try:
        data = json.loads(json_str)
    except json.JSONDecodeError as e:
        # 尝试找到 JSON 对象的起止位置
        start = json_str.find('{')
        end = json_str.rfind('}')
        if start != -1 and end != -1 and end > start:
            try:
                data = json.loads(json_str[start:end+1])
            except json.JSONDecodeError:
                result["error"] = f"JSON解析失败: {str(e)}"
                return result
        else:
            result["error"] = f"JSON解析失败: {str(e)}"
            return result

    # Step 3: Schema 验证
    if mode not in OUTPUT_SCHEMAS:
        mode = "detailed"

    schema = OUTPUT_SCHEMAS[mode]
    required_fields = schema.get("required", [])

    # 检查 required 字段
    missing = [f for f in required_fields if f not in data]
    if missing:
        result["error"] = f"缺少必需字段: {missing}"
        return result

    # 检查 mode 字段匹配
    if data.get("mode") != mode:
        result["error"] = f"mode字段不匹配: 期望'{mode}', 得到'{data.get('mode')}'"
        return result

    # Step 4: 反幻觉检查 - 检查是否有来源标注
    has_citations = False
    if "citations" in data and data["citations"]:
        has_citations = True
    if "key_points" in data:
        for kp in data["key_points"]:
            if isinstance(kp, dict) and "source" in kp:
                has_citations = True
                break

    # Step 4b: 类型与边界验证 (deep schema validation)
    type_errors = []
    for field in required_fields:
        if field not in data:
            continue  # already caught above
        value = data[field]
        prop = schema["properties"].get(field, {})
        expected_type = prop.get("type", "")
        # 类型检查
        if expected_type == "string" and not isinstance(value, str):
            type_errors.append(f"{field}: expected string, got {type(value).__name__}")
        elif expected_type == "array" and not isinstance(value, list):
            type_errors.append(f"{field}: expected array, got {type(value).__name__}")
        elif expected_type == "boolean" and not isinstance(value, bool):
            type_errors.append(f"{field}: expected boolean, got {type(value).__name__}")
        # 数组边界检查
        if isinstance(value, list):
            min_items = prop.get("minItems")
            max_items = prop.get("maxItems")
            if min_items is not None and len(value) < min_items:
                type_errors.append(f"{field}: expected >= {min_items} items, got {len(value)}")
            if max_items is not None and len(value) > max_items:
                type_errors.append(f"{field}: expected <= {max_items} items, got {len(value)}")
    if type_errors:
        result["error"] = f"Schema验证失败: {'; '.join(type_errors)}"
        return result

    result["valid"] = True
    result["data"] = data
    result["has_citations"] = has_citations

    return result


# ============================================================================
# Section 8: 交叉利用接口
# ============================================================================

class CrossSkillInterface:
    """
    与其他 Skill 的交叉利用接口
    - claude-api: 利用 Claude API 的 system parameter 和 token counting
    - summarize: 利用 summarize skill 的输出格式参考
    - prompt-optimizer: 利用 prompt-optimizer 的 A/B 测试和迭代优化
    """

    @staticmethod
    def to_claude_api_format(prompt_dict: dict, max_tokens: int = 4096) -> dict:
        """
        转换为 Claude Messages API 请求格式
        交叉利用: claude-api skill 的 system parameter 最佳实践
        """
        return {
            "model": "claude-sonnet-4-20250514",
            "max_tokens": max_tokens,
            "system": prompt_dict["system"],
            "messages": [
                {"role": "user", "content": prompt_dict["user"]}
            ]
        }

    @staticmethod
    def to_openai_api_format(prompt_dict: dict, max_tokens: int = 4096) -> dict:
        """
        转换为 OpenAI Chat Completions API 请求格式
        """
        return {
            "model": "gpt-4o",
            "max_tokens": max_tokens,
            "messages": [
                {"role": "system", "content": prompt_dict["system"]},
                {"role": "user", "content": prompt_dict["user"]}
            ],
            "response_format": {"type": "json_object"}
        }

    @staticmethod
    def to_prompt_optimizer_format(prompt_dict: dict, mode: str) -> dict:
        """
        转换为 prompt-optimizer 可用的 A/B 测试格式
        交叉利用: prompt-optimizer skill 的 A/B testing framework
        """
        return {
            "prompt_version": "v2.0.0",
            "mode": mode,
            "system_prompt": prompt_dict["system"],
            "user_prompt": prompt_dict["user"],
            "output_schema": OUTPUT_SCHEMAS.get(mode, {}),
            "evaluation_criteria": {
                "accuracy": "输出是否准确反映视频内容",
                "completeness": "是否覆盖了视频的所有关键信息",
                "conciseness": "是否简洁无冗余",
                "source_fidelity": "是否所有输出都有来源标注",
                "hallucination_rate": "编造内容的比例(应为0)"
            }
        }

    @staticmethod
    def to_summarize_skill_format(structured_output: dict) -> str:
        """
        将结构化输出转换为 summarize skill 友好的可读文本格式
        交叉利用: summarize skill 的输出格式约定
        """
        mode = structured_output.get("mode", "detailed")
        title = structured_output.get("title", "未知标题")

        lines = [f"# {title}", f"*总结模式: {mode}*", ""]

        if mode == "brief":
            lines.append(f"**一句话总结:** {structured_output.get('one_liner', '')}")
            lines.append("")
            lines.append("**关键信息:**")
            for i, kp in enumerate(structured_output.get("key_points", []), 1):
                lines.append(f"{i}. {kp}")
            lines.append(f"\n*置信度: {structured_output.get('confidence', 'N/A')}*")

        elif mode == "detailed":
            lines.append(f"**概述:** {structured_output.get('overview', '')}")
            lines.append("")
            lines.append("**关键要点:**")
            for kp in structured_output.get("key_points", []):
                lines.append(f"\n### {kp.get('heading', '')}")
                lines.append(kp.get("detail", ""))
                if kp.get("timestamp"):
                    lines.append(f"*时间: {kp['timestamp']}*")
                lines.append(f"*来源: {kp.get('source', 'N/A')}*")

        elif mode == "keypoints":
            for kp in structured_output.get("key_points", []):
                ts = kp.get("timestamp", "")
                imp = kp.get("importance", "")
                lines.append(f"- [{imp}] {kp.get('point', '')} {'(' + ts + ')' if ts else ''}")

        elif mode == "mindmap":
            lines.append(f"**中心主题:** {structured_output.get('central_topic', '')}")
            lines.append("")
            for branch in structured_output.get("branches", []):
                lines.append(f"## {branch.get('topic', '')}")
                for child in branch.get("children", []):
                    lines.append(f"  - {child.get('topic', '')}")
                    for grandchild in child.get("children", []):
                        note = f" ({grandchild.get('note', '')})" if grandchild.get('note') else ""
                        lines.append(f"    - {grandchild.get('topic', '')}{note}")

        elif mode == "study-note":
            lines.append("**学习目标:**")
            for obj in structured_output.get("learning_objectives", []):
                lines.append(f"- {obj}")
            lines.append("")
            lines.append("**核心概念:**")
            for concept in structured_output.get("key_concepts", []):
                lines.append(f"\n### {concept.get('term', '')}")
                lines.append(f"*{concept.get('definition', '')}*")
                for ex in concept.get("examples", []):
                    lines.append(f"  - 例: {ex}")

        elif mode == "qa":
            for qa in structured_output.get("questions_and_answers", []):
                lines.append(f"### Q{qa.get('id', '')}: {qa.get('question', '')}")
                lines.append(f"A: {qa.get('answer', '')}")
                lines.append(f"*来源: {qa.get('answer_source', '')} | 难度: {qa.get('difficulty', '')}*")
                lines.append("")

        return "\n".join(lines)
