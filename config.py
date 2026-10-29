from functools import lru_cache
from pathlib import Path

import yaml

CONFIG_PATH = Path(__file__).resolve().parent / "config.yaml"


@lru_cache(maxsize=1)
def load_config(path: str | Path | None = None) -> dict:
    config_path = Path(path) if path is not None else CONFIG_PATH
    with config_path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)
