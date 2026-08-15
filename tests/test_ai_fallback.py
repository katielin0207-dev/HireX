from app.config import Settings
from app.views.job_posting import _local_jd_text, _local_parse_jd


def test_placeholder_api_key_is_not_configured():
    settings = Settings()
    settings.LLM_API_KEY = "your-api-key-here"
    assert settings.is_configured is False


def test_non_placeholder_api_key_is_configured():
    settings = Settings()
    settings.LLM_API_KEY = "sk-test-value-for-unit-test"
    assert settings.is_configured is True


def test_local_jd_fallback_is_clean_and_structured():
    parsed = _local_parse_jd("招聘质量工程师，本科，3年以上经验，熟悉 8D、FMEA，善于跨部门沟通。")
    text = _local_jd_text(parsed, {"position": "质量工程师", "base_requirements": "负责质量问题闭环"})
    assert parsed["hard"]["min_years"] == 3
    assert "8D" in parsed["hard"]["must_skills"]
    assert "# 质量工程师" in text
    assert "LLM 生成失败" not in text
