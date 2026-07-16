"""
章节服务 v1.0 — B站官方章节 (view_points) 集成

三级章节来源回退链 (resolve_chapters):
  1. official — B站官方章节标记 (player API view_points, UP主手动划分)
  2. gap      — 字幕时间间隙检测 (间隙 >= CHAPTER_GAP_SECONDS 视为章节边界)
  3. slice    — 长视频等分切片 (仅 duration >= LONG_VIDEO_SECONDS 时启用)
  4. []       — 短视频且无官方章节: 空列表, 总结 prompt 保持原状

Chapter dict 规范:
  {"title": str, "from": int, "to": int, "source": "official"|"gap"|"slice"}

下游消费者:
  - summarizer.build_prompt      — 注入 <chapters> 块 + 结构指令 (章节结构 / 长视频自由结构)
  - summarizer.summarize_segments — 按章节边界分段替代等分 5 段
  - routers/kb.py /api/v2/chapters — 前端章节导航
  - docx_exporter.generate_docx  — 章节分组字幕表 (已支持 [{from,to,title}])
"""
import logging
from typing import List, Optional

from constants import (
    CHAPTER_GAP_SECONDS,
    LONG_VIDEO_SECONDS,
    CHAPTER_SLICE_SECONDS,
    MAX_CHAPTERS,
)

_logger = logging.getLogger(__name__)


# =============================================================================
# 工具
# =============================================================================

def format_ts(sec: float) -> str:
    """秒 → mm:ss / h:mm:ss 时间戳文本。"""
    sec = max(0, int(sec or 0))
    h, rem = divmod(sec, 3600)
    m, s = divmod(rem, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m:02d}:{s:02d}"


def _clip_title(text: str, limit: int = 40) -> str:
    text = (text or "").strip().replace("\n", " ")
    return text[:limit] if text else ""


# =============================================================================
# 兜底章节生成 (无官方 view_points 时)
# =============================================================================

def detect_gap_chapters(
    subtitle_body: list,
    duration: int = 0,
    gap_seconds: int = CHAPTER_GAP_SECONDS,
) -> List[dict]:
    """字幕间隙检测: 相邻字幕间隔 >= gap_seconds 视为章节边界。

    subtitle_body: SubtitleEntry 列表 (需有 .from_/.to/.content)。
    产出 < 2 个章节时视为检测失败, 返回 [] (单章节无结构意义)。
    """
    if not subtitle_body or len(subtitle_body) < 10:
        return []

    chapters: List[dict] = []
    seg_start = float(subtitle_body[0].from_)
    seg_title = _clip_title(subtitle_body[0].content, 24)
    prev_to = float(subtitle_body[0].to)

    for entry in subtitle_body[1:]:
        e_from = float(entry.from_)
        if e_from - prev_to >= gap_seconds:
            chapters.append({
                "title": seg_title or f"章节 {len(chapters) + 1}",
                "from": int(seg_start),
                "to": int(prev_to),
                "source": "gap",
            })
            seg_start = e_from
            seg_title = _clip_title(entry.content, 24)
        prev_to = max(prev_to, float(entry.to))

    chapters.append({
        "title": seg_title or f"章节 {len(chapters) + 1}",
        "from": int(seg_start),
        "to": int(prev_to),
        "source": "gap",
    })

    if len(chapters) < 2:
        return []
    return chapters[:MAX_CHAPTERS]


def slice_chapters(
    duration: int,
    slice_seconds: int = CHAPTER_SLICE_SECONDS,
) -> List[dict]:
    """长视频等分切片: 每 slice_seconds 一个章节 (最终兜底)。"""
    duration = int(duration or 0)
    if duration < LONG_VIDEO_SECONDS or slice_seconds <= 0:
        return []
    chapters = []
    start = 0
    idx = 1
    while start < duration and len(chapters) < MAX_CHAPTERS:
        end = min(start + slice_seconds, duration)
        # 末段不足半个切片时并入上一段
        if duration - end < slice_seconds // 2:
            end = duration
        chapters.append({
            "title": f"第{idx}段 [{format_ts(start)}-{format_ts(end)}]",
            "from": start,
            "to": end,
            "source": "slice",
        })
        if end >= duration:
            break
        start = end
        idx += 1
    return chapters if len(chapters) >= 2 else []


# =============================================================================
# 章节解析主入口
# =============================================================================

async def resolve_chapters(
    bvid: str,
    cid: Optional[int] = None,
    duration: int = 0,
    subtitle_body: Optional[list] = None,
) -> dict:
    """章节解析回退链: official → gap → slice → 无。

    Returns: {"source": "official"|"gap"|"slice"|"none", "chapters": [...]}
    永不抛错 —— 章节是可选增强。
    """
    # ---- 1. 官方 view_points ----
    try:
        from bilibili_client import get_view_points
        official = await get_view_points(bvid, cid=cid)
        if official:
            return {"source": "official", "chapters": official}
    except Exception:
        _logger.debug("[%s] resolve_chapters: official failed", bvid, exc_info=True)

    # ---- 2. 字幕间隙检测 (仅长视频才有结构价值) ----
    if subtitle_body and int(duration or 0) >= LONG_VIDEO_SECONDS:
        try:
            gap = detect_gap_chapters(subtitle_body, duration)
            if gap:
                return {"source": "gap", "chapters": gap}
        except Exception:
            _logger.debug("[%s] resolve_chapters: gap detection failed", bvid, exc_info=True)

    # ---- 3. 长视频等分切片 ----
    sliced = slice_chapters(duration)
    if sliced:
        return {"source": "slice", "chapters": sliced}

    return {"source": "none", "chapters": []}


