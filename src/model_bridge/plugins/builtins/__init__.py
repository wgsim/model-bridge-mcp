"""Built-in provider plugins (P3-1).

These plugins wrap the existing providers (codex, gemini, ollama, claude_code)
to demonstrate the plugin architecture while maintaining backward compatibility.
"""

import asyncio
from typing import TYPE_CHECKING

from model_bridge.plugins import ProviderPlugin, PluginCapabilities, register_provider

if TYPE_CHECKING:
    pass


@register_provider
class CodexPlugin(ProviderPlugin):
    """Plugin wrapper for Codex (ask_chatgpt_cli)."""

    @property
    def provider_id(self) -> str:
        return "codex"

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            supports_json=True,
            supports_stream=False,
            supports_force_model=True,
        )

    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        # Lazy import to avoid circular dependency
        from model_bridge.main import ask_chatgpt_cli

        return await ask_chatgpt_cli(
            prompt=prompt,
            model=model,
            timeout_seconds=options.get("timeout_seconds", 120.0),
            max_output_tokens=options.get("max_output_tokens", 0),
            response_format=options.get("response_format", "text"),
            verbosity=options.get("verbosity", "normal"),
            stream=options.get("stream", False),
            force_model=kwargs.get("force_model", False),
            save_path=kwargs.get("save_path"),
            output_mode=kwargs.get("output_mode", "clean"),
        )


@register_provider
class GeminiPlugin(ProviderPlugin):
    """Plugin wrapper for Gemini (ask_gemini_cli)."""

    @property
    def provider_id(self) -> str:
        return "gemini"

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            supports_json=True,
            supports_stream=False,
            supports_force_model=True,
        )

    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        from model_bridge.main import ask_gemini_cli

        return await ask_gemini_cli(
            prompt=prompt,
            model=model,
            timeout_seconds=options.get("timeout_seconds", 120.0),
            max_output_tokens=options.get("max_output_tokens", 0),
            response_format=options.get("response_format", "text"),
            verbosity=options.get("verbosity", "normal"),
            stream=options.get("stream", False),
            output_mode=kwargs.get("output_mode", "clean"),
        )


@register_provider
class OllamaPlugin(ProviderPlugin):
    """Plugin wrapper for Ollama (ask_ollama)."""

    @property
    def provider_id(self) -> str:
        return "ollama"

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            supports_json=True,
            supports_stream=False,
            supports_force_model=False,
        )

    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        from model_bridge.main import ask_ollama

        return await ask_ollama(
            prompt=prompt,
            model=model,
            timeout_seconds=options.get("timeout_seconds", 120.0),
            max_output_tokens=options.get("max_output_tokens", 0),
            response_format=options.get("response_format", "text"),
            verbosity=options.get("verbosity", "normal"),
            stream=options.get("stream", False),
            output_mode=kwargs.get("output_mode", "clean"),
        )


@register_provider
class ClaudeCodePlugin(ProviderPlugin):
    """Plugin wrapper for Claude Code (ask_claude_code)."""

    @property
    def provider_id(self) -> str:
        return "claude_code"

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            supports_json=True,
            supports_stream=False,
            supports_force_model=True,
        )

    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        from model_bridge.main import ask_claude_code

        return await ask_claude_code(
            prompt=prompt,
            model=model,
            timeout_seconds=options.get("timeout_seconds", 120.0),
            max_output_tokens=options.get("max_output_tokens", 0),
            response_format=options.get("response_format", "text"),
            verbosity=options.get("verbosity", "normal"),
            stream=options.get("stream", False),
            force_model=kwargs.get("force_model", False),
            output_mode=kwargs.get("output_mode", "clean"),
        )
