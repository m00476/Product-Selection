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
        proc = subprocess.run(args, cwd=cwd, env=env, capture_output=True, text=True)
        return RunResult(proc.returncode, proc.stdout or "", proc.stderr or "")
