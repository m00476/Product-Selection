import json
import os
import re
import time
from pathlib import Path

from dotenv import load_dotenv

from sourcing.collect.api_common import find_record_lists, product_score, read_json, write_json
from sourcing.collect.erp_api_fetch import ProjectPaths

load_dotenv()

PROJECT_ROOT = Path(os.environ.get("COLLECT_OUTPUT_ROOT") or Path(__file__).resolve().parents[3])
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "xiongzhen").strip() or "xiongzhen"
ERP_URL = os.environ.get("ERP_URL", "http://103.198.125.2:8077/")
ERP_USERNAME = os.environ.get("ERP_USERNAME", "")
ERP_PASSWORD = os.environ.get("ERP_PASSWORD", "")
SCRAPER_HEADLESS = os.environ.get("SCRAPER_HEADLESS", "0").lower() in {"1", "true", "yes"}


def env_int(name, default):
    value = os.environ.get(name)
    if value in (None, ""):
        return default
    try:
        return int(value)
    except ValueError:
        return default


def parse_category_path(category_name):
    parts = [part.strip() for part in re.split(r"\s*(?:>|/|\\)\s*", str(category_name or ""))]
    return [part for part in parts if part]


def build_driver_with_network_logs():
    if not ERP_USERNAME or not ERP_PASSWORD:
        raise RuntimeError("ERP_USERNAME and ERP_PASSWORD are required in .env or environment variables")

    from selenium import webdriver
    from selenium.webdriver.chrome.options import Options
    from selenium.webdriver.chrome.service import Service
    from webdriver_manager.chrome import ChromeDriverManager

    options = Options()
    if SCRAPER_HEADLESS:
        options.add_argument("--headless=new")
        options.add_argument("--window-size=1440,1000")
    else:
        options.add_argument("--start-maximized")
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--disable-dev-shm-usage")
    options.add_argument("--no-sandbox")
    options.set_capability("goog:loggingPrefs", {"performance": "ALL"})

    driver_path = os.environ.get("CHROMEDRIVER_PATH", r"C:\Users\aibp\chromedriver\chromedriver-win64\chromedriver.exe")
    if os.path.exists(driver_path):
        service = Service(driver_path)
    else:
        service = Service(ChromeDriverManager().install())

    driver = webdriver.Chrome(service=service, options=options)
    driver.set_page_load_timeout(env_int("SCRAPER_PAGE_LOAD_TIMEOUT", 60))
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def click_first(driver, xpaths, label=""):
    for xpath in xpaths:
        try:
            elements = driver.find_elements("xpath", xpath)
            for element in elements:
                if element.is_displayed() and element.is_enabled():
                    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", element)
                    time.sleep(0.2)
                    driver.execute_script("arguments[0].click();", element)
                    if label:
                        print(f"  [OK] clicked {label}")
                    return True
        except Exception:
            continue
    if label:
        print(f"  [WARN] could not click {label}")
    return False


def fill_first_inputs(driver, values):
    inputs = driver.find_elements("xpath", "//input")
    for index, value in enumerate(values):
        if index >= len(inputs):
            return False
        inputs[index].clear()
        inputs[index].send_keys(value)
    return True


def save_debug_artifacts(driver, output_dir: Path, prefix):
    output_dir.mkdir(parents=True, exist_ok=True)
    stamp = time.strftime("%Y%m%d_%H%M%S")
    html_path = output_dir / f"{prefix}_{stamp}.html"
    screenshot_path = output_dir / f"{prefix}_{stamp}.png"
    html_path.write_text(driver.page_source, encoding="utf-8")
    try:
        driver.save_screenshot(str(screenshot_path))
    except Exception:
        screenshot_path = None
    print(f"  [DEBUG] saved page: {html_path}")
    if screenshot_path:
        print(f"  [DEBUG] saved screenshot: {screenshot_path}")


def login_and_open_product_list(driver):
    print("[LOGIN] opening ERP...")
    driver.get(ERP_URL)
    time.sleep(2)
    fill_first_inputs(driver, [ERP_USERNAME, ERP_PASSWORD])
    click_first(
        driver,
        [
            "//button[contains(normalize-space(.),'登录')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'login')]",
            "//input[@type='submit']",
        ],
        label="login button",
    )
    time.sleep(5)

    for attempt in range(1, 4):
        print(f"[NAV] opening product list, attempt {attempt}...")
        product_menu = click_first(
            driver,
            [
                "//span[contains(normalize-space(.),'商品管理')]",
                "//li[contains(normalize-space(.),'商品管理')]",
                "//div[contains(normalize-space(.),'商品管理')]",
                "//*[contains(normalize-space(.),'ERP-商品管理')]",
            ],
            label="product management menu",
        )
        time.sleep(1.5)
        product_list = click_first(
            driver,
            [
                "//li[normalize-space(.)='产品列表']",
                "//span[normalize-space(.)='产品列表']",
                "//*[contains(normalize-space(.),'产品列表')]",
            ],
            label="product list menu",
        )
        time.sleep(6)
        if product_menu and product_list:
            return True
        driver.refresh()
        time.sleep(5)
    return False


