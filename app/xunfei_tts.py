"""
讯飞 TTS 语音合成模块 — 浏览器内实时播放版

使用讯飞开放平台 WebSocket API 实现语音合成。
文档：https://www.xfyun.cn/doc/tts/online_tts/API.html

音频在内存中收集 → base64 返回，不写磁盘、不弹外部播放器。

如需使用：pip install websocket-client
"""
import hashlib
import hmac
import base64
import json
from datetime import datetime
from urllib.parse import urlencode


def _build_auth_url(app_id: str, api_key: str, api_secret: str, host: str, path: str) -> str:
    """构建讯飞鉴权 URL"""
    now = datetime.utcnow()
    date = now.strftime("%a, %d %b %Y %H:%M:%S GMT")

    signature_origin = "host: {}\ndate: {}\nGET {} HTTP/1.1".format(host, date, path)
    signature_sha = hmac.new(
        api_secret.encode('utf-8'),
        signature_origin.encode('utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    signature = base64.b64encode(signature_sha).decode()

    authorization_origin = (
        'api_key="{}", algorithm="hmac-sha256", headers="host date request-line", signature="{}"'
        .format(api_key, signature)
    )
    authorization = base64.b64encode(authorization_origin.encode('utf-8')).decode()

    query = urlencode({
        "authorization": authorization,
        "date": date,
        "host": host,
    })
    return "ws://{}{}?{}".format(host, path, query)


def generate_xunfei_base64(text: str, voice: str = "x4_lingxiaoxuan") -> str | None:
    """
    使用讯飞 TTS 合成语音，返回 base64 编码的 MP3 音频。
    不写文件、不调外部播放器 — 交给浏览器 <audio> 元素播放。

    Args:
        text: 要朗读的文本（中文，最大 500 字）
        voice: 发音人
            精品发音人（推荐）:
            - x4_lingxiaoxuan: 小璇（精品女声，自然亲切）★推荐
            - x4_jifeng:       疾风（精品男声，专业稳重）★推荐
            - x4_lingfeichen:  飞晨（精品男声，温暖）
            - x4_lingxiaozhen: 小臻（精品女声，知性）
            - x4_lingxiaoyi:   小伊（精品女声，温柔）
            - x4_tingting:     婷婷（精品女声，甜美）
            基础发音人:
            - xiaoyan: 小燕（亲切女声）
            - aisjiuxu: 许久（沉稳男声）
            - aisxping: 小萍（知性女声）
            - aisjinger: 小婧（温柔女声）

    Returns:
        base64 编码的 MP3 音频字符串，失败返回 None
    """
    try:
        from app.config import settings

        if not settings.xunfei_configured:
            print("Xunfei TTS not configured")
            return None

        # 精简文本（最大 500 字）
        text = text[:500]

        import websocket
        import ssl

        host = "tts-api.xfyun.cn"
        path = "/v2/tts"
        url = _build_auth_url(
            settings.XUNFEI_APP_ID,
            settings.XUNFEI_API_KEY,
            settings.XUNFEI_API_SECRET,
            host,
            path,
        )

        audio_data = bytearray()

        def on_message(ws, message):
            try:
                msg = json.loads(message)
                if msg.get("code") != 0:
                    print("TTS error: {}".format(msg.get("message", "unknown")))
                    return
                if "data" in msg:
                    audio = base64.b64decode(msg["data"]["audio"])
                    audio_data.extend(audio)
                if msg.get("data", {}).get("status") == 2:
                    ws.close()
            except Exception:
                pass

        def on_error(ws, error):
            print("TTS websocket error: {}".format(error))

        def on_close(ws, code, msg):
            pass

        def on_open(ws):
            params = {
                "common": {"app_id": settings.XUNFEI_APP_ID},
                "business": {
                    "aue": "lame",     # MP3 格式
                    "sfl": 1,
                    "auf": "audio/L16;rate=16000",
                    "vcn": voice,      # 发音人
                    "speed": 50,       # 语速
                    "volume": 50,      # 音量
                    "pitch": 50,       # 音调
                    "tte": "utf8",
                },
                "data": {
                    "status": 2,
                    "text": base64.b64encode(text.encode('utf-8')).decode(),
                },
            }
            ws.send(json.dumps(params))

        ws = websocket.WebSocketApp(
            url,
            on_message=on_message,
            on_error=on_error,
            on_close=on_close,
            on_open=on_open,
        )
        ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE})

        if not audio_data:
            return None

        return base64.b64encode(bytes(audio_data)).decode()

    except ImportError:
        print("Xunfei TTS requires: pip install websocket-client")
        return None
    except Exception as e:
        print("TTS error: {}".format(e))
        return None


# 可用发音人映射
XUNFEI_VOICES = {
    # 精品发音人（音质好，推荐）
    "x4_lingxiaoxuan": "小璇（精品女声，自然亲切）★推荐",
    "x4_jifeng":       "疾风（精品男声，专业稳重）★面试官推荐",
    "x4_lingfeichen":  "飞晨（精品男声，温暖）",
    "x4_lingxiaozhen": "小臻（精品女声，知性）",
    "x4_lingxiaoyi":   "小伊（精品女声，温柔）",
    "x4_tingting":     "婷婷（精品女声，甜美）",
    # 基础发音人
    "xiaoyan":    "小燕（亲切女声）",
    "aisjiuxu":   "许久（沉稳男声）",
    "aisxping":   "小萍（知性女声）",
    "aisjinger":  "小婧（温柔女声）",
}
