"use strict";
// Injected into B站 popup/proxy windows - toolbar with navigation buttons

(function () {
    // [v7.1 FIX] Guard against duplicate execution when re-injected during SPA navigation
    if (window.__biliInjectLoaded) return;
    window.__biliInjectLoaded = true;

    const BACKEND_URL = "http://127.0.0.1:8000";

    function getBvid() {
        const url = window.location.href;
        const m = url.match(/BV[a-zA-Z0-9]+/) || url.match(/av[0-9]+/i);
        return m ? m[0] : "";
    }

    // [v7.1 FIX] Guard flag to prevent MutationObserver from cascading on its own DOM changes
    var _injecting = false;
    // [v7.1 FIX] Throttle: skip rapid-fire MutationObserver callbacks within this window (ms)
    var _lastInjectTime = 0;
    var _INJECT_THROTTLE_MS = 500;
    var _observer = null;

    function inject() {
        // [v7.1 FIX] Already injecting -- prevent re-entrant calls
        if (_injecting) return;
        // [v7.1 FIX] Throttle against rapid-fire observer callbacks
        var now = Date.now();
        if (now - _lastInjectTime < _INJECT_THROTTLE_MS) return;

        _injecting = true;
        try {
            if (document.getElementById("bili-inject-bar")) {
                _injecting = false;
                return;
            }

            _lastInjectTime = Date.now();
            var bvid = getBvid();
            var bar = document.createElement("div");
            bar.id = "bili-inject-bar";
            bar.style.cssText = "position:fixed;top:0;left:0;right:0;z-index:999999;background:linear-gradient(135deg,#fb7299,#e54980);padding:8px 16px;display:flex;align-items:center;justify-content:space-between;color:#fff;font-size:13px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3)";

            // Build navigation links
            var summaryUrl = bvid
                ? BACKEND_URL + "/summary?bvid=" + bvid
                : BACKEND_URL + "/summary";

            bar.innerHTML =
                '<span style="font-weight:bold;font-size:14px">📺 B站客户端</span>' +
                '<span style="display:flex;gap:6px;align-items:center">' +
                '<a href="' + BACKEND_URL + '/browse" style="padding:5px 12px;background:rgba(255,255,255,0.2);color:#fff;border-radius:16px;text-decoration:none;font-size:12px">🏠 返回BiliSum</a>' +
                '<a href="' + BACKEND_URL + '/bili/proxy?url=https://www.bilibili.com" style="padding:5px 12px;background:rgba(255,255,255,0.15);color:#fff;border-radius:16px;text-decoration:none;font-size:12px">🔗 内嵌B站</a>' +
                '<a href="' + summaryUrl + '" style="padding:5px 16px;background:#fff;color:#e54980;border-radius:16px;text-decoration:none;font-weight:bold;font-size:12px">进入总结 →</a>' +
                '</span>';

            // [v7.1 FIX] Disconnect observer BEFORE DOM mutation to prevent self-triggering
            if (_observer) {
                _observer.disconnect();
            }

            document.body.insertBefore(bar, document.body.firstChild);
            document.body.style.paddingTop = "46px";

            // [v7.1 Security] No unauthorized clipboard write — BV auto-copy is a
            // privacy violation. Clipboard access must be gated by explicit user gesture.

            // [v7.1 FIX] Reconnect observer AFTER DOM mutation completes
            if (_observer) {
                _observer.observe(document.body, { childList: true });
            }

        } catch (e) {
            // [v7.1 FIX] Silently ignore (no network/missing backend, not a code bug)
        } finally {
            // [v7.1 FIX] Always release the guard -- prevents permanent lockout on error
            _injecting = false;
        }
    }

    // [v7.1 FIX] MutationObserver: guard against SPA DOM teardown removing the inject bar
    function startObserver() {
        if (_observer) {
            _observer.disconnect();
        }
        _observer = new MutationObserver(function () {
            // Only react if the inject bar was actually removed by external code (e.g., SPA navigation)
            // The _injecting guard (checked inside inject()) prevents cascading on our own DOM writes
            if (!document.getElementById("bili-inject-bar")) {
                inject();
            }
        });
        _observer.observe(document.body, { childList: true });
    }

    // Run on ready
    if (document.readyState === "loading") {
        document.addEventListener("DOMContentLoaded", function () {
            inject();
            // [v7.1 FIX] Start observer only after initial injection succeeds
            if (!_observer) startObserver();
        });
    } else {
        inject();
        if (!_observer) startObserver();
    }

    // Also re-inject after full page load (catches late SPA render)
    window.addEventListener("load", function () {
        setTimeout(inject, 800);
    });

    // [v7.1 FIX] Cleanup on page unload — prevents MutationObserver memory leak
    function cleanup() {
        if (_observer) {
            _observer.disconnect();
            _observer = null;
        }
    }
    window.addEventListener("beforeunload", cleanup);
    window.addEventListener("pagehide", cleanup);
})();
