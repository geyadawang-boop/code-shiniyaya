"""
=============================================================================
BiliSum Video Classifier (smart-categorize v2.0)
=============================================================================
Multi-dimensional video content classifier: 12 video types x 5 dimensions
(type + topic + difficulty + duration + language).

Cross-utilization targets:
  - notebooklm: classification results feed into NotebookLM source grouping
  - multi-search-engine: category tags enhance multi-engine search queries
  - bili-note: auto-generated tags prepopulate exported Markdown frontmatter

Author: smart-categorize Skill Deep Redevelopment
Date:   2026-07-09
=============================================================================
"""

from __future__ import annotations

import json
import logging
import os
import re
import statistics
import logging
from dataclasses import dataclass, field, asdict

logger = logging.getLogger(__name__)
from datetime import datetime
from enum import Enum
from typing import Optional

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

from database import KB_DIR as KB_DIR
CLASSIFICATION_CACHE_FILE = os.path.join(KB_DIR, ".classification_cache.json")

# ---------------------------------------------------------------------------
# Enums & Dataclasses
# ---------------------------------------------------------------------------

class VideoType(str, Enum):
    """12 primary video content categories (B站-native taxonomy)."""
    TECH = "科技"            # Programming, AI, hardware, engineering
    ENTERTAINMENT = "娱乐"    # Variety shows, talk shows, comedy
    EDUCATION = "教育"        # Academic courses, lectures, exam prep
    LIFESTYLE = "生活"        # Vlogs, cooking, travel, daily life
    GAMING = "游戏"           # Gameplay, esports, game reviews
    MUSIC = "音乐"            # Music videos, performances, instrument tutorials
    FILM_TV = "影视"          # Movie/TV reviews, analysis, trailers
    KNOWLEDGE = "知识科普"    # Science popularization, history, philosophy
    TUTORIAL = "教程"         # How-to guides, step-by-step walkthroughs
    REVIEW = "评测"           # Product reviews, unboxing, comparisons
    NEWS = "新闻"             # Current events, politics, breaking news
    ANIME = "动漫"            # Anime, manga, ACG culture
    OTHER = "其他"            # Fallback

    @classmethod
    def from_label(cls, label: str) -> "VideoType":
        label = label.strip()
        for member in cls:
            if member.value == label:
                return member
        return cls.OTHER


class Difficulty(str, Enum):
    BEGINNER = "入门"
    INTERMEDIATE = "进阶"
    ADVANCED = "专业"


class Language(str, Enum):
    CHINESE = "中文"
    ENGLISH = "英文"
    MIXED = "混合"
    OTHER = "其他"


class QualityTier(str, Enum):
    S = "S"   # Exceptional: original research, deep insight, production excellence
    A = "A"   # High quality: well-structured, informative, engaging
    B = "B"   # Standard: acceptable content, useful but not exceptional
    C = "C"   # Low: superficial, repetitive, or thin content


class DurationCategory(str, Enum):
    SHORT = "短视频"      # < 5 min
    MEDIUM = "中等"        # 5-20 min
    LONG = "长视频"        # 20-60 min
    EXTENDED = "超长"      # > 60 min


# ---------------------------------------------------------------------------
# Classification Result
# ---------------------------------------------------------------------------

@dataclass
class ClassificationResult:
    """5-dimension classification output for a single video."""
    bvid: str = ""
    title: str = ""

    # Dimension 1: Content type
    video_type: str = VideoType.OTHER.value          # 12-class primary type
    video_type_confidence: float = 0.0               # 0.0-1.0

    # Dimension 2: Topic cluster (semantic topic within the type)
    topic: str = ""                                   # e.g. "Python异步编程" within TECH
    subtopics: list = field(default_factory=list)     # fine-grained subtopics

    # Dimension 3: Difficulty
    difficulty: str = Difficulty.INTERMEDIATE.value
    difficulty_confidence: float = 0.0

    # Dimension 4: Duration
    duration_category: str = DurationCategory.MEDIUM.value
    duration_seconds: int = 0

    # Dimension 5: Language
    language: str = Language.CHINESE.value

    # Metadata
    quality_tier: str = QualityTier.B.value
    tags: list = field(default_factory=list)          # LLM + rule generated
    keywords: list = field(default_factory=list)      # extracted key phrases
    reason: str = ""                                  # human-readable rationale
    classified_at: str = ""                           # ISO timestamp

    # Cross-skill metadata (for notebooklm, multi-search-engine, bili-note)
    cross_skill_hints: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        d = asdict(self)
        # Remove empty fields for cleaner storage
        return {k: v for k, v in d.items() if v or k == "video_type"}


