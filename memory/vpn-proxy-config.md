---
name: vpn-proxy-config
description: VPN代理端口7897，每次网络操作后恢复默认
metadata:
  type: project
  created: 2026-07-14
---

# VPN代理配置

- 代理地址: `http://127.0.0.1:7897` / `https://127.0.0.1:7897`
- 默认设置: 无代理（`HTTP_PROXY=` / `HTTPS_PROXY=` 为空）

## 使用规则

1. 需要网络操作时设置: `export HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897`
2. 操作完成后立即恢复: `unset HTTP_PROXY HTTPS_PROXY http_proxy https_proxy`
3. Bash 命令用 `HTTP_PROXY=http://127.0.0.1:7897 HTTPS_PROXY=http://127.0.0.1:7897 <command>` 单次设置，命令结束自动恢复

**Why:** 用户开启VPN（端口7897），需要时临时代理；默认无需代理（国内API）。
**How to apply:** 每个需要外网的Bash命令前加代理环境变量，不要全局export。
