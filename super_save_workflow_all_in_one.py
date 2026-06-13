#!/usr/bin/env python3
"""
super_save_workflow_all_in_one.py
==================================
小鹅通直播回放 · 全自动化深度处理工作流（v5.0 终极飞书闭环版）

用法：
    python super_save_workflow_all_in_one.py                                    # 默认 = 模式1
    python super_save_workflow_all_in_one.py --mode 1                           # 全自动一键通关
    python super_save_workflow_all_in_one.py --mode 1 --input "飞书URL"          # 🆕 飞书链接直输，0秒跳过ASR
    python super_save_workflow_all_in_one.py --mode 2                           # 断点续跑（跳过ASR）
    python super_save_workflow_all_in_one.py --mode 2 --input "飞书URL"          # 🆕 飞书链接→抓取→续跑
    python super_save_workflow_all_in_one.py --mode 3                           # 交互式深度对话
    python super_save_workflow_all_in_one.py --mode 3 --input "飞书URL"          # 🆕 带来源链接 + /to_feishu

模式说明：
    模式1  全自动一键通关
           新音频 → faster-whisper ASR → 分段清洗 → 提炼金句+待办
           → 顾问深度探讨 → 输出 .md 报告 + chat_session.json
           🆕 支持 --input 飞书链接：在线抓取妙记/文档文本 → 0秒跳过ASR
    模式2  断点续跑（省钱/防报错）
           跳过 ASR 阶段，直接读取已有的 temporary_raw.txt
           → 重新云端清洗 → 生成新报告（不重复消耗本地算力）
           🆕 支持 --input 飞书链接：先从飞书抓取文本 → 保存 raw → 清洗
    模式3  交互式深度对话
           加载 chat_session.json 中的完整报告背景
           在终端开启多轮对话，AI 始终保持「资深商业咨询顾问」角色
           🆕 置顶看板展示来源链接 · 支持 /to_feishu 一键导出飞书文档

🆕 v5.0 终极飞书闭环三大升级：
    ①【飞书链接直接输入】--input "飞书URL" → 在线解析妙记/文档文本 → 0秒跳过ASR
    ②【模式3链接醒目置顶】==== 看板钉住来源链接 → 存入 chat_session.json 元数据
    ③【一键转飞书文档】  /to_feishu → 将全部对话内容生成飞书云文档 → 高亮打印链接
"""

from __future__ import annotations

import os
import sys
import json
import re
import shutil
import zipfile
import argparse
import subprocess
import urllib.request
import urllib.error
from datetime import datetime, timezone
from pathlib import Path

# =========================================================================
# 【配置区】你的 API 密钥 & 模型参数
# =========================================================================
API_KEY = "YOUR_DEEPSEEK_API_KEY"  # ⚠️ 请填入你的 DeepSeek API Key
BASE_URL = "https://api.deepseek.com/v1"
MODEL_NAME = "deepseek-chat"

# =========================================================================
# 🆕【飞书开放平台配置】—— v5.0 终极飞书闭环专属
# =========================================================================
#   📌 申请步骤（请按以下顺序操作）：
#   1. 打开 飞书开放平台：https://open.feishu.cn
#   2. 登录后进入「开发者后台」→ 创建或选择一个企业自建应用
#   3. 在应用页面左侧「凭证与基础信息」中，复制以下两项并填入下方：
#        - App ID     → 填入 FEISHU_APP_ID
#        - App Secret → 填入 FEISHU_APP_SECRET
#   4. 在应用页面左侧「权限管理」中，搜索并开通以下权限：
#        - 文档(docx)：docx:document:create（创建文档）
#                       docx:document:readonly（读取文档内容）
#        - 妙记(minutes)：minutes:minute:readonly（读取妙记内容）
#        - 通讯录：contact:user.id:readonly（读取用户身份，创建文档时需要）
#   5. 权限开通后，点击右上角「创建版本」→ 填写版本号 → 「发布」→ 等待管理员审批
#   6. 审批通过后即可使用 --input 飞书链接 和 /to_feishu 功能！
#
#   ⚠️ 如果暂不需要飞书功能，留空即可——脚本其余功能完全不受影响。
# =========================================================================
FEISHU_APP_ID = ""       # TODO: 去 https://open.feishu.cn 申请后填入
FEISHU_APP_SECRET = ""   # TODO: 去 https://open.feishu.cn 申请后填入
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# =========================================================================
# 路径常量（所有中间产物和输出都在这几个目录里）
# =========================================================================
PROJECT_DIR = Path(__file__).resolve().parent
BIN_DIR = PROJECT_DIR / ".ffmpeg"
MODEL_CACHE_DIR = PROJECT_DIR / "model_cache"
INPUT_DIR = PROJECT_DIR / "input_audio"
OUTPUT_DIR = PROJECT_DIR / "output_result"

AUDIO_FILE = INPUT_DIR / "live_audio.mp3"
RAW_TEXT_FILE = PROJECT_DIR / "temporary_raw.txt"
REPORT_FILE = OUTPUT_DIR / "final_report.md"
CHAT_HISTORY_FILE = OUTPUT_DIR / "chat_session.json"

FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"

# 🆕 全局变量：当前任务的来源链接（由 --input 设置）
SOURCE_URL: str | None = None

# =========================================================================
# 0.  环境自动补全 —— pip 包 + ffmpeg，Windows 免手动配置
# =========================================================================

def _ensure_packages() -> None:
    """
    自动检测并安装缺失的 Python 依赖包。
    首次运行会自动 pip install，之后秒过。
    """
    required = {
        "faster_whisper": "faster-whisper",
        "openai": "openai",
        "imageio_ffmpeg": "imageio-ffmpeg",
    }
    for import_name, pip_name in required.items():
        try:
            __import__(import_name)
        except ImportError:
            print(f"[环境] 缺少 {pip_name}，正在自动安装...")
            subprocess.check_call(
                [sys.executable, "-m", "pip", "install", "--quiet", pip_name]
            )
            print(f"[环境] {pip_name} 安装完成！")


