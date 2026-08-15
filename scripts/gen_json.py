#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
AIOffer-Research: 面试题 JSON 数据生成脚本（通用模板版）
用法: python gen_json.py <output_json_path>
  或: python gen_json.py  (输出到当前目录 interview_data.json)

本脚本生成 DEMO 示例数据，用于展示面试页面效果。
实际使用时应由 AI 读取用户简历后动态生成（通过 WorkBuddy Skill 调用）。
"""

import json
import sys
import os

OUTPUT_PATH = sys.argv[1] if len(sys.argv) > 1 else "interview_data.json"

# ========== 通用 DEMO 面试题数据（不含个人隐私） ==========

interview_data = {
    "candidateName": "{{候选人姓名}}",
    "position": "{{目标岗位}}",
    "totalQuestions": 12,
    "rounds": [
        {
            "name": "第一轮：基础技术面",
            "questions": [
                {
                    "question": "请解释 Transformer 中 Multi-Head Attention 的原理，并写出 Q、K、V 的计算公式。",
                    "tags": ["position", "basic"],
                    "hints": [
                        "思考：Q/K/V 分别是什么的线性变换？",
                        "多头的作用是什么？相比单头有什么优势？",
                        "时间复杂度是多少？如何优化？"
                    ],
                    "answer": {
                        "intro": "Multi-Head Attention 是 Transformer 的核心组件，通过多个注意力头并行计算，捕获不同子空间的信息。",
                        "details": [
                            {
                                "title": "1. Q、K、V 计算公式",
                                "content": "对于输入序列 X ∈ R^(n×d_model)，通过三个可学习矩阵生成 Q、K、V：\n- Q = X·W_Q  (Query，查询向量)\n- K = X·W_K  (Key，键向量)\n- V = X·W_V  (Value，值向量)\n\n其中 W_Q, W_K, W_V ∈ R^(d_model × d_k)",
                                "code": """# PyTorch 实现 Multi-Head Attention 核心计算
import torch
import torch.nn as nn
import math

class MultiHeadAttention(nn.Module):
    def __init__(self, d_model, num_heads):
        super().__init__()
        assert d_model % num_heads == 0
        self.d_k = d_model // num_heads
        self.num_heads = num_heads
        self.W_q = nn.Linear(d_model, d_model, bias=False)
        self.W_k = nn.Linear(d_model, d_model, bias=False)
        self.W_v = nn.Linear(d_model, d_model, bias=False)
        self.W_o = nn.Linear(d_model, d_model, bias=False)
    
    def forward(self, x, mask=None):
        batch_size, seq_len, d_model = x.size()
        Q = self.W_q(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)
        K = self.W_k(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)
        V = self.W_v(x).view(batch_size, seq_len, self.num_heads, self.d_k).transpose(1, 2)
        scores = torch.matmul(Q, K.transpose(-2, -1)) / math.sqrt(self.d_k)
        if mask is not None:
            scores = scores.masked_fill(mask == 0, -1e9)
        attn_weights = torch.softmax(scores, dim=-1)
        output = torch.matmul(attn_weights, V)
        output = output.transpose(1, 2).contiguous().view(batch_size, seq_len, d_model)
        return self.W_o(output)"""
                            },
                            {
                                "title": "2. 缩放点积注意力公式",
                                "content": "Attention(Q, K, V) = softmax(Q·K^T / √d_k) · V\n\n- √d_k 缩放因子的作用：防止点积结果过大导致 softmax 梯度消失\n- 多头：将 d_model 拆成 h 个 d_k 维的子空间，各自独立计算后拼接"
                            },
                            {
                                "title": "3. 面试加分点",
                                "points": [
                                    "能说出为什么要除以 √d_k（梯度稳定性）",
                                    "知道 KV Cache 优化推理时 K/V 的复用机制",
                                    "了解 Multi-Query Attention (MQA) 和 Grouped-Query Attention (GQA) 的变体"
                                ]
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "只知道 Attention 是 Transformer 的一部分"},
                            {"level": 2, "desc": "能写出 Q/K/V 公式，知道多头的作用"},
                            {"level": 3, "desc": "能推导注意力公式，说出 √d_k 的作用，知道 MQA/GQA 等变体"}
                        ],
                        "bonus": "提到 Flash Attention 或 PagedAttention 等工程优化手段"
                    }
                },
                {
                    "question": "Python 的 GIL（全局解释器锁）是什么？它对多线程 CPU 密集型和 I/O 密集型任务的影响有何不同？",
                    "tags": ["basic"],
                    "hints": [
                        "GIL 保护了什么？为什么 CPython 需要它？",
                        "多线程在 CPU 密集和 I/O 密集下表现有何不同？",
                        "如何绕过 GIL 的限制？"
                    ],
                    "answer": {
                        "intro": "GIL 是 CPython 解释器级别的锁，同一时刻只允许一个线程执行 Python 字节码。对 CPU 密集型多线程无效，但对 I/O 密集型有效（I/O 等待时会释放 GIL）。",
                        "details": [
                            {
                                "title": "1. GIL 本质",
                                "content": "CPython 的内存管理（引用计数）不是线程安全的，GIL 通过强制单线程执行字节码来避免竞态条件。\n\n注意：GIL 只存在于 CPython，Jython/IronPython 没有；PyPy 有但可配置。"
                            },
                            {
                                "title": "2. CPU 密集 vs I/O 密集",
                                "content": "CPU 密集型（如矩阵运算）：多线程反而更慢，因为线程切换 + GIL 争抢开销大。\n→ 解决：用 multiprocessing（多进程，每个进程独立 GIL）或 C 扩展（如 NumPy 释放 GIL）。\n\nI/O 密集型（如网络请求、文件读写）：多线程有效，因为 I/O 等待时会释放 GIL，其他线程可以运行。",
                                "code": """import threading
