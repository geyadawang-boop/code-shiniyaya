---
name: dynamic-summary-length
description: 动态总结长度功能 — 总结长度依据信息密度/知识价值度/理解难度/视频时长/字幕字数/画面丰富度，UP主内容单独提取
metadata: 
  node_type: memory
  type: plan
  priority: high
  created: 2026-07-13
  status: pending-codex-approval
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# 动态总结长度 + UP主内容单独提取

## 用户需求

1. 详细总结采用动态字数：依据信息密度、知识价值度、理解难度、视频时长、字幕字数、画面丰富度
2. 字幕+弹幕+评论区内容全部发给总结AI做参考
3. UP主发的评论/弹幕单独摘出来给总结AI
4. 总结长度在现有基础上适当加长

## 现有系统分析

### 已有 (quality.py compute_note_budget L180-276)

当前token预算计算使用的参数:
- duration_minutes — 视频时长 ✅
- subtitle_chars — 字幕字数 ✅
- comment_records — 评论条数 ✅
- quality_multiplier — 质量系数(来自7维互动数据) ✅

输出:
- target_min/target_max — 推荐字数范围
- max_tokens_recommendation — LLM max_tokens动态值
- quality_tier — high/medium/low
- granularity — module_level/chapter_level/section_level/point_level

### 缺失

1. **信息密度** — 字幕中有效信息占比 (非废话比例)
2. **知识价值度** — 教学/科普/深度内容 vs 娱乐/闲聊
3. **理解难度** — 术语密度/专业程度
4. **画面丰富度** — 目前完全未纳入 (需要OCR/视觉分析)
5. **UP主内容分离** — 弹幕+评论中UP主的发言未单独提取给AI
6. **弹幕数据** — compute_note_budget未接收danmaku_count

## 实现方案

### Phase 1: 文本分析层 (quality.py新增)

```python
def compute_information_density(subtitle_text: str) -> float:
    """计算字幕信息密度 (0-1)"""
    # 1. 去停用词后的有效词占比
    # 2. 唯一术语密度 (TF-IDF高频词数/总词数)
    # 3. 数字/专有名词占比
    # 返回: 信息密度分数

def compute_knowledge_value(video_type: str, subtitle_text: str, tags: list) -> float:
    """计算知识价值度 (0-1)"""
    # 1. video_type匹配: 教育/知识科普/教程 > 科技/评测 > 娱乐/生活
    # 2. 解释性语言比例 (因果词、定义句式)
    # 3. 标签中教学相关标签数
    # 返回: 知识价值分数

def compute_difficulty_level(subtitle_text: str) -> float:
    """计算理解难度 (0-1)"""
    # 1. 术语密度 (专业词汇数/总词数)
    # 2. 句子平均长度
    # 3. 抽象概念占比
    # 返回: 难度分数
```

### Phase 2: token预算增强 (quality.py compute_note_budget修改)

新增参数:
- information_density: float = 0.5
- knowledge_value: float = 0.5
- difficulty: float = 0.5
- danmaku_count: int = 0
- has_ocr: bool = False (为画面丰富度预留)

公式调整:
```
base_target_min = clamp(
    600
    + duration_minutes * 35
    + subtitle_chars * 0.025
    + evidence_blocks * 8
    + min(comment_records, 300) * 3
    + min(danmaku_count, 500) * 0.8          # NEW: 弹幕贡献
    + information_density * subtitle_chars * 0.01   # NEW: 高密度→更长总结
    + knowledge_value * duration_minutes * 10       # NEW: 高价值→更深入
    + difficulty * duration_minutes * 5             # NEW: 高难度→更详细解释
    , 1200, 45000
)
```

### Phase 3: UP主内容单独提取 (prompt_engine.py修改)

build_video_context() 新增:
- up_comments: UP主发的评论列表
- up_danmaku: UP主发的弹幕列表
- 在prompt中单独一节 "UP主观点" 列出UP主的评论和弹幕

### Phase 4: 画面丰富度 (远期)

当前: has_ocr=False占位
未来: 接入视频帧分析 → OCR文本量 → 画面信息密度

## 修改文件

1. backend/quality.py — 新增3个文本分析函数 + 增强compute_note_budget
2. backend/summarizer.py — 传递新参数
3. backend/prompt_engine.py — UP主内容单独段落
4. backend/routers/ai.py — 调用处传递danmaku/tags/UP主评论

## 关联
- [[bilisum-v8.1-compression-state]]
- [[bilisum-optimization-plan]]
