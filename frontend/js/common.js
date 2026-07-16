
/**
 * BiliSum v8.1 Frontend Error Handler
 * Captures all unhandled errors and sends them to backend for logging.
 * Trace IDs correlate frontend and backend telemetry.
 */
(function setupFrontendErrorHandler() {
  const ERROR_REPORT_URL = "/api/errors/report";
  const ERROR_BATCH = [];
  const MAX_BATCH_SIZE = 10;
  const FLUSH_INTERVAL = 5000;

  // Generate a client-side trace ID for this page session
  const CLIENT_TRACE_ID = 'client-' + Math.random().toString(36).substr(2, 8);
  const PAGE_URL = window.location.href;
  const USER_AGENT = navigator.userAgent;

  function buildErrorPayload(type, message, stack, filename, lineno, colno) {
    return {
      type: type,
      message: String(message || 'Unknown error'),
      stack: String(stack || ''),
      filename: String(filename || ''),
      lineno: lineno || 0,
      colno: colno || 0,
      clientTraceId: CLIENT_TRACE_ID,
      pageUrl: PAGE_URL,
      userAgent: USER_AGENT,
      timestamp: new Date().toISOString(),
      currentBvid: (typeof currentBvid !== 'undefined') ? currentBvid : ''
    };
  }

  function sendErrorPayload(payload) {
    console.error('[BiliSum Error]', payload.type, payload.message, payload);
    ERROR_BATCH.push(payload);
    if (ERROR_BATCH.length >= MAX_BATCH_SIZE) {
      flushErrors();
    }
  }

  async function flushErrors() {
    if (ERROR_BATCH.length === 0) return;
    const batch = ERROR_BATCH.splice(0, MAX_BATCH_SIZE);
    try {
      await fetch(ERROR_REPORT_URL, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ errors: batch, clientTraceId: CLIENT_TRACE_ID }),
        keepalive: true
      });
    } catch (e) {
      console.error('[BiliSum] Failed to report errors to backend:', e.message);
      ERROR_BATCH.unshift(...batch.slice(0, 3));
    }
  }

  setInterval(flushErrors, FLUSH_INTERVAL);

  window.addEventListener('beforeunload', () => {
    if (ERROR_BATCH.length > 0) {
      try {
        const xhr = new XMLHttpRequest();
        xhr.open('POST', ERROR_REPORT_URL, false);
        xhr.setRequestHeader('Content-Type', 'application/json');
        xhr.send(JSON.stringify({ errors: ERROR_BATCH, clientTraceId: CLIENT_TRACE_ID }));
      } catch (e) { /* last-resort fail-safe */ }
    }
  });

  // Catch unhandled errors
  window.onerror = function(msg, url, line, col, error) {
    sendErrorPayload(buildErrorPayload('unhandled', msg, error ? error.stack : '', url, line, col || 0));
    try { if (typeof showToast === 'function') showToast('JS Error: ' + msg + ' at line ' + line, 'error'); } catch(e) {}
    return false;
  };

  // Catch unhandled Promise rejections
  window.addEventListener('unhandledrejection', function(event) {
    sendErrorPayload(buildErrorPayload('unhandledrejection',
      event.reason ? (event.reason.message || String(event.reason)) : 'Unknown rejection',
      event.reason && event.reason.stack ? event.reason.stack : '', '', 0, 0));
    event.preventDefault();
    try { if (typeof showToast === 'function') showToast('Promise Error: ' + (event.reason?.message || event.reason), 'error'); } catch(e) {}
  });

  // Expose manual error reporting API
  window.reportError = function(message, type) {
    sendErrorPayload(buildErrorPayload(type || 'manual', message, new Error().stack, '', 0, 0));
  };

  console.log('[BiliSum] Frontend error handler initialized, traceId=' + CLIENT_TRACE_ID);
})();

/**
 * BiliSum - Global State Manager
 * Cookie/API Key shared across all pages via localStorage
 */
