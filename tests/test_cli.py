import sys

from sourcing import cli


class FakeConn:
    def close(self):
        pass


def test_cli_import_supports_ixspy(monkeypatch, tmp_path):
    csv_path = tmp_path / "ixspy.csv"
    csv_path.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "import", "--source", "ixspy",
        "--path", str(csv_path), "--product-type", "audio",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(
        cli,
        "import_ixspy_csv",
        lambda conn, path, *, product_type, source_file: calls.append(
            (path, product_type, source_file)
        ) or {"products": 1},
    )

    cli.main()

    assert calls == [(str(csv_path), "audio", str(csv_path))]


def test_cli_import_supports_erp(monkeypatch, tmp_path):
    csv_path = tmp_path / "erp.csv"
    csv_path.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "import", "--source", "erp",
        "--path", str(csv_path), "--product-type", "socks",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(
        cli,
        "import_erp_csv",
        lambda conn, path, *, product_type, source_file: calls.append(
            (path, product_type, source_file)
        ) or {"products": 1, "skus": 1},
    )

    cli.main()

    assert calls == [(str(csv_path), "socks", str(csv_path))]


def test_cli_quality_reports_source_file(monkeypatch, tmp_path, capsys):
    csv_path = tmp_path / "ixspy.csv"
    csv_path.write_text("", encoding="utf-8")
    calls = []
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "quality", "--source", "ixspy",
        "--path", str(csv_path), "--product-type", "audio",
    ])
    monkeypatch.setattr(
        cli,
        "inspect_csv_quality",
        lambda path, *, source, product_type: calls.append(
            (path, source, product_type)
        ) or {"source": source, "total_rows": 2, "missing_price": 2},
    )

    cli.main()

    assert calls == [(str(csv_path), "ixspy", "audio")]
    assert '"missing_price": 2' in capsys.readouterr().out


def test_cli_collect_single_target(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "collect", "--source", "seerfar", "--product-type", "laptop",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "collect_all",
        lambda conn, targets, *, base_dir: calls.update(targets=targets, base_dir=base_dir) or [],
    )
    cli.main()
    assert calls["targets"] == [("seerfar", "laptop")]
    assert calls["base_dir"] == "/base518"


def test_cli_collect_all_uses_config_targets(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", ["sourcing.cli", "collect", "--all"])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(cli.config, "collect_targets", lambda: [("erp", "socks")])
    monkeypatch.setattr(
        cli, "collect_all",
        lambda conn, targets, *, base_dir: calls.update(targets=targets) or [],
    )
    cli.main()
    assert calls["targets"] == [("erp", "socks")]


def test_cli_bridge_matches(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", ["sourcing.cli", "bridge-matches"])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "app_db_path", lambda: "/x/app.db")
    monkeypatch.setattr(
        cli, "bridge_matches",
        lambda conn, path: calls.update(path=path) or {"bridged": 3, "read": 5},
    )
    cli.main()
    assert calls["path"] == "/x/app.db"


def test_cli_import_external(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", ["sourcing.cli", "import-external"])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "app_db_path", lambda: "/x/app.db")
    monkeypatch.setattr(
        cli, "import_external_products",
        lambda conn, path: calls.update(path=path) or {"imported": 4, "skipped_no_id": 1},
    )
    cli.main()
    assert calls["path"] == "/x/app.db"


def test_cli_erp_image_search_does_not_open_database(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-search",
        "--source", "seerfar",
        "--product-type", "mask",
        "--limit", "5",
        "--delay", "0",
    ])
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: str(tmp_path))
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: (_ for _ in ()).throw(AssertionError("db not needed")))
    monkeypatch.setattr(
        cli.erp_image_search,
        "run_image_search",
        lambda **kwargs: calls.update(kwargs) or {"searched": 5, "written": 5},
    )

    cli.main()

    assert calls["source"] == "seerfar"
    assert calls["product_type"] == "mask"
    assert calls["base_dir"] == str(tmp_path)
    assert calls["limit"] == 5
    assert calls["delay_seconds"] == 0


