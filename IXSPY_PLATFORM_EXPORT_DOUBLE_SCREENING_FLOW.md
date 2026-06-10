# IXSPY平台下载包双筛流程说明

本文档说明从 IXSPY 手动下载的外部商品数据包开始，如何解析外部商品、调用 ERP 以图搜索做粗筛、再用本地图片模型精筛，最后生成老板版报告。

## 目标

把平台下载包里的竞品数据保留下来，同时追加 ERP 匹配结果，形成可决策的老板版 Excel：

- 原平台字段保留：商品名、价格、销量、评论、店铺、商品链接、分类路径等。
- 竞品图片信息保留：本地图片路径、反推出来的线上图片链接。
- ERP 粗筛结果追加：ERP 候选 SKU、主 SKU、商品状态、ERP 候选图、ERP 图搜相似度。
- 模型精筛结果追加：DINOv2 图片相似度、匹配判定、老板建议。

最终重点文件是：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/boss_report.xlsx
```

## 目录约定

每个手动下载品类先整理到项目输入目录：

```text
input/platform_exports/ixspy/<product_type>/<batch>/
  source.xls
  images/
  metadata.yaml
```

示例：

```text
input/platform_exports/ixspy/home_decoration/2026-06-09_week/
  source.xls
  images/
  metadata.yaml
```

输出目录固定为：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/
```

中间工作目录为：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/_work/
```

## metadata.yaml 模板

每个新品类需要一份 `metadata.yaml`。其中最常改的是 `product_type`、`product_type_name`、`original_source.directory`、`original_source.table_file`。

```yaml
platform: ixspy
product_type: home_decoration
product_type_name: 家装
source: 速卖通产品-新品增长榜
period_type: week
period: 2026-06-01_to_2026-06-07
downloaded_at: 2026-06-09
original_source:
  directory: D:\IXSPY下载数据\家装\Product_2026_6_9_15_26_11_week\Product_2026_6_9_15_26_11_week
  table_file: Product_2026_6_9_15_26_11_week.xls
standardized_files:
  table_file: source.xls
  image_dir: images
image_url_infer:
  enabled: true
  base_url: https://ae-pic-a1.aliexpress-media.com/kf/
notes:
  - source.xls uses an HTML table format with a .xls extension.
  - Keep original platform fields, then append ERP image-search and rerank result columns in derived reports.
```

`product_type` 是英文目录名，建议稳定使用小写加下划线，例如：

```text
home_goods
safety_protection
office_education
clothing_accessories
home_decoration
```

`product_type_name` 是老板报告里展示的中文品类名。

## 第一步：整理下载包

IXSPY 下载包通常是嵌套目录：

```text
D:\IXSPY下载数据\<中文品类>\Product_xxx_week\Product_xxx_week\
  Product_xxx_week.xls
  images/
```

整理方式：

1. 把 `Product_xxx_week.xls` 复制成项目输入目录里的 `source.xls`。
2. 把 `images` 整个目录复制到项目输入目录。
3. 写入 `metadata.yaml`。

示例：

```powershell
New-Item -ItemType Directory -Force -Path "D:\ProductSourcingSystem\input\platform_exports\ixspy\home_decoration\2026-06-09_week"

Copy-Item -LiteralPath "D:\IXSPY下载数据\家装\Product_2026_6_9_15_26_11_week\Product_2026_6_9_15_26_11_week\Product_2026_6_9_15_26_11_week.xls" `
  -Destination "D:\ProductSourcingSystem\input\platform_exports\ixspy\home_decoration\2026-06-09_week\source.xls" -Force

robocopy "D:\IXSPY下载数据\家装\Product_2026_6_9_15_26_11_week\Product_2026_6_9_15_26_11_week\images" `
  "D:\ProductSourcingSystem\input\platform_exports\ixspy\home_decoration\2026-06-09_week\images" /E
```

如果后续遇到同一个品类、同一个批次，直接覆盖这个批次目录即可。

## 第二步：外部商品解析

外部商品解析入口：

```text
src/sourcing/platform_export_pipeline.py
```

关键函数：

```text
read_platform_export()
prepare_standard_input()
infer_aliexpress_image_url()
```

解析逻辑：

1. 读取 `source.xls`。
2. 这个 `.xls` 实际是 HTML 表格，不是真正的 Excel 二进制文件。
3. 用正则从 HTML 中提取图片文件名：

```text
<img src="./images/xxx.jpg">
```

4. 用 `pandas.read_html()` 解析表格字段。
5. 读取 `metadata.yaml` 中的 `product_type_name`，写入标准化类目。
6. 根据图片文件名反推 AliExpress 图片链接：

```text
https://ae-pic-a1.aliexpress-media.com/kf/<filename>
```

7. 生成标准化 CSV：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/standardized_aliexpress_products.csv
```

