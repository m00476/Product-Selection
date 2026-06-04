# 数据底座（Ingestion Foundation）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 把 `input/<source>/<product_type>/*.csv`（Seerfar / IXSPY / ERP 的 fetch 产物）读入 PostgreSQL：原始层 append-only 存档、标准层归一化、竞品多源按 `(platform, platform_product_id)` 做确定关联。

**Architecture:** 纯 Python 管道，分层清晰：`urls`（URL 规范化纯函数）→ `contracts`（数据契约 dataclass）→ `readers`（各源 CSV → 契约）→ `db`（连接+迁移）→ `repository`（写 raw/标准层/关联）→ `cli`（编排导入）。数据库为 PostgreSQL，迁移用纯 SQL 文件。不涉及 Selenium、利润、看板（后续 Plan）。

**Tech Stack:** Python 3.12、psycopg 3、pytest、python-dotenv、PostgreSQL 16、Docker Compose（DB + Metabase 占位）。

参考设计文档：`docs/superpowers/specs/2026-06-04-product-sourcing-system-design.md`（§2.1 取数、§4 数据模型、§4.1 归一化）。

---

## File Structure

```
D:\ProductSourcingSystem\
  docker-compose.yml              # postgres + metabase
  .env.example                    # 配置样例（无真实值）
  .gitignore
  pyproject.toml                  # 依赖与 pytest 配置
  migrations/
    001_raw_and_ops.sql           # raw_source_records + 运维表
    002_standard_and_analysis.sql # products/快照/关联/分析表
  src/sourcing/
    __init__.py
    config.py                     # 读 .env，DATABASE_URL 等
    urls.py                       # URL 规范化（纯函数）
    contracts.py                  # NormalizedProduct / PriceSnapshot / SalesSnapshot
    db.py                         # 连接 + 迁移运行器
    readers/
      __init__.py
      common.py                   # CSV 读取 + 安全数值转换
      seerfar.py                  # Seerfar CSV → 契约
      ixspy.py                    # IXSPY/AliExpress CSV → 契约
      erp.py                      # ERP CSV → 契约（自家商品）
    repository.py                 # 写 raw / 标准层 / source_product_links
    importer.py                   # 单源导入编排
    cli.py                        # 命令行入口
  tests/
    conftest.py                   # DB fixture（临时 schema + 迁移）
    test_urls.py
    test_contracts.py
    test_readers_seerfar.py
    test_readers_ixspy.py
    test_readers_erp.py
    test_repository_raw.py
    test_repository_standard.py
    test_repository_linking.py
    test_importer.py
    fixtures/                     # 小份样例 CSV
      seerfar_sample.csv
      ixspy_sample.csv
      erp_sample.csv
```

**单元边界**：`urls` 与 `contracts` 是无依赖纯逻辑（最易测）；`readers` 只依赖 `contracts`；`repository` 只依赖 `db`+`contracts`；`importer`/`cli` 组合上述。DB 相关测试走真实 PostgreSQL（临时 schema），纯函数测试无需 DB。

---

## Task 1: 项目脚手架与 Docker Compose

**Files:**
- Create: `pyproject.toml`, `.gitignore`, `.env.example`, `docker-compose.yml`, `src/sourcing/__init__.py`, `tests/__init__.py`

- [ ] **Step 1: 创建 `pyproject.toml`**

```toml
[project]
name = "sourcing"
version = "0.1.0"
requires-python = ">=3.12"
dependencies = [
    "psycopg[binary]>=3.2",
    "python-dotenv>=1.0",
]

[project.optional-dependencies]
dev = ["pytest>=8.0"]

[tool.pytest.ini_options]
testpaths = ["tests"]
addopts = "-v"

[build-system]
requires = ["setuptools>=68"]
build-backend = "setuptools.build_meta"

[tool.setuptools.packages.find]
where = ["src"]
```

- [ ] **Step 2: 创建 `.gitignore`**

```gitignore
__pycache__/
*.pyc
.env
.venv/
venv/
input/
output/
*.egg-info/
.pytest_cache/
```

- [ ] **Step 3: 创建 `.env.example`（仅键名，无真实值）**

```text
# PostgreSQL（与 docker-compose 一致）
DATABASE_URL=postgresql://sourcing:sourcing@localhost:5432/sourcing
# 测试库（可与上面同实例不同库；测试会建临时 schema）
TEST_DATABASE_URL=postgresql://sourcing:sourcing@localhost:5432/sourcing
# 采集产物根目录（CSV 所在）
INPUT_DIR=./input
```

- [ ] **Step 4: 创建 `docker-compose.yml`**

```yaml
services:
  postgres:
    image: postgres:16
    environment:
      POSTGRES_USER: sourcing
      POSTGRES_PASSWORD: sourcing
      POSTGRES_DB: sourcing
    ports:
      - "5432:5432"
    volumes:
      - pgdata:/var/lib/postgresql/data
  metabase:
    image: metabase/metabase:latest
    ports:
      - "3000:3000"
    depends_on:
      - postgres
volumes:
  pgdata:
```

- [ ] **Step 5: 创建空包文件**

`src/sourcing/__init__.py` 和 `tests/__init__.py` 内容均为空。

- [ ] **Step 6: 启动 DB 并安装依赖**

Run:
```powershell
docker compose up -d postgres
pip install -e ".[dev]"
```
Expected: postgres 容器运行；`pip` 安装成功。

- [ ] **Step 7: Commit**

```bash
git add pyproject.toml .gitignore .env.example docker-compose.yml src tests
git commit -m "chore: scaffold sourcing project + docker compose"
```

---

## Task 2: 配置与数据库连接 + 迁移运行器

**Files:**
- Create: `src/sourcing/config.py`, `src/sourcing/db.py`, `tests/conftest.py`

- [ ] **Step 1: 创建 `src/sourcing/config.py`**

```python
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
```

- [ ] **Step 2: 创建 `src/sourcing/db.py`（连接 + 迁移）**

