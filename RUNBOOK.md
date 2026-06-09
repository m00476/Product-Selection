# RUNBOOK — 选品对比系统手动操作手册

本手册说明如何**手动跑通全流程**，以及**换不同产品**时要改什么。

> 数据根目录 `base_dir` = `.env` 里的 `COLLECT_518_DIR`（默认 `D:\518`）。
> 所有采集 / 报告产物都在它下面。

---

## 0. 前置条件（首次/换机器时确认一次）

- `.env` 已配好：
  - `IXSPY_USERNAME` / `IXSPY_PASSWORD`（ixspy 登录）
  - `ERP_IMAGE_SEARCH_URL` / `ERP_IMAGE_SEARCH_TOKEN`（ERP 以图搜索；token 过期会**自动刷新**，刷新时会弹一次 Chrome 登录 ERP，需 `ERP_USERNAME/ERP_PASSWORD`）
  - `DATABASE_URL`（Postgres，需正在运行）
  - `COLLECT_518_DIR` / `EMBEDDING_REPO_DIR`（默认 `D:\518`）
- Chrome + chromedriver 可用（`CHROMEDRIVER_PATH` 或自动下载）
- 嵌入缓存已迁移到 SQLite（**只需一次**，已完成）：
  ```bash
  python -m sourcing.cli migrate-embedding-cache
  ```
  迁移后精筛内存恒定（+3MB），不必再关 Chrome 腾内存。

---

## 1. 跑全流程（两条命令）

以品类 `garden_tools` 为例：

```bash
cd D:\ProductSourcingSystem

# ① 采集 ixspy(AliExpress)数据 —— 会弹 Chrome：自动登录 → 选类目 → 滚动加载 → 嗅探内部接口 → 回放接口拉全量 → 导入数据库
python -m sourcing.cli collect --source ixspy --product-type garden_tools

# ② 两层匹配 + 落库 + 报告 —— 纯网络请求，不弹浏览器(token 过期才会自动弹一次刷新)
python -m sourcing.cli erp-image-pipeline --source ixspy --product-type garden_tools
```

### 一条龙命令（推荐，供计划任务调用）

把"采集 + 匹配 + 报告"串成一条命令，**带退出码 + 日志文件**：

```bash
python -m sourcing.cli run-product --source ixspy --product-type garden_tools --category 园林工具 --headless
```

- 采集失败会**立刻停止**，不会拿错/空数据继续出报告
- `--headless` 无界面跑（无人值守）；不加则显示 Chrome
- `--category` 也可不传，改写在 `.env` 的 `ALIEXPRESS_CATEGORY_NAME`（Windows 下推荐这样，避免中文在 bat 里的编码问题）
- 退出码：`0`=成功 / `1`=失败；日志写到 `<base_dir>/output/logs/<品类>/run_<时间戳>.log`

第①步内部分两小步：
- **probe**（`aliexpress_api_probe`）：用浏览器嗅出真正返回商品 JSON 的内部接口 → `output/aliexpress/<品类>/aliexpress_api_candidates.json`
- **fetch**（`aliexpress_api_fetch`）：纯 HTTP 回放该接口翻页拉全量 → `input/aliexpress/<品类>/aliexpress_products.csv` → 导库

第②步内部链路：ERP 以图搜索粗筛 → DINOv2 嵌入精配 → 落 Postgres → 生成老板报告。

### 产物位置

| 产物 | 路径（base_dir 下） |
|---|---|
| 采集明细 CSV | `input/aliexpress/<品类>/aliexpress_products.csv` |
| 老板版报告（19 列：单价/销量/评分/卖家 + ERP 最佳匹配 + 嵌入相似度 + 判定） | `output/image_search/ixspy/<品类>/best_match_report.csv` |
| 老板决策表 | `output/image_search/ixspy/<品类>/boss_decision_report.csv` / `.md` |
| 每候选明细（含 embedding_similarity） | `output/image_search/ixspy/<品类>/erp_image_search_results.csv` |

---

## 2. 换不同产品 —— 不用改任何代码文件

只动两处，关键是分清这两个概念：

| 改哪 | 含义 | 例子 |
|---|---|---|
| **`.env` 的 `ALIEXPRESS_CATEGORY_NAME`** | ⭐真正的"选品类目"——脚本往 ixspy 类目框里**直接输入**的中文文字（输入后点联想项，不是层层点选） | `ALIEXPRESS_CATEGORY_NAME=厨房用品` |
| **命令行 `--product-type`** | 内部英文 slug，只决定**文件夹名 + 数据库标签**；两条命令必须一致 | `--product-type kitchen` |

