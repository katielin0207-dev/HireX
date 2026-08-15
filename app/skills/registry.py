'''
SkillRegistry：Skill 注册表，管理所有已安装的 Skill 的生命周期。

操作：list / insert / activate / deactivate / delete / hot_reload
'''

import os
import datetime
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class SkillDefinition:
    skill_id: str
    name: str
    category: str
    trigger: str
    description: str
    depends_on: list = field(default_factory=list)
    produces: list = field(default_factory=list)
    prompt_template: str = ""
    validation_rules: list = field(default_factory=list)
    active: bool = True
    installed_at: str = ""
    source_path: str = ""


class SkillRegistry:
    def __init__(self, skills_dir: str = None):
        self.skills_dir = skills_dir or os.path.join(os.path.dirname(__file__))
        self._skills: dict[str, SkillDefinition] = {}
        self._loaded = False

    def load_all(self) -> int:
        count = 0
        if not os.path.isdir(self.skills_dir):
            return 0
        for item in os.listdir(self.skills_dir):
            skill_dir = os.path.join(self.skills_dir, item)
            if not os.path.isdir(skill_dir) or item.startswith("_"):
                continue
            yaml_path = os.path.join(skill_dir, "skill.yaml")
            if not os.path.exists(yaml_path):
                continue
            try:
                skill = self._load_from_yaml(yaml_path, skill_dir)
                self._skills[skill.skill_id] = skill
                count += 1
            except Exception as e:
                print(f"[SkillRegistry] Failed to load {item}: {e}")
        self._loaded = True
        return count

    def _load_from_yaml(self, yaml_path: str, skill_dir: str) -> SkillDefinition:
        data = self._parse_simple_yaml(open(yaml_path, 'r', encoding='utf-8').read())
        prompt_file = os.path.join(skill_dir, "prompt_template.txt")
        if os.path.exists(prompt_file):
            prompt_template = open(prompt_file, 'r', encoding='utf-8').read()
        else:
            prompt_template = data.get("prompt_template", "")
        return SkillDefinition(
            skill_id=data.get("skill_id", os.path.basename(skill_dir)),
            name=data.get("name", ""),
            category=data.get("category", "assessment"),
            trigger=data.get("trigger", "on_question_generation"),
            description=data.get("description", ""),
            depends_on=data.get("depends_on", []) if isinstance(data.get("depends_on"), list) else [],
            produces=data.get("produces", []) if isinstance(data.get("produces"), list) else [],
            prompt_template=prompt_template,
            validation_rules=data.get("validation_rules", []) if isinstance(data.get("validation_rules"), list) else [],
            active=data.get("active", True),
            installed_at=datetime.datetime.now().isoformat(),
            source_path=skill_dir,
        )

    def _parse_simple_yaml(self, content: str) -> dict:
        result = {}
        current_key = None
        current_list = None
        for line in content.split('\n'):
            stripped = line.strip()
            if not stripped or stripped.startswith('#'):
                continue
            if ':' in stripped and not stripped.startswith('-') and not stripped.startswith(' '):
                if current_key and current_list is not None:
                    result[current_key] = current_list
                key, _, value = stripped.partition(':')
                key = key.strip()
                value = value.strip()
                if value:
                    vl = value.lower()
                    if vl == 'true': result[key] = True
                    elif vl == 'false': result[key] = False
                    else: result[key] = value.strip('\'"')
                    current_key = None
                    current_list = None
                else:
                    current_key = key
                    current_list = None
            elif stripped.startswith('- ') and current_key:
                if current_list is None:
                    current_list = []
                current_list.append(stripped[2:].strip().strip('\'"'))
        if current_key and current_list is not None:
            result[current_key] = current_list
        return result

    def insert(self, skill_id_or_path: str) -> Optional[SkillDefinition]:
        if skill_id_or_path in self._skills:
            self._skills[skill_id_or_path].active = True
            return self._skills[skill_id_or_path]
        if os.path.exists(skill_id_or_path):
            if os.path.isdir(skill_id_or_path):
                yaml_path = os.path.join(skill_id_or_path, "skill.yaml")
            else:
                yaml_path = skill_id_or_path
                skill_id_or_path = os.path.dirname(yaml_path)
            if os.path.exists(yaml_path):
                skill = self._load_from_yaml(yaml_path, skill_id_or_path)
                self._skills[skill.skill_id] = skill
                return skill
        return None

    def delete(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            del self._skills[skill_id]
            return True
        return False

    def activate(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            self._skills[skill_id].active = True
            return True
        return False

    def deactivate(self, skill_id: str) -> bool:
        if skill_id in self._skills:
            self._skills[skill_id].active = False
            return True
        return False

    def hot_reload(self, skill_id: str) -> Optional[SkillDefinition]:
        skill = self._skills.get(skill_id)
        if not skill or not skill.source_path:
            return None
        yaml_path = os.path.join(skill.source_path, "skill.yaml")
        if os.path.exists(yaml_path):
            updated = self._load_from_yaml(yaml_path, skill.source_path)
            updated.active = skill.active
            self._skills[skill_id] = updated
            return updated
        return None

    def list_all(self) -> list:
        return list(self._skills.values())

    def get(self, skill_id: str) -> Optional[SkillDefinition]:
        return self._skills.get(skill_id)

    def get_active_by_trigger(self, trigger: str) -> list:
        return [s for s in self._skills.values() if s.active and s.trigger == trigger]

    def get_by_category(self, category: str) -> list:
        return [s for s in self._skills.values() if s.category == category]

    def get_active_ids(self) -> list:
        return [s.skill_id for s in self._skills.values() if s.active]

    def count(self) -> int:
        return len(self._skills)

    def to_dict(self) -> dict:
        return {
            "total": self.count(),
            "active": len(self.get_active_ids()),
            "skills": [
                {"skill_id": s.skill_id, "name": s.name, "category": s.category,
                 "trigger": s.trigger, "description": s.description, "active": s.active}
                for s in self._skills.values()
            ],
        }

    def get_skill_prompts(self, trigger: str) -> dict:
        return {s.skill_id: s.prompt_template for s in self.get_active_by_trigger(trigger)}
