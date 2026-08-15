"""
TTS 语音合成模块 — 浏览器内实时播放版

使用 edge-tts（免费、中文效果好）将面试官提问转为语音，
**音频在内存中生成 base64，不写磁盘、不弹外部播放器**。

浏览器通过 <audio autoplay> 直接解码播放，体验接近实时。
"""
import asyncio
import base64
import nest_asyncio

# Streamlit 内部运行着 Tornado asyncio 事件循环，asyncio.run() 会报 RuntimeError。
# nest_asyncio 允许嵌套调用，是 Streamlit + edge-tts 的标准解决方案。
nest_asyncio.apply()


async def _generate_edge_tts_base64(text: str, voice: str = "zh-CN-YunyangNeural",
                                     rate: str = "+5%", pitch: str = "+0Hz") -> str:
    """
    使用 edge-tts stream() 实时生成音频，内存中收集 → 返回 base64 字符串。
    零磁盘写入，零外部播放器。

    Args:
        text: 要朗读的文本
        voice: 语音角色（默认：云扬-专业男声）
        rate: 语速，如 "+10%" / "-10%"
        pitch: 音调，如 "+3Hz" / "-5Hz"

    Returns:
        base64 编码的 MP3 音频字符串，失败返回 None
    """
    try:
        import edge_tts
    except ImportError:
        raise ImportError("请安装 edge-tts: pip install edge-tts")

    communicate = edge_tts.Communicate(text, voice, rate=rate, pitch=pitch)
    audio_bytes = bytearray()

    # stream() 边生成边收集，无需等全部合成完
    async for chunk in communicate.stream():
        if chunk["type"] == "audio":
            audio_bytes.extend(chunk["data"])

    if not audio_bytes:
        return None

    return base64.b64encode(bytes(audio_bytes)).decode()


def generate_audio_base64(text: str, voice: str = "zh-CN-YunyangNeural",
                          rate: str = "+5%", pitch: str = "+0Hz") -> str | None:
    """
    同步接口：生成 edge-tts 音频并返回 base64 字符串。
    不写文件、不调外部播放器 — 交给浏览器 <audio> 元素播放。

    Returns:
        base64 字符串，可直接作为 data:audio/mp3;base64,... 的 src
    """
    try:
        return asyncio.run(_generate_edge_tts_base64(text, voice, rate, pitch))
    except ImportError:
        return None
    except Exception as e:
        import traceback
        print(f"[TTS edge-tts] 错误: {e}")
        traceback.print_exc()
        return None


# ============================================================
# 单一数据源：VOICE_REGISTRY
# 同时被 main.py（UI 下拉框）和 speak_text（发音人映射）引用,
# 绝无可能不一致。
# ============================================================
VOICE_REGISTRY = [
    # (voice_code,             display_label,        engine)
    ("zh-CN-YunyangNeural",    "云扬 (专业男声)",     "edge-tts"),
    ("zh-CN-YunjianNeural",    "云健 (热情男声)",     "edge-tts"),
    ("zh-CN-YunxiNeural",      "云希 (阳光男声)",     "edge-tts"),
    ("zh-CN-YunxiaNeural",     "云夏 (亲切男声)",     "edge-tts"),
    ("zh-CN-XiaoxiaoNeural",   "晓晓 (温暖女声)",     "edge-tts"),
    ("zh-CN-XiaoyiNeural",     "晓伊 (活泼女声)",     "edge-tts"),
    # 讯飞精品
    ("x4_jifeng",              "疾风-精品 (专业男声)", "xunfei"),
    ("x4_lingxiaoxuan",        "小璇-精品 (自然女声)", "xunfei"),
    ("x4_lingfeichen",         "飞晨-精品 (温暖男声)", "xunfei"),
    ("x4_lingxiaozhen",        "小臻-精品 (知性女声)", "xunfei"),
    ("x4_lingxiaoyi",          "小伊-精品 (温柔女声)", "xunfei"),
    ("x4_tingting",            "婷婷-精品 (甜美女声)", "xunfei"),
    # 讯飞基础
    ("xiaoyan",                "小燕 (亲切女声)",     "xunfei"),
    ("aisjiuxu",               "许久 (沉稳男声)",     "xunfei"),
    ("aisxping",               "小萍 (知性女声)",     "xunfei"),
    ("aisjinger",              "小婧 (温柔女声)",     "xunfei"),
]

def get_voice_options(engine: str) -> list:
    """返回指定引擎可用的 (display_label, voice_code) 列表"""
    return [(label, code) for code, label, eng in VOICE_REGISTRY if eng == _engine_key(engine)]

