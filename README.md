# BiliSum — B站视频AI总结与知识库工具

一键将B站视频转化为可检索、可问答的知识库。提取字幕、弹幕、评论，AI多维度总结，画面关键帧抓取，智能问答。

## 核心功能

### 视频知识库导入
- 粘贴B站BV号 → 自动抓取字幕(多P全量)、弹幕精华、热门评论
- 无字幕视频自动ASR语音转写 (faster-whisper)
- 平台话术智能过滤 (一键三连/关注/打卡等噪音自动清除)
- 弹幕智能折叠 (500条"哈哈哈"→一条"哈哈哈 x500")
- 导入内容存入知识库文件夹 (`BV号_视频标题.json`)

### AI多维度总结
- 教学优先: 动机→核心思想→机制→例子→小结
- 七维结构: 概览/核心结论/知识树/逻辑脉络/时间线笔记/术语表/复习问题
- 支持详细(Markdown)和结构化(JSON)两种输出
- 跳过寒暄、求三连、广告，保留实质性讨论
- 所有引用标注来源与置信度

### 画面关键帧抓取
- 导入时自动提取关键帧 + 场景变化帧
- VLM视觉识别画面文字 (公式、图表、代码、产品型号)
- 时间戳标注 → AI总结和问答可直接引用画面内容
- 接入阿里云百炼DashScope (qwen-vl-plus)

### AI知识库问答
- 基于已导入视频内容回答问题
- 三层检索回退: ChromaDB向量搜索 → FTS5全文搜索 → JSON文件直接扫描
- 时间戳引用: 回答可标注来自字幕还是画面内容
- 支持追问和否定重试

### 字幕三級回退
- Tier 1: 官方CC字幕/AI字幕 (优先,速度快)
- Tier 2: ASR语音转写 (无字幕时自动触发, 最长900秒)
- Tier 3: 纯视觉模式 (关键帧→VLM识别→"[画面]"字幕条目)

### 收藏夹批量导入
- 选择B站收藏夹 → 批量导入所有视频
- 自动去重 (已导入的不重复处理)
- 导入进度实时显示

### 智能分类
- 12类+5维自动分类 (科技/娱乐/教程/科普等)
- LLM标签自动生成
- 按分类浏览知识库

### 导出与备份
- 导出为Markdown笔记 (七维结构)
- 保存到Obsidian知识库
- DOCX报告 (含封面和思维导图)
- 计划: .txt纯文本 / .srt时间轴字幕导出

### 思维导图
- 现有版本: AI总结时同步生成
- v9.0计划: 独立LLM调用, 按时序多层级, 可折叠/缩放/拖拽, 点击跳转视频时刻

### B站集成
- 内嵌B站浏览 (iframe)
- 扫码登录获取高清
- 视频/音频/字幕下载 (下载到指定路径, 按 `视频标题_BV号` 目录)
- WBI v2签名完整支持

### 其他
- 下载路径自定义 + 知识库路径自定义 (改完即生效, 无需重启)
- 删除视频时自动清理: 知识库文件/搜索索引/AI向量/ASR音频缓存/下载文件夹
- API设置支持: DeepSeek / 通义千问 / Claude / OpenAI (国内优先)
- 本地Electron桌面应用

## 技术栈

| 层 | 技术 |
|----|------|
| 后端 | Python + FastAPI + uvicorn |
| 向量库 | ChromaDB + FTS5全文本搜索 |
| AI/LLM | OpenAI兼容接口 (DeepSeek等) + unified_llm_client |
| ASR | faster-whisper |
| 视频处理 | yt-dlp + ffmpeg |
| 桌面壳 | Electron |
| 前端 | 原生HTML/CSS/JS (无框架依赖) |
| 数据库 | SQLite (WAL模式) |
| VLM | DashScope qwen-vl-plus (画面文字识别) |

## 快速开始

```bash
# 安装依赖
pip install -r requirements.txt

# 启动后端
cd backend
python main.py

# 或双击 start.bat (Windows)
# 或通过Electron壳启动 (npm start)
```

打开 http://127.0.0.1:8000/browse

首次使用: ⚙ API设置 → 填入DeepSeek API Key → 保存。

## 项目结构

