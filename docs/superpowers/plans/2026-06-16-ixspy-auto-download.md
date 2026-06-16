# IXSPY 自动下载 + 双筛一条龙 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 用户给一个品类名，程序自动登录 IXSPY 下载该品类压缩包 → 解压 → 跑现有双筛 → 出老板版报告。

**Architecture:** 方案 1（模拟点击导出）。新增 `ixspy_download.py` 负责"登录+选类目+点导出+等下载+解压"，复用现有 `aliexpress_api_probe` 的登录/选类目代码；解压后喂现有 `run_from_download`（新增 `category_name` 覆盖参数）。触发用 bat→ps1（Read-Host 收中文品类名，避免 GBK 编码坑）。

**Tech Stack:** Python 3.12, Selenium, zipfile, pytest；下游复用 platform_export_pipeline。

参考 spec：`docs/superpowers/specs/2026-06-16-ixspy-auto-download-design.md`

---

## File Structure

- Create `src/sourcing/collect/ixspy_download.py` — 下载+解压（`build_download_driver` / `_wait_for_download` / `_extract_zip` / `_click_export` / `download_export`）
- Modify `src/sourcing/platform_export_pipeline.py` — `prepare_from_download` / `run_from_download` 加 `category_name` 覆盖参数
- Modify `src/sourcing/cli.py` — 新增 `ixspy-auto` 命令
- Create `scripts/ixspy_auto_prompt.ps1` — Read-Host 收品类名后调命令（ASCII 内容）
- Create `ixspy-自动下载双筛.bat` — 双击入口，调上面的 ps1（ASCII 内容）
- Test `tests/test_platform_export_auto.py`（追加）、`tests/test_ixspy_download.py`（新）

---

## Task 1: `category_name` 覆盖参数（下游接已知品类名）

**Files:**
- Modify: `src/sourcing/platform_export_pipeline.py`（`prepare_from_download`、`run_from_download`）
- Test: `tests/test_platform_export_auto.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_platform_export_auto.py`：

```python
def test_prepare_uses_explicit_category_name_over_folder(tmp_path):
    # 自动下载场景：解压目录名是 Product_xxx(无中文)，但我们已知用户输入的品类名
    src = tmp_path / "Product_2026_6_10_week"
    inner = src / "Product_2026_6_10_week"
    (inner / "images").mkdir(parents=True)
    (inner / "images" / "a.jpg").write_bytes(b"x")
    (inner / "Product_2026_6_10_week.xls").write_text("<table></table>", encoding="utf-8")
    base = tmp_path / "project"
    info = prepare_from_download(str(src), base_dir=str(base), category_name="汽车及零配件")
    assert info["product_type_name"] == "汽车及零配件"
    assert info["product_type"].startswith("qichejilingpeijian")
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_platform_export_auto.py::test_prepare_uses_explicit_category_name_over_folder -q`
Expected: FAIL（`prepare_from_download() got an unexpected keyword argument 'category_name'`）

- [ ] **Step 3: 改 `prepare_from_download` 签名与取名逻辑**

在 `prepare_from_download` 中，把：
```python
def prepare_from_download(src: str | Path, *, base_dir: str | Path,
                          platform: str = "ixspy") -> dict:
    xls_path, images_dir, inner_name = _find_export_source(src)
    category_name = _derive_category_name(src)
```
改为：
```python
def prepare_from_download(src: str | Path, *, base_dir: str | Path,
                          platform: str = "ixspy", category_name: str | None = None) -> dict:
    xls_path, images_dir, inner_name = _find_export_source(src)
    category_name = category_name or _derive_category_name(src)
```

- [ ] **Step 4: 给 `run_from_download` 透传 `category_name`**

把 `run_from_download` 签名加 `category_name: str | None = None`，并在其内部调用处：
```python
    info = prepare_from_download(src, base_dir=base_dir, platform=platform)
```
改为：
```python
    info = prepare_from_download(src, base_dir=base_dir, platform=platform,
                                 category_name=category_name)
```

- [ ] **Step 5: 跑测试确认通过 + 全套**

Run: `python -m pytest tests/test_platform_export_auto.py -q`
Expected: PASS（含新用例）
Run: `python -m pytest -q`
Expected: 全绿

- [ ] **Step 6: 提交**

```bash
git add src/sourcing/platform_export_pipeline.py tests/test_platform_export_auto.py
git commit -m "feat: prepare/run_from_download 支持 category_name 覆盖(自动下载用)"
```

---

## Task 2: `_wait_for_download` 检测下载完成（纯逻辑）

**Files:**
- Create: `src/sourcing/collect/ixspy_download.py`
- Test: `tests/test_ixspy_download.py`

- [ ] **Step 1: 写失败测试**

新建 `tests/test_ixspy_download.py`：

