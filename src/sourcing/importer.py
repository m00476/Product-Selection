from dataclasses import asdict
import psycopg

from sourcing.readers.seerfar import read_seerfar
from sourcing.repository import (
    insert_raw_record, upsert_product, insert_price_snapshot,
    insert_sales_snapshot, link_source_record,
)


def import_seerfar_csv(conn: psycopg.Connection, path: str, *, product_type: str,
                       source_file: str) -> dict:
    products, prices, sales = read_seerfar(path, product_type)
    count = 0
    for product, price, sale in zip(products, prices, sales):
        raw_id = insert_raw_record(
            conn, source=product.source, platform=product.platform,
            product_type=product_type, source_file=source_file,
            source_record_id=product.source_record_id, raw_payload=asdict(product),
        )
        product_id = upsert_product(conn, product)
        insert_price_snapshot(conn, product_id, price, raw_id)
        insert_sales_snapshot(conn, product_id, sale, raw_id)
        link_source_record(conn, product, product_id=product_id, raw_id=raw_id)
        count += 1
    return {"products": count}
