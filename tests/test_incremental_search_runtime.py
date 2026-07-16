from sourcing.incremental_search_runtime import run_searches
from sourcing.rerank.checkpoint import should_checkpoint


def test_run_searches_keeps_input_order_with_multiple_workers():
    rows = [{"external_sku": "A"}, {"external_sku": "B"}, {"external_sku": "C"}]

    results = list(
        run_searches(
            rows,
            lambda row: f"result-{row['external_sku']}",
            workers=2,
            delay_seconds=0,
        )
    )

    assert results == [
        (1, rows[0], "result-A"),
        (2, rows[1], "result-B"),
        (3, rows[2], "result-C"),
    ]


def test_run_searches_rejects_non_positive_worker_count():
    try:
        list(run_searches([], lambda row: row, workers=0))
    except ValueError as error:
        assert "workers" in str(error)
    else:
        raise AssertionError("workers=0 should be rejected")


def test_checkpoint_is_due_at_interval_and_final_chunk():
    assert should_checkpoint(1, 5, checkpoint_every=2) is False
    assert should_checkpoint(2, 5, checkpoint_every=2) is True
    assert should_checkpoint(4, 5, checkpoint_every=2) is True
    assert should_checkpoint(5, 5, checkpoint_every=2) is True
