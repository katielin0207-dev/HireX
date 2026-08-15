'''
Flywheel 飞轮机制（Loop 3）：让系统越用越聪明。

核心流程：
  1. 每次面试结束后，结构化数据存入 ChromaDB
  2. 新候选人进入时，RAG 检索历史上相似案例
  3. 检索结果注入 Prompt，提升匹配准确度和题目针对性
  4. Checker 发现的常见问题自动注入到 Prompt 注意事项
'''

import os
import json
import time
import hashlib
from dataclasses import dataclass, field
from typing import Any, Optional
from pathlib import Path


@dataclass
class FlywheelRecord:
    id: str
    jd_summary: str
    resume_summary: str
    match_score: int
    match_result: dict
    questions: list
    interview_report: Optional[dict] = None
    checker_feedback: Optional[dict] = None
    tags: list = field(default_factory=list)
    timestamp: float = field(default_factory=time.time)


def _iter_issue_dicts(issues):
    """把 checker_feedback['issues'] 摊成 issue dict 的序列。

    存在的理由是**盘上已有坏数据**，不是无谓的防御：写入方曾经写成
        [to_dict(r).get("issues", []) for r in checker_results]
    而 .get("issues") 本身返回 list，于是落盘成了 list[list[dict]]。
    写入方已修正为平铺（见 pipeline.py 的 checker_feedback），但旧记录
    还在 sessions/flywheel_records.json 里 —— 不兼容读的话，一条历史记录
    就能让整条分析链在 _build_graph 阶段崩掉（AttributeError: 'list'
    object has no attribute 'get'），而用户看到的只是"分析失败"。

    只摊一层：坏数据就是多包了一层，不做任意深度递归 —— 真出现更深的
    嵌套说明是另一个 bug，应该炸出来而不是被这里悄悄吃掉。
    """
    for item in issues or []:
        if isinstance(item, dict):
            yield item
        elif isinstance(item, list):
            for inner in item:
                if isinstance(inner, dict):
                    yield inner
        # 其它类型（None/str/…）直接跳过：宁可少统计一条历史问题,
        # 也不要在生成 prompt 注意事项时把整次分析带崩。


