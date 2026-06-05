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
