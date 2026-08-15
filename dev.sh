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
    .venv/bin/pip install -r requirements.txt
fi

# 检查 .env
if [ ! -f ".env" ]; then
    echo "错误: .env 不存在。请复制 .env.example 并填入 LLM_API_KEY"
    exit 1
fi

# 检查 Mock 数据
if [ ! -d "mock/resumes" ] || [ -z "$(ls -A mock/resumes 2>/dev/null)" ]; then
    echo "生成 Mock 数据..."
    .venv/bin/python mock/gen_mock_resumes.py
    .venv/bin/python mock/gen_mock_candidates.py
fi

# 演示模式
if [ "$1" = "demo" ]; then
    echo "=== 演示模式（读缓存，不调 API）==="
    export DEMO_MODE=on
fi

echo "启动中... http://127.0.0.1:8501"
.venv/bin/python -m streamlit run app/main.py \
    --server.address 127.0.0.1 \
    --server.port 8501 \
    --server.headless true