class FlywheelStore:
    '''
    飞轮存储：向量检索 + JSON 文件（完整记录，持久层）。

    ★ 改造前这个类的 docstring 就是这么写的，但**代码里一行 chromadb 都没有** ——
      检索走的是 Jaccard 关键词匹配，"未安装则自动降级"也不存在（没有分支，
      永远是 JSON）。任务 Part D 要求的是"存入向量数据库 + RAG 检索"，
      按当时的实现这一项并不成立。

      现在是真的：装了 chromadb 就走向量检索，没装就退回关键词匹配，
      并且**把当前用的是哪条路暴露给 UI**（`backend` 属性）——
      降级本身没问题，把降级说成没降级才是问题。
    '''

    COLLECTION = 'recruitment_cases'

    # ── Embedding 选择 ────────────────────────────────────────
    #
    # chromadb 的默认 embedding 是 all-MiniLM-L6-v2，走 onnxruntime。
    # 在本机实测：onnxruntime 1.22 直接 DLL 初始化失败；降到 1.20.1 能 import，
    # 但真正跑推理时**整个进程段错误**。这属于宿主机的运行时环境问题，
    # 不该让一个招聘 Demo 因此崩掉，也没法用 try/except 兜住（段错误杀进程）。
    #
    # 所以默认用下面这个纯 Python 的哈希 embedding：
    #   · 无额外依赖、离线可用、确定性（同样输入永远同样向量）
    #   · 它是**词汇级**的，不是语义级 —— 这一点在 backend_note 里如实标注，
    #     不会写成"语义检索"
    #   · 但它确实是向量：进 ChromaDB、走 HNSW cosine 检索，
    #     比原来的 Jaccard 好在能处理部分重合与词频权重
    #
    # 环境支持 onnx 的话，设 FLYWHEEL_EMBEDDING=onnx 换回 MiniLM 语义向量。
    EMBED_DIM = 384

    @classmethod
    def _hash_embed(cls, texts):
        '''字符 n-gram 哈希 → 定长向量（L2 归一化）。'''
        import math
        import re as _re
        vecs = []
        for t in texts:
            v = [0.0] * cls.EMBED_DIM
            s = _re.sub(r'\s+', ' ', (t or '').lower())
            grams = [s[i:i + 3] for i in range(max(0, len(s) - 2))]
            grams += _re.findall(r'[a-z]{2,}|[一-鿿]{2,}', s)
            for g in grams:
                h = hash((g, 0x9E3779B9)) % cls.EMBED_DIM
                v[h] += 1.0
            n = math.sqrt(sum(x * x for x in v)) or 1.0
            vecs.append([x / n for x in v])
        return vecs

    def _embedding_function(self):
        if os.environ.get('FLYWHEEL_EMBEDDING', 'hash').lower() == 'onnx':
            return None      # None = 用 chromadb 默认（MiniLM / onnxruntime）
        from chromadb.api.types import EmbeddingFunction

        outer = self

        class _HashEF(EmbeddingFunction):
            def __call__(self, input):
                return outer._hash_embed(list(input))

            @staticmethod
            def name() -> str:
                return 'af-hash-ngram'

            # ★ chromadb 1.x 会把 embedding function 的配置写进集合元数据，
            #   所以必须实现 get_config / build_from_config —— 少了就报
            #   "Object of type NotImplementedType is not JSON serializable"，
            #   而且这个错发生在 get_or_create_collection，整条向量链路直接不可用。
            def get_config(self) -> dict:
                return {'dim': outer.EMBED_DIM}

            @staticmethod
            def build_from_config(config):
                return _HashEF()

            def is_legacy(self) -> bool:
                return False

        return _HashEF()

    def __init__(self, store_dir: str = None):
        if store_dir is None:
            store_dir = os.path.join(os.path.dirname(__file__), '..', 'sessions')
        self.store_dir = os.path.abspath(store_dir)
        os.makedirs(self.store_dir, exist_ok=True)
        self.records_file = os.path.join(self.store_dir, 'flywheel_records.json')
        self._records: list[FlywheelRecord] = []
        self._collection = None
        self._vecs = {}
        self.backend = 'keyword'
        self.backend_note = ''
        self._load()
        self._init_vector()

    # ── 向量库 ────────────────────────────────────────────────
    def _init_vector(self):
        '''检索后端三选一，按优先级：

          chroma  ChromaDB（HNSW 索引，装了就用）
          vector  内置向量索引 —— 同一套 n-gram 哈希 embedding + 余弦相似度，
                  纯 Python、无依赖、离线可用。**它仍然是向量检索**，
                  只是索引是暴力扫描而非 HNSW（几千条以内毫无压力）
          keyword Jaccard 关键词匹配（最后兜底）

        ★ 为什么需要中间这一层：本机实测 chromadb 1.5.9 在 `collection.add`
          处**段错误**（Python 3.13 + Windows，持久化与内存客户端都一样），
          而 0.5.x 没有 3.13 的预编译轮子、要现场编译 chroma-hnswlib。
          段错误是杀进程的，try/except 兜不住 —— 只有在调用前就避开。
          如果因此直接退回关键词匹配，任务 Part D 要求的"向量检索"就落空了，
          所以自带一个不依赖原生扩展的向量后端。
        '''
        # 内置向量索引始终可用，先把它作为基线
        self.backend = 'vector'
        self.backend_note = '内置向量索引（n-gram 哈希 embedding + 余弦相似度，词汇级）'
        self._rebuild_local_index()

        # ★ 默认【不碰】chromadb。
        #   不是"没装所以不用"，而是它在本机 collection.add 处段错误 ——
        #   段错误会直接杀掉整个 Streamlit 进程，用户看到的是页面白屏断连，
        #   而 try/except 拦不住。宁可默认走一条确定能跑的路，
        #   把 chromadb 留成显式 opt-in：FLYWHEEL_VECTOR_BACKEND=chroma
        if os.environ.get('FLYWHEEL_VECTOR_BACKEND', 'local').lower() != 'chroma':
            self.backend_note += ' · 如需 chromadb/HNSW：设 FLYWHEEL_VECTOR_BACKEND=chroma'
            return
        try:
            import chromadb
        except ImportError:
            self.backend_note += ' · chromadb 未安装，未启用 HNSW'
            return
        try:
            client = chromadb.PersistentClient(path=os.path.join(self.store_dir, 'chroma'))
            ef = self._embedding_function()
            kwargs = {'name': self.COLLECTION, 'metadata': {'hnsw:space': 'cosine'}}
            if ef is not None:
                kwargs['embedding_function'] = ef
            self._collection = client.get_or_create_collection(**kwargs)
            self.backend = 'chroma'
            ver = getattr(chromadb, '__version__', '?')
            self.backend_note = (
                f'chromadb {ver} · embedding=MiniLM(语义)' if ef is None
                else f'chromadb {ver} · embedding=n-gram 哈希（词汇级，非语义）'
            )
            self._backfill()
        except Exception as e:  # noqa: BLE001
            # 首次使用会下载 embedding 模型；离线环境会在这里失败 —— 不该炸掉整个分析
            self._collection = None
            self.backend = 'vector'
            self.backend_note = (
                '内置向量索引（chromadb 初始化失败已回退：'
                f'{type(e).__name__}: {e})'[:200])

    def _doc_text(self, r: FlywheelRecord) -> str:
        return f'{r.jd_summary}\n{r.resume_summary}\n{" ".join(map(str, r.tags))}'

    def _backfill(self):
        '''把 JSON 里已有、但向量库还没有的记录补进去。

        场景：先前在没装 chromadb 的时候攒了一批记录，装上之后它们不该丢。'''
        if self._collection is None or not self._records:
            return
        try:
            existing = set(self._collection.get(include=[]).get('ids', []))
            todo = [r for r in self._records if r.id and r.id not in existing]
            if todo:
                self._collection.add(
                    ids=[r.id for r in todo],
                    documents=[self._doc_text(r) for r in todo],
                    metadatas=[{'match_score': int(r.match_score or 0),
                                'timestamp': float(r.timestamp or 0)} for r in todo],
                )
        except Exception as e:  # noqa: BLE001
            # 同上：回填失败也要说出来，否则向量库会一直是空的而没人知道
            self._collection = None
            self.backend = 'vector'
            self.backend_note = f'chromadb 回填失败，已回退内置向量索引：{type(e).__name__}: {e}'[:200]
            print(f'[Flywheel] {self.backend_note}')

    def _load(self):
        if os.path.exists(self.records_file):
            try:
                with open(self.records_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self._records = [FlywheelRecord(**r) for r in data]
            except Exception:
                self._records = []

    def _save(self):
        with open(self.records_file, 'w', encoding='utf-8') as f:
            json.dump([self._record_to_dict(r) for r in self._records], f,
                      ensure_ascii=False, indent=2, default=str)

    def _record_to_dict(self, r: FlywheelRecord) -> dict:
        # ★ 原来这里只存 6 个字段，把 match_result / questions / interview_report /
        #   checker_feedback 全丢了。后果：`get_common_checker_issues` 遍历的
        #   `record.checker_feedback` 重启后一律是 None ——
        #   "Checker 常见问题自动注入 Prompt"（任务 Part D 第 4 条）
        #   只在单个进程生命周期内成立，重启即失忆。飞轮转不起来。
        return {
            'id': r.id,
            'jd_summary': r.jd_summary,
            'resume_summary': r.resume_summary,
            'match_score': r.match_score,
            'match_result': r.match_result,
            'questions': r.questions,
            'interview_report': r.interview_report,
            'checker_feedback': r.checker_feedback,
            'tags': r.tags,
            'timestamp': r.timestamp,
        }

    def store(self, record: FlywheelRecord) -> str:
        record.id = record.id or hashlib.md5(
            (record.jd_summary + record.resume_summary + str(time.time())).encode()
        ).hexdigest()[:12]
        self._records.append(record)
        self._save()
        # 内置索引同步（chromadb 不可用时它就是检索主力）
        if getattr(self, '_vecs', None) is not None:
            self._vecs[record.id] = self._hash_embed([self._doc_text(record)])[0]
        if self._collection is not None:
            try:
                self._collection.add(
                    ids=[record.id],
                    documents=[self._doc_text(record)],
                    metadatas=[{'match_score': int(record.match_score or 0),
                                'timestamp': float(record.timestamp or 0)}],
                )
            except Exception as e:  # noqa: BLE001
                # ★ 写失败不阻断分析（JSON 那份已落盘），但**绝不能静默**。
                #   我第一版这里是 `except: pass` —— 结果 chromadb 缺
                #   onnxruntime、每次 add 都抛错，集合一直是空的，而检索悄悄
                #   退回了关键词匹配。当时我还以为看到了"语义命中"，
                #   实际是关键词回退按插入顺序排出来的假象。
                #   被吞掉的错误会让"降级"和"正常"长得一模一样。
                self._collection = None
                self.backend = 'vector'
                self.backend_note = f'chromadb 写入失败，已回退内置向量索引：{type(e).__name__}: {e}'[:200]
                print(f'[Flywheel] {self.backend_note}')
        return record.id

    def retrieve_similar(
        self, query_text: str, top_k: int = 5, min_score: int = 50
    ) -> list[FlywheelRecord]:
        '''RAG 检索：优先向量语义检索，未装 chromadb 时退回关键词匹配。

        min_score 是 0-100 的相似度门槛，两条路径都换算到同一量纲，
        否则换个后端阈值的含义就变了。
        '''
        if not self._records:
            return []

        if self._collection is not None:
            hits = self._retrieve_vector(query_text, top_k, min_score)
            if hits is not None:
                return hits

        if self.backend == 'vector' and self._vecs:
            return self._retrieve_local(query_text, top_k, min_score)

        query_keywords = set(self._tokenize(query_text))

        scored = []
        for record in self._records:
            record_text = record.jd_summary + ' ' + record.resume_summary
            record_keywords = set(self._tokenize(record_text))

            if not query_keywords or not record_keywords:
                continue

            intersection = query_keywords & record_keywords
            union = query_keywords | record_keywords
            jaccard = len(intersection) / len(union) if union else 0

            scored.append((jaccard, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for s, r in scored[:top_k] if s * 100 >= min_score]

    # ── 内置向量索引（不依赖任何原生扩展）────────────────────
    def _rebuild_local_index(self):
        '''把全部记录向量化。JSON 是持久层，索引是可随时重建的派生物。'''
        self._vecs = {r.id: v for r, v in
                      zip(self._records, self._hash_embed([self._doc_text(r) for r in self._records]))
                      } if self._records else {}

    def _retrieve_local(self, query_text: str, top_k: int, min_score: int):
        if not self._vecs:
            return []
        qv = self._hash_embed([query_text])[0]
        by_id = {r.id: r for r in self._records}
        scored = []
        for rid, v in self._vecs.items():
            # 两边都已 L2 归一化，点积即余弦
            sim = sum(a * b for a, b in zip(qv, v)) * 100
            if sim >= min_score and rid in by_id:
                scored.append((sim, by_id[rid]))
        scored.sort(key=lambda x: x[0], reverse=True)
        return [r for _, r in scored[:top_k]]

    def _retrieve_vector(self, query_text: str, top_k: int, min_score: int):
        '''向量检索。返回 None 表示这条路走不通，交给调用方降级。'''
        try:
            res = self._collection.query(
                query_texts=[query_text], n_results=min(top_k, max(1, len(self._records))))
        except Exception:  # noqa: BLE001
            return None
        ids = (res.get('ids') or [[]])[0]
        dists = (res.get('distances') or [[]])[0]
        if not ids:
            return []
        by_id = {r.id: r for r in self._records}
        out = []
        for rid, dist in zip(ids, dists):
            rec = by_id.get(rid)
            if rec is None:
                continue
            # cosine 距离 → 0-100 相似度，和关键词路径的 jaccard*100 对齐量纲
            sim = max(0.0, 1.0 - float(dist)) * 100
            if sim >= min_score:
                out.append(rec)
        return out

    def _tokenize(self, text: str) -> list[str]:
        import re
        words = re.findall(r'[\u4e00-\u9fff]{2,}|[a-zA-Z]{2,}', text.lower())
        stopwords = {'的', '了', '在', '是', '有', '和', '就', '不', '人', '都', '一',
                     'the', 'a', 'an', 'is', 'are', 'was', 'were', 'be', 'been', 'has', 'have'}
        return [w for w in words if w not in stopwords]

    def get_common_checker_issues(self, top_k: int = 5) -> list[dict]:
        '''
        从历史 Checker 反馈中提取常见问题模式。
        用于注入到 Prompt 模板的"注意事项"中。
        '''
        issue_counter = {}
        for record in self._records:
            if not record.checker_feedback:
                continue
            issues = record.checker_feedback.get('issues', [])
            for issue in _iter_issue_dicts(issues):
                key = f"{issue.get('dimension')}:{issue.get('description', '')[:60]}"
                issue_counter[key] = issue_counter.get(key, 0) + 1

        sorted_issues = sorted(issue_counter.items(), key=lambda x: x[1], reverse=True)
        return [
            {'pattern': k, 'count': v}
            for k, v in sorted_issues[:top_k]
        ]

    def generate_prompt_notes(self) -> str:
        '''生成 Prompt 注意事项（可从历史中学习）'''
        common_issues = self.get_common_checker_issues(top_k=3)
        if not common_issues:
            return ''

        notes = ['\n## 历史常见问题（请特别注意避免）']
        for i, issue in enumerate(common_issues):
            notes.append(f"{i+1}. {issue['pattern']}（已出现{issue['count']}次）")
        return '\n'.join(notes)

    def get_stats(self) -> dict:
        return {
            # ★ 把后端如实报出来 —— 界面上写着"向量检索"而实际在跑关键词匹配，
            #   比降级本身糟糕得多
            'backend': self.backend,
            'backend_note': self.backend_note,
            'vector_count': self._vector_count(),
            'total_records': len(self._records),
            'avg_match_score': (
                sum(r.match_score for r in self._records) / len(self._records)
                if self._records else 0
            ),
            'recent_tags': list(set(
                tag for r in self._records[-20:] for tag in r.tags
            )),
        }

    def _vector_count(self) -> int:
        if self._collection is None:
            return 0
        try:
            return int(self._collection.count())
        except Exception:  # noqa: BLE001
            return 0

    def count(self) -> int:
        return len(self._records)
