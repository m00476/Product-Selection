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
