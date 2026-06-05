# 采集编排（Collection Orchestration）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 用一条命令 `python -m sourcing.cli collect`，按 (源 × 品类) 调用 `518\apipy` 的 probe+fetch 脚本产出 CSV，自动导入 PostgreSQL，并把每次运行与失败记进 `collector_runs` / `collector_errors`；可交给 Windows 任务计划定时跑。

**Architecture:** 薄编排层。`sources`（源→脚本/产物路径映射，纯数据）+ `runner`（subprocess 执行单个脚本，可注入假实现）+ `runs`（运行/失败记录入库）+ `orchestrator`（串起 probe→fetch→定位CSV→导入→记录）+ CLI `collect` 子命令。凭证留在 `518/.env`（脚本自读），编排只设 `PRODUCT_TYPE`。

**Tech Stack:** Python 3.12（标准库 subprocess）、psycopg 3、pytest、PostgreSQL 16（localhost:5432）。

参考设计：`docs/.../2026-06-04-product-sourcing-system-design.md` §2.1/§2.2。依赖已合并的 Plan 1（`collector_runs`/`collector_errors` 表、三源导入器 `import_seerfar_csv`/`import_ixspy_csv`/`import_erp_csv`）。

## 关键事实（来自 518/apipy/README）
- 每源两段脚本：先 `*_probe.py`（Selenium 登录+捕获接口），后 `*_fetch.py`（回放+导出 CSV）。从 518 根目录运行，凭证读 518 根 `.env`。
- 按 `PRODUCT_TYPE` 环境变量切品类（python-dotenv `load_dotenv` 默认不覆盖已存在的环境变量，故我们在子进程 env 里设 `PRODUCT_TYPE` 会生效）。seerfar 另需 `MARKET_SOURCE=seerfar`。
- 产物路径：`<518>/input/<子目录>/<品类>/<文件名>`。源→(脚本/子目录/文件名/导入器) 映射：

| source | probe / fetch | 子目录 | 文件名 | 导入器 |
|---|---|---|---|---|
| seerfar | apipy/seerfar_api_probe.py / seerfar_api_fetch.py | seerfar | seerfar_products.csv | import_seerfar_csv |
| ixspy | apipy/aliexpress_api_probe.py / aliexpress_api_fetch.py | aliexpress | aliexpress_products.csv | import_ixspy_csv |
| erp | apipy/erp_api_probe.py / erp_api_fetch.py | erp | erp_products.csv | import_erp_csv |

## File Structure
```
src/sourcing/collect/__init__.py
src/sourcing/collect/sources.py       # SourceSpec + 路径/脚本解析（纯数据，无 DB）
src/sourcing/collect/runner.py        # RunResult + SubprocessScriptRunner
src/sourcing/collect/runs.py          # start/finish/record 运行日志（DB）
src/sourcing/collect/orchestrator.py  # collect_target / collect_all
src/sourcing/config.py                # 增加 collect_base_dir / collect_targets（修改）
src/sourcing/cli.py                   # 增加 collect 子命令（修改）
.env.example                          # 增加 COLLECT_518_DIR / COLLECT_TARGETS（修改）
tests/test_collect_sources.py
tests/test_collect_runner.py
tests/test_collect_runs.py
tests/test_collect_orchestrator.py
tests/test_cli.py                     # 追加 collect 用例（修改）
```

---

## Task 1: 源映射（sources.py，纯数据）

**Files:** Create `src/sourcing/collect/__init__.py` (empty), `src/sourcing/collect/sources.py`; Test `tests/test_collect_sources.py`.

- [ ] **Step 1: 写失败测试 `tests/test_collect_sources.py`**

```python
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
```

- [ ] **Step 2: 运行 `pytest tests/test_collect_sources.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/collect/__init__.py`（空）与 `src/sourcing/collect/sources.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_collect_sources.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/collect/__init__.py src/sourcing/collect/sources.py tests/test_collect_sources.py
git commit -m "feat: collect source specs (script + csv path mapping)"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 2: 脚本执行器（runner.py）

**Files:** Create `src/sourcing/collect/runner.py`; Test `tests/test_collect_runner.py`.

- [ ] **Step 1: 写失败测试 `tests/test_collect_runner.py`**（用一段无害的 python 命令验证 subprocess 接线，不碰 Selenium）

```python
import os
import sys
from sourcing.collect.runner import SubprocessScriptRunner, RunResult


