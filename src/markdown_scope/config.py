from __future__ import annotations

from pathlib import Path
from typing import Any

try:
    import tomllib  # py311+
except ModuleNotFoundError:  # pragma: no cover
    import tomli as tomllib  # type: ignore

from .exceptions import MDScopeError


DEFAULT_CONFIG_NAME = "md-scope.toml"


def load_config(config_path: Path | None) -> dict[str, Any]:
    if config_path is None:
        return {}
    if not config_path.exists():
        raise MDScopeError(f"Config file not found: {config_path}")
    try:
        with config_path.open("rb") as fh:
            data = tomllib.load(fh)
    except Exception as exc:  # noqa: BLE001
        raise MDScopeError(f"Failed to parse config file: {config_path}") from exc
    if not isinstance(data, dict):
        raise MDScopeError("Invalid config: top-level value must be a table/object.")
    # Support either flat top-level keys or [global] section.
    if "global" in data and isinstance(data["global"], dict):
        merged = dict(data)
        global_cfg = merged.pop("global")
        for key, value in global_cfg.items():
            merged.setdefault(key, value)
        return merged
    return data


def cfg_value(
    cfg: dict[str, Any],
    key: str,
    cli_value: Any,
    default: Any = None,
) -> Any:
    if cli_value is not None:
        return cli_value
    if key in cfg:
        return cfg[key]
    return default


def cfg_path(
    cfg: dict[str, Any],
    key: str,
    cli_value: Path | None,
    default: Path | None = None,
) -> Path | None:
    value = cfg_value(cfg, key, cli_value, default)
    if value is None:
        return None
    return Path(value)