```python
import os
import psycopg

MIGRATIONS_DIR = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "migrations")


def connect(dsn: str) -> psycopg.Connection:
    return psycopg.connect(dsn, autocommit=False)


def migration_files() -> list[str]:
    names = [f for f in os.listdir(MIGRATIONS_DIR) if f.endswith(".sql")]
    return [os.path.join(MIGRATIONS_DIR, n) for n in sorted(names)]


def run_migrations(conn: psycopg.Connection) -> None:
    for path in migration_files():
        with open(path, "r", encoding="utf-8") as fh:
            sql = fh.read()
        with conn.cursor() as cur:
            cur.execute(sql)
    conn.commit()
```

- [ ] **Step 3: 创建 `tests/conftest.py`（每次测试用临时 schema，跑迁移）**

```python
import uuid
import psycopg
import pytest
from sourcing import config, db


@pytest.fixture()
def conn():
    schema = "test_" + uuid.uuid4().hex[:12]
    connection = psycopg.connect(config.test_database_url(), autocommit=False)
    with connection.cursor() as cur:
        cur.execute(f'CREATE SCHEMA "{schema}"')
        cur.execute(f'SET search_path TO "{schema}"')
    connection.commit()
    db.run_migrations(connection)
    try:
        yield connection
    finally:
        connection.rollback()
        with connection.cursor() as cur:
            cur.execute(f'DROP SCHEMA "{schema}" CASCADE')
        connection.commit()
        connection.close()
```

> 注意：`run_migrations` 在已设置 `search_path` 的连接上执行，迁移 SQL 不写死 schema 名，故落到临时 schema。

- [ ] **Step 4: 占位迁移以便 conftest 可运行**

创建 `migrations/001_raw_and_ops.sql`，先放一行注释（Task 3 填充真实内容）：

```sql
-- placeholder, filled in Task 3
SELECT 1;
```

- [ ] **Step 5: 冒烟测试 conftest**

创建 `tests/test_smoke.py`：

```python
def test_db_fixture_works(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT 1")
        assert cur.fetchone()[0] == 1
```

Run: `pytest tests/test_smoke.py -v`
Expected: PASS（确认能连库、建/删临时 schema）。

- [ ] **Step 6: Commit**

```bash
git add src/sourcing/config.py src/sourcing/db.py tests/conftest.py migrations/001_raw_and_ops.sql tests/test_smoke.py
git commit -m "feat: db connection, migration runner, test schema fixture"
```

---

## Task 3: 迁移 001 — 原始层与运维层

**Files:**
- Modify: `migrations/001_raw_and_ops.sql`
- Test: `tests/test_repository_raw.py`（建表存在性在此先验证）

- [ ] **Step 1: 写失败测试（表与唯一键存在）**

`tests/test_repository_raw.py`：

```python
def test_raw_tables_exist(conn):
    with conn.cursor() as cur:
        cur.execute("SELECT to_regclass('raw_source_records')")
        assert cur.fetchone()[0] is not None
        cur.execute("SELECT to_regclass('collector_runs')")
        assert cur.fetchone()[0] is not None


def test_raw_unique_key_includes_collected_at(conn):
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT indexdef FROM pg_indexes
            WHERE tablename = 'raw_source_records' AND indexdef ILIKE '%unique%'
            """
        )
        defs = " ".join(row[0] for row in cur.fetchall()).lower()
    assert "collected_at" in defs and "source_record_id" in defs and "platform" in defs
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_repository_raw.py -v`
Expected: FAIL（`raw_source_records` 不存在）。

- [ ] **Step 3: 填充 `migrations/001_raw_and_ops.sql`**

```sql
CREATE TABLE raw_source_records (
    id              BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source          TEXT        NOT NULL,
    platform        TEXT        NOT NULL,
    product_type    TEXT        NOT NULL,
    source_file     TEXT        NOT NULL,
    source_record_id TEXT       NOT NULL,
    raw_payload     JSONB       NOT NULL,
    payload_hash    TEXT        NOT NULL,
    collected_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_raw UNIQUE (source, platform, source_record_id, collected_at)
);
CREATE INDEX idx_raw_lookup ON raw_source_records (source, platform, source_record_id);

CREATE TABLE collector_runs (
    id            BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source        TEXT        NOT NULL,
    product_type  TEXT,
    started_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
    finished_at   TIMESTAMPTZ,
    status        TEXT        NOT NULL DEFAULT 'running',
    record_count  INTEGER     NOT NULL DEFAULT 0
);

CREATE TABLE collector_errors (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    run_id       BIGINT REFERENCES collector_runs(id),
    source       TEXT,
    detail       TEXT,
    raw_excerpt  TEXT,
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_cursors (
    source        TEXT NOT NULL,
    product_type  TEXT NOT NULL,
    last_synced_at TIMESTAMPTZ,
    cursor_value  TEXT,
    PRIMARY KEY (source, product_type)
);
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_repository_raw.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add migrations/001_raw_and_ops.sql tests/test_repository_raw.py
git commit -m "feat: migration 001 raw_source_records + ops tables"
```

---

## Task 4: 迁移 002 — 标准层、关联与分析占位表

**Files:**
- Create: `migrations/002_standard_and_analysis.sql`
- Test: `tests/test_repository_standard.py`（先验证结构）

- [ ] **Step 1: 写失败测试**

`tests/test_repository_standard.py`：

```python
def test_standard_tables_exist(conn):
    with conn.cursor() as cur:
        for table in ["products", "price_snapshots", "sales_snapshots",
                      "reviews", "erp_skus", "source_product_links"]:
            cur.execute("SELECT to_regclass(%s)", (table,))
            assert cur.fetchone()[0] is not None, table


def test_products_partial_unique_competitor_only(conn):
    with conn.cursor() as cur:
        # 两条自家商品都无平台ID，不应冲突
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('erp', NULL, 'own A', true)")
        cur.execute("INSERT INTO products (platform, platform_product_id, title, is_own) "
                    "VALUES ('erp', NULL, 'own B', true)")
    conn.commit()
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products WHERE is_own")
        assert cur.fetchone()[0] == 2
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_repository_standard.py -v`
Expected: FAIL（表不存在）。

