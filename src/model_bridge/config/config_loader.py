"""Load and validate model_bridge configuration."""

from __future__ import annotations

import argparse
import json
from importlib import resources
from pathlib import Path
from typing import Any, Literal

import yaml
from pydantic import BaseModel, ConfigDict, Field, ValidationError, model_validator


class ConfigError(RuntimeError):
    """Raised when config is missing or invalid."""


class ProviderRoutingEntry(BaseModel):
    """Single provider entry in a routing chain with weight."""
    model_config = ConfigDict(extra="forbid")
    provider: str = Field(min_length=1, description="Provider identifier (codex, gemini, ollama, claude_code)")
    weight: int = Field(default=100, ge=1, le=100, description="Provider weight (1-100, higher is preferred)")


class ServiceCommand(BaseModel):
    model_config = ConfigDict(extra="forbid")
    exec: list[str] = Field(min_length=1)
    health: list[str] = Field(min_length=1)


class CommandsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    codex: ServiceCommand
    gemini: ServiceCommand
    ollama: ServiceCommand
    claude_code: ServiceCommand | None = None


class RoutingChains(BaseModel):
    """Legacy routing chains using provider lists (for backward compatibility)."""
    model_config = ConfigDict(extra="forbid")
    ask_chatgpt_cli: list[str] = Field(min_length=1)
    ask_gemini_cli: list[str] = Field(min_length=1)
    ask_ollama_cloud_fallback: list[str] = Field(min_length=1)


class WeightedRoutingChains(BaseModel):
    """Weighted routing chains with provider entries and weights."""
    model_config = ConfigDict(extra="forbid")
    ask_chatgpt_cli: list[ProviderRoutingEntry] | None = Field(default=None, min_length=1)
    ask_gemini_cli: list[ProviderRoutingEntry] | None = Field(default=None, min_length=1)
    ask_ollama_cloud_fallback: list[ProviderRoutingEntry] | None = Field(default=None, min_length=1)


class RoutingConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    default_chains: RoutingChains
    weighted_chains: WeightedRoutingChains | None = Field(default=None, description="Weighted provider chains with traffic distribution")


class ModelsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ollama_default_model: str = Field(min_length=1)
    ollama_final_backup_model: str = Field(min_length=1)
    ollama_catalog: list[str] = Field(min_length=1)
    ollama_aliases: dict[str, str] = Field(min_length=1)
    ollama_local_fallback_chain: list[str] = Field(min_length=1)
    codex_model_catalog: list[str] = Field(default_factory=list)
    gemini_model_catalog: list[str] = Field(default_factory=list)
    claude_code_model_catalog: list[str] = Field(default_factory=list)

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
        alias_keys = set(self.ollama_aliases.keys())
        for token in self.ollama_local_fallback_chain:
            if token not in alias_keys and token not in catalog:
                raise ValueError(
                    "models.ollama_local_fallback_chain entries must be alias keys or catalog model names"
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
    claude_code: bool = False


class AskDefaultsConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    timeout_seconds: float = Field(default=120.0, gt=0)
    max_output_tokens: int = Field(default=0, ge=0)
    response_format: str = Field(default="text")
    verbosity: str = Field(default="normal")
    stream: bool = False
    instruction_preset: str = Field(default="strict_once")
    output_mode: str = Field(default="clean")

    @model_validator(mode="after")
    def validate_enums(self) -> "AskDefaultsConfig":
        if self.response_format not in {"text", "json"}:
            raise ValueError("runtime.ask_defaults.response_format must be one of: text, json")
        if self.verbosity not in {"brief", "normal", "detailed"}:
            raise ValueError(
                "runtime.ask_defaults.verbosity must be one of: brief, normal, detailed"
            )
        if self.instruction_preset not in {"none", "strict_once"}:
            raise ValueError(
                "runtime.ask_defaults.instruction_preset must be one of: none, strict_once"
            )
        if self.output_mode not in {"clean", "raw"}:
            raise ValueError("runtime.ask_defaults.output_mode must be one of: clean, raw")
        return self


class RuntimeConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")
    system_suffix: str
    apply_system_suffix: RuntimeApplySystemSuffix
    transport_mode: Literal["subprocess", "sdk"] = "subprocess"
    subprocess_timeout_seconds: float = Field(default=120.0, gt=0)
    ollama_timeout_seconds: float = Field(default=300.0, gt=0)
    ask_defaults: AskDefaultsConfig = Field(default_factory=AskDefaultsConfig)
    prompt_cache_enabled: bool = True
    prompt_cache_ttl_seconds: int = Field(default=300, ge=1)
    prompt_cache_max_entries: int = Field(default=256, ge=1)
    session_memory_enabled: bool = False
    session_memory_ttl_seconds: int = Field(default=1800, ge=1)
    session_memory_max_turns: int = Field(default=6, ge=1)
    auto_routing_short_prompt_threshold: int = Field(default=120, ge=1)
    ollama_resource_guard_enabled: bool = True
    ollama_resource_guard_default_max_concurrency: int = Field(default=1, ge=1)
    ollama_resource_guard_hard_cap: int = Field(default=2, ge=1)
    ollama_resource_guard_safety_factor: float = Field(default=0.6, gt=0, le=1)
    ollama_resource_guard_reserve_ram_gb: float = Field(default=2.0, ge=0)
    ollama_model_memory_gb: dict[str, float] = Field(default_factory=dict)


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