# ---------------------------------------------------------------------------
# Rule Engine: Pattern-based pre-classification (no LLM required)
# ---------------------------------------------------------------------------

class RuleClassifier:
    """
    Fast, zero-cost pre-classification using title/author/partition patterns.
    Runs before LLM classification to reduce API calls.
    """

    # Title keyword -> (VideoType, confidence)
    TITLE_RULES: list[tuple[re.Pattern, VideoType, float]] = [
        # TECH
        (re.compile(r"编程|代码|Python|Java|Rust|React|Vue|前端|后端|AI|机器学习|深度学习|算法|数据结构|系统设计|架构"),
         VideoType.TECH, 0.85),
        (re.compile(r"芯片|半导体|显卡|GPU|CPU|硬件|电路|嵌入式"),
         VideoType.TECH, 0.80),
        # ENTERTAINMENT
        (re.compile(r"搞笑|挑战|真人秀|综艺|整蛊|鬼畜|吐槽|脱口秀|相声|小品"),
         VideoType.ENTERTAINMENT, 0.85),
        # EDUCATION
        (re.compile(r"高考|考研|四级|六级|雅思|托福|公开课|网课|备考|真题|课堂|讲课|教学|大学|中学|小学"),
         VideoType.EDUCATION, 0.85),
        # LIFESTYLE
        (re.compile(r"Vlog|日常|做饭|美食|旅游|穿搭|美妆|健身|家居|开箱|好物|探店"),
         VideoType.LIFESTYLE, 0.80),
        # GAMING
        (re.compile(r"游戏|实况|攻略|通关|单机|手游|端游|主机|Switch|PS5|Xbox|Steam|原神|王者|LOL|DOTA2|CS|赛博朋克|老头环"),
         VideoType.GAMING, 0.85),
        # MUSIC
        (re.compile(r"MV|翻唱|演奏|钢琴|吉他|小提琴|原创音乐|编曲|混音|DJ|电音|古典|摇滚|说唱|RAP|K-POP|练习室|直拍"),
         VideoType.MUSIC, 0.85),
        # FILM_TV
        (re.compile(r"影评|剧评|解说|拉片|电影|电视剧|番剧|纪录片|解读|几分钟.*(?:电影|剧)|速看|剧情"),
         VideoType.FILM_TV, 0.85),
        # KNOWLEDGE
        (re.compile(r"科普|历史|哲学|心理|经济|社会|政治|法律|物理|化学|生物|天文|地理|考古|人类学"),
         VideoType.KNOWLEDGE, 0.80),
        # TUTORIAL
        (re.compile(r"教程|教学|手把手|保姆级|从零|入门|快速上手|配置|安装|部署|实操|演示|示范"),
         VideoType.TUTORIAL, 0.80),
        # REVIEW
        (re.compile(r"评测|测评|体验|上手|对比|横评|值不值得|优缺点|深度|开箱试玩|首发"),
         VideoType.REVIEW, 0.85),
        # NEWS
        (re.compile(r"最新|突发|发布|发布会|官宣|速报|快讯|热点|事件|通报"),
         VideoType.NEWS, 0.75),
        # ANIME
        (re.compile(r"动漫|动画|番剧|漫画|二次元|手办|cos|cosplay|声优|新番|老番|国漫|日漫"),
         VideoType.ANIME, 0.85),
    ]

    # Title-based difficulty estimation
    DIFFICULTY_PATTERNS: list[tuple[re.Pattern, Difficulty, float]] = [
        (re.compile(r"入门|新手|小白|基础|初学|零基础|保姆级|从零|简单|快速上手"), Difficulty.BEGINNER, 0.85),
        (re.compile(r"进阶|深入|原理|源码|底层|高级|实战|优化|最佳实践|设计模式"), Difficulty.ADVANCED, 0.80),
        (re.compile(r"专业|博士|研究生|论文|学术|科研|顶级|大师|专家"), Difficulty.ADVANCED, 0.85),
    ]

    # Language detection (sampling-based)
    CJK_RANGES = [
        (0x4E00, 0x9FFF),   # CJK Unified
        (0x3400, 0x4DBF),   # CJK Extended A
        (0x20000, 0x2A6DF), # CJK Extended B
    ]

    @classmethod
    def classify_type(cls, title: str) -> tuple[VideoType, float]:
        """Rule-based video type classification. Returns (type, confidence)."""
        best_type = VideoType.OTHER
        best_conf = 0.0
        for pattern, vtype, conf in cls.TITLE_RULES:
            if pattern.search(title):
                if conf > best_conf:
                    best_type = vtype
                    best_conf = conf
        return best_type, best_conf

    @classmethod
    def classify_difficulty(cls, title: str) -> tuple[Difficulty, float]:
        """Rule-based difficulty estimation."""
        best_diff = Difficulty.INTERMEDIATE
        best_conf = 0.0
        for pattern, diff, conf in cls.DIFFICULTY_PATTERNS:
            if pattern.search(title):
                if conf > best_conf:
                    best_diff = diff
                    best_conf = conf
        return best_diff, best_conf

    @classmethod
    def detect_language(cls, text: str, sample_size: int = 2000) -> tuple[Language, float]:
        """Detect primary language by CJK vs ASCII ratio."""
        if not text:
            return Language.CHINESE, 0.5
        sample = text[:sample_size]
        total = len(sample)
        if total == 0:
            return Language.CHINESE, 0.5

        cjk_count = sum(
            1 for c in sample
            if any(lo <= ord(c) <= hi for lo, hi in cls.CJK_RANGES)
        )
        ascii_count = sum(1 for c in sample if ord(c) < 128 and c.isalpha())

        cjk_ratio = cjk_count / total
        ascii_ratio = ascii_count / total

        if cjk_ratio > 0.15 and ascii_ratio > 0.10:
            return Language.MIXED, 0.80
        elif cjk_ratio > 0.08:
            return Language.CHINESE, min(cjk_ratio * 3, 0.95)
        elif ascii_ratio > 0.30:
            return Language.ENGLISH, min(ascii_ratio, 0.95)
        else:
            return Language.CHINESE, 0.5

    @classmethod
    def categorize_duration(cls, seconds: int) -> DurationCategory:
        """Bucket video duration into a human-readable category."""
        if seconds <= 0:
            return DurationCategory.MEDIUM
        if seconds < 300:          # < 5 min
            return DurationCategory.SHORT
        elif seconds < 1200:       # 5-20 min
            return DurationCategory.MEDIUM
        elif seconds < 3600:       # 20-60 min
            return DurationCategory.LONG
        else:                      # > 60 min
            return DurationCategory.EXTENDED


