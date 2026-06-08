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


import csv
from pathlib import Path
from sourcing.rerank.embed import rerank_image_search
from sourcing.erp_image_search import output_csv_path, RESULT_FIELDS


def _write_results(base, source, product_type, rows):
    p = output_csv_path(base, source, product_type)
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})
    return p


def test_rerank_image_search_writes_similarity(tmp_path):
    base = str(tmp_path)
    _write_results(base, "ixspy", "bags", [
        {"source": "ixspy", "external_sku": "E1", "external_image_url": "q", "erp_image_url": "c"},
    ])
    fake = lambda url, source: np.array([1.0, 0.0]) if url in ("q", "c") else None
    summary = rerank_image_search(source="ixspy", product_type="bags", base_dir=base, embedder=fake)
    assert summary["reranked"] == 1 and summary["confident"] == 1
    out_rows = list(csv.DictReader(open(output_csv_path(base, "ixspy", "bags"), encoding="utf-8-sig")))
    assert out_rows[0]["embedding_similarity"] == "1.0"
    assert out_rows[0]["embedding_confident"] == "1"
