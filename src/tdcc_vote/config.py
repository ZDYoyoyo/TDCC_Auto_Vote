"""讀取 config/selectors.yaml。"""

from __future__ import annotations

from pathlib import Path

import yaml

from .paths import PROJECT_ROOT

DEFAULT_SELECTORS = PROJECT_ROOT / "config" / "selectors.yaml"


def load_selectors(path: Path | None = None) -> dict:
    path = Path(path) if path else DEFAULT_SELECTORS
    if not path.exists():
        raise FileNotFoundError(f"找不到選擇器設定檔：{path}")
    with path.open(encoding="utf-8") as fh:
        data = yaml.safe_load(fh) or {}
    if "login" not in data:
        raise ValueError(f"{path} 缺少 login 區段")
    return data
