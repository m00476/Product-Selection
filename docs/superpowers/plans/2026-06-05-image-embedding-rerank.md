# 图搜候选嵌入复核重排（Embedding Re-rank）Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax.

**Goal:** 给 ERP 以图搜款的候选补一个**真实相似度分**——用 518 的 DINOv2 嵌入算"竞品图 × 每个 ERP 候选图"的余弦相似度，写回结果、卡阈值，过滤掉"通用几何外形撞配"的假阳性；并把每个竞品的最高嵌入相似度带进决策表/看板。

**Architecture:** torch 2.12(CPU) 与 DINOv2 模型缓存已在本机本 python，可**懒加载直接 import** 518 的 `ImageEmbeddingMatcher`（把 `COLLECT_518_DIR` 加进 sys.path），**无需 subprocess**。纯逻辑（算分/重排）与重依赖（torch 嵌入器）分离：前者可 TDD，后者真机验证。

**Tech Stack:** Python、psycopg、pytest；运行期懒加载 torch + 518 `image_embedding_matcher`（DINOv2）。

依赖已合并：`erp_image_search.py`（`output_csv_path`、`_read_csv_dicts`、`build_boss_decision_rows`、`RESULT_FIELDS`、`BOSS_DECISION_FIELDS`）、`bridge/image_decisions.py`、migration 006（`erp_image_decisions` + `v_erp_image_decisions`）。

## 已核实事实
- 本 python：`torch 2.12.0+cpu`，DINOv2 缓存在 `~/.cache/torch/hub/facebookresearch_dinov2_main`，`import image_embedding_matcher`（518）可成功。
- `ImageEmbeddingMatcher(product_type=...).get_embedding(url, source)` → 归一化向量(或 None)，带 pickle 缓存；相似度 = `vq @ vc`（两归一化向量点积=余弦）。
- 图搜结果 CSV 每行含 `source / external_image_url / erp_image_url / matched_erp_sku / erp_product_status_text` 等（`RESULT_FIELDS`）。

## File Structure
```
src/sourcing/rerank/__init__.py
src/sourcing/rerank/embed.py          # rerank_rows(纯) + build_embedder(懒torch) + rerank_image_search(编排)
src/sourcing/cli.py                   # 增加 erp-image-rerank 子命令（修改）
migrations/007_decision_embedding.sql # erp_image_decisions 加列 + 视图加列
src/sourcing/erp_image_search.py      # build_boss_decision_rows 增加 max_embedding_similarity（修改）
src/sourcing/bridge/image_decisions.py# upsert 带上新列（修改）
tests/test_rerank_embed.py
tests/test_cli.py / tests/test_image_decisions.py（追加）
```

---

## Task 1: 纯逻辑 rerank_rows + 懒加载嵌入器

**Files:** Create `src/sourcing/rerank/__init__.py`(空), `src/sourcing/rerank/embed.py`; Test `tests/test_rerank_embed.py`.

- [ ] **Step 1: 写失败测试 `tests/test_rerank_embed.py`**（用假 get_embedding 注入 numpy 单位向量，不碰 torch）

