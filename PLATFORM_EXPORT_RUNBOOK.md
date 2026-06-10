# 平台下载包双筛 · 全手动操作手册

> 适用场景：从 **IXSPY 手动下载**的竞品数据包（`.xls` + `images/`）开始，
> 一步步处理 → 解析 → ERP 以图搜索粗筛 → DINOv2 本地模型精筛 → 产出**老板版报告**。
>
> 终端：**PowerShell**，工作目录始终为 `D:\ProductSourcingSystem`。
> 换一个新下载包，只需改第 0 节的 4 个变量，其余命令照抄。

---

## 目录

- [0. 每次开始前：定义 4 个变量](#0-每次开始前定义-4-个变量)
- [1. 整理下载包 → 项目输入目录](#1-整理下载包--项目输入目录)
- [2. 写 metadata.yaml](#2-写-metadatayaml)
- [3. 设置环境变量](#3-设置环境变量)
- [4. 解析 + 校验（离线）](#4-解析--校验离线)
- [5. ERP token 刷新（按需）](#5-erp-token-刷新按需)
- [6. 小样本验证双筛](#6-小样本验证双筛)
- [7. 全量双筛 + 出报告](#7-全量双筛--出报告)
- [8. 核验最终报告](#8-核验最终报告)
- [9. 报告产物清单](#9-报告产物清单)
- [流程总览图](#流程总览图)
- [报告字段与判定规则](#报告字段与判定规则)
- [常见问题排查](#常见问题排查)
- [一页速记](#一页速记)

---

## 前置条件（首次确认一次）

- `.env` 已配置：
  - `ERP_IMAGE_SEARCH_URL` + `ERP_IMAGE_SEARCH_TOKEN`（ERP 以图搜索；上传模式）
  - `ERP_USERNAME` / `ERP_PASSWORD`（token 过期时自动重登刷新要用）
- Chrome + chromedriver 可用（token 刷新会开浏览器）
- 嵌入缓存已迁移到 SQLite（一次性，已完成）：
  `python -m sourcing.cli migrate-embedding-cache`
- 依赖 `D:\518` 的 DINOv2 嵌入代码与模型缓存就位

---

## 0. 每次开始前：定义 4 个变量

在 PowerShell 顶部跑一次（**换包只改这 4 行**）：

```powershell
cd D:\ProductSourcingSystem

# ① 下载解压后含 .xls 和 images 的最内层目录
$SRC   = "D:\IXSPY下载数据\男女内衣及家居服\Product_2026_6_10_9_02_55_week\Product_2026_6_10_9_02_55_week"
# ② 英文 slug：决定输入/输出文件夹名（小写+下划线）
$PT    = "underwear_homewear"
# ③ 批次名
$BATCH = "2026-06-10_week"
# ④ 老板报告里显示的中文品类名
$NAME  = "男女内衣及家居服"

# 自动推导（不用改）
$DST  = "D:\ProductSourcingSystem\input\platform_exports\ixspy\$PT\$BATCH"
$BASE = "D:\ProductSourcingSystem\output\platform_export_match\ixspy\$PT\$BATCH"
```

> IXSPY 下载包通常是嵌套目录：
> `D:\IXSPY下载数据\<中文品类>\Product_xxx_week\Product_xxx_week\{Product_xxx_week.xls, images\}`
> `$SRC` 要指到**最内层**那个含 `.xls` 和 `images` 的目录。

---

## 1. 整理下载包 → 项目输入目录

```powershell
New-Item -ItemType Directory -Force -Path $DST | Out-Null

# .xls → source.xls（把下面的文件名换成你包里实际的 .xls 名）
Copy-Item -LiteralPath "$SRC\Product_2026_6_10_9_02_55_week.xls" -Destination "$DST\source.xls" -Force

# images 整个目录复制过去
robocopy "$SRC\images" "$DST\images" /E | Out-Null
```

目标结构：

```text
input\platform_exports\ixspy\<slug>\<批次>\
  source.xls
  images\
  metadata.yaml   ← 下一步生成
```

---

## 2. 写 metadata.yaml

```powershell
@"
platform: ixspy
product_type: $PT
product_type_name: $NAME
source: 速卖通产品-新品增长榜
period: $BATCH
downloaded_at: 2026-06-10
original_source:
  directory: $SRC
  table_file: source.xls
standardized_files:
  table_file: source.xls
  image_dir: images
image_url_infer:
  enabled: true
  base_url: https://ae-pic-a1.aliexpress-media.com/kf/
"@ | Out-File -FilePath "$DST\metadata.yaml" -Encoding utf8
```

> 也可用记事本手写 `$DST\metadata.yaml`。最关键字段：`product_type`、`product_type_name`。

---

## 3. 设置环境变量

**每开一个新 PowerShell 窗口都要先跑这两行：**

```powershell
$env:COLLECT_518_DIR    = "D:\ProductSourcingSystem"   # 输入/输出落在本项目下
$env:EMBEDDING_REPO_DIR = "D:\518"                     # DINOv2 嵌入代码在 518
```

> ERP token 从 `.env` 自动读，不用在这里设。

---

## 4. 解析 + 校验（离线）

把 `.xls`（实为 HTML 表格）+ 图片，解析成标准化 CSV。**纯本地、不调接口、很快。**

```powershell
python -X utf8 -m sourcing.cli platform-export-prepare --platform ixspy --product-type $PT --batch $BATCH
```

校验数据健康度：

```powershell
$CSV = "$BASE\standardized_aliexpress_products.csv"
python -X utf8 -c "import pandas as pd,os,sys; df=pd.read_csv(sys.argv[1]); print('行数',len(df)); print('类目',df['category'].value_counts().to_dict()); print('缺图链',int((df['image_url'].fillna('')=='').sum())); print('本地图缺失',int(sum(not os.path.exists(x) for x in df['local_image_path'].fillna('') if x)))" $CSV
```

**正常结果**：

```text
行数 ≈ 1000
类目 全部 = 中文品类名
缺图链 = 0
本地图缺失 ≈ 0   （少量错位可接受：图片数<行数时会有几条对不上，会被自动标记）
```

---

## 5. ERP token 刷新（按需）

若第 6 步图搜结果全是 `Not Found` / 匹配数为 0 → token 过期。手动刷新（会开一次 Chrome 自动登录 ERP）：

```powershell
python -X utf8 -c "from sourcing.erp_token import refresh_erp_token; print('token len', len(refresh_erp_token(r'D:\ProductSourcingSystem')))"
```

输出 `token len 298` 即成功，新 token 已写入 `.env`。

> 现已内置自愈：长跑中途 token 过期会**自动刷新并续跑**，无需盯着。这条主要用于开跑前主动刷一次。

---

## 6. 小样本验证双筛

**强烈建议先跑 30 条**确认链路通，再跑全量：

```powershell
python -X utf8 -m sourcing.cli platform-export-pipeline --platform ixspy --product-type $PT --batch $BATCH --limit 30 --delay 0.1 --threshold 0.85
```

看输出末尾 JSON：

```text
search.searched = 30
best.verdicts   = { 高置信匹配: x, 可能匹配: x, 弱匹配(需人工): x, 无匹配(疑似不同款): x }
final.matched   = 30
```

有分布、`matched=30` → 链路正常，进入全量。
若全是 `无图(竞品图失败)` 或 `matched=0` → 回[第 5 步](#5-erp-token-刷新按需)刷 token 再试。

---

## 7. 全量双筛 + 出报告

```powershell
python -X utf8 -m sourcing.cli platform-export-pipeline --platform ixspy --product-type $PT --batch $BATCH --delay 0.1 --threshold 0.85
```

- 1000 商品约 **45–60 分钟**
- 中途 token 过期会自动刷新续跑

**中断恢复**（图搜已完成、精筛/报告断了，**不重调 ERP 图搜**）：

```powershell
python -X utf8 -m sourcing.cli platform-export-finalize --platform ixspy --product-type $PT --batch $BATCH --threshold 0.85 --chunk-size 25
```

### 参数说明

| 参数 | 含义 | 建议 |
|---|---|---|
| `--limit` | 只跑前 N 条（小样本） | 验证用 30 |
| `--delay` | 每次 ERP 图搜间隔秒数 | 0.1 |
| `--threshold` | 精筛高置信阈值 | 0.85 |
| `--chunk-size` | finalize 每批精筛条数 | 25 |

---

## 8. 核验最终报告

```powershell
python -X utf8 -c "import pandas as pd,glob,sys; x=sorted(glob.glob(sys.argv[1]+r'\*.xlsx'))[-1]; df=pd.read_excel(x); print('报告:',x); print('行数:',df.shape); print('匹配判定:',df['匹配判定'].value_counts().to_dict()); print('老板建议:',df['老板建议'].value_counts().to_dict())" $BASE
```

---

## 9. 报告产物清单

全部在 `output\platform_export_match\ixspy\<slug>\<批次>\`：

| 文件 | 用途 |
|---|---|
| **`<中文品类>_<时间戳>.xlsx`** | ⭐**老板版报告**：竞品全字段 + ERP 匹配 + 精筛相似度 + 匹配判定 + 老板建议 |
| `boss_report.xlsx` | 老板版（同内容） |
| `matched_report.csv` | 明细 CSV |
| `raw_erp_image_search.csv` | 每条图搜 + 精筛原始结果 |
| `standardized_aliexpress_products.csv` | 第 4 步解析出的标准化竞品 |
| `_work\` | 中间工作目录（图搜/精筛中间产物） |

---

## 流程总览图

```text
$SRC: D:\IXSPY下载数据\<中文品类>\...\{xls, images}
        │  第1步 整理 + 第2步 metadata
        ▼
input\platform_exports\ixspy\<slug>\<批次>\{source.xls, images\, metadata.yaml}
        │  第4步 platform-export-prepare（解析 .xls=HTML + 反推图链 + 本地图配对）
        ▼
standardized_aliexpress_products.csv（标准化竞品，1000 行）
        │  第6/7步 platform-export-pipeline
        │   ├─ 层1 ERP 以图搜索（粗筛，返回候选 ERP SKU + 候选图）
        │   └─ 层2 DINOv2 精筛（竞品图 × ERP候选图 余弦相似度）
        ▼
output\platform_export_match\ixspy\<slug>\<批次>\<中文品类>_<时间戳>.xlsx  ← 老板版报告
```

---

## 报告字段与判定规则

**老板版主要追加列**：竞品图片链接、竞品本地图片、标准化SKU、标准化类目、近一年日均销量、
ERP搜索状态、最像ERP_SKU、ERP主SKU、ERP商品状态、ERP候选图、ERP以图搜索相似度、
模型精筛相似度、匹配判定、老板建议、图搜错误信息。

**匹配判定**（按模型精筛相似度）：

| 相似度 | 判定 |
|---|---|
| ≥ 0.85 | 高置信匹配 |
| 0.70 – 0.85 | 可能匹配 |
| 0.50 – 0.70 | 弱匹配(需人工) |
| < 0.50 | 无匹配(疑似不同款) |
| 无有效图/精筛失败 | 无图或精筛失败 |

**老板建议**：

| 情况 | 建议 |
|---|---|
| ERP 图搜失败 | 图搜失败，需补搜或人工确认 |
| 高置信匹配 | 疑似 ERP 已有同款，确认后不建议作为新品开发 |
| 0.50 – 0.85 | 存在相似款，建议人工复核差异点 |
| < 0.50 | **疑似新品机会，可进入选品池继续评估** |

---

## 常见问题排查

| 现象 | 原因 / 处理 |
|---|---|
| 图搜全是 `Not Found` / `matched=0` | ERP token 过期 → [第 5 步](#5-erp-token-刷新按需)刷新（现也会自动自愈） |
| `无图(竞品图失败)` 偏多 | 反推的图链取不到图，或本地图缺失；检查第 4 步"本地图缺失"数 |
| `本地图缺失` 较大 | 图片数 < 行数导致按行号配对错位；下载包不全，重新下载或忽略少量 |
| 精筛很慢 / 卡 | 首次会下载竞品图并算嵌入；确认已 `migrate-embedding-cache`，内存恒定 |
| `.xls 打不开` | 它本就是 HTML 表格，不是真 Excel；解析靠 `pandas.read_html()`，正常 |
| 中途中断 | 用 `platform-export-finalize` 续跑，不重调 ERP 图搜 |

---

## 一页速记

```powershell
cd D:\ProductSourcingSystem
# 改这 4 行 ↓
$SRC="D:\IXSPY下载数据\男女内衣及家居服\...\..."; $PT="underwear_homewear"; $BATCH="2026-06-10_week"; $NAME="男女内衣及家居服"
$DST="D:\ProductSourcingSystem\input\platform_exports\ixspy\$PT\$BATCH"; $BASE="D:\ProductSourcingSystem\output\platform_export_match\ixspy\$PT\$BATCH"

# 1 整理
New-Item -ItemType Directory -Force -Path $DST | Out-Null
Copy-Item -LiteralPath "$SRC\<你的xls名>.xls" -Destination "$DST\source.xls" -Force
robocopy "$SRC\images" "$DST\images" /E | Out-Null
# 2 metadata.yaml（见第 2 节）
# 3 环境变量
$env:COLLECT_518_DIR="D:\ProductSourcingSystem"; $env:EMBEDDING_REPO_DIR="D:\518"
# 4 解析校验
python -X utf8 -m sourcing.cli platform-export-prepare --platform ixspy --product-type $PT --batch $BATCH
# 6 小样本验证
python -X utf8 -m sourcing.cli platform-export-pipeline --platform ixspy --product-type $PT --batch $BATCH --limit 30 --delay 0.1 --threshold 0.85
# 7 全量
python -X utf8 -m sourcing.cli platform-export-pipeline --platform ixspy --product-type $PT --batch $BATCH --delay 0.1 --threshold 0.85
# 8 核验 → 9 取 $BASE 下的 <中文品类>_<时间戳>.xlsx
```

---

*配套文档：`IXSPY_PLATFORM_EXPORT_DOUBLE_SCREENING_FLOW.md`（流程原理/代码入口说明）、`RUNBOOK.md`（自动采集线 run-product）。*
```
