"""探测器通用小工具：有界等待 + 类目堵错判定（纯函数，便于测试，不依赖 selenium）。"""
import time


def wait_until(predicate, *, timeout: float, interval: float = 0.5,
               sleep=time.sleep, now=time.monotonic) -> bool:
    """轮询 predicate 直到为真或超时。返回是否在超时前满足。

    替代满屏的固定 sleep：卡死有上限，不会无限等。
    """
    deadline = now() + timeout
    while True:
        if predicate():
            return True
        if now() >= deadline:
            return False
        sleep(interval)


def should_fail_category(category_name, selected: bool) -> bool:
    """是否应在"类目没选中"时 fail-fast。

    指定了类目却没选中 -> True（抓的是错品类，必须报错退出，不能静默抓默认数据）。
    类目留空 -> False（故意抓默认排行榜，是合法用法）。
    """
    return bool((category_name or "").strip()) and not selected
