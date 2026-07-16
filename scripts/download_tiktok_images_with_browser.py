import argparse
import csv
import hashlib
import mimetypes
import time
from pathlib import Path

from selenium import webdriver
from selenium.webdriver.chrome.options import Options


def _safe_ext(content_type: str, url: str) -> str:
    guessed = mimetypes.guess_extension((content_type or "").split(";")[0].strip())
    if guessed in {".jpe"}:
        guessed = ".jpg"
    if guessed:
        return guessed
    suffix = Path(url.split("?", 1)[0]).suffix.lower()
    return suffix if suffix in {".jpg", ".jpeg", ".png", ".webp"} else ".jpg"


def _read_rows(path: Path) -> list[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        return list(csv.DictReader(file))


def _write_rows(path: Path, rows: list[dict], fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _make_driver() -> webdriver.Chrome:
    options = Options()
    options.add_argument("--headless=new")
    options.add_argument("--disable-gpu")
    options.add_argument("--window-size=900,900")
    options.add_argument(
        "--user-agent=Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/126.0 Safari/537.36"
    )
    return webdriver.Chrome(options=options)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--input-csv", required=True)
    parser.add_argument("--output-csv", required=True)
    parser.add_argument("--image-dir", required=True)
    parser.add_argument("--limit", type=int, default=None)
    parser.add_argument("--delay", type=float, default=0.2)
    parser.add_argument("--overwrite", action="store_true")
    args = parser.parse_args()

    input_csv = Path(args.input_csv)
    output_csv = Path(args.output_csv)
    image_dir = Path(args.image_dir)
    image_dir.mkdir(parents=True, exist_ok=True)

    rows = _read_rows(input_csv)
    if args.limit is not None:
        rows = rows[: args.limit]

    fieldnames = list(rows[0].keys()) if rows else []
    for field in ["local_image_path", "browser_image_status", "browser_image_error"]:
        if field not in fieldnames:
            fieldnames.append(field)

    driver = _make_driver()
    ok = 0
    failed = 0
    try:
        for index, row in enumerate(rows, start=1):
            image_url = (row.get("image_url") or "").strip()
            sku = (row.get("sku") or str(index)).strip()
            digest = hashlib.sha1(image_url.encode("utf-8")).hexdigest()[:12]
            base_name = f"{sku}_{digest}"
            existing = next(image_dir.glob(base_name + ".*"), None)
            if existing and not args.overwrite:
                row["local_image_path"] = str(existing)
                row["browser_image_status"] = "cached"
                ok += 1
                continue
            try:
                driver.get(image_url)
                result = driver.execute_async_script(
                    """
                    const done = arguments[arguments.length - 1];
                    fetch(arguments[0], {credentials: 'include'})
                      .then(resp => resp.arrayBuffer().then(buf => ({
                        ok: resp.ok,
                        status: resp.status,
                        contentType: resp.headers.get('content-type') || '',
                        bytes: Array.from(new Uint8Array(buf))
                      })))
                      .then(done)
                      .catch(err => done({ok: false, status: 0, error: String(err), bytes: []}));
                    """,
                    image_url,
                )
                if not result.get("ok") or not result.get("bytes"):
                    raise RuntimeError(f"status={result.get('status')} error={result.get('error', '')}")
                ext = _safe_ext(result.get("contentType", ""), image_url)
                path = image_dir / f"{base_name}{ext}"
                path.write_bytes(bytes(result["bytes"]))
                row["local_image_path"] = str(path)
                row["browser_image_status"] = "success"
                row["browser_image_error"] = ""
                ok += 1
            except Exception as error:
                row["local_image_path"] = ""
                row["browser_image_status"] = "error"
                row["browser_image_error"] = f"{type(error).__name__}: {error}"
                failed += 1
            if index % 25 == 0:
                print(f"processed={index} ok={ok} failed={failed}", flush=True)
            if args.delay > 0:
                time.sleep(args.delay)
    finally:
        driver.quit()

    _write_rows(output_csv, rows, fieldnames)
    print({"input": str(input_csv), "output": str(output_csv), "rows": len(rows), "ok": ok, "failed": failed})


if __name__ == "__main__":
    main()