import time
import concurrent.futures

def cpu_bound(n):
    return sum(i * i for i in range(n))

# 多线程（受 GIL 限制，无加速）
def test_threads():
    with concurrent.futures.ThreadPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(cpu_bound, 10**7) for _ in range(4)]
        return [f.result() for f in futures]

# 多进程（绕过 GIL，真正并行）
def test_processes():
    with concurrent.futures.ProcessPoolExecutor(max_workers=4) as ex:
        futures = [ex.submit(cpu_bound, 10**7) for _ in range(4)]
        return [f.result() for f in futures]"""
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "知道 GIL 存在，知道多线程受限制"},
                            {"level": 2, "desc": "能解释 GIL 的原理，区分 CPU 密集和 I/O 密集的场景差异"},
                            {"level": 3, "desc": "能写出 multiprocessing 对比代码，知道 Python 3.13 的 no-GIL 进展"}
                        ],
                        "bonus": "提到 NumPy 等 C 扩展在底层运算时会释放 GIL"
                    }
                },
                {
                    "question": "请手写一个 LRU Cache 的实现（含注释）。",
                    "tags": ["basic", "coding"],
                    "hints": [
                        "LRU 的淘汰策略是什么？",
                        "用什么数据结构可以在 O(1) 时间内完成 get 和 put？",
                        "Python 的 collections.OrderedDict 如何实现 LRU？"
                    ],
                    "answer": {
                        "intro": "LRU (Least Recently Used) Cache 在容量满时淘汰最久未访问的键值对。核心是用哈希表 + 双向链表实现 O(1) 的 get/put。",
                        "details": [
                            {
                                "title": "1. 实现思路",
                                "content": "- 哈希表：O(1) 查找 key 对应的节点\n- 双向链表：维护访问顺序，头=最新，尾=最旧\n- get 时：命中则移到头部\n- put 时：已存在则更新并移到头部；不存在则插入头部，若超容则删尾部"
                            },
                            {
                                "title": "2. Python 实现（两种写法）",
                                "code": """# 写法一：用 collections.OrderedDict（推荐，简洁）
from collections import OrderedDict

class LRUCache:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = OrderedDict()
    
    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        # 移到末尾（最新位置）
        self.cache.move_to_end(key)
        return self.cache[key]
    
    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            self.cache.move_to_end(key)
        self.cache[key] = value
        if len(self.cache) > self.capacity:
            # 弹出最久未使用的（头部）
            self.cache.popitem(last=False)

# 写法二：手动实现双向链表 + 哈希表（面试加分）
class Node:
    def __init__(self, key=0, val=0):
        self.key = key
        self.val = val
        self.prev = None
        self.next = None

