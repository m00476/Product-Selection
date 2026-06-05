import subprocess
from dataclasses import dataclass


@dataclass
class RunResult:
    returncode: int
    stdout: str
    stderr: str


class SubprocessScriptRunner:
    """运行单个脚本的默认实现。测试可注入假实现（鸭子类型：实现 run(...) 即可）。"""

    def run(self, args: list[str], *, cwd: str | None, env: dict) -> RunResult:
        # 显式 UTF-8 解码：518 脚本输出中文，不能用 OS 默认编码(Windows 上是 gbk)，
        # 否则解码报错会掀翻采集（尤其失败时要把 stderr 存进 collector_errors）。
        proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True,
                              encoding="utf-8", errors="replace")
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")
