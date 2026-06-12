import os
import sys
import subprocess
import json
import shutil
import zipfile
import urllib.request
from pathlib import Path

# ==========================================
# 【大招二配置区】在此处填入你的白菜价大模型密钥
# ==========================================
API_KEY = "你的_DEEPSEEK_或者_豆包_API_KEY"
BASE_URL = "https://api.deepseek.com/v1"  # 或者是豆包的 https://ark.cn-beijing.volces.com/api/v3
MODEL_NAME = "deepseek-chat"             # 或者是豆包的 model endpoint ID

# ==========================================
# 0. 【环境全自动补全】第三方库 + ffmpeg 一条龙
#    无需你在 Windows 里手动配置任何环境变量！
# ==========================================

PROJECT_DIR = Path(__file__).resolve().parent
BIN_DIR = PROJECT_DIR / ".ffmpeg"
FFMPEG_DOWNLOAD_URL = "https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.zip"


# --- 0.1 自动检查并安装缺失的第三方依赖库 ---
def initialize_environment():
    required_packages = {
        "faster_whisper": "faster-whisper",
        "openai": "openai",
        "imageio_ffmpeg": "imageio-ffmpeg"
    }
    for module_name, pip_name in required_packages.items():
        try:
            __import__(module_name)
        except ImportError:
            print(f"[环境初始化] 未检测到库 {pip_name}，正在自动为您安装...")
            subprocess.check_call([sys.executable, "-m", "pip", "install", pip_name])
            print(f"[环境初始化] {pip_name} 安装成功！")


# --- 0.2 ffmpeg 逐级降级检测与自动补全 ---
def _find_ffmpeg_on_path() -> str | None:
    """策略1：检查系统 PATH 里有没有 ffmpeg。"""
    return shutil.which("ffmpeg")


def _find_ffmpeg_in_project() -> str | None:
    """策略2：检查项目 .ffmpeg/ 目录下是否已有上次下载的便携版。"""
    candidates = list(BIN_DIR.rglob("ffmpeg.exe")) + list(BIN_DIR.rglob("ffmpeg"))
    for c in candidates:
        if c.is_file():
            return str(c)
    return None


def _try_imageio_ffmpeg() -> str | None:
    """策略3：用 imageio-ffmpeg 自带的静态编译版 ffmpeg。"""
    try:
        import imageio_ffmpeg
        bin_path = imageio_ffmpeg.get_ffmpeg_exe()
        if bin_path and Path(bin_path).is_file():
            return bin_path
    except ImportError:
        pass
    return None


def _download_portable_ffmpeg() -> str:
    """
    策略4：自动从 Gyan 下载 Windows 轻量版 ffmpeg（essentials build），
    解压后只保留 ffmpeg.exe 到项目 .ffmpeg/ 目录。
    """
    BIN_DIR.mkdir(parents=True, exist_ok=True)
    zip_path = BIN_DIR / "ffmpeg-release-essentials.zip"

    print("[ffmpeg] 未在系统中检测到 ffmpeg，正在自动下载便携版（约 30MB）...")
    print(f"[ffmpeg] 下载地址：{FFMPEG_DOWNLOAD_URL}")
    urllib.request.urlretrieve(FFMPEG_DOWNLOAD_URL, zip_path)
    print("[ffmpeg] 下载完成，正在解压提取 ffmpeg.exe ...")

    with zipfile.ZipFile(zip_path, "r") as zf:
        for member in zf.namelist():
            # Gyan 的压缩包里 ffmpeg.exe 位于 ffmpeg-xxx-essentials_build/bin/ 下
            if member.endswith("ffmpeg.exe") and "/bin/" in member.replace("\\", "/"):
                dest = BIN_DIR / "ffmpeg.exe"
                with zf.open(member) as src, open(dest, "wb") as dst:
                    shutil.copyfileobj(src, dst)
                break
        else:
            raise RuntimeError(
                "[ffmpeg] 下载的压缩包中未找到 ffmpeg.exe，"
                "请手动安装 ffmpeg：https://ffmpeg.org/download.html"
            )

    zip_path.unlink()  # 清理压缩包，只保留 exe
    ffmpeg_path = BIN_DIR / "ffmpeg.exe"
    if not ffmpeg_path.exists():
        raise RuntimeError("[ffmpeg] ffmpeg.exe 解压失败，请检查磁盘空间或网络后重试。")

    print(f"[ffmpeg] 便携版 ffmpeg 已就绪：{ffmpeg_path}")
    return str(ffmpeg_path)