- [ ] **Step 3: 创建 `migrations/002_standard_and_analysis.sql`**

```sql
CREATE TABLE products (
    product_id          BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    platform            TEXT        NOT NULL,
    platform_product_id TEXT,
    title               TEXT,
    category            TEXT,
    image_url           TEXT,
    brand               TEXT,
    seller_id           TEXT,
    seller_name         TEXT,
    is_own              BOOLEAN     NOT NULL DEFAULT false,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);
-- 仅竞品 listing 受唯一约束；自家商品(is_own)与无平台ID不受限
CREATE UNIQUE INDEX uq_products_competitor
    ON products (platform, platform_product_id)
    WHERE is_own = false AND platform_product_id IS NOT NULL;

CREATE TABLE erp_skus (
    sku             TEXT PRIMARY KEY,
    own_product_id  BIGINT REFERENCES products(product_id),
    cost_price          NUMERIC,
    weighted_purchase   NUMERIC,
    weighted_freight    NUMERIC,
    weighted_sorting    NUMERIC,
    stock               INTEGER,
    once_gross_margin   NUMERIC,
    main_platform       TEXT,
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE source_product_links (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    source               TEXT NOT NULL,
    source_record_id     TEXT NOT NULL,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    canonical_url        TEXT,
    product_id           BIGINT REFERENCES products(product_id),
    link_type            TEXT NOT NULL DEFAULT 'deterministic',
    confidence           NUMERIC NOT NULL DEFAULT 1.0,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    CONSTRAINT uq_link UNIQUE (source, source_record_id)
);

CREATE TABLE price_snapshots (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id           BIGINT REFERENCES products(product_id),
    source               TEXT NOT NULL,
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    price                NUMERIC,
    currency             TEXT,
    observed_at          TIMESTAMPTZ NOT NULL,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_source        TEXT,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    CONSTRAINT uq_price UNIQUE (source, platform, platform_product_id, observed_at)
);

CREATE TABLE sales_snapshots (
    id                   BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id           BIGINT REFERENCES products(product_id),
    source               TEXT NOT NULL,
    platform             TEXT NOT NULL,
    platform_product_id  TEXT,
    sales                NUMERIC,
    review_count         INTEGER,
    review_rating        NUMERIC,
    observed_at          TIMESTAMPTZ NOT NULL,
    collected_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    metric_source        TEXT,
    raw_source_record_id BIGINT REFERENCES raw_source_records(id),
    CONSTRAINT uq_sales UNIQUE (source, platform, platform_product_id, observed_at)
);

CREATE TABLE reviews (
    id           BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY,
    product_id   BIGINT REFERENCES products(product_id),
    source       TEXT,
    rating       NUMERIC,
    content      TEXT,
    observed_at  TIMESTAMPTZ,
    collected_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_repository_standard.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add migrations/002_standard_and_analysis.sql tests/test_repository_standard.py
git commit -m "feat: migration 002 standard + linking tables"
```

---

## Task 5: URL 规范化（纯函数，§4.1.3）

**Files:**
- Create: `src/sourcing/urls.py`
- Test: `tests/test_urls.py`

- [ ] **Step 1: 写失败测试（覆盖真实样例）**

`tests/test_urls.py`：

```python
from sourcing.urls import normalize_product_url


def test_ozon_bare_id():
    assert normalize_product_url("https://www.ozon.ru/product/3637903008") == (
        "ozon", "3637903008", "https://www.ozon.ru/product/3637903008")


def test_ozon_with_slug():
    assert normalize_product_url("https://www.ozon.ru/product/asus-zenbook-3637903008/") == (
        "ozon", "3637903008", "https://www.ozon.ru/product/3637903008")


def test_aliexpress_with_query_and_m_prefix():
    assert normalize_product_url("https://m.aliexpress.com/item/1005006.html?spm=a2g0o") == (
        "aliexpress", "1005006", "https://www.aliexpress.com/item/1005006.html")


def test_unknown_host():
    assert normalize_product_url("https://example.com/x") == ("unknown", None, None)


def test_empty():
    assert normalize_product_url("") == ("unknown", None, None)
    assert normalize_product_url(None) == ("unknown", None, None)


def test_aliexpress_no_item_id():
    assert normalize_product_url("https://www.aliexpress.com/store/123") == (
        "aliexpress", None, None)
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_urls.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 `src/sourcing/urls.py`**

```python
import re
from urllib.parse import urlsplit

_OZON_RE = re.compile(r"/product/(?:[^/]*-)?(\d+)")
_AE_RE = re.compile(r"/item/(\d+)\.html")


def normalize_product_url(url: str | None) -> tuple[str, str | None, str | None]:
    """返回 (platform, platform_product_id, canonical_url)。"""
    if not url or not url.strip():
        return ("unknown", None, None)
    raw = url.strip()
    parts = urlsplit(raw if "://" in raw else "https://" + raw)
    host = parts.netloc.lower()
    for prefix in ("www.", "m."):
        if host.startswith(prefix):
            host = host[len(prefix):]
    path = parts.path.rstrip("/")

    if "ozon.ru" in host:
        match = _OZON_RE.search(path)
        if match:
            pid = match.group(1)
            return ("ozon", pid, f"https://www.ozon.ru/product/{pid}")
        return ("ozon", None, None)

    if "aliexpress" in host:
        match = _AE_RE.search(path)
        if match:
            pid = match.group(1)
            return ("aliexpress", pid, f"https://www.aliexpress.com/item/{pid}.html")
        return ("aliexpress", None, None)

    return ("unknown", None, None)
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_urls.py -v`
Expected: PASS（6 个用例全过）。

- [ ] **Step 5: Commit**

```bash
git add src/sourcing/urls.py tests/test_urls.py
git commit -m "feat: URL normalization (ozon/aliexpress -> platform+id)"
```

---

## Task 6: 数据契约（dataclass）

**Files:**
- Create: `src/sourcing/contracts.py`
- Test: `tests/test_contracts.py`

- [ ] **Step 1: 写失败测试**

`tests/test_contracts.py`：

```python
from datetime import datetime, timezone
from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot


