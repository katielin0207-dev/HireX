import pytest

from app.success_feedback import apply_feedback_to_jd, fallback_success_feedback, generate_success_feedback


def _candidate():
    return {
        "resume_parsed": {
            "education": [{"school": "某大学", "degree": "本科", "major": "工业工程"}],
            "experience": [{"company": "某家电企业", "title": "质量工程师"}],
            "skills": ["8D", "SPC", "FMEA"],
        },
        "match_result": {"matched_points": ["有质量改善项目证据"]},
        "interview_eval": {
            "summary": "能用8D推动跨部门闭环。",
            "dimension_scores": {"问题解决": 92, "协作沟通": 88},
        },
    }


def _jd():
    return {
        "title": "质量工程师",
        "requirements": {
            "hard": {"must_skills": ["ISO 9001"]},
            "soft": ["沟通协作"],
        },
        "weights": {"degree": .20, "years": .20, "skills": .40, "soft": .20},
    }


def test_fallback_feedback_has_three_traceable_suggestions():
    suggestions = fallback_success_feedback(_candidate(), _jd())
    assert len(suggestions) == 3
    assert all(item["evidence"] for item in suggestions)
    weight_action = next(item["action"] for item in suggestions if item["action"]["kind"] == "set_weights")
    assert round(sum(weight_action["value"].values()), 2) == 1.0


def test_adopted_skill_updates_next_jd_without_mutating_original():
    jd = _jd()
    updated = apply_feedback_to_jd(jd, {"action": {"kind": "add_skill", "value": "8D"}})
    assert "8D" in updated["requirements"]["hard"]["must_skills"]
    assert "8D" not in jd["requirements"]["hard"]["must_skills"]
    assert updated["generation_status"] == "success_sample_optimized_draft"


def test_invalid_weight_suggestion_is_rejected():
    with pytest.raises(ValueError):
        apply_feedback_to_jd(_jd(), {
            "action": {
                "kind": "set_weights",
                "value": {"degree": .5, "years": .5, "skills": .5, "soft": .5},
            }
        })


def test_invalid_ai_weight_suggestion_falls_back_to_safe_rules():
    def invalid_ai(_prompt, expect_json=True):
        return {
            "suggestions": [{
                "title": "错误权重",
                "evidence": [{"source": "测试", "quote": "有依据"}],
                "action": {
                    "kind": "set_weights",
                    "value": {"degree": .5, "years": .5, "skills": .5, "soft": .5},
                },
            }]
        }

    feedback = generate_success_feedback(_candidate(), _jd(), llm_caller=invalid_ai)
    assert len(feedback["suggestions"]) == 3
    assert round(sum(feedback["suggestions"][1]["action"]["value"].values()), 2) == 1.0
