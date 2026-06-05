# ERP 以图搜索预筛选

用 Seerfar/Ozon 或 AliExpress/IXSPY CSV 里的 `image_url` 调用 ERP 图片搜索接口，快速判断平台商品是否疑似已有 ERP 同款。

这个步骤只生成预筛选 CSV，不会影响原采集、导入、分析和 518 桥接流程。

## 配置

先在 `.env` 填写：

```powershell
ERP_IMAGE_SEARCH_URL=http://103.198.125.2:8077/Api/prodetail/picSearchFunds
ERP_IMAGE_SEARCH_TOKEN=你的可用ERP接口token
```

不要把真实 token 提交到代码、文档或测试里。

## 小样本运行

```powershell
cd D:\ProductSourcingSystem
python -m sourcing.cli erp-image-search --source seerfar --product-type training_mask --limit 20 --delay 0.5
python -m sourcing.cli erp-image-search --source ixspy --product-type bag_accessories --limit 20 --delay 0.5
```

输出到：

```text
output\image_search\<source>\<product_type>\erp_image_search_results.csv
```

建议先跑 20 条人工核验准确率，再决定是否把结果写入 `product_matches` 作为正式查重加速层。

## 输出字段

```text
source
product_type
external_sku
external_product_name
external_product_url
external_image_url
match_status
matched_erp_sku
matched_main_sku
erp_product_status
erp_image_url
similarity
message
code
trace_id
searched_at
raw_json
```
