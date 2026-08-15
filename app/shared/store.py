"""候选人 / JD 的 JSON 文件存储。

存储位置（见 docs/CONTRACT.md 第 6 节）：
- sessions/candidates/{id}.json
- sessions/jd.json

所有函数都是同步、原子写（先写临时文件再 rename），并发安全够用。
"""
import json
import os
import tempfile
import threading
from datetime import datetime
from typing import Any, Optional

_BASE = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
SESSIONS_DIR = os.path.join(_BASE, "sessions")
CANDIDATES_DIR = os.path.join(SESSIONS_DIR, "candidates")
JD_PATH = os.path.join(SESSIONS_DIR, "jd.json")

_lock = threading.Lock()

for d in (SESSIONS_DIR, CANDIDATES_DIR):
    os.makedirs(d, exist_ok=True)


def _atomic_write(path: str, data: Any) -> None:
    """原子写入：先写临时文件再 rename，避免并发读到写了一半的文件。"""
    fd, tmp = tempfile.mkstemp(dir=os.path.dirname(path), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        os.replace(tmp, path)
    except Exception:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise


def _candidate_path(candidate_id: str) -> str:
    # 防止路径穿越
    safe = "".join(c for c in candidate_id if c.isalnum() or c in "_-")
    return os.path.join(CANDIDATES_DIR, f"{safe}.json")


def save_candidate(candidate: dict) -> str:
    """新增或整体覆盖候选人。返回 candidate_id。"""
    cid = candidate.get("id")
    if not cid:
        raise ValueError("candidate 必须包含 id 字段")
    candidate["updated_at"] = datetime.now().isoformat(timespec="seconds")
    with _lock:
        _atomic_write(_candidate_path(cid), candidate)
    return cid


def load_candidate(candidate_id: str) -> Optional[dict]:
    """读取候选人，不存在返回 None。"""
    path = _candidate_path(candidate_id)
    if not os.path.exists(path):
        return None
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def update_candidate(candidate_id: str, field: str, value: Any) -> dict:
    """只更新候选人顶层的一个字段（各模块更新自己负责的字段用这个）。

    例：update_candidate("cand_001", "risk_report", {...})
    """
    with _lock:
        cand = load_candidate(candidate_id)
        if cand is None:
            raise FileNotFoundError(f"候选人不存在: {candidate_id}")
        cand[field] = value
        cand["updated_at"] = datetime.now().isoformat(timespec="seconds")
        _atomic_write(_candidate_path(candidate_id), cand)
        return cand


def list_candidates(status: Optional[str] = None) -> list[dict]:
    """列出全部候选人，可按 status 过滤。按 updated_at 倒序。"""
    out = []
    for fname in os.listdir(CANDIDATES_DIR):
        if not fname.endswith(".json"):
            continue
        try:
            with open(os.path.join(CANDIDATES_DIR, fname), encoding="utf-8") as f:
                cand = json.load(f)
            if status is None or cand.get("status") == status:
                out.append(cand)
        except (json.JSONDecodeError, OSError):
            continue
    out.sort(key=lambda c: c.get("updated_at", ""), reverse=True)
    return out


def save_jd(jd: dict) -> None:
    with _lock:
        _atomic_write(JD_PATH, jd)


def load_jd() -> Optional[dict]:
    if not os.path.exists(JD_PATH):
        return None
    with open(JD_PATH, encoding="utf-8") as f:
        return json.load(f)
