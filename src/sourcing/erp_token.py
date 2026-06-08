"""ERP 图搜 token 自动刷新：token 过期时重跑 ERP probe 抓新 Authorization。"""
import json
import os
import sys
from pathlib import Path

from sourcing.collect.runner import SubprocessScriptRunner

_REFRESH_PRODUCT_TYPE = "token_refresh"


def extract_erp_token(candidates_path) -> str | None:
    """从 ERP probe 抓的 candidates JSON 里取 Authorization token。"""
    try:
        cands = json.loads(Path(candidates_path).read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    for cand in cands if isinstance(cands, list) else []:
        headers = (cand.get("request", {}) or {}).get("headers", {}) or {}
        for key, value in headers.items():
            if key.lower() == "authorization" and value:
                return value
    return None


def _persist_token_to_env(token: str) -> None:
    """把新 token 写回最近的 .env(best-effort, 找不到就算了)。"""
    for directory in (Path.cwd(), *Path(__file__).resolve().parents):
        env_path = directory / ".env"
        if env_path.exists():
            lines = env_path.read_text(encoding="utf-8").splitlines()
            out, seen = [], False
            for line in lines:
                if line.startswith("ERP_IMAGE_SEARCH_TOKEN="):
                    out.append("ERP_IMAGE_SEARCH_TOKEN=" + token)
                    seen = True
                else:
                    out.append(line)
            if not seen:
                out.append("ERP_IMAGE_SEARCH_TOKEN=" + token)
            env_path.write_text("\n".join(out) + "\n", encoding="utf-8")
            return


def refresh_erp_token(base_dir: str, *, runner=None, python_exe: str | None = None) -> str | None:
    """重跑 ERP probe 抓新 token，更新 os.environ 与 .env。返回新 token 或 None。"""
    runner = runner or SubprocessScriptRunner()
    python_exe = python_exe or sys.executable
    env = dict(os.environ)
    env["COLLECT_OUTPUT_ROOT"] = base_dir
    env["PRODUCT_TYPE"] = _REFRESH_PRODUCT_TYPE
    runner.run([python_exe, "-m", "sourcing.collect.erp_api_probe"], cwd=base_dir, env=env)
    candidates = Path(base_dir) / "output" / "erp" / _REFRESH_PRODUCT_TYPE / "erp_api_candidates.json"
    token = extract_erp_token(candidates)
    if token:
        os.environ["ERP_IMAGE_SEARCH_TOKEN"] = token
        _persist_token_to_env(token)
    return token