def test_normalized_product_defaults():
    p = NormalizedProduct(
        source="seerfar", platform="ozon", platform_product_id="3637903008",
        canonical_url="https://www.ozon.ru/product/3637903008",
        source_record_id="3637903008", product_type="laptop",
    )
    assert p.is_own is False
    assert p.title is None


def test_snapshots_require_observed_at():
    now = datetime.now(timezone.utc)
    ps = PriceSnapshot(source="seerfar", platform="ozon", platform_product_id="1",
                       price=91510.0, currency="RUB", observed_at=now,
                       collected_at=now, metric_source="seerfar")
    ss = SalesSnapshot(source="seerfar", platform="ozon", platform_product_id="1",
                       sales=553, review_count=28, review_rating=5.0,
                       observed_at=now, collected_at=now, metric_source="seerfar")
    assert ps.price == 91510.0 and ss.sales == 553
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_contracts.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 `src/sourcing/contracts.py`**

```python
from dataclasses import dataclass
from datetime import datetime


@dataclass
class NormalizedProduct:
    source: str
    platform: str
    platform_product_id: str | None
    canonical_url: str | None
    source_record_id: str
    product_type: str
    title: str | None = None
    brand: str | None = None
    category: str | None = None
    image_url: str | None = None
    seller_id: str | None = None
    seller_name: str | None = None
    is_own: bool = False


@dataclass
class PriceSnapshot:
    source: str
    platform: str
    platform_product_id: str | None
    price: float | None
    currency: str | None
    observed_at: datetime
    collected_at: datetime
    metric_source: str | None = None


@dataclass
class SalesSnapshot:
    source: str
    platform: str
    platform_product_id: str | None
    sales: float | None
    review_count: int | None
    review_rating: float | None
    observed_at: datetime
    collected_at: datetime
    metric_source: str | None = None
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_contracts.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/sourcing/contracts.py tests/test_contracts.py
git commit -m "feat: data contracts (NormalizedProduct + snapshots)"
```

---

## Task 7: 读取器 — 公共工具 + Seerfar

**Files:**
- Create: `src/sourcing/readers/__init__.py`, `src/sourcing/readers/common.py`, `src/sourcing/readers/seerfar.py`
- Create: `tests/fixtures/seerfar_sample.csv`
- Test: `tests/test_readers_seerfar.py`

- [ ] **Step 1: 创建样例 CSV `tests/fixtures/seerfar_sample.csv`**

（列对应 `seerfar_api_fetch.py` 的输出；一行 Ozon、一行 AliExpress）

```csv
source_rank,sku,product_name,brand,category,image_url,product_url,price,seller_id,seller_name,sales,review_count,review_rating
1,3637903008,ASUS Zenbook 14,ASUS,Electronics > Laptop,https://img/x.jpg,https://www.ozon.ru/product/3637903008,91510.0,1865500,SellerX,553,28,5.0
2,1005006,Mini Speaker,Generic,Electronics > Audio,https://img/y.jpg,https://www.aliexpress.com/item/1005006.html?spm=a2,12.5,777,SellerY,2000,150,4.6
```

- [ ] **Step 2: 写失败测试**

`tests/test_readers_seerfar.py`：

```python
from sourcing.readers.seerfar import read_seerfar


def test_seerfar_reader_maps_fields_and_platform():
    products, prices, sales = read_seerfar("tests/fixtures/seerfar_sample.csv", product_type="laptop")
    assert len(products) == 2
    ozon = products[0]
    assert ozon.source == "seerfar"
    assert ozon.platform == "ozon"
    assert ozon.platform_product_id == "3637903008"
    assert ozon.canonical_url == "https://www.ozon.ru/product/3637903008"
    assert ozon.title == "ASUS Zenbook 14"

    ae = products[1]
    assert ae.platform == "aliexpress"
    assert ae.platform_product_id == "1005006"

    assert prices[0].price == 91510.0
    assert prices[0].metric_source == "seerfar"
    assert sales[0].sales == 553
    assert sales[0].review_count == 28
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `pytest tests/test_readers_seerfar.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 4: 实现 `src/sourcing/readers/__init__.py`（空）与 `src/sourcing/readers/common.py`**

```python
import csv
from datetime import datetime, timezone


def read_csv_rows(path: str) -> list[dict]:
    with open(path, "r", encoding="utf-8-sig", newline="") as fh:
        return list(csv.DictReader(fh))


def to_float(value) -> float | None:
    if value in (None, "", "None"):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def to_int(value) -> int | None:
    f = to_float(value)
    return int(f) if f is not None else None


def now_utc() -> datetime:
    return datetime.now(timezone.utc)
```

- [ ] **Step 5: 实现 `src/sourcing/readers/seerfar.py`**

```python
from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot
from sourcing.readers.common import read_csv_rows, to_float, to_int, now_utc
from sourcing.urls import normalize_product_url

SOURCE = "seerfar"


def read_seerfar(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, prices, sales = [], [], []
    collected = now_utc()
    for row in rows:
        platform, pid, canonical = normalize_product_url(row.get("product_url"))
        record_id = (row.get("sku") or "").strip() or (canonical or f"row-{len(products)}")
        products.append(NormalizedProduct(
            source=SOURCE, platform=platform, platform_product_id=pid,
            canonical_url=canonical, source_record_id=record_id, product_type=product_type,
            title=row.get("product_name") or None, brand=row.get("brand") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
            seller_id=row.get("seller_id") or None, seller_name=row.get("seller_name") or None,
        ))
        prices.append(PriceSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            price=to_float(row.get("price")), currency=None,
            observed_at=collected, collected_at=collected, metric_source="seerfar",
        ))
        sales.append(SalesSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            sales=to_float(row.get("sales")), review_count=to_int(row.get("review_count")),
            review_rating=to_float(row.get("review_rating")),
            observed_at=collected, collected_at=collected, metric_source="seerfar",
        ))
    return products, prices, sales
```