# --- ffmpeg 四级降级检测 ---

def _ffmpeg_from_path() -> str | None:
    """策略 1：系统 PATH 中是否已有 ffmpeg。"""
    return shutil.which("ffmpeg")


def _ffmpeg_from_project() -> str | None:
    """策略 2：项目 .ffmpeg/ 下是否已有上次下载的便携版。"""
    for pattern in ("ffmpeg.exe", "ffmpeg"):
        for candidate in BIN_DIR.rglob(pattern):
            if candidate.is_file():
                return str(candidate)
    return None


def _ffmpeg_from_imageio() -> str | None:
    """策略 3：imageio-ffmpeg 自带静态编译版。"""
    try:
        import imageio_ffmpeg
        path = imageio_ffmpeg.get_ffmpeg_exe()
        if path and Path(path).is_file():
            return path
    except ImportError:
        pass
    return None


def _ffmpeg_download() -> str:
    """
    策略 4：自动下载 Windows 轻量版 ffmpeg（Gyan essentials build），
    解压出 ffmpeg.exe 放入 .ffmpeg/，用完即删 zip。
    """
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = BIN_DIR / "ffmpeg-release-essentials.zip"

    print("[ffmpeg] 未检测到系统 ffmpeg，自动下载便携版（约 30 MB）...")
    print(f"[ffmpeg] 来源：{FFMPEG_DOWNLOAD_URL}")
    urllib.request.urlretrieve(FFMPEG_DOWNLOAD_URL, zip_path)
    print("[ffmpeg] 下载完成，正在解压...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        for name in zf.namelist():
            if name.endswith("ffmpeg.exe") and "/bin/" in name.replace("\\", "/"):
                dest = BIN_DIR / "ffmpeg.exe"
                with zf.open(name) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                break
        else:
            raise RuntimeError(
                "[ffmpeg] 压缩包中未找到 ffmpeg.exe，请手动安装："
                "https://ffmpeg.org/download.html"
            )

    zip_path.unlink()
    exe = BIN_DIR / "ffmpeg.exe"
    if not exe.exists():
        raise RuntimeError("[ffmpeg] 解压失败，请检查磁盘空间或网络。")
    print(f"[ffmpeg] 便携版就绪：{exe}")
    return str(exe)


def _patch_env_for_ffmpeg(ffmpeg_path: str) -> None:
    """将 ffmpeg 所在目录注入 PATH 并设置 FFMPEG_BINARY 环境变量。"""
    ffmpeg_dir = str(Path(ffmpeg_path).parent)
    sep = os.pathsep
    os.environ["PATH"] = f"{ffmpeg_dir}{sep}{os.environ.get('PATH', '')}"
    os.environ["FFMPEG_BINARY"] = ffmpeg_path


def resolve_ffmpeg() -> str:
    """
    四级降级：系统 PATH → 项目缓存 → imageio-ffmpeg → 自动下载。
    返回 ffmpeg 可执行文件路径，并自动注入环境变量。
    """
    ffmpeg = (
        _ffmpeg_from_path()
        or _ffmpeg_from_project()
        or _ffmpeg_from_imageio()
    )
    if not ffmpeg:
        if sys.platform == "win32":
            ffmpeg = _ffmpeg_download()
        else:
            raise RuntimeError(
                "[ffmpeg] 未找到 ffmpeg。请手动安装：\n"
                "  macOS:  brew install ffmpeg\n"
                "  Linux:  sudo apt install ffmpeg\n"
                "  或执行: pip install imageio-ffmpeg"
            )
    _patch_env_for_ffmpeg(ffmpeg)
    print(f"[ffmpeg] ✅ 已激活：{ffmpeg}")
    return ffmpeg


# =========================================================================
# 1.  共享工具函数
# =========================================================================

def chunk_text(text: str, max_len: int = 12000) -> list[str]:
    """将长文本按字符数切片，防止大模型 Token 溢出。"""
    return [text[i:i + max_len] for i in range(0, len(text), max_len)]


def create_client():
    """创建 OpenAI 兼容客户端（DeepSeek / 豆包 均适用）。"""
    from openai import OpenAI
    return OpenAI(api_key=API_KEY, base_url=BASE_URL)


def banner(mode: int, title: str) -> None:
    """打印统一风格的模式标题。"""
    bar = "=" * 62
    print(f"\n{bar}")
    print(f"  模式 {mode} · {title}")
    print(f"{bar}\n")


def _now_iso() -> str:
    """返回当前 UTC 时间的 ISO 8601 字符串。"""
    return datetime.now(timezone.utc).isoformat()


# =========================================================================
# 🆕 1.5  飞书工具函数（v5.0 终极飞书闭环）
# =========================================================================

# --- 飞书 URL 检测与解析 ---

_FEISHU_URL_PATTERNS = {
    "minutes": re.compile(
        r"https?://[\w.-]+\.feishu\.cn/minutes/([a-zA-Z0-9]+)"
    ),
    "docx": re.compile(
        r"https?://[\w.-]+\.feishu\.cn/docx/([a-zA-Z0-9]+)"
    ),
    "docs": re.compile(
        r"https?://[\w.-]+\.feishu\.cn/docs/([a-zA-Z0-9]+)"
    ),
    "wiki": re.compile(
        r"https?://[\w.-]+\.feishu\.cn/wiki/([a-zA-Z0-9]+)"
    ),
}


def is_feishu_url(url: str) -> bool:
    """判断一个字符串是否为飞书链接。"""
    if not url:
        return False
    return any(pattern.search(url) for pattern in _FEISHU_URL_PATTERNS.values())


def _parse_feishu_url(url: str) -> tuple[str, str] | None:
    """
    解析飞书链接，返回 (类型, 资源ID)。
    类型：minutes / docx / docs / wiki
    如果无法识别则返回 None。
    """
    for url_type, pattern in _FEISHU_URL_PATTERNS.items():
        match = pattern.search(url)
        if match:
            return (url_type, match.group(1))
    return None


# --- 飞书 Open API 鉴权 ---

def _get_feishu_tenant_token() -> str:
    """
    获取飞书 tenant_access_token。
    需要先在配置区填入 FEISHU_APP_ID 和 FEISHU_APP_SECRET。
    """
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        raise RuntimeError(
            "❌ 飞书 API 未配置！\n"
            "   请先打开脚本，在顶部【飞书开放平台配置】区域填入：\n"
            "     FEISHU_APP_ID  = '你的App ID'\n"
            "     FEISHU_APP_SECRET = '你的App Secret'\n"
            "   申请地址：https://open.feishu.cn"
        )

    token_url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
    body = json.dumps({
        "app_id": FEISHU_APP_ID,
        "app_secret": FEISHU_APP_SECRET,
    }).encode("utf-8")

    req = urllib.request.Request(
        token_url, data=body,
        headers={"Content-Type": "application/json; charset=utf-8"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode("utf-8"))
    except urllib.error.HTTPError as e:
        raise RuntimeError(
            f"❌ 飞书鉴权失败（HTTP {e.code}）：{e.reason}\n"
            "   请检查 FEISHU_APP_ID 和 FEISHU_APP_SECRET 是否正确。"
        )
    except Exception as e:
        raise RuntimeError(f"❌ 无法连接飞书 API：{e}")

    if data.get("code") != 0:
        raise RuntimeError(
            f"❌ 飞书鉴权失败：{data.get('msg', '未知错误')}\n"
            "   请确认应用已发布且审批通过。"
        )
    return data["tenant_access_token"]


def _feishu_api_get(endpoint: str, token: str) -> dict:
    """飞书 GET 请求通用封装。"""
    url = f"{FEISHU_BASE_URL}{endpoint}"
    req = urllib.request.Request(
        url,
        headers={"Authorization": f"Bearer {token}"},
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(
            f"❌ 飞书 API 调用失败：{result.get('msg', '未知错误')}"
        )
    return result.get("data", {})


def _feishu_api_post(endpoint: str, token: str, body: dict) -> dict:
    """飞书 POST 请求通用封装。"""
    url = f"{FEISHU_BASE_URL}{endpoint}"
    data = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url, data=data,
        headers={
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        },
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
    if result.get("code") != 0:
        raise RuntimeError(
            f"❌ 飞书 API 调用失败：{result.get('msg', '未知错误')}"
        )
    return result.get("data", {})


# --- 飞书内容抓取 ---

def _fetch_feishu_docx_raw(doc_id: str, token: str) -> str:
    """
    通过飞书文档 API 获取文档纯文本内容。
    文档 ID 格式示例：doxcnXXXXXXXXXXXX
    """
    endpoint = f"/docx/v1/documents/{doc_id}/raw_content"
    data = _feishu_api_get(endpoint, token)
    content = data.get("content", "")
    if not content:
        raise RuntimeError("❌ 飞书文档内容为空，请确认该文档可被当前应用读取。")
    return content


def _fetch_feishu_minutes_text(minute_token: str, token: str) -> str:
    """
    通过飞书妙记 API 获取会议纪要/转写文本。
    妙记 token 格式示例：obcnXXXXXXXXXXXX

    飞书妙记 API 流程：
    1. 先获取妙记基本信息
    2. 获取转写/段落文本
    """
    # 获取妙记基本信息
    minute_data = _feishu_api_get(f"/minutes/v1/minutes/{minute_token}", token)

    # 尝试从 blocks/paragraphs 中提取文本
    # 飞书妙记内容存在于 blocks 字段中
    blocks = minute_data.get("blocks", [])
    if blocks:
        lines: list[str] = []
        for block in blocks:
            block_type = block.get("block_type", 0)
            if block_type == 1:  # 标题
                title_text = ""
                for elem in block.get("text", {}).get("elements", []):
                    title_text += elem.get("text_run", {}).get("content", "")
                if title_text.strip():
                    lines.append(f"\n## {title_text}\n")
            elif block_type == 2:  # 文本段落
                para_text = ""
                for elem in block.get("text", {}).get("elements", []):
                    para_text += elem.get("text_run", {}).get("content", "")
                if para_text.strip():
                    lines.append(para_text)
        if lines:
            return "\n\n".join(lines)

    # 如果没有 blocks，尝试从其他字段提取
    # 有些妙记版本可能直接在 paragraphs 字段中
    paragraphs = minute_data.get("paragraphs", [])
    if paragraphs:
        para_lines = []
        for p in paragraphs:
            text = p.get("text", "") or p.get("sentence", "")
            if text.strip():
                para_lines.append(text)
        if para_lines:
            return "\n\n".join(para_lines)

    # 最后兜底：尝试转写 API
    transcripts = minute_data.get("transcripts", [])
    if transcripts:
        text_lines = []
        for t in transcripts:
            content = t.get("text", "") or t.get("content", "")
            if content.strip():
                text_lines.append(content)
        if text_lines:
            return "\n".join(text_lines)

    raise RuntimeError(
        "❌ 无法从妙记中提取文本内容。\n"
        "   可能原因：\n"
        "   1. 妙记尚未生成转写文本\n"
        "   2. 应用权限不足，请确认已开通 'minutes:minute:readonly' 权限\n"
        "   3. 妙记不属于当前租户"
    )


def fetch_feishu_text(url: str) -> tuple[str, str]:
    """
    飞书内容抓取统一入口。
    根据 URL 类型选择合适的抓取策略。

    返回：(文本内容, 来源类型字符串)
    来源类型：'feishu_minutes' / 'feishu_docx' / 'feishu_docs' / 'feishu_wiki'
    """
    parsed = _parse_feishu_url(url)
    if not parsed:
        raise ValueError(f"❌ 无法识别的飞书链接格式：{url}")

    url_type, resource_id = parsed
    print(f"\n🔗 检测到飞书链接，类型：{url_type}")
    print(f"   资源 ID：{resource_id}")

    token = _get_feishu_tenant_token()
    print("   ✅ 飞书 API 鉴权成功，正在抓取内容...")

    if url_type in ("docx", "docs"):
        text = _fetch_feishu_docx_raw(resource_id, token)
        source_type = f"feishu_{url_type}"
    elif url_type == "minutes":
        text = _fetch_feishu_minutes_text(resource_id, token)
        source_type = "feishu_minutes"
    elif url_type == "wiki":
        # 飞书知识库暂用 docx 方式尝试
        text = _fetch_feishu_docx_raw(resource_id, token)
        source_type = "feishu_wiki"
    else:
        raise ValueError(f"❌ 不支持的飞书链接类型：{url_type}")

    word_count = len(text)
    print(f"   ✅ 抓取成功！共获取 {word_count} 字符。")
    return text, source_type


# --- 🆕 飞书文档创建（/to_feishu 用）---

def create_feishu_doc_from_conversation(
    title: str,
    messages: list[dict],
    source_url: str | None = None,
) -> str:
    """
    将模式 3 的全部对话内容导出为一篇新的飞书云文档。

    参数：
        title:      文档标题（会显示在飞书文档列表中）
        messages:   完整的对话消息列表（含 system 提示词）
        source_url: 原始来源链接（可选，写入文档头部）

    返回：
        新创建的飞书文档 URL
    """
    token = _get_feishu_tenant_token()

    # ---------- 1. 创建空白文档 ----------
    print("   📄 正在创建飞书文档...")
    create_body = {"title": title}
    create_result = _feishu_api_post(
        "/docx/v1/documents", token, create_body
    )
    document_id = create_result.get("document", {}).get("document_id", "")
    if not document_id:
        raise RuntimeError("❌ 创建文档失败，未获取到 document_id。")
    print(f"   ✅ 文档已创建，ID：{document_id}")

    # ---------- 2. 组装文档内容为飞书 Block 格式 ----------
    children_blocks: list[dict] = []

    # 头部：来源链接
    if source_url:
        children_blocks.append({
            "block_type": 2,  # 文本块
            "text": {
                "elements": [
                    {"text_run": {"content": "📎 来源链接：", "text_element_style": {"bold": True}}},
                    {"text_run": {"content": source_url, "text_element_style": {"link": {"url": source_url}}}},
                ],
                "style": {},
            },
        })
        children_blocks.append({
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": ""}}], "style": {}},
        })

    # 分割线
    children_blocks.append({
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": "━━━━━━━━━━━━━━━━"}}], "style": {}},
    })
    children_blocks.append({
        "block_type": 2,
        "text": {"elements": [{"text_run": {"content": ""}}], "style": {}},
    })

    # 逐条消息
    for msg in messages:
        role = msg.get("role", "user")
        content = msg.get("content", "")

        if role == "system":
            # System 提示词折叠展示
            label = "📋 系统背景知识（AI 已掌握）"
            truncated = content[:300] + "…[已折叠，全文在报告里]" if len(content) > 300 else content
            children_blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [
                        {"text_run": {"content": label, "text_element_style": {"bold": True, "italic": True}}},
                    ],
                    "style": {},
                },
            })
            children_blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [{"text_run": {"content": truncated, "text_element_style": {"italic": True}}}],
                    "style": {},
                },
            })
        elif role == "user":
            children_blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [
                        {"text_run": {"content": "🧑 我：", "text_element_style": {"bold": True}}},
                    ],
                    "style": {},
                },
            })
            children_blocks.append({
                "block_type": 2,
                "text": {"elements": [{"text_run": {"content": content}}], "style": {}},
            })
        elif role == "assistant":
            children_blocks.append({
                "block_type": 2,
                "text": {
                    "elements": [
                        {"text_run": {"content": "🤖 顾问：", "text_element_style": {"bold": True}}},
                    ],
                    "style": {},
                },
            })
            # AI 回复可能很长，按段落拆分更好看
            for para in content.split("\n"):
                if para.strip():
                    children_blocks.append({
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": para}}], "style": {}},
                    })
                else:
                    children_blocks.append({
                        "block_type": 2,
                        "text": {"elements": [{"text_run": {"content": ""}}], "style": {}},
                    })

        # 消息之间加空行
        children_blocks.append({
            "block_type": 2,
            "text": {"elements": [{"text_run": {"content": ""}}], "style": {}},
        })

    # ---------- 3. 写入内容到文档 ----------
    # 根节点 block_id 即 document_id
    print(f"   ✍️  正在写入 {len(children_blocks)} 个内容块到文档...")

    # 飞书 API 一次最多添加 50 个子块，需要分批
    BATCH_SIZE = 50
    for batch_start in range(0, len(children_blocks), BATCH_SIZE):
        batch = children_blocks[batch_start:batch_start + BATCH_SIZE]
        block_endpoint = f"/docx/v1/documents/{document_id}/blocks/{document_id}/children"
        _feishu_api_post(block_endpoint, token, {"children": batch})
        batch_end = min(batch_start + BATCH_SIZE, len(children_blocks))
        print(f"      批次 [{batch_start+1}-{batch_end}/{len(children_blocks)}] ✅")

    # ---------- 4. 生成文档 URL ----------
    # 飞书文档的标准 URL 格式
    doc_url = f"https://{_get_feishu_tenant_domain()}/docx/{document_id}"

    return doc_url


