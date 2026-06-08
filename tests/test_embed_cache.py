import pickle

import numpy as np

from sourcing.rerank.embed_cache import (
    SqliteEmbeddingCache,
    migrate_pickle_to_sqlite,
)


def test_set_get_roundtrip_returns_equal_vector(tmp_path):
    cache = SqliteEmbeddingCache(str(tmp_path / "e.sqlite"))
    v = np.arange(8, dtype="float32") / 7.0
    cache["k1"] = v
    got = cache.get("k1")
    assert got is not None
    assert got.dtype == np.float32
    np.testing.assert_allclose(got, v)
    cache.close()


def test_get_missing_returns_none_and_contains_false(tmp_path):
    cache = SqliteEmbeddingCache(str(tmp_path / "e.sqlite"))
    assert cache.get("nope") is None
    assert ("nope" in cache) is False
    cache["k"] = np.ones(4, dtype="float32")
    assert "k" in cache
    cache.close()


def test_persists_across_reopen(tmp_path):
    path = str(tmp_path / "e.sqlite")
    c1 = SqliteEmbeddingCache(path)
    c1["a"] = np.array([1, 2, 3], dtype="float32")
    c1.close()  # flush + close
    c2 = SqliteEmbeddingCache(path)
    np.testing.assert_allclose(c2.get("a"), [1, 2, 3])
    assert len(c2) == 1
    c2.close()


def test_dictlike_matches_matcher_usage(tmp_path):
    """ImageEmbeddingMatcher.get_embedding 用法: cache.get(key) / cache[key]=v / key in cache。"""
    cache = SqliteEmbeddingCache(str(tmp_path / "e.sqlite"))
    key = "abc123"
    assert cache.get(key) is None          # 未命中 -> 走下载+计算
    emb = np.linspace(0, 1, 1024, dtype="float32")
    cache[key] = emb                        # 算完写回
    cached = cache.get(key)                 # 二次命中
    assert cached is not None               # matcher 用 `is not None` 判定
    np.testing.assert_allclose(cached, emb, atol=1e-6)
    cache.close()


def test_migrate_pickle_to_sqlite_copies_all_vectors(tmp_path):
    pkl = tmp_path / "old.pkl"
    data = {
        "h1": np.ones(4, dtype="float32"),
        "h2": np.full(4, 2.0, dtype="float32"),
        "bad": None,  # 跳过 None
    }
    with open(pkl, "wb") as f:
        pickle.dump(data, f)
    sqlite_path = str(tmp_path / "new.sqlite")
    n = migrate_pickle_to_sqlite(str(pkl), sqlite_path)
    assert n == 2
    cache = SqliteEmbeddingCache(sqlite_path)
    np.testing.assert_allclose(cache.get("h1"), [1, 1, 1, 1])
    np.testing.assert_allclose(cache.get("h2"), [2, 2, 2, 2])
    assert cache.get("bad") is None
    cache.close()
