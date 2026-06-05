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


def test_subprocess_runner_decodes_utf8_output():
    # 子进程输出 UTF-8 中文，不应因 OS 默认编码(gbk)解码崩溃或乱码
    runner = SubprocessScriptRunner()
    code = "import sys; sys.stdout.buffer.write('中文-ok'.encode('utf-8'))"
    result = runner.run([sys.executable, "-c", code], cwd=None, env=dict(os.environ))
    assert result.returncode == 0
    assert "中文-ok" in result.stdout
