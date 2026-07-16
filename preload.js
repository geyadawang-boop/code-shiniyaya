"use strict";

const { contextBridge, ipcRenderer, shell } = require("electron");
const path = require("path");

// [v8.2] ALLOWED_SETTING_KEYS -- kept in sync with main.js ALLOWED_KEYS
const ALLOWED_SETTING_KEYS = Object.freeze(new Set([
    "apiKey", "apiProvider", "model", "userApiKey", "maxHistoryRounds", "theme",
    "obsidian_vault", "download_dir"
]));

// [v8.2] Read the configured obsidian_vault from settings.json so we can
// whitelist file:// URLs pointing inside it for openExternal.
function _getObsidianVaultPath() {
    try {
        const fs = require("fs");
        const { app } = require("electron");
        const statePath = path.join(app.getPath("userData"), "settings.json");
        if (fs.existsSync(statePath)) {
            const data = JSON.parse(fs.readFileSync(statePath, "utf-8"));
            return data["obsidian_vault"] || "";
        }
    } catch (_) { /* ignore */ }
    return "";
}

function _isAllowedFileUrl(url) {
    // Allow file:// URLs within the app resource directory
    const appDir = __dirname.replace(/\\/g, "/");
    if (url.startsWith("file:///" + appDir) || url.startsWith("file://" + appDir)) {
        return true;
    }
    // [v8.2] Allow file:// URLs within the configured obsidian vault
    const vaultPath = _getObsidianVaultPath();
    if (vaultPath) {
        const vaultNormalized = vaultPath.replace(/\\/g, "/");
        if (url.startsWith("file:///" + vaultNormalized)) {
            return true;
        }
        if (url.startsWith("file:///" + vaultNormalized.replace(/^([A-Za-z]):/, ""))) {
            return true;
        }
    }
    return false;
}

contextBridge.exposeInMainWorld("electronAPI", {
    platform: process.platform,

    openExternal: (url) => {
        if (typeof url !== "string") {
            console.warn("[Security] Blocked openExternal: non-string URL");
            return;
        }
        try {
            const parsed = new URL(url);
            if (parsed.protocol === "file:") {
                if (_isAllowedFileUrl(url)) {
                    shell.openExternal(url);
                    return;
                }
                console.warn("[Security] Blocked openExternal: file:// outside app/vault directory", url);
                return;
            }
            if (["http:", "https:"].includes(parsed.protocol) &&
                (parsed.hostname === "localhost" || parsed.hostname === "127.0.0.1")) {
                shell.openExternal(url);
                return;
            }
            if (["http:", "https:"].includes(parsed.protocol) &&
                (parsed.hostname === "bilibili.com" || parsed.hostname.endsWith(".bilibili.com"))) {
                shell.openExternal(url);
                return;
            }
            console.warn("[Security] Blocked openExternal: disallowed URL", url);
        } catch {
            console.warn("[Security] Blocked openExternal: invalid URL", url);
        }
    },

    // [v8.2] Open a folder in the system file manager (e.g., Explorer / Finder).
    // The path is validated by main.js against FS_APPROVED_ROOTS + obsidian_vault.
    openFolder: (folderPath) => {
        if (typeof folderPath !== "string" || folderPath.length > 2000) {
            console.warn("[Security] Blocked openFolder: invalid path");
            return Promise.resolve({ success: false, error: "invalid path" });
        }
        return ipcRenderer.invoke("open-folder", folderPath);
    },

    // [v8.2] Open native directory picker for selecting a download directory.
    selectDownloadDir: () => {
        return ipcRenderer.invoke("select-download-dir");
    },
    selectKbDir: () => {
        return ipcRenderer.invoke("select-kb-dir");
    },

    // [v8.2] Open native directory picker for selecting an Obsidian vault.
    // Persists the chosen path to settings.json on the main-process side.
    selectObsidianVault: () => {
        return ipcRenderer.invoke("select-obsidian-vault");
    },

    getBackendUrl: () => ipcRenderer.invoke("get-backend-url"),
    saveBiliCookies: () => ipcRenderer.invoke("save-bili-cookies"),
    getCookies: () => ipcRenderer.invoke("get-cookies"),

    _allowedSettingKeys: ALLOWED_SETTING_KEYS,

    getSetting: async (key) => {
        if (typeof key !== "string" || !ALLOWED_SETTING_KEYS.has(key)) return null;
        const local = localStorage.getItem("app_" + key);
        if (local) return local;
        try {
            const result = await ipcRenderer.invoke("get-setting", key);
            if (result && result.success) {
                localStorage.setItem("app_" + key, result.value);
                return result.value;
            }
        } catch (e) { console.error("[preload] getSetting IPC failed for key:", key, e); }
        return null;
    },
    setSetting: async (key, value) => {
        if (typeof key !== "string" || !ALLOWED_SETTING_KEYS.has(key)) return;
        if (typeof value !== "string" || value.length > 5000) return;
        localStorage.setItem("app_" + key, value);
        try {
            await ipcRenderer.invoke("set-setting", key, value);
        } catch (e) { console.error("[preload] setSetting IPC failed for key:", key, e); }
    }
});