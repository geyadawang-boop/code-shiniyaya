"use strict";

const { app, BrowserWindow, ipcMain, crashReporter, dialog, shell } = require("electron");
const path = require("path");
const http = require("http");
const fs = require("fs");

const BACKEND_URL = "http://127.0.0.1:8000";
const COOKIES_FILE = path.join(app.getPath("userData"), "bili_cookies.txt");

// [B1] In-memory cookie cache ? avoids disk I/O on every request
let _cookieCache = { value: "", expires: 0 };
function getCachedCookie() {
    const now = Date.now();
    if (now < _cookieCache.expires) return _cookieCache.value;
    try {
        if (fs.existsSync(COOKIES_FILE)) {
            _cookieCache.value = fs.readFileSync(COOKIES_FILE, "utf-8").trim();
            _cookieCache.expires = now + 60000; // 60-second cache
        }
    } catch (e) { /* ignore */ }
    return _cookieCache.value;
}
const MODERN_UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36";

// ==================== Crash Reporter (v8.1) ====================
// Collects native crash dumps for post-mortem diagnosis.
// Minidumps are written to userData/crashes/; no auto-upload.
crashReporter.start({
  productName: 'BiliSum',
  companyName: 'BiliSum',
  submitURL: '',
  uploadToServer: false,
  crashesDirectory: path.join(app.getPath('userData'), 'crashes'),
  extra: {
    app_version: app.getVersion(),
    electron_version: process.versions.electron,
    platform: process.platform,
    arch: process.arch
  }
});

// Main process uncaught exception handler (v8.1)
process.on('uncaughtException', (error) => {
  const crashLog = {
    type: 'main-process-crash',
    message: error.message,
    stack: error.stack,
    timestamp: new Date().toISOString(),
    memory: process.memoryUsage(),
    versions: process.versions
  };
  const crashDir = path.join(app.getPath('userData'), 'crashes');
  try {
    fs.mkdirSync(crashDir, { recursive: true });
    fs.writeFileSync(
      path.join(crashDir, `crash-main-${Date.now()}.json`),
      JSON.stringify(crashLog, null, 2)
    );
  } catch (_) { /* fs may fail during crash */ }
  console.error('[BiliSummary] Main process crash:', crashLog);
  process.exit(1);
});

// GPU crash handler (v8.1)
app.on('gpu-process-crashed', (event, killed) => {
  console.error('[BiliSummary] GPU process crashed, killed:', killed);
  const crashDir = path.join(app.getPath('userData'), 'crashes');
  try {
    fs.mkdirSync(crashDir, { recursive: true });
    fs.writeFileSync(
      path.join(crashDir, `crash-gpu-${Date.now()}.json`),
      JSON.stringify({ type: 'gpu-crash', killed, timestamp: new Date().toISOString() }, null, 2)
    );
  } catch (_) {}
});

// Memory pressure monitor (v8.1) — warns when heap exceeds 500MB
setInterval(() => {
  const mem = process.memoryUsage();
  if (mem.heapUsed > 500 * 1024 * 1024) {
    console.warn('[BiliSummary] High memory usage:', {
      heapUsedMB: (mem.heapUsed / 1024 / 1024).toFixed(1),
      heapTotalMB: (mem.heapTotal / 1024 / 1024).toFixed(1),
      rssMB: (mem.rss / 1024 / 1024).toFixed(1)
    });
  }
}, 30000);

// Set global UA for Electron (fixes B站 "browser too old" issue)
app.userAgentFallback = MODERN_UA;

let mainWindow = null;
let mainWebContentsId = null;
let cookiePollInterval = null;

// ==================== Cookie Management ====================

function loadCookiesFromFile() {
    try {
        if (fs.existsSync(COOKIES_FILE)) {
            return fs.readFileSync(COOKIES_FILE, "utf-8").trim();
        }
    } catch (e) {
        console.error("[BiliSummary] Failed to read cookies:", e.message);
    }
    return "";
}

// [v7.1] Encrypted cookie storage using Electron safeStorage
function loadCookiesEncrypted() {
    const encPath = COOKIES_FILE + ".enc";
    try {
        if (fs.existsSync(encPath) && require("electron").safeStorage.isEncryptionAvailable()) {
            const encrypted = fs.readFileSync(encPath);
            const decrypted = require("electron").safeStorage.decryptString(encrypted);
            return decrypted;
        }
    } catch (e) {
        console.error("[BiliSummary] Failed to decrypt cookies:", e.message);
    }
    // Fallback to plain text
    return loadCookiesFromFile();
}

