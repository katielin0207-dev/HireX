#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIOffer-Research: 将 interview_data.json 注入 HTML 模板
用法: python merge_template.py
  或: python merge_template.py <json_path> [output_html_path]
"""

import json
import os
import sys

SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
DEFAULT_JSON = os.path.join(SCRIPT_DIR, "..", "interview_data.json")
DEFAULT_HTML = os.path.join(SCRIPT_DIR, "..", "..", "AIOffer-Research-模拟面试.html")
TEMPLATE_PATH = os.path.join(SCRIPT_DIR, "..", "assets", "interview-template.html")


def main():
    json_path = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_JSON
    output_path = sys.argv[2] if len(sys.argv) > 2 else DEFAULT_HTML

    print(f"📖 读取 JSON: {json_path}")
    with open(json_path, "r", encoding="utf-8") as f:
        interview_data = json.load(f, strict=False)

    print(f"📄 读取模板: {TEMPLATE_PATH}")
    with open(TEMPLATE_PATH, "r", encoding="utf-8") as f:
        template = f.read()

    # 序列化 JSON，确保中文正确
    json_str = json.dumps(interview_data, ensure_ascii=False, indent=2)

    # 替换占位符
    result = template.replace("{{INTERVIEW_JSON}}", json_str)
    result = result.replace("{{CANDIDATE_NAME}}", interview_data.get("candidateName", ""))
    result = result.replace("{{POSITION}}", interview_data.get("position", ""))
    result = result.replace("{{TOTAL_QUESTIONS}}", str(interview_data.get("totalQuestions", "")))

    # 检查是否还有未替换的占位符
    import re
    remaining = re.findall(r"\{\{[^}]+\}\}", result)
    if remaining:
        print(f"⚠️  警告: 仍有未替换的占位符: {set(remaining)}")

    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        f.write(result)

    file_size = os.path.getsize(output_path)
    print(f"✅ 生成成功: {output_path}")
    print(f"   文件大小: {file_size:,} bytes ({file_size // 1024} KB)")
    print(f"   候选人: {interview_data.get('candidateName', '')}")
    print(f"   岗位: {interview_data.get('position', '')}")
    print(f"   总题数: {interview_data.get('totalQuestions', '')}")


if __name__ == "__main__":
    main()