```python
import numpy as np
from sourcing.rerank.embed import rerank_rows, DEFAULT_THRESHOLD


def _fake_embeddings():
    # 同向量->相似1.0；正交->0.0；None->缺失
    vecs = {
        "qA": np.array([1.0, 0.0, 0.0]),
        "cA_same": np.array([1.0, 0.0, 0.0]),
        "qB": np.array([1.0, 0.0, 0.0]),
        "cB_diff": np.array([0.0, 1.0, 0.0]),
    }
    def get_embedding(url, source):
        return vecs.get(url)  # 未知 url -> None
    return get_embedding


def test_rerank_rows_adds_similarity_and_confidence():
    rows = [
        {"source": "ixspy", "external_image_url": "qA", "erp_image_url": "cA_same"},
        {"source": "ixspy", "external_image_url": "qB", "erp_image_url": "cB_diff"},
        {"source": "ixspy", "external_image_url": "qB", "erp_image_url": "missing"},
    ]
    out = rerank_rows(rows, _fake_embeddings(), threshold=DEFAULT_THRESHOLD)
    assert out[0]["embedding_similarity"] == 1.0
    assert out[0]["embedding_confident"] == "1"
    assert out[1]["embedding_similarity"] == 0.0
    assert out[1]["embedding_confident"] == "0"
    assert out[2]["embedding_similarity"] == ""      # 缺图 -> 空
    assert out[2]["embedding_confident"] == "0"


def test_rerank_rows_caches_embeddings_per_url():
    calls = []
    def counting(url, source):
        calls.append(url)
        return np.array([1.0, 0.0])
    rows = [
        {"source": "s", "external_image_url": "q", "erp_image_url": "c"},
        {"source": "s", "external_image_url": "q", "erp_image_url": "c"},
    ]
    rerank_rows(rows, counting)
    # q 和 c 各只算一次（被缓存），共 2 次而非 4 次
    assert sorted(set(calls)) == ["c", "q"]
    assert len(calls) == 2
```

- [ ] **Step 2: 运行 `pytest tests/test_rerank_embed.py -v`，确认 FAIL。**

- [ ] **Step 3: 实现 `src/sourcing/rerank/__init__.py`（空）与 `src/sourcing/rerank/embed.py`**

```python
import os
import sys

from sourcing.erp_image_search import output_csv_path, _read_csv_dicts, RESULT_FIELDS
from sourcing.collect.api_common import write_csv

DEFAULT_THRESHOLD = 0.85
EXTRA_FIELDS = ["embedding_similarity", "embedding_confident"]


def _cosine(a, b):
    if a is None or b is None:
        return None
    return float(a @ b)


def rerank_rows(rows, get_embedding, *, threshold: float = DEFAULT_THRESHOLD):
    """给每行加 embedding_similarity(竞品图×候选图余弦) 与 embedding_confident(>=阈值)。
    get_embedding(url, source)->向量或None；按 url 缓存，避免重复计算。纯逻辑、可注入假实现。"""
    cache = {}

    def emb(url, source):
        if not url:
            return None
        key = (url, source)
        if key not in cache:
            cache[key] = get_embedding(url, source)
        return cache[key]

    out = []
    for row in rows:
        vq = emb(row.get("external_image_url"), row.get("source") or "market")
        vc = emb(row.get("erp_image_url"), "erp")
        sim = _cosine(vq, vc)
        new = dict(row)
        new["embedding_similarity"] = "" if sim is None else round(sim, 4)
        new["embedding_confident"] = "1" if (sim is not None and sim >= threshold) else "0"
        out.append(new)
    return out


def build_embedder(base_dir: str, product_type: str):
    """懒加载 518 的 DINOv2 嵌入器。返回 (get_embedding, matcher)。需 torch + 模型缓存。"""
    if base_dir not in sys.path:
        sys.path.insert(0, base_dir)
    from image_embedding_matcher import ImageEmbeddingMatcher  # 重依赖，运行期才导入
    matcher = ImageEmbeddingMatcher(product_type=product_type)
    return matcher.get_embedding, matcher


def rerank_image_search(*, source: str, product_type: str, base_dir: str,
                        limit=None, threshold: float = DEFAULT_THRESHOLD,
                        embedder=None) -> dict:
    path = output_csv_path(base_dir, source, product_type)
    rows = _read_csv_dicts(path)
    if limit is not None:
        rows = rows[:limit]
    matcher = None
    if embedder is None:
        embedder, matcher = build_embedder(base_dir, product_type)
    out = rerank_rows(rows, embedder, threshold=threshold)
    fields = list(RESULT_FIELDS) + EXTRA_FIELDS
    write_csv(str(path), out, fields)
    if matcher is not None and hasattr(matcher, "save"):
        matcher.save()
    confident = sum(1 for r in out if r.get("embedding_confident") == "1")
    return {"reranked": len(out), "confident": confident, "output": str(path)}
```

