"""
BiliSum Auth Router - QR login, cookies, favorites navigation
"""
from fastapi import APIRouter, Query, Request
from fastapi.responses import JSONResponse
import httpx, base64, os, logging
from io import BytesIO
from constants import COOKIE_FILE

router = APIRouter()
logger = logging.getLogger("bilisum.auth")


def _auth_error(message: str, status_code: int = 400) -> JSONResponse:
    """Standardized error response for auth endpoints."""
    return JSONResponse({"success": False, "error": message}, status_code=status_code)


@router.get("/auth/qrcode")
async def auth_qrcode():
    from main import db
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                "https://passport.bilibili.com/x/passport-login/web/qrcode/generate",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
            )
            data = r.json()
            if data.get("code") != 0:
                return _auth_error(data.get("message", "QR code generation failed"))
            qd = data["data"]
            try:
                import qrcode as qr
                qr_img = qr.make(qd["url"])
                buf = BytesIO()
                qr_img.save(buf, format="PNG")
                b64 = base64.b64encode(buf.getvalue()).decode("utf-8")
            except ImportError:
                b64 = ""
            return JSONResponse({
                "success": True,
                "qrcode_key": qd["qrcode_key"],
                "qrcode_url": qd["url"],
                "qrcode_image_base64": f"data:image/png;base64,{b64}"
            })
    except httpx.TimeoutException:
        return _auth_error("B站 API 请求超时，请稍后重试", 504)
    except httpx.HTTPStatusError as e:
        return _auth_error(f"B站 API 返回错误: {e.response.status_code}", 502)
    except Exception as e:
        return _auth_error(f"QR 码生成失败: {str(e)}", 500)


@router.get("/auth/qrcode/poll/{qrcode_key}")
async def auth_poll(qrcode_key: str):
    from main import db
    from bilibili_client import set_cookie
    try:
        async with httpx.AsyncClient(timeout=15) as client:
            r = await client.get(
                f"https://passport.bilibili.com/x/passport-login/web/qrcode/poll?qrcode_key={qrcode_key}",
                headers={"User-Agent": "Mozilla/5.0", "Referer": "https://www.bilibili.com/"}
            )
            data = r.json()
            pc = data.get("data", {}).get("code", -1)
            result = {"success": True, "status": "waiting"}
            if pc == 0:
                result["status"] = "success"
                # httpx: use headers.get_list() to get ALL Set-Cookie headers (B站 sends SESSDATA + bili_jct + DedeUserID separately)
                set_cookie_headers = r.headers.get_list("Set-Cookie")
                if set_cookie_headers:
                    cookies = []
                    for header in set_cookie_headers:
                        # Each header is "KEY=VALUE; Path=/; Domain=...; expires=..."
                        # Take only the first segment (KEY=VALUE) before the first ";"
                        cookie_part = header.split(";")[0].strip()
                        if "=" in cookie_part:
                            cookies.append(cookie_part)
                    if cookies:
                        cookie_str = "; ".join(cookies)
                        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
                            f.write(cookie_str)
                        set_cookie(cookie_str)
                        result["cookies_saved"] = True
                        logger.info("QR login: saved %d cookies", len(cookies))
            elif pc == 86038:
                result["status"] = "expired"
            elif pc == 86090:
                result["status"] = "scanning"
            elif pc == 86101:
                result["status"] = "confirmed"
            return JSONResponse(result)
    except httpx.TimeoutException:
        return _auth_error("B站 API 请求超时，请稍后重试", 504)
    except Exception as e:
        return _auth_error(f"QR 码轮询失败: {str(e)}", 500)


@router.post("/cookies/save")
async def cookies_save(request: Request):
    # [v7.1] POST-only for security; body is JSON with "cookie" field
    try:
        body = await request.json()
        c = body.get("cookie", "")
    except Exception:
        return _auth_error("请求体格式无效，需要 JSON 格式")
    if not c:
        return _auth_error("cookie 字段为空")
    from main import db
    from bilibili_client import set_cookie
    try:
        with open(COOKIE_FILE, "w", encoding="utf-8") as f:
            f.write(c)
        set_cookie(c)
        return JSONResponse({"success": True})
    except PermissionError:
        return _auth_error("无写入权限，无法保存 cookie", 500)
    except OSError as e:
        return _auth_error(f"文件写入失败: {str(e)}", 500)
    except Exception as e:
        return _auth_error(f"cookie 保存失败: {str(e)}", 500)
