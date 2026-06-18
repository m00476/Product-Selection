"""IXSPY 自动下载：登录 → 选类目 → 点数据导出 → 等 zip → 解压。方案1(模拟点击)。"""
import os
import time
import zipfile
from pathlib import Path


def _wait_for_download(snapshot, *, timeout: float, ext: str = ".zip",
                       sleep=time.sleep, now=time.monotonic) -> str:
    """轮询下载目录文件名列表，等到出现指定后缀文件且无 .crdownload 即完成，返回该文件名。
    snapshot() -> list[str] 当前目录文件名；超时抛 TimeoutError。"""
    deadline = now() + timeout
    while now() < deadline:
        names = list(snapshot())
        downloading = any(n.lower().endswith(".crdownload") for n in names)
        done = [n for n in names if n.lower().endswith(ext)]
        if done and not downloading:
            return done[0]
        sleep(1.0)
    raise TimeoutError(f"下载超时：未在限定时间内得到完整的 {ext} 文件")


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


def _click_url_export(driver) -> None:
    """点击"数据导出(仅含图片URL)"项。它瞬间下一个含完整图片URL的 .xls(无需等客户端打包)。
    找不到则抛错。"""
    xpaths = [
        "//*[starts-with(@id,'export_') and contains(normalize-space(.), '仅含图片URL')]",
        "//*[contains(normalize-space(.), '仅含图片URL')]",
    ]
    for xpath in xpaths:
        for element in driver.find_elements("xpath", xpath):
            try:
                if not element.is_displayed():
                    continue
                driver.execute_script("arguments[0].scrollIntoView({block:'center'});", element)
                try:
                    element.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", element)
                return
            except Exception:
                continue
    raise RuntimeError("找不到'数据导出(仅含图片URL)'项，页面可能改版，请人工确认")


def download_export(category: str, *, download_dir: str, headless: bool = False,
                    timeout: float = 120, driver_factory=None) -> str:
    """登录 IXSPY → 进新品增长榜 → 选类目 → 点"仅含图片URL"导出 → 等 xls 下完，返回 xls 路径。
    用URL版导出(秒下、含完整图片URL)，而非压缩包版(客户端逐张下图打包,慢且按钮难点)。"""
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
        time.sleep(3)  # 等导出按钮就绪
        _click_url_export(driver)
        name = _wait_for_download(
            lambda: [p.name for p in download_dir.glob("*")], timeout=timeout, ext=".xls")
        return str(download_dir / name)
    finally:
        driver.quit()
