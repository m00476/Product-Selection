import os
from dataclasses import dataclass


@dataclass(frozen=True)
class SourceSpec:
    probe_script: str | None
    fetch_script: str | None
    output_subdir: str
    output_filename: str
    probe_module: str | None = None
    fetch_module: str | None = None


SOURCE_SPECS = {
    "seerfar": SourceSpec(None, None, "seerfar", "seerfar_products.csv",
                          probe_module="sourcing.collect.seerfar_api_probe",
                          fetch_module="sourcing.collect.seerfar_api_fetch"),
    "ixspy": SourceSpec(None, None, "aliexpress", "aliexpress_products.csv",
                        probe_module="sourcing.collect.aliexpress_api_probe",
                        fetch_module="sourcing.collect.aliexpress_api_fetch"),
    "erp": SourceSpec(None, None, "erp", "erp_products.csv",
                      probe_module="sourcing.collect.erp_api_probe",
                      fetch_module="sourcing.collect.erp_api_fetch"),
}


def get_source_spec(source: str) -> SourceSpec:
    return SOURCE_SPECS[source]


def output_csv_path(base_dir: str, source: str, product_type: str) -> str:
    spec = get_source_spec(source)
    return os.path.join(base_dir, "input", spec.output_subdir, product_type, spec.output_filename)


def source_file_label(source: str, product_type: str) -> str:
    spec = get_source_spec(source)
    return f"input/{spec.output_subdir}/{product_type}/{spec.output_filename}"