```
BiliSum/
├── backend/           # Python后端 (67个.py文件)
│   ├── main.py        # FastAPI应用入口
│   ├── database.py    # SQLite数据库操作 + KB路径管理
│   ├── bilibili_client.py  # B站API完整集成 (20+端点)
│   ├── summarizer.py  # AI总结引擎 (七维教学优先)
│   ├── rag_service.py # ChromaDB向量搜索
│   ├── content_filter.py     # 平台话术/弹幕评论智能过滤
│   ├── frame_text_service.py # 画面关键帧VLM识别
│   ├── asr_service.py # 语音转写
│   ├── classifier.py  # 智能分类
│   ├── routers/       # API路由模块
│   │   ├── kb.py      # 知识库CRUD + AI问答
│   │   ├── ai.py      # AI总结
│   │   ├── bilibili.py # B站视频下载
│   │   ├── favorites.py # 收藏夹同步
│   │   └── ...
│   ├── frame_extractor.py # ffmpeg帧提取
│   ├── scene_detector.py  # 场景检测
│   ├── thumbnail_generator.py # 缩略图
│   ├── unified_llm_client.py # 多模型统一客户端(支持多模态)
│   └── ...
├── frontend/          # 前端页面
│   ├── browse.html    # 首页·B站浏览
│   ├── kb.html        # 知识库管理+AI问答
│   ├── summary.html   # AI总结页
│   ├── favorites.html # 收藏夹批量导入
│   ├── tools.html     # 工具页(下载等)
│   ├── categories.html # 智能分类浏览
│   ├── multi-platform.html # 多平台导入(YT/B站/直链)
│   ├── upload.html    # 本地视频上传
│   ├── css/           # 样式 (style.css + enhancements.css)
│   └── js/            # JS (common.js + api.js + enhancements.js)
├── memory/            # 项目记忆 (120个Markdown文件)
│   ├── all-active-rules.md           # 22条活跃规则
│   ├── bilisum-v9.0-execution-plan.md # v9.0执行蓝图
│   ├── bilisum-v8.7-master-bug-list.md # 25个Bug清单
│   ├── manual-verification-checklist.md # 人工核验清单
│   └── ...
├── references/        # 参考技能定义+文档
├── preload.js / main.js  # Electron壳
├── requirements.txt   # Python依赖
└── start.bat          # Windows一键启动
```

## 配置

### AI API
- DeepSeek: https://api.deepseek.com/v1/chat/completions
- 通义千问 DashScope: 阿里云百炼控制台
- 自定义OpenAI兼容端点

### 画面抓取 (需DashScope key)
在设置中填入 `dashscope_api_key` (阿里云百炼→API-KEY管理)

### 环境变量 (可选)
```
BILISUM_ASR_FALLBACK=0     # 禁用ASR回退
BILISUM_VISUAL_FALLBACK=0  # 禁用视觉回退
BILISUM_ASR_TIMEOUT=900    # ASR超时(秒)
```

## 开源参考

本项目参考了以下优秀的开源项目进行功能优化:
- [bilinote](https://github.com/PrideWood/bilinote) — 多平台URL/本地上传/思维导图/任务历史
- [wdkns-skills](https://github.com/wdkns/wdkns-skills) — 字幕三级回退/画面关键帧/平台话术过滤
- [bilibili-rag](https://github.com/via007/bilibili-rag) — ChromaDB同步单例/引用计数删除/自愈校准
- [Bili23-Downloader](https://github.com/) — safe_remove/目录验证/磁盘守卫/下载管理
- [ponytail](https://github.com/DietrichGebert/ponytail) — YAGNI阶梯开发原则

## 规则体系

项目遵循22条活跃开发规则 (详见 `memory/all-active-rules.md`):
- Block A 协作协议 (6条): 用户+Codex双批准/CC禁独改/双向验证/10Agent/深度分析/可复制文本
- Block B 四Skill协同 (5条): OpenSpec计划/multi-agent执行/superpowers纪律/ponytail精简×6
- Block C 技术约束 (6条): 国内API仅限/修复独立验证/强制审查/符号影响分析/逐任务反馈/Caveman压缩
- Block D 输出规则 (5条): 报告→报告文件夹/VPN代理/禁重复验证/人工复核/核验清单

## License

MIT
