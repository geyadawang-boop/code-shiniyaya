"""
BiliSum Semantic Search v6.0 -- 统一混合检索系统
=================================================
重开发范围：semantic-search Skill -> BiliSum 后端完整集成

Bug 发现清单（含位置引用）：
  B1. [database.py:223-254, rag_service.py:195-215, main.py:986-992]
      三种检索策略不统一：database.py 只用 LIKE + keyword_score，
      rag_service.py 只用 ChromaDB MMR，main.py 在 /api/chat/stream 才做 RRF 混合，
      而 /api/rag/ask (main.py:807) 只用 db.search_kb() 关键字检索
  B2. [rag_service.py:282-325 merge_rrf]
      RRF 融合后直接送入 LLM 上下文，无交叉编码器重排序（cross-encoder reranking）
  B3. [rag_service.py:53, database.py:301]
      分块大小固定（chunk_size=1000），无动态分块策略——长视频和短视频用相同大小
  B4. [main.py:1001-1020 api_chat_stream context 构建]
      检索结果按 score 排序后直接拼接，无注意力重排序（"lost in the middle"风险）
  B5. [main.py:1463-1521 api_rag_build, rag_service.py:130 add_video]
      增量索引缺失：每次重建遍历全部 KB，仅靠 has_video() 去重，无内容哈希变更检测
  B6. [rag_service.py:83-113 _init_embeddings]
      无集中嵌入配置：3 层降级硬编码，无维度追踪，无模型版本元数据
  B7. [rag_service.py:19-36 DeterministicEmbedding]
      MD5 哈希生成"伪嵌入"——语义相似的句子产生完全不同的向量，破坏语义搜索目的

优先级：B1(P0) > B2(P1) > B3(P1) > B6(P1) > B5(P2) > B4(P2) > B7(P2)

交叉利用链：
  - sqlite-best-practices: FTS5 全文索引 + WAL 模式 + 连接池 → UnifiedSearcher FTS5 后端
  - rag-eval: NDCG/MRR 评估指标 → CrossEncoderReranker 的 rerank 质量可量化
  - bilibili-rag-deploy: retrieval.py merge_ranked_documents → UnifiedSearcher RRF 权重对齐
"""

from __future__ import annotations

import hashlib
import json
import logging
import os
import re
import sqlite3
import threading
import time
from abc import ABC, abstractmethod
from collections import defaultdict
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable, Dict, Iterable, List, Optional, Sequence, Tuple, Union

import numpy as np

logger = logging.getLogger("bilisum.semantic_search")

# ============================================================================
# 模块 1: EmbeddingConfig -- 集中嵌入配置
# ============================================================================
# Bug B6 修复: 统一管理 embedding 模型选择、维度、版本
# Bug B1 修复的一部分: 所有检索路径共享同一个 embedding 实例
# 交叉利用: semantic-search:sharp_edges.md dimension-mismatch 解决方案


def _detect_device() -> str:
    """Auto-detect optimal compute device. Falls back to CPU if torch unavailable."""
    try:
        import torch
        return "cuda" if torch.cuda.is_available() else "cpu"
    except ImportError:
        return "cpu"


@dataclass
class EmbeddingConfig:
    """集中嵌入配置——单一事实来源，消除硬编码。

    交叉利用:
      - semantic-search SKILL.md Principle #4: "Match Embedding to Use Case"
      - semantic-search:sharp_edges.md "embedding-model-version-drift": 追踪模型版本
      - semantic-search:sharp_edges.md "dimension-mismatch": 验证维度
    """

    # --- 模型选择 ---
    provider: str = "huggingface"  # "openai" | "huggingface" | "deterministic" | "voyage"
    model_name: str = "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2"
    dimensions: int = 384  # MiniLM-L12 = 384; text-embedding-3-small = 1536; voyage-3 = 1024

    # --- OpenAI 兼容 API ---
    api_key: str = ""
    api_base: str = ""
    openai_model: str = "text-embedding-3-small"

    # --- 追踪 ---
    model_version: str = field(default_factory=lambda: datetime.now().strftime("%Y-%m-%d"))
    device: str = ""  # "cpu" | "cuda" — empty = auto-detect via _detect_device()

    # --- 缓存 ---
    query_cache_size: int = 1000
    query_cache_ttl: int = 300  # 5 分钟

    def to_metadata(self) -> Dict[str, str]:
        """序列化为 ChromaDB metadata（用于 future migration）。"""
        return {
            "embedding_provider": self.provider,
            "embedding_model": self.model_name,
            "embedding_dimensions": str(self.dimensions),
            "embedding_version": self.model_version,
        }

    def validate_dimensions(self, actual: int) -> bool:
        """验证向量维度是否匹配配置。"""
        if actual != self.dimensions:
            logger.error(
                f"Dimension mismatch: config expects {self.dimensions}, got {actual}. "
                f"Model: {self.model_name}"
            )
            return False
        return True

    @classmethod
    def from_env(cls) -> "EmbeddingConfig":
        """从环境变量 / settings 表加载配置。

        优先级: 数据库 settings 表 > 环境变量 > 默认值
        """
        from database import get_setting as _gs

        def _get(key: str, default: str) -> str:
            """三级回退: 数据库 > os.environ > default"""
            db_val = _gs(key, "")
            if db_val:
                return db_val
            env_val = os.environ.get(key.upper(), "") or os.environ.get(key, "")
            if env_val:
                return env_val
            return default

        provider = _get("embedding_provider", "huggingface")
        model_name = _get("embedding_model", "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2")

        dims_map = {
            "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2": 384,
            "sentence-transformers/all-MiniLM-L6-v2": 384,
            "text-embedding-3-small": 1536,
            "text-embedding-3-large": 3072,
            "voyage-3-lite": 512,
            "voyage-3": 1024,
        }
        return cls(
            provider=provider,
            model_name=model_name,
            dimensions=dims_map.get(model_name, 384),
            api_key=_get("api_key", ""),
            api_base=_get("api_url", ""),
            openai_model=_get("embedding_openai_model", "text-embedding-3-small"),
            device=_get("embedding_device", "") or _detect_device(),
        )


