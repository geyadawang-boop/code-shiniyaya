---
name: bilisum-19-items-status
description: 19项用户反馈完整追踪 — 5已修复/3部分修复/11未修复，14Agent深入扫描根因定位，Phase C-E执行计划
metadata: 
  node_type: memory
  type: project
  priority: highest
  created: 2026-07-13
  updated: 2026-07-13
  originSessionId: 1d7393c2-ece5-4e1b-8a49-34f83722e062
---

# BiliSum 19项用户反馈 — 完整状态追踪及修复计划

## 一、完成状态

### ✅ 已修复 (5/19)
| # | 问题 | 修复 | 文件:行号 |
|---|------|------|-----------|
| 1 | 弹幕读取报错 | 签名修正+动态分段循环 | bilibili_client.py L414-454 |
| 5 | Obsidian推送CSRF | CSRF_EXEMPT_PATHS追加 | main.py L217 |
| 7 | KB导入后显示无内容 | 路由/api/kb/entry+数据格式d.data | kb.html L154/L157 |
| 12 | 总结页导入KB token missing | CSRF豁免/api/kb/append | main.py L217 |
| 19 | 弹幕显示暂无弹幕 | segment_index=ceil(duration/360)循环 | bilibili_client.py L418-454 |

### ⚠️ 部分修复 (3/19)
| # | 问题 | 已完成 | 缺失 |
|---|------|--------|------|
| 2 | 评论精选优化 | ps=30→40 | UP主优先排序+子回复15条+传LLM更多评论 |
| 11 | 旧视频无法删除 | 定位CSRF豁免缺口 | 修复未执行；ChromaDB/kb_index_meta残留清理待做 |
| 13 | 40条评论+子回复 | ps增加 | 20精选+20热度分类未实现；UP主标记缺失 |

### ❌ 未修复 (11/19)
| # | 问题 | 根因（14Agent扫描定位） |
|---|------|----------------------|
| 3 | 思维导图按学霸笔记优化 | 仅加CDN白名单；14/18布局模板未移植 |
| 4 | DOCX按学霸笔记优化 | 仅激活API；模板未优化（note-skill有18布局） |
| 6 | 内嵌网站问题 | 未分析 |
| 8 | 打开库功能异常 | vault双层存储不同步(main.js+SQLite+settings.json) |
| 9 | 下载路径设置 | download_dir设置键存在但从未使用 |
| 10 | 初始化Obsidian | 无扫描vault .md文件回导入KB的功能 |
| 14 | AI资料不足 | 多P弹幕未聚合+UP主标记缺失+prompt上下文不够 |
| 15 | 内嵌页面10视频+登录失效 | 加密/明文cookie不同步+代理页面cookie跨域 |
| 16 | KB/下载存储位置设置 | KB_DIR硬编码、无用户可配置下载路径 |
| 17 | Obsidian联动调试 | vault path已修复；REST API路径不可达(无API key)；export发送空bvids |
| 18 | 视频/音频下载 | yt-dlp集成代码存在但无前端入口+无下载路径配置 |
