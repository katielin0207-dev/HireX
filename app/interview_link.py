"""
面试链接生成模块

生成唯一 token + 面试链接，支持候选人端访问。
当前为前端形式实现（无后端），未来可直接对接数据库。
"""

import hashlib
import time
import uuid
from datetime import datetime, timedelta


# 内存存储（模拟数据库）
_active_interviews = {}


def generate_token(jd_title: str = "") -> str:
    """生成唯一面试 token"""
    raw = f"{uuid.uuid4()}-{time.time()}"
    token = hashlib.sha256(raw.encode()).hexdigest()[:16]
    return token


def create_interview_link(
    base_url: str = "http://localhost:8501",
    jd_title: str = "岗位面试",
    persona_name: str = "AI面试官",
    max_rounds: int = 8,
    expire_hours: int = 48,
    interview_config: dict | None = None,
) -> dict:
    """
    创建一次面试，生成唯一的候选人链接。

    Args:
        interview_config: 面试配置 dict，包含：
            - jd_data: 结构化JD数据
            - resume_data: 结构化简历数据
            - persona: 面试官人格 {persona_name, system_prompt, strategy, ...}
            - conversation_history: 初始对话历史
            - selected_questions: 抽取的面试题
            - remaining_pool: 备选题库

    Returns:
        dict: {
            "token": "abc123...",
            "link": "http://localhost:8501?role=candidate&token=abc123",
            "expires_at": "2026-07-02 16:00:00",
            "jd_title": "算法工程师",
            "persona_name": "王主管",
            "max_rounds": 8,
        }
    """
    token = generate_token(jd_title)
    expires_at = datetime.now() + timedelta(hours=expire_hours)

    _active_interviews[token] = {
        "token": token,
        "jd_title": jd_title,
        "persona_name": persona_name,
        "max_rounds": max_rounds,
        "expires_at": expires_at,
        "created_at": datetime.now(),
        "status": "active",
        "interview_config": interview_config or {},
    }

    link = f"{base_url}?role=candidate&token={token}"

    return {
        "token": token,
        "link": link,
        "expires_at": expires_at.strftime("%Y-%m-%d %H:%M"),
        "jd_title": jd_title,
        "persona_name": persona_name,
        "max_rounds": max_rounds,
    }


def get_interview(token: str) -> dict | None:
    """根据 token 获取面试信息"""
    interview = _active_interviews.get(token)
    if not interview:
        return None
    if interview["expires_at"] < datetime.now():
        interview["status"] = "expired"
        return None
    return interview


def deactivate_interview(token: str):
    """标记面试为已结束"""
    if token in _active_interviews:
        _active_interviews[token]["status"] = "completed"


def list_active_interviews() -> list:
    """列出所有活跃的面试"""
    now = datetime.now()
    active = []
    for t, info in _active_interviews.items():
        if info["expires_at"] > now and info["status"] == "active":
            active.append(info)
    return sorted(active, key=lambda x: x["created_at"], reverse=True)
