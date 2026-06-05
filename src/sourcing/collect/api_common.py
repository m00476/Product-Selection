import csv
import json
import os
from datetime import datetime
from http.cookiejar import CookieJar
from urllib.parse import urlencode
from urllib.request import HTTPCookieProcessor, Request, build_opener


def read_json(path, default=None):
    if not os.path.exists(path):
        return default
    with open(path, "r", encoding="utf-8") as file:
        return json.load(file)


def write_json(path, data):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as file:
        json.dump(data, file, ensure_ascii=False, indent=2)


def write_csv(path, rows, fields=None):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    if fields is None:
        fields = []
        seen = set()
        for row in rows:
            for key in row:
                if key not in seen:
                    seen.add(key)
                    fields.append(key)

    output_path = path
    try:
        file = open(output_path, "w", encoding="utf-8-sig", newline="")
    except PermissionError:
        base, ext = os.path.splitext(path)
        output_path = f"{base}_{datetime.now().strftime('%Y%m%d_%H%M%S')}{ext}"
        print(f"[WARN] CSV is locked; writing to {output_path}")
        file = open(output_path, "w", encoding="utf-8-sig", newline="")

    with file:
        writer = csv.DictWriter(file, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)
    return output_path


def request_json(method, url, headers=None, body=None, params=None, timeout=60):
    if params:
        separator = "&" if "?" in url else "?"
        url = f"{url}{separator}{urlencode(params)}"

    data = None
    if isinstance(body, str):
        data = body.encode("utf-8")
    elif isinstance(body, bytes):
        data = body

    request = Request(url, data=data, method=method.upper())
    for key, value in (headers or {}).items():
        if key.startswith(":"):
            continue
        if key.lower() in {"host", "content-length", "connection", "accept-encoding"}:
            continue
        request.add_header(key, value)

    opener = build_opener(HTTPCookieProcessor(CookieJar()))
    with opener.open(request, timeout=timeout) as response:
        raw = response.read()
        text = raw.decode("utf-8", errors="replace")
        return json.loads(text), dict(response.headers)


def flatten_product_record(record):
    if not isinstance(record, dict):
        return {}

    sku_keys = ["sku", "SKU", "skuCode", "productSku", "goodsSku", "spu", "code"]
    name_keys = [
        "product_name", "productName", "goodsName", "namecn", "nameCn", "namecnn",
        "nameen", "nameEn", "name", "title", "cnName",
    ]
    category_keys = [
        "category", "categoryName", "catalogName", "cataloguename", "cataloguename2",
        "firstname", "secondname", "thirdname", "fourthname", "className", "typeName",
    ]
    image_keys = [
        "image_url", "imageUrl", "mainImage", "mainImg", "pic3", "pic1", "pic2",
        "picUrl", "imgUrl", "url",
    ]

    def first_value(keys):
        for key in keys:
            value = record.get(key)
            if value not in (None, ""):
                return str(value)
        return ""

    return {
        "sku": first_value(sku_keys),
        "product_name": first_value(name_keys),
        "category": first_value(category_keys),
        "image_url": first_value(image_keys),
    }


def find_record_lists(value, path="root"):
    lists = []
    if isinstance(value, list):
        dict_items = [item for item in value if isinstance(item, dict)]
        if dict_items:
            lists.append({"path": path, "records": dict_items})
        for index, item in enumerate(value[:5]):
            lists.extend(find_record_lists(item, f"{path}[{index}]"))
    elif isinstance(value, dict):
        for key, item in value.items():
            lists.extend(find_record_lists(item, f"{path}.{key}"))
    return lists


def product_score(records):
    score = 0
    for record in records[:20]:
        flattened = flatten_product_record(record)
        score += sum(1 for value in flattened.values() if value)
    return score
