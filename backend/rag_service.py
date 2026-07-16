"""
Enhanced RAG Service - ChromaDB + Deterministic Embedding + MMR + Hybrid Search
Based on bilibili-rag architecture, adapted for BiliSum
"""
import os
import re
import hashlib
import time
import logging
from collections import Counter
import numpy as np
from typing import Optional, List, Callable
from langchain_chroma import Chroma
from langchain_openai import ChatOpenAI
from langchain_text_splitters import RecursiveCharacterTextSplitter
from langchain_core.documents import Document
from langchain_core.embeddings import Embeddings
from langchain_core.prompts import ChatPromptTemplate
from langchain_core.output_parsers import StrOutputParser

logger = logging.getLogger("bilisum.rag")


class DeterministicEmbedding(Embeddings):
    """Character n-gram hashing + incremental TF-IDF embeddings (zero network, zero API key).

    Uses sliding n-gram windows (2-4 chars) hashed into 384-dimensional vectors with
    document-frequency weighting. Produces meaningful cosine similarity between related
    texts (e.g., "机器学习" and "深度学习" share common n-grams → ~0.3-0.8 similarity),
    unlike the previous MD5→seed→random-vector approach which gave ~0.0 for all pairs.

    DIM=384 is preserved for backward compatibility with existing ChromaDB collections."""

    DIM = 384

    def __init__(self):
        self._df = {}  # document frequency table (built incrementally)
        self._doc_count = 0

    @staticmethod
    def _extract_ngrams(text: str, n_min: int = 2, n_max: int = 4) -> List[str]:
        """Yield sliding n-gram windows from text."""
        chars = list(text)
        ngrams = []
        for n in range(n_min, n_max + 1):
            for i in range(len(chars) - n + 1):
                ngrams.append("".join(chars[i:i + n]))
        return ngrams

    def _vectorize(self, ngrams: List[str], tf: Counter) -> List[float]:
        """Hash n-grams into a 384-dim vector, weighted by TF-IDF."""
        vec = np.zeros(self.DIM, dtype=np.float64)
        for ng in ngrams:
            idx = int(hashlib.sha256(ng.encode('utf-8')).hexdigest(), 16) % self.DIM
            # TF-IDF weight: tf(ng) * log(N / df(ng))
            df = self._df.get(ng, 1)
            weight = tf.get(ng, 1) * np.log(max(1 + self._doc_count, 1) / max(df, 1))
            vec[idx] += weight
        norm = np.linalg.norm(vec)
        if norm > 0:
            vec = vec / norm
        return vec.tolist()

    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """Build incremental IDF table across all texts, then vectorize each."""
        # First pass: collect n-grams for all docs to build IDF
        all_ngram_sets = []
        for text in texts:
            ngrams = self._extract_ngrams(text)
            # Count unique docs per n-gram for IDF
            for ng in set(ngrams):
                self._df[ng] = self._df.get(ng, 0) + 1
            self._doc_count += 1
            all_ngram_sets.append(ngrams)

        # Second pass: vectorize with TF-IDF weights
        results = []
        for ngrams in all_ngram_sets:
            tf = Counter(ngrams)
            results.append(self._vectorize(ngrams, tf))
        return results

    def embed_query(self, text: str) -> List[float]:
        """Vectorize a query using accumulated IDF table (pure TF if no docs indexed)."""
        ngrams = self._extract_ngrams(text)
        tf = Counter(ngrams)
        return self._vectorize(ngrams, tf)


# Chinese stopwords for keyword extraction
STOPWORDS = set("的了吗呢吧啊嗯哦么着这也把那与其及和或但而因所以如果虽然然而因为但是不过"
                "只是还是然后就是可以可能应该需要已经正在即将之后之前之后并且")