标准化字段定义在：

```text
src/sourcing/platform_export_pipeline.py
STANDARD_FIELDS
```

主要字段包括：

```text
source_rank
sku
product_name
brand
category
image_url
local_image_path
price
product_url
sales_1y
sales_7d
comments_1y
rating
weekly_growth
first_found_at
avg_daily_sales_1y
fulfillment_type
seller_name
seller_url
category_path
```

准备命令：

```powershell
$env:COLLECT_518_DIR="D:\ProductSourcingSystem"

python -m sourcing.cli platform-export-prepare `
  --platform ixspy `
  --product-type home_decoration `
  --batch 2026-06-09_week
```

准备完成后建议检查：

```powershell
python -X utf8 -c "import pandas as pd, os; p=r'D:\ProductSourcingSystem\output\platform_export_match\ixspy\home_decoration\2026-06-09_week\standardized_aliexpress_products.csv'; df=pd.read_csv(p); print(df.shape); print(df['category'].value_counts(dropna=False).to_dict()); print('missing_local_path', int((df['local_image_path'].fillna('')=='').sum())); print('missing_local_file', int(sum(not os.path.exists(x) for x in df['local_image_path'].fillna('') if x))); print('missing_image_url', int((df['image_url'].fillna('')=='').sum()))"
```

正常状态应接近：

```text
1000 行
category 全部等于中文品类名
missing_local_path = 0
missing_local_file = 0
missing_image_url = 0
```

## 第三步：ERP以图搜索粗筛

ERP 图搜代码入口：

```text
src/sourcing/erp_image_search.py
```

关键函数：

```text
run_image_search()
output_csv_path()
RESULT_FIELDS
```

调用方式：

1. 读取标准化后的外部商品 CSV。
2. 使用 `image_url` 调用 ERP 以图搜索接口。
3. 每个外部商品写入 ERP 候选结果。
4. 输出粗筛 CSV：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/_work/output/image_search/ixspy/<product_type>/erp_image_search_results.csv
```

正式输出目录里会复制一份：

```text
output/platform_export_match/ixspy/<product_type>/<batch>/raw_erp_image_search.csv
```

ERP 图搜接口配置来自环境变量：

```text
ERP_IMAGE_SEARCH_BY_URL_URL
ERP_IMAGE_SEARCH_BY_URL_TOKEN
```

注意：文档、代码、报告中不要写入真实 token、cookie 或账号密码。

## 第四步：本地模型精筛

精筛代码入口：

```text
src/sourcing/rerank/embed.py
```

关键函数：

```text
rerank_image_search()
build_embedder()
embed_source()
```

精筛逻辑：

1. 对外部商品图生成图片 embedding。
2. 对 ERP 候选图生成图片 embedding。
3. 计算两张图的余弦相似度。
4. 写入：

```text
embedding_similarity
embedding_confident
embedding_error
```

当前默认高置信阈值：

```text
0.85
```

本地模型依赖 `D:\518` 里的图片模型和缓存逻辑，所以运行时要设置：

```powershell
$env:EMBEDDING_REPO_DIR="D:\518"
```

如果以后完全迁移掉 `D:\518`，需要把 embedding 模型、缓存、图片下载逻辑也迁到当前项目，并调整 `EMBEDDING_REPO_DIR` 默认值。

## 第五步：生成老板版报告

报告生成仍在：

```text
src/sourcing/platform_export_pipeline.py
```

关键函数：

```text
write_final_reports()
_best_result_by_sku()
_match_verdict()
_boss_advice()
```

同时会调用：

```text
src/sourcing/erp_image_search.py
generate_boss_decision_report()
generate_best_match_report()
boss_decision_csv_path()
best_match_csv_path()
```

最终输出：

```text
boss_report.xlsx
matched_report.csv
raw_erp_image_search.csv
boss_decision_report.csv
best_match_report.csv
standardized_aliexpress_products.csv
```

老板版 Excel 主要追加列：

```text
竞品图片链接
竞品本地图片
标准化SKU
标准化类目
近一年日均销量
ERP搜索状态
最像ERP_SKU
ERP主SKU
ERP商品状态
ERP候选图
ERP以图搜索相似度
模型精筛相似度
匹配判定
老板建议
图搜错误信息
```

匹配判定规则：

