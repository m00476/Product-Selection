import csv
import json
from pathlib import Path

import pytest

from sourcing import erp_image_search


def test_load_external_rows_keeps_rows_with_image_url(tmp_path):
    csv_path = tmp_path / "seerfar_products.csv"
    csv_path.write_text(
        "sku,product_name,image_url,product_url,price,sales,review_count\n"
        "A1,Alpha,https://img.example/a.jpg,https://ozon.ru/product/a-1,12.5,300,20\n"
        "B1,Beta,,https://ozon.ru/product/b-2,9.9,10,1\n",
        encoding="utf-8",
    )

    rows = erp_image_search.load_external_rows(csv_path, source="seerfar", product_type="mask")

    assert len(rows) == 1
    assert rows[0]["external_sku"] == "A1"
    assert rows[0]["external_image_url"] == "https://img.example/a.jpg"
    assert rows[0]["external_price"] == "12.5"
    assert rows[0]["external_sales"] == "300"
    assert rows[0]["external_review_count"] == "20"
    assert rows[0]["source"] == "seerfar"
    assert rows[0]["product_type"] == "mask"


def test_normalize_response_exports_one_row_per_match():
    result = erp_image_search.normalize_search_response(
        {
            "code": 200,
            "msg": "操作成功",
            "traceId": "T1",
            "data": [
                {
                    "sku": "ERP-A",
                    "mainsku": "MAIN-A",
                    "url": "https://erp.example/a.jpg",
                    "status": "8",
                    "similarity": 0.91,
                }
            ],
        }
    )

    assert result.status == "success"
    assert result.matches[0]["matched_erp_sku"] == "ERP-A"
    assert result.matches[0]["matched_main_sku"] == "MAIN-A"
    assert result.matches[0]["erp_product_status"] == "8"
    assert result.matches[0]["similarity"] == 0.91
    assert result.trace_id == "T1"


def test_result_rows_include_status_text_and_candidate_priority():
    rows = erp_image_search._result_rows(
        {
            "source": "ixspy",
            "product_type": "bag_accessories",
            "external_sku": "1005",
            "external_product_name": "Handle wrap",
            "external_product_url": "https://example.test/item/1005.html",
            "external_image_url": "https://example.test/img.jpg",
        },
        erp_image_search.SearchResult(
            status="success",
            code=200,
            message="ok",
            trace_id="T1",
            matches=[
                {
                    "matched_erp_sku": "ERP-A",
                    "matched_main_sku": "MAIN-A",
                    "erp_product_status": "8",
                    "erp_image_url": "https://erp.example/a.jpg",
                    "similarity": "",
                },
                {
                    "matched_erp_sku": "ERP-B",
                    "matched_main_sku": "MAIN-B",
                    "erp_product_status": "1",
                    "erp_image_url": "https://erp.example/b.jpg",
                    "similarity": "",
                },
            ],
            raw={"code": 200},
        ),
    )

    assert rows[0]["erp_product_status_text"] == "正常商品"
    assert rows[0]["candidate_priority"] == "可用正常商品"
    assert rows[1]["erp_product_status_text"] == "停产商品"
    assert rows[1]["candidate_priority"] == "疑似同款但停产"


def test_run_image_search_writes_results_and_raw_json(tmp_path):
    input_path = tmp_path / "input" / "seerfar" / "mask" / "seerfar_products.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        "sku,product_name,image_url,product_url\n"
        "A1,Alpha,https://img.example/a.jpg,https://ozon.ru/product/a-1\n",
        encoding="utf-8",
    )

    calls = []

    def fake_search(image_url):
        calls.append(image_url)
        return erp_image_search.SearchResult(
            status="success",
            code=200,
            message="ok",
            trace_id="T1",
            matches=[
                {
                    "matched_erp_sku": "ERP-A",
                    "matched_main_sku": "MAIN-A",
                    "erp_product_status": "8",
                    "erp_image_url": "https://erp.example/a.jpg",
                    "similarity": 0.88,
                }
            ],
            raw={"code": 200, "data": [{"sku": "ERP-A"}]},
        )

    summary = erp_image_search.run_image_search(
        source="seerfar",
        product_type="mask",
        base_dir=tmp_path,
        limit=1,
        search_func=fake_search,
        sleep_func=lambda _seconds: None,
    )

    assert calls == ["https://img.example/a.jpg"]
    assert summary["searched"] == 1
    assert summary["written"] == 1
    output_path = tmp_path / "output" / "image_search" / "seerfar" / "mask" / "erp_image_search_results.csv"
    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        written = list(csv.DictReader(file))
    assert written[0]["external_sku"] == "A1"
    assert written[0]["matched_erp_sku"] == "ERP-A"
    assert json.loads(written[0]["raw_json"])["code"] == 200


