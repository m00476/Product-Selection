import pytest

from sourcing.platform_export_pipeline import _row_image_filenames


HEADER = "<tr><td>商品id</td><td>图片</td><td>商品名</td></tr>"


def _row(sku, img, name):
    img_cell = f"<td><img src='./images/{img}' /></td>" if img else "<td></td>"
    return f"<tr><td>{sku}</td>{img_cell}<td>{name}</td></tr>"


def test_pairs_image_within_each_row():
    html = HEADER + _row("A", "a.jpg", "n1") + _row("B", "b.jpg", "n2")
    assert _row_image_filenames(html, 2) == ["a.jpg", "b.jpg"]


def test_missing_image_in_middle_row_does_not_shift_following_rows():
    """核心：第2行缺图时，第3行仍拿到自己的图(c.jpg)，不会被错位顶上来。
    旧的全局索引法会把 c.jpg 错配给第2行。"""
    html = HEADER + _row("A", "a.jpg", "n1") + _row("B", "", "n2") + _row("C", "c.jpg", "n3")
    assert _row_image_filenames(html, 3) == ["a.jpg", "", "c.jpg"]


def test_drops_header_row_when_present():
    html = HEADER + _row("A", "a.jpg", "n1")
    # 表头行(无图)被丢弃，只返回 1 个数据行的图
    assert _row_image_filenames(html, 1) == ["a.jpg"]


def test_raises_when_row_count_mismatch():
    # 数据行数(2)与声明的 n_rows(3) 对不上 -> 抛错，绝不静默错配
    html = HEADER + _row("A", "a.jpg", "n1") + _row("B", "b.jpg", "n2")
    with pytest.raises(ValueError):
        _row_image_filenames(html, 3)


def test_read_platform_export_url_mode_no_images_folder(tmp_path):
    # URL版导出: 产品图列是完整URL, 无 <img> 标签, 也无 images/ 文件夹
    from sourcing.platform_export_pipeline import read_platform_export
    html = ('<html><head><meta charset="utf-8"></head><body><table>'
            "<tr><th>商品id</th><th>产品图</th><th>商品名</th></tr>"
            "<tr><td>1</td><td>https://x/a.jpg</td><td>n1</td></tr>"
            "<tr><td>2</td><td>https://x/b.jpg</td><td>n2</td></tr>"
            "</table></body></html>")
    batch = tmp_path / "b"
    batch.mkdir()
    (batch / "source.xls").write_text(html, encoding="utf-8")
    (batch / "metadata.yaml").write_text("product_type_name: 测试品类\n", encoding="utf-8")
    _, rows = read_platform_export(str(batch))   # 不应因缺 images/ 报错
    assert rows[0]["image_url"] == "https://x/a.jpg"
    assert rows[0]["local_image_path"] == ""
    assert rows[1]["image_url"] == "https://x/b.jpg"
    assert rows[0]["category"] == "测试品类"
