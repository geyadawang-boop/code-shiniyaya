---
name: media-crawler-reference
description: MediaCrawler(NanmiCoder) — 多平台视频+评论爬虫架构参考，可用于BiliSum外部视频导入和评论抓取功能
metadata:
  type: reference
  created: 2026-07-14
---

# MediaCrawler 参考架构

## 来源
- GitHub: https://github.com/NanmiCoder/MediaCrawler
- Star: 52k+
- 技术栈: Python + Playwright(CDP模式) + asyncio + Pydantic + SQLAlchemy
- 平台: 小红书/抖音/快手/B站/微博/知乎/贴吧 (7平台)

## 可复用模式

### 1. 抽象基类架构（ABC工厂模式）
```
base/base_crawler.py → AbstractCrawler + AbstractLogin + AbstractStore + AbstractApiClient
添新平台只需实现4个抽象类 → 工厂字典注册
```
直接适用: BiliSum添加YouTube/抖音等平台 → 实现对应`{Platform}Crawler`类

### 2. 三种爬虫模式
- search模式: 关键词→批量视频列表
- detail模式: 指定ID→详情+评论
- creator模式: 创作者→全部内容
适用: BiliSum"外部视频导入"功能直接复用

### 3. CDP浏览器复用模式
`playwright.connect_over_cdp("ws://localhost:9222")` → 连接用户真实Chrome → 复用Cookie/指纹
适用: 不用维护独立Cookie，直接复用浏览器登录态

### 4. 多格式存储工厂
CSV/JSON/JSONL/SQLite/MySQL/MongoDB/Excel → 工厂模式切换
适用: BiliSum KB导入可选择不同存储后端

### 5. xpath + JS签名模式
客户端中内联JS签名函数 → 无需逆向 → Monkey-patch修复bug
适用: B站评论抓取可用JS端签名（目前BiliSum用Python WBI，可行但不稳定）

### 6. asyncio.Semaphore并发控制
`asyncio.Semaphore(MAX_CONCURRENCY_NUM)` 默认1，防止IP封禁
适用: 批量BV导入时控制并发

## BiliSum可直接采用的功能
1. **外部视频导入**: 输入任意B站/抖音链接 → MediaCrawler抓取 → ASR → KB
2. **多平台扩展**: YouTube/小红书/知乎通过抽象基类添加
3. **评论全量抓取**: detail模式获取指定视频全部评论 → 替换当前bilibili_client.py的40条限制
4. **Cookie复用**: CDP模式连真实浏览器 → 扫码一次所有平台可用
