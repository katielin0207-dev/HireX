'''
SkillMerger：将多个 Skill 的产出合并到主流程。
'''


class SkillMerger:
    @staticmethod
    def merge_questions(base_questions: list, skill_outputs: dict) -> list:
        merged = list(base_questions)
        for skill_id, questions in skill_outputs.items():
            if not questions:
                continue
            for q in questions:
                q["source"] = f"skill:{skill_id}"
                merged.append(q)
        return merged

    @staticmethod
    def merge_match_adjustments(base_score: int, skill_adjustments: dict) -> dict:
        final_score = base_score
        adjustments = []
        for skill_id, adj in skill_adjustments.items():
            delta = adj.get("adjustment", 0)
            reason = adj.get("reason", "")
            final_score += delta
            adjustments.append({"skill_id": skill_id, "adjustment": delta, "reason": reason})
        final_score = max(0, min(100, final_score))
        return {"final_score": final_score, "base_score": base_score, "adjustments": adjustments}