def _get_feishu_tenant_domain() -> str:
    """从 app_id 推断或返回默认的飞书租户域名。"""
    # 飞书文档 URL 需要租户域名，但 API 不直接返回。
    # 常见做法是用 app_id 的前缀或直接用 feishu.cn
    # 实际上飞书 API 返回的文档 URL 格式为 https://{tenant}.feishu.cn/docx/{id}
    # 如果不知道租户域名，用 api.feishu.cn 也能访问（会重定向）
    return "mddm2zre2q8.feishu.cn"  # 默认；用户可在代码里改成自己的租户域名


# =========================================================================
# 2.  模式 1 —— 全自动一键通关
#     ASR → 清洗 → 金句+待办 → 深度探讨 → 输出报告 + 对话历史
#     🆕 支持 --input 飞书链接，0秒跳过ASR
# =========================================================================

def mode1_full_pipeline(input_url: str | None = None) -> None:
    banner(1, "全自动一键通关（ASR → 清洗 → 探讨 → 报告）")

    # --- 2.1 前置检查 ---
    INPUT_DIR.mkdir(parents=True, exist_ok=True)
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    raw_text = ""
    source_type = "local_audio"

    # --- 2.2 🆕 飞书链接优先：0秒跳过 ASR ---
    if input_url and is_feishu_url(input_url):
        print("🔗 [飞书闭环] 检测到飞书链接输入，跳过本地 ASR，直接在线抓取！\n")
        global SOURCE_URL
        try:
            raw_text, source_type = fetch_feishu_text(input_url)
            SOURCE_URL = input_url  # 全局记录

            # 保存抓取到的文本（和 ASR 输出保持一致的文件路径）
            RAW_TEXT_FILE.write_text(raw_text, encoding="utf-8")
            print(f"\n💾 飞书抓取文本已保存：{RAW_TEXT_FILE}")

            # 🆕 飞书成功 → 跳 ASR
            print("\n⏩ 飞书抓取成功，0 秒跳过本地 ASR 识别，直接进入云端清洗！")
        except Exception as e:
            print(f"\n⚠️  飞书抓取失败：{e}")
            print("   将回退到本地 ASR 流程...")
            raw_text = ""  # 清空，触发后续 ASR 流程
            source_type = "local_audio"
            SOURCE_URL = input_url  # 即使失败也记录链接，方便用户排查

    # --- 2.3 🆕 非飞书 URL 的 --input 当作本地文件路径 ---
    if not raw_text and input_url and not is_feishu_url(input_url):
        local_file = Path(input_url)
        if local_file.exists():
            print(f"📂 检测到本地音频文件：{local_file}")
            # 复制到标准位置
            import shutil as _shutil
            _shutil.copy2(str(local_file), str(AUDIO_FILE))
            print(f"   已复制到：{AUDIO_FILE}")
        else:
            print(f"⚠️  未找到文件：{input_url}，将使用默认音频路径。")

    # --- 2.4 大招一：本地 ASR（0 成本）--- 🔗 飞书成功时跳过此段 ---
    if not raw_text:
        if not AUDIO_FILE.exists():
            print(f"❌ 未找到音频文件：{AUDIO_FILE}")
            print("   请将猫抓下载的音频放入 input_audio/ 并重命名为 live_audio.mp3")
            print("   或使用 --input 指定飞书链接 / 本地音频文件路径。")
            return

        print("🚀 [大招一] 本地 ASR 语音识别（白嫖本地算力）...\n")

        # 自动检测 GPU / CPU
        device = "cpu"
        compute_type = "int8"
        try:
            import torch
            if torch.cuda.is_available():
                device = "cuda"
                compute_type = "float16"
                print("✨ 检测到 CUDA 显卡，启用 GPU 硬件加速！\n")
        except Exception:
            pass

        if device == "cpu":
            print("💻 CPU 兼容模式运行，首次将下载 Whisper base 模型，请稍候...\n")

        from faster_whisper import WhisperModel

        MODEL_CACHE_DIR.mkdir(parents=True, exist_ok=True)
        model = WhisperModel(
            "base",
            device=device,
            compute_type=compute_type,
            download_root=str(MODEL_CACHE_DIR),
        )
        segments, info = model.transcribe(
            str(AUDIO_FILE),
            beam_size=5,
            language="zh",
        )

        print(f"[ASR] 检测语言：{info.language}（置信度 {info.language_probability:.2f}）\n")

        raw_texts: list[str] = []
        for seg in segments:
            timestamp = f"[{seg.start:6.1f}s → {seg.end:6.1f}s] {seg.text}"
            print(timestamp)
            raw_texts.append(seg.text)

        raw_text = "".join(raw_texts)

        RAW_TEXT_FILE.write_text(raw_text, encoding="utf-8")
        print(f"\n💾 原始文字稿已保存：{RAW_TEXT_FILE}")

    # --- 2.5 大招二：云端清洗 & 探讨 ---
    _run_cloud_pipeline(raw_text, source_type)


