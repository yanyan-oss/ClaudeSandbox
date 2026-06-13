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
    策略：先 stash 本地变更 → rebase → stash pop 恢复，
    从根源死锁代码冲突的可能性。
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

    # 检查是否有未提交的变更，有则先 stash
    rc, out, err = run_git(["status", "--porcelain"])
    has_changes = bool(out.strip())

    if has_changes:
        print("  📦 检测到本地未提交变更，先 git stash 暂存...")
        rc, out, err = run_git(["stash", "push", "--include-untracked", "-m", "sync_master_factory auto stash"])
        if rc != 0:
            print(f"  ⚠️  stash 失败: {err}")
        else:
            print(f"  ✅ 已暂存。")

    # fetch remote
    print("  📥 git fetch origin main ...")
    rc, out, err = run_git(["fetch", "origin", "main"])
    if rc != 0:
        print(f"  ⚠️  fetch 失败（网络问题？）: {err}")
        _pop_stash_if_needed(has_changes)
        print("  ⏭️  跳过同步，继续本地流程。")
        return False

    # 检查本地是否落后于远程
    rc, behind_out, err = run_git(["rev-list", "--count", "HEAD..origin/main"])
    behind_count = int(behind_out) if behind_out.isdigit() else 0

    if behind_count == 0:
        print("  ✅ 本地已是最新，无需变基。")
        _pop_stash_if_needed(has_changes)
        return True

    # 执行 rebase
    print(f"  🔄 远程领先 {behind_count} 个提交，执行 git rebase origin/main ...")
    rc, out, err = run_git(["rebase", "origin/main"])
    if rc == 0:
        print(f"  ✅ 变基成功！本地已与远程同步。\n  {out}")
        _pop_stash_if_needed(has_changes)
        return True
    else:
        # rebase 冲突 —— 中止变基，保护本地文件
        print(f"  ⚠️  rebase 冲突！自动执行 git rebase --abort 保护本地文件。")
        run_git(["rebase", "--abort"])
        print(f"  📋 冲突详情: {err}")
        _pop_stash_if_needed(has_changes)
        return False


def _pop_stash_if_needed(has_changes):
    """如果之前 stash 了，恢复 stash。"""
    if not has_changes:
        return
    rc, out, err = run_git(["stash", "list"])
    if "sync_master_factory auto stash" in out:
        print("  📤 恢复暂存的本地变更 (git stash pop)...")
        rc, out2, err2 = run_git(["stash", "pop"])
        if rc == 0:
            print("  ✅ 本地变更已恢复。")
        else:
            print(f"  ⚠️  stash pop 失败（可能有冲突，请手动处理）: {err2}")


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

        # 过滤掉仅含注释/空白的"已消化"文件
        substantive_lines = [
            l for l in email_content.split("\n")
            if l.strip() and not l.strip().startswith("<!--")
        ]
        if not substantive_lines:
            print(f"  📭 邮件源已消化完毕（无实质内容），跳过。")
        else:
            substantive_content = "\n".join(substantive_lines)
            email_fingerprint = substantive_content[:200].strip()
            if email_fingerprint and email_fingerprint not in existing_content:
                topic = "邮件通讯精华"
                source_link = f"本地邮件源 ({datetime.now(CN_TZ).strftime('%Y-%m-%d')})"
                sections = _parse_content_to_sections(substantive_content, "邮件通讯")

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
                print(f"  ✅ 邮件内容已存在，跳过。")
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
    print("🏁 同步流水线执行完毕，正在切入 DeepSeek 大师脑暴室...\n")
    # 🎯 注入 Gemini 菜单数据 + 原地刹车开聊
    secrets["_gemini_link_list"] = _load_gemini_links_as_menu()
    interactive_chat(secrets)

    return 0 if results["push_success"] else 0  # 非致命错误不阻塞




# ============================================================================
# 6. 💬  原地 DeepSeek 大师脑暴室 —— Gemini 爬虫 + AI 对话 合一引擎
# ============================================================================

import re as _re_module
import html as _html_module
import urllib.error as _urllib_error

# ---- 6a. 对话配置 ----
CHAT_CONFIG = {
    "model": "deepseek-chat",
    "base_url": "https://api.deepseek.com/v1",
    "max_tokens": 8192,
    "temperature": 0.7,
    "max_history_turns": 40,
    "stream": True,
}

THOUGHT_PACKAGES_DIR = KNOWLEDGE_DIR / "thought-packages"


# ---- 6b. Gemini 分享链接全自动爬取解析引擎 ----

