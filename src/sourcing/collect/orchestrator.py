import os
import sys

import psycopg

from sourcing.collect.runner import SubprocessScriptRunner
from sourcing.collect.runs import (
    start_collector_run, finish_collector_run, record_collector_error,
)
from sourcing.collect.sources import get_source_spec, output_csv_path, source_file_label
from sourcing.importer import import_seerfar_csv, import_ixspy_csv, import_erp_csv

IMPORTERS = {
    "seerfar": import_seerfar_csv,
    "ixspy": import_ixspy_csv,
    "erp": import_erp_csv,
}


def _build_env(source: str, product_type: str) -> dict:
    env = dict(os.environ)
    env["PRODUCT_TYPE"] = product_type
    if source == "seerfar":
        env["MARKET_SOURCE"] = "seerfar"
    return env


def collect_target(conn: psycopg.Connection, source: str, product_type: str, *,
                   base_dir: str, runner=None, python_exe: str | None = None) -> dict:
    runner = runner or SubprocessScriptRunner()
    python_exe = python_exe or sys.executable
    spec = get_source_spec(source)
    env = _build_env(source, product_type)
    run_id = start_collector_run(conn, source, product_type)

    for script in (spec.probe_script, spec.fetch_script):
        result = runner.run([python_exe, os.path.join(base_dir, script)],
                            cwd=base_dir, env=env)
        if result.returncode != 0:
            record_collector_error(conn, run_id, source,
                                   f"{script} exited {result.returncode}",
                                   (result.stderr or "")[:2000])
            finish_collector_run(conn, run_id, status="failed", record_count=0)
            return {"status": "failed", "source": source, "product_type": product_type}

    csv_path = output_csv_path(base_dir, source, product_type)
    if not os.path.exists(csv_path):
        record_collector_error(conn, run_id, source, f"output CSV not found: {csv_path}")
        finish_collector_run(conn, run_id, status="failed", record_count=0)
        return {"status": "failed", "source": source, "product_type": product_type}

    summary = IMPORTERS[source](conn, csv_path, product_type=product_type,
                                source_file=source_file_label(source, product_type))
    count = summary.get("products", 0)
    finish_collector_run(conn, run_id, status="success", record_count=count)
    return {"status": "success", "source": source, "product_type": product_type, "records": count}


def collect_all(conn: psycopg.Connection, targets, *, base_dir: str, runner=None) -> list[dict]:
    results = []
    for source, product_type in targets:
        results.append(collect_target(conn, source, product_type,
                                      base_dir=base_dir, runner=runner))
    return results
