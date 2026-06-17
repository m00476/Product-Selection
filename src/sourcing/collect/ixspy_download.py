"""IXSPY 自动下载：登录 → 选类目 → 点数据导出 → 等 zip → 解压。方案1(模拟点击)。"""
import os
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


def _extract_zip(zip_path: str, dest_dir: str) -> str:
    """解压 zip 到 dest_dir(先清空)，返回 dest_dir。"""
    import shutil
    dest = Path(dest_dir)
    if dest.exists():
        shutil.rmtree(dest)
    dest.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(zip_path) as archive:
        archive.extractall(dest)
    return str(dest)


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
