import json

from sourcing.collect import erp_api_fetch


def test_load_category_config_reads_project_yaml(tmp_path):
    config_path = tmp_path / "erp_categories.yaml"
    config_path.write_text(
        """
bag_accessories:
  name: 箱包配件
  first_catalogue_id: "75004736"
  second_catalogue_id: "2016080911304904065109"
  accepted_categories:
    - 箱包配件
    - 包部件
""".strip(),
        encoding="utf-8",
    )

    config = erp_api_fetch.load_category_config(config_path)

    assert config["bag_accessories"]["name"] == "箱包配件"
    assert config["bag_accessories"]["accepted_categories"] == ["箱包配件", "包部件"]


def test_apply_category_config_injects_catalogue_ids():
    config = {
        "bag_accessories": {
            "name": "箱包配件",
            "first_catalogue_id": "75004736",
            "second_catalogue_id": "2016080911304904065109",
        }
    }

    updated = erp_api_fetch.apply_category_config(
        '{"status":"8","page":1,"limit":100,"isfile":0}',
        "bag_accessories",
        config,
    )

    assert updated["expected_categories"] == ["箱包配件"]
    assert updated["body"]["firstcatalogueid"] == "75004736"
    assert updated["body"]["secondcatalogueid"] == "2016080911304904065109"


def test_validate_output_rows_rejects_empty_result_when_category_expected():
    try:
        erp_api_fetch.validate_output_rows([], expected_categories=["箱包配件"])
    except RuntimeError as error:
        assert "no ERP rows" in str(error)
    else:
        raise AssertionError("empty ERP result was not rejected")


def test_load_product_request_uses_project_candidate_and_output_paths(tmp_path):
    candidate_dir = tmp_path / "output" / "erp" / "bag_accessories"
    candidate_dir.mkdir(parents=True)
    (candidate_dir / "erp_api_candidates.json").write_text(
        json.dumps(
            [
                {
                    "url": "http://example.test/Api/proudect/list",
                    "best_product_score": 80,
                    "best_record_count": 100,
                    "request": {
                        "method": "POST",
                        "url": "http://example.test/Api/proudect/list",
                        "headers": {"Authorization": "redacted"},
                        "postData": '{"status":"8","page":1,"limit":100,"isfile":0}',
                    },
                }
            ]
        ),
        encoding="utf-8",
    )
    config_dir = tmp_path / "configs"
    config_dir.mkdir()
    (config_dir / "erp_categories.yaml").write_text(
        """
bag_accessories:
  name: 箱包配件
  first_catalogue_id: "75004736"
  second_catalogue_id: "2016080911304904065109"
""".strip(),
        encoding="utf-8",
    )

    paths = erp_api_fetch.ProjectPaths(tmp_path, "bag_accessories")
    request = erp_api_fetch.load_product_request(paths)

    assert request.method == "POST"
    assert request.url == "http://example.test/Api/proudect/list"
    assert json.loads(request.body)["firstcatalogueid"] == "75004736"
    assert paths.csv_file == tmp_path / "input" / "erp" / "bag_accessories" / "erp_products.csv"
