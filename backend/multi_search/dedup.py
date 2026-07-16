"""
multi_search/dedup.py — Cross-platform search result deduplication and ranking.

Implements:
  - Title similarity dedup (Levenshtein, Jaccard, n-gram)
  - URL canonicalization dedup
  - Content fingerprint dedup
  - Multi-factor result scoring and re-ranking
"""

from __future__ import annotations

import re
import hashlib
from typing import Any, Dict, List, Optional, Set, Tuple
from urllib.parse import urlparse, parse_qs, urlunparse

from .models import SearchResult, SearchQuery, ResultSource


# ============================================================================
# URL Canonicalization
# ============================================================================

def canonicalize_url(url: str) -> str:
    """Normalize URL for dedup comparison.

    Removes tracking params, fragments, www prefix differences, trailing slash.
    """
    if not url:
        return ""
    parsed = urlparse(url.lower())

    # Normalize host: remove www. and mobile. prefixes
    host = parsed.hostname or ""
    for prefix in ("www.", "m.", "mobile."):
        if host.startswith(prefix):
            host = host[len(prefix):]
            break

    # Normalize path: remove trailing slash (except root)
    path = parsed.path.rstrip("/")
    if not path:
        path = "/"

    # Remove tracking/fragment-related query params
    tracking_params = {
        "utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content",
        "ref", "referrer", "source", "spm", "from", "tracking_id",
        "fbclid", "gclid", "msclkid", "igshid", "mc_cid", "mc_eid",
        "share_id", "share_medium", "share_source", "share_plat",
        "session_id", "timestamp",
    }
    qs = parse_qs(parsed.query, keep_blank_values=True)
    cleaned_qs = {k: v for k, v in qs.items() if k.lower() not in tracking_params}
    query_str = "&".join(f"{k}={v[0]}" for k, v in sorted(cleaned_qs.items())) if cleaned_qs else ""

    return urlunparse((
        parsed.scheme or "https",
        host,
        path,
        "",  # params
        query_str,
        ""   # fragment
    ))


# ============================================================================
# Text Normalization for Similarity
# ============================================================================

def normalize_text(text: str) -> str:
    """Normalize text for similarity comparison.

    - Lowercase
    - Remove special characters (keep Chinese, English, digits)
    - Collapse whitespace
    """
    text = text.lower().strip()
    # Keep Chinese chars, ASCII letters, digits, spaces
    text = re.sub(r'[^\w\s一-鿿]', '', text)
    text = re.sub(r'\s+', ' ', text)
    return text.strip()


# ============================================================================
# Similarity Metrics
# ============================================================================

