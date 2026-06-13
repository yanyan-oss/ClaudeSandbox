# 🧠 ClaudeSandbox

<p align="center">
  <img src="https://img.shields.io/badge/architecture-pipeline--driven-blue?style=flat-square" alt="Architecture: Pipeline-Driven">
  <img src="https://img.shields.io/badge/privacy-zero--trust-red?style=flat-square" alt="Privacy: Zero-Trust">
  <img src="https://img.shields.io/badge/sync-auto--closed--loop-green?style=flat-square" alt="Sync: Auto-Closed-Loop">
  <img src="https://img.shields.io/badge/AI-deepseek%20%7C%20whisper%20%7C%20gemini-orange?style=flat-square" alt="AI Stack">
  <img src="https://img.shields.io/badge/license-MIT-lightgrey?style=flat-square" alt="License: MIT">
</p>

<p align="center"><b>
  一个由双管线驱动的 Obsidian AI 知识引擎。<br>
  本地 ASR → 云端大模型 → 飞书闭环 · 零信任隐私隔离 · 全自动同步。<br>
  纯 Python + Shell，零额外框架依赖。
</b></p>

---

## 🗺️ 架构全景

```
                            ┌──────────────────────────────┐
                            │      GitHub Actions 云端       │
                            │  ┌──────────┐ ┌───────────┐  │
                            │  │  🗞️       │ │  🤖       │  │
                            │  │Collector  │ │  Coach    │  │
                            │  │ 每日快报   │ │ 大师点评   │  │
                            │  └─────┬─────┘ └─────┬─────┘  │
                            └────────┼─────────────┼────────┘
                                     │   push       │  push
                                     ▼              ▼
  ┌─────────────────────────────────────────────────────────────┐
  │                   🏠 Obsidian Vault                          │
  │  ┌───────────────────┐  ┌──────────────────────────────┐   │
  │  │ skill-manager.js  │  │   sync_master_factory.py     │   │
  │  │   技能调度中心      │  │     全自动同步引擎            │   │
  │  │  ┌──────────────┐ │  │  🛡️ stash→rebase→pop       │   │
  │  │  │  SKILL.md    │ │  │  📋 指南哈希全量覆盖         │   │
  │  │  │  轨藏杂志风   │ │  │  🧠 大师沉淀抓取+模板排版    │   │
  │  │  └──────────────┘ │  │  🔐 secrets.txt 死锁         │   │
  │  └───────────────────┘  │  🚀 add→commit→push 闭环     │   │
  │                          └──────────────────────────────┘   │
  │  ┌──────────────────────────────────────────────────────┐   │
  │  │         super_save_workflow_all_in_one.py             │   │
  │  │              全自动深度处理工作流 v5.0                 │   │
  │  │  ┌─────────┐  ┌──────────┐  ┌───────────────────┐  │   │
  │  │  │ 模式 1  │  │  模式 2  │  │     模式 3        │  │   │
  │  │  │全自动通关│  │ 断点续跑 │  │ 交互式深度顾问     │  │   │
  │  │  │ASR→清洗 │  │跳过ASR   │  │ 多轮对话+自动保存  │  │   │
  │  │  │→报告    │  │→直接清洗 │  │ /to_feishu→飞书   │  │   │
  │  │  └─────────┘  └──────────┘  └───────────────────┘  │   │
  │  └──────────────────────────────────────────────────────┘   │
  │  ┌───────────────┐  ┌──────────────┐  ┌────────────────┐  │
  │  │ ai-master-    │  │   secrets    │  │   .gitignore   │  │
  │  │ knowledge/    │  │   .txt       │  │   隐私防火墙     │  │
  │  │ 知识沉淀库     │  │  (死锁本地)  │  │                │  │
  │  └───────────────┘  └──────────────┘  └────────────────┘  │
  └─────────────────────────────────────────────────────────────┘
```

## 🧬 核心引擎

### `sync_master_factory.py` — 全自动同步工厂

| 阶段 | 名称 | 硬核机制 |
|---|---|---|
| 🛡️ 1/5 | Git 冲突防御 | `stash push --include-untracked` → `fetch` → `rebase` → `stash pop`。原子级三步走，拒绝 merge commit 污染历史。 |
| 📋 2/5 | 官方指南全量覆盖 | `gh api` 拉取 Anthropic / Google 官方仓库 → SHA256 哈希比对 → 仅变动时全量覆写。 |
| 🧠 3/5 | 大师沉淀抓取 | 关键词智能映射到三段式 Markdown 模板 → 200 字符指纹查重 → `if fingerprint not in existing` 纯 Python 去重。**零 Token 消耗。** |
| 🔐 4/5 | 隐私保护 | 读取 `secrets.txt`（Gemini 私有链接）→ `.gitignore:107` 永久锁定 → 双阶段暂存区验证 → 紧急拦截机制。 |
| 🚀 5/5 | 闭环上传 | `git add .` → 二次验证 `secrets.txt` 不在暂存区 → `commit` → `push`。全自动，零人工干预。 |