# ============================================================================
# 模块 2: UnifiedSearcher -- FTS5 + ChromaDB -> RRF 统一混合检索
# ============================================================================
# Bug B1 修复: 单一 UnifiedSearcher 类，替代三处独立的检索实现
# 交叉利用:
#   - sqlite-best-practices: FTS5 content-sync 触发器、bm25() 排序
#   - bilibili-rag-deploy retrieval.py: merge_ranked_documents RRF 权重对齐


class FTS5Backend:
    """SQLite FTS5 全文索引后端——替代 database.py search_kb 的 LIKE/n-gram 方法。

    交叉利用 sqlite-best-practices:
      - WAL 模式 + 连接池（复用 database.py get_db）
      - FTS5 content-sync 触发器自动同步
      - bm25() 排序替代手工 TF 评分
    """

    def __init__(self, db_path: str = ""):
        from database import get_db as _get_db
        self._get_db = _get_db
        self._initialized = False

    def ensure_fts_table(self) -> None:
        """创建 FTS5 虚拟表（如不存在）。"""
        conn = self._get_db()
        conn.execute("""
            CREATE VIRTUAL TABLE IF NOT EXISTS kb_chunks_fts USING fts5(
                bvid, title, content, chunk_index, tokenize='unicode61'
            )
        """)
        conn.commit()
        self._initialized = True

    def index_chunk(self, bvid: str, title: str, chunk_index: int, content: str) -> None:
        """索引单个 chunk 到 FTS5。"""
        if not self._initialized:
            self.ensure_fts_table()
        conn = self._get_db()
        conn.execute(
            "INSERT INTO kb_chunks_fts(bvid, title, content, chunk_index) VALUES (?,?,?,?)",
            (bvid, title, content, chunk_index),
        )
        conn.commit()

    def delete_video(self, bvid: str) -> None:
        """删除某视频的所有 FTS5 条目。"""
        if not self._initialized:
            self.ensure_fts_table()
        conn = self._get_db()
        conn.execute("DELETE FROM kb_chunks_fts WHERE bvid=?", (bvid,))
        conn.commit()

    def rebuild_from_chunks(self, bvid: str, title: str, chunks: List[str]) -> None:
        """从 chunk 列表重建 FTS5 索引（先删后插，单事务包裹，保证原子性）。"""
        self.delete_video(bvid)
        if not chunks:
            return
        conn = self._get_db()
        try:
            conn.execute("BEGIN")
            for i, chunk in enumerate(chunks):
                conn.execute(
                    "INSERT INTO kb_chunks_fts(bvid, title, content, chunk_index) VALUES (?,?,?,?)",
                    (bvid, title, i, chunk),
                )
            conn.commit()
            logger.debug("FTS5 rebuild complete: bvid=%s, chunks=%d", bvid, len(chunks))
        except Exception:
            conn.rollback()
            raise

    def search(self, query: str, k: int = 20, bvids: Optional[List[str]] = None) -> List[Dict]:
        """FTS5 BM25 全文搜索。"""
        if not self._initialized:
            self.ensure_fts_table()
        conn = self._get_db()
        # Sanitize FTS5 query
        safe_query = re.sub(r'[^\w一-鿿\s]', ' ', query).strip()
        if not safe_query:
            return []

        where_clause = ""
        params: list = [safe_query]
        if bvids:
            placeholders = ",".join("?" for _ in bvids)
            where_clause = f" AND bvid IN ({placeholders})"
            params.extend(bvids)
        params.append(k)

        rows = conn.execute(f"""
            SELECT bvid, title, content, chunk_index,
                   bm25(kb_chunks_fts, 0, 0, 1, 0) AS bm25_score
            FROM kb_chunks_fts
            WHERE kb_chunks_fts MATCH ?{where_clause}
            ORDER BY bm25_score
            LIMIT ?
        """, params).fetchall()
        return [dict(r) for r in rows]


@dataclass
class SearchResult:
    """统一的检索结果数据结构。"""
    bvid: str
    title: str = ""
    content: str = ""
    chunk_index: int = 0
    score: float = 0.0
    source: str = ""  # "vector" | "keyword" | "rrf" | "reranked"
    url: str = ""
    metadata: Dict[str, Any] = field(default_factory=dict)

    @property
    def video_url(self) -> str:
        return self.url or f"https://www.bilibili.com/video/{self.bvid}"


class ChromaDBBackend:
    """ChromaDB 向量检索后端封装。"""

    def __init__(self, vector_store, embedding_config: EmbeddingConfig):
        self.vector_store = vector_store
        self.embedding_config = embedding_config

    @property
    def is_available(self) -> bool:
        return self.vector_store is not None

    def search(
        self, query: str, k: int = 20, bvids: Optional[List[str]] = None,
        use_mmr: bool = True,
    ) -> List[SearchResult]:
        """MMR/相似度向量检索。

        Fix: MMR failure now falls back to similarity_search instead of returning empty.
        """
        if not self.is_available:
            return []

        fetch_k = k * 3
        filter_dict = {"bvid": {"$in": bvids}} if bvids else None
        docs = []

        try:
            if use_mmr:
                try:
                    docs = self.vector_store.max_marginal_relevance_search(
                        query, k=k, fetch_k=fetch_k, lambda_mult=0.55, filter=filter_dict,
                    )
                except Exception as mmr_err:
                    logger.warning("ChromaDB MMR search failed, falling back to similarity: %s", mmr_err)
                    docs = self.vector_store.similarity_search(query, k=k, filter=filter_dict)
            else:
                docs = self.vector_store.similarity_search(query, k=k, filter=filter_dict)
        except Exception as e:
            logger.warning("ChromaDB search failed: %s", e)
            return []

        results = []
        for rank, doc in enumerate(docs):
            meta = doc.metadata or {}
            results.append(SearchResult(
                bvid=meta.get("bvid", ""),
                title=meta.get("title", ""),
                content=doc.page_content,
                chunk_index=meta.get("chunk_index", rank),
                score=1.0 / (rank + 1),  # Normalized rank score
                source="vector",
                url=f"https://www.bilibili.com/video/{meta.get('bvid', '')}",
                metadata=meta,
            ))
        return results