def get_voice_code(label: str) -> str:
    """通过 display_label 查 voice_code，找不到返回默认云扬"""
    for code, lbl, _ in VOICE_REGISTRY:
        if lbl == label:
            return code
    return "zh-CN-YunyangNeural"

# 兼容旧代码
AVAILABLE_VOICES = {code: code for code, _, _ in VOICE_REGISTRY}


# ════════════════════════════════════════════════════════════════
#  引擎可用性 + 统一合成入口
#
#  ★ 为什么要加这一层
#
#  改之前的行为：下拉框里固定列三个引擎，其中「XTTS 离线SDK」在 main.py 里
#  是这么处理的 ——
#
#      elif engine == "XTTS 离线SDK":
#          audio_b64 = None  # SDK DLL 通常不可用，静默跳过
#
#  用户选了它，然后【什么都不会发生，也没有任何提示】。而 SDK/ 目录在这个
#  仓库里根本不存在，所以它是 100% 必然静默失败的选项。
#
#  再加上 speak_text 里三层 except 把异常全吞掉、tts_utils 只 print 到终端
#  （Streamlit 界面看不见），结果就是：**语音坏了，但你不知道它为什么坏。**
#  这才是"语音模块要修"的真正含义 —— 不是合成不出来，是失败不可见。
#
#  现在：不可用的引擎【不进下拉框】，失败【带原因返回】。
# ════════════════════════════════════════════════════════════════

ENGINE_EDGE = "edge-tts (免费)"
ENGINE_XUNFEI = "讯飞 WebSocket TTS"
ENGINE_XTTS = "XTTS 离线SDK"


def _engine_key(engine: str) -> str:
    """显示名 → 引擎标识。集中一处，避免各处各写一个 `"讯飞" in engine`。"""
    if engine == ENGINE_XUNFEI or "讯飞" in str(engine):
        return "xunfei"
    if engine == ENGINE_XTTS or "XTTS" in str(engine):
        return "xtts"
    return "edge-tts"


# ★ 运行时失败记忆：能力检查查不出来的问题（凭证无效、配额用尽、服务端拒绝）
#   只有真调一次才知道。调失败过就记下来，让 engine_status 后续如实报告。
_RUNTIME_FAILURES: dict[str, str] = {}


def note_runtime_failure(engine: str, reason: str) -> None:
    _RUNTIME_FAILURES[engine] = (reason or "")[:120]


def clear_runtime_failure(engine: str) -> None:
    _RUNTIME_FAILURES.pop(engine, None)


def engine_status() -> list[tuple[str, bool, str]]:
    """返回 [(显示名, 是否可用, 不可用原因)]。

    ★ 判据是【真的能不能跑】，不是【代码里有没有这个分支】。
    """
    from pathlib import Path
    out: list[tuple[str, bool, str]] = []

    # edge-tts：装了包就能用（免费、无需凭证）
    try:
        import edge_tts  # noqa: F401
        out.append((ENGINE_EDGE, True, ""))
    except ImportError:
        out.append((ENGINE_EDGE, False, "未安装 edge-tts：pip install edge-tts"))

    # 讯飞：凭证齐全 **且** 上次实调没失败过
    #
    # ★ 只查"凭证存不存在"是不够的 —— 实测本机凭证齐全，engine_status() 报
    #   可用，但真正合成时服务端返回 `licc failed`（授权/配额问题）后被降级到
    #   edge-tts。结果是：下拉框里明明写着讯飞，出来的却是 edge 的声音，
    #   而"引擎选择"这个功能看上去是好的。
    #   这属于本项目反复出现的同一类问题：**能力检查查的是配置，不是能力。**
    #   凭证有效性没法免费预检（要真发一次请求），所以改为**记住运行时的失败**：
    #   一旦实调失败过，后续就如实报不可用并带上服务端原文。
    try:
        from .config import settings
        if not settings.xunfei_configured:
            out.append((ENGINE_XUNFEI, False, ".env 缺 XUNFEI_APP_ID / API_KEY / API_SECRET"))
        elif _RUNTIME_FAILURES.get(ENGINE_XUNFEI):
            out.append((ENGINE_XUNFEI, False,
                        f"凭证已配置，但实际调用失败：{_RUNTIME_FAILURES[ENGINE_XUNFEI]}"))
        else:
            out.append((ENGINE_XUNFEI, True, ""))
    except Exception as e:  # noqa: BLE001
        out.append((ENGINE_XUNFEI, False, f"配置读取失败：{e}"))

    # XTTS：需要本地 SDK DLL
    sdk = Path(__file__).resolve().parent.parent / "SDK" / "libs" / "64" / "AEE_lib.dll"
    if sdk.exists():
        out.append((ENGINE_XTTS, True, ""))
    else:
        out.append((ENGINE_XTTS, False, f"缺少本地 SDK：{sdk.relative_to(sdk.parents[3])} 不存在"))

    return out


