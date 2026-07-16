import hashlib
import json
import os
import re
from datetime import datetime
from io import BytesIO
from urllib.parse import quote, unquote
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse, urlsplit, urlunsplit
from urllib.request import Request, urlopen

import imagehash
from PIL import Image, ImageFilter, UnidentifiedImageError


BASE_DIR = os.path.dirname(os.path.abspath(__file__))
CACHE_DIR = os.environ.get("PRODUCT_SOURCING_IMAGE_CACHE_DIR", os.path.join(BASE_DIR, "cache", "images"))
HASH_CACHE_FILE = os.path.join(CACHE_DIR, "image_hashes.json")
ERROR_LOG_FILE = os.path.join(CACHE_DIR, "image_errors.log")
HASH_VERSION = 4


def _url_key(url):
    return hashlib.sha256(str(url).encode("utf-8")).hexdigest()


def _hash_key(url, source, product_type):
    return hashlib.sha256(f"{_safe_source(source)}|{_safe_product_type(product_type)}|{url}".encode("utf-8")).hexdigest()


def _safe_source(source):
    value = str(source or "unknown").strip().lower()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    return cleaned or "unknown"


def _safe_product_type(product_type):
    value = str(product_type or os.environ.get("PRODUCT_TYPE", "default")).strip().lower()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    return cleaned or "default"


def _extension_from_url(url):
    suffix = os.path.splitext(urlparse(str(url)).path)[1].lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp", ".bmp"}:
        return suffix
    return ".jpg"


def _local_image_path(value):
    text = str(value or "").strip().strip('"')
    if not text:
        return ""
    if text.lower().startswith("file://"):
        parsed = urlparse(text)
        text = unquote(parsed.path)
        if os.name == "nt" and text.startswith("/") and re.match(r"^/[a-zA-Z]:", text):
            text = text[1:]
    if os.path.exists(text) and os.path.isfile(text):
        return os.path.abspath(text)
    return ""


def high_res_image_candidates(url):
    text = str(url)
    candidates = []

    replacements = [
        (r"/wc\d+/", "/wc1000/"),
        (r"_(?:\d{2,4})x(?:\d{2,4})(?=\.)", "_1000x1000"),
        (r"_(?:\d{2,4})x(?:\d{2,4})(?=\.[a-zA-Z]+$)", "_1000x1000"),
    ]
    for pattern, replacement in replacements:
        updated = re.sub(pattern, replacement, text)
        if updated != text:
            candidates.append(updated)

    for suffix in ("_350x350.jpg", "_350x350.jpeg", "_350x350.png", "_300x300.jpg"):
        if text.endswith(suffix):
            candidates.append(text[: -len(suffix)] + suffix.replace("350x350", "1000x1000").replace("300x300", "1000x1000"))

    candidates.append(text)
    return list(dict.fromkeys(candidates))


def request_safe_url(url):
    text = str(url or "").strip()
    if not text:
        return text
    parts = urlsplit(text)
    path = quote(parts.path, safe="/%")
    query = quote(parts.query, safe="=&?/%:+,;@")
    return urlunsplit((parts.scheme, parts.netloc, path, query, parts.fragment))


