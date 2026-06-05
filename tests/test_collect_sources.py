import os
from sourcing.collect.sources import get_source_spec, output_csv_path, source_file_label


def test_seerfar_spec_paths():
    spec = get_source_spec("seerfar")
    assert spec.probe_script is None
    assert spec.fetch_script is None
    assert spec.probe_module == "sourcing.collect.seerfar_api_probe"
    assert spec.fetch_module == "sourcing.collect.seerfar_api_fetch"


def test_ixspy_maps_to_aliexpress_dir():
    path = output_csv_path("/base", "ixspy", "shoes")
    assert path == os.path.join("/base", "input", "aliexpress", "shoes", "aliexpress_products.csv")


def test_ixspy_uses_internal_collect_modules():
    spec = get_source_spec("ixspy")
    assert spec.probe_script is None
    assert spec.fetch_script is None
    assert spec.probe_module == "sourcing.collect.aliexpress_api_probe"
    assert spec.fetch_module == "sourcing.collect.aliexpress_api_fetch"


def test_erp_fetch_uses_internal_collect_module():
    spec = get_source_spec("erp")
    assert spec.probe_module == "sourcing.collect.erp_api_probe"
    assert spec.fetch_module == "sourcing.collect.erp_api_fetch"


def test_source_file_label_is_relative():
    assert source_file_label("seerfar", "laptop") == "input/seerfar/laptop/seerfar_products.csv"


def test_unknown_source_raises():
    import pytest
    with pytest.raises(KeyError):
        get_source_spec("amazon")
