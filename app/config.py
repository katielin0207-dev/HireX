"""
配置管理：从 .env 文件读取环境变量，统一管理 LLM 和服务配置。
合并自 AI-Interview Agent (场景B) + AIOffer-Research (场景A)
"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置，所有配置项从环境变量读取，敏感信息不硬编码。"""

    # ===== LLM 通用配置 =====
    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    # ===== 服务配置 =====
    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8501"))

    # ===== LLM 调用参数 =====
    TEMPERATURE: float = 0.3       # 默认低温度保证输出稳定
    EVAL_TEMPERATURE: float = 0.3  # 评估/评分专用温度
    MAX_TOKENS: int = 8192
    TIMEOUT: int = 90              # 单次请求超时（秒）
    MAX_RETRIES: int = 3

    # ===== 场景A：匹配评分 + 试题生成 =====
    MATCH_DIMENSIONS: list = ["skills", "experience", "education", "projects"]
    MIN_QUESTIONS: int = 12

    # ===== 场景B：AI 面试官 =====
    DEFAULT_MAX_ROUNDS: int = 8
    MIN_ROUNDS: int = 3
    MAX_ROUNDS: int = 15
    DEFAULT_SAMPLE_ROUNDS: int = 8  # 从题库中随机抽取的题数

    # ===== 讯飞数字人/TTS 配置 =====
    XUNFEI_APP_ID: str = os.getenv("XUNFEI_APP_ID", "")
    XUNFEI_API_KEY: str = os.getenv("XUNFEI_API_KEY", "")
    XUNFEI_API_SECRET: str = os.getenv("XUNFEI_API_SECRET", "")
    TTS_ENGINE: str = os.getenv("TTS_ENGINE", "edge-tts")  # edge-tts | xunfei | openai

    @property
    def is_configured(self) -> bool:
        """检查 LLM 是否已配置"""
        return bool(self.LLM_API_KEY)

    @property
    def xunfei_configured(self) -> bool:
        """检查讯飞 TTS 是否已配置"""
        return bool(self.XUNFEI_APP_ID and self.XUNFEI_API_KEY and self.XUNFEI_API_SECRET)


settings = Settings()
