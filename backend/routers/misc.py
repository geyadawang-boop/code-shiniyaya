"""Router: B站 proxy and ASR"""
import os
import json
import httpx
import asyncio
import logging
from fastapi import APIRouter, Query, Request, HTTPException
from fastapi.responses import JSONResponse, Response
from constants import COOKIE_FILE, FRONTEND_DIR

router = APIRouter(tags=["proxy_asr"])

logger = logging.getLogger("bilisum.misc")


# ---- B站 Proxy ----

@router.get("/bili/proxy")
async def bili_proxy(url: str = Query("https://www.bilibili.com/")):
    # SSRF protection: validate host is EXACTLY *.bilibili.com, block private IPs,
    # block dangerous schemes, block userinfo (user:pass@host) in URL.
    import re as _re
    from urllib.parse import urlparse as _urlparse
    import ipaddress as _ipaddress

    ALLOWED_SCHEMES = {"http", "https"}
    try:
        parsed = _urlparse(url or "")
        scheme = (parsed.scheme or "").lower()
        if scheme not in ALLOWED_SCHEMES:
            raise HTTPException(status_code=400, detail=f"Proxied URL scheme '{scheme}' is not allowed")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid proxy URL")

    try:
        host = (parsed.hostname or "").lower()
        if not host:
            raise HTTPException(status_code=400, detail="No hostname in proxy URL")
        # Must be exactly "bilibili.com" or label exactly ".bilibili.com"
        if host != "bilibili.com" and not host.endswith(".bilibili.com"):
            raise HTTPException(status_code=400, detail=f"Proxied URL host must be bilibili.com, got: {host}")
        # Block multi-label prefixes (evil.bilibili.com.attacker.com would have .attacker.com suffix but not pass endswith)
        if host.endswith(".bilibili.com"):
            prefix = host[:-len(".bilibili.com")]
            if "." in prefix:
                raise HTTPException(status_code=400, detail=f"Proxied URL host must be bilibili.com, got: {host}")
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=400, detail="Only bilibili.com URLs are allowed via proxy")

    # Block private/internal IPs (DNS rebinding defense)
    try:
        import asyncio as _asyncio
        resolved = await _asyncio.get_running_loop().run_in_executor(
            None, lambda: __import__('socket').getaddrinfo(host, None, proto=__import__('socket').IPPROTO_TCP)
        )
        for _, _, _, _, sockaddr in resolved:
            ip_str = sockaddr[0]
            try:
                ip = _ipaddress.ip_address(ip_str)
                if ip.is_loopback or ip.is_private or ip.is_link_local or ip.is_multicast or ip.is_unspecified:
                    raise HTTPException(status_code=400, detail=f"IP address {ip_str} is in a blocked range")
            except ValueError:
                pass
    except HTTPException:
        raise
    except Exception as e:
        logger.warning("SSRF DNS resolution failed for host=%s: %s", host, e, exc_info=True)
        raise HTTPException(status_code=400, detail=f"DNS resolution failed for host: {host}")

    # Block userinfo in URL
    if parsed.username or parsed.password:
        raise HTTPException(status_code=400, detail="Credentials in proxy URL are not allowed")
    try:
        # v8.5: Cookie priority — in-memory first (set via QR login), then file fallback
        headers = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
                   "Referer": "https://www.bilibili.com/",
                   "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
                   "Accept-Encoding": "gzip, deflate"}
        # Priority: in-memory cookie (QR login) > file cookie
        try:
            from bilibili_client import _get_headers as _bili_h
            bh = _bili_h()
            if bh.get("Cookie"):
                headers["Cookie"] = bh["Cookie"]
        except Exception:
            pass
        if not headers.get("Cookie"):
            try:
                if os.path.exists(COOKIE_FILE):
                    with open(COOKIE_FILE, "r", encoding="utf-8") as _ckf:
                        ck = _ckf.read().strip()
                    if ck: headers["Cookie"] = ck
            except OSError:
                pass

        # v8.5: Reuse shared httpx client (connection pooling, ~200ms faster than new client per request)
        from bilibili_client import _get_client as _get_shared_client
        client = await _get_shared_client()
        resp = None
        for attempt in range(3):
            try:
                resp = await client.get(url, headers=headers, follow_redirects=True)
                if resp.status_code == 200:
                    break
            except (httpx.TimeoutException, httpx.ReadError, httpx.ConnectError):
                if attempt < 2:
                    await asyncio.sleep(1.0 * (attempt + 1))
                    continue
                raise
        if resp is None:
            raise HTTPException(status_code=504, detail="B站页面加载超时，请刷新重试")
        html = resp.text
        bv_match = _re.search(r"BV[a-zA-Z0-9]+", url)
        bvid = bv_match.group(0) if bv_match else ""
        html = html.replace("<head>", '<head><base href="https://www.bilibili.com/">')
        inject_script = ""
        if "bilibili" in url.lower():
            summary_btn = f'<a href="http://127.0.0.1:8000/summary?bvid={bvid}" style="padding:4px 14px;background:#fff;color:#e54980;border-radius:12px;text-decoration:none;font-weight:bold;font-size:12px">进入总结 →</a>' if bvid else '<a href="#" style="padding:4px 14px;background:#fff;color:#e54980;border-radius:12px;text-decoration:none;font-weight:bold;font-size:12px;pointer-events:none;opacity:0.6" title="请在B站视频页面使用总结功能">进入总结 →</a>'
            inject_script = (
                # Toolbar + <a> click interception
                '<script>(function(){'
                'if(document.getElementById("bili-inject-bar"))return;'
                'document.addEventListener("click",function(e){'
                'var a=e.target.closest("a");if(!a)return;'
                'var h=a.getAttribute("href");if(!h||h.indexOf("#")===0||h.indexOf("javascript:")===0)return;'
                'if(h.indexOf("//")===0||h.indexOf("http")===0){'
                'e.preventDefault();'
                'var fullUrl=(h.indexOf("//")===0)?"https:"+h:h;'
                'window.location.href="http://127.0.0.1:8000/bili/proxy?url="+encodeURIComponent(fullUrl);return false'
                '}},true);'
                'var bar=document.createElement("div");bar.id="bili-inject-bar";'
                'bar.style.cssText="position:fixed;top:0;left:0;right:0;z-index:999999;background:linear-gradient(135deg,#fb7299,#e54980);padding:8px 16px;display:flex;align-items:center;justify-content:space-between;color:#fff;font-size:13px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3)";'
                'bar.innerHTML=' + json.dumps(
                    '<span style="font-weight:bold;font-size:14px">📺 B站客户端</span><span style="display:flex;gap:6px;align-items:center">'
                    '<a href="http://127.0.0.1:8000/browse" style="padding:5px 12px;background:rgba(255,255,255,0.2);color:#fff;border-radius:16px;text-decoration:none;font-size:12px">🏠 返回BiliSum</a>'
                    '<a href="http://127.0.0.1:8000/bili/proxy?url=https://www.bilibili.com" style="padding:5px 12px;background:rgba(255,255,255,0.15);color:#fff;border-radius:16px;text-decoration:none;font-size:12px">🔗 内嵌B站</a>'
                    + summary_btn +
                    '</span>'
                ) + ';'
                'document.body.insertBefore(bar,document.body.firstChild);'
                'document.body.style.paddingTop="46px";'
                '})();</script>'
            )
        html = html.replace("</body>", inject_script + "</body>")
        # Let B站 set its own CSP/X-Frame-Options. Don't override.
        # B站 does NOT send X-Frame-Options, so iframe embedding works.
        proxy_headers = {}
        # Forward B站 Set-Cookie headers from the proxied response
        set_cookie_vals = resp.headers.get_list("set-cookie")
        if set_cookie_vals:
            proxy_headers["Set-Cookie"] = "; ".join(
                h.split(";")[0].strip() for h in set_cookie_vals if "=" in h
            )
        return Response(content=html, media_type="text/html; charset=utf-8",
                        headers=proxy_headers)
    except Exception as e:
        from fastapi import HTTPException
        raise HTTPException(status_code=500, detail=f"Proxy error: {str(e)}")