# =============================================================================
# 字幕按章节分组 (section generation)
# =============================================================================

def group_subtitle_by_chapters(
    subtitle_body: list,
    chapters: List[dict],
    max_chars_per_chapter: int = 2500,
) -> List[dict]:
    """按章节边界把字幕条目分组为 section。

    边界规则与 docx_exporter 一致: 章节有效终点 = 下一章节的 from (若存在),
    否则本章节的 to; 末章节吸收其后所有字幕。章节前的字幕归入 "开场" 段。

    Returns: [{"title", "from", "to", "time", "text", "source"}], 空章节被跳过。
    """
    if not chapters:
        return []
    body = sorted(subtitle_body or [], key=lambda x: float(x.from_))
    norm = sorted(
        [c for c in chapters if isinstance(c, dict)],
        key=lambda c: float(c.get("from", 0) or 0),
    )
    sections: List[dict] = []

    # 章节前导内容 (官方章节可能不从 0 开始)
    first_from = float(norm[0].get("from", 0) or 0)
    if first_from > 30 and body:
        intro = [e for e in body if float(e.from_) < first_from]
        if intro:
            text = " ".join(e.content for e in intro if e.content)
            if text.strip():
                sections.append({
                    "title": "开场",
                    "from": int(float(intro[0].from_)),
                    "to": int(first_from),
                    "time": f"{format_ts(intro[0].from_)} ~ {format_ts(first_from)}",
                    "text": text[:max_chars_per_chapter],
                    "source": norm[0].get("source", "official"),
                })

    for idx, ch in enumerate(norm):
        ch_from = float(ch.get("from", 0) or 0)
        next_ch = norm[idx + 1] if idx + 1 < len(norm) else None
        if next_ch is not None:
            ch_end = float(next_ch.get("from", 0) or 0)
        else:
            ch_end = float("inf")  # 末章节吸收其后所有字幕
        entries = [e for e in body if ch_from <= float(e.from_) < ch_end]
        text = " ".join(e.content for e in entries if e.content).strip()
        if not text:
            continue
        eff_to = int(float(entries[-1].to)) if entries else int(ch.get("to", ch_from) or ch_from)
        sections.append({
            "title": ch.get("title", f"章节 {idx + 1}"),
            "from": int(ch_from),
            "to": eff_to,
            "time": f"{format_ts(ch_from)} ~ {format_ts(eff_to)}",
            "text": text[:max_chars_per_chapter],
            "source": ch.get("source", "official"),
        })
    return sections


# =============================================================================
# Prompt 注入 (由 summarizer.build_prompt 消费)
# =============================================================================

def build_chapter_block(chapters: List[dict], sanitize=None) -> str:
    """把章节列表渲染为 <chapters> XML 块 (注入 video_info)。

    sanitize: 可选回调 (summarizer._sanitize_llm_field) —— 章节标题是
    UP主可控内容, 必须经过注入防御清洗。
    """
    if not chapters:
        return ""
    if sanitize is None:
        sanitize = lambda v, _n="chapter": v  # noqa: E731 — 调用方未提供时原样返回
    lines = []
    for i, ch in enumerate(chapters, 1):
        title = sanitize(str(ch.get("title", "") or ""), "chapter_title")
        lines.append(
            f"{i}. [{format_ts(ch.get('from', 0))}-{format_ts(ch.get('to', 0))}] {title}"
        )
    src = chapters[0].get("source", "official")
    src_doc = {
        "official": "UP主官方划分",
        "gap": "字幕间隙推断",
        "slice": "等长切片",
    }.get(src, src)
    return (
        f'<chapters source="{src}" note="{src_doc}">\n'
        + "\n".join(lines)
        + "\n</chapters>"
    )


def structure_instructions(
    chapters: List[dict],
    duration: int = 0,
    source: str = "none",
) -> str:
    """生成结构指令 (置于 trust_boundary 之前, 属于可信系统指令)。

    - 官方章节        → 严格按章节结构逐章总结
    - 长视频无官方章节 → 自由结构: 由内容决定小节划分, 不套固定模板
    - 短视频无章节    → 空串 (prompt 保持原状)
    """
    duration = int(duration or 0)
    is_long = duration >= LONG_VIDEO_SECONDS

    if chapters and source == "official":
        return (
            "【章节结构要求】本视频包含UP主官方划分的章节（见下方 <chapters>）。\n"
            "请按官方章节结构组织总结正文：\n"
            "- 每个章节输出一个小节，标题格式：`### [起始时间] 章节标题`\n"
            "- 小节内概括该章节的核心内容、关键论点与结论（2-5句或分点）\n"
            "- 内容极少的章节可与相邻章节合并说明，但保留时间戳\n"
            "- 全文开头先给一段整体概述，结尾给一段全片要点收束"
        )

    if is_long:
        mins = duration // 60
        hint = ""
        if chapters:
            hint = (
                "\n下方 <chapters> 是根据时间轴自动推断的参考分段（非官方章节），"
                "仅供定位时间范围，不必逐段照搬。"
            )
        return (
            f"【长视频自由结构要求】本视频较长（约{mins}分钟），"
            "不要套用固定条数的总结模板。\n"
            "- 请根据内容的自然脉络自由划分 3-8 个主题小节\n"
            "- 每个小节标题格式：`### [大致起始时间] 小节主题`\n"
            "- 小节数量、详略与顺序完全由内容决定：信息密集处展开，过渡与闲聊压缩\n"
            "- 开头给整体概述，结尾给全片要点收束" + hint
        )

    return ""