class LRUCacheManual:
    def __init__(self, capacity: int):
        self.capacity = capacity
        self.cache = {}  # key -> Node
        self.head = Node()  # 虚拟头节点
        self.tail = Node()  # 虚拟尾节点
        self.head.next = self.tail
        self.tail.prev = self.head
    
    def _add_node(self, node: Node):
        \"\"\"插入到头部（最新）\"\"\"
        node.prev = self.head
        node.next = self.head.next
        self.head.next.prev = node
        self.head.next = node
    
    def _remove_node(self, node: Node):
        \"\"\"从链表中删除节点\"\"\"
        node.prev.next = node.next
        node.next.prev = node.prev
    
    def _move_to_head(self, node: Node):
        self._remove_node(node)
        self._add_node(node)
    
    def _pop_tail(self) -> Node:
        \"\"\"删除最久未使用的节点（尾部）\"\"\"
        node = self.tail.prev
        self._remove_node(node)
        return node
    
    def get(self, key: int) -> int:
        if key not in self.cache:
            return -1
        node = self.cache[key]
        self._move_to_head(node)
        return node.val
    
    def put(self, key: int, value: int) -> None:
        if key in self.cache:
            node = self.cache[key]
            node.val = value
            self._move_to_head(node)
        else:
            node = Node(key, value)
            self.cache[key] = node
            self._add_node(node)
            if len(self.cache) > self.capacity:
                tail = self._pop_tail()
                del self.cache[tail.key]"""
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "能说出 LRU 的思路，知道用哈希表 + 链表"},
                            {"level": 2, "desc": "能写出 OrderedDict 版本，或手动实现链表版本"},
                            {"level": 3, "desc": "手动实现双向链表版本，边界条件处理正确，能分析时间/空间复杂度"}
                        ],
                        "bonus": "提到 Python 3.7+ dict 本身就是有序的，以及为什么 OrderedDict 仍然有用"
                    }
                }
            ]
        },
        {
            "name": "第二轮：项目深挖面",
            "questions": [
                {
                    "question": "请介绍你简历上写的 {{项目名称}} 项目，你在其中负责什么角色？遇到的最大技术挑战是什么，如何解决的？",
                    "tags": ["resume"],
                    "hints": [
                        "用 STAR 法则回答：Situation → Task → Action → Result",
                        "重点讲技术决策，不要只讲业务背景",
                        "要有量化结果（性能提升百分之多少、QPS 多少等）"
                    ],
                    "answer": {
                        "intro": "面试官通过此题验证简历真实性，并评估候选人的技术深度和表达能力。",
                        "details": [
                            {
                                "title": "STAR 法则回答模板",
                                "content": "S (Situation)：项目背景，为什么做这个系统\nT (Task)：你的具体职责和目标\nA (Action)：你做了什么技术决策，为什么选这个方案\nR (Result)：最终效果，最好有量化指标"
                            },
                            {
                                "title": "面试加分点",
                                "points": [
                                    "能画出系统架构图，讲清楚数据流向",
                                    "提到具体的技术难点和解决方案（不止是'用了XX技术'）",
                                    "有反思：如果重新做，会在哪些方面改进"
                                ]
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "能介绍项目背景和自己的职责"},
                            {"level": 2, "desc": "能用 STAR 法则讲清楚技术难点和解决方案"},
                            {"level": 3, "desc": "有量化结果，能反思架构决策，展现出深度思考"}
                        ],
                        "bonus": "主动提到项目中的失败经历和复盘，展现成长型思维"
                    }
                }
            ]
        },
        {
            "name": "第三轮：系统设计与测试面",
            "questions": [
                {
                    "question": "如何设计一个 LLM Agent 的自动化测试系统？请描述测试维度、评估指标和工程实现。",
                    "tags": ["position", "basic"],
                    "hints": [
                        "LLM 输出是非确定性的，传统 assert 等式测试不适用",
                        "测试维度有哪些？功能正确性、安全性、性能、成本？",
                        "如何做 RAG 系统的评估？Retrieval 和 Generation 怎么分别测？"
                    ],
                    "answer": {
                        "intro": "LLM Agent 测试的核心挑战是非确定性输出，需要语义层面的评估而非精确匹配。",
                        "details": [
                            {
                                "title": "1. 测试维度设计",
                                "content": "- 功能正确性：输出是否符合预期（用 LLM-as-Judge 评估）\n- 工具调用正确性：Function Calling 的参数是否合法、完整\n- 安全性：是否输出有害内容、是否越权调用工具\n- 性能：Token 消耗、延迟（P50/P95/P99）\n- 成本：单次调用的平均成本"
                            },
                            {
                                "title": "2. 评估指标",
                                "content": "- Pass Rate：多次运行后正确输出的比例（建议 ≥5 次取平均）\n- BLEU/ROUGE：与参考回答的 n-gram 重叠度（适用于有明确答案的场景）\n- LLM-as-Judge：用更强的模型（如 GPT-4o）给输出打分（1-10 分）\n- 自定义 Rubric：根据业务场景定义评分维度"
                            },
                            {
                                "title": "3. 工程实现示例",
                                "code": """# LLM Agent 测试框架核心代码
import pytest
import json
from typing import List, Dict

class AgentTestCase:
    \"\"\"Agent 测试用例\"\"\"
    def __init__(self, query: str, expected_tools: List[str], 
                 rubric: Dict[str, str]):
        self.query = query
        self.expected_tools = expected_tools  # 期望调用的工具列表
        self.rubric = rubric              # 评分维度 {"准确性": "...", "完整性": "..."}

