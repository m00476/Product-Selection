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