```text
模型精筛相似度 >= 0.85: 高置信匹配
模型精筛相似度 >= 0.70: 可能匹配
模型精筛相似度 >= 0.50: 弱匹配(需人工)
模型精筛相似度 <  0.50: 无匹配(疑似不同款)
没有有效图片或精筛失败: 无图或精筛失败
```

老板建议规则：

```text
ERP 图搜失败: 图搜失败，需补搜或人工确认
高置信匹配: 疑似ERP已有同款，确认后不建议作为新品开发
0.50 到 0.85: 存在相似款，建议人工复核差异点
低于 0.50: 疑似新品机会，可进入选品池继续评估
```

## 一键跑完整双筛

先设置环境变量：

```powershell
$env:COLLECT_518_DIR="D:\ProductSourcingSystem"
$env:EMBEDDING_REPO_DIR="D:\518"
$env:ERP_IMAGE_SEARCH_BY_URL_URL="<ERP图搜接口地址>"
$env:ERP_IMAGE_SEARCH_BY_URL_TOKEN="<ERP图搜token>"
```

然后运行：

```powershell
python -m sourcing.cli platform-export-pipeline `
  --platform ixspy `
  --product-type home_decoration `
  --batch 2026-06-09_week `
  --delay 0.1 `
  --threshold 0.85
```

参数说明：

```text
--product-type  对应输入输出目录里的英文品类名
--batch         对应批次目录名
--delay         每次 ERP 图搜之间的等待秒数
--threshold     模型精筛高置信阈值
--limit         可选，小样本测试时使用，例如 --limit 30
```

## 中断后继续精筛和报告

如果 ERP 粗筛已经完成，但精筛或报告生成中断，可以用：

```powershell
$env:COLLECT_518_DIR="D:\ProductSourcingSystem"
$env:EMBEDDING_REPO_DIR="D:\518"

python -m sourcing.cli platform-export-finalize `
  --platform ixspy `
  --product-type home_decoration `
  --batch 2026-06-09_week `
  --threshold 0.85 `
  --chunk-size 25
```

这个命令不会重新调用 ERP 图搜，主要用于继续模型精筛和重新生成最终报告。

## 结果核验

报告生成后建议检查：

```powershell
python -X utf8 -c "import pandas as pd; base=r'D:\ProductSourcingSystem\output\platform_export_match\ixspy\home_decoration\2026-06-09_week'; raw=pd.read_csv(base+r'\raw_erp_image_search.csv'); print('raw_rows', len(raw)); print('match_status', raw['match_status'].value_counts(dropna=False).to_dict()); print('embedding_nonempty', (raw.get('embedding_similarity','').fillna('')!='').sum() if 'embedding_similarity' in raw else 'NA')"

python -X utf8 -c "import pandas as pd; p=r'D:\ProductSourcingSystem\output\platform_export_match\ixspy\home_decoration\2026-06-09_week\boss_report.xlsx'; df=pd.read_excel(p); print('shape', df.shape); print('标准化类目', df['标准化类目'].value_counts(dropna=False).to_dict()); print('匹配判定', df['匹配判定'].value_counts(dropna=False).to_dict()); print('老板建议', df['老板建议'].value_counts(dropna=False).to_dict())"
```

项目级测试：

```powershell
python -m pytest
```

当前测试里 `.pytest_cache` 可能有权限警告，只要结果是 `passed`，不影响双筛报告。

## 新品类复用步骤

后续换一个 IXSPY 手动下载品类，只需要按下面做：

1. 选择英文 `product_type`，例如 `pet_supplies`。
2. 建目录：

```text
input/platform_exports/ixspy/pet_supplies/2026-06-09_week/
```

3. 放入：

```text
source.xls
images/
metadata.yaml
```

4. 修改 `metadata.yaml`：

```text
product_type
product_type_name
original_source.directory
original_source.table_file
period
downloaded_at
```

5. 先跑 prepare 检查行数和图片。
6. 再跑 `platform-export-pipeline`。
7. 打开 `boss_report.xlsx` 看老板版结果。

## 已知注意事项

- IXSPY 导出的 `.xls` 实际是 HTML 表格，解析依赖 `pandas.read_html()`。
- 图片链接是根据本地图片文件名反推出来的，依赖当前 AliExpress 图片 CDN 规则。
- ERP 粗筛依赖 ERP 图搜接口和有效 token。
- 模型精筛依赖 `D:\518` 的 embedding 相关代码和缓存。
- 如果某条商品 ERP 图搜失败，最终报告仍保留原始竞品行，并在 `图搜错误信息` 和 `老板建议` 中标记。
- 如果本地图片数量少于 1000，但表格中的图片引用都能对应到实际文件，则不影响流程。部分导出包可能存在重复图片文件名。
