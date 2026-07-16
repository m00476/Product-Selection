import re

from sourcing.platform_export_pipeline import (
    _boss_report_filename,
    _boss_report_rows,
    _public_raw_erp_rows_and_fields,
)


def test_boss_report_filename_uses_product_name_and_timestamp():
    filename = _boss_report_filename("母婴")

    assert re.fullmatch(r"母婴_\d{8}_\d{6}\.xlsx", filename)
    assert filename != "boss_report.xlsx"


def test_boss_report_filename_sanitizes_windows_invalid_chars():
    filename = _boss_report_filename('家装/灯具:*?"<>|')

    assert filename.startswith("家装_灯具_")
    assert not any(char in filename for char in '<>:"/\\|?*')


def test_boss_report_rows_keeps_only_actionable_matches():
    rows = [
        {"sku": "1", "匹配判定": "高置信匹配"},
        {"sku": "2", "匹配判定": "可能匹配"},
        {"sku": "3", "匹配判定": "弱匹配(需人工)"},
        {"sku": "4", "匹配判定": "无匹配(疑似不同款)"},
        {"sku": "5", "匹配判定": "无图或精筛失败"},
    ]

    assert [row["sku"] for row in _boss_report_rows(rows)] == ["1", "2"]


def test_public_raw_erp_export_removes_erp_sell_price():
    rows = [
        {
            "external_sku": "A1",
            "matched_erp_sku": "ERP-A",
            "erp_cost_price": "10",
            "erp_sell_price": "20",
        }
    ]

    public_rows, fields = _public_raw_erp_rows_and_fields(rows)

    assert "erp_sell_price" not in fields
    assert "erp_sell_price" not in public_rows[0]
    assert public_rows[0]["erp_cost_price"] == "10"