class RAGService:
    def __init__(self, api_key: str = "", api_url: str = "", model: str = "deepseek-chat"):
        self.api_key = api_key
        self.api_url = api_url
        self.model = model
        self.embeddings = self._init_embeddings(api_key, api_url)
        self.collection_name = "bilisum_kb"

        # Text splitter (Chinese-aware)
        self.splitter = RecursiveCharacterTextSplitter(
            chunk_size=1000, chunk_overlap=200,
            separators=["\n\n", "\n", "。", "！", "？", ".", "!", "?", " ", ""]
        )

        # LLM client
        if api_key:
            is_anthropic = "anthropic.com" in (api_url or "")
            if is_anthropic:
                self.llm = None  # Handled via direct httpx calls
            else:
                self.llm = ChatOpenAI(
                    api_key=api_key, base_url=api_url, model=model,
                    temperature=0.5, max_tokens=4096
                )
        else:
            self.llm = None

        # Init ChromaDB with retry + health check
        persist_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "chroma_db")
        os.makedirs(persist_dir, exist_ok=True)
        self.vector_store = self._init_chroma_with_retry(persist_dir)

    def _init_chroma_with_retry(self, persist_dir: str, max_retries: int = 3):
        """Initialize ChromaDB with exponential backoff retry and health check."""
        last_exc = None
        for attempt in range(1, max_retries + 1):
            try:
                # Verify persist directory is writable
                test_file = os.path.join(persist_dir, ".write_test")
                with open(test_file, "w") as f:
                    f.write("test")
                os.remove(test_file)

                vs = Chroma(
                    collection_name=self.collection_name,
                    embedding_function=self.embeddings,
                    persist_directory=persist_dir,
                )
                # Health check: verify collection is accessible
                count = vs._collection.count()
                logger.info(
                    "ChromaDB initialized: collection=%s, persist=%s, docs=%d (attempt %d/%d)",
                    self.collection_name, persist_dir, count, attempt, max_retries,
                )
                return vs
            except Exception as e:
                last_exc = e
                if attempt < max_retries:
                    delay = 1.5 ** attempt
                    logger.warning(
                        "ChromaDB init failed (attempt %d/%d): %s. Retrying in %.1fs...",
                        attempt, max_retries, e, delay,
                    )
                    time.sleep(delay)
                else:
                    logger.error(
                        "ChromaDB init failed after %d attempts: %s. Vector search disabled.",
                        max_retries, e,
                    )
        # Register last exception for diagnostics
        self._chroma_init_error = str(last_exc) if last_exc else "unknown"
        return None

    @staticmethod
    def _init_embeddings(api_key: str, api_url: str) -> Embeddings:
        """Three-tier embedding initialization: API -> HuggingFace -> Deterministic.

        Fixes:
          - Normalize base URL to avoid /v1/v1 double-appending
          - Strip known API path segments (chat/completions, embeddings, etc.)
          - Log each attempt rather than silently falling through
        """
        # Tier 1: Try OpenAI-compatible embeddings API if key is configured
        if api_key:
            try:
                from langchain_openai import OpenAIEmbeddings

                # Normalize base URL -- robust against common misconfigurations
                if api_url:
                    base = api_url.strip().rstrip("/")
                    # Strip known API path segments that are endpoints, not base URLs
                    for suffix in ("/chat/completions", "/completions", "/embeddings",
                                   "/v1/chat/completions", "/v1/embeddings"):
                        if base.endswith(suffix):
                            base = base[:-len(suffix)]
                            break
                    # Ensure base ends with /v1 (OpenAI-compatible convention)
                    if not base.rstrip("/").endswith("/v1"):
                        base = base.rstrip("/") + "/v1"
                else:
                    base = "https://api.openai.com/v1"

                logger.info("Trying OpenAI-compatible embeddings at %s", base)
                emb = OpenAIEmbeddings(
                    model="text-embedding-3-small",
                    openai_api_key=api_key,
                    openai_api_base=base,
                )
                # Quick validation with local cache key to avoid repeated failures
                emb.embed_query("test")
                logger.info("OpenAI-compatible embeddings: OK (%s)", base)
                return emb
            except Exception as e:
                logger.warning("OpenAI-compatible embeddings unavailable: %s", e)
        # Tier 2: Try local HuggingFace sentence-transformers
        os.environ.setdefault("HF_ENDPOINT", "https://hf-mirror.com")
        try:
            from langchain_community.embeddings import HuggingFaceEmbeddings
            from semantic_search import _detect_device
            _device = _detect_device()
            logger.info("Trying HuggingFace embeddings (paraphrase-multilingual-MiniLM-L12-v2)")
            emb = HuggingFaceEmbeddings(
                model_name="sentence-transformers/paraphrase-multilingual-MiniLM-L12-v2",
                model_kwargs={"device": _device},
            )
            emb.embed_query("test")
            logger.info("HuggingFace embeddings: OK")
            return emb
        except Exception as e:
            logger.warning("HuggingFace embeddings unavailable: %s", e)
        # Tier 3: Deterministic fallback (zero API, zero dependency)
        logger.warning("Falling back to DeterministicEmbedding (MD5-hash based, no semantics)")
        return DeterministicEmbedding()

    # ==================== Document Management ====================

    def _build_metadata_doc(self, bvid: str, title: str, author: str, desc: str, duration: int, outline_titles: list) -> Document:
        """Create a compact metadata document for title/author recall"""
        parts = [title]
        if author: parts.append(f"UP主: {author}")
        if desc: parts.append(desc[:200])
        if duration: parts.append(f"时长: {duration // 60}分钟")
        if outline_titles:
            parts.append("章节: " + ", ".join(outline_titles[:8]))
        return Document(
            page_content=" | ".join(parts),
            metadata={"bvid": bvid, "title": title, "doc_type": "metadata", "chunk_index": -1}
        )

    def add_video(self, bvid: str, title: str, text: str, author: str = "", desc: str = "", duration: int = 0, cancel_check: Optional[Callable] = None) -> int:
        """Add video content to vector store"""
        if not self.vector_store:
            return 0

        # Build content with outline awareness
        chunks = self.splitter.split_text(text)
        chunks = [c for c in chunks if len(c) > 5]
        if not chunks:
            return 0

        docs = []
        for i, chunk in enumerate(chunks):
            docs.append(Document(
                page_content=chunk,
                metadata={"bvid": bvid, "title": title, "chunk_index": i, "doc_type": "content",
                          "source": f"https://www.bilibili.com/video/{bvid}"}
            ))

        # Add metadata doc
        docs.insert(0, self._build_metadata_doc(bvid, title, author, desc, duration, []))

        # Batch add with cancel support
        batch_size = 10
        added_ids = []
        for i in range(0, len(docs), batch_size):
            if cancel_check and cancel_check():
                # Rollback: clean up already-added chunks
                if added_ids:
                    try:
                        self.vector_store._collection.delete(ids=added_ids)
                        logger.debug("Cancelled add_video %s, rolled back %d chunks", bvid, len(added_ids))
                    except Exception as e:
                        logger.warning("Cancel rollback failed for %s: %s", bvid, e)
                return 0
            batch = docs[i:i + batch_size]
            ids = [f"{bvid}_{j}" for j in range(i, i + len(batch))]
            try:
                self.vector_store.add_documents(batch, ids=ids)
                added_ids.extend(ids)
            except Exception as e:
                logger.error("add_video batch failed for %s at chunk %d: %s", bvid, i, e)
                if added_ids:
                    try:
                        self.vector_store._collection.delete(ids=added_ids)
                    except Exception as cleanup_e:
                        logger.error("Rollback cleanup failed for %s: %s", bvid, cleanup_e)
                return 0

        logger.info("Added video %s: %d chunks into %s", bvid, len(docs), self.collection_name)
        return len(docs)

    def delete_video(self, bvid: str):
        """Remove all chunks for a video.

        Fix: use _collection.get() instead of vector_store.get() --
        the langchain_chroma Chroma wrapper does not expose get() with where= filter.
        """
        if self.vector_store:
            try:
                result = self.vector_store._collection.get(where={"bvid": bvid})
                if result and result.get("ids"):
                    self.vector_store._collection.delete(ids=result["ids"])
                    logger.debug("Deleted video %s: %d chunks removed", bvid, len(result["ids"]))
            except Exception as e:
                logger.warning("Failed to delete video %s: %s", bvid, e)

    def has_video(self, bvid: str) -> bool:
        if not self.vector_store:
            return False
        try:
            result = self.vector_store._collection.get(where={"bvid": bvid}, limit=1)
            return bool(result and result.get("ids"))
        except Exception as e:
            logger.warning("has_video check failed for %s: %s", bvid, e)
            return False

    # ==================== Search ====================

    def search(self, query: str, k: int = 8, bvids: Optional[List[str]] = None, use_mmr: bool = True) -> List[Document]:
        """MMR vector search with similarity fallback"""
        if not self.vector_store:
            return []

        fetch_k = k * 4
        filter_dict = {"bvid": {"$in": bvids}} if bvids else None

        try:
            if use_mmr:
                return self.vector_store.max_marginal_relevance_search(
                    query, k=k, fetch_k=fetch_k, lambda_mult=0.55, filter=filter_dict
                )
        except Exception as e:
            logger.warning("RAG MMR search failed, falling back to similarity: %s", e)

        try:
            return self.vector_store.similarity_search(query, k=k, filter=filter_dict)
        except Exception as e:
            logger.warning("RAG similarity search failed: %s", e)
            return []

    def get_stats(self) -> dict:
        if not self.vector_store:
            return {"total_chunks": 0, "total_videos": 0}
        try:
            coll = self.vector_store._collection
            count = coll.count()
            # Count unique bvids
            all_data = coll.get(include=["metadatas"])
            bvids = set()
            if all_data and all_data.get("metadatas"):
                for m in all_data["metadatas"]:
                    if m and m.get("bvid"):
                        bvids.add(m["bvid"])
            return {"total_chunks": count, "total_videos": len(bvids)}
        except Exception:
            return {"total_chunks": 0, "total_videos": 0}


