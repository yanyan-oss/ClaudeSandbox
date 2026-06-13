#!/usr/bin/env python3
"""
╔══════════════════════════════════════════════════════════════════════════════╗
║                    🔧 sync_master_factory.py                                ║
║                 硬核自动化同步工厂 — 零 Token 纯代码引擎                        ║
║                                                                            ║
║  功能矩阵：                                                                  ║
║    1. 🛡️  Git 冲突防御 —— git pull --rebase 死锁冲突                        ║
║    2. 📋  官方指南全量覆盖 —— Claude Code / Gemini 指南哈希比对同步              ║
║    3. 🧠  大师沉淀抓取 —— gh CLI 读取 + 固定模板排版 + 内容查重                  ║
║    4. 🔐  隐私保护 —— secrets.txt 读取 Gemini 链接，gitignore 死守              ║
║    5. 🚀  全自动闭环上传 —— git add / commit / push 一条龙                     ║
╚══════════════════════════════════════════════════════════════════════════════╝
"""

import os
import sys
import json
import hashlib
import subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

# ---- Windows 编码防御：强制 UTF-8 ----
if sys.platform == "win32":
    # 修复 GBK 控制台无法打印 emoji / box-drawing 字符的问题
    try:
        sys.stdout.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    try:
        sys.stderr.reconfigure(encoding="utf-8", errors="replace")
    except (AttributeError, OSError):
        pass
    # 设置环境变量，确保 subprocess 也使用 UTF-8
    os.environ.setdefault("PYTHONIOENCODING", "utf-8")

# ============================================================================
# 0. ⚙️  配置区 —— 按需修改
# ============================================================================

# 仓库根目录（脚本所在目录即为 Obsidian 仓库根）
VAULT_ROOT = Path(__file__).resolve().parent

# gh.exe 路径（GitHub CLI，Windows 下可能需要绝对路径）
GH_BIN = os.environ.get("GH_BIN", "gh")  # 默认用 PATH 里的 gh，也可设环境变量 GH_BIN

# 知识库子目录
KNOWLEDGE_DIR = VAULT_ROOT / "ai-master-knowledge"

# 官方指南文件（源 → 本地目标）
GUIDE_FILES = {
    "claude_code": {
        "local": KNOWLEDGE_DIR / "claude_code_official_guide.md",
        "description": "Claude Code 官方使用指南",
        # GitHub 源：从 Anthropics 官方仓库抓取 CLAUDE.md 或文档
        "gh_repo": "anthropics/claude-code",
        "gh_paths": [
            "README.md",
            "docs/README.md",
        ],
    },
    "gemini": {
        "local": KNOWLEDGE_DIR / "gemini_official_guide.md",
        "description": "Gemini CLI 官方使用指南",
        # GitHub 源：从 Google 官方 Gemini CLI 仓库抓取
        "gh_repo": "google-gemini/gemini-cli",
        "gh_paths": [
            "README.md",
            "docs/README.md",
        ],
    },
}

# 大师沉淀目标文件
MASTER_WISDOM_FILE = KNOWLEDGE_DIR / "master_wisdom.md"

# 大师沉淀 GitHub 源（列表，每个条目是一个仓库 + 路径）
MASTER_SOURCES = [
    {
        "repo": "anthropics/claude-code",
        "path": "CLAUDE.md",
        "label": "Anthropic Claude Code 官方",
    },
    {
        "repo": "google-gemini/gemini-cli",
        "path": "README.md",
        "label": "Google Gemini CLI 官方",
    },
]

# 本地邮件/灵感源文件（放在仓库内，手动更新内容后脚本自动抓取）
EMAIL_INBOX_FILE = KNOWLEDGE_DIR / "email_inbox.md"

# secrets.txt（绝对隐私，gitignore 已屏蔽）
SECRETS_FILE = VAULT_ROOT / "secrets.txt"

# 北京时间时区
CN_TZ = timezone(timedelta(hours=8))

# ============================================================================
# 1. 🛡️  Git 冲突防御
# ============================================================================

