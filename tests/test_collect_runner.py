import os
import sys
from sourcing.collect.runner import SubprocessScriptRunner, RunResult


def test_subprocess_runner_captures_stdout_and_rc(tmp_path):
    runner = SubprocessScriptRunner()
    result = runner.run([sys.executable, "-c", "print('hello-collect')"],
                        cwd=str(tmp_path), env=dict(os.environ))
    assert isinstance(result, RunResult)
    assert result.returncode == 0
    assert "hello-collect" in result.stdout


def test_subprocess_runner_nonzero_rc():
    runner = SubprocessScriptRunner()
    result = runner.run([sys.executable, "-c", "import sys; sys.exit(3)"],
                        cwd=None, env=dict(os.environ))
    assert result.returncode == 3
