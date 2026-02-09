"""Load and validate model_bridge configuration."""

from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path
from typing import Any

import yaml


class ConfigError(RuntimeError):
    """Raised when config is missing or invalid."""


def _load_yaml_from_path(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise ConfigError(f"CONFIG_NOT_FOUND: {path}")
    try:
        content = path.read_text(encoding="utf-8")
    except OSError as exc:
        raise ConfigError(f"CONFIG_READ_ERROR: {path}: {exc}") from exc
    return _parse_yaml(content, source=str(path))


def _load_default_yaml() -> dict[str, Any]:
    try:
        content = resources.files("model_bridge.config").joinpath("default.yaml").read_text(
            encoding="utf-8"
        )
    except Exception as exc:  # pragma: no cover - depends on packaging/runtime
        raise ConfigError(f"DEFAULT_CONFIG_LOAD_ERROR: {exc}") from exc
    return _parse_yaml(content, source="model_bridge.config/default.yaml")


def _parse_yaml(content: str, source: str) -> dict[str, Any]:
    try:
        parsed = yaml.safe_load(content)
    except yaml.YAMLError as exc:
        raise ConfigError(f"CONFIG_PARSE_ERROR: {source}: {exc}") from exc
    if not isinstance(parsed, dict):
        raise ConfigError(f"CONFIG_SCHEMA_ERROR: {source}: top-level must be a mapping")
    return parsed


def _require_str_list(raw: Any, key_path: str) -> list[str]:
    if not isinstance(raw, list) or not raw or not all(isinstance(item, str) for item in raw):
        raise ConfigError(f"CONFIG_SCHEMA_ERROR: {key_path} must be a non-empty list[str]")
    return raw


def _validate_commands(raw: Any) -> dict[str, dict[str, list[str]]]:
    required_services = ("codex", "gemini", "ollama")
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: commands must be a mapping")
    normalized: dict[str, dict[str, list[str]]] = {}
    for service in required_services:
        service_cfg = raw.get(service)
        if not isinstance(service_cfg, dict):
            raise ConfigError(f"CONFIG_SCHEMA_ERROR: commands.{service} must be a mapping")
        exec_cmd = _require_str_list(service_cfg.get("exec"), f"commands.{service}.exec")
        health_cmd = _require_str_list(service_cfg.get("health"), f"commands.{service}.health")
        normalized[service] = {"exec": exec_cmd, "health": health_cmd}
    return normalized


def _validate_routing(raw: Any) -> dict[str, dict[str, list[str]]]:
    required_chain_keys = ("ask_chatgpt_cli", "ask_gemini_cli", "ask_ollama_cloud_fallback")
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: routing must be a mapping")
    chains = raw.get("default_chains")
    if not isinstance(chains, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: routing.default_chains must be a mapping")
    normalized_chains: dict[str, list[str]] = {}
    for chain_key in required_chain_keys:
        normalized_chains[chain_key] = _require_str_list(
            chains.get(chain_key), f"routing.default_chains.{chain_key}"
        )
    return {"default_chains": normalized_chains}


def _validate_models(raw: Any) -> dict[str, str]:
    required_keys = ("ollama_default_model", "ollama_final_backup_model")
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: models must be a mapping")
    normalized: dict[str, str] = {}
    for key in required_keys:
        value = raw.get(key)
        if not isinstance(value, str) or not value.strip():
            raise ConfigError(f"CONFIG_SCHEMA_ERROR: models.{key} must be a non-empty string")
        normalized[key] = value
    return normalized


def _validate_security(raw: Any) -> dict[str, list[str]]:
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: security must be a mapping")
    block_patterns = _require_str_list(raw.get("block_patterns"), "security.block_patterns")
    sensitive_paths = _require_str_list(raw.get("sensitive_paths"), "security.sensitive_paths")
    return {"block_patterns": block_patterns, "sensitive_paths": sensitive_paths}


def _validate_runtime(raw: Any) -> dict[str, str]:
    if not isinstance(raw, dict):
        raise ConfigError("CONFIG_SCHEMA_ERROR: runtime must be a mapping")
    system_suffix = raw.get("system_suffix")
    if not isinstance(system_suffix, str):
        raise ConfigError("CONFIG_SCHEMA_ERROR: runtime.system_suffix must be a string")
    return {"system_suffix": system_suffix}


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    return {
        "commands": _validate_commands(raw.get("commands")),
        "routing": _validate_routing(raw.get("routing")),
        "models": _validate_models(raw.get("models")),
        "security": _validate_security(raw.get("security")),
        "runtime": _validate_runtime(raw.get("runtime")),
    }


def load_config(config_path: str | None = None) -> dict[str, Any]:
    raw = _load_yaml_from_path(Path(config_path)) if config_path else _load_default_yaml()
    return normalize_config(raw)


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Load model_bridge YAML configuration.")
    parser.add_argument("--config", type=str, default=None, help="Optional YAML file path.")
    parser.add_argument(
        "--pretty",
        action="store_true",
        help="Print normalized config with indentation.",
    )
    return parser


def main() -> int:
    args = _build_parser().parse_args()
    try:
        config = load_config(config_path=args.config)
    except ConfigError as exc:
        print(str(exc))
        return 2
    if args.pretty:
        print(json.dumps(config, indent=2, ensure_ascii=False))
    else:
        print(json.dumps(config, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