# ---- B站 API proxy-fetch (POST body passes target URL to avoid query-param corruption) ----

@router.api_route("/api/bili/proxy-fetch", methods=["GET", "POST", "PUT", "DELETE", "PATCH", "OPTIONS"])
async def bili_proxy_fetch(request: Request):
    """Proxy B站 API fetch/XHR requests from injected script.

    v8.5 rewrite: The injected JS now POSTs a JSON body {url, method, headers, body}
    instead of passing the target URL as a query parameter. This fixes the critical
    bug where encodeURIComponent'd query params were eaten by Starlette's parser.

    Supports GET fallback (?url=...) for backward compatibility.
    """
    import urllib.parse as _up
    import json as _json

    # Handle CORS preflight
    if request.method.upper() == "OPTIONS":
        return Response(status_code=204, headers={
            "Access-Control-Allow-Origin": "*",
            "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
            "Access-Control-Allow-Headers": "*",
        })

    target_url = ""
    target_method = "GET"
    target_headers = {}
    target_body = None

    # v8.5: Primary path — JSON body with {url, method, headers, body}
    if request.method.upper() == "POST":
        try:
            payload = await request.json()
            target_url = payload.get("url", "")
            target_method = (payload.get("method") or "GET").upper()
            target_headers = payload.get("headers") or {}
            target_body = (payload.get("body") or "").encode("utf-8") if payload.get("body") else None
        except Exception:
            pass

    # Fallback: GET with ?url= query param
    if not target_url:
        target_url = request.query_params.get("url", "")

    if not target_url:
        raise HTTPException(status_code=400, detail="Missing url parameter")

    # Validate target host (*.bilibili.com, *.hdslb.com, *.biliapi.net)
    parsed = _up.urlparse(target_url)
    host = (parsed.hostname or "").lower()
    valid_hosts = ("bilibili.com", "hdslb.com", "biliapi.net")
    if not any(host == vh or host.endswith("." + vh) for vh in valid_hosts):
        raise HTTPException(status_code=400, detail=f"Blocked host: {host}")
    # Block multi-label prefix attack
    for vh in valid_hosts:
        if host.endswith("." + vh):
            prefix = host[:-len("." + vh)]
            if "." in prefix:
                raise HTTPException(status_code=400, detail=f"Blocked host: {host}")

    # Build forward headers
    forward_headers = dict(target_headers)  # preserve forwarded headers from original request
    for h in ("accept", "accept-language", "content-type", "origin", "referer"):
        v = request.headers.get(h)
        if v:
            forward_headers[h] = v
    forward_headers["user-agent"] = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
    forward_headers["referer"] = forward_headers.get("referer", "https://www.bilibili.com/")

    # Add B站 cookie
    try:
        from bilibili_client import _get_headers as _bili_headers
        bili_h = _bili_headers()
        if bili_h.get("Cookie"):
            forward_headers["cookie"] = bili_h["Cookie"]
    except Exception:
        pass

    # v8.5: Reuse shared client (connection pooling, ~30-80ms saved per call)
    try:
        from bilibili_client import _get_client as _get_shared_client
        client = await _get_shared_client()
    except Exception:
        client = httpx.AsyncClient(timeout=30)

    try:
        resp = await client.request(
            target_method, target_url,
            headers=forward_headers,
            content=target_body,
        )
    except (httpx.TimeoutException, httpx.ConnectError) as e:
        raise HTTPException(status_code=504, detail=f"B站 API 超时: {str(e)[:200]}")
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"代理请求失败: {str(e)[:200]}")

    proxy_resp_headers = {
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Methods": "GET, POST, PUT, DELETE, PATCH, OPTIONS",
        "Access-Control-Allow-Headers": "*",
        "Content-Type": resp.headers.get("content-type", "application/json"),
    }
    # Forward B站 Set-Cookie (one header per cookie, properly split on comma)
    set_cookie_vals = resp.headers.get_list("set-cookie")
    if set_cookie_vals:
        for h in set_cookie_vals:
            if "=" in h:
                proxy_resp_headers["Set-Cookie"] = h.split(";")[0].strip()

    return Response(
        content=resp.content,
        status_code=resp.status_code,
        headers=proxy_resp_headers,
    )