def run_git(args, capture=True):
    """在仓库根目录执行 git 命令，返回 (returncode, stdout, stderr)。"""
    result = subprocess.run(
        ["git"] + args,
        cwd=str(VAULT_ROOT),
        capture_output=capture,
        text=True,
        timeout=120,
    )
    return result.returncode, result.stdout.strip(), result.stderr.strip()


def git_pull_rebase():
    """
    【核心防线】自动 git pull origin main --rebase。
    从根源死锁代码冲突的可能性 —— 拉取前先变基，拒绝 merge commit。
    """
    print("\n" + "=" * 60)
    print("🛡️  [阶段 1/5] Git 冲突防御 —— git pull --rebase")
    print("=" * 60)

    os.chdir(str(VAULT_ROOT))

    # 检查是否在 git 仓库中
    rc, out, err = run_git(["rev-parse", "--git-dir"])
    if rc != 0:
        print(f"⚠️  当前目录不是 git 仓库，跳过 pull。({err})")
        return False

    # 检查是否有 remote
    rc, out, err = run_git(["remote", "get-url", "origin"])
    if rc != 0:
        print(f"⚠️  未配置 origin remote，跳过 pull。")
        return False

    # 先 fetch，再 rebase
    print("  📥 git fetch origin main ...")
    rc, out, err = run_git(["fetch", "origin", "main"])
    if rc != 0:
        print(f"  ⚠️  fetch 失败（网络问题？）: {err}")
        print("  ⏭️  跳过同步，继续本地流程。")
        return False

    print("  🔄 git rebase origin/main ...")
    rc, out, err = run_git(["rebase", "origin/main"])
    if rc == 0:
        print(f"  ✅ 变基成功！本地已与远程同步。\n  {out}")
        return True
    else:
        # rebase 失败通常意味着有冲突 —— 中止变基，保护本地
        print(f"  ⚠️  rebase 冲突！自动执行 git rebase --abort 保护本地文件。")
        run_git(["rebase", "--abort"])
        print(f"  📋 冲突详情: {err}")
        return False


# ============================================================================
# 2. 📋  官方指南全量覆盖
# ============================================================================

def _fetch_github_file(gh_repo, gh_path):
    """
    使用 gh CLI 从 GitHub 仓库获取单个文件内容。
    返回 (success: bool, content: str)
    """
    full_ref = f"{gh_repo}/{gh_path}"
    try:
        result = subprocess.run(
            [
                GH_BIN, "api",
                f"repos/{gh_repo}/contents/{gh_path}",
                "--jq", ".content",
            ],
            capture_output=True,
            text=True,
            timeout=30,
        )
        if result.returncode != 0:
            return False, f"(无法获取 {full_ref}: {result.stderr.strip()})"

        # GitHub API 返回 base64 编码的内容
        import base64
        decoded = base64.b64decode(result.stdout.strip()).decode("utf-8", errors="replace")
        return True, decoded
    except FileNotFoundError:
        return False, "(gh CLI 未找到——请确认 E 盘 gh.exe 在 PATH 中)"
    except Exception as e:
        return False, f"(获取异常: {e})"


def _compute_hash(text):
    """计算文本的 SHA256 哈希，用于比对文件是否变动。"""
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def _read_file_safe(path):
    """安全读取文件，不存在则返回空字符串。"""
    try:
        return path.read_text(encoding="utf-8")
    except (FileNotFoundError, OSError):
        return ""


