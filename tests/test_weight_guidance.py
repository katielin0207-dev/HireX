from app.shared.job_utils import (
    validate_weight_total,
    weight_deviation_hint,
    weight_template_for,
)


def test_technical_job_uses_skill_heavy_template():
    template = weight_template_for({
        "title": "Python 后端开发工程师",
        "category": "工程师/技术岗",
        "recommended_weights": {
            "degree": .15, "years": .15, "skills": .45, "soft": .25,
        },
    })
    assert template["key"] == "technical"
    assert template["ranges"]["skills"] == (35, 50)
    assert template["tags"]["skills"] == "技术岗偏高"
    assert sum(template["defaults"].values()) == 100


def test_campus_and_senior_jobs_receive_different_guidance():
    campus = weight_template_for({"title": "校招管培生", "category": "职能/非技术岗"})
    senior = weight_template_for({"title": "资深质量工程师", "category": "质量/IE 方向"})
    assert campus["key"] == "campus"
    assert campus["ranges"]["degree"][0] >= 20
    assert senior["key"] == "senior"
    assert senior["ranges"]["years"][0] >= 25


def test_weight_total_is_strongly_validated():
    total, valid, message = validate_weight_total(
        {"degree": 20, "years": 20, "skills": 40, "soft": 12}
    )
    assert (total, valid) == (92, False)
    assert "还差 8%" in message

    total, valid, message = validate_weight_total(
        {"degree": 20, "years": 20, "skills": 40, "soft": 20}
    )
    assert (total, valid) == (100, True)
    assert "配置有效" in message


def test_degree_deviation_explains_business_effect():
    message, level = weight_deviation_hint("degree", 35, (10, 20))
    assert level == "warn"
    assert "校招" in message
    assert "实操型岗位" in message