def resolve_and_patch_ffmpeg() -> str:
    """
    按优先级逐级尝试获取 ffmpeg：
        1. 系统 PATH（已装过就直接用）
        2. 项目 .ffmpeg/ 已有便携版（上次下载过了）
        3. imageio-ffmpeg 自带二进制
        4. 自动下载 Gyan essentials build → .ffmpeg/ffmpeg.exe

    获取到之后自动将 ffmpeg 所在目录注入当前进程的 PATH，
    同时设置 FFMPEG_BINARY 环境变量，
    确保 faster-whisper 的 subprocess 能找到它。
    """
    ffmpeg_path = (
        _find_ffmpeg_on_path()
        or _find_ffmpeg_in_project()
        or _try_imageio_ffmpeg()
    )

    if not ffmpeg_path:
        if sys.platform == "win32":
            ffmpeg_path = _download_portable_ffmpeg()
        else:
            raise RuntimeError(
                "[ffmpeg] 未找到 ffmpeg，请手动安装：\n"
                "  macOS:   brew install ffmpeg\n"
                "  Linux:   sudo apt install ffmpeg\n"
                "  或执行:  pip install imageio-ffmpeg"
            )

    # 将 ffmpeg 所在目录注入 PATH，同时设置 FFMPEG_BINARY 环境变量
    ffmpeg_dir = str(Path(ffmpeg_path).parent)
    current_path = os.environ.get("PATH", "")
    os.environ["PATH"] = f"{ffmpeg_dir}{os.pathsep}{current_path}"
    os.environ["FFMPEG_BINARY"] = ffmpeg_path

    print(f"[ffmpeg] ✅ 已激活 ffmpeg：{ffmpeg_path}")
    return ffmpeg_path


# --- 执行环境初始化 ---
initialize_environment()
resolve_and_patch_ffmpeg()

# ==========================================
# 以下为原有业务逻辑
# ==========================================

from faster_whisper import WhisperModel
from openai import OpenAI

