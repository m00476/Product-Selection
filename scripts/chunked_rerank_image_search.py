import argparse
import csv
import math
from pathlib import Path

from sourcing.collect.api_common import write_csv
from sourcing.erp_image_search import RESULT_FIELDS, _fields_with_extras, _read_csv_dicts, output_csv_path
from sourcing.rerank.embed import EXTRA_FIELDS, build_embedder, rerank_rows, resolve_embedding_batch_size
from sourcing.rerank.checkpoint import should_checkpoint


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--source", required=True)
    parser.add_argument("--product-type", required=True)
    parser.add_argument("--base-dir", default=".")
    parser.add_argument("--threshold", type=float, default=0.85)
    parser.add_argument("--chunk-size", type=int, default=250)
    parser.add_argument("--checkpoint-every", type=int, default=4,
                        help="每处理多少个分块写一次完整检查点，默认 4")
    parser.add_argument("--embedding-batch-size", type=int, default=0,
                        help="DINOv2 每次推理的图片数量；0=自动(CPU单张/CUDA四张)")
    parser.add_argument("--max-chunks", type=int, default=None,
                        help="本次最多处理多少个含待精筛数据的分块；用于可恢复的长任务")
    parser.add_argument("--limit", type=int, default=None)
    args = parser.parse_args()

    path = output_csv_path(args.base_dir, args.source, args.product_type)
    rows = _read_csv_dicts(path)
    if args.limit is not None:
        rows = rows[: args.limit]
    if args.chunk_size < 1:
        raise ValueError("chunk-size must be at least 1")
    if args.max_chunks is not None and args.max_chunks < 1:
        raise ValueError("max-chunks must be at least 1")

    batch_size = resolve_embedding_batch_size(args.embedding_batch_size)
    embedder, matcher = build_embedder(
        product_type=args.product_type,
        batch_size=batch_size,
    )
    print(f"embedding_batch_size={batch_size}", flush=True)
    total = len(rows)
    processed = 0
    skipped = 0
    total_chunks = math.ceil(total / args.chunk_size) if total else 0
    dirty = False
    completed_pending_chunks = 0
    for chunk_number, start in enumerate(range(0, total, args.chunk_size), start=1):
        end = min(start + args.chunk_size, total)
        chunk = rows[start:end]
        # embedding_confident=0 also represents an attempted-but-unavailable image.
        # Do not retry those rows forever merely because similarity is blank.
        pending = [row for row in chunk if row.get("embedding_confident") in ("", None)]
        if not pending:
            skipped += len(chunk)
            continue
        reranked = rerank_rows(pending, embedder, threshold=args.threshold)
        reranked_by_key = {
            (
                row.get("external_sku", ""),
                row.get("matched_erp_sku", ""),
                row.get("match_rank", ""),
                row.get("erp_image_url", ""),
            ): row
            for row in reranked
        }
        for index in range(start, end):
            row = rows[index]
            key = (
                row.get("external_sku", ""),
                row.get("matched_erp_sku", ""),
                row.get("match_rank", ""),
                row.get("erp_image_url", ""),
            )
            if key in reranked_by_key:
                rows[index] = reranked_by_key[key]
                processed += 1
        dirty = True
        completed_pending_chunks += 1
        if should_checkpoint(chunk_number, total_chunks, checkpoint_every=args.checkpoint_every):
            fields = _fields_with_extras(list(RESULT_FIELDS) + EXTRA_FIELDS, rows)
            write_csv(str(path), rows, fields)
            dirty = False
            print(f"checkpoint chunk={start}-{end} processed={processed} skipped={skipped} output={path}", flush=True)
        if args.max_chunks is not None and completed_pending_chunks >= args.max_chunks:
            break

    if dirty:
        fields = _fields_with_extras(list(RESULT_FIELDS) + EXTRA_FIELDS, rows)
        write_csv(str(path), rows, fields)

    if matcher is not None and hasattr(matcher, "save"):
        matcher.save()
    confident = sum(1 for row in rows if row.get("embedding_confident") == "1")
    print({"reranked": processed, "skipped": skipped, "confident": confident, "output": str(path)})


if __name__ == "__main__":
    main()