> 说明：MVP 以 fetch 时刻作为 `observed_at`（无更精确业务时点）。后续若 Seerfar 提供数据日期，可替换。

- [ ] **Step 6: 运行测试，确认通过**

Run: `pytest tests/test_readers_seerfar.py -v`
Expected: PASS。

- [ ] **Step 7: Commit**

```bash
git add src/sourcing/readers tests/test_readers_seerfar.py tests/fixtures/seerfar_sample.csv
git commit -m "feat: seerfar CSV reader + common csv utils"
```

---

## Task 8: 读取器 — IXSPY/AliExpress 与 ERP

**Files:**
- Create: `src/sourcing/readers/ixspy.py`, `src/sourcing/readers/erp.py`
- Create: `tests/fixtures/ixspy_sample.csv`, `tests/fixtures/erp_sample.csv`
- Test: `tests/test_readers_ixspy.py`, `tests/test_readers_erp.py`

- [ ] **Step 1: 创建 `tests/fixtures/ixspy_sample.csv`**

```csv
source_rank,sku,product_name,brand,category,image_url,price,product_url
1,1005006,Mini Speaker Pro,GenericStore,Audio,https://img/y.jpg,12.5,https://www.aliexpress.com/item/1005006.html
```

- [ ] **Step 2: 写失败测试 `tests/test_readers_ixspy.py`**

```python
from sourcing.readers.ixspy import read_ixspy


def test_ixspy_reader():
    products, prices = read_ixspy("tests/fixtures/ixspy_sample.csv", product_type="audio")
    assert len(products) == 1
    p = products[0]
    assert p.source == "ixspy"
    assert p.platform == "aliexpress"
    assert p.platform_product_id == "1005006"
    assert p.title == "Mini Speaker Pro"
    assert prices[0].price == 12.5
```

- [ ] **Step 3: 运行测试，确认失败**

Run: `pytest tests/test_readers_ixspy.py -v`
Expected: FAIL。

- [ ] **Step 4: 实现 `src/sourcing/readers/ixspy.py`**

```python
from sourcing.contracts import NormalizedProduct, PriceSnapshot
from sourcing.readers.common import read_csv_rows, to_float, now_utc
from sourcing.urls import normalize_product_url

SOURCE = "ixspy"


def read_ixspy(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, prices = [], []
    collected = now_utc()
    for row in rows:
        platform, pid, canonical = normalize_product_url(row.get("product_url"))
        record_id = (row.get("sku") or "").strip() or (canonical or f"row-{len(products)}")
        products.append(NormalizedProduct(
            source=SOURCE, platform=platform, platform_product_id=pid,
            canonical_url=canonical, source_record_id=record_id, product_type=product_type,
            title=row.get("product_name") or None, brand=row.get("brand") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
        ))
        prices.append(PriceSnapshot(
            source=SOURCE, platform=platform, platform_product_id=pid,
            price=to_float(row.get("price")), currency=None,
            observed_at=collected, collected_at=collected, metric_source="ixspy",
        ))
    return products, prices
```

- [ ] **Step 5: 运行测试，确认通过**

Run: `pytest tests/test_readers_ixspy.py -v`
Expected: PASS。

- [ ] **Step 6: 创建 `tests/fixtures/erp_sample.csv`**

（列对应 `erp_api_fetch.py` 扩展后输出；含成本/库存——这些列由 Plan 3 的脚本扩展产生，本 reader 先按列名读取）

```csv
sku,main_sku,product_name,category,image_url,cost_price,weighted_purchase,weighted_freight,weighted_sorting,stock,once_gross_margin,main_platform
G-SH-WAC-225,GSHWAC225ND,半截隐形袜,女士短袜,https://img/sock.jpg,1.8361,1.6,0.2297,0.0064,100,0.47,Tiktok
```

- [ ] **Step 7: 写失败测试 `tests/test_readers_erp.py`**

```python
from sourcing.readers.erp import read_erp


def test_erp_reader_marks_own_and_cost():
    products, skus = read_erp("tests/fixtures/erp_sample.csv", product_type="socks")
    assert len(products) == 1
    p = products[0]
    assert p.is_own is True
    assert p.platform == "erp"
    assert p.platform_product_id is None  # 自家商品无竞品平台ID
    assert p.title == "半截隐形袜"
    s = skus[0]
    assert s["sku"] == "G-SH-WAC-225"
    assert abs(s["cost_price"] - 1.8361) < 1e-9
    assert s["stock"] == 100
```

- [ ] **Step 8: 运行测试，确认失败**

Run: `pytest tests/test_readers_erp.py -v`
Expected: FAIL。

- [ ] **Step 9: 实现 `src/sourcing/readers/erp.py`**

```python
from sourcing.contracts import NormalizedProduct
from sourcing.readers.common import read_csv_rows, to_float, to_int

SOURCE = "erp"


def read_erp(path: str, product_type: str):
    rows = read_csv_rows(path)
    products, skus = [], []
    for row in rows:
        sku = (row.get("sku") or "").strip()
        products.append(NormalizedProduct(
            source=SOURCE, platform="erp", platform_product_id=None,
            canonical_url=None, source_record_id=sku or f"row-{len(products)}",
            product_type=product_type, title=row.get("product_name") or None,
            category=row.get("category") or None, image_url=row.get("image_url") or None,
            is_own=True,
        ))
        skus.append({
            "sku": sku,
            "cost_price": to_float(row.get("cost_price")),
            "weighted_purchase": to_float(row.get("weighted_purchase")),
            "weighted_freight": to_float(row.get("weighted_freight")),
            "weighted_sorting": to_float(row.get("weighted_sorting")),
            "stock": to_int(row.get("stock")),
            "once_gross_margin": to_float(row.get("once_gross_margin")),
            "main_platform": row.get("main_platform") or None,
        })
    return products, skus
```

