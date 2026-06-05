import os
from sourcing.collect.sources import get_source_spec, output_csv_path, source_file_label


def test_seerfar_spec_paths():
    spec = get_source_spec("seerfar")
    assert spec.probe_script.endswith("seerfar_api_probe.py")
    assert spec.fetch_script.endswith("seerfar_api_fetch.py")


def test_ixspy_maps_to_aliexpress_dir():
    path = output_csv_path("/base", "ixspy", "shoes")
    assert path == os.path.join("/base", "input", "aliexpress", "shoes", "aliexpress_products.csv")


def test_source_file_label_is_relative():
    assert source_file_label("seerfar", "laptop") == "input/seerfar/laptop/seerfar_products.csv"


def test_unknown_source_raises():
    import pytest
    with pytest.raises(KeyError):
        get_source_spec("amazon")