- [ ] **Step 4: 运行 `pytest tests/test_rerank_embed.py -v`，确认 PASS。**

- [ ] **Step 5: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 6: Commit**
```
git add src/sourcing/rerank/__init__.py src/sourcing/rerank/embed.py tests/test_rerank_embed.py
git commit -m "feat: embedding rerank pure logic + lazy DINOv2 embedder"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 2: 编排测试 + CLI erp-image-rerank

**Files:** Modify `src/sourcing/cli.py`; Test: append to `tests/test_rerank_embed.py`（编排）、`tests/test_cli.py`（CLI）。

- [ ] **Step 1: APPEND 编排测试到 `tests/test_rerank_embed.py`**（用临时结果 CSV + 假 embedder，验证写回）

```python
import csv
import numpy as np
from pathlib import Path
from sourcing.rerank.embed import rerank_image_search
from sourcing.erp_image_search import output_csv_path, RESULT_FIELDS


def _write_results(base, source, product_type, rows):
    p = output_csv_path(base, source, product_type)
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=RESULT_FIELDS)
        w.writeheader()
        for r in rows:
            w.writerow({k: r.get(k, "") for k in RESULT_FIELDS})
    return p


def test_rerank_image_search_writes_similarity(tmp_path):
    base = str(tmp_path)
    _write_results(base, "ixspy", "bags", [
        {"source": "ixspy", "external_sku": "E1", "external_image_url": "q", "erp_image_url": "c"},
    ])
    fake = lambda url, source: np.array([1.0, 0.0]) if url in ("q", "c") else None
    summary = rerank_image_search(source="ixspy", product_type="bags", base_dir=base, embedder=fake)
    assert summary["reranked"] == 1 and summary["confident"] == 1
    out_rows = list(csv.DictReader(open(output_csv_path(base, "ixspy", "bags"), encoding="utf-8-sig")))
    assert out_rows[0]["embedding_similarity"] == "1.0"
    assert out_rows[0]["embedding_confident"] == "1"
```

- [ ] **Step 2: 运行 `pytest tests/test_rerank_embed.py -v`，确认新测试 FAIL（功能未接 CLI 不影响；此测试测 rerank_image_search 已实现 -> 应直接 PASS）。**

> 注：`rerank_image_search` 在 Task 1 已实现，故本编排测试应直接通过；若失败按报错修。

- [ ] **Step 3: 修改 `src/sourcing/cli.py`** —
(a) imports 加：`from sourcing.rerank.embed import rerank_image_search`
(b) 子命令定义区加：
```python
    rr = sub.add_parser("erp-image-rerank", help="用DINOv2嵌入给图搜候选补相似度并卡阈值")
    rr.add_argument("--source", required=True, choices=["seerfar", "ixspy", "aliexpress"])
    rr.add_argument("--product-type", required=True)
    rr.add_argument("--limit", type=int, default=None)
    rr.add_argument("--threshold", type=float, default=0.85)
```
(c) 在 quality/erp-image-search 那种**连库前就 return** 的区块里加（rerank 不需要数据库）：
```python
    if args.command == "erp-image-rerank":
        summary = rerank_image_search(
            source=args.source, product_type=args.product_type,
            base_dir=config.collect_base_dir(), limit=args.limit, threshold=args.threshold)
        print(f"[DONE] reranked: {summary}")
        return
```

- [ ] **Step 4: APPEND 测试到 `tests/test_cli.py`**

```python
def test_cli_erp_image_rerank(monkeypatch):
    calls = {}
    monkeypatch.setattr(sys, "argv", [
        "sourcing.cli", "erp-image-rerank", "--source", "ixspy", "--product-type", "bags", "--limit", "30",
    ])
    monkeypatch.setattr(cli.config, "collect_base_dir", lambda: "/base518")
    monkeypatch.setattr(
        cli, "rerank_image_search",
        lambda *, source, product_type, base_dir, limit, threshold:
            calls.update(source=source, product_type=product_type, base_dir=base_dir,
                         limit=limit, threshold=threshold) or {"reranked": 30, "confident": 12},
    )
    cli.main()
    assert calls["source"] == "ixspy" and calls["limit"] == 30 and calls["base_dir"] == "/base518"
