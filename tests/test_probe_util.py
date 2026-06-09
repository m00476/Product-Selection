from sourcing.collect.probe_util import wait_until, should_fail_category


def test_wait_until_returns_true_when_predicate_becomes_true():
    calls = {"n": 0}
    def predicate():
        calls["n"] += 1
        return calls["n"] >= 3  # 第3次轮询为真
    slept = []
    ok = wait_until(predicate, timeout=10, interval=0.5,
                    sleep=slept.append, now=lambda: 0.0)
    assert ok is True
    assert calls["n"] == 3
    assert slept == [0.5, 0.5]  # 前两次失败各睡一次


def test_wait_until_returns_false_on_timeout():
    clock = {"t": 0.0}
    def now():
        return clock["t"]
    def sleep(_):
        clock["t"] += 1.0  # 每次睡 1s 推进时钟
    ok = wait_until(lambda: False, timeout=3, interval=1.0, sleep=sleep, now=now)
    assert ok is False


def test_should_fail_category_true_when_name_set_but_not_selected():
    assert should_fail_category("园林工具", selected=False) is True


def test_should_fail_category_false_when_selected():
    assert should_fail_category("园林工具", selected=True) is False


def test_should_fail_category_false_when_name_empty():
    # 故意留空 = 抓默认排行榜，是合法用法，不该 fail
    assert should_fail_category("", selected=False) is False
    assert should_fail_category("   ", selected=False) is False
    assert should_fail_category(None, selected=False) is False
