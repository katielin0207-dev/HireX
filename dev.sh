#!/bin/bash
# 一键开发环境启动脚本
# 用法: ./dev.sh          正常启动
#       ./dev.sh demo     演示模式（读缓存，不调 API）
set -e

cd "$(dirname "$0")"

# 检查虚拟环境
if [ ! -d ".venv" ]; then
    echo "首次运行，创建虚拟环境..."
    python3 -m venv .venv
fi
.venv/bin/pip install -q -r requirements.txt

# 检查 .env
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "已创建本机 .env；未填 Key 时自动使用本地演示模式。"
fi

# 检查 Mock 数据
if [ ! -d "mock/resumes" ] || [ -z "$(ls -A mock/resumes 2>/dev/null)" ]; then
    echo "生成 Mock 数据..."
    .venv/bin/python mock/gen_mock_resumes.py
fi
if [ ! -f "sessions/jd.json" ] || [ -z "$(ls sessions/candidates/*.json 2>/dev/null)" ]; then
    echo "生成候选人演示数据..."
    .venv/bin/python mock/gen_mock_candidates.py
fi

# 演示模式
if [ "$1" = "demo" ] || ! .venv/bin/python -c "from app.config import settings; raise SystemExit(0 if settings.is_configured else 1)"; then
    echo "=== 演示模式（读缓存，不调 API）==="
    export DEMO_MODE=on
else
    echo "=== 真实 AI 模式：模型配置已读取 ==="
fi

echo "启动中... http://127.0.0.1:8501"
.venv/bin/python -m streamlit run app/main.py \
    --server.address 127.0.0.1 \
    --server.port 8501 \
    --server.headless true