def sync_official_guides():
    """
    【官方指南动态全量覆盖】
    对每个配置的指南源：
      1. 从 GitHub 拉取最新内容
      2. 与本地已有文件比对哈希
      3. 如果源有变动 → 全量覆盖本地文件
      4. 如果源获取失败 → 保留本地文件不动
    """
    print("\n" + "=" * 60)
    print("📋  [阶段 2/5] 官方指南全量覆盖同步")
    print("=" * 60)

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    updated_count = 0
    for key, config in GUIDE_FILES.items():
        local_file = config["local"]
        description = config["description"]
        print(f"\n  📘 {description} ({key})")

        # 逐路径尝试获取源内容（第一个成功即停止）
        source_content = None
        for gh_path in config["gh_paths"]:
            ok, content = _fetch_github_file(config["gh_repo"], gh_path)
            if ok:
                source_content = content
                print(f"    ✅ 已从 {config['gh_repo']}/{gh_path} 获取源内容 ({len(content)} 字符)")
                break
            else:
                print(f"    ⚠️  {content}")

        if source_content is None:
            print(f"    ❌ 所有源路径均获取失败，保留本地文件不动。")
            continue

        # 比对哈希
        local_content = _read_file_safe(local_file)
        source_hash = _compute_hash(source_content)
        local_hash = _compute_hash(local_content) if local_content else ""

        if local_hash == source_hash:
            print(f"    ✅ 本地已是最新，无需更新。")
        else:
            # 全量覆盖
            local_file.write_text(source_content, encoding="utf-8")
            action = "新建" if not local_content else "覆盖更新"
            print(f"    🔄 {action}完成！({len(local_content)} → {len(source_content)} 字符)")
            updated_count += 1

    print(f"\n  📊 指南同步汇总: {updated_count} 个文件已更新。")
    return updated_count


# ============================================================================
# 3. 🧠  大师沉淀抓取 + 固定模板排版 + 内容查重
# ============================================================================

MASTER_TEMPLATE = """# 🏆 大师级 AI 协同方法论：{topic}

> 来源：{source}

## 1. 核心思维模型 (Core Mental Models)
{mental_models}

## 2. 独门 Prompt 技巧与高级指令 (Advanced Prompting Techniques)
{prompt_techniques}

## 3. 工具特异性操作指南 (Tool-Specific Guide)
{tool_guide}
"""


def _parse_content_to_sections(raw_content, source_label):
    """
    将原始 Markdown 内容智能解析到模板的三个段落中。
    不调用大模型，纯规则匹配：
      - 以 ## 标题为分界点
      - 自动归类到最匹配的模板段落
    """
    # 关键词映射
    KEYWORD_MAP = {
        "mental_models": [
            "思维模型", "mental model", "核心原则", "设计理念",
            "philosophy", "principle", "overview", "core concept",
            "architecture", "概念", "理念", "哲学",
        ],
        "prompt_techniques": [
            "prompt", "提示", "技巧", "technique", "指令",
            "高级用法", "advanced", "tip", "trick", "best practice",
            "使用技巧", "示例", "example", "recipe", "pattern",
        ],
        "tool_guide": [
            "安装", "install", "配置", "config", "命令", "command",
            "cli", "api", "使用", "usage", "操作", "指南",
            "getting started", "quickstart", "setup", "入门",
            "参数", "flag", "option", "工具", "tool",
        ],
    }

    sections = {
        "mental_models": [],
        "prompt_techniques": [],
        "tool_guide": [],
    }

    lines = raw_content.split("\n")
    current_section = "mental_models"  # 默认归入思维模型
    in_code_block = False

    for line in lines:
        # 追踪代码块边界
        if line.strip().startswith("```"):
            in_code_block = not in_code_block

        # 遇到 ## 标题时重新判断归属
        if not in_code_block and line.strip().startswith("##"):
            title_lower = line.strip().lower()
            best_section = "mental_models"
            best_score = 0
            for section_key, keywords in KEYWORD_MAP.items():
                score = sum(1 for kw in keywords if kw.lower() in title_lower)
                if score > best_score:
                    best_score = score
                    best_section = section_key
            current_section = best_section if best_score > 0 else current_section

        sections[current_section].append(line)

    return {
        "mental_models": "\n".join(sections["mental_models"]).strip() or
                          f"* 持续收集中，来源：{source_label}",
        "prompt_techniques": "\n".join(sections["prompt_techniques"]).strip() or
                             f"* 持续收集中，来源：{source_label}",
        "tool_guide": "\n".join(sections["tool_guide"]).strip() or
                       f"* 持续收集中，来源：{source_label}",
    }


