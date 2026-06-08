import numpy as np
from sourcing.rerank.embed import rerank_rows, DEFAULT_THRESHOLD


def _fake_embeddings():
    vecs = {
        "qA": np.array([1.0, 0.0, 0.0]),
        "cA_same": np.array([1.0, 0.0, 0.0]),
        "qB": np.array([1.0, 0.0, 0.0]),
        "cB_diff": np.array([0.0, 1.0, 0.0]),
    }
    def get_embedding(url, source):
        return vecs.get(url)
    return get_embedding


def test_rerank_rows_adds_similarity_and_confidence():
    rows = [
        {"source": "ixspy", "external_image_url": "qA", "erp_image_url": "cA_same"},
        {"source": "ixspy", "external_image_url": "qB", "erp_image_url": "cB_diff"},
        {"source": "ixspy", "external_image_url": "qB", "erp_image_url": "missing"},
    ]
    out = rerank_rows(rows, _fake_embeddings(), threshold=DEFAULT_THRESHOLD)
    assert out[0]["embedding_similarity"] == 1.0
    assert out[0]["embedding_confident"] == "1"
    assert out[1]["embedding_similarity"] == 0.0
    assert out[1]["embedding_confident"] == "0"
    assert out[2]["embedding_similarity"] == ""
    assert out[2]["embedding_confident"] == "0"


def test_rerank_rows_caches_embeddings_per_url():
    calls = []
    def counting(url, source):
        calls.append(url)
        return np.array([1.0, 0.0])
    rows = [
        {"source": "s", "external_image_url": "q", "erp_image_url": "c"},
        {"source": "s", "external_image_url": "q", "erp_image_url": "c"},
    ]
    rerank_rows(rows, counting)
    assert sorted(set(calls)) == ["c", "q"]
    assert len(calls) == 2