def browser_logs(driver):
    try:
        return driver.get_log("performance")
    except Exception as error:
        print(f"[WARN] could not read performance logs: {error}")
        return []


def capture_network_candidates(driver):
    requests = {}
    responses = {}
    logs = browser_logs(driver)

    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if message.get("method") != "Network.requestWillBeSent":
            continue
        params = message.get("params", {})
        request = params.get("request", {})
        request_id = params.get("requestId")
        if request_id:
            requests[request_id] = {
                "method": request.get("method", "GET"),
                "url": request.get("url", ""),
                "headers": request.get("headers", {}),
                "postData": request.get("postData", ""),
            }

    for entry in logs:
        try:
            message = json.loads(entry["message"])["message"]
        except Exception:
            continue
        if message.get("method") != "Network.responseReceived":
            continue
        params = message.get("params", {})
        response = params.get("response", {})
        request_id = params.get("requestId")
        mime_type = response.get("mimeType", "")
        if not request_id or "json" not in mime_type.lower():
            continue
        try:
            body = driver.execute_cdp_cmd("Network.getResponseBody", {"requestId": request_id})
            text = body.get("body", "")
            parsed = json.loads(text)
        except Exception:
            continue

        record_lists = []
        for item in find_record_lists(parsed):
            records = item["records"]
            record_lists.append(
                {
                    "path": item["path"],
                    "count": len(records),
                    "product_score": product_score(records),
                    "sample": records[:2],
                }
            )

        responses[request_id] = {
            "url": response.get("url", ""),
            "status": response.get("status"),
            "mimeType": mime_type,
            "headers": response.get("headers", {}),
            "record_lists": record_lists,
            "body_sample": text[:1000],
            "request": requests.get(request_id, {}),
        }
    return responses


def build_candidates(responses):
    candidates = []
    for response in responses.values():
        best_list = max(response["record_lists"], key=lambda x: x["product_score"], default=None)
        if not best_list or best_list["product_score"] <= 0:
            continue
        candidates.append(
            {
                "url": response["url"],
                "status": response["status"],
                "mimeType": response["mimeType"],
                "best_record_path": best_list["path"],
                "best_record_count": best_list["count"],
                "best_product_score": best_list["product_score"],
                "record_lists": response["record_lists"],
                "body_sample": response["body_sample"],
                "request": response["request"],
            }
        )

    def priority(item):
        is_product_api = 1 if "Api/proudect/list" in item.get("url", "") else 0
        return (is_product_api, item["best_product_score"], item["best_record_count"])

    return sorted(candidates, key=priority, reverse=True)


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    driver = None
    try:
        print("=" * 60)
        print("  ERP API Probe")
        print("=" * 60)
        driver = build_driver_with_network_logs()
        nav_ok = login_and_open_product_list(driver)
        if not nav_ok:
            save_debug_artifacts(driver, paths.output_dir, "erp_api_probe_nav_failed")

        click_first(
            driver,
            [
                "//button[contains(@class,'btn-next') and not(@disabled)]",
                "//li[contains(@class,'next') and not(contains(@class,'disabled'))]/a",
            ],
            label="next page",
        )
        time.sleep(4)

        candidates = build_candidates(capture_network_candidates(driver))
        has_product_api = any("Api/proudect/list" in item["url"] for item in candidates)
        existing = read_json(str(paths.candidates_file), default=[])
        existing_has_product_api = any("Api/proudect/list" in item.get("url", "") for item in existing)
        if candidates and (has_product_api or not existing_has_product_api):
            write_json(str(paths.candidates_file), candidates)
        elif existing_has_product_api:
            print("[WARN] no product API captured; keeping existing product candidates file")
            candidates = existing
        else:
            write_json(str(paths.candidates_file), candidates)

        print(f"[DONE] saved {len(candidates)} API candidates to {paths.candidates_file}")
        for index, candidate in enumerate(candidates[:10], start=1):
            print(
                f"  {index}. score={candidate['best_product_score']} "
                f"count={candidate['best_record_count']} url={candidate['url']}"
            )
    except Exception as error:
        print(f"[ERROR] {error}")
        if driver:
            save_debug_artifacts(driver, paths.output_dir, "erp_api_probe_error")
        raise
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
