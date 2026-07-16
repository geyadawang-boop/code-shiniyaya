# -*- coding: utf-8 -*-
"""content_filter.py -- 平台噪音过滤: 剔除弹幕/评论中的求三连/关注/投币/充电等互动噪音."""
import re

NOISE_PATTERNS = [re.compile(p) for p in (
    r"一键三连|[求已]三连|三连[了走]|素质三连",              # 三连 variants
    r"[求已互回]关注?\b|关注(一下|走一波|up|UP)|涨粉|互粉",   # 关注/互粉 variants
    r"投币|[求已]币|硬币砸|币有了",                          # 投币 variants
    r"[求已]?点[个波]?赞|点赞|赞(起来|走一波)",              # 点赞 variants
    r"[求已先]收藏|收藏[了夹]|收藏从未|收藏吃灰",            # 收藏 variants
    r"转发|分享给",                                         # 转发 variants
    r"[求已]?充电|充个电|电池砸",                           # 充电 variants
    r"(?:https?://|www\.)\S+",                              # 引流链接
    r"^[\s\W_]*$",                                          # 纯符号/空白
    r"^(?:\[[^\[\]]{1,16}\]\s*)+$",                         # 纯表情代码 [doge]
    r"^(前排|沙发|板凳|打卡|签到|路过|考古|留名|抢首评)",     # 占位灌水
)]


def _is_noise(text: str) -> bool:
    t = text.strip()
    return not t or any(p.search(t) for p in NOISE_PATTERNS)


def clean_danmaku(items: list) -> list:
    """弹幕列表 (str) -> 去除平台噪音后的列表, 保序去重."""
    seen, out = set(), []
    for s in items or []:
        t = str(s).strip()
        if t and t not in seen and not _is_noise(t):
            seen.add(t)
            out.append(t)
    return out


def clean_comments(items: list) -> list:
    """评论列表 (str / dict / 含 .content 对象) -> 去除平台噪音后的列表, 保留原条目."""
    out = []
    for c in items or []:
        if isinstance(c, str):
            text = c
        elif isinstance(c, dict):
            text = c.get("content") or c.get("message") or ""
        else:
            text = getattr(c, "content", "") or getattr(c, "message", "")
        if not _is_noise(str(text)):
            out.append(c)
    return out