def test_run_image_search_records_failed_rows_and_continues(tmp_path):
    input_path = tmp_path / "input" / "seerfar" / "mask" / "seerfar_products.csv"
    input_path.parent.mkdir(parents=True)
    input_path.write_text(
        "sku,product_name,image_url,product_url\n"
        "A1,Alpha,https://img.example/a.jpg,https://ozon.ru/product/a-1\n"
        "B1,Beta,https://img.example/b.jpg,https://ozon.ru/product/b-2\n",
        encoding="utf-8",
    )
    calls = []

    def flaky_search(image_url):
        calls.append(image_url)
        if image_url.endswith("/a.jpg"):
            raise ConnectionResetError("reset")
        return erp_image_search.SearchResult(
            status="success",
            code=200,
            message="ok",
            trace_id="T2",
            matches=[{"matched_erp_sku": "ERP-B", "matched_main_sku": "MAIN-B", "erp_product_status": "8"}],
            raw={"code": 200},
        )

    summary = erp_image_search.run_image_search(
        source="seerfar",
        product_type="mask",
        base_dir=tmp_path,
        limit=2,
        search_func=flaky_search,
        sleep_func=lambda _seconds: None,
        max_retries=1,
    )

    assert summary["searched"] == 2
    output_path = tmp_path / "output" / "image_search" / "seerfar" / "mask" / "erp_image_search_results.csv"
    with output_path.open("r", encoding="utf-8-sig", newline="") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["match_status"] == "error"
    assert rows[0]["candidate_priority"] == "需人工确认"
    assert rows[1]["matched_erp_sku"] == "ERP-B"


def test_build_boss_decision_rows_groups_candidates_by_external_product():
    rows = [
        {
            "source": "ixspy",
            "product_type": "bag_accessories",
            "external_sku": "1005",
            "external_product_name": "Handle wrap",
            "external_product_url": "https://example.test/item/1005.html",
            "external_image_url": "https://example.test/img.jpg",
            "external_price": "12.5",
            "external_sales": "300",
            "external_review_count": "20",
            "matched_erp_sku": "ERP-STOP",
            "matched_main_sku": "STOP",
            "candidate_priority": "疑似同款但停产",
        },
        {
            "source": "ixspy",
            "product_type": "bag_accessories",
            "external_sku": "1005",
            "external_product_name": "Handle wrap",
            "external_product_url": "https://example.test/item/1005.html",
            "external_image_url": "https://example.test/img.jpg",
            "external_price": "12.5",
            "external_sales": "300",
            "external_review_count": "20",
            "matched_erp_sku": "ERP-OK",
            "matched_main_sku": "OK",
            "candidate_priority": "可用正常商品",
        },
        {
            "source": "seerfar",
            "product_type": "mask",
            "external_sku": "2006",
            "external_product_name": "Training mask",
            "external_product_url": "https://example.test/item/2006.html",
            "external_image_url": "https://example.test/mask.jpg",
            "matched_erp_sku": "ERP-OLD",
            "matched_main_sku": "OLD",
            "candidate_priority": "疑似同款但停产",
        },
    ]

    decisions = erp_image_search.build_boss_decision_rows(rows)

    assert decisions[0]["external_sku"] == "1005"
    assert decisions[0]["final_decision"] == "疑似已有正常同款"
    assert decisions[0]["boss_action"] == "先人工确认正常候选；确认同款后不要作为新品开发"
    assert decisions[0]["normal_candidate_count"] == 1
    assert decisions[0]["stopped_candidate_count"] == 1
    assert decisions[0]["external_price"] == "12.5"
    assert decisions[0]["external_sales"] == "300"
    assert decisions[0]["external_review_count"] == "20"
    assert decisions[0]["top_erp_skus"] == "ERP-STOP, ERP-OK"
    assert decisions[1]["external_sku"] == "2006"
    assert decisions[1]["final_decision"] == "有历史停产同款"
    assert decisions[1]["boss_action"] == "查停产原因和供应链；可作为恢复或重新开发机会"


