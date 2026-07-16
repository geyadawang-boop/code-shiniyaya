"""
=============================================================================
BiliSum 魔法数字常量提取 — constants.py
=============================================================================
所有魔法数字集中管理，单一事实来源 (Single Source of Truth)。
跨模块引用：from constants import *

使用规则：
  - 禁止在任何 .py 文件中硬编码数字字面量（0 和 1 除外）
  - 所有超时、大小、限制、阈值必须引用此模块
  - 每季度审计：抓取所有数字字面量与 constants.py 交叉比对

生成日期：2026-07-09
=============================================================================
"""

# =============================================================================
# 1. HTTP 超时 (秒)
# =============================================================================
HTTP_TIMEOUT_FAST = 10          # 快速查询：弹幕、检测
HTTP_TIMEOUT_DEFAULT = 15       # 默认：B站 API、收藏夹
HTTP_TIMEOUT_EXTENDED = 30      # 扩展：多页评论
HTTP_TIMEOUT_LONG = 60          # 长请求：RAG 非流式
HTTP_TIMEOUT_STREAM = 120       # 流式：AI 总结、RAG 聊天
HTTP_TIMEOUT_DOWNLOAD = 300     # 下载：Whisper、yt-dlp
HTTP_TIMEOUT_QR_POLL = 15       # 二维码轮询
HTTP_TIMEOUT_FRONTEND_FETCH = 30000   # 前端 fetch 超时 (ms)

# =============================================================================
# 2. AI/LLM 参数
# =============================================================================
LLM_MAX_TOKENS_MIN = 256             # 最小 max_tokens
LLM_MAX_TOKENS_SMALL = 2048          # 简短内容
LLM_MAX_TOKENS_MEDIUM = 4096         # 中等内容 / 分段
LLM_MAX_TOKENS_LARGE = 6144          # 较长内容
LLM_MAX_TOKENS_XL = 8192             # 丰富内容
LLM_MAX_TOKENS_DEEP = 32000          # 深度总结上限
LLM_CONTEXT_LIMIT = 200000           # Claude 上下文窗口
LLM_TOKEN_ESTIMATE_CHARS_PER_TOKEN = 3  # 粗略估算：每 token ~3 字符

# 模型默认值
DEFAULT_MODEL = "deepseek-chat"
DEFAULT_DEEPSEEK_MODEL = "deepseek-chat"
DEFAULT_API_URL = "https://api.anthropic.com/v1/messages"
DEFAULT_DEEPSEEK_URL = "https://api.deepseek.com/v1/chat/completions"

# =============================================================================
# 3. 文本处理
# =============================================================================
TEXT_CHUNK_SIZE = 1000           # 默认分块大小 (字符)
TEXT_CHUNK_OVERLAP = 200         # 分块重叠 (字符)
TEXT_CHUNK_MIN_LENGTH = 10       # 最小有效分块长度
TEXT_CHUNK_SEPARATORS = ("\n\n", "\n", "。", "！", "？", ".", "!", "?", " ")

TEXT_TRUNCATE_HIGH = 10000       # 高优先级截断长度
TEXT_TRUNCATE_RICH = 30000       # 丰富内容截断长度
TEXT_TRUNCATE_MEDIUM = 20000     # 中等内容截断
TEXT_TRUNCATE_LIGHT = 15000      # 轻度截断
TEXT_TRUNCATE_SHORT = 5000       # 短内容截断 (OCR 等)

TEXT_QA_LIMIT = 8000             # QA 上下文长度
TEXT_COMMENT_LIMIT = 12000       # 评论分析长度
TEXT_MIN_VALID = 20              # 最小有效文本长度

TEXT_SENTENCE_MAX_LEN = 18       # 中文分句最大长度
TEXT_MERGE_MAX_LEN = 20          # 合并后最大长度
TEXT_MERGE_MIN_LEN = 16          # 合并最小长度

# =============================================================================
# 4. 内容分析阈值
# =============================================================================
# Richness 评分阈值
RICHNESS_THRESHOLD_VERY_LOW = 500     # 文本量 < 500 评分低
RICHNESS_THRESHOLD_LOW = 2000
RICHNESS_THRESHOLD_MEDIUM = 5000
RICHNESS_THRESHOLD_HIGH = 10000
RICHNESS_THRESHOLD_EXTREME = 15000

COMMENT_THRESHOLD_LOW = 5
COMMENT_THRESHOLD_MEDIUM = 20
TECH_TERM_THRESHOLD_LOW = 3
TECH_TERM_THRESHOLD_MEDIUM = 10
TECH_TERM_THRESHOLD_HIGH = 20

# 摘要目标长度 (单词数)
SUMMARY_TARGET_SHORT = "300-500 words"       # <= 3min
SUMMARY_TARGET_MEDIUM = "600-900 words"       # <= 10min
SUMMARY_TARGET_LONG = "900-1500 words"        # <= 30min
SUMMARY_TARGET_VERY_LONG = "2500-4000 words"  # > 30min

# =============================================================================
# 5. 数据分页和限制
# =============================================================================
COMMENTS_MAX_PAGES = 10          # 全量评论最大页数
COMMENTS_PER_PAGE = 40           # 每页评论数
COMMENTS_HOT_COUNT = 30          # 热门评论抓取数
COMMENTS_SUB_REPLY_LIMIT = 5     # 子回复截取数
COMMENTS_HOT_SUB_REPLY = 3       # 热门评论子回复数
COMMENTS_AI_MAX = 400            # AI 评论分析数量上限

