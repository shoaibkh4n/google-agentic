from functools import lru_cache
import json
from pathlib import Path
from schemas import Settings

@lru_cache
def get_settings() -> Settings:
    config_path = Path(f"secrets.json")

    if not config_path.exists():
        raise FileNotFoundError(f"secrets.json not found")

    with open(config_path) as f:
        config_data = json.load(f)

    return Settings(**config_data)