"""可断点图搜脚本共用的受控并发执行器。"""

from concurrent.futures import ThreadPoolExecutor
import time
from collections.abc import Callable, Iterable, Iterator
from typing import TypeVar


Row = TypeVar("Row")
Result = TypeVar("Result")


def run_searches(
    rows: Iterable[Row],
    search: Callable[[Row], Result],
    *,
    workers: int = 1,
    delay_seconds: float = 0.0,
    sleep_func: Callable[[float], None] = time.sleep,
) -> Iterator[tuple[int, Row, Result]]:
    """按输入顺序返回图搜结果；等待时间由每个 worker 在请求后执行。

    `workers=1` 与历史串行行为一致。增加 worker 只用于隐藏 ERP 响应等待，
    不改变每个 worker 的请求间隔，调用方可从 2 开始小样本验证。
    """
    if workers < 1:
        raise ValueError("workers must be at least 1")

    def execute(item: tuple[int, Row]) -> tuple[int, Row, Result]:
        index, row = item
        result = search(row)
        if delay_seconds > 0:
            sleep_func(delay_seconds)
        return index, row, result

    indexed_rows = enumerate(rows, start=1)
    if workers == 1:
        for item in indexed_rows:
            yield execute(item)
        return

    with ThreadPoolExecutor(max_workers=workers, thread_name_prefix="erp-image-search") as executor:
        yield from executor.map(execute, indexed_rows)
