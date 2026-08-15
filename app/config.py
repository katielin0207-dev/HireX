"""HireX 模型与服务配置。"""
import os
from dotenv import load_dotenv

load_dotenv()


def _read_setting(name: str, default: str = "") -> str:
    """优先读取部署平台 Secrets，其次读取本机环境变量。"""
    env_value = os.getenv(name)
    if env_value is not None:
        return env_value
    try:
        import streamlit as st
        return str(st.secrets.get(name, default))
    except Exception:
        return default


class Settings:
    """全局配置，所有配置项从环境变量读取，敏感信息不硬编码。"""

    LLM_API_KEY: str = _read_setting("LLM_API_KEY", "")
    LLM_BASE_URL: str = _read_setting("LLM_BASE_URL", "https://api.deepseek.com")
    LLM_MODEL: str = _read_setting("LLM_MODEL", "deepseek-v4-flash")

    HOST: str = os.getenv("HOST", "127.0.0.1")
    PORT: int = int(os.getenv("PORT", "8501"))

    TEMPERATURE: float = 0.3
    MAX_TOKENS: int = 8192
    TIMEOUT: int = 90
    MAX_RETRIES: int = 3

    @property
    def is_configured(self) -> bool:
        """检查 LLM 是否已配置，并排除示例占位符。"""
        key = self.LLM_API_KEY.strip()
        if not key:
            return False
        normalized = key.lower().replace("_", "-")
        placeholders = (
            "your-api-key",
            "api-key-here",
            "replace-me",
            "请填写",
            "你的-",
            "here is invalid",
        )
        return not any(marker in normalized for marker in placeholders)

settings = Settings()