const AppState = {
    _store: {},

    init() {
        try {
            const saved = localStorage.getItem("bilimind_state");
            if (saved) this._store = JSON.parse(saved);
        } catch (e) { /* ignore */ }
    },

    get(key, defaultValue = "") {
        return this._store[key] !== undefined ? this._store[key] : defaultValue;
    },

    set(key, value) {
        this._store[key] = value;
        try { localStorage.setItem("bilimind_state", JSON.stringify(this._store)); } catch (e) { /* ignore */ }
    },

    // Shortcuts for common settings
    get apiKey() { return this.get("api_key"); },
    set apiKey(v) { this.set("api_key", v); },
    get apiUrl() { return this.get("api_url", "https://api.anthropic.com/v1/messages"); },
    set apiUrl(v) { this.set("api_url", v); },
    get model() { return this.get("model", "claude-opus-4-8"); },
    set model(v) { this.set("model", v); },
    get biliCookie() { return this.get("bili_cookie"); },
    set biliCookie(v) { this.set("bili_cookie", v); },
    get sessionId() { return this.get("session_id"); },
    // v8.3: directory settings getters
    get downloadDir() { return this.get("download_dir", ""); },
    set downloadDir(v) { this.set("download_dir", v); },
    get kbDir() { return this.get("kb_dir", ""); },
    set kbDir(v) { this.set("kb_dir", v); },
    get obsidianVault() { return this.get("obsidian_vault", ""); },
    set obsidianVault(v) { this.set("obsidian_vault", v); },
    set sessionId(v) { this.set("session_id", v); }
};

// Initialize on load
AppState.init();

// ==================== UI Utilities ====================

function showToast(msg, type = "info", duration = 3500) {
    const toast = document.getElementById("toast");
    if (!toast) return;
    // Cancel any pending hide timer
    if (toast._hideTimer) { clearTimeout(toast._hideTimer); toast._hideTimer = null; }
    // Remove existing close button
    const existingClose = toast.querySelector(".toast-close");
    if (existingClose) existingClose.remove();
    toast.classList.remove("slideOut");
    toast.textContent = msg;
    toast.className = "toast toast-" + type;
    toast.style.display = "block";
    // Add close button
    const closeBtn = document.createElement("button");
    closeBtn.className = "toast-close";
    closeBtn.innerHTML = "&#x2715;";
    closeBtn.onclick = () => hideToast();
    toast.appendChild(closeBtn);
    toast._hideTimer = setTimeout(() => hideToast(), duration);
}

function hideToast() {
    const toast = document.getElementById("toast");
    if (!toast) return;
    if (toast._hideTimer) { clearTimeout(toast._hideTimer); toast._hideTimer = null; }
    toast.classList.add("slideOut");
    setTimeout(() => {
        toast.style.display = "none";
        toast.classList.remove("slideOut");
    }, 300);
}

function showLoading(msg = "处理中...") {
    const overlay = document.getElementById("loadingOverlay");
    const msgEl = document.getElementById("loadingMsg");
    if (overlay) overlay.style.display = "flex";
    if (msgEl) msgEl.textContent = msg;
}

function hideLoading() {
    const overlay = document.getElementById("loadingOverlay");
    if (overlay) overlay.style.display = "none";
}

