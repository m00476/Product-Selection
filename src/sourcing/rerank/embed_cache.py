"""SQLite 按 key 懒查的嵌入缓存。

替代 518 ImageEmbeddingMatcher 里"整个 pkl 一次性 load 进内存(15万条~1-2GB)"的做法：
只在用到某个 key 时查一条向量出来，内存恒定。对 518 零侵入——本类实现了
`get / __getitem__ / __setitem__ / __contains__`，可直接替换 matcher.cache。
"""
import os
import pickle
import sqlite3

import numpy as np

VEC_DTYPE = "float32"
_COMMIT_EVERY = 50


class SqliteEmbeddingCache:
    def __init__(self, path: str):
        self.path = path
        parent = os.path.dirname(path)
        if parent:
            os.makedirs(parent, exist_ok=True)
        self.conn = sqlite3.connect(path)
        self.conn.execute(
            "CREATE TABLE IF NOT EXISTS embeddings (key TEXT PRIMARY KEY, vec BLOB NOT NULL)"
        )
        self.conn.commit()
        self._pending = 0

    def get(self, key, default=None):
        row = self.conn.execute(
            "SELECT vec FROM embeddings WHERE key=?", (key,)
        ).fetchone()
        if row is None:
            return default
        return np.frombuffer(row[0], dtype=VEC_DTYPE)

    def __getitem__(self, key):
        val = self.get(key)
        if val is None:
            raise KeyError(key)
        return val

    def __contains__(self, key):
        return self.conn.execute(
            "SELECT 1 FROM embeddings WHERE key=? LIMIT 1", (key,)
        ).fetchone() is not None

    def __setitem__(self, key, value):
        blob = np.ascontiguousarray(value, dtype=VEC_DTYPE).tobytes()
        self.conn.execute(
            "INSERT OR REPLACE INTO embeddings (key, vec) VALUES (?, ?)", (key, blob)
        )
        self._pending += 1
        if self._pending >= _COMMIT_EVERY:
            self.flush()

    def __len__(self):
        return self.conn.execute("SELECT count(*) FROM embeddings").fetchone()[0]

    def flush(self):
        if self._pending:
            self.conn.commit()
            self._pending = 0

    def close(self):
        self.flush()
        self.conn.close()


def migrate_pickle_to_sqlite(pkl_path: str, sqlite_path: str) -> int:
    """一次性把旧的 image_embeddings.pkl 灌进 SQLite。返回写入条数。

    仅此一步会把 pkl 完整读进内存一次——请在内存充裕时跑(CLI: migrate-embedding-cache)。
    之后的精筛运行都走 SQLite 懒查，内存恒定。
    """
    with open(pkl_path, "rb") as f:
        data = pickle.load(f)
    cache = SqliteEmbeddingCache(sqlite_path)
    count = 0
    try:
        for key, vec in data.items():
            if vec is None:
                continue
            cache[key] = vec
            count += 1
        cache.flush()
    finally:
        cache.close()
    return count
