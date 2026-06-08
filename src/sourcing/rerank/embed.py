import os
import sys

from sourcing.erp_image_search import output_csv_path, _read_csv_dicts, RESULT_FIELDS
from sourcing.collect.api_common import write_csv

DEFAULT_THRESHOLD = 0.85
EXTRA_FIELDS = ["embedding_similarity", "embedding_confident"]


def _cosine(a, b):
    if a is None or b is None:
        return None
    return float(a @ b)


def rerank_rows(rows, get_embedding, *, threshold: float = DEFAULT_THRESHOLD):
    """给每行加 embedding_similarity(竞品图×候选图余弦) 与 embedding_confident(>=阈值)。
    get_embedding(url, source)->向量或None；按 url 缓存。纯逻辑、可注入假实现。"""
    cache = {}

    def emb(url, source):
        if not url:
            return None
        key = (url, source)
        if key not in cache:
            cache[key] = get_embedding(url, source)
        return cache[key]

    out = []
    for row in rows:
        vq = emb(row.get("external_image_url"), row.get("source") or "market")
        vc = emb(row.get("erp_image_url"), "erp")
        sim = _cosine(vq, vc)
        new = dict(row)
        new["embedding_similarity"] = "" if sim is None else round(sim, 4)
        new["embedding_confident"] = "1" if (sim is not None and sim >= threshold) else "0"
        out.append(new)
    return out


def build_embedder(base_dir: str, product_type: str):
    """懒加载 518 的 DINOv2 嵌入器。返回 (get_embedding, matcher)。需 torch + 模型缓存。"""
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    from image_embedding_matcher import ImageEmbeddingMatcher
    matcher = ImageEmbeddingMatcher(product_type=product_type)
    return matcher.get_embedding, matcher


def rerank_image_search(*, source: str, product_type: str, base_dir: str,
                        limit=None, threshold: float = DEFAULT_THRESHOLD,
                        embedder=None) -> dict:
    path = output_csv_path(base_dir, source, product_type)
    rows = _read_csv_dicts(path)
    if limit is not None:
        rows = rows[:limit]
    matcher = None
    if embedder is None:
        embedder, matcher = build_embedder(base_dir, product_type)
    out = rerank_rows(rows, embedder, threshold=threshold)
    fields = list(RESULT_FIELDS) + EXTRA_FIELDS
    write_csv(str(path), out, fields)
    if matcher is not None and hasattr(matcher, "save"):
        matcher.save()
    confident = sum(1 for r in out if r.get("embedding_confident") == "1")
    return {"reranked": len(out), "confident": confident, "output": str(path)}
