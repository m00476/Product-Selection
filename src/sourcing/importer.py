import psycopg

from sourcing.readers.common import read_csv_rows
from sourcing.readers.erp import read_erp
from sourcing.readers.ixspy import read_ixspy
from sourcing.readers.seerfar import read_seerfar
from sourcing.repository import (
    insert_raw_record, upsert_product, insert_price_snapshot,
    insert_sales_snapshot, link_source_record, find_erp_product_id,
    upsert_erp_sku,
)


def import_seerfar_csv(conn: psycopg.Connection, path: str, *, product_type: str,
                       source_file: str) -> dict:
    products, prices, sales = read_seerfar(path, product_type)
    rows = read_csv_rows(path)
    count = 0
    for row, product, price, sale in zip(rows, products, prices, sales):
        raw_id = insert_raw_record(
            conn, source=product.source, platform=product.platform,
            product_type=product_type, source_file=source_file,
            source_record_id=product.source_record_id, raw_payload=row,
        )
        product_id = upsert_product(conn, product)
        insert_price_snapshot(conn, product_id, price, raw_id)
        insert_sales_snapshot(conn, product_id, sale, raw_id)
        link_source_record(conn, product, product_id=product_id, raw_id=raw_id)
        count += 1
    return {"products": count}


def import_ixspy_csv(conn: psycopg.Connection, path: str, *, product_type: str,
                     source_file: str) -> dict:
    products, prices, sales = read_ixspy(path, product_type)
    rows = read_csv_rows(path)
    count = 0
    for row, product, price, sale in zip(rows, products, prices, sales):
        raw_id = insert_raw_record(
            conn, source=product.source, platform=product.platform,
            product_type=product_type, source_file=source_file,
            source_record_id=product.source_record_id, raw_payload=row,
        )
        product_id = upsert_product(conn, product)
        insert_price_snapshot(conn, product_id, price, raw_id)
        insert_sales_snapshot(conn, product_id, sale, raw_id)
        link_source_record(conn, product, product_id=product_id, raw_id=raw_id)
        count += 1
    return {"products": count}


def import_erp_csv(conn: psycopg.Connection, path: str, *, product_type: str,
                   source_file: str) -> dict:
    products, skus = read_erp(path, product_type)
    rows = read_csv_rows(path)
    count = 0
    for row, product, sku in zip(rows, products, skus):
        raw_id = insert_raw_record(
            conn, source=product.source, platform=product.platform,
            product_type=product_type, source_file=source_file,
            source_record_id=product.source_record_id, raw_payload=row,
        )
        product_id = find_erp_product_id(conn, sku["sku"]) or upsert_product(conn, product)
        upsert_erp_sku(conn, sku, product_id)
        link_source_record(conn, product, product_id=product_id, raw_id=raw_id)
        count += 1
    return {"products": count, "skus": count}