class AgentTestFramework:
    def __init__(self, agent_fn):
        self.agent_fn = agent_fn  # Agent 的调用函数
        self.judge_model = None    # LLM-as-Judge 模型
    
    def run_test(self, test_case: AgentTestCase, n_runs: int = 5) -> Dict:
        \"\"\"运行单个测试用例（多次取平均）\"\"\"
        results = []
        for i in range(n_runs):
            response = self.agent_fn(test_case.query)
            score = self._judge(response, test_case.rubric)
            tool_correct = self._check_tools(response, test_case.expected_tools)
            results.append({"score": score, "tool_correct": tool_correct})
        
        return {
            "pass_rate": sum(r["tool_correct"] for r in results) / n_runs,
            "avg_score": sum(r["score"] for r in results) / n_runs,
            "details": results
        }
    
    def _judge(self, response: str, rubric: Dict[str, str]) -> float:
        \"\"\"用 LLM-as-Judge 打分\"\"\"
        prompt = f\"\"\"请对以下回答按照评分标准打分（1-10分）：
        
回答：{response}

评分标准：
{json.dumps(rubric, ensure_ascii=False, indent=2)}

只输出数字分数，不要输出其他内容。\"\"\"
        # 调用 judge_model 获取评分
        score = self.judge_model(prompt)
        return float(score.strip())
    
    def _check_tools(self, response: Dict, expected: List[str]) -> bool:
        \"\"\"检查 Agent 是否调用了期望的工具\"\"\"
        called_tools = [t["name"] for t in response.get("tool_calls", [])]
        return set(called_tools) == set(expected)"""
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "知道 LLM 测试的挑战（非确定性输出）"},
                            {"level": 2, "desc": "能说出多个测试维度和评估指标"},
                            {"level": 3, "desc": "能写出测试框架的核心代码，知道 LLM-as-Judge 的局限性（偏见、成本）"}
                        ],
                        "bonus": "提到 LangSmith / Phoenix / DeepEval 等现有评估框架，并说出它们的优缺点"
                    }
                }
            ]
        },
        {
            "name": "第四轮：HR 综合面",
            "questions": [
                {
                    "question": "请做一个 1-2 分钟的自我介绍。",
                    "tags": ["quality"],
                    "hints": [
                        "不要背简历，要讲故事",
                        "结构化：教育背景 → 核心项目/实习 → 为什么适合这个岗位",
                        "控制在 2 分钟内（约 300 字）"
                    ],
                    "answer": {
                        "intro": "自我介绍是 HR 面的第一题，目的是快速了解候选人的背景和匹配度。好的自我介绍应该像一篇微型求职信。",
                        "details": [
                            {
                                "title": "自我介绍模板（技术岗）",
                                "content": "【开场】你好，我是{{姓名}}，目前是{{学校}}{{专业}}{{年级}}。\n\n【技术背景】我在{{方向}}有{{N}}年经验，熟悉{{核心技术栈}}。\n\n【项目亮点】最有代表性的是{{项目名}}，我用{{技术}}解决了{{问题}}，最终{{量化结果}}。\n\n【为什么这个岗位】我关注到贵公司在{{方向}}的布局，和我研究方向高度匹配，希望能{{贡献点}}。\n\n【收尾】以上就是我的介绍，期待能加入贵团队，谢谢！"
                            },
                            {
                                "title": "面试加分点",
                                "points": [
                                    "有具体数字（QPS 提升 N%、论文被顶会收录）",
                                    "体现出对岗位职责的理解（不是泛泛而谈）",
                                    "语气自信但不自傲，适可而止"
                                ]
                            }
                        ],
                        "score": [
                            {"level": 1, "desc": "能介绍基本背景，但像在读简历"},
                            {"level": 2, "desc": "结构清晰，有项目亮点，时间控制合理"},
                            {"level": 3, "desc": "能结合岗位 JD 定制内容，展现出强烈的入职意愿和匹配度"}
                        ],
                        "bonus": "准备中文版和英文版两个版本，应对不同面试官"
                    }
                }
            ]
        }
    ]
}

# ========== 输出 JSON ==========

def sanitize(obj):
    """确保中文正确序列化"""
    if isinstance(obj, dict):
        return {k: sanitize(v) for k, v in obj.items()}
    elif isinstance(obj, list):
        return [sanitize(item) for item in obj]
    return obj

data = sanitize(interview_data)

os.makedirs(os.path.dirname(os.path.abspath(OUTPUT_PATH)), exist_ok=True)
with open(OUTPUT_PATH, "w", encoding="utf-8") as f:
    json.dump(data, f, ensure_ascii=False, indent=2)

print(f"✅ 已生成: {OUTPUT_PATH}")
print(f"   候选人: {data['candidateName']}")
print(f"   岗位: {data['position']}")
print(f"   总题数: {data['totalQuestions']}")
print(f"\n⚠️  这是 DEMO 示例数据，实际使用请通过 WorkBuddy Skill 动态生成！")
