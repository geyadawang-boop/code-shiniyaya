"""SQLite database operations for B站视频总结工具"""
import sqlite3
import os
import stat
import threading
import logging
from datetime import datetime
from typing import Optional

logger = logging.getLogger(__name__)

DB_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(DB_DIR, "data.db")

def _get_kb_dir() -> str:
    """Resolve KB directory from settings or default to data/knowledge_base.

    Validates that the stored path is both absolute AND writable (not placeholder text).
    Falls back to the default if the stored path is invalid.
    """
    try:
        # Use db directly to avoid circular import from get_setting
        import sqlite3 as _sql
        from pathlib import Path
        conn = _sql.connect(DB_PATH)
        row = conn.execute("SELECT value FROM api_settings WHERE key_name='kb_dir'").fetchone()
        conn.close()
        if row and row[0]:
            custom = row[0]
            # validate_kb_dir: must be absolute AND pass the write probe
            if os.path.isabs(custom):
                try:
                    path = Path(custom)
                    path.mkdir(parents=True, exist_ok=True)
                    test_file = path / ".access_test"
                    test_file.touch(exist_ok=True)
                    test_file.unlink()
                    return custom
                except (OSError, PermissionError):
                    logger.warning(
                        "_get_kb_dir: stored kb_dir is absolute but unwritable (%s), falling back to default",
                        custom
                    )
            else:
                logger.warning(
                    "_get_kb_dir: stored kb_dir is not an absolute path (%s), falling back to default",
                    custom
                )
    except Exception as e:
        logger.error("_get_kb_dir: DB connection failed, using default path: %s", e, exc_info=True)
    return os.path.join(os.path.dirname(DB_DIR), "knowledge_base")

KB_DIR = _get_kb_dir()
CHUNKS_DIR = os.path.join(KB_DIR, "chunks")


def kb_filepath(bvid: str, title: str = "") -> str:
    """Resolve the KB JSON path for a bvid.

    Reads find either the legacy {bvid}.json or the new {bvid}_{title}.json.
    Writes (title given) produce {bvid}_{safe_title}.json.
    """
    import re as _re
    legacy = os.path.join(KB_DIR, f"{bvid}.json")
    if title:
        safe = _re.sub(r'[\\/:*?"<>|]', '_', title).strip('. ')[:50]
        return os.path.join(KB_DIR, f"{bvid}_{safe}.json") if safe else legacy
    if os.path.exists(legacy):
        return legacy
    if os.path.isdir(KB_DIR):
        for f in os.listdir(KB_DIR):
            if f.startswith(f"{bvid}_") and f.endswith(".json"):
                return os.path.join(KB_DIR, f)
    return legacy


