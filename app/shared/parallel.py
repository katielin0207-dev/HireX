"""批量并发 LLM 调用工具。

批量筛选 10 份简历时，串行调 LLM 要 10 倍时间。
用 map_llm 并发（默认 3 并发，别把 API 打爆）：

    from app.shared.parallel import map_llm

    results = map_llm(
        items=resumes,
        fn=lambda r: call_llm(f"分析简历: {r}", expect_json=True),
        max_workers=3,
    )
返回与 items 顺序一致的结果列表；单个失败返回 {"error": str(e)}，不中断整批。
"""
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable


def map_llm(items: list, fn: Callable[[Any], Any], max_workers: int = 3) -> list:
    """对 items 并发执行 fn，保持顺序返回结果。单项失败返回 {"error": ...}。"""
    results = [None] * len(items)
    with ThreadPoolExecutor(max_workers=max_workers) as pool:
        futures = {pool.submit(fn, item): i for i, item in enumerate(items)}
        for future in as_completed(futures):
            i = futures[future]
            try:
                results[i] = future.result()
            except Exception as e:  # noqa: BLE001 - 批量场景单点失败不应中断整批
                results[i] = {"error": str(e)}
    return results
