"""
B站 WBI 签名机制实现
参考 bilibili-rag 项目的 wbi.py
"""
import asyncio
import hashlib
import time
import urllib.parse
import httpx

MIXIN_KEY_ENC_TAB = [
    46, 47, 18, 2, 53, 8, 23, 32, 15, 50, 10, 31, 58, 3, 45, 35,
    27, 43, 5, 49, 33, 9, 42, 19, 29, 28, 14, 39, 12, 38, 41, 13,
    37, 48, 7, 16, 24, 55, 40, 61, 26, 17, 0, 1, 60, 51, 30, 4,
    22, 25, 54, 21, 56, 59, 6, 63, 57, 62, 11, 36, 20, 34, 44, 52
]

_wbi_keys = None
_wbi_last_fetch = 0
_wbi_lock = asyncio.Lock()


def _get_mixin_key(orig: str) -> str:
    return "".join(orig[i] for i in MIXIN_KEY_ENC_TAB)[:32]


async def _fetch_wbi_keys():
    """Fetch WBI img_key and sub_key from B站 nav API (caller must hold _wbi_lock)."""
    global _wbi_keys, _wbi_last_fetch

    async with httpx.AsyncClient(timeout=10) as client:
        r = await client.get(
            "https://api.bilibili.com/x/web-interface/nav",
            headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
        )
        data = r.json()
        wbi_img = data.get("data", {}).get("wbi_img", {})
        img_url = wbi_img.get("img_url", "")
        sub_url = wbi_img.get("sub_url", "")

        # Extract key from URL filename
        img_key = img_url.split("/")[-1].split(".")[0] if img_url else ""
        sub_key = sub_url.split("/")[-1].split(".")[0] if sub_url else ""

        _wbi_keys = (img_key + sub_key)
        _wbi_last_fetch = time.time()
        return _wbi_keys


async def _get_wbi_keys():
    """Return cached WBI keys, refreshing under lock if stale or absent.

    Fast-path: return cached keys without contention when still valid.
    Slow-path: acquire lock, double-check staleness, fetch once.
    """
    global _wbi_keys, _wbi_last_fetch
    now = time.time()
    if _wbi_keys and (now - _wbi_last_fetch) < 3600:
        return _wbi_keys
    async with _wbi_lock:
        # Double-check: another coroutine may have refreshed while we waited
        if _wbi_keys and (time.time() - _wbi_last_fetch) < 3600:
            return _wbi_keys
        return await _fetch_wbi_keys()


async def sign_url(url: str) -> str:
    """对URL进行WBI签名 — 异步版本（在async上下文中可用）"""
    params = await sign_params({})
    if "w_rid" in params and "wts" in params:
        sep = "&" if "?" in url else "?"
        return f"{url}{sep}wts={params['wts']}&w_rid={params['w_rid']}"
    return url


async def sign_params(params: dict) -> dict:
    """对参数字典进行WBI签名"""
    keys = await _get_wbi_keys()
    if not keys:
        return params

    mixin_key = _get_mixin_key(keys)

    # Add timestamp
    params["wts"] = int(time.time())

    # Sort params and remove special chars
    filtered = {k: "".join(ch for ch in str(v) if ch not in "!'()*") for k, v in params.items()}
    sorted_params = sorted(filtered.items(), key=lambda x: x[0])

    # Build query string and sign
    query = urllib.parse.urlencode(sorted_params)
    w_rid = hashlib.md5((query + mixin_key).encode()).hexdigest()

    params["w_rid"] = w_rid
    return params
