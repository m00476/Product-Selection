import re

from sourcing.platform_export_pipeline import _boss_report_filename


def test_boss_report_filename_uses_product_name_and_timestamp():
    filename = _boss_report_filename("母婴")

    assert re.fullmatch(r"母婴_\d{8}_\d{6}\.xlsx", filename)
    assert filename != "boss_report.xlsx"


def test_boss_report_filename_sanitizes_windows_invalid_chars():
    filename = _boss_report_filename('家装/灯具:*?"<>|')

    assert filename.startswith("家装_灯具_")
    assert not any(char in filename for char in '<>:"/\\|?*')