```

- [ ] **Step 5: 验证 `python -c "import sourcing.cli; print('cli ok')"` 打印 `cli ok`。**

- [ ] **Step 6: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 7: Commit**
```
git add src/sourcing/cli.py tests/test_rerank_embed.py tests/test_cli.py
git commit -m "feat: cli erp-image-rerank"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 3: 决策表/看板纳入最高嵌入相似度

**Files:** Create `migrations/007_decision_embedding.sql`; Modify `src/sourcing/erp_image_search.py`, `src/sourcing/bridge/image_decisions.py`; Test: append to `tests/test_image_decisions.py`.

- [ ] **Step 1: 写失败测试（APPEND 到 `tests/test_image_decisions.py`）**

```python
def test_decisions_carry_max_embedding_similarity(conn, tmp_path):
    import csv
    from pathlib import Path
    from sourcing.bridge.image_decisions import load_image_decisions
    from sourcing.erp_image_search import output_csv_path, RESULT_FIELDS
    base = str(tmp_path)
    p = output_csv_path(base, "ixspy", "bags")
    Path(p).parent.mkdir(parents=True, exist_ok=True)
    fields = list(RESULT_FIELDS) + ["embedding_similarity", "embedding_confident"]
    rows = [
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "matched_erp_sku": "ERP1", "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品", "embedding_similarity": "0.62", "embedding_confident": "0"},
        {"source": "ixspy", "product_type": "bags", "external_sku": "E1",
         "matched_erp_sku": "ERP2", "match_status": "success", "erp_product_status": "8",
         "candidate_priority": "可用正常商品", "embedding_similarity": "0.91", "embedding_confident": "1"},
    ]
    with open(p, "w", encoding="utf-8-sig", newline="") as f:
        w = csv.DictWriter(f, fieldnames=fields); w.writeheader()
        for r in rows: w.writerow({k: r.get(k, "") for k in fields})
    load_image_decisions(conn, source="ixspy", product_type="bags", base_dir=base)
    with conn.cursor() as cur:
        cur.execute("SELECT max_embedding_similarity FROM v_erp_image_decisions WHERE external_sku='E1'")
        assert float(cur.fetchone()[0]) == 0.91
```

- [ ] **Step 2: 运行 `pytest tests/test_image_decisions.py -v`，确认新测试 FAIL。**

- [ ] **Step 3: 创建 `migrations/007_decision_embedding.sql`**

```sql
ALTER TABLE erp_image_decisions ADD COLUMN max_embedding_similarity NUMERIC;

CREATE OR REPLACE VIEW v_erp_image_decisions AS
SELECT
    source, product_type, external_sku, external_product_name, external_product_url,
    external_image_url, final_decision, boss_action, candidate_count,
    normal_candidate_count, stopped_candidate_count, risk_candidate_count,
    top_erp_skus, top_main_skus,
    (final_decision = '疑似新品机会') AS is_new_opportunity,
    generated_at,
    max_embedding_similarity
FROM erp_image_decisions;
```

- [ ] **Step 4: 改 `src/sourcing/erp_image_search.py` 的 `build_boss_decision_rows`** — 在每个决策 dict 增加 `max_embedding_similarity`，并把字段名加进 `BOSS_DECISION_FIELDS`。
在 `BOSS_DECISION_FIELDS` 列表末尾加一行 `"max_embedding_similarity",`。在 `build_boss_decision_rows` 组装 decision dict 处加：
```python
                "max_embedding_similarity": _max_embedding(items),
```
并新增辅助函数：
```python
def _max_embedding(rows: list[dict]):
    vals = []
    for row in rows:
        v = row.get("embedding_similarity")
        if v in (None, "", "None"):
            continue
        try:
            vals.append(float(v))
        except (TypeError, ValueError):
            continue
    return max(vals) if vals else ""
```