def test_cli_erp_image_decision_report_does_not_open_database(monkeypatch, tmp_path):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-decision-report",
        "--source", "ixspy",
        "--product-type", "bag_accessories",
        "--base-dir", str(tmp_path),
    ])
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: (_ for _ in ()).throw(AssertionError("db not needed")))
    monkeypatch.setattr(
        cli.erp_image_search,
        "generate_boss_decision_report",
        lambda **kwargs: calls.update(kwargs) or {"products": 3, "csv": "x.csv", "markdown": "x.md"},
    )

    cli.main()

    assert calls["source"] == "ixspy"
    assert calls["product_type"] == "bag_accessories"
    assert calls["base_dir"] == str(tmp_path)


def test_cli_erp_image_decision_report_defaults_to_current_project(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-decision-report",
        "--source", "ixspy",
        "--product-type", "bag_accessories",
    ])
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: (_ for _ in ()).throw(AssertionError("db not needed")))
    monkeypatch.setattr(
        cli.erp_image_search,
        "generate_boss_decision_report",
        lambda **kwargs: calls.update(kwargs) or {"products": 1, "csv": "x.csv", "markdown": "x.md"},
    )

    cli.main()

    assert calls["base_dir"] == "."


def test_cli_erp_image_load_db(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-load-db", "--source", "ixspy", "--product-type", "bags",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "load_image_decisions",
        lambda conn, *, source, product_type, base_dir:
            calls.update(source=source, product_type=product_type, base_dir=base_dir) or {"loaded": 7},
    )
    cli.main()
    assert calls == {"source": "ixspy", "product_type": "bags", "base_dir": "/base518"}


def test_cli_erp_image_rerank(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-rerank", "--source", "ixspy", "--product-type", "bags", "--limit", "30",
    ])
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "rerank_image_search",
        lambda *, source, product_type, base_dir, limit, threshold:
            calls.update(source=source, product_type=product_type, base_dir=base_dir,
                         limit=limit, threshold=threshold) or {"reranked": 30, "confident": 12},
    )
    cli.main()
    assert calls["source"] == "ixspy" and calls["limit"] == 30 and calls["base_dir"] == "/base518"


def test_cli_erp_image_pipeline(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-pipeline", "--source", "ixspy",
        "--product-type", "home_goods", "--limit", "50", "--threshold", "0.8",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "run_pipeline",
        lambda conn, *, source, product_type, base_dir, limit, threshold:
            calls.update(source=source, product_type=product_type, base_dir=base_dir,
                         limit=limit, threshold=threshold) or {"report": {"products": 50}},
    )
    cli.main()
    assert calls == {"source": "ixspy", "product_type": "home_goods",
                     "base_dir": "/base518", "limit": 50, "threshold": 0.8}


def test_cli_erp_image_match_report(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-match-report", "--source", "ixspy", "--product-type", "home_goods",
    ])
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli.erp_image_search, "generate_best_match_report",
        lambda *, source, product_type, base_dir:
            calls.update(source=source, product_type=product_type, base_dir=base_dir) or {"products": 1000},
    )
    cli.main()
    assert calls == {"source": "ixspy", "product_type": "home_goods", "base_dir": "/base518"}


def test_cli_seerfar_enriched_report(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "seerfar-enriched-report", "--product-type", "ozon_hot",
    ])
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: (_ for _ in ()).throw(AssertionError("db not needed")))
    monkeypatch.setattr(
        cli.erp_image_search, "generate_seerfar_enriched_report",
        lambda *, product_type, base_dir:
            calls.update(product_type=product_type, base_dir=base_dir) or {"products": 30, "csv": "x.csv"},
    )
    cli.main()
    assert calls == {"product_type": "ozon_hot", "base_dir": "/base518"}