def _run_cloud_pipeline(raw_text: str, source_type: str = "local_audio") -> None:
    """
    云端三段式处理（模式 1 和模式 2 共用）：
      阶段一：分段清洗 & 整理
      阶段二：提炼金句 + 行动清单
      阶段三：资深顾问深度探讨
    最终生成 final_report.md 和 chat_session.json。

    🆕 source_type: 标注数据来源（local_audio / feishu_minutes / feishu_docx 等）
    """
    print("\n🚀 [大招二] 调用大模型进行清洗与深度探讨...\n")

    if "你的" in API_KEY or not API_KEY:
        print("⚠️  请先在脚本顶部配置真实的 API_KEY！")
        return

    client = create_client()
    chunks = chunk_text(raw_text)

    # ---------- 阶段一：清洗 ----------
    print(f"📝 [阶段一] 文字清洗，共 {len(chunks)} 个片段...")
    cleaned_parts: list[str] = []
    for i, chunk in enumerate(chunks, 1):
        prompt = f"""你是一个极其专业的文字秘书。请帮我清洗从小鹅通直播回放中提取出的第 {i}/{len(chunks)} 段语音文本。
要求：
1. 修正错别字，删掉无意义的语气词（如啊、吧、呢、呃）和大白话重复。
2. 严格根据演讲者的逻辑脉络划分段落，并为每个段落加上生动提炼的【小标题】。
3. 保持演讲者的核心专业术语和原始观点不变。

原始语音文本：
{chunk}"""
        resp = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt}],
        )
        cleaned_parts.append(resp.choices[0].message.content)
        print(f"  [{i}/{len(chunks)}] ✅")

    final_cleaned = "\n\n".join(cleaned_parts)

    # ---------- 阶段二：金句 & 待办 ----------
    print("\n✨ [阶段二] 提炼金句与行动清单...")
    prompt_summary = f"""请通读以下整篇已经整理好的文字稿，帮我完成两件事：
1. 提炼出直播里最有价值的【核心金句摘要】（不少于5条）。
2. 根据直播里提到的任务，整理出一份高清的【行动清单（To-do List）】。

整篇文字稿：
{final_cleaned}"""
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt_summary}],
    )
    summary_content = resp.choices[0].message.content
    print("  ✅ 金句与清单提炼完成")

    # ---------- 阶段三：深度探讨 ----------
    print("\n💡 [阶段三] 资深商业顾问深度探讨...")
    prompt_discuss = f"""你现在是一位资深的商业咨询顾问。请通读以下整篇文字稿和摘要，针对这次小鹅通直播提到的业务内容，站在落地的角度，深刻提出【3个深度业务反思点与落地改进建议】。

文字稿与摘要：
{final_cleaned}
{summary_content}"""
    resp = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt_discuss}],
    )
    discuss_content = resp.choices[0].message.content
    print("  ✅ 深度探讨完成")

    # ---------- 拼装最终报告 ----------
    full_report = f"""# 📝 小鹅通直播回放全自动化深度报告

## 📌 第一部分：精修核心文字稿
{final_cleaned}

---

## 🎯 第二部分：核心提炼（金句 & 行动清单）
{summary_content}

---

## 💡 第三部分：专业顾问深度探讨与反思
{discuss_content}
"""

    REPORT_FILE.write_text(full_report, encoding="utf-8")
    print(f"\n🎉 完整报告已生成：{REPORT_FILE}")

    # ---------- 🆕 v5.0 保存对话历史（带元数据）----------
    _save_chat_v5(
        messages=[
            {
                "role": "system",
                "content": (
                    "你是一个了解该小鹅通直播全部内容的专业商业咨询顾问。"
                    "以下是该直播的完整文本及清洗探讨报告，"
                    "你可以基于此内容与用户继续深入探讨，始终站在落地角度给出深刻建议。\n\n"
                    f"{full_report}"
                ),
            }
        ],
        source_type=source_type,
        source_url=SOURCE_URL,
    )
    print(f"💾 对话历史已保存：{CHAT_HISTORY_FILE}")
    if SOURCE_URL:
        print(f"🔗 来源链接已记录：{SOURCE_URL}")
    print("   随时可用 --mode 3 进入交互式深度对话！")