```bash
# 日常使用
$env:GH_BIN = "E:\新建文件夹\bin\gh.exe"   # Windows: gh.exe 路径
python sync_master_factory.py
```

### `super_save_workflow_all_in_one.py` — 全自动深度处理 v5.0

**三模式架构：**

```
模式 1: 全自动一键通关
  本地音频 → faster-whisper ASR (0 成本) → DeepSeek 三段清洗
  → 金句提炼 → 顾问深度探讨 → final_report.md + chat_session.json

模式 2: 断点续跑
  跳过 ASR → 读取已有 temporary_raw.txt → 重新云端清洗
  (省钱/防报错/换模型重新处理)

模式 3: 交互式深度对话
  加载 chat_session.json → 终端多轮对话
  AI 始终保持「资深商业咨询顾问」角色
  🆕 /to_feishu → 一键导出飞书云文档
```

**🆕 v5.0 飞书生态深度集成：**

| 功能 | 说明 |
|---|---|
| `--input "飞书URL"` | 支持 Doc / 妙记 / 知识库链接 → 在线解析文本 → 0 秒跳过 ASR |
| `/to_feishu` | 模式 3 内置命令 → 全部对话导出为飞书云文档 → 高亮打印链接 |
| 飞书 Block API | 原生调用开放平台 API，自动组装文档 Block 树 |

**四级降级容错（ffmpeg 自动补全）：**

```
策略 1: 系统 PATH 已有 → 直接用
策略 2: 项目 .ffmpeg/ 缓存 → 便携版复用
策略 3: imageio-ffmpeg 自带二进制 → 借调
策略 4: 自动下载 Gyan essentials build → 解压到 .ffmpeg/
```

### `skill-manager.js` — 技能调度中心

- **交互式 CLI 选单** — Boxen 黑色框框 + Chalk 高亮 + Ora 加载动画
- **SKILL.md 上下文注入** — 将 130 行完整设计规范作为系统提示词加载
- **多行大纲输入** — 模拟 IDE 级交互体验
- **双技能绑定** — 轨藏杂志风 + Reveal.js 基础模板，一键切换

### `SKILL.md` — 轨藏 PPT 杂志风设计规范

```
核心美学: 杂志排版感 · 大留白 · 强对比 · 三级字体跳
色彩方案: 暗夜 #0A0A0A / 极白 #FAFAFA / 靛蓝 #1B1B3A
页面模板: 封面页 · 章节过渡 · 图文混排 · 引语页 · 结尾页
技术栈:   Reveal.js 1920×1080 · 自定义 CSS 属性 · Fragment 动画
```

---

## 🤖 GitHub Actions 双管线

### 🗞️ AI Collector — 每日前沿快报

```
触发: 每天 08:00 CST (UTC 00:00) / 手动 workflow_dispatch
流程: HN Top30 → Reddit r/ML Hot15 → arXiv cs.AI Latest10
       → DeepSeek-Chat 一锤子总结 → 归档 ai-master-knowledge/YYYY-MM-DD.md
```

### 🤖 AI Coach — 大师点评

```
触发: Push chat-logs/*.md (可通过 [skip-coach] 跳过)
流程: 扫描变更 → 清除历史点评 → DeepSeek-R1 三维度洞见
       → 追加 "## 🤖 大师点评" 段落到原文末 → 自动 push
```

---

## 🔐 零信任隐私架构

| 防线 | 机制 | 状态 |
|---|---|---|
| `secrets.txt` | `.gitignore:107` 精准锁定 · 从未被 git 追踪 · 双阶段暂存区验证 | 🔒 永久隔离 |
| `.claude/` | `.gitignore:4` 整体屏蔽 · 含 `settings.local.json` | 🔒 永久隔离 |
| `.claudecode.json` | `.gitignore:5` 屏蔽 · Claude Code 本地配置 | 🔒 永久隔离 |
| `temporary_raw.txt` | `.gitignore:75` 通配符匹配 `*temporary_raw*` | 🔒 永久隔离 |
| GitHub Token | 存储在 Windows 系统钥匙串 (`gh auth` keyring) | 🔒 从不出现在文件中 |
| API Key | 全部占位符化 · 推荐环境变量注入 | 🔐 待用户配置 |
| Git 历史 | 经过 `git filter-branch` 清洗 · 密钥已从全部 5 个 commit 中抹除 | ✅ 审计通过 |

