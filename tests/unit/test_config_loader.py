from pathlib import Path

import pytest

from model_bridge.config.config_loader import ConfigError, load_config


def _write_yaml(path: Path, text: str) -> Path:
    path.write_text(text, encoding="utf-8")
    return path


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