def test_generate_boss_decision_report_writes_csv_and_markdown(tmp_path):
    result_path = tmp_path / "output" / "image_search" / "ixspy" / "bag_accessories" / "erp_image_search_results.csv"
    result_path.parent.mkdir(parents=True)
    result_path.write_text(
        "source,product_type,external_sku,external_product_name,external_product_url,external_image_url,"
        "external_price,external_sales,external_sales_1y,external_sales_7d,external_review_count,"
        "external_comments_1y,external_weekly_growth,external_first_found_at,external_avg_daily_sales_1y,"
        "external_fulfillment_type,matched_erp_sku,matched_main_sku,candidate_priority\n"
        "ixspy,bag_accessories,1005,Handle wrap,https://example.test/item/1005.html,"
        "https://example.test/img.jpg,12.5,300,300,45,20,20,12,2026-04-20,1,半托管,ERP-OK,OK,可用正常商品\n",
        encoding="utf-8-sig",
    )

    summary = erp_image_search.generate_boss_decision_report(
        source="ixspy",
        product_type="bag_accessories",
        base_dir=tmp_path,
    )

    assert summary["products"] == 1
    with open(summary["csv"], "r", encoding="utf-8-sig", newline="") as file:
        csv_rows = list(csv.DictReader(file))
    assert "系统判断" in csv_rows[0]
    assert "final_decision" not in csv_rows[0]
    assert csv_rows[0]["系统判断"] == "疑似已有正常同款"
    assert csv_rows[0]["外部平台价格"] == "12.5"
    assert csv_rows[0]["外部平台累计销量"] == "300"
    assert csv_rows[0]["近一年销量"] == "300"
    assert csv_rows[0]["近7天销量"] == "45"
    assert csv_rows[0]["近一年评论数"] == "20"
    assert csv_rows[0]["周增长数"] == "12"
    assert csv_rows[0]["首次发现时间"] == "2026-04-20"
    assert csv_rows[0]["近一年日均销量"] == "1"
    assert csv_rows[0]["托管类型"] == "半托管"
    assert csv_rows[0]["ERP正常同款数量"] == "1"
    markdown = Path(summary["markdown"]).read_text(encoding="utf-8")
    assert "ERP 以图搜索老板决策报告" in markdown
    assert "Handle wrap" in markdown
    assert "300" in markdown


def test_boss_decision_fields_all_have_chinese_labels():
    missing = [
        field for field in erp_image_search.BOSS_DECISION_FIELDS
        if field not in erp_image_search.BOSS_DECISION_FIELD_LABELS
    ]
    assert missing == []


def test_client_requires_token(monkeypatch):
    monkeypatch.delenv("ERP_IMAGE_SEARCH_BY_URL_TOKEN", raising=False)
    monkeypatch.delenv("ERP_IMAGE_SEARCH_TOKEN", raising=False)
    with pytest.raises(RuntimeError, match="ERP_IMAGE_SEARCH_TOKEN"):
        erp_image_search.ErpImageSearchClient(token="")