def test_subprocess_runner_captures_stdout_and_rc(tmp_path):
    runner = SubprocessScriptRunner()
    result = runner.run([sys.executable, "-c", "print('hello-collect')"],
                        cwd=str(tmp_path), env=dict(os.environ))
    assert isinstance(result, RunResult)
    assert result.returncode == 0
    assert "hello-collect" in result.stdout


def test_subprocess_runner_nonzero_rc():
    runner = SubprocessScriptRunner()
    result = runner.run([sys.executable, "-c", "import sys; sys.exit(3)"],
                        cwd=None, env=dict(os.environ))
    assert result.returncode == 3
```

- [ ] **Step 2: 运行 `pytest tests/test_collect_runner.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/collect/runner.py`**

```python
import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessScriptRunner:
    """运行单个脚本的默认实现。测试可注入假实现（鸭子类型：实现 run(...) 即可）。"""

    def run(self, args: list[str], *, cwd: str | None, env: dict) -> RunResult:
        proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")
```

- [ ] **Step 4: 运行 `pytest tests/test_collect_runner.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/collect/runner.py tests/test_collect_runner.py
git commit -m "feat: subprocess script runner for collection"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 3: 运行日志（runs.py，DB）

**Files:** Create `src/sourcing/collect/runs.py`; Test `tests/test_collect_runs.py`.

依赖表（Plan 1 已建）：`collector_runs`(id, source, product_type, started_at, finished_at, status, record_count)、`collector_errors`(id, run_id, source, detail, raw_excerpt, created_at)。

- [ ] **Step 1: 写失败测试 `tests/test_collect_runs.py`**

```python
from sourcing.collect.runs import (
    start_collector_run, finish_collector_run, record_collector_error,
)


def test_start_and_finish_run(conn):
    run_id = start_collector_run(conn, "seerfar", "laptop")
    assert isinstance(run_id, int)
    with conn.cursor() as cur:
        cur.execute("SELECT status, finished_at FROM collector_runs WHERE id=%s", (run_id,))
        status, finished = cur.fetchone()
        assert status == "running" and finished is None
    finish_collector_run(conn, run_id, status="success", record_count=5)
    with conn.cursor() as cur:
        cur.execute("SELECT status, record_count, finished_at FROM collector_runs WHERE id=%s", (run_id,))
        status, count, finished = cur.fetchone()
        assert status == "success" and count == 5 and finished is not None


def test_record_error(conn):
    run_id = start_collector_run(conn, "ozon", "laptop")
    record_collector_error(conn, run_id, "ozon", "boom", "stderr excerpt")
    with conn.cursor() as cur:
        cur.execute("SELECT run_id, source, detail, raw_excerpt FROM collector_errors WHERE run_id=%s", (run_id,))
        row = cur.fetchone()
        assert row == (run_id, "ozon", "boom", "stderr excerpt")
```

- [ ] **Step 2: 运行 `pytest tests/test_collect_runs.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/collect/runs.py`**

```python
import psycopg


def start_collector_run(conn: psycopg.Connection, source: str, product_type: str) -> int:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO collector_runs (source, product_type, status) "
            "VALUES (%s, %s, 'running') RETURNING id",
            (source, product_type),
        )
        run_id = cur.fetchone()[0]
    conn.commit()
    return run_id


def finish_collector_run(conn: psycopg.Connection, run_id: int, *,
                         status: str, record_count: int) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "UPDATE collector_runs SET status=%s, record_count=%s, finished_at=now() WHERE id=%s",
            (status, record_count, run_id),
        )
    conn.commit()


def record_collector_error(conn: psycopg.Connection, run_id: int, source: str,
                           detail: str, raw_excerpt: str | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            "INSERT INTO collector_errors (run_id, source, detail, raw_excerpt) "
            "VALUES (%s, %s, %s, %s)",
            (run_id, source, detail, raw_excerpt),
        )
    conn.commit()
```

