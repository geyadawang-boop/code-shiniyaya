# -*- coding: utf-8 -*-
"""subtitle_cleaner.py

Subtitle text cleaner (ported wdkns rules).

Three rule families, applied in order by :func:`clean_subtitle_text`:

1. normalize  - strip markup/annotation cues, full-width -> half-width
                alphanumerics, unify ellipsis, tidy whitespace.
2. filler     - remove spoken filler words / interjections (Chinese and
                English) and clause-leading discourse fillers.
3. stutter    - collapse immediate repetitions produced by ASR or by the
                speaker ("我我我觉得" -> "我觉得", "the the" -> "the").

Public API:
    clean_subtitle_text(text: str) -> str

Stdlib only. Safe on empty / non-string input (returns "").
"""

from __future__ import annotations

import re

__all__ = ["clean_subtitle_text"]

# ---------------------------------------------------------------------------
# Rule data
# ---------------------------------------------------------------------------

# Interjection characters that are (almost) always filler when they appear
# standalone at a clause boundary.  Deliberately excludes ambiguous chars
# such as "额" (金额) and "啊" (sentence-final particle) unless repeated.
_CN_FILLER_CHARS = "嗯呃诶欸唉哎呣"

# Ambiguous fillers: removed only when repeated (e.g. "额额", "啊啊啊").
_CN_FILLER_AMBIGUOUS = "额啊哦噢喔嗯"

# Clause-leading discourse fillers, removed only when directly followed by a
# pause mark (comma / enumeration comma), which is the filler usage pattern.
# Longest first so alternation prefers the longer match.
_CN_LEADING_FILLERS = (
    "也就是说",
    "反正就是",
    "就是说",
    "所以说",
    "然后呢",
    "那么",
    "那个",
    "这个",
    "就是",
    "然后",
)

# English filler tokens (word-boundary matched, case-insensitive).
_EN_FILLER_RE = re.compile(
    r"\b(?:u+m+|u+h+|uhm+|er+m*|hm+|mhm+|ah+|eh+)\b[,.]?\s*",
    re.IGNORECASE,
)

# ", you know," style parentheticals -> collapse to a single comma.
_EN_PARENTHETICAL_RE = re.compile(
    r"([,，])\s*(?:you know|i mean|sort of|kind of)\s*[,，]\s*",
    re.IGNORECASE,
)

# Annotation cues commonly embedded in subtitles.
_CUE_KEYWORDS = (
    "音乐|掌声|笑声|笑|鼓掌|欢呼|叹气|咳嗽|静音|听不清|"
    "music|applause|laughter|laughs|cheering|sigh|coughs|inaudible|silence"
)

_HTML_TAG_RE = re.compile(r"</?[a-zA-Z][^<>]*>")           # <i>, <font ...>
_ASS_TAG_RE = re.compile(r"\{\\[^{}]*\}")                  # {\an8}{\i1}
_FW_BRACKET_CUE_RE = re.compile(r"【[^【】]{0,20}】")        # 【音乐】【广告】
_BRACKET_CUE_RE = re.compile(
    r"[\[\(（]\s*(?:%s)\s*[\]\)）]" % _CUE_KEYWORDS, re.IGNORECASE
)

# Punctuation classes.
_PAUSE = "，、,"                                   # pause marks
_STOP = "。！？；：.!?;:"                           # clause / sentence stops
_BOUNDARY = _PAUSE + _STOP + "…～~　 \t"

_CJK = "一-鿿"


# ---------------------------------------------------------------------------
# Stage 1: normalize
# ---------------------------------------------------------------------------

def _to_halfwidth(text: str) -> str:
    """Convert full-width ASCII letters/digits and the ideographic space."""
    out = []
    for ch in text:
        code = ord(ch)
        if code == 0x3000:                       # ideographic space
            out.append(" ")
        elif (0xFF10 <= code <= 0xFF19 or
              0xFF21 <= code <= 0xFF3A or
              0xFF41 <= code <= 0xFF5A):         # ０-９ Ａ-Ｚ ａ-ｚ
            out.append(chr(code - 0xFEE0))
        else:
            out.append(ch)
    return "".join(out)


def _strip_markup(text: str) -> str:
    text = _HTML_TAG_RE.sub("", text)
    text = _ASS_TAG_RE.sub("", text)
    text = _FW_BRACKET_CUE_RE.sub("", text)
    text = _BRACKET_CUE_RE.sub("", text)
    return text


def _normalize(text: str) -> str:
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    text = _strip_markup(text)
    text = _to_halfwidth(text)
    # Unify ellipsis variants to the standard "……".
    text = re.sub(r"(?:\.{3,}|。{3,}|…+)", "……", text)
    # Collapse runs of horizontal whitespace.
    text = re.sub(r"[ \t]+", " ", text)
    return text


# ---------------------------------------------------------------------------
# Stage 2: filler removal
# ---------------------------------------------------------------------------

_CN_FILLER_RUN_RE = re.compile(
    r"(?:^|(?<=[%s\n]))\s*[%s]+\s*[%s]?"
    % (re.escape(_BOUNDARY), _CN_FILLER_CHARS, re.escape(_PAUSE))
)
_CN_FILLER_TAIL_RE = re.compile(
    r"[%s]+(?=[%s\n]|$)" % (_CN_FILLER_CHARS, re.escape(_BOUNDARY))
)
_CN_FILLER_REPEAT_RE = re.compile(
    r"([%s])\1+" % _CN_FILLER_AMBIGUOUS
)
_CN_LEADING_RE = re.compile(
    r"(?:^|(?<=[%s\n]))\s*(?:%s)[%s]\s*"
    % (
        re.escape(_STOP),
        "|".join(map(re.escape, _CN_LEADING_FILLERS)),
        re.escape(_PAUSE),
    )
)