function escapeHtml(str) {
    if (str == null) return "";
    str = String(str);
    return str
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#x27;")
        .replace(/`/g, "&#x60;")
        .replace(/\//g, "&#x2F;");
}

/**
 * Escape for single-quoted HTML attribute values (onclick='...', data-x='...').
 * Escapes: & ' \ < > " newlines — everything that could break a JS string.
 */
function escapeHtmlAttrSingle(str) {
    if (str == null) return "";
    str = String(str);
    return str
        .replace(/&/g, "&amp;")
        .replace(/'/g, "&#x27;")
        .replace(/\\/g, "&#x5C;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/\n/g, "\\n")
        .replace(/\r/g, "\\r");
}

/**
 * Safely set textContent — XSS-proof: no HTML parsing occurs.
 * Preferred over escapeHtml() for DOM text insertion.
 */
function safeTextContent(element, text) {
    if (!element) return;
    element.textContent = text;
}

/**
 * Safe innerHTML setter — strips all tags except explicitly allowed ones.
 * If no allowedTags provided, falls back to textContent (fully safe).
 * Prefer safeTextContent() whenever possible.
 */
function safeInnerHTML(element, html, allowedTags) {
    if (!element) return;
    if (!allowedTags || !allowedTags.length) {
        element.textContent = html;
        return;
    }
    var allowedSet = {};
    allowedTags.forEach(function(t) { allowedSet[t.toLowerCase()] = true; });
    var stripped = String(html).replace(/<\/?([a-zA-Z][a-zA-Z0-9]*)\b[^>]*>/gi, function(match, tag) {
        return allowedSet[tag.toLowerCase()] ? match : "";
    });
    element.innerHTML = stripped;
}

function formatDuration(sec) {
    if (!sec) return "0:00";
    const m = Math.floor(sec / 60);
    const s = Math.floor(sec % 60);
    return m + ":" + (s < 10 ? "0" : "") + s;
}

function formatCount(n) {
    if (!n) return "0";
    if (n >= 10000) return (n / 10000).toFixed(1) + "万";
    if (n >= 1000) return (n / 1000).toFixed(1) + "k";
    return String(n);
}

function extractBvid(input) {
    const m = input.match(/BV[a-zA-Z0-9]{10}/);
    return m ? m[0] : "";
}

// ==================== Skeleton Loading Screens ====================

function showSkeleton(containerId, type = "card") {
    const el = document.getElementById(containerId);
    if (!el) return;
    el.setAttribute("data-skeleton-replace", el.innerHTML);
    if (type === "card") {
        el.innerHTML = Array.from({length: 8}, () => `
            <div class="skeleton-card">
                <div class="skeleton skeleton-thumb"></div>
                <div class="skeleton skeleton-line"></div>
                <div class="skeleton skeleton-line" style="width:65%"></div>
                <div class="skeleton skeleton-text"></div>
            </div>`).join("");
    } else if (type === "video") {
        el.innerHTML = `<div class="skeleton-video">
            <div class="skeleton skeleton-thumb"></div>
            <div class="skeleton-video-info">
                <div class="skeleton skeleton-line"></div>
                <div class="skeleton skeleton-line"></div>
                <div class="skeleton skeleton-line"></div>
            </div></div>`;
    } else if (type === "result") {
        el.innerHTML = `<div class="skeleton-result">
            ${Array.from({length: 8}, (_,i) => `<div class="skeleton skeleton-line" style="width:${100 - i*8}%"></div>`).join("")}</div>`;
    } else if (type === "list") {
        el.innerHTML = Array.from({length: 6}, () => `
            <div style="display:flex;align-items:center;gap:10px;padding:10px 12px;border-bottom:1px solid var(--border)">
                <div class="skeleton skeleton-avatar"></div>
                <div style="flex:1"><div class="skeleton skeleton-line" style="margin:0 0 6px 0"></div><div class="skeleton skeleton-line" style="width:50%;height:8px;margin:0"></div></div>
            </div>`).join("");
    }
}

function hideSkeleton(containerId) {
    const el = document.getElementById(containerId);
    if (!el) return;
    const original = el.getAttribute("data-skeleton-replace");
    if (original !== null && original !== undefined) {
        el.innerHTML = original;
        el.removeAttribute("data-skeleton-replace");
    }
}

// ==================== Hamburger Menu ====================

function setupHamburger() {
    const btn = document.getElementById("hamburgerBtn");
    const menu = document.getElementById("hamburgerMenu");
    if (!btn || !menu) return;

    btn.addEventListener("click", (e) => {
        e.stopPropagation();
        menu.classList.toggle("show");
    });

    document.addEventListener("click", () => {
        menu.classList.remove("show");
    });
}

// ==================== Settings Modal (Global) ====================

function openSettings() {
    const modal = document.getElementById("settingsModal");
    if (!modal) return;
    const apiKeyEl = document.getElementById("settingsApiKey");
    const apiUrlEl = document.getElementById("settingsApiUrl");
    const modelEl = document.getElementById("settingsModel");
    if (apiKeyEl) apiKeyEl.value = AppState.apiKey;
    if (apiUrlEl) apiUrlEl.value = AppState.apiUrl;
    if (modelEl) {
        if (modelEl.tagName === "SELECT") {
            const opts = [...modelEl.options].map(o => o.value);
            modelEl.value = opts.includes(AppState.model) ? AppState.model : opts[0];
        } else {
            modelEl.value = AppState.model;
        }
    }
    // v8.3: Load persisted directory settings from localStorage on open
    const ddEl = document.getElementById("settingsDownloadDir");
    const kbEl = document.getElementById("settingsKbDir");
    const obVaultEl2 = document.getElementById("settingsObsidianVault");
    const obKeyEl2 = document.getElementById("settingsObsidianKey");
    if (ddEl) ddEl.value = AppState.downloadDir;
    if (kbEl) kbEl.value = AppState.kbDir;
    if (obVaultEl2) obVaultEl2.value = AppState.obsidianVault;
    if (obKeyEl2 && !obKeyEl2.value) {
        try {
            const s = JSON.parse(localStorage.getItem("bilisum_settings") || "{}");
            if (s.obsidian_key) obKeyEl2.value = s.obsidian_key;
        } catch (e) { /* ignore */ }
    }
    // Clear any previous field error styles
    _clearSettingsFieldErrors();
    // If not running in Electron, show a one-time browser-mode path guidance
    if (!window.electronAPI) {
        _ensureBrowserPathWarning();
    }
    const menu = document.getElementById("hamburgerMenu");
    if (menu) menu.classList.remove("show");
    modal.style.display = "flex";
}

// v8.3: Load settings from localStorage on page init (called by DOMContentLoaded)
function loadSettings() {
    try {
        const s = JSON.parse(localStorage.getItem("bilisum_settings") || "{}");
        if (s.download_dir) AppState.downloadDir = s.download_dir;
        if (s.kb_dir) AppState.kbDir = s.kb_dir;
        if (s.obsidian_vault) AppState.obsidianVault = s.obsidian_vault;
    } catch (e) { /* ignore */ }
}

function detectProviderFromModel() {
    // Auto-detect API URL from the selected model and update the address field.
    // Called via onchange on the model dropdown in settings.
    const modelEl = document.getElementById("settingsModel");
    const apiUrlEl = document.getElementById("settingsApiUrl");
    if (!modelEl || !apiUrlEl) return;

    const model = modelEl.value || "";
    if (model.startsWith("claude-")) {
        if (!apiUrlEl.value.includes("anthropic.com")) {
            apiUrlEl.value = "https://api.anthropic.com/v1/messages";
        }
    } else if (model.startsWith("deepseek-")) {
        if (!apiUrlEl.value.includes("deepseek.com")) {
            apiUrlEl.value = "https://api.deepseek.com/v1/chat/completions";
        }
    }
}

function closeSettings() {
    const modal = document.getElementById("settingsModal");
    if (modal) modal.style.display = "none";
}

function saveSettings() {
    AppState.apiKey = document.getElementById("settingsApiKey")?.value?.trim() || AppState.apiKey;
    AppState.apiUrl = document.getElementById("settingsApiUrl")?.value?.trim() || AppState.apiUrl;
    const modelEl = document.getElementById("settingsModel");
    AppState.model = modelEl ? modelEl.value.trim() : "claude-opus-4-8";
    const downloadDirEl = document.getElementById("settingsDownloadDir");
    const kbDirEl = document.getElementById("settingsKbDir");
    const obKeyEl = document.getElementById("settingsObsidianKey");
    const obVaultEl = document.getElementById("settingsObsidianVault");
    const downloadDir = downloadDirEl ? downloadDirEl.value.trim() : "";
    const kbDir = kbDirEl ? kbDirEl.value.trim() : "";
    const obKey = obKeyEl ? obKeyEl.value.trim() : "";
    const obVault = obVaultEl ? obVaultEl.value.trim() : "";

    // v8.3: Write directory values back to AppState so they survive intra-session
    AppState.downloadDir = downloadDir;
    AppState.kbDir = kbDir;
    AppState.obsidianVault = obVault;

    // v8.3: Persist all settings to localStorage so they survive page refresh
    try {
        const settings = {
            api_key: AppState.apiKey,
            api_url: AppState.apiUrl,
            model: AppState.model,
            download_dir: downloadDir,
            kb_dir: kbDir,
            obsidian_vault: obVault,
            obsidian_key: obKey
        };
        localStorage.setItem("bilisum_settings", JSON.stringify(settings));
    } catch (e) { /* quota exceeded or localStorage disabled — non-fatal */ }

    // Also save to backend — send CSRF token from cookie
    const controller = new AbortController();
    const timeoutId = setTimeout(() => controller.abort(), 10000);
    const csrfToken = document.cookie.split("; ").find(r => r.startsWith("bilisum_csrf="));
    const csrfValue = csrfToken ? csrfToken.split("=")[1] : "";
    const body = {
        api_key: AppState.apiKey,
        api_url: AppState.apiUrl,
        model: AppState.model,
        obsidian_vault: obVault || (obKey ? "obsidian" : "")
    };
    if (downloadDir) body.download_dir = downloadDir;
    if (kbDir) body.kb_dir = kbDir;
    fetch("/api/settings", {
        method: "POST",
        headers: {
            "Content-Type": "application/json",
            "X-CSRF-Token": csrfValue
        },
        body: JSON.stringify(body),
        signal: controller.signal
    }).then(r => {
        clearTimeout(timeoutId);
        // Parse the body even on HTTP 4xx — the backend returns
        // {success:false, error:"...", field:"kb_dir"} for path validation failures.
        return r.json().catch(() => ({})).then(d => {
            if (r.ok && d.success) {
                _clearSettingsFieldErrors();
                closeSettings();
                showToast("API设置已保存，所有页面生效", "success");
                return;
            }
            // Backend explicitly rejected the save — show WHY and keep the
            // modal open so the user can correct the value immediately.
            const reason = d.error || d.detail || ("HTTP " + r.status);
            if (d.field) _markSettingsFieldError(d.field);
            showToast("保存失败：" + reason, "error", 8000);
        });
    }).catch(err => {
        clearTimeout(timeoutId);
        closeSettings();
        if (err.name === 'AbortError') {
            showToast("后端保存超时，设置仅保存在浏览器", "error");
        } else {
            showToast("无法连接后端，设置仅保存在浏览器", "error");
        }
    });
}

// Map backend field names -> settings modal input ids (for error highlighting)
const SETTINGS_FIELD_INPUTS = {
    api_key: "settingsApiKey",
    api_url: "settingsApiUrl",
    download_dir: "settingsDownloadDir",
    kb_dir: "settingsKbDir",
    obsidian_vault: "settingsObsidianVault"
};

function _markSettingsFieldError(field) {
    const id = SETTINGS_FIELD_INPUTS[field];
    const el = id ? document.getElementById(id) : null;
    if (el) {
        el.style.borderColor = "#e5484d";
        el.style.boxShadow = "0 0 0 2px rgba(229,72,77,.25)";
        el.focus();
        el.addEventListener("input", () => {
            el.style.borderColor = "";
            el.style.boxShadow = "";
        }, { once: true });
    }
}

function _clearSettingsFieldErrors() {
    Object.values(SETTINGS_FIELD_INPUTS).forEach(id => {
        const el = document.getElementById(id);
        if (el) { el.style.borderColor = ""; el.style.boxShadow = ""; }
    });
}

// IPC helpers for settings UI

// Browser-mode path warning: injected into the download/kb/obsidian paths when
// NOT running in Electron.  webkitdirectory only returns a bare folder name so
// the user MUST type the full path manually for the backend to accept it.
function _ensureBrowserPathWarning() {
    const dirFields = ["settingsDownloadDir", "settingsKbDir", "settingsObsidianVault"];
    dirFields.forEach(id => {
        const el = document.getElementById(id);
        if (!el) return;
        if (el.parentElement.querySelector(".browser-path-warn")) return;
        const warn = document.createElement("span");
        warn.className = "browser-path-warn";
        warn.style.cssText = "display:block;font-size:11px;color:#f5a623;margin-top:2px;" +
            "background:rgba(245,166,35,.08);padding:2px 6px;border-radius:4px";
        warn.textContent = "⚠ 浏览器模式下“浏览”按钮仅返回文件夹名称，请手动输入完整绝对路径（如 D:\\\\Bilibili\\\\kb）";
        el.parentElement.appendChild(warn);
    });
}

// Shared browser-fallback: uses <input type="file" webkitdirectory> for Chromium-based browsers
function _browserSelectDir(targetInputId, label) {
    const input = document.createElement('input');
    input.type = 'file';
    input.webkitdirectory = true;
    if (typeof input.webkitdirectory === 'undefined' || input.webkitdirectory === false) {
        const manualPath = prompt((label || '目录') + '：当前浏览器不支持目录选择。\n请手动输入文件夹的完整路径：', '');
        if (manualPath && manualPath.trim()) {
            document.getElementById(targetInputId).value = manualPath.trim();
        }
        return;
    }
    input.onchange = (e) => {
        const files = e.target.files;
        if (!files || files.length === 0) return;
        const dirName = files[0].webkitRelativePath.split('/')[0];
        const el = document.getElementById(targetInputId);
        // Do NOT set bare folder name — it's not a usable path!
        showToast((label ? label + '：' : '') + '浏览器浏览仅获取文件夹名「' + dirName + '」，已忽略。请手动输入完整绝对路径（如 D:\\Bilibili\\kb）', 'error', 10000);
    };
    input.addEventListener('cancel', () => { input.remove(); }, { once: true });
    input.addEventListener('change', () => { setTimeout(() => { input.remove(); }, 100); }, { once: true });
    input.click();
}

function selectDownloadDir() {
    if (window.electronAPI && window.electronAPI.selectDownloadDir) {
        window.electronAPI.selectDownloadDir().then(result => {
            if (result && result.path) document.getElementById("settingsDownloadDir").value = result.path;
        });
    } else {
        _browserSelectDir("settingsDownloadDir", "下载目录");
    }
}
function selectKbDir() {
    if (window.electronAPI && window.electronAPI.selectKbDir) {
        window.electronAPI.selectKbDir().then(result => {
            if (result && result.path) document.getElementById("settingsKbDir").value = result.path;
        });
    } else {
        _browserSelectDir("settingsKbDir", "知识库目录");
    }
}
function selectObsidianVault() {
    if (window.electronAPI && window.electronAPI.selectObsidianVault) {
        window.electronAPI.selectObsidianVault().then(result => {
            if (result && result.path) document.getElementById("settingsObsidianVault").value = result.path;
        });
    } else {
        _browserSelectDir("settingsObsidianVault", "Obsidian Vault");
    }
}

// ==================== B站 Login Modal (Global) ====================

let qrPollTimer = null;

function openLogin() {
    const modal = document.getElementById("loginModal");
    if (!modal) return;
    modal.style.display = "flex";
    document.getElementById("qrStatus").textContent = "正在生成二维码...";
    document.getElementById("qrImage").innerHTML = '<div class="spinner"></div>';
    loadQRCode();
}

function closeLogin() {
    const modal = document.getElementById("loginModal");
    if (modal) modal.style.display = "none";
    if (qrPollTimer) { clearInterval(qrPollTimer); qrPollTimer = null; }
}

async function loadQRCode() {
    try {
        const r = await fetch("/auth/qrcode");
        const data = await r.json();
        if (!data.success) {
            document.getElementById("qrStatus").textContent = "获取二维码失败";
            return;
        }
        document.getElementById("qrImage").innerHTML =
            `<img src="${data.qrcode_image_base64}" style="width:200px;height:200px" alt="QR Code">`;
        document.getElementById("qrStatus").textContent = "请使用B站App扫码";
        startQRPoll(data.qrcode_key);
    } catch (e) {
        document.getElementById("qrStatus").textContent = "连接失败";
    }
}

function startQRPoll(key) {
    if (qrPollTimer) clearInterval(qrPollTimer);
    let attempts = 0;
    qrPollTimer = setInterval(async () => {
        try {
            const r = await fetch(`/auth/qrcode/poll/${key}`);
            const data = await r.json();
            if (data.status === "success") {
                clearInterval(qrPollTimer);
                document.getElementById("qrStatus").textContent = "✅ 登录成功！";
                AppState.biliCookie = "logged_in";
                window.dispatchEvent(new CustomEvent('bilisum:login-success'));
                setTimeout(() => { closeLogin(); showToast("B站登录成功！Cookie已全局共享", "success"); }, 1000);
            } else if (data.status === "scanning") {
                document.getElementById("qrStatus").textContent = "已扫描，请在手机上确认...";
            } else if (data.status === "confirmed") {
                document.getElementById("qrStatus").textContent = "已确认，正在登录...";
            } else if (data.status === "expired") {
                clearInterval(qrPollTimer);
                document.getElementById("qrStatus").textContent = "二维码已过期，点击刷新";
            }
            if (++attempts > 90) { clearInterval(qrPollTimer); document.getElementById("qrStatus").textContent = "超时"; }
        } catch (e) { /* ignore */ }
    }, 2000);
}

// ==================== Stream Parsing Helpers ====================

function _parseNDJSONEvent(line) {
    /** Parse a raw NDJSON line into an event object, or null. */
    if (!line || !line.trim()) return null;
    try {
        const evt = JSON.parse(line);
        if (evt && typeof evt.type === "string") return evt;
    } catch (e) { /* malformed JSON */ }
    return null;
}

function _applyStreamEvent(evt, state) {
    /** Apply a parsed NDJSON event to the streaming UI state.
     *  state: { fullText, textEl, cursorEl, sources, messagesEl }
     *  Mutates state.fullText and state.sources in place. */
    switch (evt.type) {
        case "token":
            state.fullText += evt.text || "";
            state.textEl.textContent = state.fullText;
            state.messagesEl.scrollTop = state.messagesEl.scrollHeight;
            break;
        case "sources":
            state.sources = evt.items || [];
            break;
        case "retrieval":
            if (state.cursorEl) state.cursorEl.textContent = ` ▊ (${evt.count || 0}条)`;
            break;
        case "error":
            state.fullText = "❌ " + (evt.message || "未知错误");
            state.textEl.textContent = state.fullText;
            break;
    }
}

// ==================== Shared Streaming Chat ====================
// Used by both kb.html (sendRAG) and favorites.html (sendChat)

async function streamChat(question, messagesEl, options = {}) {
    /** options: { apiKey, apiUrl, model, endpoint, onBefore, onAfter } */
    const apiKey = options.apiKey || AppState.apiKey;
    const apiUrl = options.apiUrl || AppState.apiUrl;
    const model = options.model || AppState.model;
    const endpoint = options.endpoint || "/api/chat/stream";

    if (!apiKey) { showToast("请先设置API密钥", "error"); openSettings(); return; }

    if (options.onBefore) options.onBefore();
    messagesEl.innerHTML += `<div class="chat-bubble user">${escapeHtml(question)}</div>`;
    const tid = "msg_" + Date.now();
    messagesEl.innerHTML += `<div class="chat-bubble assistant" id="${tid}"><span class="stext"></span><span class="scursor">▊</span></div>`;
    messagesEl.scrollTop = messagesEl.scrollHeight;

    const el = document.getElementById(tid);
    const textEl = el.querySelector(".stext") || el.querySelector(".streaming-text");
    const cursorEl = el.querySelector(".scursor") || el.querySelector(".streaming-cursor");
    let fullText = "", sources = [];

    try {
        const r = await fetch(endpoint, {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({ question, key: apiKey, apiUrl, model })
        });
        if (!r.ok) {
            const errData = await r.json().catch(() => ({}));
            fullText = "❌ " + (errData.detail || errData.error || "HTTP " + r.status);
            textEl.textContent = fullText; if (cursorEl) cursorEl.remove(); return;
        }
        const ct = r.headers.get("content-type") || "";
        if (!ct.includes("text/event-stream") && !ct.includes("application/x-ndjson")) {
            const data = await r.json();
            fullText = "❌ " + (data.error || data.detail || "未知错误");
            textEl.textContent = fullText; if (cursorEl) cursorEl.remove(); return;
        }
        const state = { fullText, textEl, cursorEl, sources, messagesEl };
        const reader = r.body.getReader();
        const dec = new TextDecoder("utf-8"); let buf = "";
        while (true) {
            const { done, value } = await reader.read();
            if (done) break;
            buf += dec.decode(value, { stream: true });
            const lines = buf.split("\n");
            buf = lines.pop() || "";
            for (const line of lines) {
                const evt = _parseNDJSONEvent(line);
                if (evt) _applyStreamEvent(evt, state);
            }
        }
        // Process remaining buffer
        const evt = _parseNDJSONEvent(buf);
        if (evt) _applyStreamEvent(evt, state);
        // Sync back mutable state
        fullText = state.fullText;
        sources = state.sources;
    } catch (e) {
        fullText = "❌ 连接中断: " + (e.message || "未知错误");
        textEl.textContent = fullText;
    }

    if (cursorEl) cursorEl.remove();
    if (sources.length) {
        el.innerHTML += '<div class="chat-sources" style="margin-top:6px">📎 ' +
            sources.map(s => `<a href="https://www.bilibili.com/video/${s.bvid}" target="_blank">${escapeHtml(s.title || s.bvid)}</a>`).join(" · ") + '</div>';
    }
    messagesEl.scrollTop = messagesEl.scrollHeight;
    if (options.onAfter) options.onAfter(fullText, sources);
}

// Initialize on page load
document.addEventListener("DOMContentLoaded", () => {
    AppState.init();
    loadSettings();  // v8.3: restore directory settings from localStorage
    setupHamburger();
    // Close modals on backdrop click
    document.querySelectorAll(".modal-backdrop").forEach(bd => {
        bd.addEventListener("click", function (e) { if (e.target === this) this.style.display = "none"; });
    });
});

// ====== Dark Mode Toggle (v7.1) ======
(function() {
    const saved = localStorage.getItem('bilimind_theme');
    if (saved === 'dark' || saved === 'light') {
        document.documentElement.setAttribute('data-theme', saved);
    }

    window.toggleTheme = function() {
        const current = document.documentElement.getAttribute('data-theme');
        const next = current === 'dark' ? 'light' : 'dark';
        document.documentElement.setAttribute('data-theme', next);
        localStorage.setItem('bilimind_theme', next);
    };
})();

// ====== Safe fallback renderErrorState / renderEmptyState (v8.0+) ======
// These are normally provided by enhancements.js, but if it fails to load
// for any reason, browse.html needs them (it calls them unconditionally).
// SECURITY: retryFn stored on element via closure reference, not inline onclick.
if (typeof window.renderErrorState === "undefined") {
    window.renderErrorState = function(containerId, opts) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var msg = (opts && opts.message) || "未知错误";
        var retryFn = (opts && opts.onRetry) || null;
        el.innerHTML = '<div class="empty-state">' +
            '<div class="empty-state-icon">⚠️</div>' +
            '<div class="empty-state-title">出错了</div>' +
            '<div class="empty-state-text">' + escapeHtml(msg) + '</div>' +
            (retryFn ? '<button class="btn btn-outline btn-sm btn-retry-fallback">🔄 重试</button>' : '') +
            '</div>';
        if (retryFn) {
            var btn = el.querySelector('.btn-retry-fallback');
            if (btn) {
                btn.addEventListener('click', function(e) {
                    e.preventDefault();
                    retryFn();
                });
            }
        }
    };
}
if (typeof window.renderEmptyState === "undefined") {
    window.renderEmptyState = function(containerId, opts) {
        var el = document.getElementById(containerId);
        if (!el) return;
        var title = (opts && opts.title) || "暂无内容";
        var text = (opts && opts.text) || "";
        var icon = (opts && opts.icon) || "📭";
        var actionHTML = (opts && opts.actionHTML) || "";
        el.innerHTML = '<div class="empty-state">' +
            '<div class="empty-state-icon">' + icon + '</div>' +
            '<div class="empty-state-title">' + escapeHtml(title) + '</div>' +
            (text ? '<div class="empty-state-text">' + escapeHtml(text) + '</div>' : '') +
            (actionHTML ? '<div class="empty-state-action">' + actionHTML + '</div>' : '') +
            '</div>';
    };
}


// [v7.1 P0] Global image fallback for blocked B站 CDN resources
document.addEventListener('DOMContentLoaded', function() {
    document.addEventListener('error', function(e) {
        if (e.target && e.target.tagName === 'IMG') {
            const img = e.target;
            if (!img.dataset.failedOnce) {
                img.dataset.failedOnce = '1';
                const fallbackSVG = 'data:image/svg+xml,' + encodeURIComponent(
                    '<svg xmlns="http://www.w3.org/2000/svg" width="160" height="90" viewBox="0 0 160 90">' +
                    '<rect fill="#1a1a2e" width="160" height="90" rx="4"/>' +
                    '<text fill="#666" x="80" y="50" text-anchor="middle" font-size="12" font-family="Arial">图片加载失败</text>' +
                    '</svg>'
                );
                img.src = fallbackSVG;
                img.style.objectFit = 'cover';
            }
        }
    }, true);
});