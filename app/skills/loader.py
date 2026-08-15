'''
SkillLoader：从 YAML 目录加载 Skill。
'''

import os
from .registry import SkillRegistry


class SkillLoader:
    @staticmethod
    def load_from_directory(skills_dir: str) -> dict:
        registry = SkillRegistry(skills_dir)
        registry.load_all()
        return {s.skill_id: s for s in registry.list_all()}
