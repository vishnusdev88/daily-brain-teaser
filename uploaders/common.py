"""Shared helpers: .env handling and an HTTP wrapper with retries."""
from __future__ import annotations

import os
import time
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
ENV_PATH = ROOT / ".env"

_sleep = time.sleep  # replaced in tests


def load_env(path=None) -> None:
    """Read KEY=value lines from .env into os.environ (real env vars win)."""
    path = Path(path or ENV_PATH)
    if not path.exists():
        return
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        os.environ.setdefault(key.strip(), value.strip().strip('"').strip("'"))


def save_env(key: str, value: str, path=None) -> None:
    """Add or replace KEY=value in .env (created if missing, owner-only permissions)."""
    path = Path(path or ENV_PATH)
    lines = path.read_text(encoding="utf-8").splitlines() if path.exists() else []
    out, done = [], False
    for line in lines:
        if not line.lstrip().startswith("#") and line.split("=", 1)[0].strip() == key:
            out.append(f"{key}={value}")
            done = True
        else:
            out.append(line)
    if not done:
        out.append(f"{key}={value}")
    path.write_text("\n".join(out) + "\n", encoding="utf-8")
    try:
        os.chmod(path, 0o600)
    except OSError:
        pass
    os.environ[key] = value


def need(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing {name} - see SETUP.md")
    return value


class ApiError(RuntimeError):
    def __init__(self, message: str, status: int | None = None):
        super().__init__(message)
        self.status = status


def request(method: str, url: str, *, retries: int = 3, timeout: int = 300, **kwargs):
    """requests.request with retries on network errors, 429 and 5xx; ApiError on any failure.

    Error text never includes the query string, so tokens passed in params stay out of logs.
    """
    last = None
    for attempt in range(retries):
        try:
            resp = requests.request(method, url, timeout=timeout, **kwargs)
        except requests.RequestException as exc:
            last = ApiError(f"{method} {url}: {type(exc).__name__}")
        else:
            if resp.status_code < 400:
                return resp
            last = ApiError(f"{method} {url} -> {resp.status_code}: {resp.text[:500]}",
                            resp.status_code)
            if resp.status_code not in (429, 500, 502, 503, 504):
                raise last
        if attempt < retries - 1:
            _sleep(2 ** (attempt + 1))
    raise last