```python
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
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ixspy_download.py -q`
Expected: FAIL（`ModuleNotFoundError: No module named 'sourcing.collect.ixspy_download'`）

- [ ] **Step 3: 新建模块 + 实现 `_wait_for_download`**

新建 `src/sourcing/collect/ixspy_download.py`：

```python
"""IXSPY 自动下载：登录 → 选类目 → 点数据导出 → 等 zip → 解压。方案1(模拟点击)。"""
import time
import zipfile
from pathlib import Path


def _wait_for_download(snapshot, *, timeout: float, sleep=time.sleep, now=time.monotonic) -> str:
    """轮询下载目录文件名列表，等到出现 .zip 且无 .crdownload 即完成，返回该 zip 文件名。
    snapshot() -> list[str] 当前目录文件名；超时抛 TimeoutError。"""
    deadline = now() + timeout
    while now() < deadline:
        names = list(snapshot())
        downloading = any(n.lower().endswith(".crdownload") for n in names)
        zips = [n for n in names if n.lower().endswith(".zip")]
        if zips and not downloading:
            return zips[0]
        sleep(1.0)
    raise TimeoutError("下载超时：未在限定时间内得到完整的 .zip")
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ixspy_download.py -q`
Expected: 3 passed

- [ ] **Step 5: 提交**

```bash
git add src/sourcing/collect/ixspy_download.py tests/test_ixspy_download.py
git commit -m "feat: ixspy_download._wait_for_download 下载完成检测"
```

---

## Task 3: `_extract_zip` 解压

**Files:**
- Modify: `src/sourcing/collect/ixspy_download.py`
- Test: `tests/test_ixspy_download.py`（追加）

- [ ] **Step 1: 写失败测试**

追加到 `tests/test_ixspy_download.py`：

```python
def test_extract_zip_unpacks_nested_pack(tmp_path):
    z = tmp_path / "pack.zip"
    with zipfile.ZipFile(z, "w") as zf:
        zf.writestr("Product_x/images/a.jpg", "x")
        zf.writestr("Product_x/Product_x.xls", "<table></table>")
    dest = _extract_zip(str(z), str(tmp_path / "out"))
    assert (Path(dest) / "Product_x" / "Product_x.xls").exists()
    assert (Path(dest) / "Product_x" / "images" / "a.jpg").exists()
```

- [ ] **Step 2: 跑测试确认失败**

Run: `python -m pytest tests/test_ixspy_download.py::test_extract_zip_unpacks_nested_pack -q`
Expected: FAIL（`cannot import name '_extract_zip'`）

- [ ] **Step 3: 实现 `_extract_zip`**

在 `ixspy_download.py` 末尾追加：

```python
def _extract_zip(zip_path: str, dest_dir: str) -> str:
    """解压 zip 到 dest_dir(先清空)，返回 dest_dir。"""
    dest = Path(dest_dir)
    if dest.exists():
        import shutil
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    return str(dest)
```

- [ ] **Step 4: 跑测试确认通过**

Run: `python -m pytest tests/test_ixspy_download.py -q`
Expected: 4 passed

- [ ] **Step 5: 提交**

```bash
git add src/sourcing/collect/ixspy_download.py tests/test_ixspy_download.py
git commit -m "feat: ixspy_download._extract_zip 解压压缩包"
```

---

## Task 4: 浏览器下载（`build_download_driver` / `_click_export` / `download_export`）

> 浏览器胶水代码，不做单测（Selenium 需真环境）；靠 Task 7 真实冒烟验证。提供完整代码。

**Files:**
- Modify: `src/sourcing/collect/ixspy_download.py`

- [ ] **Step 1: 追加导入与下载驱动**

在 `ixspy_download.py` 顶部 `import` 区补 `import os`，并在末尾追加：

```python
def build_download_driver(download_dir: str, *, headless: bool):
    """起 Chrome 并把下载目录固定到 download_dir(禁下载弹窗)。"""
    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    if headless:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
    else:
        options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.add_experimental_option("prefs", {
        "download.default_directory": str(download_dir),
        "download.prompt_for_download": False,
        "download.directory_upgrade": True,
        "safebrowsing.enabled": True,
    })
    driver_path = os.environ.get(
        "CHROMEDRIVER_PATH", r"C:\Users\aibp\chromedriver\chromedriver-win64\chromedriver.exe")
    service = Service(driver_path) if os.path.exists(driver_path) else Service(ChromeDriverManager().install())
    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(int(os.environ.get("SCRAPER_PAGE_LOAD_TIMEOUT") or 60))
    return driver
```

- [ ] **Step 2: 追加点导出按钮**