- [ ] **Step 10: 运行测试，确认通过**

Run: `pytest tests/test_readers_erp.py -v`
Expected: PASS。

- [ ] **Step 11: Commit**

```bash
git add src/sourcing/readers/ixspy.py src/sourcing/readers/erp.py tests/test_readers_ixspy.py tests/test_readers_erp.py tests/fixtures/ixspy_sample.csv tests/fixtures/erp_sample.csv
git commit -m "feat: ixspy + erp CSV readers"
```

---

## Task 9: Repository — 原始层写入（append-only + 哈希去重）

**Files:**
- Create: `src/sourcing/repository.py`
- Test: `tests/test_repository_raw.py`（追加用例）

- [ ] **Step 1: 追加失败测试到 `tests/test_repository_raw.py`**

```python
import json
from sourcing.repository import insert_raw_record


def test_insert_raw_dedupes_identical_payload(conn):
    payload = {"sku": "1", "price": 10}
    first = insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                              source_file="input/seerfar/t/x.csv", source_record_id="1",
                              raw_payload=payload)
    second = insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                               source_file="input/seerfar/t/x.csv", source_record_id="1",
                               raw_payload=payload)
    assert second == first  # 内容相同 -> 返回已有 id，不新增
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_source_records WHERE source_record_id='1'")
        assert cur.fetchone()[0] == 1


def test_insert_raw_keeps_history_on_change(conn):
    insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                      source_file="f", source_record_id="2", raw_payload={"price": 10})
    insert_raw_record(conn, source="seerfar", platform="ozon", product_type="t",
                      source_file="f", source_record_id="2", raw_payload={"price": 11})
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM raw_source_records WHERE source_record_id='2'")
        assert cur.fetchone()[0] == 2  # 内容变化 -> 保留历史
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_repository_raw.py -v`
Expected: FAIL（`insert_raw_record` 不存在）。

- [ ] **Step 3: 实现 `src/sourcing/repository.py`（先写 raw 部分）**

```python
import hashlib
import json
import psycopg


def _hash_payload(payload: dict) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def insert_raw_record(conn: psycopg.Connection, *, source: str, platform: str,
                      product_type: str, source_file: str, source_record_id: str,
                      raw_payload: dict) -> int:
    """Append-only：内容变化才新增；与最新一条相同则返回其 id。"""
    payload_hash = _hash_payload(raw_payload)
    with conn.cursor() as cur:
        cur.execute(
            """
            SELECT id, payload_hash FROM raw_source_records
            WHERE source=%s AND platform=%s AND source_record_id=%s
            ORDER BY collected_at DESC LIMIT 1
            """,
            (source, platform, source_record_id),
        )
        latest = cur.fetchone()
        if latest is not None and latest[1] == payload_hash:
            return latest[0]
        cur.execute(
            """
            INSERT INTO raw_source_records
                (source, platform, product_type, source_file, source_record_id,
                 raw_payload, payload_hash)
            VALUES (%s, %s, %s, %s, %s, %s, %s)
            RETURNING id
            """,
            (source, platform, product_type, source_file, source_record_id,
             json.dumps(raw_payload, ensure_ascii=False), payload_hash),
        )
        new_id = cur.fetchone()[0]
    conn.commit()
    return new_id
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_repository_raw.py -v`
Expected: PASS（含 Task 3 的结构用例）。

- [ ] **Step 5: Commit**

```bash
git add src/sourcing/repository.py tests/test_repository_raw.py
git commit -m "feat: append-only raw record writer with hash dedup"
```

---

## Task 10: Repository — 标准层 upsert（products + 快照）

**Files:**
- Modify: `src/sourcing/repository.py`
- Test: `tests/test_repository_standard.py`（追加用例）

- [ ] **Step 1: 追加失败测试**

```python
from datetime import datetime, timezone
from sourcing.contracts import NormalizedProduct, PriceSnapshot
from sourcing.repository import upsert_product, insert_price_snapshot


def test_upsert_product_competitor_idempotent(conn):
    p = NormalizedProduct(source="seerfar", platform="ozon", platform_product_id="900",
                          canonical_url="u", source_record_id="900", product_type="t",
                          title="X")
    id1 = upsert_product(conn, p)
    id2 = upsert_product(conn, p)  # 同竞品再来一次
    assert id1 == id2  # 命中部分唯一索引 -> 同一行
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 1


def test_price_snapshot_unique_observed_at(conn):
    now = datetime.now(timezone.utc)
    p = NormalizedProduct(source="seerfar", platform="ozon", platform_product_id="901",
                          canonical_url="u", source_record_id="901", product_type="t")
    pid = upsert_product(conn, p)
    snap = PriceSnapshot(source="seerfar", platform="ozon", platform_product_id="901",
                         price=10.0, currency="RUB", observed_at=now, collected_at=now,
                         metric_source="seerfar")
    insert_price_snapshot(conn, pid, snap)
    insert_price_snapshot(conn, pid, snap)  # 同 observed_at -> upsert 不新增
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM price_snapshots")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_repository_standard.py -v`
Expected: FAIL（函数不存在）。

- [ ] **Step 3: 在 `repository.py` 追加实现**