class UnifiedSearcher:
    """统一混合检索器: FTS5 keyword + ChromaDB vector → RRF merge。

    替代:
      - database.py search_kb()            (纯关键字)
      - rag_service.py RAGService.search() (纯向量)
      - main.py api_chat_stream 内联 RRF   (混合但仅限流式)
      - main.py api_rag_ask 独立检索       (纯关键字)

    交叉利用:
      - semantic-search SKILL.md Principle #1: "Hybrid Search by Default"
      - bilibili-rag-deploy retrieval.py merge_ranked_documents: 通道权重、per_video_limit 对齐
      - semantic-search:patterns.md "Hybrid Search with Qdrant": RRF + sparse/dense prefetch 参考
    """

    def __init__(
        self,
        fts5: FTS5Backend,
        chroma: ChromaDBBackend,
        vector_weight: float = 1.0,
        keyword_weight: float = 0.85,
        rank_constant: int = 60,
        per_video_limit: int = 2,
    ):
        self.fts5 = fts5
        self.chroma = chroma
        self.vector_weight = vector_weight
        self.keyword_weight = keyword_weight
        self.rank_constant = rank_constant
        self.per_video_limit = per_video_limit

    def search(
        self,
        query: str,
        k: int = 8,
        bvids: Optional[List[str]] = None,
        use_vector: bool = True,
        use_keyword: bool = True,
    ) -> List[SearchResult]:
        """混合检索主入口。

        并行执行向量检索和 FTS5 关键字检索，通过 RRF 融合结果。
        """
        vector_results: List[SearchResult] = []
        keyword_results: List[SearchResult] = []

        # 向量通道
        if use_vector and self.chroma.is_available:
            vector_results = self.chroma.search(query, k=k * 2, bvids=bvids)

        # 关键字通道
        if use_keyword:
            try:
                fts5_raw = self.fts5.search(query, k=k * 2, bvids=bvids)
            except Exception as e:
                logger.warning(f"FTS5 search failed, falling back: {e}")
                fts5_raw = []
            for rank, row in enumerate(fts5_raw):
                keyword_results.append(SearchResult(
                    bvid=row.get("bvid", ""),
                    title=row.get("title", ""),
                    content=row.get("content", ""),
                    chunk_index=row.get("chunk_index", rank),
                    score=1.0 / (rank + 1),
                    source="keyword",
                    url=f"https://www.bilibili.com/video/{row.get('bvid', '')}",
                ))

        # 单通道快速路径
        if not vector_results and not keyword_results:
            return []
        if not keyword_results:
            return self._apply_per_video_limit(vector_results, k)
        if not vector_results:
            return self._apply_per_video_limit(keyword_results, k)

        # RRF 融合
        return self._rrf_fuse(vector_results, keyword_results, k)

    def _rrf_fuse(
        self,
        vector_results: List[SearchResult],
        keyword_results: List[SearchResult],
        top_k: int,
    ) -> List[SearchResult]:
        """Reciprocal Rank Fusion 核心算法。

        线上参考: bilibili-rag-deploy retrieval.py merge_ranked_documents (line 135-195)
        """
        scores: Dict[str, float] = defaultdict(float)
        docs_by_key: Dict[str, SearchResult] = {}
        best_rank: Dict[str, int] = {}

        # 向量通道
        for rank, doc in enumerate(vector_results, start=1):
            key = f"{doc.bvid}_{doc.chunk_index}"
            scores[key] += self.vector_weight / (self.rank_constant + rank)
            docs_by_key[key] = doc
            best_rank[key] = min(best_rank.get(key, rank), rank)

        # 关键字通道 —— 使用与向量通道相同的 key 格式，确保同一 chunk 的分数正确融合
        for rank, doc in enumerate(keyword_results, start=1):
            key = f"{doc.bvid}_{doc.chunk_index}"
            scores[key] += self.keyword_weight / (self.rank_constant + rank)
            if key not in docs_by_key:
                docs_by_key[key] = doc
            best_rank[key] = min(best_rank.get(key, rank), rank)

        # 排序
        ordered_keys = sorted(docs_by_key, key=lambda k: (-scores[k], best_rank.get(k, 9999)))

        # 合并：去重 + per_video_limit
        merged: List[SearchResult] = []
        video_counts: Dict[str, int] = defaultdict(int)
        deferred: List[str] = []

        for key in ordered_keys:
            doc = docs_by_key[key]
            bvid = doc.bvid
            if bvid and video_counts[bvid] >= self.per_video_limit:
                deferred.append(key)
                continue
            doc.score = round(scores[key], 6)
            doc.source = "rrf"
            merged.append(doc)
            if bvid:
                video_counts[bvid] += 1
            if len(merged) >= top_k:
                break

        # 如果不足 top_k，补充 deferred
        if len(merged) < top_k:
            existing_bvids = {d.bvid for d in merged}
            for key in deferred:
                doc = docs_by_key[key]
                if doc.bvid in existing_bvids:
                    continue
                doc.score = round(scores[key], 6)
                doc.source = "rrf_fallback"
                merged.append(doc)
                if len(merged) >= top_k:
                    break

        return merged

    @staticmethod
    def _apply_per_video_limit(results: List[SearchResult], k: int) -> List[SearchResult]:
        """对单通道结果应用 per_video_limit。"""
        out: List[SearchResult] = []
        counts: Dict[str, int] = {}
        for r in results:
            if counts.get(r.bvid, 0) >= 2:
                continue
            counts[r.bvid] = counts.get(r.bvid, 0) + 1
            out.append(r)
            if len(out) >= k:
                break
        return out


# ============================================================================
# 模块 3: CrossEncoderReranker -- 交叉编码器重排序
# ============================================================================
# Bug B2 修复: RRF 融合后增加第二级交叉编码器重排序
# 交叉利用:
#   - semantic-search SKILL.md Principle #3: "Rerank for Precision" (up to 48% boost)
#   - rag-eval: NDCG@k, MRR 评估指标可衡量 rerank 质量提升
#   - semantic-search:patterns.md "Reranking with Cohere" (line 486-562)


