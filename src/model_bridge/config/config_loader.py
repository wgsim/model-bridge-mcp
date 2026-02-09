"""Load and validate model_bridge configuration."""

from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path
from typing import Any

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ConfigError(RuntimeError):
    """Raised when config is missing or invalid."""


class ServiceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exec: list[str] = Field(min_length=1)
    health: list[str] = Field(min_length=1)


class CommandsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codex: ServiceCommand
    gemini: ServiceCommand
    ollama: ServiceCommand


class RoutingChains(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ask_chatgpt_cli: list[str] = Field(min_length=1)
    ask_gemini_cli: list[str] = Field(min_length=1)
    ask_ollama_cloud_fallback: list[str] = Field(min_length=1)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_chains: RoutingChains


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ollama_default_model: str = Field(min_length=1)
    ollama_final_backup_model: str = Field(min_length=1)
    ollama_catalog: list[str] = Field(min_length=1)
    ollama_aliases: dict[str, str] = Field(min_length=1)

    @model_validator(mode="after")
    def validate_ollama_model_links(self) -> "ModelsConfig":
        catalog = set(self.ollama_catalog)
        if self.ollama_default_model not in catalog:
            raise ValueError("models.ollama_default_model must exist in models.ollama_catalog")
        if self.ollama_final_backup_model not in catalog:
            raise ValueError("models.ollama_final_backup_model must exist in models.ollama_catalog")
        for alias, model_name in self.ollama_aliases.items():
            if not alias.strip():
                raise ValueError("models.ollama_aliases keys must be non-empty")
            if model_name not in catalog:
                raise ValueError(
                    f"models.ollama_aliases.{alias} must reference a model in models.ollama_catalog"
                )
        return self


class SecurityConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    block_patterns: list[str] = Field(min_length=1)
    sensitive_paths: list[str] = Field(min_length=1)


class RuntimeApplySystemSuffix(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codex: bool
    gemini: bool
    ollama: bool


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_suffix: str
    apply_system_suffix: RuntimeApplySystemSuffix


class AppConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    commands: CommandsConfig
    routing: RoutingConfig
    models: ModelsConfig
    security: SecurityConfig
    runtime: RuntimeConfig


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


def normalize_config(raw: dict[str, Any]) -> dict[str, Any]:
    try:
        return AppConfig.model_validate(raw).model_dump(mode="python")
    except ValidationError as exc:
        raise ConfigError(f"CONFIG_SCHEMA_ERROR: {exc}") from exc


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
