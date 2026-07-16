# ERP 以图搜索预筛选

用 SeerFar、IXSPY、AliExpress CSV 里的 `image_url` 调用 ERP 以图搜索接口，先生成 ERP 候选，再交给 DINOv2 做第二层精筛。

## 配置

真实 token、账号、密码只放 `.env` 或当前终端环境变量，不写进代码、文档和测试。

```powershell
ERP_IMAGE_SEARCH_TOKEN=你的ERP后台Authorization
ERP_IMAGE_SEARCH_BY_URL_TOKEN=你的ERP开放接口Authorization
ERP_IMAGE_SEARCH_TOP_N=10
ERP_IMAGE_SEARCH_ENRICH_SUB_SKUS=1
```

可选接口地址：

```powershell
ERP_IMAGE_SEARCH_BY_URL_URL=http://103.198.125.2:16777/open/pic/searchProductsByPicUrl
ERP_IMAGE_SEARCH_BY_URL_LEGACY_URL=http://103.198.125.2:16777/open/pic/searchProductByPicUrl
ERP_IMAGE_SEARCH_URL=http://103.198.125.2:8077/Api/prodetail/picSearchFunds
ERP_SUB_SKU_URL=http://103.198.125.2:8077/Api/progroup/findSonSku
```

默认策略：

- 优先用 URL 以图搜索，多结果接口 `searchProductsByPicUrl`。
- URL 多结果接口 HTTP 报错时，回退旧 URL 接口 `searchProductByPicUrl`。
- 没有 URL token 时，才下载外部图片并走上传接口 `picSearchFunds`。
- `ERP_IMAGE_SEARCH_ENRICH_SUB_SKUS=1` 时，用主 SKU 调 `findSonSku` 补库存、成本、售价、销量。

## 小样本运行

```powershell
cd D:\ProductSourcingSystem
$env:ERP_IMAGE_SEARCH_TOP_N="10"
$env:ERP_IMAGE_SEARCH_ENRICH_SUB_SKUS="1"
python -m sourcing.cli erp-image-search --source seerfar --product-type <品类slug> --limit 30 --delay 0.5
python -m sourcing.cli erp-image-rerank --source seerfar --product-type <品类slug> --threshold 0.85
python -m sourcing.cli erp-image-match-report --source seerfar --product-type <品类slug>
python -m sourcing.cli seerfar-enriched-report --product-type <品类slug>
```

输入文件位置：

```text
input\seerfar\<品类slug>\seerfar_products.csv
```

输出文件位置：

```text
output\image_search\seerfar\<品类slug>\erp_image_search_results.csv
output\image_search\seerfar\<品类slug>\best_match_report.csv
output\image_search\seerfar\<品类slug>\seerfar_enriched_report.csv
```

SeerFar 老板版报告基于 `input\seerfar\<品类slug>\seerfar_products.csv` 的原始业务字段追加 ERP 匹配信息，最终只保留 `高置信匹配` 和 `可能匹配` 两类，低置信、无匹配、无图和未参与匹配的行仍保留在上游明细结果里用于排查。

## 新增输出字段

```text
match_rank              ERP 候选排名
match_source            候选来源
erp_subsku_count        ERP 子 SKU 数量
erp_total_inventory     ERP 子 SKU 总库存
erp_cost_price          ERP 代表子 SKU 成本价
erp_sell_price          ERP 代表子 SKU 售价
erp_sales_num           ERP 子 SKU 销量合计
erp_subsku_json         ERP 子 SKU 明细 JSON
```

## 注意

SeerFar 数据如果已有图片链接，优先走 URL 搜图。不要一开始就全量下载图片上传，除非 URL 搜图失败率很高。子 SKU 明细只是 ERP 商品信息补充，不等于新的视觉匹配候选。
