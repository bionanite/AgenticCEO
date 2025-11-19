from __future__ import annotations

import os
from pathlib import Path
from typing import Optional, Union

_ENV_LOADED = False


def load_env(dotenv_path: Optional[Union[str, Path]] = None) -> None:
    """
    Minimal .env loader so scripts automatically pick up local secrets.

    Parameters
    ----------
    dotenv_path:
        Optional explicit path to the .env file. Defaults to project root.
    """

    global _ENV_LOADED
    if _ENV_LOADED:
        return

    default_path = Path(__file__).resolve().parent / ".env"
    path = Path(dotenv_path) if dotenv_path else default_path

    if not path.exists():
        _ENV_LOADED = True
        return

    for line in path.read_text().splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or "=" not in stripped:
            continue

        key, value = stripped.split("=", 1)
        key = key.strip()
        value = value.strip().strip('"').strip("'")
        if key and key not in os.environ:
            os.environ[key] = value

    _ENV_LOADED = True