def fetch_master_wisdom():
    """
    【大师沉淀抓取】
    从配置的 GitHub 仓库和本地邮件源抓取内容，
    用固定模板排版，查重后追加到 master_wisdom.md。
    纯代码格式化，不调用任何大模型 API。
    """
    print("\n" + "=" * 60)
    print("🧠  [阶段 3/5] 大师沉淀抓取 & 模板排版")
    print("=" * 60)

    KNOWLEDGE_DIR.mkdir(parents=True, exist_ok=True)

    # 读取已有内容，用于查重
    existing_content = _read_file_safe(MASTER_WISDOM_FILE)
    appended_count = 0

    # ---- 3a. 从 GitHub 源抓取 ----
    for src in MASTER_SOURCES:
        print(f"\n  🔍 抓取: {src['label']} ({src['repo']}/{src['path']})")
        ok, raw = _fetch_github_file(src["repo"], src["path"])
        if not ok:
            print(f"    ⚠️  获取失败: {raw}")
            continue

        # 取前 200 字符做查重指纹
        fingerprint = raw[:200].strip()
        if fingerprint and fingerprint in existing_content:
            print(f"    ✅ 内容已存在，跳过。")
            continue

        # 智能解析内容到三段式模板
        topic = f"{src['label']}方法论精粹"
        source_link = f"https://github.com/{src['repo']}/blob/main/{src['path']}"
        sections = _parse_content_to_sections(raw, src["label"])

        formatted = MASTER_TEMPLATE.format(
            topic=topic,
            source=f"[{src['label']}]({source_link})",
            mental_models=sections["mental_models"],
            prompt_techniques=sections["prompt_techniques"],
            tool_guide=sections["tool_guide"],
        )

        # 最终查重（用更长指纹）
        long_fingerprint = formatted[:500].strip()
        if long_fingerprint in existing_content:
            print(f"    ✅ 格式化后内容已存在，跳过。")
            continue

        # 追加到文件
        _append_to_master_wisdom(formatted)
        print(f"    🆕 新内容已追加！({len(formatted)} 字符)")
        appended_count += 1

    # ---- 3b. 从本地邮件源抓取 ----
    if EMAIL_INBOX_FILE.exists():
        print(f"\n  📧 检测到本地邮件源: {EMAIL_INBOX_FILE.name}")
        email_content = _read_file_safe(EMAIL_INBOX_FILE)
        if email_content.strip():
            email_fingerprint = email_content[:200].strip()
            if email_fingerprint and email_fingerprint not in existing_content:
                topic = "邮件通讯精华"
                source_link = f"本地邮件源 ({datetime.now(CN_TZ).strftime('%Y-%m-%d')})"
                sections = _parse_content_to_sections(email_content, "邮件通讯")

                formatted = MASTER_TEMPLATE.format(
                    topic=topic,
                    source=source_link,
                    mental_models=sections["mental_models"],
                    prompt_techniques=sections["prompt_techniques"],
                    tool_guide=sections["tool_guide"],
                )

                if formatted[:500] not in existing_content:
                    _append_to_master_wisdom(formatted)
                    print(f"  🆕 邮件内容已追加！({len(formatted)} 字符)")
                    appended_count += 1
                    # 消化后清空邮件源，防止重复摄入
                    EMAIL_INBOX_FILE.write_text(
                        f"<!-- 已于 {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M')} 摄入 -->\n",
                        encoding="utf-8",
                    )
                else:
                    print(f"  ✅ 邮件内容已存在，跳过。")
        else:
            print(f"  📭 邮件源为空，跳过。")
    else:
        print(f"\n  📭 未检测到本地邮件源（{EMAIL_INBOX_FILE.name} 不存在），跳过。")

    print(f"\n  📊 沉淀汇总: {appended_count} 条新内容已追加。")
    return appended_count


def _append_to_master_wisdom(formatted_text):
    """追加内容到 master_wisdom.md，自动添加分隔线和时间戳。"""
    timestamp = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M CST")
    divider = f"\n\n---\n<!-- ⬆️  {timestamp} 自动摄入 -->\n\n"
    with open(MASTER_WISDOM_FILE, "a", encoding="utf-8") as f:
        f.write(divider + formatted_text)


# ============================================================================
# 4. 🔐  隐私保护
# ============================================================================