def refresh_kb_dir():
    """Hot-reload KB_DIR/CHUNKS_DIR from settings (call after kb_dir setting changes).

    Module-level constants are re-pointed so all in-module consumers pick up
    the new path immediately; also syncs classifier's imported copy.
    """
    global KB_DIR, CHUNKS_DIR
    KB_DIR = _get_kb_dir()
    CHUNKS_DIR = os.path.join(KB_DIR, "chunks")
    os.makedirs(KB_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    # Sync classifier module copy (it imports KB_DIR by value at import time)
    try:
        import classifier as _clf_mod
        _clf_mod.KB_DIR = KB_DIR
        _clf_mod.CLASSIFICATION_CACHE_FILE = os.path.join(KB_DIR, ".classification_cache.json")
    except Exception as e:
        logger.warning("refresh_kb_dir: classifier sync failed: %s", e)
    _invalidate_kb_index()
    logger.info("KB_DIR refreshed: %s", KB_DIR)
    return KB_DIR


def get_db():
    """Create a fresh SQLite connection with WAL mode and optimized PRAGMAs.

    Each call opens a new connection to avoid shared mutable state across
    async coroutines.  SQLite WAL mode + busy_timeout=5000 handles
    concurrent write contention safely; connection-open overhead is
    negligible in WAL mode.
    """
    conn = sqlite3.connect(DB_PATH)
    # [P0-9] Ensure write permission for WAL mode on Windows
    try:
        os.chmod(DB_PATH, 0o600)
    except Exception:
        pass  # Windows: os.chmod has limited effect; use icacls if needed
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.execute("PRAGMA mmap_size=268435456")
    conn.execute("PRAGMA cache_size=-64000")
    conn.execute("PRAGMA temp_store=MEMORY")
    conn.execute("PRAGMA foreign_keys=ON")
    return conn


# In-memory KB index for O(1) lookups (populated lazily)
_kb_index = None
_kb_index_lock = threading.Lock()


def _rebuild_kb_index():
    """Rebuild the in-memory knowledge base index from disk."""
    import json as _json
    global _kb_index
    idx = {}
    if os.path.exists(KB_DIR):
        for f in os.listdir(KB_DIR):
            if f.endswith(".json"):
                try:
                    with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fp:
                        data = _json.load(fp)
                    bvid = data.get("bvid", "")
                    if bvid:
                        idx[bvid] = {
                            "bvid": bvid,
                            "title": data.get("title", ""),
                            "author": data.get("author", ""),
                            "pic": data.get("pic", ""),
                            "savedAt": data.get("savedAt", ""),
                            "textLength": data.get("textLength", 0)
                        }
                except Exception:
                    logger.warning("Error reading KB entry: %s", f, exc_info=True)
    _kb_index = idx
    return idx


def _get_kb_index():
    global _kb_index
    if _kb_index is None:
        with _kb_index_lock:
            if _kb_index is None:
                _rebuild_kb_index()
    return _kb_index


def _invalidate_kb_index():
    global _kb_index
    with _kb_index_lock:
        _kb_index = None


def init_db():
    os.makedirs(KB_DIR, exist_ok=True)
    os.makedirs(CHUNKS_DIR, exist_ok=True)
    conn = get_db()
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA busy_timeout=5000")
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS history (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            bvid TEXT NOT NULL,
            title TEXT DEFAULT '',
            author TEXT DEFAULT '',
            mode TEXT DEFAULT 'detailed',
            summary TEXT DEFAULT '',
            created_at TEXT DEFAULT (datetime('now', 'localtime'))
        );
        CREATE TABLE IF NOT EXISTS api_settings (
            key_name TEXT PRIMARY KEY,
            value TEXT DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS idx_history_bvid ON history(bvid);
        CREATE INDEX IF NOT EXISTS idx_history_created ON history(created_at DESC);
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_fts USING fts5(
            bvid, title, content, tokenize='unicode61'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS history_fts USING fts5(
            title, author, summary, content='history', content_rowid='id',
            tokenize='unicode61 remove_diacritics 2'
        );
        CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
            bvid, title, content, chunk_index, tokenize='unicode61'
        );
    """)
    # Clean ghost FTS entries (orphaned records with no .json file)
    try:
        ghosts = conn.execute("SELECT bvid FROM kb_fts").fetchall()
        for g in ghosts:
            if not os.path.isfile(kb_filepath(g['bvid'])):
                conn.execute("DELETE FROM kb_fts WHERE bvid=?", (g['bvid'],))
        conn.commit()
    except Exception as e:
        logger.warning("Ghost FTS cleanup failed: %s", e, exc_info=True)
    conn.close()

    # Schema migration: upgrade KB entries to latest version
    _migrate_kb_entries()

def _migrate_kb_entries():
    """Auto-migrate KB JSON entries to schema_version=2.

    v1 entries (schema_version absent or < 2) get default classification fields
    added so that the filtered KB listing and smart-classify features don't break.
    """
    import json as _json
    if not os.path.exists(KB_DIR):
        return
    migrated = 0
    for f in os.listdir(KB_DIR):
        if not f.endswith(".json"):
            continue
        filepath = os.path.join(KB_DIR, f)
        try:
            with open(filepath, "r", encoding="utf-8") as fp:
                entry = _json.load(fp)
            sv = entry.get("schema_version", 1)
            if sv >= 2:
                continue
            # Add default fields for v2 classification
            entry.setdefault("video_type", "")
            entry.setdefault("difficulty", "")
            entry.setdefault("language", "")
            entry.setdefault("duration_category", "")
            entry.setdefault("topic", "")
            entry.setdefault("quality_tier", "B")
            entry.setdefault("tags", [])
            entry.setdefault("classification", {})
            entry["schema_version"] = 2
            with open(filepath, "w", encoding="utf-8") as fp:
                _json.dump(entry, fp, ensure_ascii=False, indent=2)
            migrated += 1
        except Exception:
            logger.debug("Failed to migrate KB entry: %s", f, exc_info=True)
    if migrated > 0:
        logger.info("Migrated %d KB entries from v1 to v2", migrated)
        _invalidate_kb_index()

    # Create FTS5 sync triggers for history table (idempotent via IF NOT EXISTS)
    conn = get_db()
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS history_ai AFTER INSERT ON history BEGIN
            INSERT INTO history_fts(rowid, title, author, summary)
            VALUES (new.id, new.title, new.author, new.summary);
        END;
        CREATE TRIGGER IF NOT EXISTS history_ad AFTER DELETE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, author, summary)
            VALUES ('delete', old.id, old.title, old.author, old.summary);
        END;
        CREATE TRIGGER IF NOT EXISTS history_au AFTER UPDATE ON history BEGIN
            INSERT INTO history_fts(history_fts, rowid, title, author, summary)
            VALUES ('delete', old.id, old.title, old.author, old.summary);
            INSERT INTO history_fts(rowid, title, author, summary)
            VALUES (new.id, new.title, new.author, new.summary);
        END;
    """)

    # Populate FTS5 index from existing history data (idempotent)
    conn.execute("""
        INSERT OR IGNORE INTO history_fts(rowid, title, author, summary)
        SELECT id, title, author, summary FROM history
    """)
    conn.commit()


# --- History ---

def save_history(bvid: str, title: str, author: str, mode: str, summary: str) -> int:
    conn = get_db()
    c = conn.execute(
        "INSERT INTO history (bvid, title, author, mode, summary) VALUES (?,?,?,?,?)",
        (bvid, title, author, mode, summary)
    )
    conn.commit()
    row_id = c.lastrowid
    conn.close()
    return row_id


def get_history_list(search: str = "", limit: int = 50, offset: int = 0) -> list:
    conn = get_db()
    if search:
        # Build FTS5 query: prefix queries for instant partial matching
        terms = [f'"{word}"*' for word in search.split() if len(word) >= 1]
        if terms:
            fts_query = " OR ".join(terms)
            try:
                rows = conn.execute("""
                    SELECT h.*
                    FROM history h
                    INNER JOIN history_fts fts ON h.id = fts.rowid
                    WHERE history_fts MATCH ?
                    ORDER BY rank
                    LIMIT ? OFFSET ?
                """, (fts_query, limit, offset)).fetchall()
                conn.close()
                return [dict(r) for r in rows]
            except Exception:
                logger.warning("FTS5 history search failed, falling back to LIKE", exc_info=True)
        # Fallback: LIKE-based search
        rows = conn.execute(
            "SELECT * FROM history WHERE title LIKE ? OR bvid LIKE ? OR summary LIKE ? ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (f"%{search}%", f"%{search}%", f"%{search}%", limit, offset)
        ).fetchall()
    else:
        rows = conn.execute(
            "SELECT * FROM history ORDER BY created_at DESC LIMIT ? OFFSET ?",
            (limit, offset)
        ).fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_history_by_id(history_id: int) -> Optional[dict]:
    conn = get_db()
    row = conn.execute("SELECT * FROM history WHERE id=?", (history_id,)).fetchone()
    return dict(row) if row else None


def get_history_for_bvid(bvid: str, limit: int = 10) -> list:
    """Get history entries for a specific video by BVID."""
    conn = get_db()
    rows = conn.execute(
        "SELECT * FROM history WHERE bvid=? ORDER BY created_at DESC LIMIT ?",
        (bvid, limit)
    ).fetchall()
    return [dict(r) for r in rows]


def delete_history(history_id: int) -> bool:
    conn = get_db()
    cursor = conn.execute("DELETE FROM history WHERE id=?", (history_id,))
    conn.commit()
    changes = cursor.rowcount
    return changes > 0


# --- API Settings ---

def get_setting(key: str, default: str = "") -> str:
    conn = get_db()
    row = conn.execute("SELECT value FROM api_settings WHERE key_name=?", (key,)).fetchone()
    conn.close()
    return row["value"] if row else default


def save_setting(key: str, value: str):
    conn = get_db()
    conn.execute(
        "INSERT OR REPLACE INTO api_settings (key_name, value) VALUES (?,?)",
        (key, value)
    )
    conn.commit()
    conn.close()


# --- Knowledge Base ---

def save_kb_entry(bvid: str, title: str, author: str, pic: str, text: str, folder_name: str = "", source: str = "manual",
                   desc: str = "", duration: int = 0, pubdate: str = "", tags: str = "",
                   tname: str = "", stat: dict = None, owner_mid: int = 0) -> dict:
    import json
    entry = {
        "bvid": bvid,
        "title": title,
        "author": author,
        "pic": pic,
        "folder": folder_name,
        "source": source,
        "desc": desc or "",
        "duration": duration or 0,
        "pubdate": pubdate or "",
        "tags": tags or "",
        "tname": tname or "",
        "stat": stat or {},
        "owner_mid": owner_mid or 0,
        "savedAt": datetime.now().isoformat(),
        "textLength": len(text),
        "text": text[:100000]
    }
    # Remove any older file for this bvid (name may differ if title changed)
    old = kb_filepath(bvid)
    if os.path.exists(old):
        try:
            os.remove(old)
        except OSError:
            logger.warning("Could not remove old KB file: %s", old)
    filepath = kb_filepath(bvid, title)
    with open(filepath, "w", encoding="utf-8") as f:
        json.dump(entry, f, ensure_ascii=False, indent=2)
    _invalidate_kb_index()  # flush cached index
    return entry


def get_kb_list() -> list:
    """Get KB entries from in-memory index (O(1) after first load)."""
    idx = _get_kb_index()
    entries = list(idx.values())
    entries.sort(key=lambda x: x.get("savedAt", ""), reverse=True)
    return entries


def get_kb_entry(bvid: str) -> Optional[dict]:
    import json
    filepath = kb_filepath(bvid)
    if os.path.exists(filepath):
        with open(filepath, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def delete_kb_entry(bvid: str) -> bool:
    filepath = kb_filepath(bvid)
    if os.path.exists(filepath):
        os.remove(filepath)
        # Also remove chunks
        if os.path.exists(CHUNKS_DIR):
            for f in os.listdir(CHUNKS_DIR):
                if f.startswith(f"{bvid}_"):
                    os.remove(os.path.join(CHUNKS_DIR, f))
        # Clean both FTS5 tables (kb_fts + kb_chunks_fts)
        try:
            conn2 = get_db()
            for tbl in ("kb_fts", "kb_chunks_fts"):
                conn2.execute(f"DELETE FROM {tbl} WHERE bvid=?", (bvid,))
            conn2.commit()
        except Exception as e:
            logger.warning("FTS cleanup failed for bvid=%s: %s", bvid, e)
        # Clean FTS5Backend state (semantic_search)
        try:
            from semantic_search import FTS5Backend
            FTS5Backend().delete_video(bvid)
        except Exception as e:
            logger.warning("FTS5Backend cleanup failed for bvid=%s: %s", bvid, e)
        # Clean ChromaDB vector store (use singleton so api_key is wired)
        try:
            from main import get_rag_service
            rag = get_rag_service()
            if rag is not None:
                rag.delete_video(bvid)
        except Exception as e:
            logger.warning("ChromaDB cleanup failed for bvid=%s: %s", bvid, e)
        # Clean ASR audio cache files (data/asr_cache/{bvid}_{cid}.m4a)
        try:
            from asr_service import AUDIO_CACHE_DIR
            if os.path.exists(AUDIO_CACHE_DIR):
                for f in os.listdir(AUDIO_CACHE_DIR):
                    if f.startswith(f"{bvid}_"):
                        os.remove(os.path.join(AUDIO_CACHE_DIR, f))
        except Exception as e:
            logger.warning("ASR cache cleanup failed for bvid=%s: %s", bvid, e)
        # Clean keyframe/visual-context video cache (data/frames_cache/{bvid}/)
        try:
            import shutil
            from constants import FRAMES_CACHE_DIR
            frames_dir = os.path.join(FRAMES_CACHE_DIR, bvid)
            if os.path.isdir(frames_dir):
                shutil.rmtree(frames_dir, ignore_errors=True)
        except Exception as e:
            logger.warning("Frames cache cleanup failed for bvid=%s: %s", bvid, e)
        # Clean downloaded video files (download_dir/*_{bvid}/ or download_dir/{bvid}/)
        try:
            import shutil
            download_root = get_setting("download_dir", "") or os.path.join(
                os.path.dirname(DB_DIR), "downloads")
            if os.path.isdir(download_root):
                for entry in os.listdir(download_root):
                    if entry == bvid or entry.endswith(f"_{bvid}"):
                        rm_path = os.path.join(download_root, entry)
                        if os.path.isdir(rm_path):
                            shutil.rmtree(rm_path, ignore_errors=True)
        except Exception as e:
            logger.warning("Download dir cleanup failed for bvid=%s: %s", bvid, e)
        # Clean classification cache (classifier.py)
        try:
            from classifier import get_classifier
            clf = get_classifier()
            if bvid in clf._classification_cache:
                del clf._classification_cache[bvid]
                clf._save_cache()
        except Exception as e:
            logger.warning("Classification cache cleanup failed for bvid=%s: %s", bvid, e)
        # Clean incremental index metadata
        try:
            conn3 = get_db()
            conn3.execute("DELETE FROM kb_index_meta WHERE bvid=?", (bvid,))
            conn3.commit()
            conn3.close()
        except Exception as e:
            logger.warning("kb_index_meta cleanup failed for bvid=%s: %s", bvid, e)
        _invalidate_kb_index()
        return True
    return False


def search_kb(query: str, max_results: int = 8, filter_bvids: list = None) -> list:
    import json

    # Try FTS5 full-text search first
    try:
        conn = get_db()
        # Sanitize query for FTS5: build prefix terms to avoid syntax errors from
        # special characters (double-quotes, asterisks, parentheses, caret, etc.)
        # Also filter out FTS5 boolean operators (AND, OR, NOT, NEAR) which would
        # be interpreted as operators rather than search terms.
        _FTS5_OPERATORS = {"AND", "OR", "NOT", "NEAR"}
        terms = []
        cleaned = query.replace('"', '').replace('*', '').replace('(', '').replace(')', '').replace('^', '')
        for word in cleaned.split():
            w = word.strip().strip("'")
            if len(w) >= 1:
                if w.upper() in _FTS5_OPERATORS:
                    continue
                terms.append(f'"{w}"*')
        fts_query = " OR ".join(terms) if terms else query.replace('"', '""')
        sql = (
            "SELECT bvid, title, snippet(kb_fts, 2, '<mark>', '</mark>', '...', 40) as snippet, "
            "rank FROM kb_fts WHERE kb_fts MATCH ? ORDER BY rank LIMIT ?"
        )
        fts_results = conn.execute(sql, (fts_query, max_results)).fetchall()
        if fts_results:
            results = []
            for r in fts_results:
                bvid = r["bvid"]
                if not os.path.isfile(kb_filepath(bvid)):
                    continue  # skip ghost entries
                if filter_bvids and bvid not in filter_bvids:
                    continue
                results.append({
                    "bvid": bvid,
                    "title": r["title"],
                    "snippet": r["snippet"],
                    "score": 1.0 / (1.0 + abs(r["rank"])) if r["rank"] is not None else 1.0,
                    "url": f"https://www.bilibili.com/video/{bvid}",
                    "_fts": True,
                })
            if results:
                conn.close()
                return results
    except Exception:
        logger.warning("FTS5 kb_fts search failed, falling back to file scan", exc_info=True)
        conn.close()

    # Fallback: linear scan over chunk files (O(n) CJK keyword search)
    results = []
    if not os.path.exists(CHUNKS_DIR):
        return results

    for f in os.listdir(CHUNKS_DIR):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(CHUNKS_DIR, f), "r", encoding="utf-8") as fp:
                data = json.load(fp)

            if filter_bvids and data.get("bvid", "") not in filter_bvids:
                continue

            content = data.get("content", "")
            score = _keyword_score(query, content)
            if score > 0:
                results.append({
                    "bvid": data.get("bvid", ""),
                    "title": data.get("title", ""),
                    "content": content,
                    "chunkIndex": data.get("chunkIndex", 0),
                    "score": score,
                    "url": f"https://www.bilibili.com/video/{data.get('bvid', '')}"
                })
        except Exception:
            logger.warning("Error reading chunk file: %s", f, exc_info=True)

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


def index_kb_fts(bvid: str, title: str, text: str, conn=None):
    """Index KB document into FTS5 for full-text search."""
    if conn is None:
        conn = get_db()
    try:
        # Remove existing entries for this bvid
        conn.execute("DELETE FROM kb_fts WHERE bvid=?", (bvid,))
        # Insert as a single document (concatenate title + text for search)
        conn.execute(
            "INSERT INTO kb_fts (bvid, title, content) VALUES (?, ?, ?)",
            (bvid, title, text[:100000])
        )
        conn.commit()
    except Exception:
        logger.warning("FTS5 index_kb_fts failed for bvid=%s", bvid, exc_info=True)


def rebuild_kb_fts() -> dict:
    """Rebuild both kb_fts and kb_chunks_fts from all KB JSON files.
    Returns counts of indexed documents, chunks, and any errors."""
    import json as _json

    if not os.path.exists(KB_DIR):
        return {"kb_fts": 0, "kb_chunks_fts": 0, "errors": ["KB_DIR not found"]}

    conn = get_db()
    errors = []
    kb_count = 0
    chunk_count = 0

    try:
        conn.execute("DELETE FROM kb_fts")
        conn.execute("DELETE FROM kb_chunks_fts")
    except Exception as e:
        errors.append(f"FTS clear failed: {e}")
        conn.close()
        return {"kb_fts": 0, "kb_chunks_fts": 0, "errors": errors}

    for fname in os.listdir(KB_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(KB_DIR, fname), "r", encoding="utf-8") as fp:
                entry = _json.load(fp)
        except Exception as e:
            errors.append(f"Failed to read {fname}: {e}")
            continue

        bvid = entry.get("bvid", "")
        title = entry.get("title", "")
        text = entry.get("text", "")
        if not bvid or (not title and not text):
            continue

        try:
            conn.execute(
                "INSERT INTO kb_fts (bvid, title, content) VALUES (?, ?, ?)",
                (bvid, title, text[:100000])
            )
            kb_count += 1
        except Exception as e:
            errors.append(f"kb_fts insert failed for {bvid}: {e}")

        if text:
            chunks = _split_text(text)
            for i, chunk in enumerate(chunks):
                try:
                    conn.execute(
                        "INSERT INTO kb_chunks_fts (bvid, title, content, chunk_index) VALUES (?, ?, ?, ?)",
                        (bvid, title, chunk, i)
                    )
                    chunk_count += 1
                except Exception as e:
                    errors.append(f"kb_chunks_fts insert failed for {bvid} chunk {i}: {e}")

    conn.commit()
    conn.close()
    logger.info("rebuild_kb_fts: indexed %d KB entries, %d chunks, %d errors", kb_count, chunk_count, len(errors))
    return {"kb_fts": kb_count, "kb_chunks_fts": chunk_count, "errors": errors}


def save_chunks(bvid: str, title: str, text: str):
    """Split text into chunks and save"""
    import json
    chunks = _split_text(text)
    # Remove old chunks
    if os.path.exists(CHUNKS_DIR):
        for f in os.listdir(CHUNKS_DIR):
            if f.startswith(f"{bvid}_"):
                os.remove(os.path.join(CHUNKS_DIR, f))
    # Save new chunks
    for i, chunk in enumerate(chunks):
        chunk_data = {
            "bvid": bvid,
            "title": title,
            "chunkIndex": i,
            "content": chunk,
            "totalChunks": len(chunks)
        }
        with open(os.path.join(CHUNKS_DIR, f"{bvid}_{i}.json"), "w", encoding="utf-8") as f:
            json.dump(chunk_data, f, ensure_ascii=False, indent=2)

    # Save metadata chunk
    meta_content = f"视频标题：{title}"
    with open(os.path.join(CHUNKS_DIR, f"{bvid}_meta.json"), "w", encoding="utf-8") as f:
        json.dump({
            "bvid": bvid, "title": title, "chunkIndex": -1,
            "content": meta_content, "totalChunks": len(chunks), "isMetadata": True
        }, f, ensure_ascii=False, indent=2)

    # Also index into FTS5 (atomic: same connection)
    conn = get_db()
    index_kb_fts(bvid, title, text, conn=conn)
    # v8.3: Also populate kb_chunks_fts for per-chunk full-text search
    conn.execute("DELETE FROM kb_chunks_fts WHERE bvid=?", (bvid,))
    for i, chunk in enumerate(chunks):
        conn.execute(
            "INSERT INTO kb_chunks_fts (bvid, title, content, chunk_index) VALUES (?, ?, ?, ?)",
            (bvid, title, chunk, i)
        )
    conn.commit()


def get_kb_stats() -> dict:
    total_videos = 0
    total_chunks = 0
    if os.path.exists(KB_DIR):
        for f in os.listdir(KB_DIR):
            if f.endswith(".json"):
                total_videos += 1
    if os.path.exists(CHUNKS_DIR):
        total_chunks = len([f for f in os.listdir(CHUNKS_DIR) if f.endswith(".json")])
    return {"totalVideos": total_videos, "totalChunks": total_chunks}


# --- Smart Categorize: Classification database operations ---

def _load_json_entry(bvid: str) -> Optional[dict]:
    """Load a KB JSON entry by bvid. Returns None if not found."""
    import json as _json
    filepath = kb_filepath(bvid)
    if not os.path.exists(filepath):
        return None
    with open(filepath, "r", encoding="utf-8") as f:
        return _json.load(f)


def _save_json_entry(bvid: str, entry: dict):
    """Save (overwrite) a KB JSON entry."""
    import json as _json
    filepath = kb_filepath(bvid)
    with open(filepath, "w", encoding="utf-8") as f:
        _json.dump(entry, f, ensure_ascii=False, indent=2)


def save_classification(bvid: str, classification: dict) -> bool:
    """
    Persist classification data into the KB entry JSON.
    Updates the entry in-place with classification fields + schema_version bump.
    Returns True on success.
    """
    entry = _load_json_entry(bvid)
    if entry is None:
        return False
    entry["classification"] = classification
    entry["video_type"] = classification.get("video_type", "")
    entry["tags"] = classification.get("tags", [])
    entry["difficulty"] = classification.get("difficulty", "")
    entry["language"] = classification.get("language", "")
    entry["duration_category"] = classification.get("duration_category", "")
    entry["topic"] = classification.get("topic", "")
    entry["quality_tier"] = classification.get("quality_tier", "B")
    entry["schema_version"] = 2
    _save_json_entry(bvid, entry)
    _invalidate_kb_index()
    return True


def get_kb_list_filtered(
    video_type: str = "",
    difficulty: str = "",
    language: str = "",
    duration_category: str = "",
    quality_tier: str = "",
    tag: str = "",
    search: str = "",
    source: str = "",
    sort_by: str = "savedAt",
    sort_order: str = "desc",
    limit: int = 50,
    offset: int = 0,
) -> list:
    """
    Multi-dimensional filtered KB listing.
    Supports all 5 classification dimensions + tag filtering + source.
    source: ""=all, "manual"=手动导入, "favorites"=收藏夹导入
    """
    import json as _json
    entries = []

    if not os.path.exists(KB_DIR):
        return entries

    for f in os.listdir(KB_DIR):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fp:
                data = _json.load(fp)
            entries.append(data)
        except Exception:
            logger.warning("Error reading chunk file: %s", f, exc_info=True)

    # Apply filters
    if video_type:
        entries = [e for e in entries if e.get("video_type", "") == video_type]
    if difficulty:
        entries = [e for e in entries if e.get("difficulty", "") == difficulty]
    if language:
        entries = [e for e in entries if e.get("language", "") == language]
    if duration_category:
        entries = [e for e in entries if e.get("duration_category", "") == duration_category]
    if quality_tier:
        entries = [e for e in entries if e.get("quality_tier", "") == quality_tier]
    if tag:
        tag_lower = tag.lower()
        entries = [e for e in entries if any(tag_lower in t.lower() for t in e.get("tags", []))]
    if search:
        s_lower = search.lower()
        entries = [e for e in entries
                   if s_lower in (e.get("title", "") + e.get("author", "")).lower()]
    if source:
        entries = [e for e in entries if e.get("source", source) == source]

    # Sort
    reverse = sort_order == "desc"
    if sort_by == "savedAt":
        entries.sort(key=lambda x: x.get("savedAt", ""), reverse=reverse)
    elif sort_by == "title":
        entries.sort(key=lambda x: x.get("title", ""), reverse=reverse)
    elif sort_by == "quality_tier":
        tier_order = {"S": 4, "A": 3, "B": 2, "C": 1}
        entries.sort(key=lambda x: tier_order.get(x.get("quality_tier", "B"), 2), reverse=reverse)
    elif sort_by == "textLength":
        entries.sort(key=lambda x: x.get("textLength", 0), reverse=reverse)

    # Paginate
    total = len(entries)
    entries = entries[offset:offset + limit]

    # Strip text field for list view performance
    summary_entries = []
    for e in entries:
        summary_entries.append({
            "bvid": e.get("bvid", ""),
            "title": e.get("title", ""),
            "author": e.get("author", ""),
            "pic": e.get("pic", ""),
            "savedAt": e.get("savedAt", ""),
            "textLength": e.get("textLength", 0),
            "video_type": e.get("video_type", "未分类"),
            "difficulty": e.get("difficulty", ""),
            "language": e.get("language", ""),
            "duration_category": e.get("duration_category", ""),
            "quality_tier": e.get("quality_tier", "B"),
            "topic": e.get("topic", ""),
            "tags": e.get("tags", [])[:8],
            "folder": e.get("folder", ""),
            "source": e.get("source", "manual"),
        })

    return {"entries": summary_entries, "total": total, "limit": limit, "offset": offset}


def get_category_index() -> dict:
    """
    Build a categorized index of all KB entries.
    Returns a nested dict: {video_type: {difficulty: [...entries]}}
    """
    import json as _json
    index: dict[str, dict[str, list]] = {}

    if not os.path.exists(KB_DIR):
        return index

    for f in os.listdir(KB_DIR):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fp:
                data = _json.load(fp)
        except Exception:
            logger.warning("Error reading KB file in get_category_index: %s", f, exc_info=True)
            continue

        vt = data.get("video_type", "未分类") or "未分类"
        diff = data.get("difficulty", "未知") or "未知"

        if vt not in index:
            index[vt] = {}
        if diff not in index[vt]:
            index[vt][diff] = []

        index[vt][diff].append({
            "bvid": data.get("bvid", ""),
            "title": data.get("title", ""),
            "author": data.get("author", ""),
            "pic": data.get("pic", ""),
            "savedAt": data.get("savedAt", ""),
            "textLength": data.get("textLength", 0),
            "quality_tier": data.get("quality_tier", "B"),
            "tags": data.get("tags", [])[:5],
            "topic": data.get("topic", ""),
            "language": data.get("language", ""),
            "duration_category": data.get("duration_category", ""),
        })

    return index


def get_tag_cloud(limit: int = 50) -> list:
    """Return the most frequent tags across all KB entries."""
    import json as _json
    tag_counts: dict[str, int] = {}

    if not os.path.exists(KB_DIR):
        return []

    for f in os.listdir(KB_DIR):
        if not f.endswith(".json"):
            continue
        try:
            with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fp:
                data = _json.load(fp)
        except Exception:
            logger.warning("Error reading KB file in get_tag_cloud: %s", f, exc_info=True)
            continue

        for tag in data.get("tags", []):
            tag_clean = tag.strip()
            if tag_clean:
                tag_counts[tag_clean] = tag_counts.get(tag_clean, 0) + 1

    sorted_tags = sorted(tag_counts.items(), key=lambda x: x[1], reverse=True)[:limit]
    # Normalize for tag cloud display: max count maps to font-size multiplier
    max_count = sorted_tags[0][1] if sorted_tags else 1
    return [
        {"tag": tag, "count": count, "weight": round(count / max_count, 2)}
        for tag, count in sorted_tags
    ]


def get_category_stats_extended() -> dict:
    """
    Extended KB stats with category distribution.
    Replaces plain get_kb_stats() for the dashboard.
    """
    import json as _json
    total_videos = 0
    total_chunks = 0
    type_counts: dict[str, int] = {}
    difficulty_counts: dict[str, int] = {}
    quality_counts: dict[str, int] = {}
    language_counts: dict[str, int] = {}
    duration_counts: dict[str, int] = {}
    unclassified = 0

    if os.path.exists(KB_DIR):
        for f in os.listdir(KB_DIR):
            if f.endswith(".json"):
                total_videos += 1
                try:
                    with open(os.path.join(KB_DIR, f), "r", encoding="utf-8") as fp:
                        data = _json.load(fp)
                except Exception:
                    logger.warning("Error reading KB file in get_category_stats_extended: %s", f, exc_info=True)
                    continue

                vt = data.get("video_type", "") or "未分类"
                if not data.get("video_type"):
                    unclassified += 1
                type_counts[vt] = type_counts.get(vt, 0) + 1

                diff = data.get("difficulty", "") or "未知"
                difficulty_counts[diff] = difficulty_counts.get(diff, 0) + 1

                qt = data.get("quality_tier", "") or "B"
                quality_counts[qt] = quality_counts.get(qt, 0) + 1

                lang = data.get("language", "") or "未知"
                language_counts[lang] = language_counts.get(lang, 0) + 1

                dc = data.get("duration_category", "") or "未知"
                duration_counts[dc] = duration_counts.get(dc, 0) + 1

    if os.path.exists(CHUNKS_DIR):
        total_chunks = len([f for f in os.listdir(CHUNKS_DIR) if f.endswith(".json")])

    return {
        "totalVideos": total_videos,
        "totalChunks": total_chunks,
        "unclassified": unclassified,
        "classificationRate": round((total_videos - unclassified) / max(total_videos, 1) * 100, 1),
        "byType": dict(sorted(type_counts.items(), key=lambda x: x[1], reverse=True)),
        "byDifficulty": difficulty_counts,
        "byQuality": quality_counts,
        "byLanguage": language_counts,
        "byDuration": duration_counts,
    }


def search_kb_classified(
    query: str,
    video_type: str = "",
    difficulty: str = "",
    max_results: int = 8,
    filter_bvids: list = None,
    boost_classified: bool = True,
) -> list:
    """
    Category-aware KB search.
    When boost_classified=True, results whose video_type matches query keywords
    get a 1.5x score multiplier.
    """
    results = search_kb(query, max_results=max_results * 2, filter_bvids=filter_bvids)

    if not boost_classified:
        return results[:max_results]

    # Boost results matching category context
    for doc in results:
        entry = _load_json_entry(doc.get("bvid", ""))
        if entry:
            vt = entry.get("video_type", "").lower()
            topic = entry.get("topic", "").lower()
            tags_lower = [t.lower() for t in entry.get("tags", [])]
            query_lower = query.lower()

            boost = 1.0
            # Category type match
            if vt and any(kw in query_lower for kw in vt.split()):
                boost = 1.5
            # Topic match
            if topic and topic in query_lower:
                boost = max(boost, 1.8)
            # Tag match
            if any(t in query_lower for t in tags_lower):
                boost = max(boost, 1.3)

            doc["score"] = round(doc["score"] * boost, 3)
            doc["video_type"] = entry.get("video_type", "")
            doc["tags"] = entry.get("tags", [])[:5]

    results.sort(key=lambda x: x["score"], reverse=True)
    return results[:max_results]


# --- Text Processing ---

def _split_text(text: str, chunk_size: int = 1000, chunk_overlap: int = 200) -> list:
    """RecursiveCharacterTextSplitter equivalent"""
    if not text:
        return []
    separators = ["\n\n", "\n", "。", "！", "？", ".", "!", "?", " "]
    chunks = []
    remaining = text
    while len(remaining) > 0:
        if len(remaining) <= chunk_size:
            chunk = remaining.strip()
            if len(chunk) > 10:
                chunks.append(chunk)
            break
        split_point = chunk_size
        for sep in separators:
            idx = remaining.rfind(sep, 0, chunk_size)
            if idx >= chunk_size // 2:
                split_point = idx + len(sep)
                break
        chunk = remaining[:split_point].strip()
        if len(chunk) > 10:
            chunks.append(chunk)
        remaining = remaining[max(0, split_point - chunk_overlap):]
    return chunks


def _keyword_score(query: str, text: str) -> float:
    """Compute CJK-aware keyword overlap score using n-gram decomposition."""
    if not query or not text:
        return 0.0
    q_lower = query.lower()
    t_lower = text.lower()
    tokens = []

    def _is_cjk(c: str) -> bool:
        """Check if a character falls within CJK Unified Ideographs or Extension A."""
        return '一' <= c <= '鿿' or '㐀' <= c <= '䶿'

    # Chinese CJK n-grams (2-4 char windows)
    cjk_chars = ''.join(c for c in q_lower if _is_cjk(c))
    for n in (4, 3, 2):
        for i in range(len(cjk_chars) - n + 1):
            tokens.append(cjk_chars[i:i+n])
    # English/number tokens
    eng = [w for w in q_lower.split() if len(w) > 1 and not all(_is_cjk(c) for c in w)]
    tokens.extend(eng)
    # Full query as phrase match
    tokens.append(q_lower)
    unique_t = set(tokens)
    matches = sum(1 for t in unique_t if t in t_lower)
    return matches / len(unique_t) if unique_t else 0.0


# Initialize DB lazily -- use init_db() explicitly from main.py or when run directly.
# Previously called at import-time, which caused side effects for test isolation
# and module reloading.
if __name__ == "__main__":
    init_db()