# ---------------------------------------------------------------------------
# LLM-based Classifier
# ---------------------------------------------------------------------------

class LLMClassifier:
    """
    AI-powered classifier that uses the configured LLM to produce
    fine-grained classification beyond what pattern rules can achieve.
    """

    @staticmethod
    def build_prompt(title: str, text_sample: str, rule_hints: dict) -> str:
        """Build the classification prompt with rule-engine hints injected."""
        from summarizer import _sanitize_llm_field, _wrap_field
        safe_title = _sanitize_llm_field(title, "title")
        safe_text = _sanitize_llm_field(text_sample[:2000], "content")
        hints_block = ""
        if rule_hints:
            hints_block = "规则预分类提示（仅供参考，AI 可以覆盖）：\n"
            hints_block += json.dumps(rule_hints, ensure_ascii=False, indent=2) + "\n\n"

        return f"""你是 BiliSum 视频内容分类专家。分析以下B站视频并返回多维分类结果。

{hints_block}{_wrap_field('title', safe_title)}

视频文本前2000字:
{_wrap_field('content', safe_text)}

请严格按照以下JSON格式返回（不要包含markdown代码块标记）:
{{
  "video_type": "科技|娱乐|教育|生活|游戏|音乐|影视|知识科普|教程|评测|新闻|动漫|其他",
  "video_type_confidence": 0.0-1.0,
  "topic": "具体主题（10字内）",
  "subtopics": ["子主题1", "子主题2"],
  "difficulty": "入门|进阶|专业",
  "difficulty_confidence": 0.0-1.0,
  "language": "中文|英文|混合|其他",
  "quality_tier": "S|A|B|C",
  "tags": ["标签1", "标签2", "标签3", "标签4", "标签5"],
  "keywords": ["关键词1", "关键词2", "关键词3"],
  "reason": "30字内的分类理由",
  "cross_skill_hints": {{
    "notebooklm_group": "适合NotebookLM分组的类别名",
    "search_engine_queries": ["增强搜索引擎的搜索词1", "搜索词2"],
    "bili_note_tags": ["导出Markdown时使用的标签1", "标签2"]
  }}
}}

规则:
1. video_type 必须从给定的枚举值中选择
2. 置信度根据内容明确度赋值，非常明确=0.9+，较明确=0.7-0.9，模糊=0.5-0.7
3. quality_tier: S=顶级原创/深度洞察, A=高质量有结构, B=标准内容, C=较浅薄
4. cross_skill_hints 是给其他技能使用的元数据，请认真填写
"""