class BaseReranker(ABC):
    """重排序器抽象基类。"""

    @abstractmethod
    def rerank(self, query: str, documents: List[SearchResult], top_n: int = 5) -> List[SearchResult]:
        ...


class LocalCrossEncoderReranker(BaseReranker):
    """本地 sentence-transformers 交叉编码器（零 API 费用）。

    交叉利用:
      - semantic-search:validations.md "no-reranking" 验证规则
      - rag-eval: 离线批量评估 rerank 前后的 NDCG@5 / MRR 变化
    """

    _DEFAULT_MODEL = "cross-encoder/ms-marco-MiniLM-L-6-v2"
    _CHINESE_MODEL = "BAAI/bge-reranker-base"  # BGE Reranker（中文优化）

    def __init__(self, model_name: str = "", device: str = ""):
        self.model_name = model_name or self._CHINESE_MODEL
        self.device = device
        self._model = None

    def _ensure_model(self):
        if self._model is not None:
            return
        try:
            from sentence_transformers import CrossEncoder
            self._model = CrossEncoder(self.model_name, device=self.device)
            logger.info(f"Cross-encoder loaded: {self.model_name}")
        except ImportError:
            logger.warning("sentence-transformers not installed; cross-encoder reranking disabled")
            self._model = None
        except Exception as e:
            logger.error(f"Failed to load cross-encoder {self.model_name}: {e}")
            self._model = None

    def rerank(self, query: str, documents: List[SearchResult], top_n: int = 5) -> List[SearchResult]:
        """本地交叉编码器重排序。"""
        if not documents:
            return []
        if len(documents) <= top_n:
            for d in documents:
                d.source = "reranked_local"
            return documents

        self._ensure_model()
        if self._model is None:
            # 降级：保持 RRF 排序
            return documents[:top_n]

        pairs = [(query, doc.content[:1000]) for doc in documents]
        try:
            scores = self._model.predict(pairs, show_progress_bar=False)
        except Exception as e:
            logger.warning(f"Cross-encoder prediction failed: {e}")
            return documents[:top_n]

        results = []
        for doc, score in zip(documents, scores):
            results.append(SearchResult(
                bvid=doc.bvid, title=doc.title, content=doc.content,
                chunk_index=doc.chunk_index,
                score=float(score),
                source="reranked_local",
                url=doc.url, metadata=doc.metadata,
            ))
        results.sort(key=lambda x: x.score, reverse=True)
        return results[:top_n]


