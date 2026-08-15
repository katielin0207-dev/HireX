from app.talent_pool import (
    comparison_rows,
    decision_score,
    display_stage,
    radar_scores,
    recommend_backups,
)


def _candidate(candidate_id, score, risk="低", status="screened"):
    return {
        "id": candidate_id,
        "name": candidate_id,
        "status": status,
        "match_result": {
            "overall_score": score,
            "hard_score": score,
            "soft_score": score,
            "breakdown": {
                "skills_match": {"score": score},
                "experience_match": {"score": score - 1},
                "education_match": {"score": 100},
                "project_relevance": {"score": score - 2},
            },
        },
        "risk_report": {"level": risk},
        "tags": [],
    }


def test_comparison_rows_are_ranked():
    rows = comparison_rows([_candidate("B", 70), _candidate("A", 90)])
    assert [row["候选人"] for row in rows] == ["A", "B"]


def test_radar_scores_follow_contract():
    scores = radar_scores(_candidate("A", 90))
    assert scores == {"技能": 90.0, "经验": 89.0, "学历": 100.0, "项目": 88.0}


def test_backup_excludes_declined_and_high_risk():
    candidates = [
        _candidate("winner", 95, status="declined"),
        _candidate("risky", 92, risk="高"),
        _candidate("backup", 80),
    ]
    backups = recommend_backups(candidates, "winner")
    assert [candidate["id"] for candidate in backups] == ["backup"]


def test_decision_score_requires_interview_evidence():
    candidate = _candidate("A", 90)
    assert decision_score(candidate) is None
    candidate["interview_eval"] = {"dimension_scores": {"专业能力": 80, "沟通表达": 90}}
    assert decision_score(candidate) == 89.2


def test_display_stage_prioritizes_business_status():
    candidate = _candidate("A", 90, status="offered")
    candidate["interview_eval"] = {"dimension_scores": {"专业能力": 80}}
    assert display_stage(candidate) == "已发Offer"


def test_display_stage_marks_success_sample():
    candidate = _candidate("A", 90, status="hired")
    assert display_stage(candidate) == "已入职·成功样本"