def test_normalize_classifies_status_404_as_auth_error():
    """ERP 鉴权失败返回 {"status":404,...}(无 code 字段)，应判为 error 且 code=404，
    这样 _is_auth_failure 能触发自动刷新（之前被误判成 empty 导致不刷新）。"""
    from sourcing.erp_image_search import normalize_search_response, _is_auth_failure
    payload = {"error": "Not Found", "message": "Not Found",
               "path": "/prodetail/picSearchFunds", "status": 404}
    result = normalize_search_response(payload)
    assert result.status == "error"
    assert result.code == 404
    assert _is_auth_failure(result) is True


def test_refresh_image_search_client_updates_url_search_token(monkeypatch):
    from sourcing import erp_image_search as e

    class FakeLoginClient:
        def __init__(self, timeout):
            assert timeout == 15

        def _login(self):
            return "fresh-token"

    class SearchClient:
        timeout = 15
        token = "old-token"
        url_api_token = "old-url-token"

    monkeypatch.setattr(e, "ErpSubSkuClient", FakeLoginClient)
    client = SearchClient()

    assert e.refresh_image_search_client_token(client) == "fresh-token"
    assert client.token == "fresh-token"
    assert client.url_api_token == "fresh-token"


def test_normalize_keeps_success_with_code_200():
    from sourcing.erp_image_search import normalize_search_response
    payload = {"code": 200, "data": [{"sku": "E1", "url": "u1"}]}
    result = normalize_search_response(payload)
    assert result.status == "success"
    assert result.code == 200


def test_search_retries_temporary_erp_response_error():
    calls = []
    sleeps = []

    def search(_image_url):
        calls.append("called")
        if len(calls) == 1:
            return erp_image_search.SearchResult(
                status="error", code=429, message="too many requests", trace_id="", matches=[], raw={}
            )
        return erp_image_search.SearchResult(
            status="success", code=200, message="ok", trace_id="", matches=[], raw={}
        )

    result = erp_image_search._search_with_retries(
        search,
        "https://img.example/a.jpg",
        max_retries=3,
        sleep_func=sleeps.append,
    )

    assert result.status == "success"
    assert len(calls) == 2
    assert sleeps == [2]


def test_url_search_body_includes_topn_aliases():
    body = erp_image_search.build_url_search_body("https://img.example/a.jpg", top_n=12)

    assert body["picUrl"] == "https://img.example/a.jpg"
    for key in ("topN", "topK", "limit", "pageSize", "size", "count", "top_num"):
        assert body[key] == 12


def test_url_search_request_url_includes_topn_aliases():
    url = erp_image_search.build_url_search_request_url(
        "http://erp.example/open/pic/searchProductsByPicUrl?limit=3",
        top_n=12,
    )

    assert "limit=3" in url
    for item in ("topN=12", "topK=12", "pageSize=12", "size=12", "count=12", "top_num=12"):
        assert item in url


def test_normalize_handles_nested_topn_results_and_field_aliases():
    result = erp_image_search.normalize_search_response(
        {
            "code": 200,
            "data": {
                "records": [
                    {
                        "picName": "ERP-B",
                        "mainSkuCode": "MAIN-B",
                        "imgUrl": "https://erp.example/b.jpg",
                        "productStatus": "1",
                        "similarScore": "0.72",
                    },
                    {
                        "sku": "ERP-A",
                        "mainSKu": "MAIN-A",
                        "fileUrl": "https://erp.example/a.jpg",
                        "status": "8",
                        "score": 0.91,
                    },
                ]
            },
        }
    )

    assert result.status == "success"
    assert [match["matched_erp_sku"] for match in result.matches] == ["ERP-A", "ERP-B"]
    assert result.matches[0]["match_rank"] == 1
    assert result.matches[0]["matched_main_sku"] == "MAIN-A"
    assert result.matches[1]["matched_main_sku"] == "MAIN-B"
    assert result.matches[1]["similarity"] == 0.72