```python
from sourcing.contracts import NormalizedProduct, PriceSnapshot, SalesSnapshot


def upsert_product(conn: psycopg.Connection, p: NormalizedProduct) -> int:
    with conn.cursor() as cur:
        if not p.is_own and p.platform_product_id is not None:
            cur.execute(
                """
                SELECT product_id FROM products
                WHERE is_own = false AND platform = %s AND platform_product_id = %s
                """,
                (p.platform, p.platform_product_id),
            )
            existing = cur.fetchone()
            if existing:
                cur.execute(
                    """
                    UPDATE products SET title=COALESCE(%s, title),
                        category=COALESCE(%s, category), image_url=COALESCE(%s, image_url),
                        brand=COALESCE(%s, brand), seller_id=COALESCE(%s, seller_id),
                        seller_name=COALESCE(%s, seller_name)
                    WHERE product_id=%s
                    """,
                    (p.title, p.category, p.image_url, p.brand, p.seller_id,
                     p.seller_name, existing[0]),
                )
                conn.commit()
                return existing[0]
        cur.execute(
            """
            INSERT INTO products
                (platform, platform_product_id, title, category, image_url,
                 brand, seller_id, seller_name, is_own)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s) RETURNING product_id
            """,
            (p.platform, p.platform_product_id, p.title, p.category, p.image_url,
             p.brand, p.seller_id, p.seller_name, p.is_own),
        )
        product_id = cur.fetchone()[0]
    conn.commit()
    return product_id


def insert_price_snapshot(conn: psycopg.Connection, product_id: int, snap: PriceSnapshot,
                          raw_id: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO price_snapshots
                (product_id, source, platform, platform_product_id, price, currency,
                 observed_at, collected_at, metric_source, raw_source_record_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, platform, platform_product_id, observed_at) DO NOTHING
            """,
            (product_id, snap.source, snap.platform, snap.platform_product_id, snap.price,
             snap.currency, snap.observed_at, snap.collected_at, snap.metric_source, raw_id),
        )
    conn.commit()


def insert_sales_snapshot(conn: psycopg.Connection, product_id: int, snap: SalesSnapshot,
                          raw_id: int | None = None) -> None:
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO sales_snapshots
                (product_id, source, platform, platform_product_id, sales, review_count,
                 review_rating, observed_at, collected_at, metric_source, raw_source_record_id)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, platform, platform_product_id, observed_at) DO NOTHING
            """,
            (product_id, snap.source, snap.platform, snap.platform_product_id, snap.sales,
             snap.review_count, snap.review_rating, snap.observed_at, snap.collected_at,
             snap.metric_source, raw_id),
        )
    conn.commit()
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_repository_standard.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/sourcing/repository.py tests/test_repository_standard.py
git commit -m "feat: upsert products + insert price/sales snapshots"
```

---

## Task 11: Repository — 跨源确定关联（source_product_links）

**Files:**
- Modify: `src/sourcing/repository.py`
- Test: `tests/test_repository_linking.py`

- [ ] **Step 1: 写失败测试**

`tests/test_repository_linking.py`：

```python
from sourcing.contracts import NormalizedProduct
from sourcing.repository import upsert_product, link_source_record


def _product(source):
    return NormalizedProduct(source=source, platform="aliexpress",
                             platform_product_id="1005006", canonical_url="c",
                             source_record_id="1005006", product_type="audio",
                             title=f"from-{source}")


def test_two_sources_same_id_link_to_one_product(conn):
    seerfar = _product("seerfar")
    ixspy = _product("ixspy")
    pid_a = upsert_product(conn, seerfar)
    pid_b = upsert_product(conn, ixspy)
    assert pid_a == pid_b  # 同 (platform, platform_product_id) -> 同一 product

    link_source_record(conn, seerfar, product_id=pid_a, raw_id=None)
    link_source_record(conn, ixspy, product_id=pid_b, raw_id=None)
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_product_links WHERE product_id=%s", (pid_a,))
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(DISTINCT source) FROM source_product_links")
        assert cur.fetchone()[0] == 2


def test_link_upsert_by_source_record(conn):
    seerfar = _product("seerfar")
    pid = upsert_product(conn, seerfar)
    link_source_record(conn, seerfar, product_id=pid, raw_id=None)
    link_source_record(conn, seerfar, product_id=pid, raw_id=None)  # 重复
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM source_product_links")
        assert cur.fetchone()[0] == 1
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_repository_linking.py -v`
Expected: FAIL（`link_source_record` 不存在）。

- [ ] **Step 3: 在 `repository.py` 追加实现**

```python
def link_source_record(conn: psycopg.Connection, p: NormalizedProduct, *,
                       product_id: int, raw_id: int | None) -> None:
    link_type = "deterministic" if p.platform_product_id else "fuzzy_pending"
    confidence = 1.0 if p.platform_product_id else 0.0
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO source_product_links
                (source, source_record_id, raw_source_record_id, platform,
                 platform_product_id, canonical_url, product_id, link_type, confidence)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)
            ON CONFLICT (source, source_record_id) DO UPDATE SET
                product_id = EXCLUDED.product_id,
                raw_source_record_id = EXCLUDED.raw_source_record_id,
                link_type = EXCLUDED.link_type,
                confidence = EXCLUDED.confidence
            """,
            (p.source, p.source_record_id, raw_id, p.platform, p.platform_product_id,
             p.canonical_url, product_id, link_type, confidence),
        )
    conn.commit()
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_repository_linking.py -v`
Expected: PASS。

- [ ] **Step 5: Commit**

```bash
git add src/sourcing/repository.py tests/test_repository_linking.py
git commit -m "feat: source_product_links deterministic linking"
```

---

## Task 12: 导入编排 + CLI

**Files:**
- Create: `src/sourcing/importer.py`, `src/sourcing/cli.py`
- Test: `tests/test_importer.py`

- [ ] **Step 1: 写失败测试（端到端：读 Seerfar 样例 → 入库 → 关联）**

`tests/test_importer.py`：

