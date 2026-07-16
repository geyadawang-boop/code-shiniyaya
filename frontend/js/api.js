/**
 * BiliSum - API Client
 */

const API = {
    // Shared CSRF token helper — read from cookie set by backend
    _csrfToken() {
        const match = document.cookie.match(/(?:^|;\s*)bilisum_csrf=([^;]*)/);
        return match ? match[1] : "";
    },

    async get(url, timeoutMs = 30000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const r = await fetch(url, { signal: controller.signal });
            if (!r.ok) {
                const body = await r.json().catch(() => ({}));
                return { success: false, error: body.detail || body.error || `HTTP ${r.status}`, _status: r.status };
            }
            return r.json();
        } catch (err) {
            if (err.name === 'AbortError') return { success: false, error: "请求超时" };
            throw err;
        } finally {
            clearTimeout(timer);
        }
    },

    async post(url, body, timeoutMs = 30000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const r = await fetch(url, {
                method: "POST",
                headers: { "Content-Type": "application/json", "X-CSRF-Token": this._csrfToken() },
                body: JSON.stringify(body),
                signal: controller.signal
            });
            if (!r.ok) {
                const errBody = await r.json().catch(() => ({}));
                return { success: false, error: errBody.detail || errBody.error || `HTTP ${r.status}`, _status: r.status };
            }
            return r.json();
        } catch (err) {
            if (err.name === 'AbortError') return { success: false, error: "请求超时" };
            throw err;
        } finally {
            clearTimeout(timer);
        }
    },

    async del(url, timeoutMs = 30000) {
        const controller = new AbortController();
        const timer = setTimeout(() => controller.abort(), timeoutMs);
        try {
            const r = await fetch(url, { method: "DELETE", signal: controller.signal, headers: { "X-CSRF-Token": this._csrfToken() } });
            if (!r.ok) {
                const body = await r.json().catch(() => ({}));
                return { success: false, error: body.detail || body.error || `HTTP ${r.status}`, _status: r.status };
            }
            return r.json();
        } catch (err) {
            if (err.name === 'AbortError') return { success: false, error: "请求超时" };
            throw err;
        } finally {
            clearTimeout(timer);
        }
    },

    // B站 API
    fetchVideoInfo(bvid) { return this.get(`/api/bili/info?bvid=${bvid}`); },
    fetchTranscript(bvid) { return this.get(`/api/transcript?url=${bvid}`); }, /* Note: backend accepts ?url= for transcript; ?bvid= also works */
    fetchTimedText(bvid) { return this.get(`/api/timed-text?url=${bvid}`, 120000); }, /* Note: backend accepts ?url= for timed-text; ?bvid= also works */
    fetchComments(bvid) { return this.get(`/api/v2/comments?bvid=${bvid}`); },
    fetchSearch(keyword) { return this.get(`/api/bili/search?keyword=${encodeURIComponent(keyword)}`); },
    fetchPopular(pn = 1) { return this.get(`/api/bili/popular?pn=${pn}&ps=50`); },
    fetchSubtitleDetect(bvid) { return this.get(`/api/v2/subtitle/detect?bvid=${bvid}`, 60000); },
    fetchOutline(bvid) { return this.get(`/api/v2/outline?bvid=${bvid}`); },
    fetchChapters(bvid) { return this.get(`/api/v2/chapters?bvid=${bvid}`); },
    fetchAudio(bvid) { return this.get(`/api/bili/audio?bvid=${bvid}`); },
    fetchDanmaku(bvid) { return this.get(`/api/danmaku?bvid=${bvid}`); },

    // AI Summary (API key now read from backend settings table)
    fetchSummarize(bvid, mode = "detailed") {
        const params = new URLSearchParams({
            url: bvid,
            mode: mode
        });
        return this.get(`/api/summarize?${params}`, 180000);
    },

    fetchSegments(bvid) {
        const params = new URLSearchParams({
            url: bvid
        });
        return this.get(`/api/segments?${params}`, 120000);
    },

    // Knowledge Base
    fetchKBList() { return this.get("/api/kb/list"); },
    fetchKBSave(bvid) { return this.post("/api/rag/save", { bvid }); },
    fetchKBSearch(q) { return this.get(`/api/kb/search?q=${encodeURIComponent(q)}`); },
    fetchKBDelete(bvid) { return this.del(`/api/kb/delete?bvid=${bvid}`); },
    fetchRAGStats() { return this.get("/api/rag/stats"); },
    fetchRAGAsk(question) {
        const key = (typeof AppState !== 'undefined') ? AppState.apiKey : '';
        const apiUrl = (typeof AppState !== 'undefined') ? AppState.apiUrl : '';
        const model = (typeof AppState !== 'undefined') ? AppState.model : '';
        return this.post("/api/rag/ask", {
            question,
            key,
            apiUrl,
            model
        });
    },

    // History
    fetchHistory(search = "") { return this.get(`/api/history?search=${encodeURIComponent(search)}`); },
    deleteHistory(id) { return this.del(`/api/history/${id}`); },

    // Settings
    fetchSettings() { return this.get("/api/settings"); },
    saveSettings(settings) { return this.post("/api/settings", settings); },

    // Auth
    fetchQRCode() { return this.get("/auth/qrcode"); },
    fetchQRPoll(key) { return this.get(`/auth/qrcode/poll/${key}`); },
    fetchFavoritesNav() { return this.get("/api/v2/favorites/nav"); },
    fetchFavoritesFolders(mid) { return this.get(`/api/v2/favorites/folders?mid=${mid}`); },
    fetchFavoritesVideos(mediaId, pn = 1) { return this.get(`/api/v2/favorites/videos?mediaId=${mediaId}&pn=${pn}`); },

    // Export
    getExportUrl(type, bvid) {
        switch (type) {
            case "md": return `/api/v2/export/md?bvid=${bvid}`;
            case "txt": return `/api/v2/export/txt?bvid=${bvid}`;
            case "srt": return `/api/v2/subtitle/srt?bvid=${bvid}`;
            case "vtt": return `/api/v2/subtitle/vtt?bvid=${bvid}`;
            case "comments_md": return `/api/v2/comments/md?bvid=${bvid}`;
            case "docx": return `/api/export?url=${bvid}`;
            default: return "#";
        }
    },

    getExportDocUrl(bvid) {
        const params = new URLSearchParams({
            url: bvid
        });
        return `/api/export?${params}`;
    },

    downloadFile(url, filename) {
        const a = document.createElement("a");
        a.href = url;
        a.download = filename;
        document.body.appendChild(a);
        a.click();
        document.body.removeChild(a);
    }
};
