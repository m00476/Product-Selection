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
        "external_price,external_sales,external_review_count,matched_erp_sku,matched_main_sku,candidate_priority\n"
        "ixspy,bag_accessories,1005,Handle wrap,https://example.test/item/1005.html,"
        "https://example.test/img.jpg,12.5,300,20,ERP-OK,OK,可用正常商品\n",
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
    assert csv_rows[0]["final_decision"] == "疑似已有正常同款"
    assert csv_rows[0]["external_price"] == "12.5"
    assert csv_rows[0]["external_sales"] == "300"
    markdown = Path(summary["markdown"]).read_text(encoding="utf-8")
    assert "ERP 以图搜索老板决策报告" in markdown
    assert "Handle wrap" in markdown
    assert "300" in markdown


def test_client_requires_token():
    with pytest.raises(RuntimeError, match="ERP_IMAGE_SEARCH_TOKEN"):
        erp_image_search.ErpImageSearchClient(token="")
