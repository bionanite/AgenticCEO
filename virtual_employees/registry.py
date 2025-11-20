
from __future__ import annotations

from pathlib import Path
from typing import Dict

import yaml

from .base import VirtualEmployeeConfig


ROLE_CONFIG_DIR = Path(__file__).parent / "role_configs"


def load_role_configs() -> Dict[str, VirtualEmployeeConfig]:
    """
    Load all *.yaml role definitions from role_configs/ into a dict.

    Returns:
        dict mapping role_id -> VirtualEmployeeConfig
    """
    configs: Dict[str, VirtualEmployeeConfig] = {}

    if not ROLE_CONFIG_DIR.exists():
        return configs

    for path in ROLE_CONFIG_DIR.glob("*.yaml"):
        with open(path, "r", encoding="utf-8") as f:
            data = yaml.safe_load(f) or {}
        cfg = VirtualEmployeeConfig(**data)
        configs[cfg.role_id] = cfg

    return configs
