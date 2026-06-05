import json
import os
import re
import time

from pathlib import Path
from dataclasses import dataclass

from dotenv import load_dotenv

from sourcing.collect.api_common import find_record_lists, product_score, read_json, write_json

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "xiongzhen").strip() or "xiongzhen"
SEERFAR_URL = os.environ.get("SEERFAR_URL", "https://seerfar.cn/admin/index.html")
PRODUCT_SEARCH_URL = os.environ.get("SEERFAR_PRODUCT_SEARCH_URL", "https://seerfar.cn/admin/product-search.html")
SEERFAR_USERNAME = os.environ.get("SEERFAR_USERNAME", "")
SEERFAR_PASSWORD = os.environ.get("SEERFAR_PASSWORD", "")
SEERFAR_CATEGORY_NAME = os.environ.get("SEERFAR_CATEGORY_NAME", "")
SEERFAR_CATEGORY_SEARCH_KEYWORD = os.environ.get("SEERFAR_CATEGORY_SEARCH_KEYWORD", "")
SCRAPER_HEADLESS = os.environ.get("SCRAPER_HEADLESS", "0").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    product_type: str

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "output" / "seerfar" / self.product_type

    @property
    def candidates_file(self) -> Path:
        return self.output_dir / "seerfar_api_candidates.json"

    @property
    def requests_file(self) -> Path:
        return self.output_dir / "seerfar_api_requests.json"


def parse_category_path(category_name):
    parts = [part.strip() for part in re.split(r"\s*(?:>|/|\\)\s*", str(category_name or ""))]
    return [part for part in parts if part]


def build_driver_with_network_logs():
    if not SEERFAR_USERNAME or not SEERFAR_PASSWORD:
        raise RuntimeError("SEERFAR_USERNAME and SEERFAR_PASSWORD are required in .env or environment variables")

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
    driver.set_page_load_timeout(int(os.environ.get("SCRAPER_PAGE_LOAD_TIMEOUT") or 60))
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


def open_market_page(driver):
    print("[LOGIN] opening Seerfar...")
    driver.get(SEERFAR_URL)
    time.sleep(2)
    fill_first_inputs(driver, [SEERFAR_USERNAME, SEERFAR_PASSWORD])
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

    print("[NAV] opening product search page...")
    driver.get(PRODUCT_SEARCH_URL)
    time.sleep(6)
    click_first(
        driver,
        [
            "//button[contains(@class,'filter-button') and contains(normalize-space(.),'潜力市场')]",
            "//button[contains(normalize-space(.),'潜力市场')]",
            "//*[contains(@class,'filter-button') and contains(normalize-space(.),'潜力')]",
            "//*[contains(normalize-space(.),'潜力市场')]",
        ],
        label="potential market filter",
    )
    time.sleep(3)

    browser_logs(driver)
    category_ok = select_category_and_search(driver, SEERFAR_CATEGORY_NAME)
    time.sleep(8)
    return category_ok


def select_category_and_search(driver, category_name):
    if not category_name:
        print("  [WARN] SEERFAR_CATEGORY_NAME is empty; using current page filters")
        return True
    category_path = parse_category_path(category_name)
    print(f"[NAV] selecting category: {' > '.join(category_path) if category_path else category_name}")

    clicked_category_control = click_first(
        driver,
        [
            "//*[contains(@placeholder,'类目')]",
            "//*[contains(@placeholder,'分类')]",
            "//*[contains(normalize-space(.),'类目选择')]",
            "//*[contains(normalize-space(.),'选择类目')]",
            "//*[contains(normalize-space(.),'全部类目')]",
            "//*[contains(normalize-space(.),'类目')]//input",
        ],
        label="category selector",
    )
    time.sleep(1.5)
    if not clicked_category_control:
        return False

    keyword = SEERFAR_CATEGORY_SEARCH_KEYWORD or (category_path[-1] if category_path else category_name)
    typed = type_category_keyword(driver, keyword)
    time.sleep(1.5)
    clicked_select_all = click_first(
        driver,
        [
            "//*[normalize-space(.)='全选']",
            "//*[contains(normalize-space(.),'全选')]",
        ],
        label="select all category matches",
    )
    if not (typed and clicked_select_all):
        print(f"  [WARN] category input/select-all was not confirmed for {category_name}")
        return False

    clicked_query = click_first(
        driver,
        [
            "//button[contains(normalize-space(.),'查询')]",
            "//button[contains(normalize-space(.),'搜索')]",
            "//button[contains(translate(normalize-space(.),'ABCDEFGHIJKLMNOPQRSTUVWXYZ','abcdefghijklmnopqrstuvwxyz'),'search')]",
        ],
        label="query button",
    )
    return clicked_query


def type_category_keyword(driver, category_name):
    inputs = driver.find_elements("xpath", "//input[contains(@class,'el-cascader__search-input')]")
    if not inputs:
        inputs = driver.find_elements(
            "xpath",
            "//input[contains(@placeholder,'类目') or contains(@placeholder,'分类')]",
        )
    for input_element in inputs:
        try:
            if not input_element.is_enabled():
                continue
            driver.execute_script(
                """
                const input = arguments[0];
                input.style.width = '220px';
                input.focus();
                const setter = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set;
                setter.call(input, '');
                input.dispatchEvent(new Event('input', { bubbles: true }));
                input.dispatchEvent(new Event('change', { bubbles: true }));
                """,
                input_element,
            )
            input_element.send_keys(category_name)
            print(f"  [OK] typed category keyword {category_name}")
            return True
        except Exception:
            continue
    print(f"  [WARN] could not type category keyword {category_name}")
    return False


def browser_logs(driver):
    try:
        return driver.get_log("performance")
    except Exception as error:
        print(f"[WARN] could not read performance logs: {error}")
        return []


def capture_network_candidates(driver, paths: ProjectPaths):
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

    product_requests = [
        request for request in requests.values()
        if "product-report/product/search" in request.get("url", "")
    ]
    if product_requests:
        write_json(str(paths.requests_file), product_requests)

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
        is_product_api = 1 if "product-report/product/search" in item.get("url", "") else 0
        return (is_product_api, item["best_product_score"], item["best_record_count"])

    return sorted(candidates, key=priority, reverse=True)


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    driver = None
    try:
        print("=" * 60)
        print("  Seerfar API Probe")
        print("=" * 60)
        driver = build_driver_with_network_logs()
        opened = open_market_page(driver)
        if not opened:
            save_debug_artifacts(driver, paths.output_dir, "seerfar_api_probe_market_failed")

        candidates = build_candidates(capture_network_candidates(driver, paths))
        existing = read_json(str(paths.candidates_file), default=[])
        if candidates:
            write_json(str(paths.candidates_file), candidates)
        elif existing:
            print("[WARN] no candidates captured; keeping existing candidates file")
            save_debug_artifacts(driver, paths.output_dir, "seerfar_api_probe_no_candidates")
            candidates = existing

        print(f"[DONE] saved {len(candidates)} API candidates to {paths.candidates_file}")
        for index, candidate in enumerate(candidates[:10], start=1):
            print(
                f"  {index}. score={candidate['best_product_score']} "
                f"count={candidate['best_record_count']} url={candidate['url']}"
            )
    except Exception as error:
        print(f"[ERROR] {error}")
        if driver:
            save_debug_artifacts(driver, paths.output_dir, "seerfar_api_probe_error")
        raise
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