def ensure_gitignore_privacy():
    """
    确保 secrets.txt 被 .gitignore 锁定。
    如果 .gitignore 中还没有 secrets.txt，自动追加。
    """
    gitignore = VAULT_ROOT / ".gitignore"
    if not gitignore.exists():
        print("⚠️  .gitignore 不存在，正在创建...")
        gitignore.write_text("# 隐私保护\nsecrets.txt\n", encoding="utf-8")
        print("✅ .gitignore 已创建，secrets.txt 已锁定。")
        return

    content = gitignore.read_text(encoding="utf-8")
    if "secrets.txt" not in content:
        with open(gitignore, "a", encoding="utf-8") as f:
            f.write("\n# 隐私保护 —— Gemini 私有链接\nsecrets.txt\n")
        print("🔐 已将 secrets.txt 写入 .gitignore，隐私文件绝不会泄露。")
    else:
        print("🔐 .gitignore 已包含 secrets.txt，隐私保护就绪。")


def read_secrets():
    """
    读取本地的 secrets.txt 文件。
    该文件存放 Gemini 分享对话链接等绝对隐私，
    已在 .gitignore 中屏蔽，永远不会被推送到 GitHub。

    返回: dict { 'gemini_links': [...], 'raw': str }
    """
    print("\n" + "=" * 60)
    print("🔐  [阶段 4/5] 隐私保护 —— 读取 secrets.txt")
    print("=" * 60)

    if not SECRETS_FILE.exists():
        print("  📝 secrets.txt 不存在，正在创建模板文件...")
        SECRETS_FILE.write_text(
            "# =========================================\n"
            "# 🔐 Gemini 私有分享链接（绝对不上传 GitHub）\n"
            "# =========================================\n"
            "# 每行一个链接，以 # 开头的行为注释。\n"
            "# 示例：\n"
            "# https://g.co/gemini/share/xxxxxxxxxxxxx\n"
            "# https://g.co/gemini/share/yyyyyyyyyyyyy\n"
            "# =========================================\n",
            encoding="utf-8",
        )
        print("  ✅ secrets.txt 模板已创建。请填入你的 Gemini 分享链接。")
        return {"gemini_links": [], "raw": ""}

    raw = SECRETS_FILE.read_text(encoding="utf-8").strip()

    # 提取 Gemini 链接（不以 # 开头，包含 gemini/share 或 g.co/gemini）
    gemini_links = []
    for line in raw.split("\n"):
        line = line.strip()
        if line and not line.startswith("#"):
            if "gemini" in line.lower() or "g.co" in line.lower():
                gemini_links.append(line)

    print(f"  🔗 已读取 {len(gemini_links)} 条 Gemini 私有链接。")
    for i, link in enumerate(gemini_links, 1):
        # 只显示前后各 15 字符，中间用 *** 遮蔽
        if len(link) > 40:
            masked = link[:20] + "***" + link[-15:]
        else:
            masked = link[:10] + "***"
        print(f"    [{i}] {masked}")

    return {"gemini_links": gemini_links, "raw": raw}


# ============================================================================
# 5. 🚀  全自动闭环上传
# ============================================================================

