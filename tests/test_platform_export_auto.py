from datetime import date
from pathlib import Path

import pytest

from sourcing.platform_export_pipeline import (
    _derive_slug,
    _derive_batch,
    _derive_category_name,
    _find_export_source,
    prepare_from_download,
)


# ---------- slug ----------

def test_slug_is_ascii_and_deterministic():
    s1 = _derive_slug("男女内衣及家居服")
    s2 = _derive_slug("男女内衣及家居服")
    assert s1 == s2                      # 同名稳定(输出目录/缓存命名靠它)
    assert s1.isascii() and s1           # 纯 ascii、非空
    assert s1 != _derive_slug("园林工具")  # 不同品类不撞


def test_slug_keeps_ascii_readable_part():
    s = _derive_slug("Pet Supplies 宠物")
    assert s.startswith("pet_supplies_")


def test_slug_transliterates_chinese_to_pinyin():
    # 纯中文应转成可读拼音(而非 cat_哈希)，便于从文件夹名识别品类
    s = _derive_slug("汽车及零配件")
    assert s.startswith("qichejilingpeijian")
    assert not s.startswith("cat_")


# ---------- batch ----------

def test_batch_parsed_from_product_dir_name():
    assert _derive_batch("Product_2026_6_10_9_02_55_week") == "2026-06-10_week"


def test_batch_falls_back_to_today():
    assert _derive_batch("whatever_no_date", today=date(2026, 6, 10)) == "2026-06-10_week"


# ---------- category name ----------

def test_category_name_from_dragged_folder():
    assert _derive_category_name(r"D:\IXSPY下载数据\男女内衣及家居服") == "男女内衣及家居服"


def test_category_name_skips_inner_product_dir():
    # 万一拖的是最内层 Product_xxx 目录，用其父目录的中文名
    assert _derive_category_name(r"D:\IXSPY下载数据\园林工具\Product_2026_6_10_week") == "园林工具"


# ---------- find source ----------

def test_find_export_source_locates_xls_and_images(tmp_path):
    inner = tmp_path / "Product_2026_6_10_week" / "Product_2026_6_10_week"
    (inner / "images").mkdir(parents=True)
    (inner / "Product_2026_6_10_week.xls").write_text("<table></table>", encoding="utf-8")
    xls, images, inner_name = _find_export_source(str(tmp_path))
    assert Path(xls).name.endswith(".xls")
    assert Path(images).is_dir()
    assert inner_name == "Product_2026_6_10_week"


def test_find_export_source_raises_when_missing(tmp_path):
    with pytest.raises(FileNotFoundError):
        _find_export_source(str(tmp_path))


# ---------- organize (prepare_from_download) ----------

def test_prepare_from_download_organizes_into_standard_input(tmp_path):
    # 造一个仿真下载包
    src = tmp_path / "下载" / "男女内衣及家居服"
    inner = src / "Product_2026_6_10_9_02_55_week" / "Product_2026_6_10_9_02_55_week"
    (inner / "images").mkdir(parents=True)
    (inner / "images" / "a.jpg").write_bytes(b"x")
    (inner / "Product_2026_6_10_9_02_55_week.xls").write_text("<table></table>", encoding="utf-8")

    base = tmp_path / "project"
    info = prepare_from_download(str(src), base_dir=str(base))

    assert info["product_type_name"] == "男女内衣及家居服"
    assert info["batch"] == "2026-06-10_week"
    slug = info["product_type"]
    dst = base / "input" / "platform_exports" / "ixspy" / slug / "2026-06-10_week"
    assert (dst / "source.xls").exists()
    assert (dst / "images" / "a.jpg").exists()
    assert (dst / "metadata.yaml").exists()
    meta = (dst / "metadata.yaml").read_text(encoding="utf-8")
    assert "男女内衣及家居服" in meta
