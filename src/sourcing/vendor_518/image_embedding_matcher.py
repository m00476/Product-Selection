import hashlib
import os
import pickle

import numpy as np
import torch
from PIL import Image, ImageOps, UnidentifiedImageError

from .image_matcher import CACHE_DIR, ImageMatcher


DEFAULT_MODEL_NAME = "dinov2_vitl14"
MODEL_NAME = os.environ.get("IMAGE_EMBEDDING_MODEL", DEFAULT_MODEL_NAME).strip() or DEFAULT_MODEL_NAME
EMBEDDING_VERSION = 3
EMBEDDING_CACHE_FILE = os.path.join(CACHE_DIR, "image_embeddings.pkl")


def _safe_source(source):
    value = str(source or "unknown").strip().lower()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    return cleaned or "unknown"


def _safe_product_type(product_type):
    value = str(product_type or os.environ.get("PRODUCT_TYPE", "default")).strip().lower()
    cleaned = "".join(char if char.isalnum() or char in {"_", "-"} else "_" for char in value)
    return cleaned or "default"


def _embedding_key(url, source, product_type, model_name):
    raw = f"{EMBEDDING_VERSION}|{model_name}|{_safe_source(source)}|{_safe_product_type(product_type)}|{url}"
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


class ImageEmbeddingMatcher:
    def __init__(self, enabled=True, timeout=8, device=None, product_type=None):
        self.enabled = enabled
        self.timeout = timeout
        self.product_type = _safe_product_type(product_type)
        self.model_name = os.environ.get("IMAGE_EMBEDDING_MODEL", MODEL_NAME).strip() or MODEL_NAME
        self.device = device or ("cuda" if torch.cuda.is_available() else "cpu")
        self.downloader = ImageMatcher(enabled=enabled, timeout=timeout, product_type=self.product_type)
        self.model = None
        self.cache = self._load_cache()

    def _load_cache(self):
        if not os.path.exists(EMBEDDING_CACHE_FILE):
            return {}
        try:
            with open(EMBEDDING_CACHE_FILE, "rb") as file:
                return pickle.load(file)
        except (OSError, pickle.PickleError, EOFError):
            return {}

    def save(self):
        os.makedirs(CACHE_DIR, exist_ok=True)
        with open(EMBEDDING_CACHE_FILE, "wb") as file:
            pickle.dump(self.cache, file, protocol=pickle.HIGHEST_PROTOCOL)
        self.downloader.save()

    def _load_model(self):
        if self.model is not None:
            return self.model
        repo = os.path.expanduser("~/.cache/torch/hub/facebookresearch_dinov2_main")
        if not os.path.exists(repo):
            raise RuntimeError("DINOv2 repo cache not found. Cannot load image embedding model offline.")
        self.model = torch.hub.load(repo, self.model_name, source="local", pretrained=True)
        self.model.eval().to(self.device)
        return self.model

    def _prepare_image(self, path):
        with Image.open(path) as image:
            image = ImageOps.exif_transpose(image).convert("RGB")
            width, height = image.size
            if width <= 0 or height <= 0:
                raise ValueError("invalid image size")
            if width < height:
                new_width = 256
                new_height = round(height * 256 / width)
            else:
                new_height = 256
                new_width = round(width * 256 / height)
            image = image.resize((new_width, new_height), Image.Resampling.BICUBIC)
            left = max((new_width - 224) // 2, 0)
            top = max((new_height - 224) // 2, 0)
            image = image.crop((left, top, left + 224, top + 224))
        array = np.asarray(image).astype("float32") / 255.0
        mean = np.array([0.485, 0.456, 0.406], dtype="float32")
        std = np.array([0.229, 0.224, 0.225], dtype="float32")
        array = (array - mean) / std
        tensor = torch.from_numpy(array).permute(2, 0, 1).unsqueeze(0)
        return tensor.to(self.device)

    def get_embedding(self, url, source):
        if not self.enabled or not url:
            return None
        key = _embedding_key(url, source, self.product_type, self.model_name)
        cached = self.cache.get(key)
        if cached is not None:
            return cached

        path = self.downloader.download_image(url, source)
        if not path:
            return None
        try:
            model = self._load_model()
            tensor = self._prepare_image(path)
            with torch.inference_mode():
                embedding = model(tensor).detach().cpu().numpy().reshape(-1).astype("float32")
            norm = float(np.linalg.norm(embedding))
            if norm <= 0:
                return None
            embedding = embedding / norm
            self.cache[key] = embedding
            return embedding
        except (OSError, UnidentifiedImageError, RuntimeError, ValueError) as error:
            self.downloader._log_error(url, f"embedding_failed: {error}")
            return None

    def build_index(self, rows, source, url_column="image_url", save_every=200):
        items = []
        vectors = []
        total = len(rows)
        for pos, (idx, row) in enumerate(rows.iterrows(), start=1):
            embedding = self.get_embedding(row[url_column], source)
            if embedding is not None:
                items.append((pos - 1, idx))
                vectors.append(embedding)
            if save_every > 0 and pos % save_every == 0:
                self.save()
                print(f"  {source} embedding cache prepared: {pos}/{total}")
        self.save()
        if not vectors:
            return items, np.empty((0, 0), dtype="float32")
        return items, np.vstack(vectors).astype("float32")

    def top_matches(self, url, source, index_items, index_vectors, top_n):
        if index_vectors.size == 0:
            return []
        query = self.get_embedding(url, source)
        if query is None:
            return []
        scores = index_vectors @ query
        top_n = min(top_n, len(scores))
        if top_n <= 0:
            return []
        top_positions = np.argpartition(scores, -top_n)[-top_n:]
        ordered = top_positions[np.argsort(scores[top_positions])[::-1]]
        results = []
        for vector_pos in ordered:
            e_pos, e_idx = index_items[int(vector_pos)]
            score = float(max(0.0, min(100.0, round(float(scores[int(vector_pos)]) * 100, 2))))
            results.append((score, e_pos, e_idx))
        return results