function saveCookiesEncrypted(cookieStr) {
    try {
        if (require("electron").safeStorage.isEncryptionAvailable()) {
            const encrypted = require("electron").safeStorage.encryptString(cookieStr);
            fs.writeFileSync(COOKIES_FILE + ".enc", encrypted);
            console.log("[BiliSummary] Cookies saved (encrypted)");
            return;
        }
    } catch (e) {
        console.error("[BiliSummary] Encryption failed, saving plain:", e.message);
    }
    // Fallback
    fs.writeFileSync(COOKIES_FILE, cookieStr, "utf-8");
}

function sendCookiesToBackend(cookieStr) {
    if (!cookieStr) return;
    // [CRITICAL FIX] Save cookies locally FIRST — backend notification is best-effort only.
    // If the backend is unreachable, the error handler fires but cookies are already persisted.
    saveCookiesEncrypted(cookieStr);
    const postData = JSON.stringify({ cookie: cookieStr });
    const url = `${BACKEND_URL}/cookies/save`;
    const options = {
        method: "POST",
        headers: { "Content-Type": "application/json", "Content-Length": Buffer.byteLength(postData) }
    };
    const req = http.request(url, options, (res) => {
        let data = "";
        res.on("data", (chunk) => { data += chunk; });
        res.on("end", () => {
            try {
                const result = JSON.parse(data);
                if (result.success) {
                    console.log("[BiliSummary] Cookies saved to backend");
                } else {
                    console.error("[BiliSummary] Backend rejected cookies:", result.error || "unknown");
                }
            } catch (e) { /* ignore parse errors */ }
        });
    });
    req.on("error", (e) => {
        console.error("[BiliSummary] Cookie save failed:", e.message);
    });
    req.setTimeout(5000, () => {
        req.destroy();
        console.error("[BiliSummary] Cookie save timed out after 5s");
    });
    req.write(postData);
    req.end();
}

function syncCookiesToSession() {
    if (!mainWindow) return;
    const content = loadCookiesEncrypted();
    if (!content) return;

    const pairs = content.split(";").map(s => s.trim().split("="));
    pairs.forEach((pair) => {
        if (pair.length >= 2) {
            const name = pair[0].trim();
            const value = pair.slice(1).join("=").trim();
            if (!name || !value) return;
            mainWindow.webContents.session.cookies.set({
                url: "https://www.bilibili.com",
                name: name,
                value: value,
                domain: ".bilibili.com",
                secure: true,
                sameSite: "no_restriction"
            }).catch(() => {});
        }
    });
}

// ==================== IPC Handler ====================

