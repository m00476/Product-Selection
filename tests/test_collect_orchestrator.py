import os
import shutil
from sourcing.collect.runner import RunResult
from sourcing.collect.sources import output_csv_path
from sourcing.collect.orchestrator import collect_target


class FakeRunner:
    """成功：在“跑脚本”时把 seerfar fixture 复制到期望产物路径。失败：返回非零。"""
    def __init__(self, base_dir, source, product_type, fail=False):
        self.csv_path = output_csv_path(base_dir, source, product_type)
        self.fail = fail
        self.calls = 0

    def run(self, args, *, cwd, env):
        self.calls += 1
        if self.fail:
            return RunResult(1, "", "boom")
        os.makedirs(os.path.dirname(self.csv_path), exist_ok=True)
        shutil.copyfile("tests/fixtures/seerfar_sample.csv", self.csv_path)
        return RunResult(0, "ok", "")


def test_collect_target_success_imports_and_logs(conn, tmp_path):
    base = str(tmp_path)
    runner = FakeRunner(base, "seerfar", "laptop")
    result = collect_target(conn, "seerfar", "laptop", base_dir=base, runner=runner)
    assert result["status"] == "success"
    assert result["records"] == 2
    assert runner.calls == 2  # probe + fetch
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT status, record_count FROM collector_runs WHERE source='seerfar'")
        assert cur.fetchone() == ("success", 2)


def test_collect_target_script_failure_logs_error_no_import(conn, tmp_path):
    base = str(tmp_path)
    runner = FakeRunner(base, "seerfar", "laptop", fail=True)
    result = collect_target(conn, "seerfar", "laptop", base_dir=base, runner=runner)
    assert result["status"] == "failed"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 0
        cur.execute("SELECT status FROM collector_runs WHERE source='seerfar'")
        assert cur.fetchone()[0] == "failed"
        cur.execute("SELECT count(*) FROM collector_errors")
        assert cur.fetchone()[0] == 1


def test_collect_target_missing_csv_fails(conn, tmp_path):
    base = str(tmp_path)
    class NoOutputRunner:
        def run(self, args, *, cwd, env):
            return RunResult(0, "ok", "")
    result = collect_target(conn, "seerfar", "laptop", base_dir=base, runner=NoOutputRunner())
    assert result["status"] == "failed"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM collector_errors")
        assert cur.fetchone()[0] == 1
