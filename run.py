#!/usr/bin/env python3
"""
AI 智能招聘系统 - 一键启动

Usage:
  1. Copy .env.example to .env and fill in your LLM_API_KEY
  2. pip install -r requirements.txt
  3. python run.py
  4. Open http://127.0.0.1:8501 in browser

功能：
  · 简历分析 Tab — JD+简历解析 / 匹配度评分 / 试题生成 / 模糊点追问
  · AI面试 Tab — 面试官角色扮演 / 多轮对话 / TTS语音 / 数字人
  · 评估报告 Tab — 5维雷达图 / 逐题评审 / 录用建议
"""
import sys
import os
import subprocess

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    # Check .env
    if not os.path.exists(".env"):
        print("=" * 60)
        print("  .env file not found!")
        print("=" * 60)
        print()
        print("Please:")
        print("  1. Copy .env.example to .env")
        print("  2. Fill in your LLM_API_KEY")
        print()
        print("Supported providers:")
        print("  DeepSeek: LLM_BASE_URL=https://api.deepseek.com/v1")
        print("            LLM_MODEL=deepseek-chat")
        print("  Qwen:     LLM_BASE_URL=https://dashscope.aliyuncs.com/compatible-mode/v1")
        print("            LLM_MODEL=qwen-plus")
        print("  OpenAI:   LLM_BASE_URL=https://api.openai.com/v1")
        print("            LLM_MODEL=gpt-4o")
        print("  Kimi:     LLM_BASE_URL=https://api.moonshot.cn/v1")
        print("            LLM_MODEL=moonshot-v1-8k")
        print()
        sys.exit(1)

    from app.config import settings
    if not settings.is_configured:
        print("=" * 60)
        print("  LLM_API_KEY not configured!")
        print("=" * 60)
        print("  Please edit .env and set LLM_API_KEY")
        print()
        sys.exit(1)

    print("=" * 60)
    print("  AI 智能招聘系统 v2.0")
    print("=" * 60)
    print(f"  Model: {settings.LLM_MODEL}")
    print(f"  URL:   http://{settings.HOST}:{settings.PORT}")
    print("=" * 60)
    print()

    # Launch Streamlit
    subprocess.run([
        sys.executable, "-m", "streamlit", "run",
        os.path.join("app", "main.py"),
        "--server.address", settings.HOST,
        "--server.port", str(settings.PORT),
    ])


if __name__ == "__main__":
    main()