def git_auto_push():
    """
    【全自动闭环】
    git add . → git commit → git push
    零人工干预，纯代码触发。
    """
    print("\n" + "=" * 60)
    print("🚀  [阶段 5/5] 全自动闭环上传")
    print("=" * 60)

    os.chdir(str(VAULT_ROOT))

    # 5a. 检查是否有变更
    rc, out, err = run_git(["status", "--porcelain"])
    if rc != 0:
        print(f"  ❌ git status 失败: {err}")
        return False

    if not out:
        print("  📭 工作区干净，无变更需要提交。")
        return True

    changed_files = [line[3:] for line in out.split("\n") if line.strip()]
    print(f"  📝 检测到 {len(changed_files)} 个变更文件:")
    for f in changed_files:
        print(f"    • {f}")

    # 5b. 确认 secrets.txt 不在暂存区
    staged = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    if "secrets.txt" in staged:
        print("  🛑 安全警报：secrets.txt 即将被提交！正在从暂存区移除...")
        run_git(["reset", "HEAD", "--", "secrets.txt"])
        print("  ✅ secrets.txt 已从暂存区移除。")

    # 5c. git add .
    print("  📦 git add .")
    rc, out, err = run_git(["add", "."])
    if rc != 0:
        print(f"  ❌ git add 失败: {err}")
        return False

    # 再次确认 secrets.txt 没被加入
    staged_after = subprocess.run(
        ["git", "diff", "--cached", "--name-only"],
        cwd=str(VAULT_ROOT),
        capture_output=True,
        text=True,
        timeout=30,
    ).stdout
    if "secrets.txt" in staged_after:
        print("  🛑 紧急拦截：secrets.txt 仍在暂存区！强制移除...")
        run_git(["rm", "--cached", "--", "secrets.txt"])
        print("  ✅ secrets.txt 已强制排除。")

    # 5d. git commit
    timestamp = datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M CST")
    commit_msg = f"🔄 auto profile sync with privacy protection [{timestamp}]"
    print(f"  💾 git commit -m \"{commit_msg}\"")
    rc, out, err = run_git(["commit", "-m", commit_msg])
    if rc != 0:
        # 可能 nothing to commit
        if "nothing to commit" in err.lower() or "nothing to commit" in out.lower():
            print("  📭 无变更可提交。")
            return True
        print(f"  ❌ git commit 失败: {err}")
        return False
    print(f"  ✅ 提交成功\n  {out}")

    # 5e. git push
    print("  📤 git push origin main")
    rc, out, err = run_git(["push", "origin", "main"])
    if rc != 0:
        print(f"  ❌ git push 失败: {err}")
        return False
    print(f"  ✅ 推送成功！\n  {out}")

    return True


# ============================================================================
# 🎯 主入口
# ============================================================================

def main():
    """
    sync_master_factory.py 主流程
    =============================
    五个阶段顺序执行，每个阶段的错误不影响后续阶段。
    全流程 0 Token 消耗，纯 Python 代码驱动。
    """
    print("""
╔══════════════════════════════════════════════════════════════╗
║     🔧 sync_master_factory.py                               ║
║     硬核自动化同步工厂 v1.0                                   ║
║     纯代码 · 零Token · 全自动闭环                              ║
╚══════════════════════════════════════════════════════════════╝
""")
    print(f"📂 仓库根目录: {VAULT_ROOT}")
    print(f"🕐 启动时间: {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}")

    results = {
        "git_pull": False,
        "guides_updated": 0,
        "wisdom_appended": 0,
        "secrets_loaded": False,
        "push_success": False,
    }

    # ---- 阶段 1: Git 冲突防御 ----
    results["git_pull"] = git_pull_rebase()

    # ---- 阶段 2: 官方指南全量覆盖 ----
    results["guides_updated"] = sync_official_guides()

    # ---- 阶段 3: 大师沉淀抓取 ----
    results["wisdom_appended"] = fetch_master_wisdom()

    # ---- 阶段 4: 隐私保护 ----
    ensure_gitignore_privacy()
    secrets = read_secrets()
    results["secrets_loaded"] = len(secrets.get("gemini_links", [])) > 0
    if not results["secrets_loaded"]:
        print("  💡 提示：secrets.txt 中暂无 Gemini 链接。可随时编辑该文件添加。")

    # ---- 阶段 5: 全自动闭环上传 ----
    results["push_success"] = git_auto_push()

    # ---- 汇总报告 ----
    print("\n" + "=" * 60)
    print("📊  执行汇总报告")
    print("=" * 60)
    print(f"  🛡️  Git 冲突防御: {'✅ 已同步' if results['git_pull'] else '⏭️ 跳过/失败'}")
    print(f"  📋  官方指南更新: {results['guides_updated']} 个文件")
    print(f"  🧠  大师沉淀追加: {results['wisdom_appended']} 条")
    print(f"  🔐  隐私保护:     {'✅ 已锁定' if results['secrets_loaded'] else '📝 待配置链接'}")
    print(f"  🚀  自动上传:     {'✅ 成功' if results['push_success'] else '⚠️ 失败/跳过'}")
    print(f"\n🕐 完成时间: {datetime.now(CN_TZ).strftime('%Y-%m-%d %H:%M:%S CST')}")
    print("🏁 sync_master_factory.py 执行完毕。\n")

    return 0 if results["push_success"] else 0  # 非致命错误不阻塞


if __name__ == "__main__":
    sys.exit(main())