class ImageMatcher:
    def __init__(self, enabled=True, timeout=12, product_type=None):
        self.enabled = enabled
        self.timeout = timeout
        self.product_type = _safe_product_type(product_type)
        self.hash_cache = self._load_hash_cache()

    def _load_hash_cache(self):
        if not os.path.exists(HASH_CACHE_FILE):
            return {}
        try:
            with open(HASH_CACHE_FILE, "r", encoding="utf-8") as file:
                return json.load(file)
        except (json.JSONDecodeError, OSError):
            return {}

    def save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(HASH_CACHE_FILE, "w", encoding="utf-8") as file:
            json.dump(self.hash_cache, file, ensure_ascii=False, indent=2)

    def _log_error(self, url, message):
        os.makedirs(CACHE_DIR, exist_ok=True)
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        with open(ERROR_LOG_FILE, "a", encoding="utf-8") as file:
            file.write(f"[{timestamp}] {url} | {message}\n")

    def _cache_path(self, url, source):
        folder = os.path.join(CACHE_DIR, _safe_source(source), self.product_type)
        os.makedirs(folder, exist_ok=True)
        return os.path.join(folder, _url_key(url) + _extension_from_url(url))

    def download_image(self, url, source):
        local_path = _local_image_path(url)
        if local_path:
            return local_path
        if not url or not str(url).startswith(("http://", "https://")):
            return ""
        path = self._cache_path(url, source)
        refresh = os.environ.get("IMAGE_REFRESH_HIGH_RES", "0").lower() in {"1", "true", "yes"}
        if not refresh and os.path.exists(path) and os.path.getsize(path) > 0:
            return path

        last_error = ""
        for candidate_url in high_res_image_candidates(url):
            request = Request(
                request_safe_url(candidate_url),
                headers={
                    "User-Agent": "Mozilla/5.0",
                    "Accept": "image/avif,image/webp,image/apng,image/svg+xml,image/*,*/*;q=0.8",
                },
            )
            try:
                with urlopen(request, timeout=self.timeout) as response:
                    data = response.read()
                Image.open(BytesIO(data)).verify()
                with open(path, "wb") as file:
                    file.write(data)
                return path
            except (HTTPError, URLError, TimeoutError, OSError, UnidentifiedImageError) as error:
                last_error = f"{candidate_url} -> {error}"
                continue
        self._log_error(url, last_error or "download_failed")
        return ""

    def get_hashes(self, url, source):
        if not self.enabled or not url:
            return None
        key = _hash_key(url, source, self.product_type)
        cached = self.hash_cache.get(key)
        if cached and cached.get("version") == HASH_VERSION:
            return cached
        if cached and cached.get("error") == "hash_failed":
            return None

        path = self.download_image(url, source)
        if not path:
            return None
        try:
            with Image.open(path) as image:
                image = image.convert("RGB")
                edge_image = image.convert("L").filter(ImageFilter.FIND_EDGES)
                hashes = {
                    "version": HASH_VERSION,
                    "url": str(url),
                    "path": path,
                    "phash": str(imagehash.phash(image)),
                    "dhash": str(imagehash.dhash(image)),
                    "ahash": str(imagehash.average_hash(image)),
                    "whash": str(imagehash.whash(image)),
                    "shape_phash": str(imagehash.phash(edge_image)),
                    "shape_dhash": str(imagehash.dhash(edge_image)),
                    "color_histogram": color_histogram(image),
                }
            self.hash_cache[key] = hashes
            return hashes
        except (OSError, UnidentifiedImageError, ValueError) as error:
            self._log_error(url, str(error))
            self.hash_cache[key] = {"url": str(url), "error": "hash_failed"}
            return None

    def compare(self, market_url, erp_url, market_source="seerfar"):
        if not self.enabled:
            return empty_result()
        market_hashes = self.get_hashes(market_url, market_source)
        erp_hashes = self.get_hashes(erp_url, "erp")
        if not market_hashes or not erp_hashes:
            return empty_result()
        return compare_hashes(market_hashes, erp_hashes)


def compare_hashes(market_hashes, erp_hashes):
    appearance_distance = hash_distance(market_hashes, erp_hashes, ("phash", "dhash", "ahash", "whash"))
    shape_distance = hash_distance(market_hashes, erp_hashes, ("shape_phash", "shape_dhash"))
    appearance_score = score_from_distance(appearance_distance, 32)
    shape_score = score_from_distance(shape_distance, 32)
    color_hist_score = histogram_similarity(
        market_hashes.get("color_histogram", []),
        erp_hashes.get("color_histogram", []),
    )
    color_score = float(round(color_hist_score, 2))
    score = round((appearance_score * float(os.getenv("IMAGE_WEIGHT_APPEARANCE", "0.45"))) + (shape_score * float(os.getenv("IMAGE_WEIGHT_SHAPE", "0.35"))) + (color_score * float(os.getenv("IMAGE_WEIGHT_COLOR", "0.20"))), 2)
    return {
        "score": score,
        "distance": float(round(appearance_distance, 2)),
        "appearance_score": appearance_score,
        "shape_score": shape_score,
        "color_score": color_score,
        "color_distance": "",
        "shape_distance": float(round(shape_distance, 2)),
        "reason": (
            f"image_visual:{score:.2f}"
            f"(color:{color_score:.2f},shape:{shape_score:.2f},appearance:{appearance_score:.2f})"
        ),
    }


def empty_result():
    return {
        "score": "",
        "distance": "",
        "appearance_score": "",
        "shape_score": "",
        "color_score": "",
        "color_distance": "",
        "shape_distance": "",
        "reason": "",
    }


def hash_distance(left_hashes, right_hashes, names):
    distances = []
    for name in names:
        left_value = left_hashes.get(name)
        right_value = right_hashes.get(name)
        if not left_value or not right_value:
            continue
        left = imagehash.hex_to_hash(left_value)
        right = imagehash.hex_to_hash(right_value)
        distances.append(float(left - right))
    if not distances:
        return 64.0
    return float(sum(distances) / len(distances))


def score_from_distance(distance, max_distance):
    return float(max(0, min(100, round(100 - distance * 100 / max_distance, 2))))


def color_histogram(image, bins=16):
    image = image.convert("RGB").resize((128, 128))
    raw_histogram = image.histogram()
    grouped = []
    for channel in range(3):
        channel_histogram = raw_histogram[channel * 256 : (channel + 1) * 256]
        bin_size = 256 // bins
        grouped.extend(
            sum(channel_histogram[start : start + bin_size])
            for start in range(0, 256, bin_size)
        )
    total = float(sum(grouped)) or 1.0
    return [round(value / total, 6) for value in grouped]


def histogram_similarity(left, right):
    if not left or not right or len(left) != len(right):
        return 0.0
    return float(round(sum(min(float(a), float(b)) for a, b in zip(left, right)) * 100, 2))
