import json
import os
import time
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

from sourcing.collect.api_common import find_record_lists, product_score, request_json, read_json, write_csv, write_json

load_dotenv()

PROJECT_ROOT = Path(__file__).resolve().parents[3]
PRODUCT_TYPE = os.environ.get("PRODUCT_TYPE", "furniture").strip() or "furniture"
IXSPY_LOGIN_URL = os.environ.get("IXSPY_LOGIN_URL", "https://user.ixspy.com/login")
IXSPY_DATA_URL = os.environ.get("IXSPY_DATA_URL", "https://ixspy.com/data")
ALIEXPRESS_IXSPY_LIST_URL = os.environ.get("ALIEXPRESS_IXSPY_LIST_URL", "https://ixspy.com/data#/product/new-product-grow")
IXSPY_USERNAME = os.environ.get("IXSPY_USERNAME", "")
IXSPY_PASSWORD = os.environ.get("IXSPY_PASSWORD", "")
ALIEXPRESS_CATEGORY_NAME = os.environ.get("ALIEXPRESS_CATEGORY_NAME", os.environ.get("IXSPY_CATEGORY_NAME", ""))
ALIEXPRESS_SCROLL_ROUNDS = int(os.environ.get("ALIEXPRESS_SCROLL_ROUNDS") or 80)
SCRAPER_HEADLESS = os.environ.get("SCRAPER_HEADLESS", "0").lower() in {"1", "true", "yes"}


@dataclass(frozen=True)
class ProjectPaths:
    root_dir: Path
    product_type: str

    @property
    def output_dir(self) -> Path:
        return self.root_dir / "output" / "aliexpress" / self.product_type

    @property
    def candidates_file(self) -> Path:
        return self.output_dir / "aliexpress_api_candidates.json"

    @property
    def requests_file(self) -> Path:
        return self.output_dir / "aliexpress_api_requests.json"

    @property
    def visible_products_file(self) -> Path:
        return self.output_dir / "aliexpress_visible_products.csv"


def build_driver_with_network_logs():
    if not IXSPY_USERNAME or not IXSPY_PASSWORD:
        raise RuntimeError("IXSPY_USERNAME and IXSPY_PASSWORD are required in .env or environment variables")

    from selenium import webdriver
    from selenium.common.exceptions import TimeoutException
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
    driver.TimeoutException = TimeoutException
    driver.set_page_load_timeout(int(os.environ.get("SCRAPER_PAGE_LOAD_TIMEOUT") or 60))
    driver.execute_cdp_cmd("Network.enable", {})
    return driver


def get_login_token_url():
    if not IXSPY_USERNAME or not IXSPY_PASSWORD:
        raise RuntimeError("IXSPY_USERNAME and IXSPY_PASSWORD are required in .env or environment variables")

    payload, _ = request_json(
        "POST",
        IXSPY_LOGIN_URL,
        headers={
            "Content-Type": "application/json",
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
        },
        body=json.dumps(
            {
                "user_name_email": IXSPY_USERNAME,
                "password": IXSPY_PASSWORD,
                "site": "7",
                "toUrl": IXSPY_DATA_URL,
                "redirectUrl": "https://ixspy.com/login",
                "ext_url": "",
            },
            ensure_ascii=False,
        ),
        timeout=60,
    )
    error = payload.get("error") or {}
    if error.get("code") not in (0, "0", None):
        raise RuntimeError(f"IXSPY login failed: {error}")
    token_url = ((payload.get("data") or {}).get("url") or "").strip()
    if not token_url:
        raise RuntimeError("IXSPY login succeeded but no token URL was returned")
    return token_url


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


def search_category(driver, category_name):
    if not category_name:
        print("  [WARN] ALIEXPRESS_CATEGORY_NAME is empty; using current page filters")
        return True

    print(f"[NAV] searching AliExpress category: {category_name}")
    time.sleep(3)
    for _ in range(20):
        loading = driver.execute_script(
            """
            return Array.from(document.querySelectorAll('.el-loading-mask')).some(
                node => node.offsetParent !== null && getComputedStyle(node).display !== 'none'
            );
            """
        )
        if not loading:
            break
        time.sleep(0.5)

    inputs = driver.find_elements("xpath", "//input[@type='text']")
    category_input = None
    for item in inputs:
        try:
            placeholder = item.get_attribute("placeholder") or ""
            if item.is_displayed() and ("类目" in placeholder or "分类" in placeholder):
                category_input = item
                break
        except Exception:
            continue
    if not category_input:
        print("  [WARN] category input not found")
        return False

    driver.execute_script("arguments[0].scrollIntoView({block: 'center'});", category_input)
    driver.execute_script("arguments[0].click();", category_input)
    category_input.clear()
    category_input.send_keys(category_name)
    time.sleep(2)

    clicked = driver.execute_script(
        """
        const keyword = arguments[0];
        const selectors = ['.el-cascader__suggestion-item', '.el-cascader-node__label', 'li', 'span'];
        for (const selector of selectors) {
            for (const node of document.querySelectorAll(selector)) {
                if (node.offsetParent !== null && node.textContent && node.textContent.includes(keyword)) {
                    node.click();
                    return true;
                }
            }
        }
        return false;
        """,
        category_name,
    )
    if not clicked:
        print("  [WARN] category suggestion not clicked")
        return False

    time.sleep(1.5)
    for text in ["搜索", "查询"]:
        buttons = driver.find_elements("xpath", f"//button[.//span[contains(normalize-space(.),'{text}')]]")
        for button in buttons:
            try:
                if button.is_displayed() and button.is_enabled():
                    driver.execute_script("arguments[0].click();", button)
                    print(f"  [OK] clicked {text}")
                    time.sleep(6)
                    return True
            except Exception:
                continue
    print("  [WARN] search button not found")
    return False