# =========================================================================
# 3.  模式 2 —— 断点续跑
#     跳过 ASR，直接读取 temporary_raw.txt 重新云端清洗
#     🆕 支持 --input 飞书链接：先从飞书抓取再清洗
# =========================================================================

def mode2_resume_cleaning(input_url: str | None = None) -> None:
    banner(2, "断点续跑（跳过 ASR，仅重新清洗 & 生成报告）")

    source_type = "local_audio"
    raw_text = ""  # 显式初始化，避免变量不存在

    # 🆕 如果提供了飞书链接，先抓取
    if input_url and is_feishu_url(input_url):
        print("🔗 [飞书闭环] 检测到飞书链接，正在在线抓取...\n")
        try:
            raw_text, source_type = fetch_feishu_text(input_url)
            global SOURCE_URL
            SOURCE_URL = input_url

            # 保存抓取到的文本
            RAW_TEXT_FILE.write_text(raw_text, encoding="utf-8")
            print(f"💾 飞书抓取文本已保存：{RAW_TEXT_FILE}\n")
        except Exception as e:
            print(f"\n⚠️  飞书抓取失败：{e}")
            print("   将回退读取本地 temporary_raw.txt...")
            raw_text = ""  # 清空，触发本地加载
            source_type = "local_audio"

    # 如果没有通过飞书获取到文本，读取本地文件
    if not raw_text:
        if not RAW_TEXT_FILE.exists():
            print(f"❌ 未找到原始文字稿：{RAW_TEXT_FILE}")
            print("   请先运行模式 1 生成 temporary_raw.txt，或手动放入该文件。")
            print("   也可使用 --input 飞书链接 直接抓取内容。")
            return

        raw_text = RAW_TEXT_FILE.read_text(encoding="utf-8")
        print(f"📂 已加载原始文字稿（{len(raw_text)} 字符）")
        print("   将直接送入大模型进行清洗，不重复消耗本地算力。\n")

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    _run_cloud_pipeline(raw_text, source_type)


