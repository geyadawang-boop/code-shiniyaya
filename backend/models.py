"""Pydantic data models for B站视频总结工具"""

from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime, timezone


class VideoStat(BaseModel):
    """B站视频互动数据统计 — maps directly to B站 API data['stat']"""
    view: int = 0          # 播放量
    danmaku: int = 0       # 弹幕数
    reply: int = 0         # 评论数
    favorite: int = 0      # 收藏数
    coin: int = 0          # 投币数
    share: int = 0         # 分享数
    like: int = 0          # 点赞数
    now_rank: int = 0      # 当前排名 (0 if unranked)


class VideoInfo(BaseModel):
    # Identity
    bvid: str = Field(default="", pattern=r"^(|BV[a-zA-Z0-9]{10})$")
    aid: int = 0
    cid: int = 0

    # Content metadata
    title: str = ""
    desc: str = ""
    pic: str = ""
    duration: int = 0         # seconds
    tname: str = ""           # partition (分区), e.g. "知识", "科技", "生活"
    videos_count: int = 1     # multi-part count

    # Owner
    owner_name: str = ""
    owner_mid: int = 0
    owner_face: str = ""      # avatar URL from data['owner']['face']

    # Engagement — 7-dimension stat (was MISSING — Bug#1: P0 crash at summarizer.py:100)
    stat: VideoStat = Field(default_factory=VideoStat)

    # Temporal
    pubdate: str = ""                        # B站 API pubdate (empty if unavailable)
    pubdate_dt: Optional[datetime] = None    # parsed datetime
    fetched_at: str = ""                     # ISO 8601 fetch timestamp (UTC)

    # Tags (pipe-separated, includes partition tname + tag API)
    tags: str = ""


class SubtitleEntry(BaseModel):
    from_: float = 0
    to: float = 0
    content: str = ""


class SubtitleData(BaseModel):
    body: List[SubtitleEntry] = []
    text: str = ""
    tags: str = ""
    desc: str = ""
    all_channels_failed: bool = False
    source: str = "none"  # "official" | "asr" | "visual" | "none"
    parts_total: int = 1   # total P-count of the video (1 for single-page)
    parts_ok: int = 1      # pages whose subtitle was actually fetched


class CommentEntry(BaseModel):
    user: str = ""
    content: str = ""
    likes: int = 0
    replies: List["CommentReply"] = []


class CommentReply(BaseModel):
    user: str = ""
    content: str = ""
    likes: int = 0


class SummarizeRequest(BaseModel):
    bvid: str = Field(..., pattern=r"^BV[a-zA-Z0-9]{10}$")
    mode: str = "detailed"  # brief, detailed, keypoints, segments
    api_key: str = ""
    api_url: str = ""
    model: str = ""


class SummarizeResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class KBEntry(BaseModel):
    bvid: str = Field(..., pattern=r"^BV[a-zA-Z0-9]{10}$")
    title: str = ""
    author: str = ""
    pic: str = ""
    saved_at: str = ""
    text_length: int = 0
    text: str = ""


class KBSaveRequest(BaseModel):
    bvid: str = Field(..., pattern=r"^BV[a-zA-Z0-9]{10}$")


class RAGAskRequest(BaseModel):
    question: str
    bvids: Optional[List[str]] = None
    k: int = 5
    api_key: str = ""
    api_url: str = ""
    model: str = ""


class RAGSearchRequest(BaseModel):
    q: str
    k: int = 8
    bvids: Optional[List[str]] = None


class QAResponse(BaseModel):
    success: bool
    data: Optional[dict] = None
    error: Optional[str] = None


class HistoryEntry(BaseModel):
    id: int
    bvid: str = Field(..., pattern=r"^BV[a-zA-Z0-9]{10}$")
    title: str = ""
    author: str = ""
    mode: str = ""
    summary: str = ""
    created_at: str = ""