def levenshtein_ratio(s1: str, s2: str) -> float:
    """Levenshtein-based similarity ratio in [0, 1].

    1.0 = identical, 0.0 = completely different.
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    len_s1, len_s2 = len(s1), len(s2)
    max_len = max(len_s1, len_s2)

    # Optimize: early exit if length difference > 50%
    if min(len_s1, len_s2) / max_len < 0.4:
        return 0.0

    # Create matrix only for the shorter dimension
    prev = list(range(len_s2 + 1))
    for i, c1 in enumerate(s1):
        curr = [i + 1]
        for j, c2 in enumerate(s2):
            # Insertion, deletion, substitution
            cost = 0 if c1 == c2 else 1
            curr.append(min(
                curr[-1] + 1,           # insertion
                prev[j + 1] + 1,        # deletion
                prev[j] + cost          # substitution
            ))
        prev = curr

    distance = prev[-1]
    return 1.0 - (distance / max_len)


def jaccard_similarity(s1: str, s2: str, n: int = 3) -> float:
    """N-gram Jaccard similarity in [0, 1].

    Good for fuzzy matching of Chinese/English text.
    """
    if not s1 and not s2:
        return 1.0
    if not s1 or not s2:
        return 0.0

    def ngrams(text: str, n_size: int) -> Set[str]:
        if len(text) < n_size:
            return {text}
        return {text[i:i + n_size] for i in range(len(text) - n_size + 1)}

    set1 = ngrams(s1, n)
    set2 = ngrams(s2, n)

    if not set1 or not set2:
        return 0.0

    intersection = len(set1 & set2)
    union = len(set1 | set2)
    return intersection / union if union > 0 else 0.0


def content_similarity(r1: SearchResult, r2: SearchResult) -> float:
    """Compute overall content similarity between two results.

    Combines title similarity (weighted) + URL similarity.
    Returns float in [0, 1].
    """
    title1 = normalize_text(r1.title)
    title2 = normalize_text(r2.title)

    # Title similarity: use Jaccard for Chinese, Levenshtein for short strings
    if len(title1) < 20 or len(title2) < 20:
        title_sim = levenshtein_ratio(title1, title2)
    else:
        title_sim = jaccard_similarity(title1, title2, n=3)

    # URL similarity
    url1 = canonicalize_url(r1.url)
    url2 = canonicalize_url(r2.url)
    url_sim = 1.0 if url1 == url2 else 0.0

    # Fingerprint comparison
    fp_sim = 1.0 if r1.similarity_fingerprint() == r2.similarity_fingerprint() else 0.0

    # Weighted combination
    score = title_sim * 0.6 + url_sim * 0.3 + fp_sim * 0.1
    return min(score, 1.0)


# ============================================================================
# Deduplication Engine
# ============================================================================

class ResultDeduplicator:
    """Deduplicates search results across multiple engines.

    Two-pass strategy:
      1. Exact URL dedup (fast, hash-based)
      2. Content similarity dedup (fuzzy, O(n^2) but bounded)
    """

    def __init__(self, threshold: float = 0.75):
        self.threshold = threshold

    def deduplicate(
        self,
        results: List[SearchResult],
        query: Optional[SearchQuery] = None,
    ) -> Tuple[List[SearchResult], int]:
        """Deduplicate results, returning (unique_results, removed_count).

        Args:
            results: Raw results from all engines
            query: Optional query for threshold customization
        """
        threshold = query.dedup_threshold if query else self.threshold
        original_count = len(results)

        if original_count <= 1:
            return results, 0

        # Pass 1: Exact URL canonicalization dedup (fast)
        url_seen: Dict[str, SearchResult] = {}
        url_unique: List[SearchResult] = []
        for r in results:
            canon = canonicalize_url(r.url)
            if canon not in url_seen:
                url_seen[canon] = r
                url_unique.append(r)
            else:
                # Keep the one with higher relevance score
                existing = url_seen[canon]
                if r.relevance_score > existing.relevance_score:
                    # Replace existing with higher-scoring result
                    idx = url_unique.index(existing)
                    url_unique[idx] = r
                    url_seen[canon] = r

        # Pass 2: Content similarity dedup (fuzzy)
        content_unique: List[SearchResult] = []
        removed_by_content = 0
        for i, r in enumerate(url_unique):
            is_dup = False
            for existing in content_unique:
                sim = content_similarity(r, existing)
                if sim >= threshold:
                    # Merge metadata from duplicate into existing
                    self._merge_metadata(existing, r)
                    is_dup = True
                    removed_by_content += 1
                    break
            if not is_dup:
                content_unique.append(r)

        removed_count = original_count - len(content_unique)
        return content_unique, removed_count

    def _merge_metadata(self, target: SearchResult, source: SearchResult):
        """Merge useful metadata from duplicate into the kept result."""
        # Add cross-platform source info
        if "alt_sources" not in target.metadata:
            target.metadata["alt_sources"] = []
        target.metadata["alt_sources"].append({
            "source": source.source.value,
            "engine": source.engine.value,
            "url": source.url,
            "title": source.title,
        })
        # Keep the higher relevance score
        if source.relevance_score > target.relevance_score:
            target.relevance_score = source.relevance_score
        # Merge descriptions if target is empty
        if not target.description and source.description:
            target.description = source.description


# ============================================================================
# Result Scoring and Ranking
# ============================================================================

class ResultRanker:
    """Multi-factor ranking of search results.

    Scoring formula:
      final_score = w1 * relevance_score  (native search engine score)
                  + w2 * quality_score    (view/like count normalization)
                  + w3 * freshness_score  (recency boost)
                  + w4 * diversity_bonus  (source diversity)
                  + w5 * content_depth    (description length, metadata richness)
    """

    def __init__(
        self,
        w_relevance: float = 0.35,
        w_quality: float = 0.25,
        w_freshness: float = 0.15,
        w_diversity: float = 0.10,
        w_depth: float = 0.15,
        recency_days: int = 365,
    ):
        self.w_relevance = w_relevance
        self.w_quality = w_quality
        self.w_freshness = w_freshness
        self.w_diversity = w_diversity
        self.w_depth = w_depth
        self.recency_days = recency_days

    def rank(self, results: List[SearchResult]) -> List[SearchResult]:
        """Score and re-rank results by final_score descending."""
        if not results:
            return results

        # Compute per-factor scores
        for r in results:
            relevance = r.relevance_score

            quality = self._compute_quality(r)

            freshness = self._compute_freshness(r)

            # Diversity bonus computed after we know source counts
            r.final_score = self.w_relevance * relevance
            r.final_score += self.w_quality * quality
            r.final_score += self.w_freshness * freshness

        # Compute diversity bonus across the entire result set
        source_counts = self._count_sources(results)
        total = len(results) or 1
        for r in results:
            source_count = source_counts.get(r.source.value, 0)
            diversity = 1.0 - (source_count / total)
            depth = self._compute_depth(r)
            r.final_score += self.w_diversity * diversity
            r.final_score += self.w_depth * depth

        # Sort by final score descending
        results.sort(key=lambda x: x.final_score, reverse=True)
        return results

    def _compute_quality(self, r: SearchResult) -> float:
        """Normalize engagement metrics to [0, 1]."""
        # Log-scale normalization for view count
        import math
        v_score = 0.0
        if r.view_count > 0:
            v_score = math.log10(r.view_count + 1) / 8.0  # 100M views -> 1.0
        v_score = min(v_score, 1.0)

        l_score = 0.0
        if r.like_count > 0:
            l_score = math.log10(r.like_count + 1) / 6.0  # 1M likes -> 1.0
        l_score = min(l_score, 1.0)

        return v_score * 0.4 + l_score * 0.6

    def _compute_freshness(self, r: SearchResult) -> float:
        """Score based on how recent the content is.

        Returns 1.0 for very recent, decaying to 0.0 after recency_days.
        """
        if not r.published_at:
            return 0.5  # neutral if unknown

        try:
            from datetime import datetime, timezone
            # Parse ISO format
            pub_date = datetime.fromisoformat(r.published_at.replace("Z", "+00:00"))
            now = datetime.now(timezone.utc)
            delta = (now - pub_date).total_seconds()
            max_seconds = self.recency_days * 86400
            return max(0.0, 1.0 - delta / max_seconds)
        except (ValueError, TypeError):
            return 0.5

    def _compute_depth(self, r: SearchResult) -> float:
        """Score based on content richness."""
        desc_len = len(r.description) if r.description else 0
        desc_score = min(desc_len / 500, 1.0)
        has_author = 1.0 if r.author else 0.0
        has_thumbnail = 1.0 if r.thumbnail else 0.0
        has_duration = 1.0 if r.duration > 0 else 0.0
        has_metadata = 1.0 if r.metadata else 0.0
        return desc_score * 0.4 + has_author * 0.15 + has_thumbnail * 0.15 + has_duration * 0.15 + has_metadata * 0.15

    def _count_sources(self, results: List[SearchResult]) -> Dict[str, int]:
        """Count results per source for diversity calculation."""
        counts: Dict[str, int] = {}
        for r in results:
            key = r.source.value
            counts[key] = counts.get(key, 0) + 1
        return counts


__all__ = [
    "canonicalize_url",
    "normalize_text",
    "levenshtein_ratio",
    "jaccard_similarity",
    "content_similarity",
    "ResultDeduplicator",
    "ResultRanker",
]