def test_enrich_matches_with_sub_skus_adds_inventory_cost_and_sales():
    matches = [
        {"matched_erp_sku": "ERP-A", "matched_main_sku": "MAIN-A"},
        {"matched_erp_sku": "ERP-B", "matched_main_sku": "MAIN-B"},
    ]

    def fetcher(main_sku):
        return {
            "MAIN-A": [
                {
                    "sku": "ERP-A-RED",
                    "skucolor": "red",
                    "status": "8",
                    "inventory": 7,
                    "costprice": 3.4,
                    "skusell": 9.9,
                    "salesnum": 20,
                },
                {"sku": "ERP-A-BLUE", "totalinventory": 5, "costprice": 3.6, "singledaysales": 2},
            ],
            "MAIN-B": [],
        }[main_sku]

    enriched = erp_image_search.enrich_matches_with_sub_skus(matches, fetcher)

    assert enriched[0]["erp_subsku_count"] == 2
    assert enriched[0]["erp_total_inventory"] == 12
    assert enriched[0]["erp_cost_price"] == 3.4
    assert enriched[0]["erp_sell_price"] == 9.9
    assert enriched[0]["erp_sales_num"] == 22
    assert enriched[0]["erp_product_status"] == "8"
    assert "ERP-A-RED" in enriched[0]["erp_subsku_json"]
    assert enriched[1]["erp_subsku_count"] == 0


def test_sku_lookup_key_matches_plugin_normalization():
    assert erp_image_search.normalize_sku_lookup_key("G-SH-WAC-225-ND") == "GSHWAC225ND"
    assert erp_image_search.normalize_sku_lookup_key("gshwac225nd") == "GSHWAC225ND"
    assert erp_image_search.get_product_list_query_values("G-SH-WAC-225") == [
        "G-SH-WAC-225",
        "GSHWAC225",
    ]


def test_select_sub_sku_uses_normalized_sku_key():
    selected = erp_image_search._select_sub_sku(
        "G-SH-WAC-225-ND",
        [{"sku": "OTHER"}, {"sku": "GSHWAC225ND", "inventory": 9}],
    )

    assert selected["sku"] == "GSHWAC225ND"


def test_merge_product_list_details_uses_normalized_sku_and_overrides_find_son_sku_values():
    records = [
        {
            "sku": "G-SH-WAC-225-ND",
            "inventory": 0,
            "costprice": 99,
            "salesnum": 0,
        }
    ]
    product_list = [
        {
            "sku": "GSHWAC225ND",
            "inventory": 12,
            "costprice": 7.5,
            "singledaysales": 3,
            "pic3": "https://erp.example/real.jpg",
        }
    ]

    merged = erp_image_search.merge_product_list_details(records, product_list)

    assert merged[0]["inventory"] == 12
    assert merged[0]["costprice"] == 7.5
    assert merged[0]["singledaysales"] == 3
    assert merged[0]["pic3"] == "https://erp.example/real.jpg"


def test_sub_sku_client_fetch_merges_find_son_sku_with_product_list_details(monkeypatch):
    client = erp_image_search.ErpSubSkuClient(token="token")
    monkeypatch.setattr(
        client,
        "_fetch_find_son_sku",
        lambda main_sku: [{"sku": "G-SH-WAC-225-ND", "inventory": 0, "costprice": 99}],
    )
    monkeypatch.setattr(
        client,
        "_fetch_product_list",
        lambda main_sku: [{"sku": "GSHWAC225ND", "inventory": 12, "costprice": 7.5}],
    )

    rows = client.fetch("G-SH-WAC-225")

    assert rows[0]["inventory"] == 12
    assert rows[0]["costprice"] == 7.5


def test_extract_product_records_accepts_sub_sku_list_aliases():
    records = erp_image_search._extract_product_records(
        {"data": {"skuList": [{"sku": "ERP-1"}, {"sku": "ERP-2"}]}}
    )

    assert [row["sku"] for row in records] == ["ERP-1", "ERP-2"]


def test_extract_login_access_token_from_nested_payload():
    token = erp_image_search.extract_login_access_token(
        {"code": 200, "data": {"accessToken": "eyJ.token.value", "expireTime": 1}}
    )

    assert token == "eyJ.token.value"


