import os
import sys

from sourcing.erp_image_search import output_csv_path, _read_csv_dicts, RESULT_FIELDS, _fields_with_extras
from sourcing.collect.api_common import write_csv

DEFAULT_THRESHOLD = 0.85
EXTRA_FIELDS = ["embedding_similarity", "embedding_confident"]

# 我们的源名 -> 518 图片下载器认的"市场"名（决定取图用的头/防盗链处理）。
# 例：本系统 source=ixspy，实际市场是 aliexpress，下载器只认 aliexpress。
_EMBED_SOURCE = {"ixspy": "aliexpress"}


def embed_source(row_source) -> str:
    s = (row_source or "").strip()
    return _EMBED_SOURCE.get(s, s or "market")


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
        vq = emb(row.get("external_image_url"), embed_source(row.get("source")))
        vc = emb(row.get("erp_image_url"), "erp")
        sim = _cosine(vq, vc)
        new = dict(row)
        new["embedding_similarity"] = "" if sim is None else round(sim, 4)
        new["embedding_confident"] = "1" if (sim is not None and sim >= threshold) else "0"
        out.append(new)
    return out


def sqlite_cache_path(repo_dir: str | None = None) -> str:
    """嵌入 SQLite 缓存路径(与 518 pkl 同目录)。"""
    import image_embedding_matcher as iem
    return os.path.join(os.path.dirname(iem.EMBEDDING_CACHE_FILE), "image_embeddings.sqlite")


def _import_iem(repo_dir: str | None = None):
    from sourcing import config
    repo_dir = repo_dir or config.embedding_repo_dir()
    if repo_dir not in sys.path:
        sys.path.insert(0, repo_dir)
    try:
        import pillow_avif  # noqa: F401  注册 AVIF 解码：AliExpress 图多为 AVIF，PIL 默认读不了
    except ImportError:
        pass
    return repo_dir


def build_embedder(repo_dir: str | None = None, product_type: str | None = None,
                   use_sqlite_cache: bool | None = None):
    """懒加载 518 的 DINOv2 嵌入器。返回 (get_embedding, matcher)。需 torch + 模型缓存。
    repo_dir = 518 嵌入代码所在目录（与数据 base_dir 解耦），默认 config.embedding_repo_dir()。

    use_sqlite_cache: True/None 且 SQLite 已迁移时，用按 key 懒查的 SQLite 缓存替换 matcher.cache，
    避免把 15万条 pkl 一次性载入内存(OOM)。未迁移则回退原 pkl 行为(零变化)。
    """
    _import_iem(repo_dir)
    import image_embedding_matcher as iem
    from image_embedding_matcher import ImageEmbeddingMatcher

    sqlite_path = sqlite_cache_path(repo_dir)
    want_sqlite = use_sqlite_cache if use_sqlite_cache is not None else os.path.exists(sqlite_path)
    if not want_sqlite:
        matcher = ImageEmbeddingMatcher(product_type=product_type)
        return matcher.get_embedding, matcher

    # 关键：构造前临时把 pkl 路径指向不存在的文件，阻止 _load_cache 把整个 pkl 读进内存。
    from sourcing.rerank.embed_cache import SqliteEmbeddingCache
    orig_pkl = iem.EMBEDDING_CACHE_FILE
    iem.EMBEDDING_CACHE_FILE = sqlite_path + ".__skip__"
    try:
        matcher = ImageEmbeddingMatcher(product_type=product_type)
    finally:
        iem.EMBEDDING_CACHE_FILE = orig_pkl

    cache = SqliteEmbeddingCache(sqlite_path)
    matcher.cache = cache
    _orig_downloader_save = matcher.downloader.save
    def _save():  # 只刷 SQLite + 图片路径缓存，不再 pickle 整个 cache
        cache.flush()
        _orig_downloader_save()
    matcher.save = _save
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
        embedder, matcher = build_embedder(product_type=product_type)
    out = rerank_rows(rows, embedder, threshold=threshold)
    fields = _fields_with_extras(list(RESULT_FIELDS) + EXTRA_FIELDS, out)
    write_csv(str(path), out, fields)
    if matcher is not None and hasattr(matcher, "save"):
        matcher.save()
    confident = sum(1 for r in out if r.get("embedding_confident") == "1")
    return {"reranked": len(out), "confident": confident, "output": str(path)}
