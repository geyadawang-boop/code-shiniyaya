---
name: bilisum-v8.5-exe-delivered
description: BiliSup v8.5 EXE portable zip built via electron-builder, backed up to E: drive and GitHub tag v8.5.
metadata:
  type: project
  updated: 2026-07-15
---

# BiliSum v8.5 EXE 便携版

- Desktop: `C:\Users\shiniyaya\Desktop\BiliSum8.5-win64.zip` (87 MB)
- E: drive: `E:\即将完成\BiliSum8.5-win64.zip` + `E:\即将完成\bilisum8.5\`
- GitHub: branch `fix-claude-findings`, tag `v8.5` (4 commits)

## How to use

1. Extract `BiliSum8.5-win64.zip`
2. `pip install -r backend/requirements.txt` once
3. Double-click `启动BiliSum.bat` — starts backend + Electron window
4. Open `http://127.0.0.1:8000/browse`
5. ⚙ API Settings → set DeepSeek key → save

## What's inside the EXE zip

- `BiliSum.exe` (Electron 33.4.11, win32 x64)
- `resources/app.asar` (packaged frontend + backend)
- `locales/zh-CN.pak` (Chinese locale only, slimmed)
- `启动BiliSum.bat` (launcher script)

[[bilisum-v8.5-delivered]]
[[bilisum-v8.5-e-drive-backup]]