def _remove_fillers(text: str) -> str:
    # Repeated ambiguous interjections ("啊啊啊", "额额") -> removed entirely.
    text = _CN_FILLER_REPEAT_RE.sub("", text)
    # Unambiguous interjection runs at clause start (with optional pause mark).
    text = _CN_FILLER_RUN_RE.sub("", text)
    # Interjection runs right before a clause boundary.
    text = _CN_FILLER_TAIL_RE.sub("", text)
    # Clause-leading discourse fillers ("那个，" "就是说，").
    text = _CN_LEADING_RE.sub("", text)
    # English fillers.
    text = _EN_PARENTHETICAL_RE.sub(r"\1 ", text)
    text = _EN_FILLER_RE.sub("", text)
    return text


# ---------------------------------------------------------------------------
# Stage 3: stutter / repetition collapse
# ---------------------------------------------------------------------------

_CN_CHAR_STUTTER_RE = re.compile(r"([%s])\1{2,}" % _CJK)         # 我我我 -> 我
_CN_CHAR_PAUSE_STUTTER_RE = re.compile(                          # 我、我、我 -> 我
    r"([%s])(?:[%s]\1)+" % (_CJK, re.escape(_PAUSE))
)
_CN_WORD_STUTTER_RE = re.compile(r"([%s]{2,4})\1+" % _CJK)       # 就是就是 -> 就是
_CN_WORD_PAUSE_STUTTER_RE = re.compile(                          # 然后，然后， -> 然后，
    r"([%s]{2,4}[%s])\1+" % (_CJK, re.escape(_PAUSE))
)
_CN_WORD_PAUSE_LEAD_RE = re.compile(                             # 然后，然后我们 -> 然后我们
    r"([%s]{2,4})[%s](?=\1)" % (_CJK, re.escape(_PAUSE))
)
_EN_WORD_STUTTER_RE = re.compile(r"\b(\w+)(?:\s+\1\b)+", re.IGNORECASE)
_EN_PARTIAL_STUTTER_RE = re.compile(r"\b(\w+)-\s*(?=\1\b)", re.IGNORECASE)


def _collapse_stutters(text: str) -> str:
    text = _CN_CHAR_PAUSE_STUTTER_RE.sub(r"\1", text)
    text = _CN_CHAR_STUTTER_RE.sub(r"\1", text)
    text = _CN_WORD_PAUSE_STUTTER_RE.sub(r"\1", text)
    text = _CN_WORD_PAUSE_LEAD_RE.sub("", text)
    text = _CN_WORD_STUTTER_RE.sub(r"\1", text)
    text = _EN_PARTIAL_STUTTER_RE.sub("", text)
    text = _EN_WORD_STUTTER_RE.sub(r"\1", text)
    return text


# ---------------------------------------------------------------------------
# Final tidy-up
# ---------------------------------------------------------------------------

_DUP_PUNCT_RE = re.compile(r"([%s])\1+" % re.escape(_PAUSE + "。！？；：!?;:"))
_SPACE_AROUND_CJK_PUNCT_RE = re.compile(r"\s*([，。！？、；：…])\s*")
_LEAD_PUNCT_RE = re.compile(
    r"(?:^|(?<=\n))[%s]+" % re.escape(_PAUSE + "。；：;:")
)
_PAUSE_BEFORE_STOP_RE = re.compile(r"[，、,](?=[。！？.!?])")


def _tidy(text: str) -> str:
    text = _DUP_PUNCT_RE.sub(r"\1", text)
    text = _SPACE_AROUND_CJK_PUNCT_RE.sub(r"\1", text)
    text = _LEAD_PUNCT_RE.sub("", text)
    text = _PAUSE_BEFORE_STOP_RE.sub("", text)   # "，。" -> "。"
    text = re.sub(r"[ \t]+", " ", text)
    text = re.sub(r" ?\n ?", "\n", text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def clean_subtitle_text(text: str) -> str:
    """Clean one piece of subtitle text using the ported wdkns rules.

    Applies, in order: normalization (markup / width / whitespace),
    filler-word removal (Chinese + English), stutter collapse, and a final
    punctuation / whitespace tidy-up.

    Args:
        text: Raw subtitle text (a line, a cue, or a whole transcript).

    Returns:
        The cleaned text.  Returns "" for empty or non-string input.
    """
    if not isinstance(text, str) or not text.strip():
        return ""
    text = _normalize(text)
    text = _remove_fillers(text)
    text = _collapse_stutters(text)
    text = _tidy(text)
    return text


if __name__ == "__main__":
    _samples = [
        "嗯，那个，我我我觉得这个方案挺好的",
        "就是说，我们要要要努力啊啊啊",
        "Um, I I think, you know, it's fine.",
        "【音乐】大家好{\\an8}<i>欢迎回来</i>。。。",
        "然后，然后，然后我们就开始了",
        "Ｈｅｌｌｏ　ｗｏｒｌｄ１２３",
        "这个项目的金额很大，额度也够",
    ]
    for _s in _samples:
        print(repr(_s), "->", repr(clean_subtitle_text(_s)))
