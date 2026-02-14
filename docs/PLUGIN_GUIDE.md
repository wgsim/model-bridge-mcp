# Plugin Architecture Guide

This guide explains how to create custom provider plugins for model-bridge-mcp.

## Overview

model-bridge-mcp supports a plugin architecture that allows you to extend it with custom AI providers without modifying the core codebase.

## Plugin Locations

Plugins are loaded from:

1. **Built-in plugins**: `src/model_bridge/plugins/builtins/`
2. **User plugins**: `~/.model_bridge/plugins/`

Each plugin should be in its own subdirectory with a `plugin.py` file.

## Creating a Custom Plugin

### Step 1: Create Plugin Directory

```bash
mkdir -p ~/.model_bridge/plugins/my_provider
```

### Step 2: Create Plugin File

Create `~/.model_bridge/plugins/my_provider/plugin.py`:

```python
from model_bridge.plugins import ProviderPlugin, PluginCapabilities, register_provider

@register_provider
class MyCustomProvider(ProviderPlugin):
    """My custom AI provider."""

    @property
    def provider_id(self) -> str:
        return "my_custom"

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
        """Execute the prompt and return the response."""
        # Your implementation here
        # options contains: timeout_seconds, max_output_tokens, response_format, verbosity, stream

        import asyncio
        # Example: call your API
        response = await call_my_api(prompt, model, options)
        return response

    def is_configured(self) -> bool:
        """Check if the provider is properly configured."""
        import os
        return bool(os.environ.get("MY_API_KEY"))
```

### Step 3: Use Your Plugin

Once the plugin is in place, it will be automatically discovered and loaded. You can use it like any built-in provider:

```python
# Via MCP tool
ask("hello", provider="my_custom")

# With model selection
ask("write code", provider="my_custom", model="my-model-v1")
```

## ProviderPlugin Interface

### Required Methods

| Method | Description |
|--------|-------------|
| `provider_id` | Unique identifier for the provider |
| `execute(prompt, model, options, **kwargs)` | Execute a prompt and return response |

### Optional Methods

| Method | Default | Description |
|--------|---------|-------------|
| `capabilities` | `PluginCapabilities()` | Provider capabilities |
| `is_configured()` | `True` | Check if provider is ready |

### PluginCapabilities

| Property | Default | Description |
|----------|---------|-------------|
| `supports_json` | `True` | Supports JSON response format |
| `supports_stream` | `False` | Supports streaming |
| `supports_force_model` | `True` | Supports force_model option |

## Options Dict

The `options` parameter contains normalized request options:

```python
{
    "timeout_seconds": float,      # Request timeout (default: 120.0)
    "max_output_tokens": int,      # Max output tokens (default: 0 = unlimited)
    "response_format": str,        # "text" or "json"
    "verbosity": str,              # "brief", "normal", or "detailed"
    "stream": bool,                # Whether streaming is requested
}
```

## Example: OpenAI Plugin

```python
import os
import json
from model_bridge.plugins import ProviderPlugin, PluginCapabilities, register_provider

@register_provider
class OpenAIProvider(ProviderPlugin):
    """OpenAI provider using the openai library."""

    @property
    def provider_id(self) -> str:
        return "openai"

    @property
    def capabilities(self) -> PluginCapabilities:
        return PluginCapabilities(
            supports_json=True,
            supports_stream=True,
            supports_force_model=True,
        )

    async def execute(
        self,
        prompt: str,
        model: str | None,
        options: dict,
        **kwargs,
    ) -> str:
        from openai import AsyncOpenAI

        client = AsyncOpenAI()

        response_format = None
        if options.get("response_format") == "json":
            response_format = {"type": "json_object"}

        response = await client.chat.completions.create(
            model=model or "gpt-4",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=options.get("max_output_tokens") or None,
            response_format=response_format,
        )

        return response.choices[0].message.content

    def is_configured(self) -> bool:
        return bool(os.environ.get("OPENAI_API_KEY"))
```

## Debugging

Enable debug logging to see plugin loading:

```python
import logging
logging.basicConfig(level=logging.DEBUG)
```

Check which plugins are loaded:

```python
from model_bridge.plugins import PluginLoader

loader = PluginLoader.instance()
print(loader.list_plugins())
```

## Built-in Plugins

The following providers are included as built-in plugins:

| Provider ID | Description |
|-------------|-------------|
| `codex` | OpenAI Codex via ask_chatgpt_cli |
| `gemini` | Google Gemini via ask_gemini_cli |
| `ollama` | Ollama local models |
| `claude_code` | Anthropic Claude via Claude Code CLI |
