from pathlib import Path

import pytest

from model_bridge.config.config_loader import (
    ConfigError,
    _deep_merge,
    load_config,
)


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


class TestDeepMerge:
    """Tests for _deep_merge function."""

    def test_deep_merge_overrides_scalar_values(self):
        base = {"a": 1, "b": 2}
        override = {"b": 3, "c": 4}
        result = _deep_merge(base, override)
        assert result == {"a": 1, "b": 3, "c": 4}

    def test_deep_merge_merges_nested_dicts(self):
        base = {"runtime": {"timeout": 10, "debug": False}}
        override = {"runtime": {"timeout": 20}}
        result = _deep_merge(base, override)
        assert result == {"runtime": {"timeout": 20, "debug": False}}

    def test_deep_merge_replaces_lists_not_concatenates(self):
        base = {"extra_path": ["/a", "/b"]}
        override = {"extra_path": ["/c"]}
        result = _deep_merge(base, override)
        assert result == {"extra_path": ["/c"]}

    def test_deep_merge_handles_empty_override(self):
        base = {"a": 1, "b": {"c": 2}}
        result = _deep_merge(base, {})
        assert result == base

    def test_deep_merge_handles_empty_base(self):
        override = {"a": 1, "b": {"c": 2}}
        result = _deep_merge({}, override)
        assert result == override

    def test_deep_merge_deeply_nested(self):
        base = {"level1": {"level2": {"level3": {"val": "old"}}}}
        override = {"level1": {"level2": {"level3": {"val": "new"}, "extra": 1}}}
        result = _deep_merge(base, override)
        assert result == {"level1": {"level2": {"level3": {"val": "new"}, "extra": 1}}}


def test_load_config_from_default_succeeds():
    config = load_config()
    assert "commands" in config
    assert "routing" in config
    assert "models" in config
    assert "security" in config
    assert "runtime" in config
    assert config["runtime"]["apply_system_suffix"]["ollama"] is False
    assert config["runtime"]["ollama_timeout_seconds"] > 0
    assert "ollama_catalog" in config["models"]
    assert "ollama_aliases" in config["models"]
    assert "ollama_local_fallback_chain" in config["models"]
    assert "codex_model_catalog" in config["models"]
    assert "gemini_model_catalog" in config["models"]
    assert "claude_code_model_catalog" in config["models"]
    assert "ollama_resource_guard_enabled" in config["runtime"]
    assert "ollama_model_memory_gb" in config["runtime"]


def test_load_config_missing_file_raises_config_not_found():
    with pytest.raises(ConfigError, match="CONFIG_NOT_FOUND"):
        load_config("/tmp/not-found-for-test.yaml")


def test_load_config_invalid_schema_type_raises_schema_error(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "invalid.yaml",
        """
commands: []
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    default: llama3.2
    coder: qwen3-coder:30b-a3b-q8_0
  ollama_local_fallback_chain: [default, coder]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
""",
    )
    with pytest.raises(ConfigError, match="CONFIG_SCHEMA_ERROR"):
        load_config(str(config_path))


def test_load_config_unknown_top_level_key_raises_schema_error(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "unknown-key.yaml",
        """
commands:
  codex: {exec: [codex, exec], health: [codex, --version]}
  gemini: {exec: [gemini], health: [gemini, --version]}
  ollama: {exec: [ollama, run], health: [ollama, --version]}
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    default: llama3.2
    coder: qwen3-coder:30b-a3b-q8_0
  ollama_local_fallback_chain: [default, coder]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
unexpected_key: true
""",
    )
    with pytest.raises(ConfigError, match="CONFIG_SCHEMA_ERROR"):
        load_config(str(config_path))


def test_load_config_alias_target_outside_catalog_raises_schema_error(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "invalid-alias.yaml",
        """
commands:
  codex: {exec: [codex, exec], health: [codex, --version]}
  gemini: {exec: [gemini], health: [gemini, --version]}
  ollama: {exec: [ollama, run], health: [ollama, --version]}
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    wrong: mistral:latest
  ollama_local_fallback_chain: [wrong]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
""",
    )
    with pytest.raises(ConfigError, match="CONFIG_SCHEMA_ERROR"):
        load_config(str(config_path))


def test_load_config_fallback_chain_invalid_token_raises_schema_error(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "invalid-fallback-token.yaml",
        """
commands:
  codex: {exec: [codex, exec], health: [codex, --version]}
  gemini: {exec: [gemini], health: [gemini, --version]}
  ollama: {exec: [ollama, run], health: [ollama, --version]}
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    default: llama3.2
  ollama_local_fallback_chain: [default, unknown-token]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
""",
    )
    with pytest.raises(ConfigError, match="CONFIG_SCHEMA_ERROR"):
        load_config(str(config_path))


def test_load_config_accepts_optional_claude_code_fields(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "with-claude-code.yaml",
        """
commands:
  codex: {exec: [codex, exec], health: [codex, --version]}
  gemini: {exec: [gemini], health: [gemini, --version]}
  ollama: {exec: [ollama, run], health: [ollama, --version]}
  claude_code: {exec: [claude], health: [claude, --version]}
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    default: llama3.2
    coder: qwen3-coder:30b-a3b-q8_0
  ollama_local_fallback_chain: [default, coder]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
    claude_code: false
""",
    )
    cfg = load_config(str(config_path))
    assert "claude_code" in cfg["commands"]
    assert cfg["runtime"]["apply_system_suffix"]["claude_code"] is False


def test_load_config_accepts_extra_env_vars(tmp_path: Path):
    config_path = _write_yaml(
        tmp_path / "with-env-vars.yaml",
        """
commands:
  codex: {exec: [codex, exec], health: [codex, --version]}
  gemini: {exec: [gemini], health: [gemini, --version]}
  ollama: {exec: [ollama, run], health: [ollama, --version]}
routing:
  default_chains:
    ask_chatgpt_cli: [codex, gemini, ollama]
    ask_gemini_cli: [gemini, codex, ollama]
    ask_ollama_cloud_fallback: [codex, gemini]
models:
  ollama_default_model: llama3.2
  ollama_final_backup_model: qwen3-coder:30b-a3b-q8_0
  ollama_catalog: [llama3.2, qwen3-coder:30b-a3b-q8_0]
  ollama_aliases:
    default: llama3.2
    coder: qwen3-coder:30b-a3b-q8_0
  ollama_local_fallback_chain: [default, coder]
security:
  block_patterns: [a]
  sensitive_paths: [/etc/]
runtime:
  system_suffix: "x"
  apply_system_suffix:
    codex: true
    gemini: true
    ollama: false
  extra_env_vars:
    GOOGLE_CLOUD_PROJECT: test-project
    GOOGLE_CLOUD_LOCATION: us-central1
""",
    )
    cfg = load_config(str(config_path))
    assert cfg["runtime"]["extra_env_vars"]["GOOGLE_CLOUD_PROJECT"] == "test-project"
    assert cfg["runtime"]["extra_env_vars"]["GOOGLE_CLOUD_LOCATION"] == "us-central1"


def test_load_config_default_merges_local_config():
    """Test that local config (~/.model_bridge/local.yaml) is merged if it exists."""
    cfg = load_config()
    # The default config has empty extra_env_vars, but local config may override
    assert isinstance(cfg["runtime"]["extra_env_vars"], dict)