- [ ] **Step 4: 运行 `pytest tests/test_collect_runs.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/collect/runs.py tests/test_collect_runs.py
git commit -m "feat: collector run/error logging"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 4: 编排器（orchestrator.py）

**Files:** Create `src/sourcing/collect/orchestrator.py`; Test `tests/test_collect_orchestrator.py`.

- [ ] **Step 1: 写失败测试 `tests/test_collect_orchestrator.py`**（用假 runner：成功时把 fixture CSV 写到期望产物路径；失败时返回非零）

```python
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
    # runner 成功但不产出 CSV
    class NoOutputRunner:
        def run(self, args, *, cwd, env):
            return RunResult(0, "ok", "")
    result = collect_target(conn, "seerfar", "laptop", base_dir=base, runner=NoOutputRunner())
    assert result["status"] == "failed"
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM collector_errors")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行 `pytest tests/test_collect_orchestrator.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/collect/orchestrator.py`**

```python
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
```

- [ ] **Step 4: 运行 `pytest tests/test_collect_orchestrator.py -v`，确认 PASS（3 个用例）。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/collect/orchestrator.py tests/test_collect_orchestrator.py
git commit -m "feat: collection orchestrator (probe+fetch -> import -> log)"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 5: 配置 + CLI collect 子命令

**Files:** Modify `src/sourcing/config.py`, `src/sourcing/cli.py`, `.env.example`; Test: append to `tests/test_cli.py`.

- [ ] **Step 1: 在 `src/sourcing/config.py` 末尾追加**

```python
def collect_base_dir() -> str:
    return os.environ.get("COLLECT_518_DIR", r"C:\Users\aibp\Desktop\518")


def collect_targets() -> list[tuple[str, str]]:
    """解析 COLLECT_TARGETS，如 'seerfar:xiongzhen,erp:xiongzhen' -> [('seerfar','xiongzhen'),...]"""
    raw = os.environ.get("COLLECT_TARGETS", "")
    targets = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        source, _, product_type = item.partition(":")
        if source and product_type:
            targets.append((source, product_type))
    return targets
```

- [ ] **Step 2: 在 `.env.example` 末尾追加**

```text
# 采集编排：518 项目根目录，与逗号分隔的 源:品类 列表
COLLECT_518_DIR=C:\Users\aibp\Desktop\518
COLLECT_TARGETS=seerfar:xiongzhen,erp:xiongzhen
```

- [ ] **Step 3: 修改 `src/sourcing/cli.py`** — 增加 `collect` 子命令。完整新内容：

```python
import argparse
import json
from sourcing import config, db
from sourcing.importer import import_erp_csv, import_ixspy_csv, import_seerfar_csv
from sourcing.analysis.run import run_analysis
from sourcing.quality import inspect_csv_quality
from sourcing.collect.orchestrator import collect_all


def main() -> None:
    parser = argparse.ArgumentParser(description="Sourcing pipeline CLI")
    sub = parser.add_subparsers(dest="command", required=True)

    imp = sub.add_parser("import", help="导入源 CSV 到 PostgreSQL")
    imp.add_argument("--source", required=True, choices=["seerfar", "ixspy", "erp"])
    imp.add_argument("--path", required=True, help="CSV 文件路径")
    imp.add_argument("--product-type", required=True)

    quality = sub.add_parser("quality", help="检查源 CSV 字段完整性")
    quality.add_argument("--source", required=True, choices=["seerfar", "ixspy", "erp"])
    quality.add_argument("--path", required=True, help="CSV 文件路径")
    quality.add_argument("--product-type", required=True)

    sub.add_parser("analyze", help="计算利润估算与机会分")

    col = sub.add_parser("collect", help="调用采集脚本产出CSV并导入")
    col.add_argument("--source", choices=["seerfar", "ixspy", "erp"],
                     help="单个源（与 --product-type 一起用）")
    col.add_argument("--product-type", help="单个品类")
    col.add_argument("--all", action="store_true", help="按 COLLECT_TARGETS 采集全部")

    args = parser.parse_args()

    if args.command == "quality":
        report = inspect_csv_quality(args.path, source=args.source, product_type=args.product_type)
        print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
        return

    conn = db.connect(config.database_url())
    try:
        if args.command == "import":
            importers = {
                "seerfar": import_seerfar_csv,
                "ixspy": import_ixspy_csv,
                "erp": import_erp_csv,
            }
            summary = importers[args.source](
                conn, args.path, product_type=args.product_type, source_file=args.path)
            print(f"[DONE] imported: {summary}")
        elif args.command == "analyze":
            summary = run_analysis(conn)
            print(f"[DONE] analyzed: {summary}")
        elif args.command == "collect":
            if args.all:
                targets = config.collect_targets()
            elif args.source and args.product_type:
                targets = [(args.source, args.product_type)]
            else:
                raise SystemExit("collect 需要 --all，或同时给 --source 与 --product-type")
            results = collect_all(conn, targets, base_dir=config.collect_base_dir())
            print(f"[DONE] collected: {results}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

- [ ] **Step 4: APPEND 测试到 `tests/test_cli.py`**（沿用文件里既有的 FakeConn 风格；monkeypatch 掉 collect_all）

```python
def test_cli_collect_single_target(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "collect", "--source", "seerfar", "--product-type", "laptop",
    ])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "collect_all",
        lambda conn, targets, *, base_dir: calls.update(targets=targets, base_dir=base_dir) or [],
    )
    cli.main()
    assert calls["targets"] == [("seerfar", "laptop")]
    assert calls["base_dir"] == "/base518"