def scroll_page(driver):
    for _ in range(max(1, ALIEXPRESS_SCROLL_ROUNDS)):
        driver.execute_script("window.scrollTo(0, document.body.scrollHeight);")
        driver.execute_script(
            """
            const wrap = document.querySelector('.el-scrollbar__wrap');
            if (wrap) wrap.scrollTop = wrap.scrollHeight;
            for (const node of document.querySelectorAll('[class*="scroll"]')) {
                if (node.scrollHeight > node.clientHeight) node.scrollTop = node.scrollHeight;
            }
            """
        )
        time.sleep(1.5)


def extract_visible_products(driver):
    products = []
    rank_elements = driver.find_elements("xpath", "//span[contains(@class,'rank-num')]")
    for rank_element in rank_elements:
        try:
            rank_text = rank_element.text.strip().replace("No.", "").strip()
            rank = int(rank_text) if rank_text.isdigit() else ""
            card = rank_element
            for _ in range(10):
                parent = card.find_element("xpath", "..")
                if len(parent.text or "") > 100:
                    card = parent
                    break
                card = parent

            image_url = ""
            for image in card.find_elements("xpath", ".//img"):
                src = (image.get_attribute("src") or image.get_attribute("data-src") or "").strip()
                if src.startswith("http") and "logo" not in src.lower():
                    image_url = src
                    if "aliexpress-media.com" in src:
                        break

            lines = [line.strip() for line in (card.text or "").splitlines() if line.strip()]
            product_name = ""
            for line in lines:
                if "No." in line or line.startswith("http"):
                    continue
                if len(line) > len(product_name):
                    product_name = line
            if rank or product_name or image_url:
                products.append(
                    {
                        "source_rank": rank,
                        "sku": "",
                        "product_name": product_name,
                        "brand": "",
                        "category": ALIEXPRESS_CATEGORY_NAME,
                        "image_url": image_url,
                        "price": "",
                        "product_url": "",
                    }
                )
        except Exception:
            continue
    return products


def browser_logs(driver):
    try:
        return driver.get_log("performance")
    except Exception as error:
        print(f"[WARN] could not read performance logs: {error}")
        return []


def capture_network_candidates(driver, paths: ProjectPaths):
    requests = {}
    extra_headers = {}
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
        if message.get("method") != "Network.requestWillBeSentExtraInfo":
            continue
        params = message.get("params", {})
        request_id = params.get("requestId")
        if request_id:
            extra_headers[request_id] = params.get("headers", {})

    for request_id, headers in extra_headers.items():
        if request_id not in requests:
            continue
        merged_headers = dict(requests[request_id].get("headers") or {})
        merged_headers.update(headers)
        requests[request_id]["headers"] = merged_headers

    product_requests = [
        request for request in requests.values()
        if any(token in request.get("url", "").lower() for token in ["product", "goods", "item", "ixspy"])
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
        url = item.get("url", "").lower()
        is_product_api = 1 if any(token in url for token in ["product", "goods", "item", "ranking"]) else 0
        return (is_product_api, item["best_product_score"], item["best_record_count"])

    return sorted(candidates, key=priority, reverse=True)


def main():
    paths = ProjectPaths(PROJECT_ROOT, PRODUCT_TYPE)
    paths.output_dir.mkdir(parents=True, exist_ok=True)
    driver = None
    try:
        print("=" * 60)
        print("  AliExpress IXSPY API Probe")
        print("=" * 60)
        token_url = get_login_token_url()
        driver = build_driver_with_network_logs()
        try:
            driver.get(token_url)
        except Exception:
            print("  [WARN] IXSPY token page timed out; continuing with current browser session")
        time.sleep(6)
        driver.get(ALIEXPRESS_IXSPY_LIST_URL)
        time.sleep(8)
        browser_logs(driver)
        if not search_category(driver, ALIEXPRESS_CATEGORY_NAME):
            save_debug_artifacts(driver, paths.output_dir, "aliexpress_api_probe_search_failed")

        scroll_page(driver)
        visible_products = extract_visible_products(driver)
        if visible_products:
            write_csv(
                str(paths.visible_products_file),
                visible_products,
                fields=["source_rank", "sku", "product_name", "brand", "category", "image_url", "price", "product_url"],
            )

        candidates = build_candidates(capture_network_candidates(driver, paths))
        existing = read_json(str(paths.candidates_file), default=[])
        if candidates:
            write_json(str(paths.candidates_file), candidates)
        elif existing:
            print("[WARN] no candidates captured; keeping existing candidates file")
            save_debug_artifacts(driver, paths.output_dir, "aliexpress_api_probe_no_candidates")
            candidates = existing

        print(f"[DONE] saved {len(candidates)} API candidates to {paths.candidates_file}")
        print(f"[DONE] visible products: {len(visible_products)} -> {paths.visible_products_file}")
        for index, candidate in enumerate(candidates[:10], start=1):
            print(
                f"  {index}. score={candidate['best_product_score']} "
                f"count={candidate['best_record_count']} url={candidate['url']}"
            )
    except Exception as error:
        print(f"[ERROR] {error}")
        if driver:
            save_debug_artifacts(driver, paths.output_dir, "aliexpress_api_probe_error")
        raise
    finally:
        if driver:
            driver.quit()


if __name__ == "__main__":
    main()