def main():
    # 创建必要的文件夹
    os.makedirs("input_audio", exist_ok=True)
    os.makedirs("output_result", exist_ok=True)

    audio_path = "input_audio/live_audio.mp3"
    raw_text_path = "temporary_raw.txt"
    final_report_path = "output_result/final_report.md"
    chat_history_path = "output_result/chat_session.json"

    if not os.path.exists(audio_path):
        print(f"❌ 错误：未在 {audio_path} 找到音频文件！请先将猫抓下载的音频放入 input_audio 并改名为 live_audio.mp3")
        return

    # ==========================================
    # 2. 【大招一】本地 ASR 语音识别阶段 (0成本)
    # ==========================================
    print("🚀 启动【大招一】：本地 ASR 语音识别中（正在白嫖本地算力）...")

    # 自动检测硬件，决定是跑 GPU 还是 CPU 兼容模式
    device = "cpu"
    compute_type = "int8"
    try:
        import torch
        if torch.cuda.is_available():
            device = "cuda"
            compute_type = "float16"
            print("✨ 检测到独立显卡，开启 GPU 硬件加速！")
    except:
        pass

    if device == "cpu":
        print("💻 运行于 CPU 兼容模式下，首次运行将自动下载 Whisper 模型补丁，请稍候...")

    # 加载模型并识别（首次会自动下载 base 模型，以后直接秒开）
    model = WhisperModel("base", device=device, compute_type=compute_type, download_root="./model_cache")
    segments, info = model.transcribe(audio_path, beam_size=5, language="zh")

    raw_texts = []
    for segment in segments:
        print(f"[{segment.start:.1f}s -> {segment.end:.1f}s]: {segment.text}")
        raw_texts.append(segment.text)

    full_raw_text = "".join(raw_texts)

    with open(raw_text_path, "w", encoding="utf-8") as f:
        f.write(full_raw_text)
    print(f"💾 原始大白话文字稿已保存至：{raw_text_path}")

    # ==========================================
    # 3. 【大招二】大模型清洗与探讨阶段
    # ==========================================
    print("🚀 启动【大招二】：调用国内白菜价大模型进行清洗和深度探讨...")
    if "你的" in API_KEY or not API_KEY:
        print("⚠️ 提示：请先在代码开头配置您真实的大模型 API_KEY，否则无法完成清洗阶段。")
        return

    client = OpenAI(api_key=API_KEY, base_url=BASE_URL)

    # 自动切分长文本（每 1.2 万字切一段，防止 Token 溢出）
    def chunk_text(text, max_len=12000):
        return [text[i:i+max_len] for i in range(0, len(text), max_len)]

    chunks = chunk_text(full_raw_text)
    cleaned_paragraphs = []

    # --- 阶段一：清洗与整理 ---
    print(f"📝 正在清洗文字稿，共切分为 {len(chunks)} 个片段处理...")
    for idx, chunk in enumerate(chunks):
        prompt_clean = f"""你是一个极其专业的文字秘书。请帮我清洗从小鹅通直播回放中提取出的第 {idx+1}/{len(chunks)} 段语音文本。
要求：
1. 修正错别字，删掉无意义的语气词（如啊、吧、呢、呃）和大白话重复。
2. 严格根据演讲者的逻辑脉络划分段落，并为每个段落加上生动提炼的【小标题】。
3. 保持演讲者的核心专业术语和原始观点不变。

原始语音文本：
{chunk}"""

        response = client.chat.completions.create(
            model=MODEL_NAME,
            messages=[{"role": "user", "content": prompt_clean}]
        )
        cleaned_paragraphs.append(response.choices[0].message.content)

    final_cleaned_text = "\n\n".join(cleaned_paragraphs)

    # --- 阶段二：提取金句与待办 ---
    print("✨ 正在提炼金句和行动清单（王振宇老板指令）...")
    prompt_summary = f"""请通读以下整篇已经整理好的文字稿，帮我完成两件事：
1. 提炼出直播里最有价值的【核心金句摘要】（不少于5条）。
2. 根据直播里提到的任务，整理出一份高清的【行动清单（To-do List）】。

整篇文字稿：
{final_cleaned_text}"""

    res_summary = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt_summary}]
    )
    summary_content = res_summary.choices[0].message.content

    # --- 阶段三：深度探讨 ---
    print("💡 正在模拟专业顾问进行深度探讨与反思...")
    prompt_discuss = f"""你现在是一位资深的商业咨询顾问。请通读以下整篇文字稿和摘要，针对这次小鹅通直播提到的业务内容，站在落地的角度，深刻提出【3个深度业务反思点与落地改进建议】。

文字稿与摘要：
{final_cleaned_text}
{summary_content}"""

    res_discuss = client.chat.completions.create(
        model=MODEL_NAME,
        messages=[{"role": "user", "content": prompt_discuss}]
    )
    discuss_content = res_discuss.choices[0].message.content

    # ==========================================
    # 4. 最终输出与持久化历史记录（方便后续探讨）
    # ==========================================
    full_report_markdown = f"""# 📝 小鹅通直播回放全自动化深度报告

## 📌 第一部分：精修核心文字稿
{final_cleaned_text}

---

## 🎯 第二部分：王振宇老板要求的核心提炼
{summary_content}

---

## 💡 第三部分：专业顾问深度探讨与反思
{discuss_content}
"""

    with open(final_report_path, "w", encoding="utf-8") as f:
        f.write(full_report_markdown)
    print(f"🎉 恭喜！完整的文字稿与探讨报告已成功生成在：{final_report_path}")

    # 保存对话历史（方便后续直接续写探讨）
    session_data = [
        {"role": "system", "content": f"你是一个了解该小鹅通直播全部内容的专业顾问。以下是该直播的完整文本及清洗探讨报告，你可以基于此内容与用户继续深入探讨：\n{full_report_markdown}"}
    ]
    with open(chat_history_path, "w", encoding="utf-8") as f:
        json.dump(session_data, f, ensure_ascii=False, indent=2)
    print(f"💾 后续探讨上下文历史文件已生成：{chat_history_path}。")

if __name__ == "__main__":
    main()