```python
from sourcing.importer import import_seerfar_csv


def test_import_seerfar_end_to_end(conn):
    summary = import_seerfar_csv(conn, "tests/fixtures/seerfar_sample.csv",
                                 product_type="laptop",
                                 source_file="input/seerfar/laptop/seerfar_products.csv")
    assert summary["products"] == 2
    with conn.cursor() as cur:
        cur.execute("SELECT count(*) FROM products")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM price_snapshots")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM sales_snapshots")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM source_product_links WHERE link_type='deterministic'")
        assert cur.fetchone()[0] == 2
        cur.execute("SELECT count(*) FROM raw_source_records")
        assert cur.fetchone()[0] == 2
```

- [ ] **Step 2: 运行测试，确认失败**

Run: `pytest tests/test_importer.py -v`
Expected: FAIL（模块不存在）。

- [ ] **Step 3: 实现 `src/sourcing/importer.py`**

```python
from dataclasses import asdict
import psycopg

from sourcing.readers.seerfar import read_seerfar
from sourcing.repository import (
    insert_raw_record, upsert_product, insert_price_snapshot,
    insert_sales_snapshot, link_source_record,
)


def import_seerfar_csv(conn: psycopg.Connection, path: str, *, product_type: str,
                       source_file: str) -> dict:
    products, prices, sales = read_seerfar(path, product_type)
    count = 0
    for product, price, sale in zip(products, prices, sales):
        raw_id = insert_raw_record(
            conn, source=product.source, platform=product.platform,
            product_type=product_type, source_file=source_file,
            source_record_id=product.source_record_id, raw_payload=asdict(product),
        )
        product_id = upsert_product(conn, product)
        insert_price_snapshot(conn, product_id, price, raw_id)
        insert_sales_snapshot(conn, product_id, sale, raw_id)
        link_source_record(conn, product, product_id=product_id, raw_id=raw_id)
        count += 1
    return {"products": count}
```

- [ ] **Step 4: 运行测试，确认通过**

Run: `pytest tests/test_importer.py -v`
Expected: PASS。

- [ ] **Step 5: 实现 `src/sourcing/cli.py`**

```python
import argparse
from sourcing import config, db
from sourcing.importer import import_seerfar_csv


def main() -> None:
    parser = argparse.ArgumentParser(description="Import source CSV into PostgreSQL")
    parser.add_argument("--source", required=True, choices=["seerfar"])
    parser.add_argument("--path", required=True, help="CSV 文件路径")
    parser.add_argument("--product-type", required=True)
    args = parser.parse_args()

    conn = db.connect(config.database_url())
    try:
        if args.source == "seerfar":
            summary = import_seerfar_csv(
                conn, args.path, product_type=args.product_type, source_file=args.path)
        print(f"[DONE] imported: {summary}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
```

> 说明：CLI 一期只接 Seerfar（最高价值的竞品销量源）。IXSPY/ERP 的 importer 在 Plan 2/3 接入（与利润/匹配一起更连贯）。

- [ ] **Step 6: 全量回归**

Run: `pytest -v`
Expected: 所有测试 PASS。

- [ ] **Step 7: 对真实数据冒烟（手动，可选）**

Run:
```powershell
docker compose up -d postgres
python -m sourcing.cli --source seerfar --path "C:\Users\aibp\Desktop\518\input\seerfar\xiongzhen\seerfar_products.csv" --product-type xiongzhen
```
Expected: 打印导入条数；若真实 CSV 列与样例不符则记录差异，反馈到 reader（不在本任务范围内修正）。

- [ ] **Step 8: Commit**

```bash
git add src/sourcing/importer.py src/sourcing/cli.py tests/test_importer.py
git commit -m "feat: seerfar import orchestration + CLI"
```

---

## Task 13: 运行手册（README）

**Files:**
- Create: `README.md`

- [ ] **Step 1: 写 `README.md`**

````markdown
# 跨境电商选品系统 — 数据底座

## 这是什么
读取 Seerfar/IXSPY/ERP 的 CSV 产物，归一化入 PostgreSQL。设计见
`docs/superpowers/specs/2026-06-04-product-sourcing-system-design.md`。

## 本地启动
```powershell
copy .env.example .env   # 按需修改
docker compose up -d postgres
pip install -e ".[dev]"
```

## 建表（迁移）
迁移在测试中自动执行；对本地库手动建表：
```powershell
python -c "from sourcing import config, db; c=db.connect(config.database_url()); db.run_migrations(c)"
```

## 导入数据
```powershell
python -m sourcing.cli --source seerfar --path <CSV路径> --product-type <品类>
```

## 测试
```powershell
pytest -v
```

## 数据来源
取数脚本在 `C:\Users\aibp\Desktop\518\apipy`（Selenium 探测+接口回放，产出 CSV 到 `input/<源>/<品类>/`）。本系统消费这些 CSV，不直接抓取。
````

- [ ] **Step 2: Commit**

```bash
git add README.md
git commit -m "docs: add runbook README"
```

---

## Self-Review 结论

- **Spec 覆盖**：§4 全部表（raw/标准/运维/分析占位）由迁移 001/002 建立；§4.1 归一化由 Task 5（URL）+ Task 11（确定关联）实现；§2.1 三源由 readers（Task 7/8）覆盖。利润估算（§6）、机会打分（§6）、Metabase（§4④/§6）、采集编排与脚本扩展（§2.2/§8 第零步）**不在本 Plan**，属 Plan 2/3/4，已在开头标注。
- **占位符**：无 TODO/TBD；所有代码步骤含完整可执行代码（迁移 SQL 已用真实 `BIGINT GENERATED ALWAYS AS IDENTITY PRIMARY KEY`）。
- **类型一致性**：`NormalizedProduct/PriceSnapshot/SalesSnapshot` 字段在 contracts、readers、repository、importer 间一致；`upsert_product`、`insert_price_snapshot`、`insert_sales_snapshot`、`insert_raw_record`、`link_source_record` 签名跨任务一致。
- **已知简化（YAGNI，留待后续 Plan）**：`observed_at` 暂用 fetch 时刻；ERP/IXSPY 的 importer 与模糊匹配（§5）后续接入；模糊匹配 `fuzzy_pending` 仅建模不实现逻辑。