ipcMain.handle("save-bili-cookies", async (event) => {
    // [v7.1] Validate sender is our renderer
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: save-bili-cookies");
        return { success: false, error: "unauthorized sender" };
    }
    try {
        if (!mainWindow) return { success: false, error: "no window" };
        const cookies = await mainWindow.webContents.session.cookies.get({ domain: ".bilibili.com" });
        if (!cookies || cookies.length === 0) return { success: false, error: "not logged in" };
        const str = cookies.map(c => c.name + "=" + c.value).join("; ");
        saveCookiesEncrypted(str);
        sendCookiesToBackend(str);
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle("get-cookies", (event) => {
    // [v7.1] Validate sender is our renderer
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: get-cookies");
        return { success: false, error: "unauthorized sender" };
    }
    try {
        return { success: true, cookies: loadCookiesEncrypted() };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle("get-backend-url", (event) => {
    // [v7.2] Validate sender is our renderer
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: get-backend-url");
        return { error: "unauthorized sender" };
    }
    return { url: BACKEND_URL };
});

ipcMain.handle("get-setting", async (event, key) => {
    // [v7.1] Validate sender is our renderer
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: get-setting");
        return { success: false, error: "unauthorized sender" };
    }
    // [v7.2] Validate key is a known safe setting name
    const ALLOWED_KEYS = ["apiKey", "apiProvider", "model", "userApiKey", "maxHistoryRounds", "theme", "obsidian_vault", "download_dir", "kb_dir"];
    if (typeof key !== "string" || !ALLOWED_KEYS.includes(key)) {
        console.warn("[Security] Blocked IPC with invalid key: get-setting", key);
        return { success: false, error: "invalid key" };
    }
    try {
        const statePath = path.join(app.getPath("userData"), "settings.json");
        if (fs.existsSync(statePath)) {
            const data = JSON.parse(fs.readFileSync(statePath, "utf-8"));
            return { success: true, value: data[key] || "" };
        }
    } catch (e) { /* ignore */ }
    return { success: false, value: "" };
});

ipcMain.handle("set-setting", async (event, key, value) => {
    // [v7.1] Validate sender is our renderer
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: set-setting");
        return { success: false, error: "unauthorized sender" };
    }
    // [v7.2] Validate key is a known safe setting name
    const ALLOWED_KEYS = ["apiKey", "apiProvider", "model", "userApiKey", "maxHistoryRounds", "theme", "obsidian_vault", "download_dir", "kb_dir"];
    if (typeof key !== "string" || !ALLOWED_KEYS.includes(key)) {
        console.warn("[Security] Blocked IPC with invalid key: set-setting", key);
        return { success: false, error: "invalid key" };
    }
    // [v7.2] Validate value type — reject objects/arrays to prevent prototype pollution
    if (typeof value === "object" || typeof value === "undefined") {
        console.warn("[Security] Blocked IPC with invalid value type: set-setting", typeof value);
        return { success: false, error: "invalid value type" };
    }
    try {
        const statePath = path.join(app.getPath("userData"), "settings.json");
        let data = {};
        if (fs.existsSync(statePath)) {
            data = JSON.parse(fs.readFileSync(statePath, "utf-8"));
        }
        data[key] = value;
        fs.writeFileSync(statePath, JSON.stringify(data, null, 2), "utf-8");
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ==================== File System IPC Handlers (v8.2) ====================

// Approved directory roots for shell.openPath -- prevents arbitrary
// filesystem traversal from the renderer.
const FS_APPROVED_ROOTS = (() => {
    const home = app.getPath("home");
    const desktop = app.getPath("desktop");
    const documents = app.getPath("documents");
    const downloads = app.getPath("downloads");
    return [home, desktop, documents, downloads];
})();

function _isPathAllowed(targetPath) {
    if (!targetPath || typeof targetPath !== "string") return false;
    const normalized = path.normalize(targetPath);
    for (const root of FS_APPROVED_ROOTS) {
        if (normalized.startsWith(path.normalize(root) + path.sep) ||
            normalized === path.normalize(root)) {
            return true;
        }
    }
    // Also allow the configured obsidian vault path
    try {
        const statePath = path.join(app.getPath("userData"), "settings.json");
        if (fs.existsSync(statePath)) {
            const data = JSON.parse(fs.readFileSync(statePath, "utf-8"));
            const vault = data["obsidian_vault"] || "";
            if (vault && normalized.startsWith(path.normalize(vault) + path.sep)) return true;
            if (vault && normalized === path.normalize(vault)) return true;
        }
    } catch (_) { /* ignore */ }
    return false;
}

ipcMain.handle("open-folder", async (event, targetPath) => {
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: open-folder");
        return { success: false, error: "unauthorized sender" };
    }
    if (!_isPathAllowed(targetPath)) {
        console.warn("[Security] Blocked open-folder: path outside approved roots", targetPath);
        return { success: false, error: "path not in approved directories" };
    }
    try {
        const normalized = path.normalize(targetPath);
        if (!fs.existsSync(normalized)) {
            return { success: false, error: "path does not exist" };
        }
        if (!fs.statSync(normalized).isDirectory()) {
            return { success: false, error: "path is not a directory" };
        }
        const errMsg = await shell.openPath(normalized);
        if (errMsg) {
            console.warn("[BiliSummary] open-folder warning:", errMsg);
            return { success: false, error: errMsg };
        }
        return { success: true };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle("select-download-dir", async (event) => {
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: select-download-dir");
        return { success: false, error: "unauthorized sender" };
    }
    try {
        const result = await dialog.showOpenDialog(mainWindow, {
            title: "选择下载目录",
            defaultPath: app.getPath("downloads"),
            properties: ["openDirectory", "createDirectory"]
        });
        if (result.canceled) {
            return { success: false, error: "user cancelled", canceled: true };
        }
        const chosen = result.filePaths[0];
        if (!chosen) {
            return { success: false, error: "no directory selected" };
        }
        return { success: true, path: chosen };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle("select-kb-dir", async (event) => {
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: select-kb-dir");
        return { success: false, error: "unauthorized sender" };
    }
    try {
        const result = await dialog.showOpenDialog(mainWindow, {
            title: "选择知识库存储目录",
            defaultPath: app.getPath("documents"),
            properties: ["openDirectory", "createDirectory"]
        });
        if (result.canceled) {
            return { success: false, error: "user cancelled", canceled: true };
        }
        const chosen = result.filePaths[0];
        if (!chosen) {
            return { success: false, error: "no directory selected" };
        }
        return { success: true, path: chosen };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

ipcMain.handle("select-obsidian-vault", async (event) => {
    if (!event.sender || event.sender !== mainWindow?.webContents) {
        console.warn("[Security] Blocked IPC from unknown sender: select-obsidian-vault");
        return { success: false, error: "unauthorized sender" };
    }
    try {
        const result = await dialog.showOpenDialog(mainWindow, {
            title: "选择 Obsidian Vault 目录",
            defaultPath: app.getPath("documents"),
            properties: ["openDirectory"]
        });
        if (result.canceled) {
            return { success: false, error: "user cancelled", canceled: true };
        }
        const chosen = result.filePaths[0];
        if (!chosen) {
            return { success: false, error: "no directory selected" };
        }
        // Persist to settings
        const statePath = path.join(app.getPath("userData"), "settings.json");
        let data = {};
        if (fs.existsSync(statePath)) {
            data = JSON.parse(fs.readFileSync(statePath, "utf-8"));
        }
        data["obsidian_vault"] = chosen;
        fs.writeFileSync(statePath, JSON.stringify(data, null, 2), "utf-8");
        console.log("[BiliSummary] Obsidian vault set to:", chosen);
        return { success: true, path: chosen };
    } catch (e) {
        return { success: false, error: e.message };
    }
});

// ==================== Toolbar Injection ====================
// [v7.1] Canonical toolbar — keep this, /bili/proxy blue bar removed

function getToolbarHTML(bvid) {
    // bvid extracted from URL by maybeInject() -> regex match BV[a-zA-Z0-9]+
    const summaryLink = bvid
        ? `<a href="${BACKEND_URL}/summary?bvid=${bvid}" style="padding:5px 14px;background:#fff;color:#e54980;border-radius:16px;text-decoration:none;font-weight:bold;font-size:12px">进入总结 →</a>`
        : "";
    return `
      <div id="bili-inject-bar" style="position:fixed;top:0;left:0;right:0;z-index:999999;background:linear-gradient(135deg,#fb7299,#e54980);padding:8px 16px;display:flex;align-items:center;justify-content:space-between;color:#fff;font-size:13px;font-family:sans-serif;box-shadow:0 2px 8px rgba(0,0,0,0.3)">
        <span style="font-weight:bold;font-size:14px">📺 B站客户端</span>
        <span>
          <a href="${BACKEND_URL}/browse" style="padding:4px 10px;background:rgba(255,255,255,0.2);color:#fff;border-radius:12px;text-decoration:none;font-size:12px;margin-right:6px">← 返回首页</a>
          ${summaryLink}
        </span>
      </div>
    `;
}

function injectBiliButtons(contents, bvid) {
    // Use encodeURIComponent to safely embed the toolbar HTML into a JS string literal
    const toolbarHtml = getToolbarHTML(bvid);
    const encoded = JSON.stringify(toolbarHtml);
    const script = `
    (function() {
      var old = document.getElementById("bili-inject-bar");
      if (old) { old.remove(); }

      var bar = document.createElement("div");
      bar.id = "bili-inject-bar";
      bar.innerHTML = ${encoded};

      document.body.insertBefore(bar, document.body.firstChild);
      document.body.style.paddingTop = "46px";

      // Prevent duplicate injection from SPA navigation
      var obs = new MutationObserver(function() {
        if (!document.getElementById("bili-inject-bar")) {
          document.body.insertBefore(bar.cloneNode(true), document.body.firstChild);
          document.body.style.paddingTop = "46px";
        }
      });
      if (document.body) obs.observe(document.body, {childList: true, subtree: true});
    })();
  `;
    contents.executeJavaScript(script).catch((e) => {
        console.error("[BiliSummary] Inject failed:", e.message);
    });
}

let injectedTabs = new Set();

function maybeInject(contents, url) {
    if (!url || url.indexOf("bilibili.com") < 0) return;
    if (url.indexOf("/bili/proxy") >= 0) return;  // [P0-15] skip proxy pages
    if (url.indexOf("passport.bilibili.com/login") >= 0) return; // Don't inject on login page

    const bv = url.match(/BV[a-zA-Z0-9]+/);
    const bvid = bv ? bv[0] : "";
    const key = contents.id + "|" + bvid + "|" + (url.split("?")[0]);

    // Throttle: don't re-inject the same tab+page within 3 seconds
    if (injectedTabs.has(key)) return;
    injectedTabs.add(key);
    setTimeout(() => injectedTabs.delete(key), 1000);

    setTimeout(() => {
        try {
            if (contents.isDestroyed && contents.isDestroyed()) return;
            injectBiliButtons(contents, bvid);
        } catch (e) { /* ignore */ }
    }, 100);
}

// ==================== App Event Handlers ====================

app.on("web-contents-created", (event, contents) => {
    contents.setWindowOpenHandler((details) => {
        if (details.url && details.url.indexOf("bilibili.com") >= 0) {
            return {
                action: "allow",
                overrideBrowserWindowOptions: {
                    webPreferences: {
                        preload: path.join(__dirname, "preload-inject.js"),
                        nodeIntegration: false,
                        contextIsolation: true,
                        sandbox: false,
                        webSecurity: true,
                        allowRunningInsecureContent: false,
                        experimentalFeatures: false
                    },
                    title: "B站 - 视频总结"
                }
            };
        }
        // [v7.2] Block all non-bilibili popups from renderer
        return { action: "deny" };
    });

    // Single injection point - did-finish-load covers all cases
    contents.on("did-finish-load", () => {
        try {
            const url = contents.getURL();
            maybeInject(contents, url);
        } catch (e) { /* ignore */ }
    });

    // Auto-save cookies after B站 login (main window only)
    contents.on("did-navigate", (event, url) => {
        // [P1] Only track cookies from the main window, not popups/iframes
        if (contents.id !== mainWebContentsId) return;
        if (url && url.indexOf("bilibili.com") >= 0 &&
            url.indexOf("passport.bilibili.com/login") < 0) {
            setTimeout(async () => {
                try {
                    if (contents.isDestroyed && contents.isDestroyed()) return;
                    const cookies = await contents.session.cookies.get({ domain: ".bilibili.com" });
                    if (cookies && cookies.length > 5) {
                        const str = cookies.map(c => c.name + "=" + c.value).join("; ");
                        saveCookiesEncrypted(str);
                        sendCookiesToBackend(str);
                        console.log("[BiliSummary] Cookies auto-saved after login");
                    }
                } catch (e) { /* ignore */ }
            }, 2000);
        }
    });
});

function createWindow() {
    mainWindow = new BrowserWindow({
        width: 1280,
        height: 800,
        minWidth: 960,
        minHeight: 600,
        title: "B站视频总结工具 v5.0",
        webPreferences: {
            preload: path.join(__dirname, "preload.js"),
            nodeIntegration: false,
            contextIsolation: true,
            sandbox: false,  // false: preload needs Node APIs (safeStorage via IPC only → true would be ideal but breaks existing preload)
            webSecurity: true,
            allowRunningInsecureContent: false,
            experimentalFeatures: false
        }
    });

    mainWebContentsId = mainWindow.webContents.id;

    // Override user-agent for all requests (prevents B站 "browser too old")
    mainWindow.webContents.setUserAgent(MODERN_UA);

    // [v7.2] Block navigation to non-local origins in main window
    mainWindow.webContents.on("will-navigate", (event, url) => {
        // [P1] Only allow our own error page (did-fail-load), not arbitrary data:text/html
        const isOwnErrorPage = url.startsWith("data:text/html,") && url.includes("页面加载失败");
        let allowedHost = false;
        try {
            const u = new URL(url);
            allowedHost = (u.hostname === "localhost" || u.hostname === "127.0.0.1" ||
                           u.hostname === "bilibili.com" || u.hostname.endsWith(".bilibili.com"));
        } catch { /* relative URLs from localhost won't parse; allow them */ }
        const allowed = isOwnErrorPage || allowedHost;
        if (!allowed) {
            console.warn("[Security] Blocked navigation to:", url);
            event.preventDefault();
        }
    });

    mainWindow.on("closed", () => {
        if (cookiePollInterval) clearInterval(cookiePollInterval);
        if (healthCheckTimer) clearTimeout(healthCheckTimer);
        cookiePollInterval = null;
        healthCheckTimer = null;
        mainWindow = null;
    });

    // Fix B站 requests - add proper Referer + UA + Cookies
    mainWindow.webContents.session.webRequest.onBeforeSendHeaders(
        { urls: ["*://*.hdslb.com/*", "*://*.bilibili.com/*", "*://*.bilivideo.com/*"] },
        (details, callback) => {
            details.requestHeaders["Referer"] = "https://www.bilibili.com/";
            details.requestHeaders["User-Agent"] = MODERN_UA;
            // Inject B站 cookies
            try {
                const ck = loadCookiesEncrypted();
                if (ck) details.requestHeaders["Cookie"] = ck;
            } catch (e) { /* ignore */ }
            callback({ requestHeaders: details.requestHeaders });
        }
    );

    // [P0-17] CORS: Inject origin headers for B站 API calls from proxy pages
    // v8.4: Use single-value (not array) to avoid multi-origin CORS rejection.
    mainWindow.webContents.session.webRequest.onHeadersReceived(
        { urls: ["*://*.bilibili.com/*", "*://*.hdslb.com/*", "*://*.bilivideo.com/*"] },
        (details, callback) => {
            callback({
                responseHeaders: {
                    ...details.responseHeaders,
                    "access-control-allow-origin": "http://127.0.0.1:8000",
                    "access-control-allow-credentials": "true",
                    "access-control-allow-methods": "GET, POST, PUT, DELETE, OPTIONS, PATCH",
                    "access-control-allow-headers": "*"
                }
            });
        }
    );

    // [v7.2] Security: CSP header for renderer (covers local app + B站 popups)
    mainWindow.webContents.session.webRequest.onHeadersReceived(
        { urls: ["http://127.0.0.1:8000/*", "http://localhost:8000/*"] },
        (details, callback) => {
            if (details.url.includes("/bili/proxy")) {
                callback({ responseHeaders: details.responseHeaders });
                return;
            }
            callback({
                responseHeaders: {
                    ...details.responseHeaders,
                "Content-Security-Policy": [
                    "default-src 'self'; " +
                    "script-src 'self' 'unsafe-inline' https://cdn.jsdelivr.net; " +
                    "style-src 'self' 'unsafe-inline'; " +
                    "img-src 'self' data: https://*.hdslb.com https://*.bilibili.com https://*.bilivideo.com; " +
                    "connect-src 'self' http://localhost:8000 http://127.0.0.1:8000 https://cdn.jsdelivr.net; " +
                    "font-src 'self' data:; " +
                    "frame-src 'self' https://*.bilibili.com; " +
                    "frame-ancestors 'self'; " +
                    "media-src 'self'; " +
                    "worker-src 'self'; " +
                    "object-src 'none'; " +
                    "base-uri 'self'; " +
                    "form-action 'self';"
                ]
            }
        });
    });

    // Health check backend then load (v1.0 pattern: graceful degradation)
    let loadAttempt = 0;
    let healthCheckTimer = null;
    const MAX_ATTEMPTS = 5;
    function tryLoad() {
        if (!mainWindow || mainWindow.isDestroyed()) {
            if (healthCheckTimer) { clearTimeout(healthCheckTimer); healthCheckTimer = null; }
            return;
        }
        // [P1] Prevent double-increment: req.destroy() in setTimeout fires error handler
        let handled = false;
        const req = http.get(`${BACKEND_URL}/health`, (res) => {
            // [P1] Drain response body to prevent socket leak across retries
            res.resume();
            if (!mainWindow || mainWindow.isDestroyed()) return;
            if (res.statusCode === 200) {
                handled = true;
                mainWindow.loadURL(`${BACKEND_URL}/browse`);
                return;
            }
            if (!handled && ++loadAttempt < MAX_ATTEMPTS) {
                healthCheckTimer = setTimeout(tryLoad, 1000);
            } else if (!handled) {
                // [v1.0] Graceful degradation: load anyway even if health check fails
                handled = true;
                mainWindow.loadURL(`${BACKEND_URL}/browse`);
            }
        });
        req.on("error", () => {
            if (!mainWindow || mainWindow.isDestroyed()) return;
            if (!handled && ++loadAttempt < MAX_ATTEMPTS) {
                healthCheckTimer = setTimeout(tryLoad, 1000);
            } else if (!handled) {
                // [v1.0] Graceful degradation: load anyway even if backend not reachable
                handled = true;
                mainWindow.loadURL(`${BACKEND_URL}/browse`);
            }
        });
        req.setTimeout(3000, () => {
            req.destroy();
            if (!mainWindow || mainWindow.isDestroyed()) return;
            if (!handled && ++loadAttempt < MAX_ATTEMPTS) {
                healthCheckTimer = setTimeout(tryLoad, 1000);
            } else if (!handled) {
                handled = true;
                mainWindow.loadURL(`${BACKEND_URL}/browse`);
            }
        });
    }
    tryLoad();

    // [v7.2] Crash recovery — reload on render process crash, OOM, or kill
    mainWindow.webContents.on('render-process-gone', (event, details) => {
        console.error('[BiliSummary] Render process gone:', details.reason, details.exitCode);
        const fatalReasons = ['crashed', 'killed', 'oom', 'integrity-failure'];
        if (fatalReasons.includes(details.reason)) {
            console.log('[BiliSummary] Reloading after crash (reason: ' + details.reason + ')...');
            // Show a brief error dialog then reload
            try {
                const { dialog } = require('electron');
                dialog.showErrorBox(
                    '渲染进程崩溃',
                    `原因: ${details.reason}\n退出代码: ${details.exitCode}\n\n应用将尝试重新加载。`
                );
            } catch (_) { /* dialog may fail if UI is dead */ }
            setTimeout(() => {
                if (mainWindow && !mainWindow.isDestroyed()) {
                    mainWindow.loadURL(`${BACKEND_URL}/browse`);
                }
            }, 1000);
        }
    });

    // [v7.2] Detect unresponsive renderer
    mainWindow.webContents.on('unresponsive', () => {
        console.warn('[BiliSummary] Renderer unresponsive — consider reloading');
    });

    // Handle page load failures
    mainWindow.webContents.on("did-fail-load", (event, errorCode, errorDesc, validatedURL) => {
        console.error("[BiliSum] Page load failed:", errorCode, errorDesc);
        if (errorCode !== -3) {  // -3 = user aborted, not an error
            mainWindow.loadURL(`data:text/html,
                <html><body style="font-family:sans-serif;display:flex;align-items:center;justify-content:center;height:100vh;background:#1a1a2e;color:#e8e8e8;text-align:center">
                <div><h2>⚠️ 页面加载失败</h2><p>${errorDesc} (${errorCode})</p>
                <button onclick="location.reload()" style="margin-top:12px;padding:8px 20px;border-radius:20px;border:none;background:#fb7299;color:#fff;cursor:pointer;font-size:14px">🔄 重试</button>
                </div></body></html>`);
        }
    });

    // Sync cookies periodically
    cookiePollInterval = setInterval(() => {
        if (mainWindow) syncCookiesToSession();
    }, 2000);

    // Auto-save cookies when navigating to local app
    mainWindow.webContents.on("did-navigate", async (event, url) => {
        if (url && url.indexOf("localhost:8000") >= 0) {
            try {
                const cookies = await mainWindow.webContents.session.cookies.get({ domain: ".bilibili.com" });
                if (cookies && cookies.length > 0) {
                    const str = cookies.map(c => c.name + "=" + c.value).join("; ");
                    sendCookiesToBackend(str);
                }
            } catch (e) { /* ignore */ }
        }
    });
}

// [v7.2] CDP debug port — only enabled in dev mode, bound to localhost only
if (process.env.BILISUM_DEV === "1") {
    app.commandLine.appendSwitch("remote-debugging-port", "9222");
    app.commandLine.appendSwitch("remote-debugging-address", "127.0.0.1");
}
app.whenReady().then(createWindow);

app.on("window-all-closed", () => {
    if (cookiePollInterval) clearInterval(cookiePollInterval);
    if (process.platform !== "darwin") app.quit();
});

app.on("activate", () => {
   if (BrowserWindow.getAllWindows().length === 0) createWindow();
});
