"""精筛长任务的检查点判断。"""


def should_checkpoint(completed_chunks: int, total_chunks: int, *, checkpoint_every: int) -> bool:
    if checkpoint_every < 1:
        raise ValueError("checkpoint_every must be at least 1")
    if total_chunks < 1:
        return False
    return completed_chunks % checkpoint_every == 0 or completed_chunks == total_chunks
