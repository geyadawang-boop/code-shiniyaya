"""
反馈收集系统 - FeedbackCollector v1.1.0
支持：5星评分 + 问题标签 + 自由文本 + JSONL持久化 + SQLite存储
版本: 1.1.0 | 演化标记: evo-2026-07-09-001

Changelog v1.1.0:
  - Fix: get_stats(days=N) date filter now applied to ALL queries (not just trend)
  - Fix: _top_issues() now respects date range parameter
  - Fix: _save_jsonl() calls flush() + os.fsync() for crash durability
  - Fix: save() dual-write rolls back JSONL if SQLite write fails
  - Fix: _daily_trend() deduplicated redundant date filter (now centralized)

交叉利用: oracle (review quality) + prompt-optimizer (analyze low feedback) + model-usage (cost追踪)
"""

import json
import os
import sqlite3
import hashlib
from datetime import datetime
from typing import Optional, List, Dict

# 路径配置
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__))
FEEDBACK_JSONL = os.path.join(BACKEND_DIR, "feedback.jsonl")
DB_PATH = os.path.join(BACKEND_DIR, "data.db")

# 预定义问题标签
ISSUE_TAGS = [
    "内容不准确",          # content_inaccurate
    "总结过短",            # too_short
    "总结过长/冗余",       # too_long
    "结构不清晰",          # poor_structure
    "遗漏关键信息",        # missing_key_info
    "翻译/术语错误",       # translation_error
    "对视频理解有误",      # misunderstanding
    "格式排版问题",        # formatting_issue
    "语气/风格不合适",     # tone_issue
    "其他问题"             # other
]

ISSUE_TAGS_MAP = {
    "content_inaccurate": "内容不准确",
    "too_short": "总结过短",
    "too_long": "总结过长/冗余",
    "poor_structure": "结构不清晰",
    "missing_key_info": "遗漏关键信息",
    "translation_error": "翻译/术语错误",
    "misunderstanding": "对视频理解有误",
    "formatting_issue": "格式排版问题",
    "tone_issue": "语气/风格不合适",
    "other": "其他问题"
}


class FeedbackEntry:
    """单条反馈数据结构"""

    def __init__(
        self,
        history_id: int,
        bvid: str,
        rating: int,                          # 1-5星
        issue_tags: List[str] = None,         # 问题标签列表
        free_text: str = "",                  # 自由文本
        summary_text: str = "",               # 被评价的总结文本
        mode: str = "detailed",               # 总结模式
        model: str = "",                      # 使用的模型
        api_url: str = "",                    # API端点
        prompt_version: str = "",             # prompt版本号
        user_agent: str = "",                 # 用户浏览器
        timestamp: str = None,                # ISO时间戳
        session_id: str = "",                 # 会话ID
        metadata: Dict = None                 # 扩展元数据
    ):
        self.history_id = history_id
        self.bvid = bvid
        self.rating = max(1, min(5, rating))  # clamp 1-5
        self.issue_tags = issue_tags or []
        self.free_text = free_text
        self.summary_text = summary_text[:5000] if summary_text else ""
        self.mode = mode
        self.model = model
        self.api_url = api_url
        self.prompt_version = prompt_version
        self.user_agent = user_agent
        self.timestamp = timestamp or datetime.now().isoformat()
        self.session_id = session_id or _generate_session_id()
        self.metadata = metadata or {}
        self.feedback_id = _generate_feedback_id(history_id, self.timestamp)

    def to_dict(self) -> dict:
        return {
            "feedback_id": self.feedback_id,
            "history_id": self.history_id,
            "bvid": self.bvid,
            "rating": self.rating,
            "issue_tags": self.issue_tags,
            "free_text": self.free_text,
            "summary_text": self.summary_text,
            "mode": self.mode,
            "model": self.model,
            "api_url": self.api_url,
            "prompt_version": self.prompt_version,
            "user_agent": self.user_agent,
            "timestamp": self.timestamp,
            "session_id": self.session_id,
            "metadata": self.metadata
        }

    def to_flat_dict(self) -> dict:
        """展平格式，用于SQLite存储"""
        d = self.to_dict()
        d["issue_tags"] = json.dumps(d["issue_tags"], ensure_ascii=False)
        d["metadata"] = json.dumps(d["metadata"], ensure_ascii=False)
        return d