```python
def _click_export(driver) -> None:
    """点击"数据导出(下载压缩包...)"按钮。找不到则抛错。"""
    xpaths = [
        "//button[contains(normalize-space(.), '数据导出')]",
        "//*[contains(@class,'btn') and contains(normalize-space(.), '数据导出')]",
        "//a[contains(normalize-space(.), '数据导出')]",
        "//span[contains(normalize-space(.), '数据导出')]/ancestor::button",
    ]
    for xpath in xpaths:
        for element in driver.find_elements("xpath", xpath):
            try:
                if element.is_displayed():
                    driver.execute_script("arguments[0].click();", element)
                    return
            except Exception:
                continue
    raise RuntimeError("找不到'数据导出'按钮，页面可能改版，请人工确认")
```

- [ ] **Step 3: 追加 `download_export` 编排**

```python
def download_export(category: str, *, download_dir: str, headless: bool = False,
                    timeout: float = 600, driver_factory=None) -> str:
    """登录 IXSPY → 进新品增长榜 → 选类目 → 点数据导出 → 等 zip 下完，返回 zip 路径。"""
    from sourcing.collect.aliexpress_api_probe import (
        get_login_token_url, search_category, save_debug_artifacts, ALIEXPRESS_IXSPY_LIST_URL,
    )
    from sourcing.collect.probe_util import should_fail_category

    download_dir = Path(download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)
    for old in download_dir.glob("*"):           # 清空旧文件，确保检测到的是这次下的
        if old.is_file():
            old.unlink()

    token_url = get_login_token_url()
    factory = driver_factory or build_download_driver
    driver = factory(str(download_dir), headless=headless)
    try:
        try:
            driver.get(token_url)
        except Exception:
            print("  [WARN] token 页超时，继续用当前会话")
        time.sleep(6)
        driver.get(ALIEXPRESS_IXSPY_LIST_URL)
        time.sleep(8)
        selected = search_category(driver, category)
        if should_fail_category(category, selected):
            save_debug_artifacts(driver, download_dir, "ixspy_download_category_failed")
            raise RuntimeError(f"类目未选中，已中止以防下错品类: {category!r}")
        _click_export(driver)
        name = _wait_for_download(
            lambda: [p.name for p in download_dir.glob("*")], timeout=timeout)
        return str(download_dir / name)
    finally:
        driver.quit()
```

- [ ] **Step 4: 导入自检 + 全套测试**

Run: `python -c "import sourcing.collect.ixspy_download; print('ok')"`
Expected: `ok`
Run: `python -m pytest -q`
Expected: 全绿（浏览器函数无新测试，纯逻辑测试仍通过）

- [ ] **Step 5: 提交**

```bash
git add src/sourcing/collect/ixspy_download.py
git commit -m "feat: ixspy_download 浏览器下载(登录+选类目+点导出+等下载)"
```

---

## Task 5: CLI 命令 `ixspy-auto`

**Files:**
- Modify: `src/sourcing/cli.py`

- [ ] **Step 1: 注册子命令**

在 `cli.py` 中 `args = parser.parse_args()` 之前，与其它 `platform-export-*` 解析器并列加：

```python
    iad = sub.add_parser("ixspy-auto",
                         help="一键: 自动登录IXSPY下载该品类压缩包 + 双筛 + 报告")
    iad.add_argument("--category", required=True, help="品类中文名, 如 汽车及零配件")
    iad.add_argument("--headless", action="store_true", help="无界面跑Chrome")
    iad.add_argument("--limit", type=int, default=None, help="小样本测试, 如 --limit 30")
    iad.add_argument("--delay", type=float, default=0.1)
    iad.add_argument("--threshold", type=float, default=0.85)
```

- [ ] **Step 2: 加处理分支**

在 `if args.command == "platform-export-run":` 分支**之前**加：

```python
    if args.command == "ixspy-auto":
        import os
        from sourcing.collect.ixspy_download import download_export, _extract_zip
        from sourcing.platform_export_pipeline import run_from_download, default_base_dir
        base = default_base_dir()
        dl_dir = os.path.join(base, "_downloads", "ixspy")
        print(f"[1/3] 下载品类: {args.category} (会弹Chrome自动登录)")
        zip_path = download_export(args.category, download_dir=dl_dir, headless=args.headless)
        print(f"[2/3] 解压: {zip_path}")
        src = _extract_zip(zip_path, os.path.join(base, "_downloads", "ixspy_extract"))
        print("[3/3] 双筛 + 报告")
        result = run_from_download(src, base_dir=base, category_name=args.category,
                                   limit=args.limit, delay_seconds=args.delay,
                                   threshold=args.threshold)
        report_dir = result.get("report_dir", "")
        print(f"[DONE] {args.category} | 匹配 {result.get('final', {}).get('matched')}"
              f"/{result.get('final', {}).get('products')} | 报告: {report_dir}")
        try:
            os.startfile(report_dir)
        except Exception:
            pass
        return
```

- [ ] **Step 3: 导入自检 + help 检查**

