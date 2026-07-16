"""
bili_exceptions.py -- BiliSum custom exception hierarchy
14 exception classes, each mapping to a standard HTTP status code + JSON error response.
"""

import time
from typing import Any, Optional

__all__ = [
    "BiliSumException",
    "APIError",
    "AIError",
    "EmbeddingError",
    "SubtitleError",
    "TimeoutError",
    "ValidationError",
    "AuthenticationError",
    "NotFoundError",
    "RateLimitError",
    "DatabaseError",
    "ExportError",
    "ConfigurationError",
    "ServiceUnavailableError",
    "BILI_ERROR_CODE_MAP",
]

# B站 API 常见错误码 -> 中文消息映射
BILI_ERROR_CODE_MAP = {
    -1: "B站 API 请求异常",
    -2: "B站 API 参数错误",
    -3: "B站 API 权限不足",
    -101: "B站账号未登录或登录过期",
    -102: "B站账号被封禁",
    -104: "B站 API 签名校验失败",
    -105: "B站 API 接口不存在",
    -400: "B站 API 请求参数错误",
    -403: "B站 API 访问权限不足",
    -404: "B站视频或资源不存在",
    -412: "B站 API 请求被拦截（风控）",
    -500: "B站 API 服务器内部错误",
    -509: "B站 API 请求过于频繁",
    -616: "B站 API 频率限制",
}


class BiliSumException(Exception):
    """Base class for all BiliSum custom exceptions.

    Attributes:
        message: User-facing error description (Chinese).
        detail: Additional diagnostic information for developers (dict or None).
        http_status: Corresponding HTTP status code.
        error_code: Machine-readable error code (UPPER_SNAKE_CASE).
        timestamp: Unix timestamp when the exception was created.
    """
    http_status: int = 500
    error_code: str = "INTERNAL_ERROR"

    def __init__(
        self,
        message: str = "服务器内部错误",
        detail: Optional[Any] = None,
    ) -> None:
        super().__init__(message)
        self.message = message
        self.detail = detail
        self.timestamp = time.time()

    def __repr__(self) -> str:
        return (
            f"{self.__class__.__name__}(message={self.message!r}, "
            f"error_code={self.error_code!r}, http_status={self.http_status!r})"
        )

    def to_dict(self) -> dict:
        """Serialize this exception as a standardized dict for JSON error responses."""
        result = {
            "code": self.error_code,
            "message": self.message,
            "timestamp": self.timestamp,
        }
        if self.detail is not None:
            result["detail"] = self.detail
        return result


# ==================== API / External Service Errors ====================

class APIError(BiliSumException):
    """Bilibili API call failure (network error, non-zero return code, parse failure, etc.)."""
    http_status = 502
    error_code = "BILI_API_ERROR"

    def __init__(
        self,
        message: str = "B站 API 调用失败",
        detail: Optional[Any] = None,
        bili_code: Optional[int] = None,
    ) -> None:
        super().__init__(message, detail)
        self.bili_code = bili_code

    @classmethod
    def from_bili_code(cls, bili_code: int, detail: Optional[Any] = None) -> "APIError":
        """Factory: create an APIError with a Chinese message resolved from a B站 error code."""
        message = BILI_ERROR_CODE_MAP.get(bili_code, f"B站 API 调用失败 (code={bili_code})")
        return cls(message=message, detail=detail, bili_code=bili_code)


class AIError(BiliSumException):
    """AI model call failure (Anthropic / OpenAI / DeepSeek API returned error)."""
    http_status = 502
    error_code = "AI_API_ERROR"

    def __init__(
        self,
        message: str = "AI 模型调用失败",
        detail: Optional[Any] = None,
        model: Optional[str] = None,
        http_status_code: Optional[int] = None,
    ) -> None:
        super().__init__(message, detail)
        self.model = model
        self.api_http_status = http_status_code


class EmbeddingError(BiliSumException):
    """Embedding computation failure (vectorization service unavailable or returned error)."""
    http_status = 502
    error_code = "EMBEDDING_ERROR"


class SubtitleError(BiliSumException):
    """Subtitle retrieval failure (no subtitles available from any channel or parse failure)."""
    http_status = 404
    error_code = "SUBTITLE_NOT_FOUND"

    def __init__(
        self,
        message: str = "该视频没有可用的字幕",
        detail: Optional[Any] = None,
        bvid: Optional[str] = None,
    ) -> None:
        super().__init__(message, detail)
        self.bvid = bvid


class TimeoutError(BiliSumException):
    """Request timeout (Bilibili API, AI API, RAG service, or download timed out)."""
    http_status = 504
    error_code = "TIMEOUT_ERROR"

    def __init__(
        self,
        message: str = "请求超时，请稍后重试",
        detail: Optional[Any] = None,
        service: Optional[str] = None,
        timeout_seconds: Optional[float] = None,
    ) -> None:
        super().__init__(message, detail)
        self.service = service
        self.timeout_seconds = timeout_seconds


# ==================== Input Validation Errors ====================

class ValidationError(BiliSumException):
    """Input validation failure (invalid BV number, missing parameters, type errors, etc.)."""
    http_status = 400
    error_code = "VALIDATION_ERROR"


class AuthenticationError(BiliSumException):
    """Authentication failure (expired cookie, unconfigured/invalid API Key)."""
    http_status = 401
    error_code = "AUTHENTICATION_ERROR"


# ==================== Resource / State Errors ====================

class NotFoundError(BiliSumException):
    """Requested resource does not exist (video not found, KB entry missing, etc.)."""
    http_status = 404
    error_code = "NOT_FOUND"


class RateLimitError(BiliSumException):
    """Request rate limit exceeded (Bilibili API rate limit, AI API quota exhausted)."""
    http_status = 429
    error_code = "RATE_LIMIT_ERROR"


# ==================== Data / Storage Errors ====================

class DatabaseError(BiliSumException):
    """Database operation failure (SQLite write error, JSON file corruption, etc.)."""
    http_status = 500
    error_code = "DATABASE_ERROR"


class ExportError(BiliSumException):
    """Export failure (Markdown/DOC/SRT/VTT generation error)."""
    http_status = 500
    error_code = "EXPORT_ERROR"


# ==================== Application-Level Errors ====================

class ConfigurationError(BiliSumException):
    """Configuration error (missing required environment variables, invalid config files)."""
    http_status = 500
    error_code = "CONFIGURATION_ERROR"


class ServiceUnavailableError(BiliSumException):
    """External service unavailable (third-party API timeout, network unreachable)."""
    http_status = 503
    error_code = "SERVICE_UNAVAILABLE"
