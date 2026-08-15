'''
Skills 模块：可插拔的招聘 Agent 能力扩展。

预置 Skills（6个）：
  tech-coding-test     — 技术笔试生成
  english-assessment   — 英语评估
  culture-fit          — 文化契合
  salary-negotiation   — 薪资谈判
  campus-recruit       — 校招专项
  executive-search     — 高管猎头
'''

from .registry import SkillRegistry
from .loader import SkillLoader
from .merger import SkillMerger

__all__ = ["SkillRegistry", "SkillLoader", "SkillMerger"]