DANMAKU_MAX = 50                 # 弹幕最大获取量
DANMAKU_MIN_LEN = 2              # 弹幕最小有效长度

FAVORITES_MAX_PAGES = 50         # 收藏夹最大页数
FAVORITES_PER_PAGE = 20          # 收藏夹每页
FAVORITES_SYNC_PAGES = 10        # 同步时最大页数

SEARCH_KB_MAX = 8                # 知识库搜索最大返回数
SEARCH_KB_IDS = 5                # 知识库搜索 (ID-based)

RAG_RRF_RANK_CONSTANT = 60       # RRF 排名常数
RAG_RRF_VEC_WEIGHT = 1.0         # 向量通道权重
RAG_RRF_KW_WEIGHT = 0.9          # 关键词通道权重
RAG_RRF_PER_VIDEO_LIMIT = 2      # 每个视频最大片段数
RAG_RRF_TOP_K = 8                # RRF 最终返回数
RAG_MMR_LAMBDA = 0.55            # MMR 多样性参数
RAG_MMR_FETCH_K_MULTIPLIER = 4   # MMR 预取倍数

# =============================================================================
# 6. Quality Budget 系数
# =============================================================================
QUALITY_MULTIPLIER_MIN = 0.85
QUALITY_MULTIPLIER_MAX = 1.4
QUALITY_SCALE = 0.55

NOTE_BUDGET_MIN = 1200
NOTE_BUDGET_MAX = 45000
NOTE_BUDGET_ABS_MAX = 65000
NOTE_BUDGET_DEEP_MAX = 110000
NOTE_BUDGET_QUICK_MIN = 800
NOTE_BUDGET_QUICK_MAX = 12000

# 时长阈值 (分钟)
DURATION_SHORT = 3
DURATION_MEDIUM = 10
DURATION_LONG = 30
DURATION_VERY_LONG = 60
DURATION_EXTENDED = 120

# 视觉依赖检测
VISUAL_DENSITY_LOW = 120        # 低字幕密度 (chars/min)
VISUAL_DENSITY_MEDIUM = 180     # 中等密度
VISUAL_SPARSE_MIN_CHARS = 800   # 稀疏字幕字符数
VISUAL_MIN_DURATION = 10        # 无字幕视频最小检测时长
VISUAL_LONG_MIN = 25            # 长视频稀疏检测起点

# 加权系数
ENGAGEMENT_WEIGHTS = {
    "like": 1.0,
    "favorite": 1.4,
    "coin": 2.2,
    "reply": 1.8,
    "danmaku": 0.8,
    "share": 1.5,
}

# Note Budget 系数
BUDGET_COEFF_DURATION = 35           # 每分钟
BUDGET_COEFF_SUBTITLE = 0.025        # 每字幕字符
BUDGET_COEFF_EVIDENCE = 8            # 每证据块
BUDGET_COEFF_COMMENT = 3             # 每评论
BUDGET_COEFF_ARTICLE_DURATION = 25   # 文章每分钟
BUDGET_COEFF_ARTICLE_CHAR = 0.06     # 文章每字符
BUDGET_COMPRESSION_RATIO = 1.45      # target_max = target_min * ratio
BUDGET_QUICK_RATIO = 0.45            # quick_target = target_min * ratio
BUDGET_DEEP_RATIO = 1.6              # deep_target = target_max * ratio

# =============================================================================
# 7. 对话框/通知
# =============================================================================
TOAST_DURATION_MS = 3500        # Toast 显示时长
TOAST_ANIMATION_MS = 300        # Toast 动画时长
QR_POLL_INTERVAL_MS = 2000      # 二维码轮询间隔
QR_POLL_MAX_ATTEMPTS = 90       # 最大轮询次数
MODAL_ANIMATION_MS = 250        # 弹窗动画时长

# =============================================================================
# 8. 杂项
# =============================================================================
WHALE_LEAP_MS = 1200            # 鲸鱼跳跃动画时长
WHALE_RETURN_MS = 100           # 鲸鱼归位动画
WHALE_EXHALE_MS = 2400          # 喷水动画
WHALE_EXHALE_INTERVAL = 2000    # 喷水间隔
SPLASH_DROPLET_COUNT = 12       # 水花粒子数
SPLASH_DURATION_MS = 1000       # 水花持续时间

MAX_HEADER_LINES = 8            # Obsidian header 截取
CHAPTER_GAP_SECONDS = 20        # 章节检测间隔阈值 (字幕间隙兜底)
LONG_VIDEO_SECONDS = 1200       # 长视频阈值 (20分钟): 启用章节结构 / 自由结构总结
CHAPTER_SLICE_SECONDS = 480     # 无章节长视频等分切片长度 (8分钟)
MAX_CHAPTERS = 40               # 章节数量上限 (防止 prompt 膨胀)
MIN_CHAPTER_SECONDS = 5         # 官方章节最短时长 (过滤异常标记)
ASYNC_DELAY_SMALL = 0.1         # 小延迟 (秒)
ASYNC_DELAY_MEDIUM = 0.3        # 中延迟 (秒)

# =============================================================================
# 9. 文件路径
# =============================================================================
import os as _os
COOKIE_FILE = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "bili_cookies.txt")
FRONTEND_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "frontend")
# Keyframe/visual-context video cache: data/frames_cache/{bvid}/ (peer of data/asr_cache).
# Written by routers/ai.py shared download; removed per-bvid by database.delete_kb_entry.
FRAMES_CACHE_DIR = _os.path.join(_os.path.dirname(_os.path.dirname(_os.path.abspath(__file__))), "data", "frames_cache")