def test_cli_collect_all_uses_config_targets(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", ["sourcing.cli", "collect", "--all"])
    monkeypatch.setattr(cli.config, "database_url", lambda: "db")
    monkeypatch.setattr(cli.db, "connect", lambda _dsn: FakeConn())
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(cli.config, "collect_targets", lambda: [("erp", "socks")])
    monkeypatch.setattr(
        cli, "collect_all",
        lambda conn, targets, *, base_dir: calls.update(targets=targets) or [],
    )
    cli.main()
    assert calls["targets"] == [("erp", "socks")]
```

- [ ] **Step 5: 验证 CLI 可导入：`python -c "import sourcing.cli; print('cli ok')"`，期望 `cli ok`。**

- [ ] **Step 6: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 7: Commit**
```
git add src/sourcing/config.py src/sourcing/cli.py .env.example tests/test_cli.py
git commit -m "feat: cli collect subcommand + collect config"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 6: README — 采集与定时

**Files:** Modify `README.md`.

- [ ] **Step 1: 在 README「计算利润与机会分」一节后插入：**

````markdown
## 采集（调用 518 脚本并入库）
凭证放在 `518` 项目根的 `.env`（脚本自读）。本系统只负责编排：
```powershell
# 单个源×品类
python -m sourcing.cli collect --source seerfar --product-type xiongzhen
# 按 .env 的 COLLECT_TARGETS 全部采集
python -m sourcing.cli collect --all
```
配置（`.env`）：`COLLECT_518_DIR`（518 根目录）、`COLLECT_TARGETS`（如 `seerfar:xiongzhen,erp:xiongzhen`）。
每次运行记录在 `collector_runs` / `collector_errors`。

### 定时（Windows 任务计划）
新建基本任务，操作设为：
`程序` = `python`，`参数` = `-m sourcing.cli collect --all`，`起始于` = 项目目录 `D:\ProductSourcingSystem`。
建议每天凌晨触发；采集依赖 Chrome/Chromedriver 与 518/.env 凭证。
````

- [ ] **Step 2: Commit**
```
git add README.md
git commit -m "docs: collect command + Windows Task Scheduler runbook"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Self-Review 结论
- **Spec 覆盖**：§2.2「复用编排现成 probe+fetch 脚本 → CSV → 导入」由 orchestrator 实现；§7 失败隔离/运行记录由 runs + collector_runs/errors 实现；调度交 Windows 任务计划（设计认可的拆分部署/外部调度）。
- **可测性**：编排逻辑用假 runner + fixture CSV 全程可测（成功/脚本失败/缺CSV三路径）；真实 Selenium 抓取依赖用户环境与 518/.env 凭证，不在自动化测试内（设计已注明此机制比官方API脆弱）。
- **占位符**：无 TODO/TBD；所有代码步骤含完整可执行代码。
- **类型一致性**：`SourceSpec`、`RunResult`、`get_source_spec/output_csv_path/source_file_label`、`start/finish_collector_run/record_collector_error`、`collect_target/collect_all`、`config.collect_base_dir/collect_targets` 跨任务一致；导入器签名 `(conn, path, *, product_type, source_file)` 与 Plan 1/已合并改动一致。
- **已知边界/后续**：probe token 过期自动刷新由 518 脚本内部处理（ERP 已实现）；限速/错峰由调度与脚本承担；ERP 成本字段解析扩展、Seerfar extra_metrics 落库属其它工单。
- **依赖**：`collector_runs`/`collector_errors`（Plan 1）、三源导入器（已合并）均就绪；不改动既有模块行为，仅新增 collect 包并扩展 CLI/config。
```
