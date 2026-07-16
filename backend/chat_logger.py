"""
BiliSum Chat Logger — adapted from LegalGraphQA chat_logger.py
Persists QA conversations as structured JSON with search/export/statistics.
"""
import json
import os
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any, Optional


class ChatLogger:
    """对话记录和提示词记录器 — adapted from LegalGraphQA"""

    def __init__(self, log_dir: str = None):
        if log_dir is None:
            from constants import DATA_DIR
            log_dir = os.path.join(DATA_DIR, "chat_logs")
        self.log_dir = Path(log_dir)
        self.log_dir.mkdir(parents=True, exist_ok=True)
        self.log_file = self.log_dir / "chat_history.json"
        self._load_history()

    def _load_history(self):
        if self.log_file.exists():
            try:
                with open(self.log_file, 'r', encoding='utf-8') as f:
                    self.history = json.load(f)
            except (json.JSONDecodeError, FileNotFoundError):
                self.history = {"conversations": []}
        else:
            self.history = {"conversations": []}

    def _save_history(self):
        with open(self.log_file, 'w', encoding='utf-8') as f:
            json.dump(self.history, f, ensure_ascii=False, indent=2)

    def log_conversation(self, question: str, answer: str,
                         sources: List[Dict] = None,
                         bvids: List[str] = None,
                         processing_time: float = None,
                         model: str = None) -> Dict:
        conversation = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "answer": answer,
            "sources": sources or [],
            "bvids": bvids or [],
            "processing_time": round(processing_time, 2) if processing_time else None,
            "model": model,
        }
        self.history["conversations"].append(conversation)
        self._save_history()
        return conversation

    def get_recent(self, limit: int = 10) -> List[Dict]:
        return self.history["conversations"][-limit:]

    def search(self, keyword: str) -> List[Dict]:
        keyword = keyword.lower()
        return [c for c in self.history["conversations"]
                if keyword in c.get("question", "").lower()
                or keyword in c.get("answer", "").lower()]

    def get_statistics(self) -> Dict[str, Any]:
        convs = self.history["conversations"]
        if not convs:
            return {"total": 0, "bvids": {}, "avg_time": 0}
        bvid_usage = {}
        for c in convs:
            for b in c.get("bvids", []):
                bvid_usage[b] = bvid_usage.get(b, 0) + 1
        times = [c.get("processing_time", 0) for c in convs if c.get("processing_time")]
        return {
            "total": len(convs),
            "top_bvids": sorted(bvid_usage.items(), key=lambda x: -x[1])[:10],
            "avg_time": round(sum(times) / len(times), 2) if times else 0,
        }

    def clear(self):
        self.history = {"conversations": []}
        self._save_history()


_chat_logger: Optional[ChatLogger] = None


def get_chat_logger() -> ChatLogger:
    global _chat_logger
    if _chat_logger is None:
        _chat_logger = ChatLogger()
    return _chat_logger