# ---------------------------------------------------------------------------
# Tag Generation Engine
# ---------------------------------------------------------------------------

class TagGenerator:
    """
    Generates tags using a mix of LLM extraction + rule-based filtering.
    Tags are formatted for:
      - Frontend tag clouds
      - Markdown frontmatter (bili-note integration)
      - Multi-search-engine query augmentation
    """

    # Blacklisted generic tags that add no signal
    TAG_BLACKLIST: set[str] = {
        "bilibili", "b站", "视频", "哔哩哔哩", "bilisum",
        "原创", "自制", "转载", "搬运", "投稿", "默认", "未分类",
        "热门", "推荐",
        # v8.2: high-frequency CJK stop words / pronouns / connectives
        "我们", "一个", "这个", "我的", "然后", "给我", "所以",
        "什么", "怎么", "可以", "没有", "如果", "因为", "但是",
        "大家", "其实", "真的", "知道", "还是", "已经", "可能",
        "是不是", "一下", "所有", "各种", "如何", "为什么",
    }

    # Minimum / maximum tag length
    MIN_TAG_LEN = 2
    MAX_TAG_LEN = 20

    @classmethod
    def filter_tags(cls, tags: list[str]) -> list[str]:
        """Apply blacklist, deduplication, length constraints, and CJK garbage patterns."""
        # v8.3: CJK garbage patterns that produce meaningless fragments
        _garbage_patterns = [
            r"^的.", r".的$",     # possessive particle fragments: "的档", "子的"
            r"^.了", r".了$",     # aspect particle fragments: "了我", "动了"
            r"^个.", r".个$",     # classifier fragments: "个这", "这个"(已黑名单)
            r"^.们", r".们$",     # plural fragments: "们的", "们可以"
            r"^后.",              # temporal sequencer: "后我"
            r"^.给.", r"^给.",   # dative marker: "给我", "能给"
        ]
        import re as _re_filter
        seen = set()
        result = []
        for tag in tags:
            tag_clean = tag.strip().lower()
            if not tag_clean:
                continue
            if len(tag_clean) < cls.MIN_TAG_LEN:
                continue
            if len(tag_clean) > cls.MAX_TAG_LEN:
                continue
            if tag_clean in cls.TAG_BLACKLIST:
                continue
            # v8.3: Character-level CJK garbage pattern check
            if any(_re_filter.match(p, tag_clean) for p in _garbage_patterns):
                continue
            if tag_clean in seen:
                continue
            seen.add(tag_clean)
            result.append(tag.strip())  # Preserve original casing from LLM
        return result[:10]  # Cap at 10 tags

    @classmethod
    def extract_keywords_from_text(cls, text: str, top_n: int = 10) -> list[str]:
        """
        Fast keyword extraction using TF-like heuristics.
        Removes stopwords and returns top-N frequent CJK bigrams/trigrams.
        """
        if not text:
            return []

        # CJK stop characters — v8.2 expanded
        stop_chars = set("的了吗呢吧啊呀嗯哼着也在就和与或到从被把让对向以可以会要能都还但只没不太这那是"
                         "我你他她它们个些每很什么怎么怎哪子过有给后里上下中")

        # Extract CJK n-grams
        def extract_ngrams(s: str, n: int) -> list[str]:
            cjk = [c for c in s if '一' <= c <= '鿿']
            return [''.join(cjk[i:i+n]) for i in range(len(cjk) - n + 1)]

        bigrams = extract_ngrams(text, 2)
        trigrams = extract_ngrams(text, 3)

        # Count frequencies
        from collections import Counter
        freq = Counter(bigrams + trigrams)

        # Filter and score
        scored = []
        for ngram, count in freq.most_common(50):
            # Reject if >=50% of chars are stop_chars (v8.2: was "all(c in stop_chars)")
            if len(ngram) >= 3:
                # v8.3: For trigrams, >=1 stop char = reject (was >=2, missed "的档案","的信息")
                stop_count = sum(1 for c in ngram if c in stop_chars)
                if stop_count >= 1:
                    continue
            else:
                # For bigrams, any stop char = reject (prevents "们的","这个","一个")
                if any(c in stop_chars for c in ngram):
                    continue
            # Prefer longer n-grams
            score = count * (1.2 if len(ngram) == 3 else 1.0)
            scored.append((ngram, score))

        scored.sort(key=lambda x: x[1], reverse=True)
        return [item[0] for item in scored[:top_n]]

    @classmethod
    def merge_tags(cls, llm_tags: list[str], keyword_tags: list[str],
                   rule_tags: list[str]) -> list[str]:
        """
        Merge tags from three sources, deduplicate, and return a ranked list.
        Priority: LLM > keyword > rule
        """
        combined = []
        seen = set()

        # LLM tags first (highest quality)
        for tag in llm_tags:
            clean = tag.strip().lower()
            if clean not in seen:
                seen.add(clean)
                combined.append(tag.strip())

        # Keyword extraction next
        for tag in keyword_tags:
            clean = tag.strip().lower()
            if clean not in seen:
                seen.add(clean)
                combined.append(tag.strip())

        # Rule-generated fallback
        for tag in rule_tags:
            clean = tag.strip().lower()
            if clean not in seen:
                seen.add(clean)
                combined.append(tag.strip())

        return cls.filter_tags(combined)