---

## 🚀 快速开始

### 环境要求

- Python 3.11+ （`super_save_workflow*.py`）
- Node.js 18+ （`skill-manager.js`）
- `gh` CLI 已认证 （`sync_master_factory.py` 需要）
- Git Bash / WSL （Windows 推荐）

### 首次配置

```bash
# 1. 克隆仓库
git clone https://github.com/yanyan-oss/ClaudeSandbox.git
cd ClaudeSandbox

# 2. Python 依赖
pip install faster-whisper openai

# 3. Node.js 依赖（可选）
npm install

# 4. 配置 API Key（二选一）
#    方式 A: 直接编辑脚本
#      编辑 super_save_workflow_all_in_one.py:54
#      API_KEY = "你的_DeepSeek_API_Key"
#
#    方式 B: 环境变量（推荐）
$env:DEEPSEEK_API_KEY = "sk-xxxxxxxx"

# 5. 填入 Gemini 私有链接（可选）
#    编辑 secrets.txt（已被 .gitignore 锁定，不会泄露）

# 6. 启动同步引擎
python sync_master_factory.py
```

### 运行模式速查

```bash
# 🧠 全自动同步工厂
python sync_master_factory.py

# 🎙️ 直播回放全自动处理
python super_save_workflow_all_in_one.py --mode 1

# 🎙️ 飞书链接直输（跳过 ASR）
python super_save_workflow_all_in_one.py --mode 1 --input "https://..."

# 🎙️ 断点续跑（省钱）
python super_save_workflow_all_in_one.py --mode 2

# 🎙️ 交互式深度对话
python super_save_workflow_all_in_one.py --mode 3

# 🎨 技能管理 CLI
node skill-manager.js
```

---

## 📂 项目结构

```
ClaudeSandbox/                       # Obsidian Vault 根目录
├── sync_master_factory.py           # 🔧 五阶段全自动同步引擎
├── super_save_workflow_all_in_one.py # 🎙️ 深度处理 v5.0（飞书闭环版）
├── super_save_workflow.py           # 🎙️ 深度处理 v1（精简版）
├── skill-manager.js                 # 🎨 技能调度 CLI 中心
├── SKILL.md                         # 📐 轨藏杂志风设计规范（130 行）
├── CLAUDE.md                        # 🤖 Claude Code 项目指引
├── package.json                     # 📦 Node 依赖声明
├── .gitignore                       # 🛡️ 隐私防火墙（107 行规则）
├── secrets.txt                      # 🔐 Gemini 私有链接（死锁本地）
├── ai-master-knowledge/             # 🧠 知识沉淀库
│   ├── claude_code_official_guide.md
│   ├── gemini_official_guide.md
│   ├── master_wisdom.md             # 大师沉淀（自动追加）
│   └── email_inbox.md               # 邮件灵感入口
├── .github/workflows/               # 🤖 双管线
│   ├── workflow-collector.yml       # 每日 AI 快报
│   └── workflow-coach.yml           # 大师点评
├── input_audio/                     # 🎤 音频输入（gitignored）
├── output_result/                   # 📄 报告输出（gitignored）
└── model_cache/                     # 🗜️ 模型缓存（gitignored）
```

---

## 🎯 设计哲学

> **纯代码，零 Token。**
>
> 所有格式化、去重、模板排版均由纯 Python 逻辑完成。
> 不调用大模型做胶水代码能做的事。
> LLM 只用于它擅长的：语义理解与内容生成。

> **隐私不是附加功能，是架构基座。**
>
> `secrets.txt` 从文件创建的第一秒就被 `.gitignore` 锁定。
> 脚本内置双阶段暂存区验证 —— 即使有人手动 `git add secrets.txt`，
> 推送前也会被强制移除。

> **容错不是优雅降级，是进攻性自适应。**
>
> ffmpeg 四级降级、gh CLI 路径可配置、GitHub API 多路径回退、
> 网络失败不阻塞本地流程。每个外部依赖都有逃生舱。

---

## 📄 许可证

MIT License — 详见 [LICENSE](LICENSE)

---

<p align="center">
  <sub>
    🏗️ 由 <a href="https://claude.ai/code">Claude Code</a> 深度架构审计后自主设计生成<br>
    📅 最后更新：2026-06-13 · 🔗 <a href="https://github.com/yanyan-oss/ClaudeSandbox">yanyan-oss/ClaudeSandbox</a>
  </sub>
</p>
