import os
from dotenv import load_dotenv

load_dotenv()


def database_url() -> str:
    url = os.environ.get("DATABASE_URL")
    if not url:
        raise RuntimeError("DATABASE_URL not set (see .env.example)")
    return url


def test_database_url() -> str:
    return os.environ.get("TEST_DATABASE_URL") or database_url()


def input_dir() -> str:
    return os.environ.get("INPUT_DIR", "./input")


def collect_base_dir() -> str:
    return os.environ.get("COLLECT_518_DIR", r"C:\Users\aibp\Desktop\518")


def collect_targets() -> list[tuple[str, str]]:
    """解析 COLLECT_TARGETS，如 'seerfar:xiongzhen,erp:xiongzhen' -> [('seerfar','xiongzhen'),...]"""
    raw = os.environ.get("COLLECT_TARGETS", "")
    targets = []
    for item in raw.split(","):
        item = item.strip()
        if not item:
            continue
        source, _, product_type = item.partition(":")
        if source and product_type:
            targets.append((source, product_type))
    return targets