def test_build_seerfar_enriched_report_rows_preserves_source_and_appends_best_erp_match():
    source_rows = [
        {
            "source_rank": "1",
            "sku": "OZ1",
            "product_name": "Ozon Chair",
            "image_url": "https://img.example/oz1.jpg",
            "product_url": "https://www.ozon.ru/product/1",
            "brand": "BrandA",
            "category": "折叠椅\nСтул",
            "sale_mode": "跨境卖家可售",
            "price": "100",
            "currency": "RUB",
            "sales": "88",
            "sales_revenue": "8800",
            "gross_margin": "45",
            "review_count": "12",
            "review_rating": "4.8",
            "weight": "1.2kg",
            "volume": "10x20x30",
            "seller_name": "ShopA",
            "seller_type": "跨境",
            "delivery_method": "FBS",
        }
    ]
    match_rows = [
        {
            "external_sku": "OZ1",
            "matched_erp_sku": "ERP-LOW",
            "matched_main_sku": "MAIN-LOW",
            "erp_product_status_text": "正常商品",
            "erp_image_url": "https://erp.example/low.jpg",
            "similarity": "0.91",
            "embedding_similarity": "0.60",
            "match_rank": "1",
            "erp_total_inventory": "3",
            "erp_sales_num": "5",
        },
        {
            "external_sku": "OZ1",
            "matched_erp_sku": "ERP-HIGH",
            "matched_main_sku": "MAIN-HIGH",
            "erp_product_status_text": "停产商品",
            "erp_image_url": "https://erp.example/high.jpg",
            "similarity": "0.72",
            "embedding_similarity": "0.92",
            "match_rank": "2",
            "erp_weight": "1.1kg",
            "erp_total_inventory": "9",
            "erp_sales_num": "30",
            "erp_cost_price": "20",
            "erp_sell_price": "50",
            "erp_subsku_count": "2",
        },
    ]

    rows = erp_image_search.build_seerfar_enriched_report_rows(source_rows, match_rows)

    assert rows == [
        {
            "排名": "1",
            "SeerFar SKU": "OZ1",
            "SeerFar 标题": "Ozon Chair",
            "SeerFar 主图": "https://img.example/oz1.jpg",
            "SeerFar 商品链接": "https://www.ozon.ru/product/1",
            "品牌": "BrandA",
            "类目": "折叠椅\nСтул",
            "销售方式": "跨境卖家可售",
            "SeerFar 售价": "100",
            "币种": "RUB",
            "SeerFar 销量": "88",
            "SeerFar 销售额": "8800",
            "SeerFar 毛利率": "45",
            "SeerFar 评论数": "12",
            "SeerFar 评分": "4.8",
            "SeerFar 重量": "1.2kg",
            "SeerFar 体积": "10x20x30",
            "店铺": "ShopA",
            "卖家类型": "跨境",
            "配送方式": "FBS",
            "匹配判定": "高置信匹配",
            "嵌入相似度": "0.92",
            "ERP以图搜索相似度": "0.72",
            "ERP候选排名": "2",
            "ERP子SKU": "ERP-HIGH",
            "ERP主SKU": "MAIN-HIGH",
            "ERP商品状态": "停产商品",
            "ERP图片链接": "https://erp.example/high.jpg",
            "ERP库存": "9",
            "ERP销量": "30",
            "ERP子SKU数量": "2",
            "建议动作": "高置信同款，先确认 ERP 状态、库存和供应链；正常在售则不作为新品，停产/缺货可评估恢复或替代开发",
        }
    ]


def test_build_seerfar_enriched_report_marks_unsearched_rows_separately():
    rows = erp_image_search.build_seerfar_enriched_report_rows(
        [{"sku": "OZ2", "product_name": "Not searched"}],
        [],
    )

    assert rows[0]["匹配判定"] == "未参与本次匹配"
    assert rows[0]["建议动作"] == "本次样本未覆盖；正式判断前需要先执行 ERP 以图搜索和 DINOv2 精筛"