# =========================================================================
# 4.  模式 3 —— 交互式深度对话（🆕 v5.0 飞书闭环版）
#     加载 chat_session.json，在终端与 AI 多轮实时对话
#     🆕 置顶看板展示来源链接
#     🆕 支持 /to_feishu 一键导出飞书文档
# =========================================================================

def mode3_interactive_discussion() -> None:
    banner(3, "交互式深度对话（基于直播报告的 AI 专业顾问）")

    if not CHAT_HISTORY_FILE.exists():
        print(f"❌ 未找到对话历史：{CHAT_HISTORY_FILE}")
        print("   请先运行模式 1，生成报告后再进入交互对话。")
        return

    if "你的" in API_KEY or not API_KEY:
        print("⚠️  请先在脚本顶部配置真实的 API_KEY！")
        return

    # --- 🆕 加载会话（兼容 v3.0 旧格式） ---
    raw_data = json.loads(CHAT_HISTORY_FILE.read_text(encoding="utf-8"))
    metadata: dict = {}
    messages: list[dict] = []

    if isinstance(raw_data, list):
        # v3.0 旧格式：纯消息列表
        messages = raw_data
        metadata = {
            "version": "3.0",
            "source_type": "local_audio",
            "source_url": None,
        }
    elif isinstance(raw_data, dict):
        # v5.0 新格式：{metadata: {...}, messages: [...]}
        metadata = raw_data.get("metadata", {})
        messages = raw_data.get("messages", [])

    # 🆕 如果 v3.0 旧格式数据通过 --input 进入的，用全局 SOURCE_URL 覆盖
    if SOURCE_URL and not metadata.get("source_url"):
        metadata["source_url"] = SOURCE_URL

    source_url = metadata.get("source_url", SOURCE_URL)

    # --- 🆕 置顶看板：来源链接 ---
    bar_double = "=" * 62
    bar_single = "-" * 62
    print(f"\n{bar_double}")
    print(f"  📎 任务来源链接")
    print(f"{bar_double}")
    if source_url:
        print(f"  🔗 {source_url}")
        print(f"  📂 来源类型：{metadata.get('source_type', '未知')}")
    else:
        print(f"  ℹ️  无外部来源链接（本地音频文件）")
        print(f"  💡 提示：使用 --input 飞书URL 启动模式 3 可钉住来源")
    print(f"  📅 创建时间：{metadata.get('created_at', '未知')}")
    print(f"  📦 会话版本：{metadata.get('version', '未知')}")
    print(f"{bar_double}")

    print(f"\n📂 已加载对话历史（{len(messages)} 条消息）")
    print("   AI 已掌握该直播的完整背景，随时可以深度探讨。\n")

    client = create_client()

    print(bar_single)
    print("  输入你的问题，AI 顾问将结合直播内容为你解答")
    print("  命令：")
    print("    /save      保存对话")
    print("    /clear     清屏")
    print("    /to_feishu 🆕 一键将全部对话生成飞书云文档")
    print("    /exit 或 /quit  退出")
    print(bar_single)

    turn = 0
    while True:
        try:
            user_input = input("\n>>> ").strip()
        except (EOFError, KeyboardInterrupt):
            print("\n\n👋 再见！对话已自动保存。")
            break

        # --- 内置命令 ---
        if user_input.lower() in ("/exit", "/quit"):
            _save_chat_v5(messages, metadata.get("source_type", "local_audio"), source_url)
            print("👋 对话已保存，再见！")
            break

        if user_input.lower() == "/save":
            _save_chat_v5(messages, metadata.get("source_type", "local_audio"), source_url)
            print("💾 对话已保存。")
            continue

        if user_input.lower() == "/clear":
            os.system("cls" if sys.platform == "win32" else "clear")
            # 🆕 清屏后重新打印看板
            print(f"\n{bar_double}")
            print(f"  📎 任务来源链接")
            print(f"{bar_double}")
            if source_url:
                print(f"  🔗 {source_url}")
            else:
                print(f"  ℹ️  本地音频文件")
            print(f"{bar_double}\n")
            print(bar_single)
            print("  命令：/save 保存  /clear 清屏  /to_feishu 导出飞书文档  /exit 退出")
            print(bar_single)
            continue

        # --- 🆕 /to_feishu 一键导出飞书文档 ---
        if user_input.lower() == "/to_feishu":
            _handle_to_feishu(messages, source_url)
            continue

        if not user_input:
            continue

        # --- 发送给 AI ---
        turn += 1
        messages.append({"role": "user", "content": user_input})

        try:
            print(f"\n🤔 AI 顾问思考中...", end="\r")
            resp = client.chat.completions.create(
                model=MODEL_NAME,
                messages=messages,
            )
            reply = resp.choices[0].message.content
            messages.append({"role": "assistant", "content": reply})

            print(f"{' ' * 20}", end="\r")  # 清除 "思考中"
            print(f"\n📢 顾问：\n{reply}")

            # 每轮自动保存，防丢失
            _save_chat_v5(messages, metadata.get("source_type", "local_audio"), source_url)

        except Exception as e:
            # 发送失败时回滚最后一条 user 消息，避免污染上下文
            messages.pop()
            print(f"\n⚠️  请求失败：{e}")
            print("   消息未发送，请检查网络后重试。")

    print(f"\n本次对话共 {turn} 轮。")


