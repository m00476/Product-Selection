import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    probe_script: str
    fetch_script: str
    output_subdir: str
    output_filename: str


SOURCE_SPECS = {
    "seerfar": SourceSpec("apipy/seerfar_api_probe.py", "apipy/seerfar_api_fetch.py",
                          "seerfar", "seerfar_products.csv"),
    "ixspy": SourceSpec("apipy/aliexpress_api_probe.py", "apipy/aliexpress_api_fetch.py",
                        "aliexpress", "aliexpress_products.csv"),
    "erp": SourceSpec("apipy/erp_api_probe.py", "apipy/erp_api_fetch.py",
                      "erp", "erp_products.csv"),
}


def get_source_spec(source: str) -> SourceSpec:
    return SOURCE_SPECS[source]


def output_csv_path(base_dir: str, source: str, product_type: str) -> str:
    spec = get_source_spec(source)
    return os.path.join(base_dir, "input", spec.output_subdir, product_type, spec.output_filename)


def source_file_label(source: str, product_type: str) -> str:
    spec = get_source_spec(source)
    return f"input/{spec.output_subdir}/{product_type}/{spec.output_filename}"