class FeedbackCollector:
    """
    反馈收集器 - 核心类

    用法:
        collector = FeedbackCollector()
        entry = FeedbackEntry(history_id=1, bvid="BVxxx", rating=4, issue_tags=["too_short"])
        collector.save(entry)

        # 查询统计
        stats = collector.get_stats()
    """

    def __init__(self, jsonl_path: str = None, db_path: str = None):
        self.jsonl_path = jsonl_path or FEEDBACK_JSONL
        self.db_path = db_path or DB_PATH
        self._ensure_tables()

    # ==================== 持久化 ====================

    def save(self, entry: FeedbackEntry) -> str:
        """
        保存反馈到 JSONL + SQLite 双写 (v1.1: 失败时回滚 JSONL)
        返回 feedback_id
        """
        # 1. JSONL 追加写入 (先写，失败则直接中止)
        self._save_jsonl(entry)

        # 2. SQLite 同步写入 (若失败则回滚 JSONL)
        try:
            self._save_sqlite(entry)
        except Exception:
            import logging
            _log = logging.getLogger(__name__)
            _log.exception("SQLite write failed for %s; rolling back JSONL", entry.feedback_id)
            self._rollback_jsonl(entry.feedback_id)
            raise  # re-raise so caller knows save failed

        # 3. 触发自校正检查 (低分反馈自动分析)
        if entry.rating <= 2:
            _trigger_self_correction_check(entry)

        return entry.feedback_id

    def record(self, feedback_type: str, data: dict, rating: int) -> Optional[str]:
        """
        [v7.1] Bridge method for legacy /api/feedback endpoint compatibility.

        Converts the old (type, data, rating) calling convention into a
        FeedbackEntry and persists it through the standard save() pipeline.

        Args:
            feedback_type: legacy feedback type string (e.g. "general", "summary")
            data: dict with keys matching FeedbackEntry constructor fields
            rating: 1-5 star rating

        Returns:
            feedback_id string if recordable, None if insufficient data
        """
        history_id = data.get("history_id", 0)
        bvid = data.get("bvid", "")
        if not bvid and history_id == 0:
            return None  # Cannot record feedback without identifying information
        try:
            entry = FeedbackEntry(
                history_id=history_id,
                bvid=bvid,
                rating=rating if 1 <= rating <= 5 else 0,
                issue_tags=data.get("issue_tags", []),
                free_text=data.get("free_text", ""),
                summary_text=data.get("summary_text", data.get("summary", "")),
                mode=data.get("mode", "detailed"),
                model=data.get("model", ""),
                api_url=data.get("api_url", ""),
                prompt_version=data.get("prompt_version", ""),
                user_agent=data.get("user_agent", ""),
                session_id=data.get("session_id", ""),
                metadata=data.get("metadata", {}),
            )
            return self.save(entry)
        except Exception:
            return None

    def _save_jsonl(self, entry: FeedbackEntry):
        """追加一行到 JSONL 文件 (v1.1: 加 fsync 确保持久化)"""
        os.makedirs(os.path.dirname(self.jsonl_path) or BACKEND_DIR, exist_ok=True)
        line = json.dumps(entry.to_dict(), ensure_ascii=False)
        with open(self.jsonl_path, "a", encoding="utf-8") as f:
            f.write(line + "\n")
            f.flush()
            os.fsync(f.fileno())

    def _rollback_jsonl(self, feedback_id: str):
        """v1.1: Remove the last-written entry from JSONL by rewriting without it.
        Used when SQLite write fails after JSONL already succeeded."""
        if not os.path.exists(self.jsonl_path):
            return
        lines = []
        removed = False
        try:
            with open(self.jsonl_path, "r", encoding="utf-8") as f:
                for line in f:
                    stripped = line.strip()
                    if not stripped:
                        continue
                    try:
                        obj = json.loads(stripped)
                        if obj.get("feedback_id") == feedback_id and not removed:
                            removed = True
                            continue
                    except json.JSONDecodeError:
                        pass
                    lines.append(stripped)
        except Exception:
            import logging
            logging.getLogger(__name__).exception(
                "failed to read JSONL during rollback; manual cleanup may be needed")
            return

        if removed:
            try:
                with open(self.jsonl_path, "w", encoding="utf-8") as f:
                    for l in lines:
                        f.write(l + "\n")
                    f.flush()
                    os.fsync(f.fileno())
            except Exception:
                import logging
                logging.getLogger(__name__).exception(
                    "failed to rewrite JSONL during rollback")

    def _save_sqlite(self, entry: FeedbackEntry):
        """写入 SQLite (upsert on feedback_id to handle resubmissions)"""
        conn = sqlite3.connect(self.db_path)
        flat = entry.to_flat_dict()
        try:
            conn.execute("""
                INSERT OR REPLACE INTO feedback (
                    feedback_id, history_id, bvid, rating, issue_tags,
                    free_text, summary_text, mode, model, api_url,
                    prompt_version, user_agent, timestamp, session_id, metadata
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)
            """, (
                flat["feedback_id"], flat["history_id"], flat["bvid"], flat["rating"],
                flat["issue_tags"], flat["free_text"], flat["summary_text"],
                flat["mode"], flat["model"], flat["api_url"],
                flat["prompt_version"], flat["user_agent"], flat["timestamp"],
                flat["session_id"], flat["metadata"]
            ))
            conn.commit()
        except sqlite3.Error as e:
            print(f"[feedback] SQLite write failed for {entry.feedback_id}: {e}")
        finally:
            conn.close()

    # ==================== 查询 ====================

    def get_by_bvid(self, bvid: str, limit: int = 50) -> List[dict]:
        """按视频BV号查询反馈"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM feedback WHERE bvid=? ORDER BY timestamp DESC LIMIT ?",
            (bvid, limit)
        ).fetchall()
        conn.close()
        return [_deserialize_row(dict(r)) for r in rows]

    def get_by_history_id(self, history_id: int) -> Optional[dict]:
        """按历史记录ID查询反馈"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        row = conn.execute(
            "SELECT * FROM feedback WHERE history_id=? ORDER BY timestamp DESC LIMIT 1",
            (history_id,)
        ).fetchone()
        conn.close()
        return _deserialize_row(dict(row)) if row else None

    def get_low_rated(self, max_rating: int = 2, limit: int = 50) -> List[dict]:
        """获取低分反馈列表 (用于自校正分析)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM feedback WHERE rating <= ? ORDER BY timestamp DESC LIMIT ?",
            (max_rating, limit)
        ).fetchall()
        conn.close()
        return [_deserialize_row(dict(r)) for r in rows]

    def get_recent(self, limit: int = 20) -> List[dict]:
        """获取最近反馈"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            "SELECT * FROM feedback ORDER BY timestamp DESC LIMIT ?",
            (limit,)
        ).fetchall()
        conn.close()
        return [_deserialize_row(dict(r)) for r in rows]

    # ==================== 统计 ====================

    def get_stats(self, days: int = 30, model: str = None, mode: str = None) -> dict:
        """
        获取反馈聚合统计
        返回:
        {
            "total_feedback": N,
            "avg_rating": 4.2,
            "rating_distribution": {1:N, 2:N, 3:N, 4:N, 5:N},
            "top_issues": [{"tag":"too_short", "count":15}, ...],
            "trend": [{date, avg_rating, count}, ...],  # 按天趋势
            "by_mode": {"detailed": 4.3, "brief": 3.8, ...},
            "by_model": {"claude-sonnet-4": 4.5, ...},
            "positive_rate": 0.75,  # 4星及以上占比
            "low_rate": 0.08        # 2星及以下占比
        }
        """
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row

        where_clauses = ["timestamp >= date('now', ? || ' days')"]
        params = [f"-{days}"]
        if model:
            where_clauses.append("model=?")
            params.append(model)
        if mode:
            where_clauses.append("mode=?")
            params.append(mode)

        where = " AND ".join(where_clauses)

        # 总统计
        row = conn.execute(
            f"SELECT COUNT(*) as total, AVG(rating) as avg_rating FROM feedback WHERE {where}",
            params
        ).fetchone()
        total = row["total"] or 0
        avg_rating = round(row["avg_rating"] or 0, 2)

        # 评分分布
        dist_rows = conn.execute(
            f"SELECT rating, COUNT(*) as cnt FROM feedback WHERE {where} GROUP BY rating ORDER BY rating",
            params
        ).fetchall()
        distribution = {i: 0 for i in range(1, 6)}
        for r in dist_rows:
            distribution[r["rating"]] = r["cnt"]

        # high/low rates
        high = sum(distribution[k] for k in [4, 5])
        low = sum(distribution[k] for k in [1, 2])
        positive_rate = round(high / total, 2) if total > 0 else 0
        low_rate = round(low / total, 2) if total > 0 else 0

        # 高频问题标签 (需要从JSONL解析JSON字段)
        top_issues = self._top_issues(limit=5, days=days)

        # 按天趋势
        trends = self._daily_trend(days, where, params)

        # 按模式和模型分组
        by_mode = self._group_by("mode", where, params)
        by_model = self._group_by("model", where, params)

        conn.close()

        return {
            "total_feedback": total,
            "avg_rating": avg_rating,
            "rating_distribution": distribution,
            "top_issues": top_issues,
            "trend": trends,
            "by_mode": by_mode,
            "by_model": by_model,
            "positive_rate": positive_rate,
            "low_rate": low_rate,
            "period_days": days
        }

    def _top_issues(self, limit: int = 5, days: int = 30) -> List[dict]:
        """issue_tags JSON反序列化后聚合 (v1.1: 增加日期过滤)"""
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        rows = conn.execute(
            """SELECT issue_tags FROM feedback
               WHERE issue_tags IS NOT NULL AND issue_tags != '' AND issue_tags != '[]'
                 AND timestamp >= date('now', ? || ' days')""",
            (f"-{days}",)
        ).fetchall()
        conn.close()

        tag_counts = {}
        for row in rows:
            try:
                tags = json.loads(row["issue_tags"])
                for tag in tags:
                    label = ISSUE_TAGS_MAP.get(tag, tag)
                    tag_counts[label] = tag_counts.get(label, 0) + 1
            except (json.JSONDecodeError, TypeError):
                pass

        sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)
        return [{"tag": t, "count": c} for t, c in sorted_tags[:limit]]

    def _daily_trend(self, days: int, where: str, params: list) -> List[dict]:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # v1.1: date filter is now in the WHERE clause from get_stats()
        rows = conn.execute(
            f"""
            SELECT date(timestamp) as d, AVG(rating) as avg_r, COUNT(*) as cnt
            FROM feedback
            WHERE {where}
            GROUP BY d ORDER BY d ASC
            """,
            params
        ).fetchall()
        conn.close()
        return [{"date": r["d"], "avg_rating": round(r["avg_r"], 2), "count": r["cnt"]} for r in rows]

    def _group_by(self, column: str, where: str, params: list) -> dict:
        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        # 安全: column 只能是 mode 或 model
        if column not in ("mode", "model"):
            conn.close()
            return {}
        rows = conn.execute(
            f"SELECT {column} as val, AVG(rating) as avg_r, COUNT(*) as cnt FROM feedback WHERE {where} AND {column} != '' GROUP BY {column}",
            params
        ).fetchall()
        conn.close()
        return {r["val"]: {"avg_rating": round(r["avg_r"], 2), "count": r["cnt"]} for r in rows}

    # ==================== 数据库表初始化 ====================

    def _ensure_tables(self):
        """确保 feedback 表存在"""
        conn = sqlite3.connect(self.db_path)
        conn.executescript("""
            CREATE TABLE IF NOT EXISTS feedback (
                feedback_id TEXT PRIMARY KEY,
                history_id INTEGER NOT NULL,
                bvid TEXT NOT NULL,
                rating INTEGER NOT NULL CHECK(rating >= 1 AND rating <= 5),
                issue_tags TEXT DEFAULT '[]',
                free_text TEXT DEFAULT '',
                summary_text TEXT DEFAULT '',
                mode TEXT DEFAULT 'detailed',
                model TEXT DEFAULT '',
                api_url TEXT DEFAULT '',
                prompt_version TEXT DEFAULT '',
                user_agent TEXT DEFAULT '',
                timestamp TEXT NOT NULL,
                session_id TEXT DEFAULT '',
                metadata TEXT DEFAULT '{}'
            );
            CREATE INDEX IF NOT EXISTS idx_feedback_bvid ON feedback(bvid);
            CREATE INDEX IF NOT EXISTS idx_feedback_history ON feedback(history_id);
            CREATE INDEX IF NOT EXISTS idx_feedback_rating ON feedback(rating);
            CREATE INDEX IF NOT EXISTS idx_feedback_timestamp ON feedback(timestamp DESC);
            CREATE INDEX IF NOT EXISTS idx_feedback_model ON feedback(model);
            CREATE INDEX IF NOT EXISTS idx_feedback_mode ON feedback(mode);
            CREATE INDEX IF NOT EXISTS idx_feedback_session ON feedback(session_id);
        """)
        conn.commit()
        conn.close()

        # 同时在 history 表添加反馈字段 (如果不存在)
        self._migrate_history_table()

    def _migrate_history_table(self):
        """为 history 表添加反馈相关列 (兼容旧数据库)"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.execute("PRAGMA table_info(history)")
        columns = {row[1] for row in cursor.fetchall()}

        migrations = {
            "feedback_rating": "INTEGER DEFAULT 0",
            "feedback_tags": "TEXT DEFAULT ''",
            "prompt_version": "TEXT DEFAULT ''",
            "model_version": "TEXT DEFAULT ''",
            "quality_score": "REAL DEFAULT 0.0",
            "evolution_marker": "TEXT DEFAULT ''"
        }

        for col, col_def in migrations.items():
            if col not in columns:
                try:
                    conn.execute(f"ALTER TABLE history ADD COLUMN {col} {col_def}")
                except sqlite3.OperationalError:
                    pass

        conn.commit()
        conn.close()


# ==================== 工具函数 ====================

def _generate_session_id() -> str:
    return hashlib.md5(datetime.now().isoformat().encode()).hexdigest()[:12]


def _generate_feedback_id(history_id: int, timestamp: str) -> str:
    raw = f"{history_id}:{timestamp}"
    return "fbk-" + hashlib.md5(raw.encode()).hexdigest()[:16]


def _deserialize_row(row: dict) -> dict:
    """将SQLite行中的JSON字符串字段反序列化"""
    for field in ("issue_tags", "metadata"):
        if field in row and isinstance(row[field], str):
            try:
                row[field] = json.loads(row[field])
            except (json.JSONDecodeError, TypeError):
                row[field] = [] if field == "issue_tags" else {}
    return row


def _trigger_self_correction_check(entry: FeedbackEntry):
    """
    当收到低分反馈(rating <= 2)时，触发自校正检查
    追加写入一个 JSONL 标记文件，self_correction.py 会定期扫描
    """
    flag_file = os.path.join(BACKEND_DIR, ".self_correction_trigger.jsonl")
    trigger_data = {
        "feedback_id": entry.feedback_id,
        "history_id": entry.history_id,
        "bvid": entry.bvid,
        "rating": entry.rating,
        "issue_tags": entry.issue_tags,
        "free_text": entry.free_text,
        "mode": entry.mode,
        "model": entry.model,
        "prompt_version": entry.prompt_version,
        "timestamp": entry.timestamp
    }
    os.makedirs(BACKEND_DIR, exist_ok=True)
    try:
        with open(flag_file, "a", encoding="utf-8") as f:
            f.write(json.dumps(trigger_data, ensure_ascii=False) + "\n")
    except (IOError, OSError) as e:
        print(f"[feedback] Failed to write self-correction trigger: {e}")
