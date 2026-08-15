#!/usr/bin/env python3
"""HireX 招聘甄选 AI 智能体一键启动。

Usage:
  1. pip install -r requirements.txt
  2. python run.py
  3. Open http://127.0.0.1:8501 in browser

主流程：简历筛选（含岗位 JD 与面试辅助）→ 人才评价 → 录用前风险核验
"""
import sys
import os
import subprocess
import shutil

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))


def main():
    if not os.path.exists(".env"):
        shutil.copyfile(".env.example", ".env")
        print("  已创建 .env；未填 Key 时使用本地演示模式。")

    from app.config import settings
    if not settings.is_configured:
        os.environ["DEMO_MODE"] = "on"

    print("=" * 60)
    print("  HireX 招聘甄选 AI 智能体")
    print("=" * 60)
    print(f"  Mode:  {'真实 AI' if settings.is_configured else '本地演示'}")
    print(f"  Model: {settings.LLM_MODEL if settings.is_configured else '无需模型'}")
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