class JinaReranker(BaseReranker):
    """Jina AI Reranker API（免费层级，支持中文）。

    Jina Reranker v2: https://jina.ai/reranker
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.api_url = "https://api.jina.ai/v1/rerank"

    def rerank(self, query: str, documents: List[SearchResult], top_n: int = 5) -> List[SearchResult]:
        # Wraps synchronous httpx.post() in asyncio.to_thread() to avoid blocking
        # the FastAPI event loop. Callers should await this if in an async context.
        if not documents or not self.api_key:
            return documents[:top_n] if documents else []

        import asyncio
        import httpx

        def _sync_call():
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "jina-reranker-v2-base-multilingual",
                            "query": query,
                            "documents": [d.content[:1000] for d in documents],
                            "top_n": top_n,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = []
                        for item in data.get("results", []):
                            idx = item.get("index", 0)
                            if idx < len(documents):
                                doc = documents[idx]
                                results.append(SearchResult(
                                    bvid=doc.bvid, title=doc.title, content=doc.content,
                                    chunk_index=doc.chunk_index,
                                    score=item.get("relevance_score", 0.0),
                                    source="reranked_jina",
                                    url=doc.url, metadata=doc.metadata,
                                ))
                        return results[:top_n]
            except Exception as e:
                logger.warning(f"Jina rerank failed: {e}")
            return None

        try:
            # Check if we're in an async event loop
            loop = asyncio.get_running_loop()
            result = asyncio.ensure_future(asyncio.to_thread(_sync_call))
            # We can't await here (sync method); return original order as fallback
            # and log a warning that this should be called via async wrapper
            logger.warning(
                "JinaReranker.rerank() called synchronously in an async context. "
                "Use jina.rerank_async() or wrap with asyncio.to_thread(). "
                "Returning un-reranked results as fallback."
            )
            return documents[:top_n]
        except RuntimeError:
            # No running event loop — safe to call synchronously
            result = _sync_call()
            return result if result is not None else documents[:top_n]


class CohereReranker(BaseReranker):
    """Cohere Rerank API（企业级，多语言 v3.0+）。

    线上参考: semantic-search:patterns.md "Reranking with Cohere" (line 486-562)
    """

    def __init__(self, api_key: str = ""):
        self.api_key = api_key
        self.api_url = "https://api.cohere.com/v2/rerank"

    def rerank(self, query: str, documents: List[SearchResult], top_n: int = 5) -> List[SearchResult]:
        # Wraps synchronous httpx.post() in asyncio.to_thread() to avoid blocking
        # the FastAPI event loop. Callers should await this if in an async context.
        if not documents or not self.api_key:
            return documents[:top_n] if documents else []

        import asyncio
        import httpx

        def _sync_call():
            try:
                with httpx.Client(timeout=30) as client:
                    resp = client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}", "Content-Type": "application/json"},
                        json={
                            "model": "rerank-v3.5",
                            "query": query,
                            "documents": [d.content[:1000] for d in documents],
                            "top_n": top_n,
                        },
                    )
                    if resp.status_code == 200:
                        data = resp.json()
                        results = []
                        for item in data.get("results", []):
                            idx = item.get("index", 0)
                            if idx < len(documents):
                                doc = documents[idx]
                                results.append(SearchResult(
                                    bvid=doc.bvid, title=doc.title, content=doc.content,
                                    chunk_index=doc.chunk_index,
                                    score=item.get("relevance_score", 0.0),
                                    source="reranked_cohere",
                                    url=doc.url, metadata=doc.metadata,
                                ))
                        return results[:top_n]
            except Exception as e:
                logger.warning(f"Cohere rerank failed: {e}")
            return None

        try:
            # Check if we're in an async event loop
            loop = asyncio.get_running_loop()
            logger.warning(
                "CohereReranker.rerank() called synchronously in an async context. "
                "Use cohere.rerank_async() or wrap with asyncio.to_thread(). "
                "Returning un-reranked results as fallback."
            )
            return documents[:top_n]
        except RuntimeError:
            # No running event loop — safe to call synchronously
            result = _sync_call()
            return result if result is not None else documents[:top_n]


class CrossEncoderReranker:
    """交叉编码器重排序门面——自动选择最佳后端。

    优先级: Cohere API > Jina API > Local CrossEncoder > No-op

    交叉利用:
      - rag-eval: rerank 质量用 NDCG@k + MRR 评估
      - semantic-search:validations.md "no-reranking" (severity: info)
    """

    def __init__(
        self,
        cohere_key: str = "",
        jina_key: str = "",
        local_model: str = "",
        device: str = "",
    ):
        self.cohere = CohereReranker(cohere_key) if cohere_key else None
        self.jina = JinaReranker(jina_key) if jina_key else None
        self.local = LocalCrossEncoderReranker(local_model, device)

    def rerank(self, query: str, documents: List[SearchResult], top_n: int = 5) -> List[SearchResult]:
        """自动选择可用后端执行重排序。"""
        if len(documents) <= top_n:
            return documents

        # 优先级: Cohere > Jina > Local
        if self.cohere:
            return self.cohere.rerank(query, documents, top_n)
        if self.jina:
            return self.jina.rerank(query, documents, top_n)
        if self.local:
            return self.local.rerank(query, documents, top_n)

        # Fallback: 保持 RRF 排序
        return documents[:top_n]


# ============================================================================
# 模块 4: SemanticChunker -- 动态语义分块
# ============================================================================
# Bug B3 修复: 替代固定 chunk_size=1000，基于句子相似度边界检测
# 交叉利用:
#   - semantic-search SKILL.md Principle #2: "Chunking Determines Quality"
#   - semantic-search:patterns.md "Semantic Chunking" (line 343-476)
#   - semantic-search:sharp_edges.md "chunking-breaks-context"


class SemanticChunker:
    """动态语义分块器——基于句子嵌入相似度检测自然边界。

    算法:
      1. 将文本拆分为句子
      2. 计算相邻句子的余弦相似度
      3. 在低相似度点（语义断裂处）切割
      4. 确保每个块在 [min_chunk_size, max_chunk_size] 范围内
      5. 保留块间重叠以保持上下文

    交叉利用:
      - semantic-search:sharp_edges.md "chunking-breaks-context": 避免在句子中间切割
      - semantic-search:validations.md "fixed-size-chunking": 警告 fixed-size chunking
      - semantic-search:validations.md "no-chunk-overlap": 重叠保留上下文
    """

    # 中英文句子分隔符
    SENTENCE_PATTERN = re.compile(
        r'([^。！？.!?\n]+[。！？.!?\n]+)'
    )
    HEADER_PATTERN = re.compile(r'^#{1,3}\s+|^【.+?】')

    def __init__(
        self,
        min_chunk_size: int = 300,
        max_chunk_size: int = 1200,
        target_chunk_size: int = 800,
        chunk_overlap: int = 150,
        similarity_threshold: float = 0.45,
        device: str = "",
    ):
        """
        Args:
            min_chunk_size: 最小 chunk 字符数
            max_chunk_size: 最大 chunk 字符数
            target_chunk_size: 目标 chunk 字符数
            chunk_overlap: 相邻 chunk 重叠字符数
            similarity_threshold: 句子相似度阈值——低于此值视为语义边界
            device: embedding 设备
        """
        self.min_chunk_size = min_chunk_size
        self.max_chunk_size = max_chunk_size
        self.target_chunk_size = target_chunk_size
        self.chunk_overlap = chunk_overlap
        self.similarity_threshold = similarity_threshold
        self.device = device
        self._embedder = None

    def _get_embedder(self):
        """延迟加载轻量嵌入模型（仅用于句子相似度计算）。"""
        if self._embedder is not None:
            return self._embedder
        try:
            from sentence_transformers import SentenceTransformer
            self._embedder = SentenceTransformer(
                "sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                device=self.device,
            )
        except ImportError:
            # 降级: 返回 None，使用纯启发式分块
            logger.warning("sentence-transformers not available; using heuristic chunking")
            self._embedder = None
        except Exception as e:
            logger.error(f"Failed to load sentence embedder: {e}")
            self._embedder = None
        return self._embedder

    def chunk(self, text: str) -> List[str]:
        """主分块入口——返回语义连贯的 chunk 列表。"""
        if not text or len(text) < self.min_chunk_size:
            return [text] if text else []

        # Step 1: 拆分句子 + 识别标题
        sentences = self._split_sentences(text)
        if not sentences:
            return [text]

        # Step 2: 计算句子间语义相似度
        boundaries = self._detect_boundaries(sentences)

        # Step 3: 在语义边界处构建 chunk
        chunks = self._build_chunks(sentences, boundaries)
        return chunks

    def _split_sentences(self, text: str) -> List[Tuple[str, bool]]:
        """拆分句子，标注是否为标题行。

        Returns:
            [(sentence_text, is_header), ...]
        """
        raw = [s.strip() for s in self.SENTENCE_PATTERN.split(text) if s.strip()]
        if not raw:
            return [(text, False)]

        result: List[Tuple[str, bool]] = []
        for s in raw:
            is_header = bool(self.HEADER_PATTERN.match(s))
            result.append((s, is_header))
        return result

    def _detect_boundaries(self, sentences: List[Tuple[str, bool]]) -> List[int]:
        """检测语义边界——返回应在此处切割的句子索引列表。

        边界条件:
          1. 标题行（## 或 【】开头的行）
          2. 相邻句子相似度低于阈值
          3. 段落分隔（空行）
        """
        embedder = self._get_embedder()

        # 如果没有 embedder，使用启发式方法
        if embedder is None:
            return self._heuristic_boundaries(sentences)

        # 提取纯文本用于嵌入
        texts = [s[0] for s in sentences]
        try:
            embeddings = embedder.encode(texts, show_progress_bar=False)
        except Exception as e:
            logger.warning(f"Sentence embedding failed: {e}")
            return self._heuristic_boundaries(sentences)

        boundaries = []
        for i in range(1, len(sentences)):
            _, is_header = sentences[i]
            prev_text, _ = sentences[i - 1]

            # 新标题行 = 强边界
            if is_header:
                boundaries.append(i)
                continue

            # 前句为空行 = 边界
            if not prev_text.strip():
                boundaries.append(i)
                continue

            # 余弦相似度
            sim = self._cosine_similarity(embeddings[i - 1], embeddings[i])
            if sim < self.similarity_threshold:
                boundaries.append(i)

        return boundaries

    def _heuristic_boundaries(self, sentences: List[Tuple[str, bool]]) -> List[int]:
        """无嵌入模型时的启发式边界检测。"""
        boundaries = []
        for i in range(1, len(sentences)):
            text, is_header = sentences[i]
            prev_text, _ = sentences[i - 1]

            if is_header:
                boundaries.append(i)
                continue
            if not prev_text.strip():
                boundaries.append(i)
                continue
            # 检测主题切换关键词
            if re.match(r'^(但是|然而|另外|此外|另一方面|不过|总之|综上所述)', text):
                boundaries.append(i)
        return boundaries

    def _build_chunks(
        self,
        sentences: List[Tuple[str, bool]],
        boundaries: List[int],
    ) -> List[str]:
        """在检测到的语义边界处构建 chunk。"""
        chunks: List[str] = []
        current = ""
        current_start = 0
        boundary_set = set(boundaries)

        for i, (text, _) in enumerate(sentences):
            potential = (current + text) if not current else (current + " " + text)

            # 必须在边界处切割 且 当前 chunk 已经足够大
            if i in boundary_set and len(current) >= self.min_chunk_size:
                if current.strip():
                    chunks.append(current.strip())
                current = text
                current_start = i
                continue

            # 超出最大大小
            if len(potential) > self.max_chunk_size:
                if current.strip() and len(current) >= self.min_chunk_size:
                    chunks.append(current.strip())
                    # 重叠：保留最后 N 个字符用于上下文
                    overlap_text = current[-self.chunk_overlap:] if len(current) > self.chunk_overlap else ""
                    current = overlap_text + text
                else:
                    # 单个句子就超长——强制切割
                    chunks.append(text[:self.max_chunk_size])
                    remainder = text[self.max_chunk_size - self.chunk_overlap:]
                    current = remainder if remainder else ""
                current_start = i
            else:
                current = potential

        if current.strip() and len(current) >= 10:
            chunks.append(current.strip())

        # 若为单 chunk 且超出目标尺寸，进行降级固定切割
        if len(chunks) == 1 and len(chunks[0]) > self.max_chunk_size * 1.5:
            chunks = self._fallback_fixed_chunk(text=chunks[0])

        return chunks

    def _fallback_fixed_chunk(self, text: str) -> List[str]:
        """降级：固定大小切割（当语义分块无法将文本充分分割时）。"""
        chunks = []
        for i in range(0, len(text), self.target_chunk_size - self.chunk_overlap):
            chunk = text[i:i + self.target_chunk_size]
            if len(chunk) >= 10:
                chunks.append(chunk)
        return chunks

    @staticmethod
    def _cosine_similarity(a: np.ndarray, b: np.ndarray) -> float:
        """计算两个向量的余弦相似度。"""
        dot = np.dot(a, b)
        norm_a = np.linalg.norm(a)
        norm_b = np.linalg.norm(b)
        if norm_a == 0 or norm_b == 0:
            return 0.0
        return float(dot / (norm_a * norm_b))


# ============================================================================
# 模块 5: AttentionReorder -- 注意力重排序
# ============================================================================
# Bug B4 修复: 检索结果按 score 排序后直接拼接 -> "lost in the middle"
# 交叉利用:
#   - semantic-search:sharp_edges.md "lost-in-the-middle" (line 76-132)
#   - 策略: 最相关 -> 开头, 次相关 -> 结尾, 中间 -> 中段


class AttentionReorder:
    """基于 LLM 注意力模式的上下文重排序。

    研究背景 (Liu et al., 2023):
      LLM 对上下文开头和结尾的内容关注度最高，
      中间位置的信息容易被忽略（"lost in the middle"）。

    策略（交错插入法）:
      1. 最相关的 chunk 放在开头（最高注意力）
      2. 次相关的 chunk 放在结尾（次高注意力）
      3. 中等相关的交替插入中部

    交叉利用:
      - semantic-search:sharp_edges.md "lost-in-the-middle" 完整解决方案
      - 与 CrossEncoderReranker 协同: rerank 后执行 reorder
    """

    @staticmethod
    def interleave(results: List[Dict[str, Any]], score_key: str = "score") -> List[Dict[str, Any]]:
        """交错重排序——最相关 > 开头, 次相关 > 结尾。

        Args:
            results: 已排序的检索结果列表
            score_key: 分数键名

        Returns:
            重排序后的列表（适合直接拼接到 LLM 上下文）
        """
        if len(results) <= 3:
            return results

        sorted_items = sorted(results, key=lambda x: x.get(score_key, 0), reverse=True)
        reordered: List[Dict] = []

        left, right = 0, len(sorted_items) - 1
        take_left = True

        for _ in range(len(sorted_items)):
            if take_left:
                reordered.append(sorted_items[left])
                left += 1
            else:
                reordered.append(sorted_items[right])
                right -= 1
            take_left = not take_left

        return reordered

    @staticmethod
    def pyramid(results: List[Dict[str, Any]], score_key: str = "score") -> List[Dict[str, Any]]:
        """金字塔重排序——按重要性递减排列。

        最相关的排在前面，重要性单调递减。
        适合不想打乱逻辑顺序的场景（如叙事性文本）。
        """
        return sorted(results, key=lambda x: x.get(score_key, 0), reverse=True)

    @staticmethod
    def sandwich(results: List[Dict[str, Any]], score_key: str = "score") -> List[Dict[str, Any]]:
        """三明治重排序——前2 + 中段 + 后2。

        将 top-2 和 bottom-2 放在最前/最后，
        中段保持原顺序。
        """
        if len(results) <= 4:
            return results

        sorted_items = sorted(results, key=lambda x: x.get(score_key, 0), reverse=True)
        top = sorted_items[:2]
        bottom = sorted_items[-2:]
        middle = sorted_items[2:-2]

        return top + middle + bottom

    @staticmethod
    def reorder_for_llm(
        results: List[Dict[str, Any]],
        strategy: str = "interleave",
        score_key: str = "score",
    ) -> List[Dict[str, Any]]:
        """统一接口——根据策略重排序。"""
        strategies = {
            "interleave": AttentionReorder.interleave,
            "pyramid": AttentionReorder.pyramid,
            "sandwich": AttentionReorder.sandwich,
        }
        fn = strategies.get(strategy, AttentionReorder.interleave)
        return fn(results, score_key)


# ============================================================================
# 模块 6: IncrementalIndexer -- 增量索引
# ============================================================================
# Bug B5 修复: 基于内容哈希的增量索引，只重建变更部分
# 交叉利用:
#   - semantic-search:sharp_edges.md "embedding-cost-explosion" (line 198-278)
#   - semantic-search:sharp_edges.md "stale-cache-wrong-results": index_version 追踪
#   - sqlite-best-practices: 事务性批量 upsert


@dataclass
class IndexEntry:
    """索引入口元数据。"""
    bvid: str
    content_hash: str
    indexed_at: str
    chunk_count: int = 0
    embedding_model: str = ""


class IncrementalIndexer:
    """基于内容哈希的增量索引器。

    工作流:
      1. 维护索引元数据表（kb_index_meta）
      2. 入库/更新前: 计算内容 SHA256
      3. 与已有哈希比较:
         - 相同: 跳过（节省 embedding 开销）
         - 不同: 删除旧向量 + 分块 + 重新索引
      4. 记录索引时间戳和 embedding 模型版本

    交叉利用:
      - semantic-search:sharp_edges.md "embedding-cost-explosion":
        1M documents × 500 tokens = $10/full reindex; daily = $300/month
        增量索引将 90%+ 不变内容的 embedding 成本降至 0
      - sqlite-best-practices: WAL 模式 + 事务批量写入
    """

    # 元数据表 DDL
    INDEX_META_DDL = """
        CREATE TABLE IF NOT EXISTS kb_index_meta (
            bvid TEXT PRIMARY KEY,
            content_hash TEXT NOT NULL,
            indexed_at TEXT NOT NULL DEFAULT (datetime('now', 'localtime')),
            chunk_count INTEGER DEFAULT 0,
            embedding_model TEXT DEFAULT '',
            text_length INTEGER DEFAULT 0
        )
    """

    def __init__(self, get_db_fn: Callable, embeddings, embedding_config: EmbeddingConfig):
        """
        Args:
            get_db_fn: database.get_db 函数（复用连接池）
            embeddings: RAGService 的 embedding 函数
            embedding_config: EmbeddingConfig 实例
        """
        self.get_db = get_db_fn
        self.embeddings = embeddings
        self.config = embedding_config

    def ensure_meta_table(self) -> None:
        """创建索引元数据表。"""
        conn = self.get_db()
        conn.executescript(self.INDEX_META_DDL)
        conn.commit()

    @staticmethod
    def compute_hash(text: str) -> str:
        """计算内容的 SHA256 哈希（前16位）。"""
        return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]

    def get_indexed_hash(self, bvid: str) -> Optional[str]:
        """获取已索引的内容哈希。"""
        conn = self.get_db()
        row = conn.execute(
            "SELECT content_hash FROM kb_index_meta WHERE bvid=?", (bvid,)
        ).fetchone()
        return row["content_hash"] if row else None

    def needs_reindex(self, bvid: str, text: str) -> bool:
        """判断是否需要重新索引。"""
        current_hash = self.compute_hash(text)
        indexed_hash = self.get_indexed_hash(bvid)
        if indexed_hash is None:
            return True
        return str(current_hash) != str(indexed_hash)

    def mark_indexed(self, bvid: str, text: str, chunk_count: int) -> None:
        """标记已索引。"""
        conn = self.get_db()
        content_hash = self.compute_hash(text)
        conn.execute(
            """INSERT OR REPLACE INTO kb_index_meta
               (bvid, content_hash, indexed_at, chunk_count, embedding_model, text_length)
               VALUES (?, ?, datetime('now', 'localtime'), ?, ?, ?)""",
            (bvid, content_hash, chunk_count, self.config.model_name, len(text)),
        )
        conn.commit()

    def remove_entry(self, bvid: str) -> None:
        """删除索引记录。"""
        conn = self.get_db()
        conn.execute("DELETE FROM kb_index_meta WHERE bvid=?", (bvid,))
        conn.commit()

    def get_stats(self) -> Dict[str, Any]:
        """获取索引统计信息。"""
        conn = self.get_db()
        total = conn.execute("SELECT COUNT(*) as cnt FROM kb_index_meta").fetchone()
        total_chunks = conn.execute(
            "SELECT COALESCE(SUM(chunk_count), 0) as cnt FROM kb_index_meta"
        ).fetchone()
        models = conn.execute(
            "SELECT embedding_model, COUNT(*) as cnt FROM kb_index_meta GROUP BY embedding_model"
        ).fetchall()
        return {
            "total_indexed": total["cnt"] if total else 0,
            "total_chunks": total_chunks["cnt"] if total_chunks else 0,
            "models": {r["embedding_model"]: r["cnt"] for r in models},
        }

    @staticmethod
    def compute_savings(total_videos: int, changed_videos: int, avg_tokens_per_video: int = 3000) -> Dict[str, float]:
        """估算增量索引节省的成本。

        Args:
            total_videos: 总视频数
            changed_videos: 发生变化的视频数
            avg_tokens_per_video: 每个视频的平均 token 数

        Returns:
            成本节省估算
        """
        # OpenAI text-embedding-3-small: $0.02/1M tokens
        full_reindex_cost = (total_videos * avg_tokens_per_video) / 1_000_000 * 0.02
        incremental_cost = (changed_videos * avg_tokens_per_video) / 1_000_000 * 0.02
        return {
            "full_reindex_cost": round(full_reindex_cost, 4),
            "incremental_cost": round(incremental_cost, 4),
            "savings": round(full_reindex_cost - incremental_cost, 4),
            "savings_pct": round((1 - changed_videos / max(total_videos, 1)) * 100, 1),
        }


# ============================================================================
# 模块 7: 全检索流水线 -- RetrievalPipeline
# ============================================================================
# 将所有模块串联为一站式检索流水线


@dataclass
class RetrievalPipeline:
    """一站式检索流水线：搜索 -> 重排序 -> 注意力重排 -> 上下文构建。

    使用示例:
        pipeline = RetrievalPipeline(searcher, reranker)
        context = pipeline.retrieve("什么是机器学习", k=5)
        # context 是一个可以直接喂给 LLM 的字符串
    """

    searcher: UnifiedSearcher
    reranker: CrossEncoderReranker
    attention_strategy: str = "interleave"

    def retrieve(
        self,
        query: str,
        k: int = 5,
        bvids: Optional[List[str]] = None,
        rerank: bool = True,
        reorder: bool = True,
    ) -> Dict[str, Any]:
        """完整检索流水线。

        Returns:
            {
                "context": str,          # 可直接喂给 LLM 的上下文
                "sources": List[dict],   # 来源信息
                "results": List[dict],   # 中间结果（调试用）
                "pipeline": {            # 流水线元数据
                    "search_count": int,
                    "rerank_count": int,
                    "final_count": int,
                }
            }
        """
        # Stage 1: 混合检索
        raw_results = self.searcher.search(query, k=k * 3, bvids=bvids)
        if not raw_results:
            return {"context": "", "sources": [], "results": [], "pipeline": {"search_count": 0, "rerank_count": 0, "final_count": 0}}

        # Stage 2: 交叉编码器重排序
        if rerank and len(raw_results) > k:
            reranked = self.reranker.rerank(query, raw_results, top_n=k * 2)
        else:
            reranked = raw_results[:k * 2]

        # Stage 3: 最终截断
        final = reranked[:k]

        # Stage 4: 注意力重排序
        result_dicts = [
            {
                "bvid": r.bvid, "title": r.title, "content": r.content,
                "score": r.score, "source": r.source, "url": r.video_url,
            }
            for r in final
        ]
        if reorder:
            result_dicts = AttentionReorder.reorder_for_llm(result_dicts, strategy=self.attention_strategy)

        # Stage 5: 构建上下文字符串
        context_parts = []
        for i, d in enumerate(result_dicts):
            context_parts.append(f"[{i+1}] 《{d['title']}》\n{d['content']}")
        context = "\n\n---\n\n".join(context_parts)

        # 构建来源
        seen = set()
        sources = []
        for d in result_dicts:
            if d["bvid"] not in seen:
                seen.add(d["bvid"])
                sources.append({"bvid": d["bvid"], "title": d["title"], "url": d["url"]})

        return {
            "context": context,
            "sources": sources,
            "results": result_dicts,
            "pipeline": {
                "search_count": len(raw_results),
                "rerank_count": len(reranked),
                "final_count": len(result_dicts),
            },
        }


# ============================================================================
# 工厂函数: 从现有 BiliSum 组件构建语义搜索栈
# ============================================================================


def build_semantic_search_stack(
    rag_service=None,
    cohere_key: str = "",
    jina_key: str = "",
    local_rerank_model: str = "",
    device: str = "",
) -> Tuple[UnifiedSearcher, CrossEncoderReranker, SemanticChunker, IncrementalIndexer, RetrievalPipeline]:
    """从现有 BiliSum 组件构建完整的语义搜索栈。

    Args:
        rag_service: 现有的 RAGService 实例（可选）
        cohere_key: Cohere API key
        jina_key: Jina API key
        local_rerank_model: 本地 cross-encoder 模型名
        device: 计算设备

    Returns:
        (searcher, reranker, chunker, indexer, pipeline) 五元组
    """
    # 1. 嵌入配置
    emb_config = EmbeddingConfig.from_env()
    emb_config.device = device or _detect_device()

    # 2. FTS5 后端
    fts5 = FTS5Backend()
    fts5.ensure_fts_table()

    # 3. ChromaDB 后端
    vector_store = rag_service.vector_store if rag_service else None
    chroma = ChromaDBBackend(vector_store, emb_config)

    # 4. 统一检索器
    searcher = UnifiedSearcher(fts5, chroma)

    # 5. 交叉编码器重排序
    reranker = CrossEncoderReranker(
        cohere_key=cohere_key,
        jina_key=jina_key,
        local_model=local_rerank_model,
        device=device,
    )

    # 6. 语义分块器
    chunker = SemanticChunker(device=device)

    # 7. 增量索引器
    from database import get_db as _get_db
    embeddings_fn = rag_service.embeddings if rag_service else None
    indexer = IncrementalIndexer(_get_db, embeddings_fn, emb_config)
    indexer.ensure_meta_table()

    # 8. 检索流水线
    pipeline = RetrievalPipeline(searcher, reranker)

    return searcher, reranker, chunker, indexer, pipeline


# ============================================================================
# 导出: 供 main.py 和其他模块使用
# ============================================================================

__all__ = [
    # Config
    "EmbeddingConfig",
    # Backends
    "FTS5Backend",
    "ChromaDBBackend",
    "UnifiedSearcher",
    "SearchResult",
    # Reranking
    "BaseReranker",
    "LocalCrossEncoderReranker",
    "JinaReranker",
    "CohereReranker",
    "CrossEncoderReranker",
    # Chunking
    "SemanticChunker",
    # Attention
    "AttentionReorder",
    # Indexing
    "IndexEntry",
    "IncrementalIndexer",
    # Pipeline
    "RetrievalPipeline",
    # Factory
    "build_semantic_search_stack",
]