# ---------------------------------------------------------------------------
# Main VideoClassifier Class
# ---------------------------------------------------------------------------

class VideoClassifier:
    """
    Primary classifier orchestrating rule engine + LLM classifier + tag generation.

    Usage:
        clf = VideoClassifier()
        result = await clf.classify(bvid, title, text, duration_seconds=300)
        clf.persist(result)  # Save to KB JSON + cache
    """

    def __init__(self):
        self._classification_cache: dict[str, ClassificationResult] = {}
        self._load_cache()

    # ---- Cache management ----

    def _load_cache(self):
        """Load persisted classification results from disk cache."""
        if os.path.exists(CLASSIFICATION_CACHE_FILE):
            try:
                with open(CLASSIFICATION_CACHE_FILE, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                cache: dict[str, ClassificationResult] = {}
                bad_entries = 0
                for bvid, data in raw.items():
                    try:
                        cache[bvid] = ClassificationResult(**data)
                    except (TypeError, ValueError) as e:
                        bad_entries += 1
                        print(f"[classifier] Skipping corrupt cache entry {bvid}: {e}")
                self._classification_cache = cache
                if bad_entries > 0:
                    print(f"[classifier] Loaded cache with {len(cache)} entries "
                          f"({bad_entries} corrupt entries skipped)")
            except (json.JSONDecodeError, IOError, OSError) as e:
                print(f"[classifier] Failed to load classification cache: {e}")
                self._classification_cache = {}

    def _save_cache(self):
        """Persist classification cache to disk (atomic write)."""
        os.makedirs(os.path.dirname(CLASSIFICATION_CACHE_FILE), exist_ok=True)
        serializable = {
            bvid: result.to_dict()
            for bvid, result in self._classification_cache.items()
        }
        tmp_path = CLASSIFICATION_CACHE_FILE + ".tmp"
        try:
            with open(tmp_path, "w", encoding="utf-8") as f:
                json.dump(serializable, f, ensure_ascii=False, indent=2)
            os.replace(tmp_path, CLASSIFICATION_CACHE_FILE)  # atomic on same fs
        except (IOError, OSError) as e:
            print(f"[classifier] Failed to save classification cache: {e}")
            if os.path.exists(tmp_path):
                try:
                    os.remove(tmp_path)
                except OSError:
                    pass

    def get_cached(self, bvid: str) -> ClassificationResult | None:
        """Return cached classification for a video, or None."""
        return self._classification_cache.get(bvid)

    # ---- Classification pipeline ----

    async def classify(
        self,
        bvid: str,
        title: str,
        text: str,
        duration_seconds: int = 0,
        author: str = "",
        *,
        llm_api_key: str = "",
        llm_api_url: str = "",
        llm_model: str = "",
        force_refresh: bool = False,
    ) -> ClassificationResult:
        """
        Full 5-dimension classification pipeline.

        Steps:
          1. Check cache (unless force_refresh)
          2. Rule engine pre-classification
          3. LLM fine-grained classification (if API key available)
          4. Tag generation (LLM + keyword + rule merge)
          5. Cross-skill hint generation
        """
        # Step 1: Cache hit
        if not force_refresh:
            cached = self.get_cached(bvid)
            if cached:
                return cached

        # Step 2: Rule engine
        rule_type, type_conf = RuleClassifier.classify_type(title)
        rule_diff, diff_conf = RuleClassifier.classify_difficulty(title)
        rule_lang, lang_conf = RuleClassifier.detect_language(text)
        rule_duration = RuleClassifier.categorize_duration(duration_seconds)

        rule_hints = {
            "suggested_type": rule_type.value,
            "type_confidence": round(type_conf, 2),
            "suggested_difficulty": rule_diff.value,
            "difficulty_confidence": round(diff_conf, 2),
            "suggested_language": rule_lang.value,
            "language_confidence": round(lang_conf, 2),
            "duration_category": rule_duration.value,
            "duration_seconds": duration_seconds,
        }

        # Step 3: LLM classification
        if llm_api_key:
            llm_result = await self._call_llm_classify(
                title, text, rule_hints,
                llm_api_key, llm_api_url, llm_model
            )
        else:
            logger.warning("No LLM API key configured — falling back to keyword extraction only. "
                           "Tags will be low quality. Set api_key in settings to enable LLM-generated tags.")
            llm_result = {}

        # Step 4: Tag generation
        rule_tags = self._generate_rule_tags(title, text, author)
        keyword_tags = TagGenerator.extract_keywords_from_text(text)
        llm_tags_raw = llm_result.get("tags", [])

        merged_tags = TagGenerator.merge_tags(llm_tags_raw, keyword_tags, rule_tags)

        # Step 5: Cross-skill hints
        cross_hints = llm_result.get("cross_skill_hints", {})
        if not cross_hints:
            cross_hints = self._generate_cross_hints(
                llm_result.get("video_type", rule_type.value),
                merged_tags, title
            )

        # Assemble result
        result = ClassificationResult(
            bvid=bvid,
            title=title,
            video_type=llm_result.get("video_type", rule_type.value),
            video_type_confidence=llm_result.get("video_type_confidence", type_conf),
            topic=llm_result.get("topic", ""),
            subtopics=llm_result.get("subtopics", []),
            difficulty=llm_result.get("difficulty", rule_diff.value),
            difficulty_confidence=llm_result.get("difficulty_confidence", diff_conf),
            duration_category=rule_duration.value,
            duration_seconds=duration_seconds,
            language=llm_result.get("language", rule_lang.value),
            quality_tier=llm_result.get("quality_tier", QualityTier.B.value),
            tags=merged_tags,
            keywords=llm_result.get("keywords", keyword_tags[:5]),
            reason=llm_result.get("reason", f"规则分类: {rule_type.value}"),
            classified_at=datetime.now().isoformat(),
            cross_skill_hints=cross_hints,
        )

        # Cache
        self._classification_cache[bvid] = result
        self._save_cache()
        return result

    async def _call_llm_classify(
        self, title: str, text: str, rule_hints: dict,
        api_key: str, api_url: str, model: str,
    ) -> dict:
        """Call LLM API for classification. Supports Anthropic and OpenAI-compatible."""
        import httpx

        prompt = LLMClassifier.build_prompt(title, text, rule_hints)
        system_msg = "你是一个视频内容分类专家，只输出JSON。不要包含任何额外文字。"

        try:
            is_anthropic = "anthropic.com" in api_url.lower()
            headers = {"Content-Type": "application/json"}

            if is_anthropic:
                headers.update({
                    "x-api-key": api_key,
                    "anthropic-version": "2023-06-01",
                })
                req_body = {
                    "model": model or "claude-sonnet-4-20250514",
                    "max_tokens": 600,
                    "system": system_msg,
                    "messages": [{"role": "user", "content": prompt}],
                }
            else:
                headers["Authorization"] = f"Bearer {api_key}"
                req_body = {
                    "model": model or "deepseek-chat",
                    "max_tokens": 600,
                    "temperature": 0.1,
                    "messages": [
                        {"role": "system", "content": system_msg},
                        {"role": "user", "content": prompt},
                    ],
                }

            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(api_url, headers=headers, json=req_body)
                if r.status_code != 200:
                    error_detail = ""
                    try:
                        error_detail = r.text[:200]
                    except Exception as e:
                        logger.warning("Failed to read error response body: %s", e)
                    print(f"[classifier] LLM API returned {r.status_code}: {error_detail}")
                    return {}
                data = r.json()

            # Extract response text
            if is_anthropic:
                content = data.get("content", [])
                text_blocks = [
                    b.get("text", "") for b in content if b.get("type") == "text"
                ]
                raw = "".join(text_blocks)
            else:
                raw = data.get("choices", [{}])[0].get("message", {}).get("content", "")

            # Clean response: strip markdown code fences
            raw = raw.strip()
            for prefix in ("```json", "```"):
                if raw.startswith(prefix):
                    raw = raw[len(prefix):].strip()
            if raw.endswith("```"):
                raw = raw[:-3].strip()

            return json.loads(raw)

        except Exception:
            return {}

    def _generate_rule_tags(
        self, title: str, text: str, author: str
    ) -> list[str]:
        """Generate tags from rule-based patterns."""
        tags = []

        # v8.2: Author name is NOT a content tag. Removed to prevent names like
        # "他们都叫我蜗牛学长" appearing in tag clouds.
        # Author is already stored separately in kb_entries.author.

        # Platform-specific content signals
        signals = [
            (r"字幕|字幕组|翻译", "双语字幕"),
            (r"AI生成|AI总结|大模型|LLM|GPT|Claude", "AI"),
            (r"开源|GitHub|github", "开源"),
            (r"年终|年度|202[0-9]", "年度总结"),
            (r"入门|教程|指南|攻略", "入门指南"),
        ]
        for pattern, tag in signals:
            if re.search(pattern, title + text[:500]):
                tags.append(tag)

        return tags

    def _generate_cross_hints(
        self, video_type: str, tags: list[str], title: str
    ) -> dict:
        """Generate cross-skill metadata for notebooklm, multi-search-engine, bili-note."""
        return {
            "notebooklm_group": f"B站-{video_type}" if video_type else "B站-未分类",
            "search_engine_queries": [
                f"{title[:50]} 深入分析",
                f"{' '.join(tags[:3])} 教程",
                f"{video_type} 最佳推荐",
            ],
            "bili_note_tags": tags[:5],
        }

    # ---- Persistence to KB entry JSON ----

    def persist_to_entry(self, bvid: str) -> bool:
        """
        Write classification data to the KB entry JSON file.
        Mutates the on-disk JSON to include classification fields.
        """
        from database import kb_filepath
        filepath = kb_filepath(bvid)
        if not os.path.exists(filepath):
            return False

        result = self._classification_cache.get(bvid)
        if not result:
            return False

        try:
            with open(filepath, "r", encoding="utf-8") as f:
                entry = json.load(f)

            # Inject classification fields
            entry["classification"] = result.to_dict()
            entry["video_type"] = result.video_type
            entry["tags"] = result.tags
            entry["difficulty"] = result.difficulty
            entry["language"] = result.language
            entry["duration_category"] = result.duration_category
            entry["topic"] = result.topic
            entry["quality_tier"] = result.quality_tier
            entry["schema_version"] = 2  # Mark schema upgrade

            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(entry, f, ensure_ascii=False, indent=2)

            return True
        except Exception:
            return False

    # ---- Batch classification ----

    async def classify_batch(
        self,
        entries: list[dict],
        *,
        llm_api_key: str = "",
        llm_api_url: str = "",
        llm_model: str = "",
        max_concurrent: int = 3,
        progress_callback=None,
    ) -> list[ClassificationResult]:
        """
        Classify multiple videos with concurrency control and progress reporting.
        """
        import asyncio

        semaphore = asyncio.Semaphore(max_concurrent)
        results = []
        total = len(entries)

        async def classify_one(idx: int, entry: dict):
            async with semaphore:
                result = await self.classify(
                    bvid=entry.get("bvid", ""),
                    title=entry.get("title", ""),
                    text=entry.get("text", ""),
                    duration_seconds=entry.get("duration", 0),
                    author=entry.get("author", ""),
                    llm_api_key=llm_api_key,
                    llm_api_url=llm_api_url,
                    llm_model=llm_model,
                )
                if progress_callback:
                    progress_callback(idx + 1, total, result)
                return result

        tasks = [
            classify_one(i, entry) for i, entry in enumerate(entries)
        ]
        results = await asyncio.gather(*tasks, return_exceptions=True)

        # Filter out exceptions, keep successes
        successful = []
        for r in results:
            if isinstance(r, ClassificationResult):
                self.persist_to_entry(r.bvid)
                successful.append(r)

        return successful

    # ---- Statistics & Aggregation ----

    def get_category_stats(self) -> dict:
        """
        Compute category distribution across all classified entries.
        Returns data suitable for frontend charts.
        """
        type_counts: dict[str, int] = {}
        difficulty_counts: dict[str, int] = {}
        quality_counts: dict[str, int] = {}
        language_counts: dict[str, int] = {}
        duration_counts: dict[str, int] = {}
        all_tags: dict[str, int] = {}
        total = 0

        for result in self._classification_cache.values():
            total += 1
            vt = result.video_type
            type_counts[vt] = type_counts.get(vt, 0) + 1
            difficulty_counts[result.difficulty] = difficulty_counts.get(result.difficulty, 0) + 1
            quality_counts[result.quality_tier] = quality_counts.get(result.quality_tier, 0) + 1
            language_counts[result.language] = language_counts.get(result.language, 0) + 1
            duration_counts[result.duration_category] = duration_counts.get(result.duration_category, 0) + 1
            for tag in result.tags:
                all_tags[tag] = all_tags.get(tag, 0) + 1

        return {
            "total_classified": total,
            "by_type": dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)),
            "by_difficulty": difficulty_counts,
            "by_quality": quality_counts,
            "by_language": language_counts,
            "by_duration": duration_counts,
            "top_tags": dict(sorted(all_tags.items(), key=lambda x: x[1], reverse=True)[:30]),
        }

    def get_classification(self, bvid: str) -> ClassificationResult | None:
        """Get classification for a single video."""
        return self._classification_cache.get(bvid)

    def invalidate(self, bvid: str):
        """Remove classification from cache (e.g. when entry is deleted)."""
        self._classification_cache.pop(bvid, None)
        self._save_cache()


# ---------------------------------------------------------------------------
# Singleton accessor (shared across routes)
# ---------------------------------------------------------------------------

_classifier_instance: VideoClassifier | None = None


def get_classifier() -> VideoClassifier:
    """Get or create the singleton VideoClassifier instance."""
    global _classifier_instance
    if _classifier_instance is None:
        _classifier_instance = VideoClassifier()
    return _classifier_instance