def test_build_seerfar_enriched_report_backfills_status_from_subsku_json():
    rows = erp_image_search.build_seerfar_enriched_report_rows(
        [{"sku": "OZ3", "product_name": "Status fallback"}],
        [
            {
                "external_sku": "OZ3",
                "matched_erp_sku": "ERP-3",
                "embedding_similarity": "0.91",
                "erp_subsku_json": json.dumps(
                    [{"sku": "ERP-3", "status": 8}],
                    ensure_ascii=False,
                ),
            }
        ],
    )

    assert rows[0]["ERP商品状态"] == "正常商品"


def test_seerfar_boss_report_rows_keeps_only_actionable_matches():
    rows = [
        {"SeerFar SKU": "HIGH", "匹配判定": "高置信匹配"},
        {"SeerFar SKU": "POSSIBLE", "匹配判定": "可能匹配"},
        {"SeerFar SKU": "WEAK", "匹配判定": "弱匹配(需人工)"},
        {"SeerFar SKU": "NONE", "匹配判定": "无匹配(疑似不同款)"},
        {"SeerFar SKU": "NO_IMAGE", "匹配判定": "无图(竞品图失败)"},
        {"SeerFar SKU": "UNSEARCHED", "匹配判定": "未参与本次匹配"},
    ]

    kept_rows = erp_image_search._seerfar_boss_report_rows(rows)

    assert [row["SeerFar SKU"] for row in kept_rows] == ["HIGH", "POSSIBLE"]


def test_generate_seerfar_enriched_report_writes_only_actionable_matches(tmp_path):
    input_dir = tmp_path / "input" / "seerfar" / "ozon_hot"
    output_dir = tmp_path / "output" / "image_search" / "seerfar" / "ozon_hot"
    input_dir.mkdir(parents=True)
    output_dir.mkdir(parents=True)
    with (input_dir / "seerfar_products.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(f, fieldnames=["sku", "product_name", "image_url"])
        writer.writeheader()
        writer.writerows([
            {"sku": "HIGH", "product_name": "High", "image_url": "https://img.example/high.jpg"},
            {"sku": "POSSIBLE", "product_name": "Possible", "image_url": "https://img.example/possible.jpg"},
            {"sku": "WEAK", "product_name": "Weak", "image_url": "https://img.example/weak.jpg"},
            {"sku": "NONE", "product_name": "None", "image_url": "https://img.example/none.jpg"},
            {"sku": "UNSEARCHED", "product_name": "Unsearched", "image_url": "https://img.example/unsearched.jpg"},
        ])
    with (output_dir / "erp_image_search_results.csv").open("w", newline="", encoding="utf-8") as f:
        writer = csv.DictWriter(
            f,
            fieldnames=[
                "external_sku",
                "matched_erp_sku",
                "embedding_similarity",
                "similarity",
                "match_rank",
            ],
        )
        writer.writeheader()
        writer.writerows([
            {"external_sku": "HIGH", "matched_erp_sku": "ERP-H", "embedding_similarity": "0.91", "similarity": "0.8", "match_rank": "1"},
            {"external_sku": "POSSIBLE", "matched_erp_sku": "ERP-P", "embedding_similarity": "0.75", "similarity": "0.7", "match_rank": "1"},
            {"external_sku": "WEAK", "matched_erp_sku": "ERP-W", "embedding_similarity": "0.60", "similarity": "0.6", "match_rank": "1"},
            {"external_sku": "NONE", "matched_erp_sku": "ERP-N", "embedding_similarity": "0.20", "similarity": "0.2", "match_rank": "1"},
        ])

    result = erp_image_search.generate_seerfar_enriched_report(
        product_type="ozon_hot",
        base_dir=tmp_path,
    )

    with Path(result["csv"]).open(newline="", encoding="utf-8") as f:
        report_rows = list(csv.DictReader(f))
    assert result["products"] == 2
    assert result["verdicts"] == {"高置信匹配": 1, "可能匹配": 1}
    assert [row["SeerFar SKU"] for row in report_rows] == ["HIGH", "POSSIBLE"]