# ==================== Hybrid Retrieval (Keyword + Vector RRF) ====================

def extract_keywords(text: str, max_kw: int = 16) -> List[str]:
    """Extract recall keywords with n-gram support (from bilibili-rag)"""
    if not text: return []
    cleaned = text.strip()
    for sw in sorted(STOPWORDS, key=len, reverse=True):
        cleaned = cleaned.replace(sw, " ")
    keywords, seen = [], set()
    def add(t):
        t = t.strip()
        if len(t) < 2 or t in STOPWORDS or t in seen: return
        seen.add(t); keywords.append(t)
    for token in re.findall(r"[A-Za-z][A-Za-z0-9_+.#-]{1,}|[0-9]{2,}", cleaned):
        add(token)
    for chunk in re.findall(r"[一-鿿]{2,}", cleaned):
        add(chunk)
        if len(chunk) > 4:
            for n in (4, 3, 2):
                for i in range(len(chunk) - n + 1):
                    add(chunk[i:i + n])
    return keywords[:max_kw]


def build_snippet(text: str, keywords: list, max_length: int = 700) -> str:
    """Return a compact snippet around the first keyword hit.

    Centers a window of max_length around the earliest keyword occurrence:
    first_hit - max_length/3 to first_hit + 2*max_length/3.
    Uses case-insensitive matching for keywords containing letters,
    exact matching for pure-CJK keywords.

    Source: bilibili-rag/retrieval.py:94-116"""
    value = (text or "").strip()
    if len(value) <= max_length:
        return value

    first_hit = -1
    for keyword in keywords:
        idx = value.lower().find(keyword.lower()) if re.search(r"[A-Za-z]", keyword) else value.find(keyword)
        if idx >= 0 and (first_hit < 0 or idx < first_hit):
            first_hit = idx

    if first_hit < 0:
        return value[:max_length].rstrip() + "..."

    start = max(0, first_hit - max_length // 3)
    end = min(len(value), start + max_length)
    snippet = value[start:end].strip()
    if start > 0:
        snippet = "..." + snippet
    if end < len(value):
        snippet += "..."
    return snippet


def keyword_score_docs(keywords: List[str], docs: List[dict]) -> List[dict]:
    """Score documents by keyword match with field weights — v8.4 enhanced with bilibili-rag count-based scoring.

    Now uses: count(keyword_in_field) * field_weight * keyword_length_weight
    rather than: single-hit boolean weighting.

    Source: bilibili-rag/retrieval.py:60-91"""
    scored = []
    for doc in docs:
        raw_content = doc.get("content") or ""
        title = (doc.get("title") or "").lower()
        content = raw_content.lower()
        author = (doc.get("author") or "").lower()
        desc = (doc.get("desc") or "").lower()

        score = 0.0
        for kw in keywords:
            kw_l = kw.lower()
            w = min(max(len(kw), 2), 8)  # weight proportional to keyword length
            # Count ALL occurrences per field for granular scoring
            if kw_l in title:
                score += title.count(kw_l) * 8.0 * w
            if kw_l in author:
                score += author.count(kw_l) * 5.0 * w
            if kw_l in desc:
                score += desc.count(kw_l) * 3.0 * w
            if kw_l in content:
                score += content.count(kw_l) * 1.0 * w
        if score > 0:
            scored.append({**doc, "score": score, "snippet": build_snippet(raw_content, keywords)})
    scored.sort(key=lambda x: x["score"], reverse=True)
    return scored


def merge_rrf(vector_ranked: List[Document], keyword_ranked: List[dict],
              top_k: int = 8, vec_weight: float = 1.0, kw_weight: float = 0.85,
              rank_constant: int = 60, per_video_limit: int = 2) -> List[dict]:
    """RRF (Reciprocal Rank Fusion) across vector + keyword channels.

    Fix: keyword channel now uses the same key format as the vector channel
    ({bvid}_{chunk_index}) so that the same chunk appearing in both channels
    receives a combined RRF score.
    """
    scores = {}
    docs_map = {}

    # Vector channel
    for rank, doc in enumerate(vector_ranked):
        bvid = doc.metadata.get("bvid", "")
        chunk_index = doc.metadata.get("chunk_index", rank)
        key = f"{bvid}_{chunk_index}"
        scores[key] = vec_weight / (rank_constant + rank + 1)
        docs_map[key] = {
            "content": doc.page_content, "bvid": bvid,
            "title": doc.metadata.get("title", ""), "retrieval_score": scores[key],
            "source": "vector", "url": f"https://www.bilibili.com/video/{bvid}"
        }

    # Keyword channel -- unified key format for cross-channel RRF fusion
    for rank, doc in enumerate(keyword_ranked):
        bvid = doc.get("bvid", "")
        if not bvid:
            continue
        chunk_index = doc.get("chunk_index", rank)
        key = f"{bvid}_{chunk_index}"
        scores[key] = scores.get(key, 0) + kw_weight / (rank_constant + rank + 1)
        if key not in docs_map:
            docs_map[key] = {
                "content": doc.get("content", ""), "bvid": bvid,
                "title": doc.get("title", ""), "retrieval_score": scores[key],
                "source": "keyword", "url": f"https://www.bilibili.com/video/{bvid}"
            }

    # Sort by score, apply per-video limit
    sorted_items = sorted(scores.items(), key=lambda x: x[1], reverse=True)
    result = []
    deferred = []
    video_counts = {}
    for key, score in sorted_items:
        doc = docs_map.get(key)
        if not doc: continue
        bvid = doc["bvid"]
        if video_counts.get(bvid, 0) >= per_video_limit:
            deferred.append((key, score, bvid))
            continue
        video_counts[bvid] = video_counts.get(bvid, 0) + 1
        doc["retrieval_score"] = round(score, 6)
        result.append(doc)

    # v8.4: deferred fallback — fill remaining slots if result insufficient
    if len(result) < top_k and deferred:
        existing_bvids = {d["bvid"] for d in result}
        for key, score, bvid in deferred:
            if bvid in existing_bvids:
                continue
            doc = docs_map.get(key)
            if not doc: continue
            doc["retrieval_score"] = round(score, 6)
            result.append(doc)
            existing_bvids.add(bvid)
            if len(result) >= top_k:
                break

    return result[:top_k]