# ---- ASR ----

@router.post("/api/asr/transcribe")
async def api_asr_transcribe(request: Request):
    try:
        body = await request.json()
        bvid = body.get("bvid", "").strip()
        if not bvid:
            return JSONResponse({"success": False, "error": "no bvid"})
        from bilibili_client import get_video_info as gvi, get_audio_url
        info = await gvi(bvid)
        audio_data = await get_audio_url(bvid)
        if not audio_data.get("url"):
            return JSONResponse({"success": False, "error": "无法获取音频URL"})
        try:
            import dashscope
            from dashscope.audio.asr import Transcription
            task = Transcription.async_call(model="paraformer-v2", file_urls=[audio_data["url"]], language_hints=["zh", "en"])
            for _ in range(30):
                result = Transcription.fetch(task)
                if result.status_code == 200:
                    output = result.output
                    if output and output.get("results"):
                        transcripts = output["results"][0].get("transcripts", [])
                        if transcripts:
                            text = transcripts[0].get("text", "")
                            return JSONResponse({"success": True, "data": {"text": text, "source": "dashscope_asr"}})
                    break
                await asyncio.sleep(2)
            return JSONResponse({"success": False, "error": "ASR processing timed out"})
        except ImportError:
            return JSONResponse({"success": False, "error": "dashscope 未安装"})
        except Exception as e:
            err = str(e)
            if "data_inspection" in err.lower():
                return JSONResponse({"success": False, "error": "内容安全检查未通过"})
            return JSONResponse({"success": False, "error": err[:200]})
    except Exception as e:
        return JSONResponse({"success": False, "error": str(e)})


@router.post("/api/asr/local")
async def api_asr_local(request: Request):
    return JSONResponse({"success": False, "error": "本地Whisper需要浏览器环境。请使用Chrome扩展 subbatch-local 或配置 DashScope API。"})