def available_engines() -> list[str]:
    """只返回**真正可用**的引擎显示名，用于 UI 下拉框。"""
    return [name for name, ok, _ in engine_status() if ok]


class TTSResult:
    """合成结果。失败时带上【原因】，而不是一个沉默的 None。"""

    __slots__ = ("audio_b64", "engine_used", "error", "fell_back")

    def __init__(self, audio_b64=None, engine_used="", error="", fell_back=False):
        self.audio_b64 = audio_b64
        self.engine_used = engine_used
        self.error = error
        self.fell_back = fell_back

    @property
    def ok(self) -> bool:
        return bool(self.audio_b64)


def synthesize(text: str, engine: str = ENGINE_EDGE, voice: str = None) -> TTSResult:
    """统一合成入口：选引擎 → 合成 → 失败则降级 → **把发生了什么如实带回去**。

    调用方拿到的是 TTSResult，不是 None —— 沉默的 None 是上一版最大的问题：
    它让"没配凭证""网络不通""引擎压根不存在"三种完全不同的情况长得一模一样。
    """
    key = _engine_key(engine)
    voice = voice or ("x4_lingxiaoxuan" if key == "xunfei" else "zh-CN-YunyangNeural")

    status = {name: (ok, why) for name, ok, why in engine_status()}
    ok, why = status.get(engine, (False, "未知引擎"))
    if not ok:
        # ★ 不静默跳过。选了不可用的引擎，就明说它为什么不可用，
        #   然后降级到 edge-tts —— 并且告诉调用方"降级了"。
        fb = _try_edge(text, "zh-CN-YunyangNeural")
        if fb.ok:
            fb.fell_back = True
            fb.error = f"「{engine}」不可用（{why}），已自动改用 edge-tts"
            return fb
        return TTSResult(error=f"「{engine}」不可用（{why}），且 edge-tts 降级也失败：{fb.error}")

    if key == "xunfei":
        try:
            from .xunfei_tts import generate_xunfei_base64
            b64 = generate_xunfei_base64(text, voice)
            if b64:
                clear_runtime_failure(ENGINE_XUNFEI)   # 又能用了就恢复
                return TTSResult(b64, ENGINE_XUNFEI)
            reason = "讯飞返回空音频（凭证或配额问题）"
        except Exception as e:  # noqa: BLE001
            reason = f"讯飞调用异常：{type(e).__name__}: {e}"
        note_runtime_failure(ENGINE_XUNFEI, reason)
        fb = _try_edge(text, "zh-CN-YunyangNeural")
        if fb.ok:
            fb.fell_back = True
            fb.error = f"{reason}，已自动改用 edge-tts"
        else:
            fb.error = f"{reason}；edge-tts 降级也失败：{fb.error}"
        return fb

    if key == "xtts":
        try:
            from .xtts_offline import XTTSOffline
            engine_obj = XTTSOffline()
            b64 = engine_obj.synthesize_base64(text, voice)  # type: ignore[attr-defined]
            if b64:
                return TTSResult(b64, ENGINE_XTTS)
            reason = "XTTS 返回空音频"
        except Exception as e:  # noqa: BLE001
            reason = f"XTTS 调用异常：{type(e).__name__}: {e}"
        fb = _try_edge(text, "zh-CN-YunyangNeural")
        fb.fell_back = fb.ok
        fb.error = f"{reason}，已自动改用 edge-tts" if fb.ok else reason
        return fb

    return _try_edge(text, voice)


def _try_edge(text: str, voice: str) -> TTSResult:
    try:
        b64 = asyncio.run(_generate_edge_tts_base64(text, voice))
        if b64:
            return TTSResult(b64, ENGINE_EDGE)
        return TTSResult(error="edge-tts 返回空音频")
    except ImportError:
        return TTSResult(error="未安装 edge-tts：pip install edge-tts")
    except Exception as e:  # noqa: BLE001
        # ★ 不再只 print 到终端 —— Streamlit 里那是看不见的地方
        return TTSResult(error=f"edge-tts 失败：{type(e).__name__}: {e}")