Run: `python -c "import sourcing.cli; print('ok')"`
Expected: `ok`
Run: `python -m sourcing.cli ixspy-auto --help`
Expected: 显示 `--category` 等参数

- [ ] **Step 4: 全套测试**

Run: `python -m pytest -q`
Expected: 全绿

- [ ] **Step 5: 提交**

```bash
git add src/sourcing/cli.py
git commit -m "feat: CLI ixspy-auto 一键自动下载+双筛"
```

---

## Task 6: 双击触发（bat → ps1，避免中文编码坑）

**Files:**
- Create: `scripts/ixspy_auto_prompt.ps1`（ASCII 内容；PowerShell 收中文输入无碍）
- Create: `ixspy-自动下载双筛.bat`（ASCII 内容）

- [ ] **Step 1: 写 ps1（用英文提示，避免 PS5.1 读 UTF-8 非ASCII 乱码；中文输入照样收）**

`scripts/ixspy_auto_prompt.ps1`：

```powershell
Set-Location "D:\ProductSourcingSystem"
$env:EMBEDDING_REPO_DIR = "D:\518"
$cat = Read-Host "Enter category name (Chinese OK, e.g. auto parts category)"
if ([string]::IsNullOrWhiteSpace($cat)) {
    Write-Host "No category entered. Exiting."
    Read-Host "Press Enter to close"
    exit 1
}
python -X utf8 -m sourcing.cli ixspy-auto --category "$cat"
Read-Host "Done. Press Enter to close"
```

- [ ] **Step 2: 写 bat（纯 ASCII，调 ps1）**

`ixspy-自动下载双筛.bat`：

```bat
@echo off
chcp 65001 >nul
cd /d D:\ProductSourcingSystem
powershell -NoProfile -ExecutionPolicy Bypass -File "scripts\ixspy_auto_prompt.ps1"
```

- [ ] **Step 3: 校验 ASCII（bat 与 ps1 内容均不含非 ASCII 字节）**

Run:
```bash
python -c "import sys; [print(f, any(b>127 for b in open(f,'rb').read())) for f in ['scripts/ixspy_auto_prompt.ps1']]"
```
Expected: `scripts/ixspy_auto_prompt.ps1 False`
（bat 文件名是中文没关系，关键是**内容**为 ASCII。）

- [ ] **Step 4: 提交**

```bash
git add scripts/ixspy_auto_prompt.ps1 "ixspy-自动下载双筛.bat"
git commit -m "feat: 双击入口 ixspy-自动下载双筛.bat(收品类名)"
```

---

## Task 7: 真实冒烟验证（人工，非自动）

**Files:** 无（手动跑）

- [ ] **Step 1: 小样本真实跑（盯着第一次，非 headless）**

Run（用一个真实品类，先 `--limit 30` 省时）：
```bash
python -X utf8 -m sourcing.cli ixspy-auto --category "汽车及零配件" --limit 30
```
Expected: 弹 Chrome → 自动登录 → 选中"汽车及零配件"类目 → 点数据导出 → `_downloads/ixspy/` 出现 zip → 解压 → 跑双筛 → 打印报告路径并自动打开报告文件夹。

- [ ] **Step 2: 失败路径确认**

Run（故意写错类目）：
```bash
python -X utf8 -m sourcing.cli ixspy-auto --category "不存在的类目xyz" --limit 5
```
Expected: 选类目失败 → 报错退出 + `_downloads/ixspy/` 下留有截图，**不会下错品类**。

- [ ] **Step 3: 双击入口确认**

双击 `ixspy-自动下载双筛.bat` → 输入"汽车及零配件" → 回车 → 同 Step 1 效果。

- [ ] **Step 4: 记录结果**

把冒烟结论（成功/卡在哪）反馈，若 Selenium 选择器需微调，回 Task 4 调整 `_click_export` 的 xpath。

---

## Self-Review

- **Spec 覆盖**：登录下载(Task4)、解压(Task3)、下载完成检测(Task2)、品类名覆盖(Task1)、CLI(Task5)、双击入口(Task6)、错误处理(类目fail-fast在Task4 / 截图)、测试策略(纯逻辑Task1-3单测 + Task7冒烟)、首次发现时间留接口(本期YAGNI，未做参数实现，符合spec"留接口"——`download_export` 可后续加 `filters` 参数)。✅
- **占位扫描**：无 TBD/TODO；每个代码步骤含完整代码。✅
- **类型/签名一致**：`download_export(category, *, download_dir, headless, timeout, driver_factory)`、`_wait_for_download(snapshot,*,timeout,sleep,now)`、`_extract_zip(zip_path,dest_dir)`、`prepare_from_download(...,category_name)`、`run_from_download(...,category_name)` 各 Task 引用一致。✅
- **注意**：`_downloads/` 为运行期数据目录，建议确认其在 `.gitignore`（若未忽略，执行时补一行 `_downloads/`）。