换"厨房用品"的完整操作：

```ini
# .env 加/改这一行
ALIEXPRESS_CATEGORY_NAME=厨房用品
```
```bash
python -m sourcing.cli collect --source ixspy --product-type kitchen
python -m sourcing.cli erp-image-pipeline --source ixspy --product-type kitchen
```

> ⚠️ `ALIEXPRESS_CATEGORY_NAME` 的文字必须和 ixspy 类目框能联想出来的名字对得上，否则 probe 报 `category suggestion not clicked` 并停在页面（这是常见卡住原因）。
> 第一次换新品类时建议 `SCRAPER_HEADLESS=0` 盯着看它有没有选中类目。

---

## 3. 可选调参（都在 `.env` 或 CLI，无需改代码）

| 变量 / 参数 | 作用 | 默认 |
|---|---|---|
| `ALIEXPRESS_SCROLL_ROUNDS` | 滚动轮数 ≈ 抓多少商品 | 80 |
| `ALIEXPRESS_API_TARGET_COUNT` | fetch 回放目标条数（0=全量） | 0 |
| `ALIEXPRESS_API_PAGE_SIZE` | fetch 每页条数 | 100 |
| `SCRAPER_HEADLESS` | 1=后台无界面跑 Chrome | 0（显示） |
| `--limit`（CLI，仅图搜步骤） | 只跑前 N 个，小样本试跑 | 全量 |
| `--threshold`（CLI，仅图搜步骤） | 嵌入精配置信阈值 | 0.85 |

---

## 4. 单步执行（排查 / 重跑用）

需要时可以拆开跑（`collect` 跑完后这些都不弹浏览器，token 过期除外）：

```bash
# 只跑 ERP 以图搜索（小样本试 5 个）
python -m sourcing.cli erp-image-search --source ixspy --product-type kitchen --limit 5

# 只跑 DINOv2 嵌入精配
python -m sourcing.cli erp-image-rerank --source ixspy --product-type kitchen

# 只把决策落库
python -m sourcing.cli erp-image-load-db --source ixspy --product-type kitchen

# 只重生成老板报告
python -m sourcing.cli erp-image-match-report --source ixspy --product-type kitchen
python -m sourcing.cli erp-image-decision-report --source ixspy --product-type kitchen
```

---

## 4.5 定时自动化（Windows 计划任务）

1. 编辑 `scripts\run_product.bat`，把 `PRODUCT` 改成你的品类 slug；类目名写在 `.env` 的 `ALIEXPRESS_CATEGORY_NAME`。
2. 打开"任务计划程序" → 创建基本任务 → 触发器（如每天 02:00）→ 操作选"启动程序" → 程序填 `D:\ProductSourcingSystem\scripts\run_product.bat`。
3. 勾选"不管用户是否登录都运行"（无人值守）。计划任务会根据退出码（0/1）记录成功/失败。
4. 排查看日志：`D:\518\output\logs\<品类>\run_<时间戳>.log`。

> 多品类：复制多份 bat（各自改 `PRODUCT` + 对应 `.env` 类目）或建多个任务。
> 类目没选中时一条龙会 fail-fast（退出码 1），不会静默抓错品类——计划任务能立刻发现。

## 5. 常见问题

| 现象 | 原因 / 处理 |
|---|---|
| 卡在页面不动 / `category suggestion not clicked` | `ALIEXPRESS_CATEGORY_NAME` 与 ixspy 类目名对不上 → 改成能联想出来的名字，`SCRAPER_HEADLESS=0` 观察 |
| 图搜全部 `Not Found` | ERP token 过期 → 系统会自动重登刷新（弹一次 Chrome）；若无人值守遇验证码可能停 |
| 精筛内存吃满 / OOM | 确认已跑过 `migrate-embedding-cache`（走 SQLite 懒查后内存恒定） |
| AliExpress 图片无法识别 | AliExpress 多为 AVIF 格式，已装 `pillow-avif-plugin`；缺了就 `pip install pillow-avif-plugin` |

---

## 6. 一图流速记

```
.env: ALIEXPRESS_CATEGORY_NAME=<中文类目>
        │
        ▼
collect --source ixspy --product-type <slug>     ← 弹 Chrome，采集+导库
        │  input/aliexpress/<slug>/aliexpress_products.csv
        ▼
erp-image-pipeline --source ixspy --product-type <slug>   ← 纯网络，匹配+报告
        │
        ▼
output/image_search/ixspy/<slug>/best_match_report.csv    ← 拿去汇报
```