- [ ] **Step 5: 改 `src/sourcing/bridge/image_decisions.py` 的 `upsert_image_decision`** — INSERT 列与 VALUES、ON CONFLICT SET 各加 `max_embedding_similarity`：
列清单加 `max_embedding_similarity`；VALUES 占位多一个 `%s`；参数元组末尾加 `_to_float(d.get("max_embedding_similarity"))`（复用文件里已有的 `_to_int` 旁边加一个 `_to_float`，若无则新增）；ON CONFLICT DO UPDATE 加 `max_embedding_similarity=EXCLUDED.max_embedding_similarity`。
新增（若文件无 `_to_float`）：
```python
def _to_float(value):
    try:
        return float(value)
    except (TypeError, ValueError):
        return None
```

- [ ] **Step 6: 运行 `pytest tests/test_image_decisions.py -v`，确认 PASS。**

- [ ] **Step 7: 全量 `pytest -v`，确认无回归。**

- [ ] **Step 8: Commit**
```
git add migrations/007_decision_embedding.sql src/sourcing/erp_image_search.py src/sourcing/bridge/image_decisions.py tests/test_image_decisions.py
git commit -m "feat: carry max embedding similarity into decisions + view"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Task 4: README + Metabase 文档

**Files:** Modify `README.md`, `docs/metabase-dashboards.md`.

- [ ] **Step 1: README「看板（Metabase）」一节后/相关处加：**

```markdown
### 图搜候选嵌入复核（提精度）
在图搜与落库之间插一步，用 DINOv2 给候选补真实相似度并卡阈值：
```powershell
python -m sourcing.cli erp-image-search --source ixspy --product-type <品类> --limit 50
python -m sourcing.cli erp-image-rerank   --source ixspy --product-type <品类> --threshold 0.85
python -m sourcing.cli erp-image-load-db  --source ixspy --product-type <品类>
```
需 torch + 518 的 DINOv2 缓存（本机已具备）。决策表新增 `max_embedding_similarity`，
看板按它排序/筛选可显著降低"形似不同款"的假阳性。
```

- [ ] **Step 2: `docs/metabase-dashboards.md` 的「看板三」SQL 加一列 `max_embedding_similarity` 并建议按它倒序。**

- [ ] **Step 3: Commit**
```
git add README.md docs/metabase-dashboards.md
git commit -m "docs: embedding rerank usage"
```
Include trailer `Co-Authored-By: Claude Opus 4.8 <noreply@anthropic.com>`. Do NOT push.

---

## Self-Review 结论
- **目标**：给图搜候选补 DINOv2 余弦相似度 → 过滤"通用外形撞配"假阳性 → 决策表/看板可按 `max_embedding_similarity` 排序筛选。
- **架构简化**：torch 在本 python，懒加载 import 518 `ImageEmbeddingMatcher`，**无 subprocess**。
- **可测**：`rerank_rows`(注入假向量)、`rerank_image_search`(假 embedder+临时CSV)、决策聚合(带嵌入列的CSV)、CLI(monkeypatch) 全可测；真实 DINOv2 计算（`build_embedder`）真机验证，不入单测。
- **占位符**：无；代码完整。
- **类型一致性**：`rerank_rows/rerank_image_search/build_embedder`、`embedding_similarity/embedding_confident/max_embedding_similarity` 列名跨任务/SQL/文档一致。
- **不破坏既有**：图搜/决策/落库原行为不变，仅新增列与命令；`build_boss_decision_rows` 仅多输出一字段（无嵌入列时为空）。
- **真机验证（计划外，控制器执行）**：对 bag_accessories 小样本跑 rerank，确认真同款相似度高、之前误配(铜杯垫/币)相似度低被区分；再 load + 看板查 max_embedding_similarity。