def _scrape_gemini_share(url):
    """
    【核心引擎】请求 gemini.google.com/share/... 页面，
    从 HTML 中提取完整对话文本（用户提问 + Gemini 回复）。

    多策略解析（依次尝试，任一成功即返回）：
      策略 A — 从 __NEXT_DATA__ / JSON-LD / <script> 标签中提取结构化对话数据
      策略 B — 从 <title> + meta description 提取摘要
      策略 C — 从可见文本区域 regex 提取对话块
      策略 D — 返回页面纯文本作为回退

    返回: (success: bool, conversation_text: str)
    """
    if not url:
        return False, ""

    # 规范化 URL：确保是完整的 gemini.google.com 分享链接
    url = url.strip()
    if not url.startswith("http"):
        url = "https://" + url.lstrip("/")

    # 发送 HTTP GET，伪装成浏览器
    req = urllib.request.Request(
        url,
        headers={
            "User-Agent": (
                "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            ),
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
        },
    )

    try:
        with urllib.request.urlopen(req, timeout=20) as resp:
            raw_html = resp.read().decode("utf-8", errors="replace")
    except _urllib_error.HTTPError as e:
        return False, "(HTTP {0} — 链接可能已失效或为私有链接)".format(e.code)
    except _urllib_error.URLError as e:
        return False, "(网络错误: {0})".format(str(e.reason)[:80])
    except Exception as e:
        return False, "(抓取异常: {0})".format(str(e)[:100])

    if not raw_html or len(raw_html) < 200:
        return False, "(页面内容过短，无法解析)"

    # ========== 策略 A：结构化 JSON 数据提取 ==========
    # Gemini share 页面的对话数据通常嵌入在 <script> 标签中
    # 尝试多种 JSON 提取模式

    json_blobs = []

    # A1: __NEXT_DATA__ (Next.js SSR 页面)
    for match in _re_module.finditer(
        r'<script[^>]*id="__NEXT_DATA__"[^>]*type="application/json"[^>]*>(.*?)</script>',
        raw_html, _re_module.DOTALL
    ):
        try:
            data = json.loads(match.group(1))
            json_blobs.append(("next_data", data))
        except (json.JSONDecodeError, KeyError):
            pass

    # A2: 任意 type="application/json" 的 script 标签
    for match in _re_module.finditer(
        r'<script[^>]*type="application/json"[^>]*>(.*?)</script>',
        raw_html, _re_module.DOTALL
    ):
        try:
            data = json.loads(match.group(1))
            if isinstance(data, (dict, list)):
                json_blobs.append(("json_script", data))
        except (json.JSONDecodeError, KeyError):
            pass

    # A3: window.__DATA__ 或类似 JS 变量赋值
    for match in _re_module.finditer(
        r'(?:window\.)?__(?:DATA|STATE|PROPS|INITIAL)__\s*=\s*(\{.*?\});',
        raw_html, _re_module.DOTALL
    ):
        try:
            data = json.loads(match.group(1))
            json_blobs.append(("js_var", data))
        except (json.JSONDecodeError, KeyError):
            pass

    # 遍历所有 JSON blob，递归搜索包含对话文本的结构
    def _extract_conversation_from_json(obj, depth=0):
        """递归遍历 JSON 对象，查找对话 turns。"""
        if depth > 15:
            return None
        if isinstance(obj, dict):
            # 检查是否直接包含对话 turns
            for key in ("turns", "messages", "conversation", "contents", "parts"):
                if key in obj and isinstance(obj[key], list):
                    turns_text = _parse_turns_list(obj[key])
                    if turns_text:
                        return turns_text
            # 检查 text/role 模式（OpenAI 兼容格式）
            if "role" in obj and "content" in obj:
                role = str(obj.get("role", ""))
                text = str(obj.get("content", "")) if isinstance(obj.get("content"), str) else ""
                if text.strip():
                    return "[{0}]: {1}".format(role, text)
            # 递归搜索
            for v in obj.values():
                result = _extract_conversation_from_json(v, depth + 1)
                if result:
                    return result
        elif isinstance(obj, list):
            # 尝试将 list 解析为 turns
            turns_text = _parse_turns_list(obj)
            if turns_text:
                return turns_text
            for item in obj:
                result = _extract_conversation_from_json(item, depth + 1)
                if result:
                    return result
        return None

    def _parse_turns_list(turns):
        """将 turns/messages 列表解析为对话文本。"""
        if not turns or not isinstance(turns, list):
            return None
        lines = []
        for turn in turns:
            if isinstance(turn, dict):
                # 多种可能的字段名
                text = (
                    turn.get("text") or turn.get("content") or
                    turn.get("message") or turn.get("description") or ""
                )
                # 处理 parts 数组（Gemini 原生格式）
                if not text and "parts" in turn:
                    parts = turn["parts"]
                    if isinstance(parts, list):
                        part_texts = []
                        for p in parts:
                            if isinstance(p, dict):
                                part_texts.append(str(p.get("text", "")))
                            elif isinstance(p, str):
                                part_texts.append(p)
                        text = " ".join(part_texts)
                if isinstance(text, str) and text.strip():
                    role = turn.get("role", turn.get("author", turn.get("speaker", "unknown")))
                    lines.append("[{0}]: {1}".format(role, text.strip()))
            elif isinstance(turn, str):
                lines.append(turn)
        return "\n\n".join(lines) if lines else None

    for _blob_type, blob in json_blobs:
        extracted = _extract_conversation_from_json(blob)
        if extracted and len(extracted) > 50:
            return True, extracted

    # 如果 JSON 策略部分成功但内容较短，合并所有 blob 的文本
    if json_blobs:
        all_texts = []
        for _bt, blob in json_blobs:
            t = _extract_conversation_from_json(blob)
            if t:
                all_texts.append(t)
        if all_texts:
            combined = "\n\n---\n\n".join(all_texts)
            if len(combined) > 50:
                return True, combined

    # ========== 策略 B：Meta 标签 + Title 提取 ==========
    title_text = ""
    desc_text = ""

    title_match = _re_module.search(r'<title[^>]*>(.*?)</title>', raw_html, _re_module.DOTALL)
    if title_match:
        title_text = _html_module.unescape(title_match.group(1).strip())
        # 去除 " - Gemini" 等后缀
        title_text = _re_module.sub(r'\s*[-–|]\s*(Gemini|Google).*$', '', title_text, flags=_re_module.IGNORECASE)

    desc_match = _re_module.search(
        r'<meta[^>]*name="description"[^>]*content="([^"]*)"',
        raw_html, _re_module.IGNORECASE
    )
    if desc_match:
        desc_text = _html_module.unescape(desc_match.group(1).strip())

    meta_result = ""
    if title_text:
        meta_result += "📌 主题: {0}\n".format(title_text)
    if desc_text:
        meta_result += "📝 摘要: {0}\n".format(desc_text)

    # ========== 策略 C：从纯文本中提取对话块 ==========
    # 移除 script/style 标签
    cleaned = _re_module.sub(
        r'<(script|style|noscript)[^>]*>.*?</\1>',
        '', raw_html, flags=_re_module.DOTALL | _re_module.IGNORECASE
    )
    # 移除 HTML 标签
    cleaned = _re_module.sub(r'<[^>]+>', '\n', cleaned)
    # 解码 HTML 实体
    cleaned = _html_module.unescape(cleaned)
    # 合并空白行
    cleaned = _re_module.sub(r'\n\s*\n+', '\n\n', cleaned)
    # 去除首尾空白
    cleaned = cleaned.strip()

    # 尝试提取引号内的对话文本（中英文引号）
    quoted_texts = _re_module.findall(r'["""]([^"""]{20,})["'']', cleaned)
    if quoted_texts:
        quotes_block = "\n\n".join(
            "💬 {0}".format(q.strip()) for q in quoted_texts[:20]
        )
    else:
        quotes_block = ""

    # ========== 策略 D：返回页面纯文本 ==========
    # 截取前 8000 字符
    plain_text = cleaned[:8000] if len(cleaned) > 8000 else cleaned

    # ---- 组合所有策略结果 ----
    final_parts = []
    if meta_result:
        final_parts.append(meta_result.strip())
    if quotes_block:
        final_parts.append(quotes_block.strip())
    if plain_text and not quotes_block:
        final_parts.append(plain_text.strip())

    if final_parts:
        combined = "\n\n---\n\n".join(final_parts)
        if len(combined) > 30:
            return True, combined

    return False, "(无法从该 Gemini 链接中解析出有效对话内容，请确认链接为公开分享链接)"


# ---- 6c. 辅助工具函数 ----

def _load_deepseek_api_key():
    """优先从环境变量 DEEPSEEK_API_KEY 读取，其次从 secrets.txt。"""
    env_key = os.environ.get("DEEPSEEK_API_KEY", "").strip()
    if env_key:
        return env_key

    if SECRETS_FILE.exists():
        raw = SECRETS_FILE.read_text(encoding="utf-8", errors="ignore")
        for line in raw.split("\n"):
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            if "=" in line:
                key_part, _, val_part = line.partition("=")
                if key_part.strip().lower() in (
                    "deepseek_api_key", "deepseek_key", "deepseek-api-key"
                ):
                    return val_part.strip().strip('"').strip("'")
            if line.lower().startswith("sk-") and "deepseek" in raw.lower():
                return line

    return ""


def _load_gemini_links_as_menu():
    """从 secrets.txt 提取所有 Gemini 分享链接，组装为菜单列表。"""
    if not SECRETS_FILE.exists():
        return []

    raw = SECRETS_FILE.read_text(encoding="utf-8", errors="ignore").strip()
    result = []
    idx = 0
    for line in raw.split("\n"):
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "gemini" in line.lower() or "g.co/gemini" in line.lower():
            idx += 1
            if "=" in line and not line.lower().startswith("http"):
                label_part, _, url_part = line.partition("=")
                label = label_part.strip()
                url = url_part.strip().strip('"').strip("'")
            else:
                url = line
                label = "Gemini 对话锚点 {0}".format(idx)
            result.append((idx, url, label))

    return result


def _load_master_wisdom_text():
    """全量读取 master_wisdom.md 大师沉淀全文。"""
    if MASTER_WISDOM_FILE.exists():
        text = MASTER_WISDOM_FILE.read_text(encoding="utf-8", errors="ignore")
        if text.strip():
            return text
    return "（大师沉淀文件尚未生成。请先确保同步流水线阶段 3 成功摄入大师方法论。）"


def _build_system_prompt(anchor_link_url=None, scraped_content=None):
    """
    构建 DeepSeek System Prompt。
    核心：全量注入 master_wisdom.md 大师思想钢印 + Gemini 锚点爬取内容。
    """
    master_text = _load_master_wisdom_text()

    anchor_block = ""
    if anchor_link_url and scraped_content:
        anchor_block = (
            "\n## 🔗 当前探讨锚点 — 已从 Gemini 链接爬取完整对话内容\n"
            "用户选择了以下 Gemini 私有对话作为本次脑暴的上下文锚点：\n"
            "{0}\n\n"
            "### 📡 爬取的原始对话内容（全量注入）\n\n"
            "{1}\n\n"
            "请深度消化以上锚点内容，与大师方法论融会贯通后展开探讨。\n"
        ).format(anchor_link_url, scraped_content)
    elif anchor_link_url:
        anchor_block = (
            "\n## 🔗 当前探讨锚点\n"
            "用户选择了以下 Gemini 对话链接作为探讨锚点：\n{0}\n"
            "（注意：该链接内容未能成功爬取，请用户手动提供关键信息。）\n"
        ).format(anchor_link_url)

    prompt = (
        "你是 sync_master_factory 内置的 DeepSeek 大师级 AI 脑暴顾问，"
        "运行在用户的 Obsidian 知识库环境中。\n\n"
        "## 🧠 大师思想钢印 —— 必须内化并贯彻以下方法论\n\n"
        "{master_wisdom}\n"
        "{anchor_block}\n"
        "## 仓库上下文\n"
        "- 根目录：{vault_root}\n"
        "- 知识库目录：{knowledge_dir}\n"
        "- 大师沉淀文件：{master_wisdom_file}\n"
        "- 脑暴存档目录：{thought_packages_dir}\n\n"
        "## 行为准则\n"
        "1. 用中文回复（除非用户用英文提问）。\n"
        "2. 以大师沉淀中的方法论为最高指导思想，融会贯通后给出洞见。\n"
        "3. 回答简洁有力，直击要害，敢于提出不同角度甚至反向观点。\n"
        "4. 支持连续追问和深度展开，像真正的顾问一样主动追问用户未言明的需求。\n"
        "5. 涉及代码操作时，给出可直接运行的 Python/Bash 代码片段。\n"
        "6. 绝不泄露 API Key 或隐私配置。\n"
        "7. 如果你的知识截止日期之前的信息与用户本地知识库矛盾，以用户知识库为准。"
    ).format(
        master_wisdom=master_text,
        anchor_block=anchor_block,
        vault_root=str(VAULT_ROOT),
        knowledge_dir=str(KNOWLEDGE_DIR),
        master_wisdom_file=str(MASTER_WISDOM_FILE),
        thought_packages_dir=str(THOUGHT_PACKAGES_DIR),
    )

    return prompt


def _call_deepseek_api(client, system_prompt, history, config):
    """
    通过 OpenAI SDK 调用 DeepSeek API。
    支持流式和非流式。返回 assistant 回复文本；失败返回 None。
    """
    messages = [{"role": "system", "content": system_prompt}] + history

    try:
        if config.get("stream", True):
            print()
            print("┌" + "─" * 66 + "┐")
            print("│" + "  🤖 DeepSeek 回复".ljust(66) + "│")
            print("└" + "─" * 66 + "┘")
            print()

            stream = client.chat.completions.create(
                model=config["model"],
                messages=messages,
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
                stream=True,
            )

            full_text_parts = []
            for chunk in stream:
                if chunk.choices and len(chunk.choices) > 0:
                    delta = chunk.choices[0].delta
                    if delta and delta.content:
                        sys.stdout.write(delta.content)
                        sys.stdout.flush()
                        full_text_parts.append(delta.content)

            print()
            print("─" * 68)
            return "".join(full_text_parts)

        else:
            sys.stdout.write("  💭 思考中...")
            sys.stdout.flush()

            response = client.chat.completions.create(
                model=config["model"],
                messages=messages,
                max_tokens=config["max_tokens"],
                temperature=config["temperature"],
                stream=False,
            )

            sys.stdout.write("\r" + " " * 30 + "\r")
            sys.stdout.flush()

            print()
            print("┌" + "─" * 66 + "┐")
            print("│" + "  🤖 DeepSeek 回复".ljust(66) + "│")
            print("└" + "─" * 66 + "┘")
            print()

            text = ""
            if response.choices and len(response.choices) > 0:
                msg = response.choices[0].message
                if msg and msg.content:
                    text = msg.content
                    print(text)

            print()
            print("─" * 68)
            return text

    except Exception as e:
        sys.stdout.write("\r" + " " * 30 + "\r")
        sys.stdout.flush()
        error_msg = str(e)
        if "401" in error_msg or "auth" in error_msg.lower():
            print("\n  🔐 DeepSeek API Key 无效或过期。")
        elif "429" in error_msg or "rate" in error_msg.lower():
            print("\n  ⏳ API 速率限制，请稍后重试。")
        elif "402" in error_msg or "insufficient" in error_msg.lower() or "balance" in error_msg.lower():
            print("\n  💰 DeepSeek 账户余额不足，请充值。")
        elif "connection" in error_msg.lower() or "timeout" in error_msg.lower():
            print("\n  🌐 网络连接异常: {0}".format(error_msg[:200]))
        else:
            print("\n  ❌ API 调用异常: {0}".format(error_msg[:300]))
        return None


def _extract_first_sentence(text):
    """从文本中提取第一句有意义的话，用作文件名主干。最长 60 字符。"""
    if not text:
        return "untitled"
    clean = text.strip()
    cutoff = len(clean)
    for sep in ("。", "？", "！", ".", "?", "!", "\n"):
        pos = clean.find(sep)
        if pos > 0 and pos < cutoff:
            cutoff = pos
    result = clean[:cutoff].strip()
    unsafe_chars = r'<>:"/\|?*'
    for ch in unsafe_chars:
        result = result.replace(ch, "")
    result = result.strip()
    if len(result) > 60:
        result = result[:60]
    return result if result else "untitled"


def _estimate_tokens(text):
    """粗略估算 token 数量。"""
    if not text:
        return 0
    chinese_chars = sum(1 for c in text if '一' <= c <= '鿿' or '㐀' <= c <= '䶿')
    other_chars = len(text) - chinese_chars
    return int(chinese_chars / 1.5 + other_chars / 4)


def _trim_history(history, max_turns):
    """保留最近 max_turns 轮对话，超出截断。"""
    max_messages = max_turns * 2
    if len(history) <= max_messages:
        return history
    removed = (len(history) - max_messages) // 2
    print("\n  📜 (已自动截断 {0} 轮早期对话以控制上下文长度)\n".format(removed))
    return history[-max_messages:]


def _export_clean_messages(history):
    """从对话历史提取纯净 Q&A 对（不含 system prompt）。返回 (md_text, feishu_text)。"""
    lines = [
        "# 💬 DeepSeek 大师脑暴对话记录",
        "",
        "> 导出时间: {0}".format(datetime.now(CN_TZ).strftime("%Y-%m-%d %H:%M CST")),
        "",
    ]

    qa_pairs = []
    i = 0
    while i < len(history):
        user_msg = None
        assistant_msg = None
        if i < len(history) and history[i]["role"] == "user":
            user_msg = history[i]
            i += 1
        if i < len(history) and history[i]["role"] == "assistant":
            assistant_msg = history[i]
            i += 1

        if user_msg:
            q_num = len(qa_pairs) + 1
            lines.append("---")
            lines.append("")
            lines.append("### ❓ Q{0}".format(q_num))
            lines.append("")
            lines.append(user_msg["content"])
            lines.append("")

            if assistant_msg:
                lines.append("### 💡 A{0}".format(q_num))
                lines.append("")
                lines.append(assistant_msg["content"])
                lines.append("")

            qa_pairs.append({
                "q": user_msg["content"],
                "a": assistant_msg["content"] if assistant_msg else "(未回复)",
            })

    md_text = "\n".join(lines)

    total = len(qa_pairs)
    feishu_title = "## 💬 DeepSeek 大师脑暴对话\n"
    feishu_summary = "共 {0} 轮问答\n\n".format(total)
    feishu_body = ""
    recent = qa_pairs[-3:] if total > 3 else qa_pairs
    for pair in recent:
        q_idx = qa_pairs.index(pair) + 1
        feishu_body += "**Q{0}**: {1}\n\n**A{0}**: {2}\n\n---\n\n".format(
            q_idx, pair["q"][:200], pair["a"][:300]
        )
    feishu_full = feishu_title + feishu_summary + feishu_body

    return md_text, feishu_full


def _send_to_feishu_webhook(content):
    """通过飞书 Webhook 推送卡片消息。"""
    webhook_url = os.environ.get("FEISHU_WEBHOOK_URL", "").strip()

    if not webhook_url and SECRETS_FILE.exists():
        raw = SECRETS_FILE.read_text(encoding="utf-8", errors="ignore").strip()
        for line in raw.split("\n"):
            line = line.strip()
            if line.startswith("#") or "=" not in line:
                continue
            key_part, _, val_part = line.partition("=")
            if key_part.strip().lower() in (
                "feishu_webhook", "feishu_webhook_url", "feishu-webhook"
            ):
                webhook_url = val_part.strip().strip('"').strip("'")
                break

    if not webhook_url:
        return False, (
            "未配置飞书 Webhook URL。"
            "请在 secrets.txt 中添加 feishu_webhook=https://open.feishu.cn/open-apis/bot/v2/hook/..."
        )

    try:
        payload = json.dumps({
            "msg_type": "interactive",
            "card": {
                "header": {
                    "title": {"tag": "plain_text", "content": "DeepSeek 大师脑暴对话"},
                    "template": "blue",
                },
                "elements": [
                    {
                        "tag": "markdown",
                        "content": content[:3000],
                    }
                ],
            },
        }, ensure_ascii=False).encode("utf-8")

        req = urllib.request.Request(
            webhook_url,
            data=payload,
            headers={"Content-Type": "application/json; charset=utf-8"},
        )
        with urllib.request.urlopen(req, timeout=10) as resp:
            if resp.status == 200:
                return True, "飞书推送成功！"
            else:
                return False, "飞书推送返回 HTTP {0}".format(resp.status)
    except Exception as e:
        return False, "飞书推送失败: {0}".format(str(e)[:100])


def _handle_slash_command(cmd_line, history, config):
    """
    处理三大核心指令 + 辅助指令。
    返回 (handled: bool, should_exit: bool, message: str)
    """
    parts = cmd_line.strip().split(maxsplit=1)
    cmd = parts[0].lower()
    arg = parts[1] if len(parts) > 1 else ""

    if cmd in ("/exit", "/quit", "/q"):
        return True, True, "👋 大师脑暴密室已关闭。知识已沉淀，下次见！"

    if cmd == "/save":
        if not history:
            return True, False, "📭 当前无对话可保存。"
        THOUGHT_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
        first_user = ""
        for msg in history:
            if msg["role"] == "user":
                first_user = msg["content"]
                break
        stem = _extract_first_sentence(first_user)
        date_str = datetime.now(CN_TZ).strftime("%Y%m%d_%H%M")
        filename = "{0}_{1}.md".format(date_str, stem)
        filepath = THOUGHT_PACKAGES_DIR / filename
        md_text, _ = _export_clean_messages(history)
        filepath.write_text(md_text, encoding="utf-8")
        return True, False, "💾 对话已落盘 → {0}".format(filepath.relative_to(VAULT_ROOT))

    if cmd == "/to_feishu":
        if not history:
            return True, False, "📭 当前无对话可导出。"
        md_text, feishu_text = _export_clean_messages(history)
        THOUGHT_PACKAGES_DIR.mkdir(parents=True, exist_ok=True)
        date_str = datetime.now(CN_TZ).strftime("%Y%m%d_%H%M")
        feishu_file = THOUGHT_PACKAGES_DIR / "feishu_export_{0}.md".format(date_str)
        feishu_file.write_text(md_text, encoding="utf-8")
        ok, msg = _send_to_feishu_webhook(feishu_text)
        result_lines = [
            "📋 纯净 Q&A 已导出 → {0}".format(feishu_file.relative_to(VAULT_ROOT)),
            "📡 飞书推送: {0}".format(msg),
        ]
        return True, False, "\n".join(result_lines)

    if cmd == "/model":
        return True, False, "🎛️  当前模型: {0} (DeepSeek)\nBase URL: {1}".format(
            config["model"], config["base_url"])

    if cmd == "/temp":
        if not arg:
            return True, False, "🌡️  当前 temperature: {0}".format(config["temperature"])
        try:
            t = float(arg)
            if 0.0 <= t <= 2.0:
                config["temperature"] = t
                return True, False, "✅ temperature 已设为 {0}".format(t)
            return True, False, "❌ temperature 范围: 0.0 ~ 2.0"
        except ValueError:
            return True, False, "❌ 请输入数字，如 /temp 0.5"

    if cmd in ("/clear", "/cls"):
        history.clear()
        return True, False, "🧹 对话历史已清空。"

    if cmd == "/history":
        if not history:
            return True, False, "📭 当前无对话历史。"
        turns = len(history) // 2
        lines = ["📜 当前对话 ({0} 轮):".format(turns)]
        for i, msg in enumerate(history):
            role = "👤 You" if msg["role"] == "user" else "🤖 DeepSeek"
            preview = msg["content"][:80].replace("\n", " ")
            lines.append("  [{0}] {1}: {2}...".format(i, role, preview))
        return True, False, "\n".join(lines)

    if cmd == "/stream":
        if arg.lower() in ("off", "false", "0", "no", "关"):
            config["stream"] = False
            return True, False, "📝 流式输出已关闭"
        else:
            config["stream"] = True
            return True, False, "🌊 流式输出已开启"

    if cmd in ("/help", "/?"):
        help_text = (
            "📋 大师脑暴室指令清单:\n"
            "  /exit, /quit, /q  —— 优雅退出\n"
            "  /save             —— 落盘到 thought-packages/\n"
            "  /to_feishu        —— 纯净 Q&A 导出 + 飞书推送\n"
            "  /clear, /cls      —— 清空对话历史\n"
            "  /history          —— 对话摘要\n"
            "  /model            —— 当前模型\n"
            "  /temp [值]        —— temperature 调节\n"
            "  /stream on|off    —— 流式开关\n"
            "  /help, /?         —— 显示帮助"
        )
        return True, False, help_text

    return False, False, ""


def _print_gemini_menu(gemini_links):
    """打印 Gemini 私有链接数字菜单。"""
    print()
    print("=" * 60)
    print("📡  Gemini 私有链接连接池 —— 选择脑暴锚点")
    print("=" * 60)
    print()
    for idx, url, label in gemini_links:
        if len(url) > 50:
            masked = url[:25] + "***" + url[-20:]
        else:
            masked = url[:15] + "***"
        print("  [{0}] {1}".format(idx, label))
        print("      🔗 {0}".format(masked))
    print()
    print("  [回车] 自由大师探讨模式（不设锚点）")
    print("─" * 60)


# ---- 6d. 核心对话循环 ----

def interactive_chat(secrets_data):
    """
    【DeepSeek 大师脑暴室 —— 完整版】
    1. 检测 DEEPSEEK_API_KEY
    2. Gemini 菜单选择探讨锚点 → 爬取链接真实对话内容
    3. 全量注入 master_wisdom.md 大师思想钢印 + 爬取内容
    4. 进入多轮对话循环
    """
    # ---- 加载 API Key ----
    api_key = _load_deepseek_api_key()

    if not api_key:
        print("\n" + "=" * 60)
        print("💬  [阶段 6/6] DeepSeek 大师脑暴室")
        print("=" * 60)
        print()
        print("  ⚠️  未检测到 DEEPSEEK_API_KEY。")
        print()
        print("  配置方法（任选一种）：")
        print("    1. 设置环境变量: set DEEPSEEK_API_KEY=sk-...")
        print("    2. 在 secrets.txt 中添加: DEEPSEEK_API_KEY=sk-...")
        print()
        print("  💡 配置好后重新运行脚本即可自动进入大师脑暴室。")
        print("  🏁 sync_master_factory.py 同步流水线执行完毕。\n")
        return

    # ---- 初始化 OpenAI SDK（指向 DeepSeek） ----
    try:
        from openai import OpenAI
    except ImportError:
        print("\n  ⚠️  未安装 openai SDK。请运行: pip install openai")
        print("  🏁 跳过对话模式，同步流水线已完成。\n")
        return

    client = OpenAI(api_key=api_key, base_url=CHAT_CONFIG["base_url"])

    # ---- 对话状态 ----
    history = []
    chat_config = dict(CHAT_CONFIG)

    # ---- Gemini 菜单 + 爬取 ----
    gemini_links = secrets_data.get("_gemini_link_list", [])
    anchor_link_url = None
    scraped_content = None

    if gemini_links:
        _print_gemini_menu(gemini_links)
        try:
            choice = input("  👉 请输入数字选择锚点（直接回车 = 自由模式）: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  👋 已取消。\n")
            return

        if choice.isdigit():
            idx_choice = int(choice)
            for idx, url, label in gemini_links:
                if idx == idx_choice:
                    anchor_link_url = url
                    print("\n  🔗 已选择锚点 [{0}] {1}".format(idx, label))
                    break
            if anchor_link_url is None:
                print("\n  ⚠️  无效序号，自动进入自由大师探讨模式。")
        else:
            print("\n  🕊️  进入自由大师探讨模式。")

    # ---- 如果选择了锚点，爬取 Gemini 链接真实内容 ----
    if anchor_link_url:
        print("  🌐 正在爬取 Gemini 链接中的真实对话内容...")
        ok, content = _scrape_gemini_share(anchor_link_url)
        if ok:
            scraped_content = content
            preview = content[:200].replace("\n", " ")
            print("  ✅ 爬取成功！获取 {0} 字符对话数据。".format(len(content)))
            print("  📄 内容预览: {0}...".format(preview))
        else:
            print("  ⚠️  爬取失败: {0}".format(content))
            print("  💡 将仅以链接 URL 作为锚点继续探讨。")

    # ---- 构建 System Prompt ----
    system_prompt = _build_system_prompt(
        anchor_link_url=anchor_link_url,
        scraped_content=scraped_content,
    )

    # ---- 欢迎界面 ----
    print()
    print("=" * 60)
    print("💬  [阶段 6/6] DeepSeek 大师脑暴室")
    print("=" * 60)
    print("""
  🎛️  模型: {model}
  🌡️  Temperature: {temp}
  📜 上下文窗口: 最近 {turns} 轮
  🌊 流式输出: {stream}
  🧠 思想钢印: master_wisdom.md 全量注入
  {anchor_status}

  ⌨️   /help 查看指令  |  /exit 退出密室
  ──────────────────────────────────────────────────
""".format(
        model=chat_config["model"],
        temp=chat_config["temperature"],
        turns=chat_config["max_history_turns"],
        stream="开" if chat_config["stream"] else "关",
        anchor_status=(
            "🔗 Gemini 锚点: 已爬取并注入 {0} 字符对话数据".format(len(scraped_content))
            if scraped_content else
            "🔗 Gemini 锚点: {0} (未爬取到内容)".format(anchor_link_url)
            if anchor_link_url else
            "🕊️  自由探讨模式"
        ),
    ))

    # ---- 主循环 ----
    while True:
        try:
            user_input = input("  👤 You: ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n  👋 大师脑暴密室已关闭。下次见！\n")
            break

        if not user_input:
            continue

        if user_input.startswith("/"):
            handled, should_exit, message = _handle_slash_command(
                user_input, history, chat_config
            )
            if handled:
                print("\n  {0}\n".format(message))
                if should_exit:
                    break
                continue

        history.append({"role": "user", "content": user_input})

        assistant_text = _call_deepseek_api(client, system_prompt, history, chat_config)

        if assistant_text is not None:
            history.append({"role": "assistant", "content": assistant_text})
            history = _trim_history(history, chat_config["max_history_turns"])
            total_est = _estimate_tokens(system_prompt) + sum(
                _estimate_tokens(m["content"]) for m in history
            )
            print(
                "  📊 上下文 ~{0:,} tokens | /save 落盘 | /to_feishu 导出 | /exit 退出"
                .format(total_est)
            )
            print()
        else:
            history.pop()
            print("  💡 API 调用失败，可直接重新输入或 /help 查看指令。\n")

    print("🏁 sync_master_factory.py 全流程完毕。\n")


# ============================================================================
# 🎯 主入口
# ============================================================================

if __name__ == "__main__":
    sys.exit(main())