# --- 🆕 /to_feishu 命令处理 ---

def _handle_to_feishu(messages: list[dict], source_url: str | None = None) -> None:
    """
    处理 /to_feishu 命令：
    将当前模式 3 的全部对话内容，通过飞书开放平台 API 创建为一篇新的飞书云文档。
    创建成功后，高亮打印文档链接。
    """
    bar_star = "★" * 62
    print(f"\n{bar_star}")
    print("  🚀 /to_feishu · 一键导出飞书云文档")
    print(f"{bar_star}")

    # 检查 API 配置
    if not FEISHU_APP_ID or not FEISHU_APP_SECRET:
        print("\n❌ 飞书 API 未配置，无法创建文档！\n")
        print("   📌 请按以下步骤配置：")
        print("   1. 打开飞书开放平台：https://open.feishu.cn")
        print("   2. 进入「开发者后台」→ 创建企业自建应用")
        print("   3. 在「凭证与基础信息」中复制 App ID 和 App Secret")
        print("   4. 填入脚本顶部【飞书开放平台配置】区域的：")
        print("        FEISHU_APP_ID = 'cli_xxxxxxxxxxxxxxxxx'")
        print("        FEISHU_APP_SECRET = 'YOUR_FEISHU_APP_SECRET'")
        print("   5. 在「权限管理」中开通以下权限：")
        print("        - docx:document:create（创建文档）")
        print("        - contact:user.id:readonly（读取用户身份）")
        print("   6. 创建版本 → 发布 → 等待管理员审批\n")
        print("   📖 详见脚本顶部【飞书开放平台配置】注释区域。")
        print(f"{bar_star}\n")
        return

    # 过滤出有意义的对话消息（排除系统提示词）
    conversation_msgs = [m for m in messages if m.get("role") in ("user", "assistant")]

    if not conversation_msgs:
        print("\n⚠️  当前还没有对话内容，请先与 AI 顾问进行几轮交流后再导出。\n")
        return

    # 生成文档标题
    now_str = datetime.now().strftime("%Y-%m-%d %H:%M")
    user_first_msg = ""
    for m in conversation_msgs:
        if m.get("role") == "user":
            user_first_msg = m.get("content", "")[:50]
            break
    title = f"深度探讨记录 · {now_str}"
    if user_first_msg:
        title += f" · {user_first_msg}..."

    print(f"\n📝 文档标题：{title}")
    print(f"📊 共 {len(conversation_msgs)} 条对话消息")
    print(f"🔄 正在通过飞书 API 创建文档...\n")

    try:
        doc_url = create_feishu_doc_from_conversation(
            title=title,
            messages=messages,
            source_url=source_url,
        )

        # 🎉 醒目打印文档链接
        print(f"\n{'=' * 62}")
        print(f"  🎉 飞书云文档已生成！")
        print(f"{'=' * 62}")
        print(f"  📄 文档标题：{title}")
        print(f"  🔗 文档链接：{doc_url}")
        print(f"{'=' * 62}")
        print(f"  💡 点击上方链接即可在浏览器中打开飞书文档。")
        print(f"  📱 也可在飞书客户端「云文档」中直接搜索标题查看。")
        print(f"{'=' * 62}\n")

    except Exception as e:
        print(f"\n❌ 创建飞书文档失败：{e}")
        print(f"\n   请检查：")
        print(f"   1. FEISHU_APP_ID / FEISHU_APP_SECRET 是否正确")
        print(f"   2. 应用是否已发布并通过审批")
        print(f"   3. 权限是否包含 docx:document:create 和 contact:user.id:readonly")
        print(f"   4. 网络是否能访问 open.feishu.cn\n")


