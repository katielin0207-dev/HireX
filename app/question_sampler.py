"""
题库随机抽取模块：从分析环节生成的完整题库中，按策略随机抽取 N 道题供 AI 面试使用。

抽取策略：
1. 分层抽样：按维度（category/tags）分组，每个维度至少保底1题
2. 随机补足：保底后随机从剩余题库补齐到目标题数
3. 保留元信息：每道题完整保留 question/tags/hints/answer/difficulty/scoring_criteria 等
4. 剩余题库：未抽取的题目作为 remaining_pool 供面试官追问/切换时使用
"""
import random
import json
from collections import defaultdict
from typing import Optional


def sample_questions_for_interview(
    all_questions: list[dict],
    n_rounds: int = 8,
    dimension_field: str = "category",
) -> tuple[list[dict], list[dict]]:
    """
    从完整题库中随机抽取 N 道题用于 AI 面试。

    Args:
        all_questions: 分析环节生成的全部题目列表，每題含 question/tags/category 等
        n_rounds: 需要抽取的题目数量（默认8）
        dimension_field: 用于分层的字段名，默认 "category"（如"技术基础/项目深挖/..."）

    Returns:
        (selected_questions, remaining_pool) 元组
        - selected_questions: 抽取的题目列表（按原维度排序）
        - remaining_pool: 未被抽取的题目列表（作为备选题库）

    抽取规则：
    1. N = min(n_rounds, len(all_questions))
    2. 按维度(category)分层：每个维度至少抽取1题（如果该维度有题的话）
    3. 剩余名额从所有未抽取题目中随机补足
    4. 保留完整题目元信息
    """
    n = min(n_rounds, len(all_questions))
    if n <= 0:
        return [], list(all_questions)

    # 按维度分组
    by_dimension = defaultdict(list)
    for i, q in enumerate(all_questions):
        dim = q.get(dimension_field, "未分类")
        by_dimension[dim].append((i, q))

    dimensions = list(by_dimension.keys())
    selected_indices = set()
    selected = []

    # 第1轮：每个有題的维度保底1题
    guaranteed = 0
    for dim in dimensions:
        pool = by_dimension[dim]
        if pool:
            idx, q = random.choice(pool)
            if idx not in selected_indices:
                selected_indices.add(idx)
                selected.append(q)
                guaranteed += 1

    # 第2轮：随机补足到 N
    remaining_indices = [i for i in range(len(all_questions)) if i not in selected_indices]
    needed = n - len(selected)
    if needed > 0 and remaining_indices:
        # 随机打乱，取前 needed 个
        random.shuffle(remaining_indices)
        for idx in remaining_indices[:needed]:
            selected.append(all_questions[idx])
            selected_indices.add(idx)

    # 最终截断为 N
    selected = selected[:n]
    
    # 用最终选中列表的索引重建 selected_indices
    final_indices = set()
    for sq in selected:
        for i, q in enumerate(all_questions):
            if q is sq:
                final_indices.add(i)
                break

    # 剩余题库 = 不在最终列表中的题目
    remaining_pool = [q for i, q in enumerate(all_questions) if i not in final_indices]

    return selected, remaining_pool


def sample_questions_by_tags(
    all_questions: list[dict],
    n_rounds: int = 8,
) -> tuple[list[dict], list[dict]]:
    """
    按 tags 字段分层抽样（备选方案）。
    tags 是数组如 ["resume", "position", "basic", "quality"]，每个 tag 保底1题。

    Args:
        all_questions: 分析环节生成的全部题目列表
        n_rounds: 需要抽取的题目数量

    Returns:
        (selected_questions, remaining_pool)
    """
    n = min(n_rounds, len(all_questions))
    if n <= 0:
        return [], list(all_questions)

    # 按 tag 分组
    by_tag = defaultdict(list)
    for i, q in enumerate(all_questions):
        tags = q.get("tags", [])
        if not tags:
            tags = ["未分类"]
        for tag in tags:
            by_tag[tag].append((i, q))

    selected_indices = set()
    selected = []

    # 每个 tag 保底1题
    for tag, pool in by_tag.items():
        if pool:
            idx, q = random.choice(pool)
            if idx not in selected_indices:
                selected_indices.add(idx)
                selected.append(q)

    # 补足
    remaining_indices = [i for i in range(len(all_questions)) if i not in selected_indices]
    needed = n - len(selected)
    if needed > 0 and remaining_indices:
        random.shuffle(remaining_indices)
        for idx in remaining_indices[:needed]:
            selected.append(all_questions[idx])
            selected_indices.add(idx)

    selected = selected[:n]
    
    final_indices = set()
    for sq in selected:
        for i, q in enumerate(all_questions):
            if q is sq:
                final_indices.add(i)
                break

    remaining_pool = [q for i, q in enumerate(all_questions) if i not in final_indices]

    return selected, remaining_pool


def get_dimension_stats(questions: list[dict], dimension_field: str = "category") -> dict:
    """统计题目维度分布，用于前端展示"""
    stats = defaultdict(int)
    for q in questions:
        dim = q.get(dimension_field, "未分类")
        stats[dim] += 1
    return dict(stats)
