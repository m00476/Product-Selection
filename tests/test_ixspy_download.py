import zipfile
from pathlib import Path

import pytest

from sourcing.collect.ixspy_download import _wait_for_download, _extract_zip


def _clock():
    state = {"t": 0.0}
    def now():
        return state["t"]
    def sleep(seconds):
        state["t"] += seconds
    return now, sleep


def test_wait_returns_zip_after_crdownload_finishes():
    states = [["pack.zip.crdownload"], ["pack.zip.crdownload"], ["pack.zip"]]
    i = {"n": 0}
    def snapshot():
        s = states[min(i["n"], len(states) - 1)]
        i["n"] += 1
        return s
    now, sleep = _clock()
    name = _wait_for_download(snapshot, timeout=100, sleep=sleep, now=now)
    assert name == "pack.zip"


def test_wait_ignores_zip_while_crdownload_present():
    # 同时存在 .zip 和 .crdownload 不算完成(Chrome 完成时才会去掉 .crdownload)
    def snapshot():
        return ["pack.zip", "pack.zip.crdownload"]
    now, sleep = _clock()
    with pytest.raises(TimeoutError):
        _wait_for_download(snapshot, timeout=3, sleep=sleep, now=now)


def test_wait_times_out_when_no_zip():
    now, sleep = _clock()
    with pytest.raises(TimeoutError):
        _wait_for_download(lambda: ["other.txt"], timeout=3, sleep=sleep, now=now)


def test_extract_zip_unpacks_nested_pack(tmp_path):
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Product_x/images/a.jpg", "x")
        zf.writestr("Product_x/Product_x.xls", "<table></table>")
    dest = _extract_zip(str(z), str(tmp_path / "out"))
    assert (Path(dest) / "Product_x" / "Product_x.xls").exists()
    assert (Path(dest) / "Product_x" / "images" / "a.jpg").exists()
