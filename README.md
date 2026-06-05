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
python -m sourcing.cli import --source seerfar --path <CSV路径> --product-type <品类>
python -m sourcing.cli import --source ixspy --path <CSV路径> --product-type <品类>
python -m sourcing.cli import --source erp --path <CSV路径> --product-type <品类>
```

## 检查 CSV 数据质量
```powershell
python -m sourcing.cli quality --source ixspy --path <CSV路径> --product-type <品类>
```
用于查看缺失 URL、价格、ERP 成本/库存、无法确定关联等问题。

## 计算利润与机会分
```powershell
python -m sourcing.cli analyze
```
结果写入 `profit_estimates`、`opportunity_scores` 两张表。

## ERP 内置采集
ERP API fetch 已迁入本项目，类目配置在 `configs/erp_categories.yaml`。运行示例：
```powershell
cd D:\ProductSourcingSystem
$env:PRODUCT_TYPE="bag_accessories"
$env:ERP_USERNAME="你的ERP用户名"
$env:ERP_PASSWORD="你的ERP密码"
python -m sourcing.collect.erp_api_probe
$env:ERP_API_TARGET_COUNT="100"
python -m sourcing.collect.erp_api_fetch
```
输出到 `input\erp\<PRODUCT_TYPE>\erp_products.csv`。如果 `output\erp\<PRODUCT_TYPE>\erp_api_candidates.json`
里的登录凭证过期，需要先运行 probe 刷新候选请求，再运行 fetch。

## AliExpress/IXSPY 内置采集
IXSPY 的 AliExpress probe/fetch 也已迁入本项目。运行示例：
```powershell
cd D:\ProductSourcingSystem
$env:PRODUCT_TYPE="bag_accessories"
$env:ALIEXPRESS_CATEGORY_NAME="箱包配件"
python -m sourcing.collect.aliexpress_api_probe
$env:ALIEXPRESS_API_TARGET_COUNT="100"
python -m sourcing.collect.aliexpress_api_fetch
```
输出到 `input\aliexpress\<PRODUCT_TYPE>\aliexpress_products.csv`。

## Seerfar/Ozon 内置采集
Seerfar probe/fetch 已迁入本项目。运行示例：
```powershell
cd D:\ProductSourcingSystem
$env:PRODUCT_TYPE="training_mask"
$env:SEERFAR_CATEGORY_NAME="运动与休闲 > 装备与护具 > 训练面罩"
python -m sourcing.collect.seerfar_api_probe
$env:SEERFAR_API_TARGET_COUNT="100"
python -m sourcing.collect.seerfar_api_fetch
```
输出到 `input\seerfar\<PRODUCT_TYPE>\seerfar_products.csv`。如果 fetch 返回 401，需要先运行 probe 刷新候选请求。

## 采集编排
三个源的采集模块已内置。本系统可以统一编排：
```powershell
# 单个源×品类
python -m sourcing.cli collect --source seerfar --product-type xiongzhen
# 按 .env 的 COLLECT_TARGETS 全部采集
python -m sourcing.cli collect --all
```
配置（`.env`）：`COLLECT_518_DIR`（518 根目录）、`COLLECT_TARGETS`（如 `seerfar:xiongzhen,erp:xiongzhen`）。
每次运行记录在 `collector_runs` / `collector_errors`。

### 定时（Windows 任务计划）
新建基本任务，操作设为：
`程序` = `python`，`参数` = `-m sourcing.cli collect --all`，`起始于` = 项目目录 `D:\ProductSourcingSystem`。
建议每天凌晨触发；采集依赖 Chrome/Chromedriver 与本项目 `.env` 凭证。

## 导入 518 已抓竞品（让匹配能对齐）
518 已抓的竞品在 `app.db` 的 `external_products`。把它们导入本系统（按 product_url
推导市场+商品ID），使其与 518 的匹配结果对齐，桥接才能命中：
```powershell
python -m sourcing.cli import-external
```

## 匹配桥接（复用 518 的匹配结果）
518 项目用 DINOv2/FAISS + 文本相似度做商品匹配，结果存在 `518/data/app.db`。
本命令把其 `match_results` 桥接进本系统 `product_matches`（按 平台商品ID / erp_sku 映射）：
```powershell
python -m sourcing.cli bridge-matches
```
配置 `.env` 的 `APP_DB_PATH` 指向 518 的 app.db。`status` 取值：
`confirmed`（已匹配自家 SKU）、`no_erp_match`（竞品在 ERP 无对应 = 选品机会）、`pending` / `rejected`。

## 看板（Metabase）
SQL 视图 `v_opportunities`（选品机会）、`v_competitor_monitor`（竞品监控）已就绪。
搭建步骤见 `docs/metabase-dashboards.md`。
```powershell
docker compose up -d metabase   # http://localhost:3000
```

## 测试
```powershell
pytest -v
```

## 数据来源
ERP、AliExpress/IXSPY、Seerfar/Ozon API probe/fetch 均已在本项目内置，分别输出到
`input/erp/<品类>/`、`input/aliexpress/<品类>/`、`input/seerfar/<品类>/`。
`C:\Users\aibp\Desktop\518` 仍可作为历史数据和匹配结果桥接来源。