# --- 🆕 v5.0 会话保存（带元数据）---

def _save_chat_v5(
    messages: list[dict],
    source_type: str = "local_audio",
    source_url: str | None = None,
) -> None:
    """将当前对话持久化到 chat_session.json（v5.0 带元数据格式）。"""
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    session_data = {
        "metadata": {
            "version": "5.0",
            "source_type": source_type,
            "source_url": source_url,
            "created_at": _now_iso(),
        },
        "messages": messages,
    }
    CHAT_HISTORY_FILE.write_text(
        json.dumps(session_data, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


# 🆕 向后兼容保存（v3.0 旧版调用兼容）
def _save_chat(messages: list[dict]) -> None:
    """v3.0 兼容：将当前对话持久化到 chat_session.json。"""
    _save_chat_v5(messages)


# =========================================================================
# 5.  入口 —— 命令行参数路由
# =========================================================================

def main() -> None:
    parser = argparse.ArgumentParser(
        description="小鹅通直播回放 · 全自动化深度处理工作流（v5.0 终极飞书闭环版）",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例：
  python super_save_workflow_all_in_one.py                                     # 默认模式1
  python super_save_workflow_all_in_one.py --mode 1                            # 全自动一键通关
  python super_save_workflow_all_in_one.py --mode 1 --input "飞书URL"           # 🆕 飞书链接直输
  python super_save_workflow_all_in_one.py --mode 2                            # 断点续跑（跳过ASR）
  python super_save_workflow_all_in_one.py --mode 2 --input "飞书URL"           # 🆕 飞书链接续跑
  python super_save_workflow_all_in_one.py --mode 3                            # 交互式深度对话
  python super_save_workflow_all_in_one.py --mode 3 --input "飞书URL"           # 🆕 带来源链接

🆕 v5.0 飞书闭环：
  ① --input "https://xxx.feishu.cn/minutes/xxx"  在线解析飞书妙记/文档
  ② 模式3 置顶看板展示来源链接，存入 chat_session.json 元数据
  ③ 模式3 输入 /to_feishu → 一键将全部对话生成为飞书云文档
        """,
    )
    parser.add_argument(
        "--mode", "-m",
        type=int,
        choices=(1, 2, 3),
        default=1,
        help="运行模式：1=全自动通关  2=断点续跑  3=交互对话（默认：1）",
    )
    parser.add_argument(
        "--input", "-i",
        type=str,
        default=None,
        help=(
            "🆕 输入来源：飞书链接 / 本地音频文件路径。\n"
            "  · 飞书链接（如 https://xxx.feishu.cn/minutes/xxx）：\n"
            "    在线抓取妙记/文档文本，0秒跳过ASR，直达云端清洗。\n"
            "  · 本地文件路径：指定音频文件，覆盖默认 input_audio/live_audio.mp3"
        ),
    )
    args = parser.parse_args()

    # 🆕 全局记录来源链接
    global SOURCE_URL
    if args.input and is_feishu_url(args.input):
        SOURCE_URL = args.input

    # --- 环境初始化（所有模式通用） ---
    print("=" * 62)
    print("  super_save_workflow  ·  All-in-One  ·  v5.0 终极飞书闭环版")
    print("=" * 62)
    _ensure_packages()
    resolve_ffmpeg()

    # --- 路由 ---
    if args.mode == 1:
        mode1_full_pipeline(input_url=args.input)
    elif args.mode == 2:
        mode2_resume_cleaning(input_url=args.input)
    elif args.mode == 3:
        mode3_interactive_discussion()


if __name__ == "__main__":
    main()
