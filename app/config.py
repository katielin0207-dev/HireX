"""HireX 模型与服务配置。"""
import os
from dotenv import load_dotenv

load_dotenv()


class Settings:
    """全局配置，所有配置项从环境变量读取，敏感信息不硬编码。"""

    LLM_API_KEY: str = os.getenv("LLM_API_KEY", "")
    LLM_BASE_URL: str = os.getenv("LLM_BASE_URL", "https://api.deepseek.com/v1")
    LLM_MODEL: str = os.getenv("LLM_MODEL", "deepseek-chat")

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8501"))

    TEMPERATURE: float = 0.3
    MAX_TOKENS: int = 8192
    TIMEOUT: int = 90
    MAX_RETRIES: int = 3

    @property
    def is_configured(self) -> bool:
        """检查 LLM 是否已配置"""
        return bool(self.LLM_API_KEY)

settings = Settings()
